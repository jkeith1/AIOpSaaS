# orchestrator/models/__init__.py
"""
Model abstraction layer - pluggable LLM providers.
Supports OpenAI, Anthropic, Azure, and extensible to any LLM.
"""

from .base import ModelProvider, Message, Role
from .openai_provider import OpenAIProvider
from .claude_provider import ClaudeProvider

__all__ = [
    "ModelProvider",
    "Message",
    "Role",
    "OpenAIProvider",
    "ClaudeProvider",
]
