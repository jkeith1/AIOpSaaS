"""GitHub Copilot SDK provider implementation using the official SDK."""

import os
import asyncio
from typing import List, Optional

try:
    from copilot import CopilotClient
    from copilot.session_events import AssistantMessageData, SessionIdleData
    from copilot.session import PermissionHandler
except ImportError:
    raise ImportError("github-copilot-sdk package required: pip install github-copilot-sdk")

from .base import ModelProvider, ModelConfig, Message, Role


class CopilotSDKProvider(ModelProvider):
    """GitHub Copilot SDK provider using the official SDK.
    
    Uses the official GitHub Copilot SDK (async) for chat completions.
    This is the recommended way to use GitHub Copilot programmatically.
    
    Requirements:
    - GitHub account with Copilot subscription
    - Valid GitHub personal access token (PAT)
    - `github-copilot-sdk` library
    """

    def __init__(self, config: ModelConfig):
        """Initialize Copilot SDK provider.
        
        Args:
            config: ModelConfig with GitHub token
        """
        super().__init__(config)
        self.client = None
        self.token = config.api_key

    def validate_config(self, config: ModelConfig) -> bool:
        """Validate Copilot SDK configuration.
        
        Args:
            config: ModelConfig to validate
            
        Returns:
            True if valid GitHub token present
        """
        if not config.api_key:
            raise ValueError("GitHub token required for Copilot SDK provider")
        if not config.model_name:
            config.model_name = "gpt-4"  # Copilot uses GPT-4
        return True

    def complete(self, messages: List[Message]) -> str:
        """Call GitHub Copilot SDK and get response.
        
        Args:
            messages: List of Message objects
            
        Returns:
            Response text from Copilot
            
        Raises:
            Exception: If SDK call fails
        """
        try:
            # Convert Message objects to dict format for SDK
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "role": msg.role.value,
                    "content": msg.content
                })
            
            # Combine system and user messages into a single prompt
            # The SDK works with user messages, so we'll combine context
            prompt = ""
            for msg in formatted_messages:
                if msg["role"] == "system":
                    prompt += f"{msg['content']}\n\n"
                elif msg["role"] == "user":
                    prompt += msg["content"]
            
            # Run async operation
            response = asyncio.run(self._async_complete(prompt))
            return response
            
        except Exception as e:
            raise Exception(f"GitHub Copilot SDK error: {str(e)}")

    async def _async_complete(self, prompt: str) -> str:
        """Async helper to call Copilot SDK.
        
        Args:
            prompt: The user prompt
            
        Returns:
            Response text
        """
        response_text = ""
        
        try:
            async with CopilotClient(token=self.token) as client:
                async with await client.create_session(
                    on_permission_request=PermissionHandler.approve_all,
                    model=self.config.model_name or "gpt-4"
                ) as session:
                    done = asyncio.Event()
                    
                    def on_event(event):
                        nonlocal response_text
                        if isinstance(event.data, AssistantMessageData):
                            response_text += event.data.content
                        elif isinstance(event.data, SessionIdleData):
                            done.set()
                    
                    session.on(on_event)
                    await session.send(prompt)
                    await asyncio.wait_for(done.wait(), timeout=self.config.timeout)
            
            return response_text
            
        except asyncio.TimeoutError:
            raise Exception("GitHub Copilot SDK request timed out")
        except Exception as e:
            raise Exception(f"GitHub Copilot SDK error: {str(e)}")

    def get_model_name(self) -> str:
        """Return Copilot model name.
        
        Returns:
            Model identifier
        """
        return self.config.model_name or "gpt-4"

    @staticmethod
    def from_env() -> "CopilotSDKProvider":
        """Create provider from environment variables.
        
        Expects:
        - GITHUB_TOKEN: GitHub personal access token (required)
        - GITHUB_COPILOT_MODEL (optional): Model name (default: gpt-4)
        - GITHUB_COPILOT_TEMPERATURE (optional): Temperature 0-2 (default: 0.7)
        - GITHUB_COPILOT_MAX_TOKENS (optional): Max output tokens (default: 2048)
        
        Returns:
            Configured CopilotSDKProvider instance
            
        Raises:
            ValueError: If required env vars missing
        """
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN environment variable not set")
        
        config = ModelConfig(
            api_key=token,
            model_name=os.getenv("GITHUB_COPILOT_MODEL", "gpt-4"),
            temperature=float(os.getenv("GITHUB_COPILOT_TEMPERATURE", 0.7)),
            max_tokens=int(os.getenv("GITHUB_COPILOT_MAX_TOKENS", 2048)),
        )
        return CopilotSDKProvider(config)
