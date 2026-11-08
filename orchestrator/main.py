"""AIOps Agent entrypoint.

Runs LLM-backed triage against real cluster state. Designed to be run as a
Kubernetes CronJob (analyse every watched namespace, log the findings) but
equally usable ad hoc from a shell.

Usage:
    # Triage every namespace in WATCH_NAMESPACES (the CronJob default)
    python -m orchestrator.main

    # One namespace
    python -m orchestrator.main --namespace my-app

    # One pod
    python -m orchestrator.main --namespace my-app --pod api-7d9f-x2k1

    # Every unhealthy pod in a namespace, individually
    python -m orchestrator.main --namespace my-app --unhealthy

    # Collect and print context without calling the LLM (no tokens spent)
    python -m orchestrator.main --namespace my-app --dry-run

Provider selection (see orchestrator/models/factory.py):
    export ANTHROPIC_API_KEY="sk-ant-..."     # -> claude (Messages API)
    export LLM_PROVIDER="claude-agent"        # -> Claude Agent SDK tool loop
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List

from .agent import ClusterTroubleshooterAgent
from .config import Config
from .tools import k8s

logger = logging.getLogger("aiops")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    # The SDKs are chatty at DEBUG and drown out our own output.
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _print_report(result: Dict[str, Any]) -> None:
    """Render one triage result as readable text."""
    target = result.get("pod") or result.get("namespace", "?")
    print("\n" + "=" * 72)
    print(f"TRIAGE: {target}")
    if result.get("severity") and result["severity"] != "unknown":
        print(f"Severity: {result['severity'].upper()}")
    print("=" * 72)

    print(f"\n{result.get('summary') or '(no summary returned)'}\n")

    for label, key in (
        ("Root causes", "root_causes"),
        ("Evidence", "evidence"),
        ("Recommended fixes", "recommended_fixes"),
        ("Affected objects", "affected_objects"),
    ):
        items = result.get(key) or []
        if not items:
            continue
        print(f"{label}:")
        for item in items:
            if isinstance(item, dict):
                item = json.dumps(item)
            print(f"  - {item}")
        print()

    if result.get("parse_error"):
        print("NOTE: the model did not return valid JSON; summary holds raw output.")
    print(f"[model: {result.get('model') or 'none'}]")


def _run(args: argparse.Namespace, config: Config) -> int:
    """Execute the requested triage and return a process exit code."""
    if args.dry_run:
        # No provider, no tokens - just show what would be sent.
        if args.pod:
            print(k8s.collect_pod_context(args.namespace, args.pod))
        else:
            print(k8s.collect_namespace_context(args.namespace))
        return 0

    agent = ClusterTroubleshooterAgent(config=config)
    if not agent.has_llm:
        logger.error(
            "No LLM provider could be initialised. Set ANTHROPIC_API_KEY "
            "(or LLM_API_KEY) and optionally LLM_PROVIDER."
        )
        return 1

    logger.info("Using %s", agent.provider.get_model_name())
    results: List[Dict[str, Any]] = []

    if args.pod:
        results.append(agent.triage_pod(args.namespace, args.pod))
    elif args.unhealthy:
        results.extend(
            agent.triage_unhealthy_pods(
                args.namespace, limit=config.max_pods_per_namespace
            )
        )
        if not results:
            logger.info("No unhealthy pods found in '%s'", args.namespace)
    else:
        namespaces = [args.namespace] if args.namespace else config.watch_namespaces
        for namespace in namespaces:
            try:
                results.append(agent.triage_namespace(namespace))
            except k8s.KubectlError as exc:
                logger.error("Skipping namespace '%s': %s", namespace, exc)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        for result in results:
            _print_report(result)

    return 0


def main(argv: List[str] = None) -> int:
    """Main orchestrator entrypoint."""
    parser = argparse.ArgumentParser(
        prog="orchestrator",
        description="LLM-backed Kubernetes triage agent.",
    )
    parser.add_argument(
        "-n", "--namespace",
        help="Namespace to triage. Defaults to every namespace in WATCH_NAMESPACES.",
    )
    parser.add_argument("-p", "--pod", help="Triage a single pod (requires --namespace).")
    parser.add_argument(
        "--unhealthy",
        action="store_true",
        help="Triage each unhealthy pod in the namespace individually.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the collected cluster context without calling the LLM.",
    )
    args = parser.parse_args(argv)

    config = Config()
    _configure_logging(config.log_level)

    if (args.pod or args.unhealthy) and not args.namespace:
        args.namespace = config.default_namespace
        logger.info("No --namespace given, using '%s'", args.namespace)
    if args.dry_run and not args.namespace:
        args.namespace = config.default_namespace

    logger.info("AIOps agent starting (provider=%s)", config.llm_provider)

    try:
        return _run(args, config)
    except k8s.KubectlError as exc:
        logger.error("Kubernetes access failed: %s", exc)
        logger.error(
            "In-cluster this means the ServiceAccount lacks RBAC or kubectl "
            "cannot reach the API server; locally, check your kubecontext."
        )
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - top-level guard
        logger.error("Unexpected error: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
