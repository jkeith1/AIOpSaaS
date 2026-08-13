import os
import requests

GITLAB_URL = os.getenv("GITLAB_URL", "")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN", "")

def _headers():
    return {"PRIVATE-TOKEN": GITLAB_TOKEN}

def get_pipeline(project_id: str, pipeline_id: str):
    """Fetch a GitLab pipeline."""
    if not GITLAB_URL or not GITLAB_TOKEN:
        return None

    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/pipelines/{pipeline_id}"
    resp = requests.get(url, headers=_headers())
    return resp.json() if resp.ok else None

def get_recent_commits(project_id: str):
    """Fetch recent commits."""
    if not GITLAB_URL or not GITLAB_TOKEN:
        return None

    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/repository/commits"
    resp = requests.get(url, headers=_headers())
    return resp.json() if resp.ok else None

