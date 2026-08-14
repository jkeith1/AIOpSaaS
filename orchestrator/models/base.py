"""Base abstract model provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Any


class Role(str, Enum):
    """Message roles - standardized across all LLM providers."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """Standardized message format for all LLM providers."""
    role: Role
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role.value, "content": self.content}


@dataclass
class ModelConfig:
    """Common configuration across all LLM providers."""
    api_key: str
    temperature: float = 0.7
    max_tokens: int = 2048
    model_name: Optional[str] = None
    timeout: int = 30


class ModelProvider(ABC):
    """Abstract base class for LLM providers.
    
    All LLM integrations must inherit from this and implement:
    - complete(): Send messages and get response
    - validate_config(): Check configuration validity
    - get_model_name(): Return the provider's model identifier
    """

    def __init__(self, config: ModelConfig):
        """Initialize provider with configuration.
        
        Args:
            config: ModelConfig object with API key and parameters
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not self.validate_config(config):
            raise ValueError(f"Invalid configuration for {self.__class__.__name__}")
        self.config = config

    @abstractmethod
    def validate_config(self, config: ModelConfig) -> bool:
        """Validate provider-specific configuration.
        
        Args:
            config: ModelConfig to validate
            
        Returns:
            True if config is valid, False otherwise
        """
        pass

    @abstractmethod
    def complete(self, messages: List[Message]) -> str:
        """Send messages to LLM and get response.
        
        Args:
            messages: List of Message objects with conversation history
            
        Returns:
            LLM response as string
            
        Raises:
            Exception: If API call fails
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the provider's model identifier.
        
        Returns:
            Model name (e.g., 'gpt-4o', 'claude-3-5-sonnet-20241022')
        """
        pass

    def format_messages_for_api(self, messages: List[Message]) -> Any:
        """Format messages for provider's API. Override if needed.
        
        Args:
            messages: List of Message objects
            
        Returns:
            Provider-specific message format
        """
        return [msg.to_dict() for msg in messages]
