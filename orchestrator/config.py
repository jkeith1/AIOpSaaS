import os

class Config:
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")
    KUBECONFIG = os.getenv("KUBECONFIG", "/kube/config")
    DEFAULT_NAMESPACE = os.getenv("DEFAULT_NAMESPACE", "default")

