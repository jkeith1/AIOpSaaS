"""Offline tests for the Claude provider and factory.

The `anthropic` SDK is stubbed, so these run with no network and no API key.
Run with: python -m unittest discover -s tests -v
"""

import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# --------------------------------------------------------------------------
# Stub the anthropic SDK before importing the provider.
# --------------------------------------------------------------------------
class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text="ok"):
        self.content = [_Block(text)]


class _Messages:
    def __init__(self, owner):
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        if self._owner.raise_with is not None:
            error, self._owner.raise_with = self._owner.raise_with, None
            raise error
        return _Response(self._owner.reply)


class _FakeAnthropic:
    instances = []

    def __init__(self, api_key=None, timeout=None):
        self.api_key = api_key
        self.timeout = timeout
        self.calls = []
        self.reply = '{"summary": "all good", "root_causes": []}'
        self.raise_with = None
        self.messages = _Messages(self)
        _FakeAnthropic.instances.append(self)


class _APIStatusError(Exception):
    def __init__(self, message="boom", status_code=500):
        super().__init__(message)
        self.status_code = status_code


_stub = types.ModuleType("anthropic")
_stub.Anthropic = _FakeAnthropic
_stub.APIStatusError = _APIStatusError
_stub.APIConnectionError = type("APIConnectionError", (Exception,), {})
_stub.RateLimitError = type("RateLimitError", (Exception,), {})
sys.modules["anthropic"] = _stub

from orchestrator.models.base import Message, ModelConfig, Role  # noqa: E402
from orchestrator.models.claude_provider import ClaudeProvider  # noqa: E402
from orchestrator.models.factory import ModelProviderFactory  # noqa: E402
from orchestrator.workflows._common import extract_json  # noqa: E402


def _provider(**overrides):
    config = ModelConfig(api_key="sk-ant-test", **overrides)
    return ClaudeProvider(config)


