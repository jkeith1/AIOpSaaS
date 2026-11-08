"""Factory for creating model providers based on configuration.

Providers are resolved lazily: a provider module is only imported when that
provider is actually requested. This matters because each provider module
imports a third-party SDK that may not be installed in a given image — with
eager imports, a missing `openai` or `github-copilot-sdk` wheel would break
*every* provider, including Claude.
"""

import importlib
import logging
import os
from typing import Dict, Optional, Type, Union

from .base import ModelProvider, ModelConfig

logger = logging.getLogger(__name__)

# Provider name -> "module:ClassName", imported on demand.
_LAZY_PROVIDERS: Dict[str, str] = {
    # Anthropic Claude via the Messages API (default).
    "claude": ".claude_provider:ClaudeProvider",
    "anthropic": ".claude_provider:ClaudeProvider",
    # Anthropic Claude via the Claude Agent SDK (agentic tool-use loop).
    "claude-agent": ".claude_agent_provider:ClaudeAgentProvider",
    "claude-agent-sdk": ".claude_agent_provider:ClaudeAgentProvider",
    "claude-code": ".claude_agent_provider:ClaudeAgentProvider",
    # OpenAI.
    "openai": ".openai_provider:OpenAIProvider",
    "gpt": ".openai_provider:OpenAIProvider",
    # GitHub Copilot (legacy REST attempt + official SDK).
    "github-copilot": ".github_copilot_provider:GitHubCopilotProvider",
    "copilot": ".github_copilot_provider:GitHubCopilotProvider",
    "copilot-sdk": ".copilot_sdk_provider:CopilotSDKProvider",
    "github-copilot-sdk": ".copilot_sdk_provider:CopilotSDKProvider",
}


class ModelProviderFactory:
    """Factory for instantiating LLM providers.

    Usage:
        # Auto-detect from env (LLM_PROVIDER, then available API keys)
        provider = ModelProviderFactory.create()

        # Explicit provider
        provider = ModelProviderFactory.create(provider="claude")

        # Custom config
        config = ModelConfig(api_key="...", model_name="claude-opus-5")
        provider = ModelProviderFactory.create(provider="claude", config=config)

        # Register custom provider
        ModelProviderFactory.register_provider("bedrock", BedrockProvider)
    """

    #: Explicitly registered classes take precedence over the lazy table.
    _providers: Dict[str, Type[ModelProvider]] = {}

    @classmethod
    def available_providers(cls) -> list:
        """Return every provider name this factory knows about."""
        return sorted(set(_LAZY_PROVIDERS) | set(cls._providers))

    @classmethod
    def _resolve(cls, name: str) -> Type[ModelProvider]:
        """Resolve a provider name to a class, importing it on demand."""
        if name in cls._providers:
            return cls._providers[name]

        target = _LAZY_PROVIDERS.get(name)
        if target is None:
            raise ValueError(
                f"Unknown provider: '{name}'. "
                f"Available: {', '.join(cls.available_providers())}"
            )

        module_path, class_name = target.split(":")
        try:
            module = importlib.import_module(module_path, package=__package__)
        except ImportError as exc:
            raise ImportError(
                f"Provider '{name}' is registered but its dependencies are not "
                f"installed: {exc}"
            ) from exc

        provider_class = getattr(module, class_name)
        cls._providers[name] = provider_class
        return provider_class

    @classmethod
    def create(
        cls,
        provider: Optional[str] = None,
        config: Optional[ModelConfig] = None,
    ) -> ModelProvider:
        """Create a model provider instance.

        Priority for provider detection:
          1. Explicit ``provider`` argument
          2. ``LLM_PROVIDER`` environment variable
          3. Auto-detect from whichever API key is present

        Args:
            provider: Provider name ('claude', 'claude-agent', 'openai', ...).
            config: Explicit config. If None, the provider loads from env.

        Returns:
            A configured ModelProvider instance.
        """
        if provider is None:
            provider = cls._detect_provider()

        name = provider.strip().lower()
        provider_class = cls._resolve(name)
        logger.info("Selected LLM provider: %s (%s)", name, provider_class.__name__)

        if config is None:
            if not hasattr(provider_class, "from_env"):
                raise ValueError(
                    f"No configuration provided and {provider} has no from_env() method"
                )
            return provider_class.from_env()

        return provider_class(config)

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[ModelProvider],
    ) -> None:
        """Register a custom provider class under ``name``."""
        if not issubclass(provider_class, ModelProvider):
            raise TypeError(
                f"{provider_class.__name__} must inherit from ModelProvider"
            )
        cls._providers[name.lower()] = provider_class

    @staticmethod
    def _detect_provider() -> str:
        """Auto-detect the provider from environment variables.

        Detection priority:
          1. LLM_PROVIDER (what the Helm chart sets — always wins)
          2. ANTHROPIC_API_KEY / CLAUDE_API_KEY -> 'claude'
          3. OPENAI_API_KEY                     -> 'openai'
          4. GITHUB_TOKEN                       -> 'copilot-sdk'
        """
        explicit = os.getenv("LLM_PROVIDER")
        if explicit and explicit.strip():
            return explicit.strip()

        if os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"):
            return "claude"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("GITHUB_TOKEN"):
            return "copilot-sdk"

        raise ValueError(
            "Could not auto-detect an LLM provider. Set one of:\n"
            "  - ANTHROPIC_API_KEY  (detected as 'claude')\n"
            "  - OPENAI_API_KEY     (detected as 'openai')\n"
            "  - GITHUB_TOKEN       (detected as 'copilot-sdk')\n"
            "  - LLM_PROVIDER       (explicit: 'claude', 'claude-agent', 'openai', ...)\n"
        )
