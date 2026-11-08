"""Pod-level triage workflow, backed by an LLM."""

import logging
from typing import Any, Dict, Optional

from .. import prompts
from ..tools import k8s
from ._common import run_structured

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def run(
    namespace: str,
    pod_name: str,
    provider=None,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Diagnose a single pod and return structured findings.

    Args:
        namespace: Pod's namespace.
        pod_name: Pod to diagnose.
        provider: A ModelProvider. If None, only the collected facts are returned.
        context: Pre-collected describe/logs/events. Collected here if omitted.

    Returns:
        dict with summary, root_causes, evidence, recommended_fixes, severity.
    """
    if context is None:
        logger.info("Collecting context for pod '%s/%s'", namespace, pod_name)
        context = k8s.collect_pod_context(namespace, pod_name)

    defaults: Dict[str, Any] = {
        "namespace": namespace,
        "pod": pod_name,
        "summary": "",
        "root_causes": [],
        "evidence": [],
        "recommended_fixes": [],
        "severity": "unknown",
    }

    if provider is None:
        defaults["summary"] = (
            f"Collected diagnostics for '{pod_name}' in '{namespace}', but no "
            "LLM provider is configured, so no analysis was performed."
        )
        defaults["model"] = None
        defaults["parse_error"] = False
        return defaults

    logger.info(
        "Diagnosing pod '%s/%s' with %s", namespace, pod_name, provider.get_model_name()
    )

    result = run_structured(
        provider=provider,
        system_prompt=prompts.load("triage_pod"),
        user_content=f"Pod under analysis: {namespace}/{pod_name}\n\n{context}",
        defaults=defaults,
    )

    severity = str(result.get("severity", "")).lower()
    result["severity"] = severity if severity in VALID_SEVERITIES else "unknown"
    return result
