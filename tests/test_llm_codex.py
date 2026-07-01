"""_llm codex provider + transport-error classification (issue #55).

These pin the PURE half: client construction, provider dispatch in complete/probe, and the
401/403/429/insufficient_quota → LLMTransportError classification — with the codex subprocess
behind the injected `_codex_exec` seam, so no CLI nor API is touched. The live `codex exec`
call is exercised in the deploy/verify step, not here.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _llm  # noqa: E402


class FakeAPIError(Exception):
    """Shaped like an openai SDK error: carries .status_code."""
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


class FakeChatClient:
    """Openai-compatible client whose chat call raises a canned error."""
    def __init__(self, error):
        self._error = error
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        raise self._error


class MakeClientCodex(unittest.TestCase):
    def test_codex_needs_no_api_key(self):
        client = _llm.make_client({"provider": "codex"}, api_key=None)
        self.assertIsInstance(client, _llm.CodexClient)

    def test_unknown_provider_still_raises(self):
        with self.assertRaises(ValueError):
            _llm.make_client({"provider": "nope"}, api_key="k")


class CompleteViaCodex(unittest.TestCase):
    def test_complete_routes_through_codex_exec(self):
        calls = {}

        def fake_exec(prompt, model, max_tokens):
            calls.update(prompt=prompt, model=model, max_tokens=max_tokens)
            return "verdict text"

        client = _llm.CodexClient(exec_fn=fake_exec)
        out = _llm.complete(client, "gpt-5.2-codex", "judge this", max_tokens=123)
        self.assertEqual(out, "verdict text")
        self.assertEqual(calls["prompt"], "judge this")
        self.assertEqual(calls["model"], "gpt-5.2-codex")
        self.assertEqual(calls["max_tokens"], 123)

    def test_codex_failure_is_transport_error(self):
        def broken_exec(prompt, model, max_tokens):
            raise _llm.LLMTransportError("codex exec exit 1: not logged in")

        client = _llm.CodexClient(exec_fn=broken_exec)
        with self.assertRaises(_llm.LLMTransportError):
            _llm.complete(client, "gpt-5.2-codex", "p")


class TransportClassification(unittest.TestCase):
    """API-side billing/auth/quota failures must surface TYPED, never as content."""

    def test_quota_429_becomes_transport_error(self):
        client = FakeChatClient(FakeAPIError("insufficient_quota", status_code=429))
        with self.assertRaises(_llm.LLMTransportError) as ctx:
            _llm.complete(client, "gpt-5.4", "p")
        self.assertEqual(ctx.exception.status, 429)

    def test_auth_401_becomes_transport_error(self):
        client = FakeChatClient(FakeAPIError("bad key", status_code=401))
        with self.assertRaises(_llm.LLMTransportError):
            _llm.complete(client, "gpt-5.4", "p")

    def test_insufficient_quota_without_status_becomes_transport_error(self):
        client = FakeChatClient(FakeAPIError("You exceeded your quota: insufficient_quota"))
        with self.assertRaises(_llm.LLMTransportError):
            _llm.complete(client, "gpt-5.4", "p")

    def test_other_errors_still_raise_unchanged(self):
        boom = FakeAPIError("model_not_found", status_code=404)
        client = FakeChatClient(boom)
        with self.assertRaises(FakeAPIError):
            _llm.complete(client, "gpt-5.4", "p")


class ProbeCodex(unittest.TestCase):
    def test_probe_chat_ok(self):
        client = _llm.CodexClient(exec_fn=lambda p, m, t: "ok")
        r = _llm.probe(client, "gpt-5.2-codex")
        self.assertTrue(r["ok"])

    def test_probe_chat_failure_reports_not_raises(self):
        def broken(p, m, t):
            raise _llm.LLMTransportError("codex CLI ausente", status=None)

        r = _llm.probe(_llm.CodexClient(exec_fn=broken), "gpt-5.2-codex")
        self.assertFalse(r["ok"])
        self.assertIn("codex", r["detail"])

    def test_probe_embedding_on_codex_is_unsupported(self):
        r = _llm.probe(_llm.CodexClient(exec_fn=lambda p, m, t: "ok"),
                       "text-embedding-3-small", kind="embedding")
        self.assertFalse(r["ok"])
        self.assertIn("embedding", r["detail"])


if __name__ == "__main__":
    unittest.main()
