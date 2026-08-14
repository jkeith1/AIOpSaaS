"""Factory for creating model providers based on configuration."""

import os
from typing import Type, Optional

from .base import ModelProvider, ModelConfig
from .openai_provider import OpenAIProvider
from .claude_provider import ClaudeProvider
from .github_copilot_provider import GitHubCopilotProvider


class ModelProviderFactory:
    """Factory for instantiating LLM providers.
    
    Automatically detects provider based on environment variables or explicit selection.
    
    Usage:
        # Auto-detect from env (checks GITHUB_TOKEN, OPENAI_API_KEY, ANTHROPIC_API_KEY)
        provider = ModelProviderFactory.create()
        
        # Explicit provider
        provider = ModelProviderFactory.create(provider="github-copilot")
        
        # Custom config
        config = ModelConfig(api_key="...", model_name="gpt-4-turbo")
        provider = ModelProviderFactory.create(provider="github-copilot", config=config)
        
        # Register custom provider
        ModelProviderFactory.register_provider("bedrock", BedrockProvider)
        provider = ModelProviderFactory.create(provider="bedrock")
    """

    _providers = {
        "github-copilot": GitHubCopilotProvider,
        "copilot": GitHubCopilotProvider,
        "openai": OpenAIProvider,
        "gpt": OpenAIProvider,
        "anthropic": ClaudeProvider,
        "claude": ClaudeProvider,
    }

    @classmethod
    def create(
        cls,
        provider: Optional[str] = None,
        config: Optional[ModelConfig] = None,
    ) -> ModelProvider:
        """Create a model provider instance.
        
        Priority for provider detection:
        1. Explicit 'provider' parameter
        2. LLM_PROVIDER environment variable
        3. Auto-detect from API key env vars (GitHub, OpenAI, Anthropic)
        
        Args:
            provider: Provider name ('github-copilot', 'openai', 'claude', etc). If None, auto-detect.
            config: ModelConfig instance. If None, loads from environment.
            
        Returns:
            Configured ModelProvider instance
            
        Raises:
            ValueError: If provider not found or config invalid
            
        Examples:
            # Auto-detect and load from environment
            provider = ModelProviderFactory.create()
            
            # Explicit provider with auto-loaded config
            provider = ModelProviderFactory.create(provider="github-copilot")
            
            # Full custom config
            config = ModelConfig(api_key="ghp_...", model_name="gpt-4-turbo")
            provider = ModelProviderFactory.create(provider="github-copilot", config=config)
        """
        if provider is None:
            provider = cls._detect_provider()
        
        provider_lower = provider.lower()
        if provider_lower not in cls._providers:
            available = ", ".join(sorted(set(cls._providers.keys())))
            raise ValueError(
                f"Unknown provider: '{provider}'. Available: {available}"
            )
        
        provider_class = cls._providers[provider_lower]
        
        if config is None:
            # Try to load from environment using provider's from_env() if available
            if hasattr(provider_class, "from_env"):
                return provider_class.from_env()
            else:
                raise ValueError(
                    f"No configuration provided and {provider} has no from_env() method"
                )
        
        return provider_class(config)

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[ModelProvider],
    ) -> None:
        """Register a custom provider.
        
        This allows extending the factory with new LLM providers without modifying
        the factory code. Simply implement ModelProvider and register it.
        
        Args:
            name: Provider identifier (e.g., 'cohere', 'bedrock', 'ollama')
            provider_class: Class that inherits from ModelProvider
            
        Raises:
            TypeError: If provider_class doesn't inherit from ModelProvider
            
        Examples:
            # Register Bedrock provider
            class BedrockProvider(ModelProvider):
                ...
            
            ModelProviderFactory.register_provider("bedrock", BedrockProvider)
            provider = ModelProviderFactory.create(provider="bedrock")
        """
        if not issubclass(provider_class, ModelProvider):
            raise TypeError(
                f"{provider_class.__name__} must inherit from ModelProvider"
            )
        cls._providers[name.lower()] = provider_class

    @staticmethod
    def _detect_provider() -> str:
        """Auto-detect provider from environment variables.
        
        Detection priority:
        1. Explicit LLM_PROVIDER env var
        2. GITHUB_TOKEN → 'github-copilot'
        3. OPENAI_API_KEY → 'openai'
        4. ANTHROPIC_API_KEY → 'anthropic'
        
        Returns:
            Provider name (lowercase)
            
        Raises:
            ValueError: If no provider can be detected
        """
        # Explicit provider specification takes priority
        if os.getenv("LLM_PROVIDER"):
            return os.getenv("LLM_PROVIDER")
        
        # Auto-detect from API keys (order matters - check most specific first)
        # Prioritize GitHub Copilot if token is available
        if os.getenv("GITHUB_TOKEN"):
            return "github-copilot"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        if os.getenv("ANTHROPIC_API_KEY"):
            return "anthropic"
        
        raise ValueError(
            "Could not auto-detect LLM provider. Set one of:\n"
            "  - GITHUB_TOKEN (detected as 'github-copilot') - easiest if you have GitHub Copilot\n"
            "  - OPENAI_API_KEY (detected as 'openai')\n"
            "  - ANTHROPIC_API_KEY (detected as 'anthropic')\n"
            "  - LLM_PROVIDER (explicit: 'github-copilot', 'openai', 'claude', etc)\n"
        )
