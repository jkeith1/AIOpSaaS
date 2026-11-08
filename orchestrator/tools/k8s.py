"""Read-only Kubernetes introspection via kubectl.

Two levels of API here:

* ``get_*`` / ``list_*``  - raw data, as before.
* ``summarize_*``         - compact text built for an LLM prompt.

The summarizers exist because a namespace dump is enormous: the original
``list_all_objects`` fetched full JSON for every namespaced resource type
including CRDs, which is both slow and far too large for a prompt. The
summarizers keep only the fields that carry triage signal and cap their own
output, so a busy namespace still fits comfortably in a request.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: Per-command timeout. kubectl hangs are a real failure mode in a CronJob.
DEFAULT_TIMEOUT = 60

#: Resource types worth walking for a namespace summary. Everything else is
#: reachable on demand via ``get_object_json``.
CORE_RESOURCES = [
    "pods",
    "deployments",
    "statefulsets",
    "daemonsets",
    "replicasets",
    "jobs",
    "cronjobs",
    "services",
    "ingresses",
    "configmaps",
    # NOTE: "secrets" deliberately omitted - this data is sent to an LLM API.
    "persistentvolumeclaims",
    "serviceaccounts",
    "horizontalpodautoscalers",
]

#: Truncation limits for anything heading into a prompt.
MAX_LOG_CHARS = 12_000
MAX_DESCRIBE_CHARS = 12_000
MAX_OBJECT_CHARS = 20_000
MAX_EVENTS = 60


class KubectlError(RuntimeError):
    """Raised when a kubectl invocation fails."""


def _run(args: List[str], timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run kubectl with the given arguments and return stdout.

    Arguments are passed as a list (no shell), so namespace and object names
    cannot be used for command injection.
    """
    if shutil.which("kubectl") is None:
        raise KubectlError("kubectl not found on PATH")

    cmd = ["kubectl", *args]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise KubectlError(f"kubectl timed out after {timeout}s: {' '.join(cmd)}") from exc

    if result.returncode != 0:
        raise KubectlError(
            f"kubectl failed ({result.returncode}): {' '.join(cmd)}\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _run_json(args: List[str], timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Run kubectl with -o json and parse the result."""
    out = _run([*args, "-o", "json"], timeout=timeout)
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise KubectlError(f"kubectl returned invalid JSON: {exc}") from exc


def _truncate(text: str, limit: int, label: str = "output") -> str:
    """Trim ``text`` to ``limit`` characters, keeping the tail for logs."""
    if len(text) <= limit:
        return text
    kept = text[-limit:]
    dropped = len(text) - limit
    return f"[...{dropped} earlier characters of {label} omitted...]\n{kept}"


def _age(timestamp: Optional[str]) -> str:
    """Render an ISO8601 timestamp as a compact age like '3d' or '12m'."""
    if not timestamp:
        return "?"
    try:
        then = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "?"
    delta = datetime.now(timezone.utc) - then
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


# ----------------------------------------------------------------------
# Discovery
# ----------------------------------------------------------------------


def discover_resources() -> List[str]:
    """Return all namespaced Kubernetes resource types (built-in + CRDs)."""
    out = _run(["api-resources", "--verbs=list", "--namespaced", "-o", "name"])
    return [line.strip() for line in out.splitlines() if line.strip()]


def list_objects(namespace: str, resource: str) -> List[dict]:
    """Return the items of one resource type in a namespace ([] on failure)."""
    try:
        return _run_json(["get", resource, "-n", namespace]).get("items", [])
    except KubectlError as exc:
        logger.debug("Skipping %s in %s: %s", resource, namespace, exc)
        return []


def list_all_objects(namespace: str, resources: Optional[List[str]] = None) -> Dict[str, list]:
    """Return objects for the core resource types in a namespace.

    Unlike the original implementation this does *not* walk every CRD by
    default - that produced megabytes of JSON. Pass ``resources`` explicitly
    (e.g. from :func:`discover_resources`) if you really want a full sweep.
    """
    objects: Dict[str, list] = {}
    for resource in resources or CORE_RESOURCES:
        items = list_objects(namespace, resource)
        if items:
            objects[resource] = items
    return objects


# ----------------------------------------------------------------------
# Raw getters
# ----------------------------------------------------------------------


def get_events(namespace: str) -> dict:
    """Return all events in a namespace as raw JSON."""
    return _run_json(["get", "events", "-n", namespace])


def get_pod_logs(
    namespace: str,
    pod: str,
    tail_lines: int = 200,
    previous: bool = False,
    container: Optional[str] = None,
) -> str:
    """Fetch recent logs for a pod.

    Args:
        tail_lines: How many trailing lines to fetch.
        previous: Read the previous (terminated) container - what you want
            for a CrashLoopBackOff.
        container: Specific container; defaults to the first.
    """
    args = ["logs", pod, "-n", namespace, f"--tail={tail_lines}"]
    if previous:
        args.append("--previous")
    if container:
        args.extend(["-c", container])
    try:
        return _truncate(_run(args), MAX_LOG_CHARS, "logs")
    except KubectlError as exc:
        return f"Unable to fetch logs for {pod}: {exc}"


def describe_pod(namespace: str, pod: str) -> str:
    """Return kubectl describe output for a pod."""
    try:
        return _truncate(
            _run(["describe", "pod", pod, "-n", namespace]),
            MAX_DESCRIBE_CHARS,
            "describe output",
        )
    except KubectlError as exc:
        return f"Unable to describe {pod}: {exc}"


def get_object_json(namespace: str, resource: str, name: str) -> str:
    """Return the full JSON for one object, truncated to a promptable size."""
    try:
        obj = _run_json(["get", resource, name, "-n", namespace])
    except KubectlError as exc:
        return f"Unable to get {resource}/{name}: {exc}"

    # managedFields is pure noise for triage and often the largest field.
    obj.get("metadata", {}).pop("managedFields", None)
    return _truncate(json.dumps(obj, indent=2), MAX_OBJECT_CHARS, "object JSON")


# ----------------------------------------------------------------------
# Summarizers (LLM-facing)
# ----------------------------------------------------------------------


def pod_status(pod: dict) -> Dict[str, Any]:
    """Extract the triage-relevant status of a single pod."""
    meta = pod.get("metadata", {})
    status = pod.get("status", {})
    containers = status.get("containerStatuses") or []

    restarts = sum(c.get("restartCount", 0) for c in containers)
    ready = sum(1 for c in containers if c.get("ready"))

    reasons: List[str] = []
    for container in containers:
        state = container.get("state", {})
        for phase in ("waiting", "terminated"):
            info = state.get(phase)
            if info and info.get("reason"):
                detail = info["reason"]
                if info.get("exitCode") is not None:
                    detail += f"(exit {info['exitCode']})"
                reasons.append(f"{container.get('name')}:{detail}")

    phase = status.get("phase", "Unknown")
    healthy = (
        phase in ("Running", "Succeeded")
        and (not containers or ready == len(containers))
        and not reasons
    )

    return {
        "name": meta.get("name", "?"),
        "phase": phase,
        "ready": f"{ready}/{len(containers)}" if containers else "0/0",
        "restarts": restarts,
        "age": _age(meta.get("creationTimestamp")),
        "node": pod.get("spec", {}).get("nodeName") or "unscheduled",
        "reasons": reasons,
        "healthy": healthy,
    }


def unhealthy_pods(namespace: str) -> List[Dict[str, Any]]:
    """Return the status dicts of pods that are not fully healthy."""
    pods = list_objects(namespace, "pods")
    return [s for s in (pod_status(p) for p in pods) if not s["healthy"]]


def summarize_namespace(namespace: str) -> str:
    """Build a compact, promptable summary of a namespace's workloads."""
    lines: List[str] = [f"# Namespace: {namespace}", ""]

    pods = list_objects(namespace, "pods")
    statuses = [pod_status(p) for p in pods]
    unhealthy = [s for s in statuses if not s["healthy"]]

    lines.append(
        f"Pods: {len(statuses)} total, {len(statuses) - len(unhealthy)} healthy, "
        f"{len(unhealthy)} unhealthy"
    )
    lines.append("")

    if statuses:
        lines.append("## Pods (NAME  PHASE  READY  RESTARTS  AGE  NODE  REASONS)")
        for s in sorted(statuses, key=lambda s: (s["healthy"], s["name"])):
            marker = "  " if s["healthy"] else "! "
            reasons = ", ".join(s["reasons"]) if s["reasons"] else "-"
            lines.append(
                f"{marker}{s['name']}  {s['phase']}  {s['ready']}  "
                f"{s['restarts']}  {s['age']}  {s['node']}  {reasons}"
            )
        lines.append("")

    # Workload controllers: desired vs available is usually enough signal.
    for resource in ("deployments", "statefulsets", "daemonsets"):
        items = list_objects(namespace, resource)
        if not items:
            continue
        lines.append(f"## {resource.capitalize()}")
        for item in items:
            name = item.get("metadata", {}).get("name", "?")
            status = item.get("status", {})
            desired = (
                item.get("spec", {}).get("replicas")
                if resource != "daemonsets"
                else status.get("desiredNumberScheduled")
            )
            available = status.get("availableReplicas", status.get("numberAvailable", 0)) or 0
            flag = "" if available == (desired or 0) else "  <-- not fully available"
            lines.append(f"  {name}: {available}/{desired} available{flag}")
        lines.append("")

    for resource in ("jobs", "services", "ingresses", "persistentvolumeclaims"):
        items = list_objects(namespace, resource)
        if not items:
            continue
        names = ", ".join(i.get("metadata", {}).get("name", "?") for i in items[:25])
        more = f" (+{len(items) - 25} more)" if len(items) > 25 else ""
        lines.append(f"{resource}: {names}{more}")

    return "\n".join(lines).strip()


def summarize_events(namespace: str, limit: int = MAX_EVENTS) -> str:
    """Return recent events, warnings first, as compact text."""
    try:
        events = get_events(namespace).get("items", [])
    except KubectlError as exc:
        return f"Unable to fetch events: {exc}"

    if not events:
        return f"No events in namespace {namespace}."

    def sort_key(event: dict):
        warning = event.get("type") == "Warning"
        ts = (
            event.get("lastTimestamp")
            or event.get("eventTime")
            or event.get("metadata", {}).get("creationTimestamp")
            or ""
        )
        return (not warning, ts)

    events.sort(key=sort_key, reverse=False)
    warnings = [e for e in events if e.get("type") == "Warning"]

    lines = [
        f"# Events in {namespace}: {len(events)} total, {len(warnings)} warnings",
        "",
    ]
    for event in events[:limit]:
        obj = event.get("involvedObject", {})
        ts = event.get("lastTimestamp") or event.get("eventTime")
        lines.append(
            f"[{event.get('type', '?')}] {_age(ts)} ago  "
            f"{obj.get('kind', '?')}/{obj.get('name', '?')}  "
            f"{event.get('reason', '?')}: {(event.get('message') or '').strip()}"
            f"  (x{event.get('count', 1)})"
        )
    if len(events) > limit:
        lines.append(f"... {len(events) - limit} older events omitted")

    return "\n".join(lines)


def collect_namespace_context(namespace: str, include_logs: bool = True) -> str:
    """Assemble everything a one-shot triage prompt needs for a namespace.

    Includes the workload summary, events, and - for unhealthy pods only -
    describe output and recent logs. Healthy pods contribute a single line
    each, which is what keeps this affordable.
    """
    sections = [summarize_namespace(namespace), "", summarize_events(namespace)]

    if include_logs:
        broken = unhealthy_pods(namespace)
        for status in broken[:5]:
            pod = status["name"]
            sections.extend(["", f"## Detail for unhealthy pod: {pod}", ""])
            sections.append(describe_pod(namespace, pod))
            # A crashlooping container's useful logs are in the previous run.
            previous = any("CrashLoop" in r or "Error" in r for r in status["reasons"])
            sections.extend(
                ["", f"### Logs for {pod} (previous={previous})", ""]
            )
            sections.append(
                get_pod_logs(namespace, pod, tail_lines=100, previous=previous)
            )
        if len(broken) > 5:
            sections.append(f"\n... {len(broken) - 5} further unhealthy pods not detailed")

    return "\n".join(sections)


def collect_pod_context(namespace: str, pod: str) -> str:
    """Assemble describe + current and previous logs for a single pod."""
    sections = [
        f"# Pod {pod} in namespace {namespace}",
        "",
        "## kubectl describe",
        describe_pod(namespace, pod),
        "",
        "## Current logs (tail 200)",
        get_pod_logs(namespace, pod, tail_lines=200),
        "",
        "## Previous container logs (tail 200)",
        get_pod_logs(namespace, pod, tail_lines=200, previous=True),
        "",
        "## Namespace events",
        summarize_events(namespace, limit=30),
    ]
    return "\n".join(sections)