class TestSystemMessageHandling(unittest.TestCase):
    """The original bug: system messages were sent inside `messages`."""

    def test_system_message_goes_to_system_param(self):
        provider = _provider()
        provider.complete([
            Message(role=Role.SYSTEM, content="You are an SRE."),
            Message(role=Role.USER, content="What broke?"),
        ])

        call = provider.client.calls[-1]
        self.assertEqual(call["system"], "You are an SRE.")
        self.assertEqual(call["messages"], [{"role": "user", "content": "What broke?"}])
        # No system role may appear in the messages array.
        self.assertNotIn("system", [m["role"] for m in call["messages"]])

    def test_multiple_system_messages_are_joined(self):
        provider = _provider()
        provider.complete([
            Message(role=Role.SYSTEM, content="Rule one."),
            Message(role=Role.SYSTEM, content="Rule two."),
            Message(role=Role.USER, content="Go."),
        ])
        self.assertEqual(provider.client.calls[-1]["system"], "Rule one.\n\nRule two.")

    def test_consecutive_user_messages_are_merged(self):
        provider = _provider()
        provider.complete([
            Message(role=Role.USER, content="First."),
            Message(role=Role.USER, content="Second."),
        ])
        messages = provider.client.calls[-1]["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "First.\n\nSecond.")

    def test_conversation_must_open_with_user_turn(self):
        provider = _provider()
        provider.complete([
            Message(role=Role.ASSISTANT, content="Earlier answer."),
            Message(role=Role.USER, content="Follow-up."),
        ])
        self.assertEqual(provider.client.calls[-1]["messages"][0]["role"], "user")

    def test_empty_messages_rejected(self):
        provider = _provider()
        with self.assertRaises(ValueError):
            provider.complete([Message(role=Role.SYSTEM, content="Only system.")])


class TestConfig(unittest.TestCase):
    def test_temperature_is_sent(self):
        provider = _provider(temperature=0.2)
        provider.complete([Message(role=Role.USER, content="hi")])
        self.assertEqual(provider.client.calls[-1]["temperature"], 0.2)

    def test_default_model_applied(self):
        self.assertEqual(_provider().get_model_name(), "claude-sonnet-5")

    def test_model_alias_expanded(self):
        self.assertEqual(_provider(model_name="opus").get_model_name(), "claude-opus-5")

    def test_missing_api_key_rejected(self):
        with self.assertRaises(ValueError):
            ClaudeProvider(ModelConfig(api_key=""))

    def test_out_of_range_temperature_rejected(self):
        with self.assertRaises(ValueError):
            ClaudeProvider(ModelConfig(api_key="k", temperature=2.5))


class TestEnvPrecedence(unittest.TestCase):
    """The Helm chart injects LLM_*; the provider must honour those names."""

    def test_llm_api_key_fallback(self):
        with mock.patch.dict(os.environ, {"LLM_API_KEY": "sk-ant-from-helm"}, clear=True):
            self.assertEqual(ClaudeProvider.from_env().config.api_key, "sk-ant-from-helm")

    def test_anthropic_key_wins_over_llm_key(self):
        env = {"ANTHROPIC_API_KEY": "sk-primary", "LLM_API_KEY": "sk-fallback"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ClaudeProvider.from_env().config.api_key, "sk-primary")

    def test_llm_model_and_tuning_read_from_env(self):
        env = {
            "LLM_API_KEY": "sk-ant-test",
            "LLM_MODEL": "claude-opus-5",
            "LLM_TEMPERATURE": "0.1",
            "LLM_MAX_TOKENS": "8192",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            provider = ClaudeProvider.from_env()
        self.assertEqual(provider.config.model_name, "claude-opus-5")
        self.assertEqual(provider.config.temperature, 0.1)
        self.assertEqual(provider.config.max_tokens, 8192)

    def test_no_key_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                ClaudeProvider.from_env()


class TestRetries(unittest.TestCase):
    def test_server_error_is_retried(self):
        provider = _provider()
        provider.client.raise_with = _APIStatusError("overloaded", 529)
        with mock.patch("time.sleep"):
            result = provider.complete([Message(role=Role.USER, content="hi")])
        self.assertEqual(len(provider.client.calls), 2)
        self.assertIn("all good", result)

    def test_client_error_is_not_retried(self):
        provider = _provider()
        provider.client.raise_with = _APIStatusError("bad request", 400)
        with mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                provider.complete([Message(role=Role.USER, content="hi")])
        self.assertEqual(len(provider.client.calls), 1)


class TestFactory(unittest.TestCase):
    def test_claude_aliases_resolve(self):
        for name in ("claude", "anthropic"):
            with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=True):
                self.assertIsInstance(ModelProviderFactory.create(name), ClaudeProvider)

    def test_llm_provider_env_wins(self):
        env = {"LLM_PROVIDER": "claude", "GITHUB_TOKEN": "ghp_x", "ANTHROPIC_API_KEY": "sk"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ModelProviderFactory._detect_provider(), "claude")

    def test_anthropic_key_detected_before_github(self):
        env = {"ANTHROPIC_API_KEY": "sk", "GITHUB_TOKEN": "ghp_x"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(ModelProviderFactory._detect_provider(), "claude")

    def test_missing_optional_sdk_does_not_break_claude(self):
        """A broken copilot/openai import must not take Claude down with it."""
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk"}, clear=True):
            with mock.patch.dict(sys.modules, {"openai": None, "copilot": None}):
                self.assertIsInstance(ModelProviderFactory.create("claude"), ClaudeProvider)

    def test_unknown_provider_lists_alternatives(self):
        with self.assertRaises(ValueError) as ctx:
            ModelProviderFactory.create("nope")
        self.assertIn("claude", str(ctx.exception))


class TestJSONExtraction(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_with_preamble(self):
        self.assertEqual(extract_json('Sure!\n{"a": 1}\nHope that helps.'), {"a": 1})

    def test_unparseable_returns_none(self):
        self.assertIsNone(extract_json("no json here"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
