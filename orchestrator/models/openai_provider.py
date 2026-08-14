"""OpenAI GPT provider implementation."""

import os
from typing import List, Optional

try:
    from openai import OpenAI, APIError, APIConnectionError, RateLimitError
except ImportError:
    raise ImportError("openai package required: pip install openai")

from .base import ModelProvider, ModelConfig, Message, Role


class OpenAIProvider(ModelProvider):
    """OpenAI GPT provider.
    
    Supports latest models:
    - gpt-4o (recommended - multimodal, fastest, cheapest)
    - gpt-4-turbo
    - gpt-3.5-turbo
    
    Model versions are easily swappable via OPENAI_MODEL environment variable.
    """

    def __init__(self, config: ModelConfig):
        """Initialize OpenAI provider.
        
        Args:
            config: ModelConfig with OpenAI API key
        """
        super().__init__(config)
        self.client = OpenAI(api_key=config.api_key)

    def validate_config(self, config: ModelConfig) -> bool:
        """Validate OpenAI configuration.
        
        Args:
            config: ModelConfig to validate
            
        Returns:
            True if valid API key present
        """
        if not config.api_key:
            raise ValueError("OpenAI API key required")
        if not config.model_name:
            config.model_name = "gpt-4o"  # Latest recommended model
        return True

    def complete(self, messages: List[Message]) -> str:
        """Call OpenAI API and get response.
        
        Args:
            messages: List of Message objects
            
        Returns:
            Response text from OpenAI
            
        Raises:
            APIError: If OpenAI API call fails
        """
        try:
            formatted_messages = self.format_messages_for_api(messages)
            
            response = self.client.chat.completions.create(
                model=self.config.model_name,
                messages=formatted_messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout=self.config.timeout,
            )
            
            return response.choices[0].message.content
            
        except (APIError, APIConnectionError, RateLimitError) as e:
            raise Exception(f"OpenAI API error: {str(e)}")

    def get_model_name(self) -> str:
        """Return OpenAI model name.
        
        Returns:
            Model identifier
        """
        return self.config.model_name or "gpt-4o"

    @staticmethod
    def from_env() -> "OpenAIProvider":
        """Create provider from environment variables.
        
        Expects:
        - OPENAI_API_KEY: OpenAI API key (required)
        - OPENAI_MODEL (optional): Model name (default: gpt-4o)
          Current recommended models:
          - gpt-4o (latest, multimodal, recommended)
          - gpt-4-turbo (legacy, still available)
          - gpt-3.5-turbo (cost-effective)
        - OPENAI_TEMPERATURE (optional): Temperature 0-2 (default: 0.7)
        - OPENAI_MAX_TOKENS (optional): Max output tokens (default: 2048)
        
        Returns:
            Configured OpenAIProvider instance
            
        Raises:
            ValueError: If required env vars missing
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        config = ModelConfig(
            api_key=api_key,
            model_name=os.getenv("OPENAI_MODEL", "gpt-4o"),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", 0.7)),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", 2048)),
        )
        return OpenAIProvider(config)
