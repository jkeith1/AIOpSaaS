"""Namespace-wide triage workflow, backed by an LLM."""

import logging
from typing import Any, Dict, Optional

from .. import prompts
from ..tools import k8s
from ._common import run_structured

logger = logging.getLogger(__name__)


def run(
    namespace: str,
    provider=None,
    context: Optional[str] = None,
    include_logs: bool = True,
) -> Dict[str, Any]:
    """Analyse a whole namespace and return structured findings.

    Args:
        namespace: Namespace to triage.
        provider: A ModelProvider. If None, only the mechanical summary is
            returned - useful for a dry run without spending tokens.
        context: Pre-collected cluster context. Collected here if omitted.
        include_logs: Pull describe/logs for unhealthy pods.

    Returns:
        dict with summary, root_causes, evidence, recommended_fixes,
        affected_objects, plus counts and the model used.
    """
    if context is None:
        logger.info("Collecting cluster context for namespace '%s'", namespace)
        context = k8s.collect_namespace_context(namespace, include_logs=include_logs)

    unhealthy = k8s.unhealthy_pods(namespace)

    defaults: Dict[str, Any] = {
        "namespace": namespace,
        "summary": "",
        "root_causes": [],
        "evidence": [],
        "recommended_fixes": [],
        "affected_objects": [u["name"] for u in unhealthy],
        "unhealthy_pod_count": len(unhealthy),
    }

    if provider is None:
        defaults["summary"] = (
            f"Namespace '{namespace}': {len(unhealthy)} unhealthy pod(s). "
            "No LLM provider configured, so no analysis was performed."
        )
        defaults["model"] = None
        defaults["parse_error"] = False
        return defaults

    logger.info(
        "Analysing namespace '%s' with %s (%d chars of context)",
        namespace,
        provider.get_model_name(),
        len(context),
    )

    return run_structured(
        provider=provider,
        system_prompt=prompts.load("triage_namespace"),
        user_content=f"Namespace under analysis: {namespace}\n\n{context}",
        defaults=defaults,
    )
