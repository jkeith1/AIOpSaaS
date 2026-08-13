from typing import Dict, Any

from .tools import k8s
from .workflows import triage_namespace, triage_pod


class ClusterTroubleshooterAgent:
    """
    The orchestrator brain.
    It connects:
    - tools (k8s, gitlab, argocd)
    - workflows (triage_namespace, triage_pod)
    - prompts (later, when Claude is added)
    """
   
    def __init__(self, config=None):
    	self.config = config

    def triage_namespace(self, namespace: str) -> Dict[str, Any]:
        """Collect all namespace data and run the namespace triage workflow."""

        objects = k8s.list_all_objects(namespace)
        events = k8s.get_events(namespace)

        return triage_namespace.run(namespace, objects, events)

    def triage_pod(self, namespace: str, pod_name: str) -> Dict[str, Any]:
        """Collect pod-level data and run the pod triage workflow."""

        logs = k8s.get_pod_logs(namespace, pod_name)
        describe = k8s.describe_pod(namespace, pod_name)

        return triage_pod.run(namespace, pod_name)

