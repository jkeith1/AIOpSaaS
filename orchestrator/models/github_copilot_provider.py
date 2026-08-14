"""GitHub Copilot provider implementation."""

import os
from typing import List, Optional
import base64
import json

try:
    import requests
except ImportError:
    raise ImportError("requests package required: pip install requests")

from .base import ModelProvider, ModelConfig, Message, Role


class GitHubCopilotProvider(ModelProvider):
    """GitHub Copilot provider via GitHub API.
    
    Utilizes GitHub's Copilot API endpoints through a valid GitHub token.
    This allows using Copilot through your GitHub subscription without
    separate API costs.
    
    Requirements:
    - GitHub account with Copilot subscription
    - Valid GitHub personal access token (PAT) or GitHub App token
    - `requests` library
    """

    # GitHub Copilot API endpoints
    GITHUB_API_BASE = "https://api.github.com"
    COPILOT_CHAT_ENDPOINT = "/copilot/chat"
    COPILOT_COMPLETIONS_ENDPOINT = "/copilot/completions"

    def __init__(self, config: ModelConfig):
        """Initialize GitHub Copilot provider.
        
        Args:
            config: ModelConfig with GitHub token
        """
        super().__init__(config)
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {config.api_key}",
            "X-GitHub-Api-Version": "2024-01-01",
            "User-Agent": "AIOpS-Agent/0.1.0",
        })

    def validate_config(self, config: ModelConfig) -> bool:
        """Validate GitHub Copilot configuration.
        
        Args:
            config: ModelConfig to validate
            
        Returns:
            True if valid GitHub token present
        """
        if not config.api_key:
            raise ValueError("GitHub token required for Copilot provider")
        if not config.model_name:
            config.model_name = "gpt-4-turbo"  # Copilot uses GPT-4
        return True

    def complete(self, messages: List[Message]) -> str:
        """Call GitHub Copilot API and get response.
        
        Args:
            messages: List of Message objects
            
        Returns:
            Response text from Copilot
            
        Raises:
            Exception: If GitHub API call fails
        """
        try:
            # Format messages for Copilot API
            formatted_messages = self.format_messages_for_api(messages)
            
            # Call Copilot chat endpoint
            url = f"{self.GITHUB_API_BASE}{self.COPILOT_CHAT_ENDPOINT}"
            
            payload = {
                "messages": formatted_messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            
            response = self.session.post(
                url,
                json=payload,
                timeout=self.config.timeout,
            )
            
            # Handle API errors
            if response.status_code == 401:
                raise Exception("GitHub token invalid or expired")
            elif response.status_code == 403:
                raise Exception("GitHub Copilot subscription not active or token lacks permissions")
            elif response.status_code == 429:
                raise Exception("GitHub API rate limit exceeded")
            elif response.status_code >= 500:
                raise Exception(f"GitHub API server error: {response.status_code}")
            elif response.status_code >= 400:
                raise Exception(f"GitHub API error: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            # Extract response text from Copilot API response
            if "choices" in data and len(data["choices"]) > 0:
                return data["choices"][0].get("message", {}).get("content", "")
            elif "message" in data:
                return data["message"]
            else:
                raise Exception(f"Unexpected response format from Copilot API: {data}")
            
        except requests.exceptions.Timeout:
            raise Exception("GitHub API request timed out")
        except requests.exceptions.ConnectionError:
            raise Exception("Failed to connect to GitHub API")
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from GitHub API")
        except Exception as e:
            raise Exception(f"GitHub Copilot API error: {str(e)}")

    def get_model_name(self) -> str:
        """Return Copilot model name.
        
        Returns:
            Model identifier
        """
        return self.config.model_name or "gpt-4-turbo"

    @staticmethod
    def from_env() -> "GitHubCopilotProvider":
        """Create provider from environment variables.
        
        Expects:
        - GITHUB_TOKEN: GitHub personal access token or GitHub App token (required)
          PAT should have 'copilot' or equivalent scope
        - GITHUB_COPILOT_MODEL (optional): Model name (default: gpt-4-turbo)
        - GITHUB_COPILOT_TEMPERATURE (optional): Temperature 0-2 (default: 0.7)
        - GITHUB_COPILOT_MAX_TOKENS (optional): Max output tokens (default: 2048)
        - GITHUB_COPILOT_ENDPOINT (optional): Custom endpoint URL
        
        Returns:
            Configured GitHubCopilotProvider instance
            
        Raises:
            ValueError: If required env vars missing
        """
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        
        config = ModelConfig(
            api_key=token,
            model_name=os.getenv("GITHUB_COPILOT_MODEL", "gpt-4-turbo"),
            temperature=float(os.getenv("GITHUB_COPILOT_TEMPERATURE", 0.7)),
            max_tokens=int(os.getenv("GITHUB_COPILOT_MAX_TOKENS", 2048)),
        )
        return GitHubCopilotProvider(config)

    def get_token_usage(self) -> Optional[dict]:
        """Get GitHub token usage and rate limit info.
        
        Returns:
            Dictionary with rate limit info or None if unavailable
        """
        try:
            response = self.session.get(
                f"{self.GITHUB_API_BASE}/rate_limit",
                timeout=self.config.timeout,
            )
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return None
