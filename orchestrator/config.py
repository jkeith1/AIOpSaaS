"""Runtime configuration, sourced from environment variables.

The ``LLM_*`` names are the ones the Helm chart injects (ConfigMap for the
non-sensitive values, Secret for the key), so the same image works for any
provider without per-provider plumbing.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _env(*names: str, default: Optional[str] = None) -> Optional[str]:
    """Return the first non-empty environment variable among ``names``."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def _namespaces() -> List[str]:
    """Parse WATCH_NAMESPACES (comma-separated) into a list."""
    raw = os.getenv("WATCH_NAMESPACES", "default")
    return [ns.strip() for ns in raw.split(",") if ns.strip()]


@dataclass
class Config:
    """Agent configuration."""

    # LLM
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", default="claude"))
    llm_api_key: str = field(
        default_factory=lambda: _env(
            "ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "LLM_API_KEY", default=""
        )
    )
    llm_model: Optional[str] = field(
        default_factory=lambda: _env("CLAUDE_MODEL", "ANTHROPIC_MODEL", "LLM_MODEL")
    )

    # Kubernetes
    kubeconfig: Optional[str] = field(default_factory=lambda: os.getenv("KUBECONFIG"))
    watch_namespaces: List[str] = field(default_factory=_namespaces)
    default_namespace: str = field(
        default_factory=lambda: os.getenv("DEFAULT_NAMESPACE", "default")
    )

    # Behaviour
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "info"))
    max_pods_per_namespace: int = field(
        default_factory=lambda: int(os.getenv("MAX_PODS_PER_NAMESPACE", "5"))
    )

    @property
    def has_api_key(self) -> bool:
        return bool(self.llm_api_key)


# Backwards-compatible module-level accessor.
config = Config()
