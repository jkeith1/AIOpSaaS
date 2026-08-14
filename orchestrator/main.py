"""AIOps Agent Main Orchestrator.

Coordinates:
- Kubernetes cluster introspection
- LLM-based analysis and diagnostics
- Alert generation and routing
- Multi-provider LLM support (OpenAI, Anthropic, etc)

Usage:
    # Set your LLM provider via environment:
    export OPENAI_API_KEY="sk-..."
    # or
    export ANTHROPIC_API_KEY="sk-ant-..."
    
    python -m orchestrator.main
"""

import os
import sys
from typing import List
import logging

from .models import Message, Role
from .models.factory import ModelProviderFactory


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KubernetesAnalyzer:
    """Analyzes Kubernetes cluster health and generates insights using LLM.
    
    This is provider-agnostic - uses any LLM via the ModelProvider interface.
    """

    def __init__(self, llm_provider):
        """Initialize analyzer with LLM provider.
        
        Args:
            llm_provider: Configured ModelProvider instance (OpenAI, Claude, etc)
        """
        self.llm = llm_provider
        logger.info(f"Initialized KubernetesAnalyzer with {self.llm.get_model_name()}")

    def analyze_cluster_status(self, cluster_info: dict) -> str:
        """Analyze cluster status and generate insights.
        
        Args:
            cluster_info: Dictionary with cluster metrics and events
            
        Returns:
            AI-generated analysis and recommendations
        """
        system_prompt = (
            "You are an expert Kubernetes Operations (AIOps) agent. "
            "Analyze the provided cluster information and identify issues, "
            "trends, and recommend remediation steps. Be concise but thorough. "
            "Format your response with clear sections: Status, Issues, Resources, Actions."
        )
        
        cluster_data = f"""Cluster Information:
{cluster_info}

Provide analysis in this format:
1. **Current Health Status**: Overall cluster health
2. **Critical Issues**: Any blocking problems
3. **Resource Utilization**: CPU, Memory, Storage summary
4. **Recommended Actions**: Ordered by priority
"""
        
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=cluster_data),
        ]
        
        logger.info(f"Sending cluster analysis request to {self.llm.get_model_name()}")
        response = self.llm.complete(messages)
        logger.info(f"Received analysis ({len(response)} chars)")
        
        return response

    def diagnose_pod_issues(self, pod_info: dict) -> str:
        """Diagnose issues with a specific pod.
        
        Args:
            pod_info: Pod details including logs and events
            
        Returns:
            AI-generated diagnosis and remediation steps
        """
        messages = [
            Message(
                role=Role.SYSTEM,
                content=(
                    "You are a Kubernetes debugging expert. "
                    "Analyze pod information and provide structured diagnosis."
                ),
            ),
            Message(
                role=Role.USER,
                content=(
                    f"Pod Issue Analysis:\n{pod_info}\n\n"
                    "Provide: 1) Root cause, 2) Severity level, 3) Remediation steps"
                ),
            ),
        ]
        
        logger.info(f"Sending pod diagnosis request to {self.llm.get_model_name()}")
        response = self.llm.complete(messages)
        
        return response

    def suggest_optimizations(self, cluster_config: dict) -> str:
        """Suggest cluster optimizations based on current configuration.
        
        Args:
            cluster_config: Cluster configuration details
            
        Returns:
            AI-generated optimization recommendations
        """
        messages = [
            Message(
                role=Role.SYSTEM,
                content=(
                    "You are a Kubernetes architect. "
                    "Review the cluster configuration and suggest optimizations "
                    "for cost, performance, and reliability."
                ),
            ),
            Message(
                role=Role.USER,
                content=f"Cluster Configuration:\n{cluster_config}",
            ),
        ]
        
        return self.llm.complete(messages)


def main():
    """Main orchestrator entrypoint."""
    logger.info("="*60)
    logger.info("Starting AIOps Agent Orchestrator")
    logger.info("="*60)
    
    try:
        # Create LLM provider from environment
        logger.info("Initializing LLM provider...")
        llm_provider = ModelProviderFactory.create()
        logger.info(f"✓ Using {llm_provider.get_model_name()}")
        
        # Initialize analyzer
        analyzer = KubernetesAnalyzer(llm_provider)
        
        # Example 1: Analyze cluster status
        sample_cluster_info = {
            "nodes": 3,
            "pods_running": 45,
            "pods_pending": 2,
            "pods_failed": 1,
            "memory_usage": "65%",
            "cpu_usage": "42%",
            "disk_usage": "78%",
            "recent_events": [
                "Node memory pressure detected",
                "ImagePullBackOff on 2 pods (redis-cache-*)",
                "CrashLoopBackOff on 1 pod (worker-3)",
            ],
            "network_errors": 124,
            "node_conditions": {
                "node-1": "Ready",
                "node-2": "Ready",
                "node-3": "NotReady (memory pressure)",
            },
        }
        
        logger.info("\nRunning cluster analysis...")
        analysis = analyzer.analyze_cluster_status(sample_cluster_info)
        print("\n" + "="*70)
        print("CLUSTER ANALYSIS REPORT")
        print("="*70)
        print(analysis)
        print("="*70 + "\n")
        
        logger.info("✓ Orchestrator completed successfully")
        return 0
        
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        print(f"\n✗ Error: {str(e)}\n")
        print("Setup Instructions:")
        print("\n  For OpenAI (ChatGPT):")
        print("    export OPENAI_API_KEY='sk-...'")
        print("    # Optional: export OPENAI_MODEL='gpt-4o'  (default)")
        print("\n  For Anthropic (Claude):")
        print("    export ANTHROPIC_API_KEY='sk-ant-...'")
        print("    # Optional: export CLAUDE_MODEL='claude-3-5-sonnet-20241022'  (default)")
        print("\n  Or explicitly specify provider:")
        print("    export LLM_PROVIDER='openai'  # or 'claude'")
        print()
        return 1
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        print(f"\n✗ Unexpected error: {str(e)}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
