"""Shared helpers for LLM-backed triage workflows."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ..models.base import Message, Role

logger = logging.getLogger(__name__)

#: Appended to every triage prompt so the model returns parseable output.
JSON_INSTRUCTION = (
    "\n\nRespond with a single JSON object and nothing else - no prose before "
    "or after it, no markdown code fences."
)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from a model response.

    Handles the three things models actually do: return clean JSON, wrap it in
    a markdown fence, or bury it in a sentence of preamble.
    """
    text = (text or "").strip()
    if not text:
        return None

    candidates: List[str] = [text]

    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def run_structured(
    provider,
    system_prompt: str,
    user_content: str,
    defaults: Dict[str, Any],
) -> Dict[str, Any]:
    """Call the LLM and coerce the reply into a dict with the expected keys.

    If the model returns something unparseable the raw text is preserved under
    ``summary`` and a ``parse_error`` flag is set, so a bad response degrades
    into a readable report instead of an exception.

    Args:
        provider: A ModelProvider instance.
        system_prompt: The triage instructions.
        user_content: The cluster data to analyse.
        defaults: Keys (and fallback values) the result must contain.

    Returns:
        A dict containing at least ``defaults``' keys plus ``model``.
    """
    messages = [
        Message(role=Role.SYSTEM, content=system_prompt + JSON_INSTRUCTION),
        Message(role=Role.USER, content=user_content),
    ]

    raw = provider.complete(messages)
    parsed = extract_json(raw)

    result: Dict[str, Any] = dict(defaults)
    if parsed is None:
        logger.warning("Model response was not valid JSON; returning raw text")
        result["summary"] = raw.strip()
        result["parse_error"] = True
    else:
        result.update(parsed)
        result["parse_error"] = False

    result["model"] = provider.get_model_name()
    return result
