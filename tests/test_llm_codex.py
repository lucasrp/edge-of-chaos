"""_llm codex provider + transport-error classification (issue #55).

These pin the PURE half: client construction, provider dispatch in complete/probe, and the
401/403/429/insufficient_quota → LLMTransportError classification — with the codex subprocess
behind the injected `_codex_exec` seam, so no CLI nor API is touched. The live `codex exec`
call is exercised in the deploy/verify step, not here.
"""
import sys
import tempfile
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


class CodexExecCommand(unittest.TestCase):
    """The nested completer gets a disposable writable CODEX_HOME and keeps its
    model-generated commands in the read-only sandbox."""

    def test_uses_disposable_auth_only_home_and_cleans_it(self):
        from unittest import mock

        seen = {}
        with tempfile.TemporaryDirectory() as source:
            auth = Path(source) / "auth.json"
            auth.write_text('{"token":"not-a-real-secret"}')

            def fake_run(cmd, **kw):
                seen["cmd"] = cmd
                seen["env"] = kw["env"]
                seen["input"] = kw["input"]
                tmp_home = Path(kw["env"]["CODEX_HOME"])
                seen["tmp_home"] = tmp_home
                seen["auth_mode"] = (tmp_home / "auth.json").stat().st_mode & 0o777
                self.assertEqual(
                    sorted(p.name for p in tmp_home.iterdir()), ["auth.json"]
                )
                Path(cmd[cmd.index("-o") + 1]).write_text("NESTED_OK")
                return _Result(0, "", "")

            with mock.patch.dict(_llm.os.environ, {"CODEX_HOME": source}), \
                 mock.patch("_llm.subprocess.run", fake_run):
                self.assertEqual(_llm._codex_exec("one word", "gpt-test", 8), "NESTED_OK")

        self.assertEqual(seen["input"], "one word")
        self.assertEqual(seen["auth_mode"], 0o600)
        self.assertFalse(seen["tmp_home"].exists())
        self.assertIn("read-only", seen["cmd"])
        self.assertIn("--ignore-user-config", seen["cmd"])
        self.assertIn("--ephemeral", seen["cmd"])

    def test_missing_auth_is_typed_transport_failure(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as source, \
             mock.patch.dict(_llm.os.environ, {"CODEX_HOME": source}):
            with self.assertRaises(_llm.LLMTransportError) as ctx:
                _llm._codex_exec("p", None, 8)
        self.assertIn("autenticação", str(ctx.exception))


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


class MakeClientClaude(unittest.TestCase):
    def test_claude_needs_no_api_key(self):
        client = _llm.make_client({"provider": "claude"}, api_key=None)
        self.assertIsInstance(client, _llm.ClaudeClient)


class CompleteViaClaude(unittest.TestCase):
    def test_complete_routes_through_claude_exec(self):
        calls = {}

        def fake_exec(prompt, model, max_tokens):
            calls.update(prompt=prompt, model=model, max_tokens=max_tokens)
            return "completion text"

        client = _llm.ClaudeClient(exec_fn=fake_exec)
        out = _llm.complete(client, "opus", "write this", max_tokens=123)
        self.assertEqual(out, "completion text")
        self.assertEqual(calls["prompt"], "write this")
        self.assertEqual(calls["model"], "opus")
        self.assertEqual(calls["max_tokens"], 123)

    def test_claude_failure_is_transport_error(self):
        def broken_exec(prompt, model, max_tokens):
            raise _llm.LLMTransportError("claude -p exit 1: Not logged in")

        client = _llm.ClaudeClient(exec_fn=broken_exec)
        with self.assertRaises(_llm.LLMTransportError):
            _llm.complete(client, "opus", "p")


class ClaudeExecCommand(unittest.TestCase):
    """The real _claude_exec builds a print-mode, no-tools command and treats any
    non-zero exit / missing binary / timeout as TRANSPORT — never returns text."""

    def _run(self, fake_run):
        from unittest import mock
        with mock.patch("_llm.subprocess.run", fake_run):
            return _llm._claude_exec("hi there", "opus", 800)

    def test_command_is_print_mode_and_disables_all_tools(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            seen["input"] = kw.get("input")
            return _Result(0, "pong", "")

        self.assertEqual(self._run(fake_run), "pong")
        cmd = seen["cmd"]
        self.assertEqual(cmd[0], "claude")
        self.assertIn("-p", cmd)
        self.assertIn("opus", cmd)                       # model passed through
        # no-tools flag: --tools "" disables all built-in tools
        i = cmd.index("--tools")
        self.assertEqual(cmd[i + 1], "")
        self.assertIn("--strict-mcp-config", cmd)        # no MCP tool escape
        self.assertIn("--no-session-persistence", cmd)   # no session-store pollution
        self.assertEqual(seen["input"], "hi there")      # prompt via stdin

    def test_nonzero_exit_is_transport_error(self):
        def fake_run(cmd, **kw):
            return _Result(1, "", "Not logged in")

        from unittest import mock
        with mock.patch("_llm.subprocess.run", fake_run):
            with self.assertRaises(_llm.LLMTransportError):
                _llm._claude_exec("p", "opus", 800)

    def test_missing_binary_is_transport_error(self):
        def fake_run(cmd, **kw):
            raise FileNotFoundError("claude")

        from unittest import mock
        with mock.patch("_llm.subprocess.run", fake_run):
            with self.assertRaises(_llm.LLMTransportError):
                _llm._claude_exec("p", "opus", 800)


class _Result:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class ProbeClaude(unittest.TestCase):
    def test_probe_chat_ok(self):
        client = _llm.ClaudeClient(exec_fn=lambda p, m, t: "ok")
        r = _llm.probe(client, "opus")
        self.assertTrue(r["ok"])

    def test_probe_chat_failure_reports_not_raises(self):
        def broken(p, m, t):
            raise _llm.LLMTransportError("claude CLI ausente", status=None)

        r = _llm.probe(_llm.ClaudeClient(exec_fn=broken), "opus")
        self.assertFalse(r["ok"])
        self.assertIn("claude", r["detail"])

    def test_probe_embedding_on_claude_is_unsupported(self):
        r = _llm.probe(_llm.ClaudeClient(exec_fn=lambda p, m, t: "ok"),
                       "text-embedding-3-small", kind="embedding")
        self.assertFalse(r["ok"])
        self.assertIn("embedding", r["detail"])


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
