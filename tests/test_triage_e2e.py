"""End-to-end triage tests against a fake kubectl and a fake LLM provider.

Proves the collection -> prompt -> parse -> report path works without a
cluster or an API key.
"""

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Put the fake kubectl first on PATH.
os.environ["PATH"] = f"{ROOT / 'tests' / 'fake'}{os.pathsep}{os.environ['PATH']}"

from orchestrator.models.base import Message, ModelProvider, Role  # noqa: E402
from orchestrator.tools import k8s  # noqa: E402
from orchestrator.workflows import triage_namespace, triage_pod  # noqa: E402


class FakeProvider(ModelProvider):
    """Records the prompt it was given and returns canned triage JSON."""

    def __init__(self, reply=None):
        self.received = []
        self.reply = reply or json.dumps({
            "summary": "worker-3 is crashlooping against an unreachable redis.",
            "root_causes": ["redis-cache-0 never started (bad image tag)"],
            "evidence": ["ConnectionRefusedError on redis:6379", "ImagePullBackOff"],
            "recommended_fixes": ["Correct the redis image tag"],
            "affected_objects": ["worker-3", "redis-cache-0"],
            "severity": "high",
        })

    def validate_config(self, config):
        return True

    def complete(self, messages):
        self.received = messages
        return self.reply

    def get_model_name(self):
        return "fake-model"


class TestCollection(unittest.TestCase):
    def test_unhealthy_pods_detected(self):
        names = {p["name"] for p in k8s.unhealthy_pods("demo")}
        self.assertEqual(names, {"worker-3", "redis-cache-0"})

    def test_healthy_pod_not_flagged(self):
        self.assertNotIn("api-7d9f-abcde", {p["name"] for p in k8s.unhealthy_pods("demo")})

    def test_restart_count_and_reason_surface(self):
        worker = next(p for p in k8s.unhealthy_pods("demo") if p["name"] == "worker-3")
        self.assertEqual(worker["restarts"], 7)
        self.assertTrue(any("CrashLoopBackOff" in r for r in worker["reasons"]))

    def test_namespace_summary_is_compact_and_marks_problems(self):
        summary = k8s.summarize_namespace("demo")
        self.assertIn("! worker-3", summary)
        self.assertIn("1/2 available", summary)
        # The whole point of the summarizer: this must stay prompt-sized.
        self.assertLess(len(summary), 4000)

    def test_events_put_warnings_first(self):
        text = k8s.summarize_events("demo")
        self.assertIn("2 warnings", text)
        self.assertLess(text.index("[Warning]"), text.index("[Normal]"))

    def test_namespace_context_includes_logs_for_broken_pods_only(self):
        context = k8s.collect_namespace_context("demo")
        self.assertIn("Detail for unhealthy pod: worker-3", context)
        self.assertIn("ConnectionRefusedError", context)
        self.assertNotIn("Detail for unhealthy pod: api-7d9f", context)

    def test_injection_safe(self):
        """Namespace names are passed as argv, never interpolated into a shell."""
        from unittest import mock

        with mock.patch("subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="{}", stderr="")
            k8s._run(["get", "pods", "-n", "demo; rm -rf /"])

        cmd, kwargs = run.call_args[0][0], run.call_args[1]
        self.assertIsInstance(cmd, list)
        # The hostile string stays one opaque argv element.
        self.assertIn("demo; rm -rf /", cmd)
        self.assertFalse(kwargs.get("shell", False))


class TestNamespaceTriage(unittest.TestCase):
    def test_returns_structured_findings(self):
        provider = FakeProvider()
        result = triage_namespace.run("demo", provider=provider)

        self.assertFalse(result["parse_error"])
        self.assertEqual(result["namespace"], "demo")
        self.assertEqual(result["unhealthy_pod_count"], 2)
        self.assertIn("crashlooping", result["summary"])
        self.assertEqual(result["model"], "fake-model")
        self.assertTrue(result["recommended_fixes"])

    def test_prompt_carries_system_and_cluster_data(self):
        provider = FakeProvider()
        triage_namespace.run("demo", provider=provider)

        roles = [m.role for m in provider.received]
        self.assertIn(Role.SYSTEM, roles)
        system = next(m for m in provider.received if m.role == Role.SYSTEM).content
        user = next(m for m in provider.received if m.role == Role.USER).content
        self.assertIn("Kubernetes Troubleshooting Agent", system)
        self.assertIn("worker-3", user)

    def test_no_provider_degrades_to_summary(self):
        result = triage_namespace.run("demo", provider=None)
        self.assertIsNone(result["model"])
        self.assertIn("2 unhealthy pod(s)", result["summary"])

    def test_unparseable_reply_preserved_not_raised(self):
        result = triage_namespace.run("demo", provider=FakeProvider(reply="I think it's fine"))
        self.assertTrue(result["parse_error"])
        self.assertEqual(result["summary"], "I think it's fine")

    def test_fenced_json_reply_parses(self):
        reply = '```json\n{"summary": "fenced", "root_causes": ["x"]}\n```'
        result = triage_namespace.run("demo", provider=FakeProvider(reply=reply))
        self.assertFalse(result["parse_error"])
        self.assertEqual(result["summary"], "fenced")


class TestPodTriage(unittest.TestCase):
    def test_returns_severity(self):
        result = triage_pod.run("demo", "worker-3", provider=FakeProvider())
        self.assertEqual(result["severity"], "high")
        self.assertEqual(result["pod"], "worker-3")

    def test_bogus_severity_normalised(self):
        reply = json.dumps({"summary": "s", "severity": "catastrophic"})
        result = triage_pod.run("demo", "worker-3", provider=FakeProvider(reply=reply))
        self.assertEqual(result["severity"], "unknown")

    def test_context_includes_previous_logs_and_describe(self):
        provider = FakeProvider()
        triage_pod.run("demo", "worker-3", provider=provider)
        user = next(m for m in provider.received if m.role == Role.USER).content
        self.assertIn("kubectl describe", user)
        self.assertIn("Previous container logs", user)


class TestMainCLI(unittest.TestCase):
    def test_dry_run_prints_context_without_provider(self):
        from orchestrator.main import main
        self.assertEqual(main(["--namespace", "demo", "--dry-run"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
