# orchestrator/models/__init__.py
"""Model abstraction layer - pluggable LLM providers.

Only the provider-agnostic pieces are imported eagerly. Concrete providers are
imported on demand by ``ModelProviderFactory`` so that a missing optional SDK
never breaks the providers that *are* installed.
"""

from .base import ModelProvider, ModelConfig, Message, Role
from .factory import ModelProviderFactory

__all__ = [
    "ModelProvider",
    "ModelConfig",
    "Message",
    "Role",
    "ModelProviderFactory",
]
