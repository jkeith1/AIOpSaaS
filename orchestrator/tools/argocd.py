import os
import requests

ARGOCD_URL = os.getenv("ARGOCD_URL", "")
ARGOCD_TOKEN = os.getenv("ARGOCD_TOKEN", "")

def _headers():
    return {"Authorization": f"Bearer {ARGOCD_TOKEN}"}

def get_app(app_name: str):
    """Fetch ArgoCD application details."""
    if not ARGOCD_URL or not ARGOCD_TOKEN:
        return None

    url = f"{ARGOCD_URL}/api/v1/applications/{app_name}"
    resp = requests.get(url, headers=_headers())
    return resp.json() if resp.ok else None

def get_app_history(app_name: str):
    """Fetch ArgoCD application sync history."""
    if not ARGOCD_URL or not ARGOCD_TOKEN:
        return None

    url = f"{ARGOCD_URL}/api/v1/applications/{app_name}/history"
    resp = requests.get(url, headers=_headers())
    return resp.json() if resp.ok else None

