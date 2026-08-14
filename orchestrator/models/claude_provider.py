"""Anthropic Claude provider implementation."""

import os
from typing import List

try:
    from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
except ImportError:
    raise ImportError("anthropic package required: pip install anthropic")

from .base import ModelProvider, ModelConfig, Message, Role


class ClaudeProvider(ModelProvider):
    """Anthropic Claude provider.
    
    Supports latest models:
    - claude-3-5-sonnet-20241022 (recommended - best price/performance)
    - claude-3-opus-20240229 (most capable)
    - claude-3-haiku-20240307 (fastest/cheapest)
    
    Model versions are easily swappable via CLAUDE_MODEL environment variable.
    """

    def __init__(self, config: ModelConfig):
        """Initialize Claude provider.
        
        Args:
            config: ModelConfig with Anthropic API key
        """
        super().__init__(config)
        self.client = Anthropic(api_key=config.api_key)

    def validate_config(self, config: ModelConfig) -> bool:
        """Validate Claude configuration.
        
        Args:
            config: ModelConfig to validate
            
        Returns:
            True if valid API key present
        """
        if not config.api_key:
            raise ValueError("Anthropic API key required")
        if not config.model_name:
            config.model_name = "claude-3-5-sonnet-20241022"  # Latest recommended
        return True

    def complete(self, messages: List[Message]) -> str:
        """Call Anthropic Claude API and get response.
        
        Args:
            messages: List of Message objects
            
        Returns:
            Response text from Claude
            
        Raises:
            APIError: If Anthropic API call fails
        """
        try:
            formatted_messages = self.format_messages_for_api(messages)
            
            response = self.client.messages.create(
                model=self.config.model_name,
                max_tokens=self.config.max_tokens,
                messages=formatted_messages,
            )
            
            return response.content[0].text
            
        except (APIError, APIConnectionError, RateLimitError) as e:
            raise Exception(f"Anthropic API error: {str(e)}")

    def get_model_name(self) -> str:
        """Return Claude model name.
        
        Returns:
            Model identifier
        """
        return self.config.model_name or "claude-3-5-sonnet-20241022"

    @staticmethod
    def from_env() -> "ClaudeProvider":
        """Create provider from environment variables.
        
        Expects:
        - ANTHROPIC_API_KEY: Claude API key (required)
        - CLAUDE_MODEL (optional): Model name (default: claude-3-5-sonnet-20241022)
          Current recommended models:
          - claude-3-5-sonnet-20241022 (latest, best value)
          - claude-3-opus-20240229 (most powerful)
          - claude-3-haiku-20240307 (fastest)
        - CLAUDE_TEMPERATURE (optional): Temperature 0-1 (default: 0.7)
        - CLAUDE_MAX_TOKENS (optional): Max output tokens (default: 2048)
        
        Returns:
            Configured ClaudeProvider instance
            
        Raises:
            ValueError: If required env vars missing
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        
        config = ModelConfig(
            api_key=api_key,
            model_name=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
            temperature=float(os.getenv("CLAUDE_TEMPERATURE", 0.7)),
            max_tokens=int(os.getenv("CLAUDE_MAX_TOKENS", 2048)),
        )
        return ClaudeProvider(config)
