import subprocess
import json

def _run(cmd: str) -> str:
    """Run a shell command and return stdout or raise an error."""
    result = subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{result.stderr}")
    return result.stdout

def discover_resources() -> list[str]:
    """Return all namespaced Kubernetes resource types (built-in + CRDs)."""
    out = _run("kubectl api-resources --verbs=list --namespaced -o name")
    return [line.strip() for line in out.splitlines() if line.strip()]

def list_all_objects(namespace: str) -> dict:
    """Return all objects of all resource types in a namespace."""
    resources = discover_resources()
    objects: dict[str, list[dict]] = {}

    for r in resources:
        try:
            out = _run(f"kubectl get {r} -n {namespace} -o json")
            data = json.loads(out)
            items = data.get("items", [])
            if items:
                objects[r] = items
        except Exception:
            # Ignore resources we cannot list
            continue

    return objects

def get_events(namespace: str) -> dict:
    """Return all events in a namespace."""
    out = _run(f"kubectl get events -n {namespace} -o json")
    return json.loads(out)

def get_pod_logs(namespace: str, pod: str) -> str:
    """Fetch logs for a pod (first container only)."""
    try:
        return _run(f"kubectl logs {pod} -n {namespace}")
    except Exception:
        return "Unable to fetch logs."

def describe_pod(namespace: str, pod: str) -> str:
    """Return kubectl describe output for a pod."""
    try:
        return _run(f"kubectl describe pod {pod} -n {namespace}")
    except Exception:
        return "Unable to describe pod."

