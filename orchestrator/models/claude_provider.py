"""Anthropic Claude provider implementation.

Uses the Anthropic Messages API directly (synchronous). This is the default
provider for the AIOps agent: no extra runtime beyond the `anthropic` package.

For an agentic loop where Claude drives kubectl itself, see
``claude_agent_provider.ClaudeAgentProvider`` (provider name ``claude-agent``).
"""

import logging
import os
import random
import time
from typing import List, Optional, Tuple

from .base import ModelProvider, ModelConfig, Message, Role

logger = logging.getLogger(__name__)

# Current Anthropic model identifiers.
#   claude-opus-5             - most capable, complex agentic work
#   claude-sonnet-5           - best speed/intelligence balance (default here)
#   claude-haiku-4-5-20251001 - fastest / cheapest
DEFAULT_MODEL = "claude-sonnet-5"

MODEL_ALIASES = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5-20251001",
}


def _first_env(*names: str, default: Optional[str] = None) -> Optional[str]:
    """Return the first non-empty environment variable among ``names``."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


class ClaudeProvider(ModelProvider):
    """Anthropic Claude provider.

    Model is selectable via env (``CLAUDE_MODEL``/``ANTHROPIC_MODEL``/``LLM_MODEL``)
    or ``ModelConfig.model_name``. Short aliases ``opus``/``sonnet``/``haiku``
    are accepted and expanded.
    """

    #: Number of attempts for transient (overloaded / rate limit / connection) errors.
    MAX_ATTEMPTS = 4

    def __init__(self, config: ModelConfig):
        """Initialize Claude provider.

        Args:
            config: ModelConfig with Anthropic API key

        Raises:
            ImportError: If the `anthropic` package is not installed.
            ValueError: If the configuration is invalid.
        """
        super().__init__(config)

        # Imported lazily so that merely importing this module (e.g. from the
        # provider factory) does not require the SDK to be installed.
        try:
            from anthropic import Anthropic
        except ImportError as exc:  # pragma: no cover - exercised via packaging
            raise ImportError(
                "anthropic package required: pip install 'anthropic>=0.40.0'"
            ) from exc

        self.client = Anthropic(api_key=config.api_key, timeout=config.timeout)

    # ------------------------------------------------------------------
    # ModelProvider interface
    # ------------------------------------------------------------------

    def validate_config(self, config: ModelConfig) -> bool:
        """Validate Claude configuration, filling in defaults in place."""
        if not config.api_key:
            raise ValueError(
                "Anthropic API key required (set ANTHROPIC_API_KEY or LLM_API_KEY)"
            )

        model = config.model_name or DEFAULT_MODEL
        config.model_name = MODEL_ALIASES.get(model.lower(), model)

        if not 0.0 <= config.temperature <= 1.0:
            raise ValueError(
                f"temperature must be between 0.0 and 1.0, got {config.temperature}"
            )
        if config.max_tokens < 1:
            raise ValueError(f"max_tokens must be positive, got {config.max_tokens}")
        return True

    def complete(self, messages: List[Message]) -> str:
        """Send messages to Claude and return the response text.

        System messages are extracted into the top-level ``system`` parameter,
        which is what the Anthropic Messages API expects; passing ``role:
        "system"`` inside ``messages`` is rejected by the API.

        Args:
            messages: Conversation history.

        Returns:
            Claude's response as plain text.

        Raises:
            RuntimeError: If the API call fails after retries.
        """
        from anthropic import APIConnectionError, APIStatusError, RateLimitError

        system_prompt, api_messages = self._split_system(messages)
        if not api_messages:
            raise ValueError("At least one user or assistant message is required")

        kwargs = {
            "model": self.config.model_name,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": api_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        last_error: Optional[Exception] = None
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = self.client.messages.create(**kwargs)
                return self._extract_text(response)

            except (RateLimitError, APIConnectionError) as exc:
                last_error = exc
                retryable = True
            except APIStatusError as exc:
                last_error = exc
                # 429 and 5xx are worth retrying; 4xx client errors are not.
                retryable = exc.status_code == 429 or exc.status_code >= 500
            except Exception as exc:  # noqa: BLE001 - surfaced below
                raise RuntimeError(f"Anthropic API error: {exc}") from exc

            if not retryable or attempt == self.MAX_ATTEMPTS:
                break

            backoff = min(2 ** attempt, 30) + random.uniform(0, 1)
            logger.warning(
                "Anthropic call failed (attempt %d/%d): %s - retrying in %.1fs",
                attempt,
                self.MAX_ATTEMPTS,
                last_error,
                backoff,
            )
            time.sleep(backoff)

        raise RuntimeError(
            f"Anthropic API error after {self.MAX_ATTEMPTS} attempts: {last_error}"
        )

    def get_model_name(self) -> str:
        """Return the resolved Claude model identifier."""
        return self.config.model_name or DEFAULT_MODEL

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_system(messages: List[Message]) -> Tuple[str, List[dict]]:
        """Split system messages out and normalise the rest for the API.

        The Anthropic Messages API requires:
          * system instructions in a separate top-level ``system`` parameter
          * ``messages`` to contain only user/assistant turns
          * the first turn to be ``user``, with roles alternating

        Consecutive same-role messages are merged so callers can build message
        lists naturally without tripping the alternation rule.
        """
        system_parts: List[str] = []
        turns: List[dict] = []

        for msg in messages:
            content = (msg.content or "").strip()
            if not content:
                continue

            if msg.role == Role.SYSTEM:
                system_parts.append(content)
                continue

            role = msg.role.value
            if turns and turns[-1]["role"] == role:
                turns[-1]["content"] += "\n\n" + content
            else:
                turns.append({"role": role, "content": content})

        # The API requires the conversation to open with a user turn.
        if turns and turns[0]["role"] != Role.USER.value:
            turns.insert(0, {"role": Role.USER.value, "content": "Continue."})

        return "\n\n".join(system_parts), turns

    @staticmethod
    def _extract_text(response) -> str:
        """Concatenate all text blocks from a Messages API response."""
        parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text"
        ]
        if not parts:
            raise RuntimeError("Anthropic response contained no text content")
        return "".join(parts)

    # ------------------------------------------------------------------
    # Construction from environment
    # ------------------------------------------------------------------

    @staticmethod
    def from_env() -> "ClaudeProvider":
        """Create a provider from environment variables.

        Reads (first match wins):
          * API key:     ANTHROPIC_API_KEY, CLAUDE_API_KEY, LLM_API_KEY
          * Model:       CLAUDE_MODEL, ANTHROPIC_MODEL, LLM_MODEL
          * Temperature: CLAUDE_TEMPERATURE, LLM_TEMPERATURE  (default 0.2)
          * Max tokens:  CLAUDE_MAX_TOKENS, LLM_MAX_TOKENS    (default 4096)
          * Timeout:     LLM_TIMEOUT                          (default 120s)

        The ``LLM_*`` names are what the Helm chart injects, so the same
        deployment works regardless of which provider is selected.
        """
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
            # Triage wants reproducible, low-variance output, not creativity.
            temperature=float(
                _first_env("CLAUDE_TEMPERATURE", "LLM_TEMPERATURE", default="0.2")
            ),
            max_tokens=int(
                _first_env("CLAUDE_MAX_TOKENS", "LLM_MAX_TOKENS", default="4096")
            ),
            timeout=int(_first_env("LLM_TIMEOUT", default="120")),
        )
        return ClaudeProvider(config)
