"""Claude Agent SDK provider - Claude drives the kubectl tools itself.

Where :class:`~.claude_provider.ClaudeProvider` is a one-shot call (you dump
cluster state into a prompt and get text back), this provider hands Claude a
set of read-only Kubernetes tools and lets it decide what to look at: list
pods, pull logs for the one that is crashlooping, describe it, check events,
then conclude. That is the agentic loop the Copilot SDK was being used for.

Runtime requirements (beyond `pip install claude-agent-sdk`):
  * Node.js 18+ on PATH
  * the Claude Code CLI, which the SDK manages/launches as a subprocess

The Containerfile installs both. If either is missing, this provider raises at
construction time and the plain ``claude`` provider remains usable.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from .base import ModelProvider, ModelConfig, Message, Role
from .claude_provider import DEFAULT_MODEL, MODEL_ALIASES, _first_env

logger = logging.getLogger(__name__)

# Claude is told to stay read-only; the RBAC role should enforce the same thing.
DEFAULT_SYSTEM_PROMPT = (
    "You are an AIOps Kubernetes triage agent running inside the cluster you "
    "are diagnosing. Use the provided read-only tools to investigate before "
    "concluding: start broad (objects, events), then narrow to the specific "
    "workloads that look unhealthy and pull their logs and describe output. "
    "Never speculate about a root cause you have not gathered evidence for. "
    "You cannot modify the cluster - recommend fixes, do not attempt them."
)


def _build_k8s_tools():
    """Define the read-only Kubernetes tools exposed to Claude.

    Imported lazily inside the function so that this module can be imported
    for introspection without the SDK present.
    """
    from claude_agent_sdk import tool

    from ..tools import k8s

    @tool(
        "list_objects",
        "List all Kubernetes objects in a namespace, summarised to the fields "
        "that matter for triage (kind, name, status, restarts, age, reason).",
        {"namespace": str},
    )
    async def list_objects(args: Dict[str, Any]) -> Dict[str, Any]:
        summary = await asyncio.to_thread(k8s.summarize_namespace, args["namespace"])
        return {"content": [{"type": "text", "text": summary}]}

    @tool(
        "get_events",
        "Get recent events in a namespace, newest first. Warnings are the "
        "fastest route to a root cause.",
        {"namespace": str},
    )
    async def get_events(args: Dict[str, Any]) -> Dict[str, Any]:
        text = await asyncio.to_thread(k8s.summarize_events, args["namespace"])
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "get_pod_logs",
        "Fetch recent log lines for a pod. Set previous=true to read the logs "
        "of the last terminated container, which is what you want for a "
        "CrashLoopBackOff.",
        {"namespace": str, "pod": str, "previous": bool},
    )
    async def get_pod_logs(args: Dict[str, Any]) -> Dict[str, Any]:
        text = await asyncio.to_thread(
            k8s.get_pod_logs,
            args["namespace"],
            args["pod"],
            tail_lines=200,
            previous=bool(args.get("previous", False)),
        )
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "describe_pod",
        "Run kubectl describe on a pod to see its conditions, container "
        "statuses, probes, volumes and scheduling events.",
        {"namespace": str, "pod": str},
    )
    async def describe_pod(args: Dict[str, Any]) -> Dict[str, Any]:
        text = await asyncio.to_thread(k8s.describe_pod, args["namespace"], args["pod"])
        return {"content": [{"type": "text", "text": text}]}

    @tool(
        "get_object",
        "Fetch the full JSON for one specific object, e.g. resource='deployment' "
        "name='api'. Use this only after narrowing down - it is verbose.",
        {"namespace": str, "resource": str, "name": str},
    )
    async def get_object(args: Dict[str, Any]) -> Dict[str, Any]:
        text = await asyncio.to_thread(
            k8s.get_object_json, args["namespace"], args["resource"], args["name"]
        )
        return {"content": [{"type": "text", "text": text}]}

    return [list_objects, get_events, get_pod_logs, describe_pod, get_object]


class ClaudeAgentProvider(ModelProvider):
    """Claude with tool use, via the Claude Agent SDK."""

    def __init__(self, config: ModelConfig, max_turns: int = 20):
        super().__init__(config)

        try:
            from claude_agent_sdk import create_sdk_mcp_server  # noqa: F401
        except ImportError as exc:  # pragma: no cover - packaging concern
            raise ImportError(
                "claude-agent-sdk package required: pip install claude-agent-sdk "
                "(also needs Node.js and the Claude Code CLI on PATH)"
            ) from exc

        self.max_turns = max_turns
        # The SDK/CLI authenticates from the environment.
        os.environ.setdefault("ANTHROPIC_API_KEY", config.api_key)

    def validate_config(self, config: ModelConfig) -> bool:
        if not config.api_key:
            raise ValueError(
                "Anthropic API key required (set ANTHROPIC_API_KEY or LLM_API_KEY)"
            )
        model = config.model_name or DEFAULT_MODEL
        config.model_name = MODEL_ALIASES.get(model.lower(), model)
        return True

    def get_model_name(self) -> str:
        return self.config.model_name or DEFAULT_MODEL

    # ------------------------------------------------------------------
    # ModelProvider interface
    # ------------------------------------------------------------------

    def complete(self, messages: List[Message]) -> str:
        """Run an agentic turn and return Claude's final text.

        Satisfies the same interface as every other provider, so the existing
        workflows work unchanged - they just get an answer that Claude
        researched with live cluster calls instead of one inferred from a
        single pre-built prompt.
        """
        system_parts = [
            m.content.strip() for m in messages if m.role == Role.SYSTEM and m.content
        ]
        prompt_parts = [
            m.content.strip() for m in messages if m.role != Role.SYSTEM and m.content
        ]
        if not prompt_parts:
            raise ValueError("At least one user message is required")

        system_prompt = "\n\n".join(system_parts) or DEFAULT_SYSTEM_PROMPT
        return self._run(("\n\n".join(prompt_parts)), system_prompt)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run(self, prompt: str, system_prompt: str) -> str:
        """Drive the async SDK from sync code."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run_async(prompt, system_prompt))

        # Already inside an event loop - run in a private one on a worker thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                asyncio.run, self._run_async(prompt, system_prompt)
            ).result()

    async def _run_async(self, prompt: str, system_prompt: str) -> str:
        from claude_agent_sdk import ClaudeAgentOptions, create_sdk_mcp_server, query

        k8s_server = create_sdk_mcp_server(
            name="k8s",
            version="1.0.0",
            tools=_build_k8s_tools(),
        )

        options = ClaudeAgentOptions(
            model=self.get_model_name(),
            system_prompt=system_prompt,
            mcp_servers={"k8s": k8s_server},
            allowed_tools=[
                "mcp__k8s__list_objects",
                "mcp__k8s__get_events",
                "mcp__k8s__get_pod_logs",
                "mcp__k8s__describe_pod",
                "mcp__k8s__get_object",
            ],
            # Only our own read-only tools are allowed; nothing can mutate the
            # cluster or the filesystem.
            permission_mode="default",
            max_turns=self.max_turns,
        )

        chunks: List[str] = []
        async for message in query(prompt=prompt, options=options):
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)

        result = "\n".join(chunks).strip()
        if not result:
            raise RuntimeError("Claude Agent SDK returned no text output")
        return result

    # ------------------------------------------------------------------
    # Construction from environment
    # ------------------------------------------------------------------

    @staticmethod
    def from_env() -> "ClaudeAgentProvider":
        """Create from env. Same variables as ClaudeProvider, plus AGENT_MAX_TURNS."""
        api_key = _first_env("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "LLM_API_KEY")
        if not api_key:
            raise ValueError(
                "No Anthropic API key found. Set ANTHROPIC_API_KEY "
                "(or LLM_API_KEY when using the Helm chart's shared secret)."
            )

        config = ModelConfig(
            api_key=api_key,
            model_name=_first_env(
                "CLAUDE_MODEL", "ANTHROPIC_MODEL", "LLM_MODEL", default=DEFAULT_MODEL
            ),
            temperature=float(
                _first_env("CLAUDE_TEMPERATURE", "LLM_TEMPERATURE", default="0.2")
            ),
            max_tokens=int(
                _first_env("CLAUDE_MAX_TOKENS", "LLM_MAX_TOKENS", default="4096")
            ),
            timeout=int(_first_env("LLM_TIMEOUT", default="300")),
        )
        return ClaudeAgentProvider(
            config, max_turns=int(_first_env("AGENT_MAX_TURNS", default="20"))
        )
