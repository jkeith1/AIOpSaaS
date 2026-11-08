"""The orchestrator brain: connects tools, workflows and the LLM provider."""

import logging
from typing import Any, Dict, List, Optional

from .models import ModelProviderFactory
from .tools import k8s
from .workflows import triage_namespace, triage_pod

logger = logging.getLogger(__name__)


class ClusterTroubleshooterAgent:
    """Coordinates cluster introspection and LLM-backed triage.

    The LLM provider is resolved once at construction and reused, so a single
    CronJob run that triages several namespaces pays the setup cost once.
    """

    def __init__(self, config=None, provider=None):
        """Initialize the agent.

        Args:
            config: Optional Config object.
            provider: An explicit ModelProvider. If None, one is built from
                the environment; if that fails the agent still runs and
                returns mechanical summaries without analysis.
        """
        self.config = config

        if provider is None:
            try:
                provider = ModelProviderFactory.create()
                logger.info("LLM provider ready: %s", provider.get_model_name())
            except Exception as exc:  # noqa: BLE001 - degrade, don't crash
                logger.error("No LLM provider available: %s", exc)
                provider = None

        self.provider = provider

    @property
    def has_llm(self) -> bool:
        """Whether analysis (as opposed to raw collection) is available."""
        return self.provider is not None

    def triage_namespace(self, namespace: str) -> Dict[str, Any]:
        """Run the namespace triage workflow."""
        return triage_namespace.run(namespace, provider=self.provider)

    def triage_pod(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Run the pod triage workflow."""
        return triage_pod.run(namespace, pod_name, provider=self.provider)

    def triage_unhealthy_pods(
        self, namespace: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Diagnose each unhealthy pod in a namespace, most broken first."""
        broken = k8s.unhealthy_pods(namespace)
        if not broken:
            logger.info("No unhealthy pods in namespace '%s'", namespace)
            return []

        broken.sort(key=lambda s: s["restarts"], reverse=True)
        return [self.triage_pod(namespace, s["name"]) for s in broken[:limit]]
