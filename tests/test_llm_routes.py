"""Public LLM routing surfaces are Hermes-only for completion."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _llm  # noqa: E402
import llm_routes  # noqa: E402
import runtime_policy  # noqa: E402


AGENT = """\
routers:
  chat:
    provider: hermes
    model: default
  review:
    provider: hermes
    model: default
  embedding:
    provider: openai
    model: text-embedding-3-small
    secret_ref: openai.env:OPENAI_API_KEY
"""


def temp_repo(openai_key="sk-test"):
    root = Path(tempfile.mkdtemp())
    (root / "agent.yaml").write_text(AGENT)
    if openai_key is not None:
        (root / "secrets").mkdir()
        (root / "secrets" / "openai.env").write_text("OPENAI_API_KEY=" + str(openai_key))
    return root


class Routes(unittest.TestCase):
    def test_lists_routes_without_exposing_secret_values(self):
        repo = temp_repo()
        rows = {row["route"]: row for row in llm_routes.routes(repo=repo)}
        self.assertEqual(rows["chat"]["provider"], "hermes")
        self.assertTrue(rows["chat"]["subscription"])
        self.assertEqual(rows["embedding"]["credential"], "ok")
        self.assertNotIn("sk-test", repr(rows))

    def test_missing_embedding_secret_is_reported_without_value(self):
        repo = temp_repo(openai_key=None)
        rows = {row["route"]: row for row in llm_routes.routes(repo=repo)}
        self.assertEqual(rows["embedding"]["credential"], "ausente")


class SetProvider(unittest.TestCase):
    def test_allowed_provider_options_are_route_specific(self):
        self.assertEqual(llm_routes.allowed_providers_for_route("chat"), ("hermes",))
        self.assertEqual(
            set(llm_routes.allowed_providers_for_route("embedding")),
            set(runtime_policy.ALLOWED_EMBEDDING_PROVIDERS),
        )

    def test_completion_rejects_every_external_provider_before_write(self):
        for provider in ("claude", "codex", "grok", "xai", "openrouter", "openai"):
            with self.subTest(provider=provider):
                repo = temp_repo()
                before = (repo / "agent.yaml").read_bytes()
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    llm_routes.set_provider("chat", provider, repo=repo)
                self.assertEqual((repo / "agent.yaml").read_bytes(), before)

    def test_hermes_completion_model_can_be_updated_without_touching_other_routes(self):
        repo = temp_repo()
        llm_routes.set_provider("review", "hermes", repo=repo, model="provider/model")
        rows = {row["route"]: row for row in llm_routes.routes(repo=repo)}
        self.assertEqual(rows["review"]["provider"], "hermes")
        self.assertEqual(rows["review"]["model"], "provider/model")
        self.assertEqual(rows["chat"]["provider"], "hermes")
        self.assertEqual(rows["embedding"]["provider"], "openai")

    def test_embedding_uses_closed_provider_policy(self):
        repo = temp_repo()
        llm_routes.set_provider(
            "embedding", "openrouter", repo=repo, model="text-embedding-safe"
        )
        rows = {row["route"]: row for row in llm_routes.routes(repo=repo)}
        self.assertEqual(rows["embedding"]["provider"], "openrouter")
        before = (repo / "agent.yaml").read_bytes()
        for provider in ("claude", "codex", "grok", "xai"):
            with self.subTest(provider=provider):
                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    llm_routes.set_provider("embedding", provider, repo=repo)
                self.assertEqual((repo / "agent.yaml").read_bytes(), before)

    def test_unknown_route_is_rejected_before_write(self):
        repo = temp_repo()
        before = (repo / "agent.yaml").read_bytes()
        with self.assertRaises(ValueError):
            llm_routes.set_provider("unknown", "hermes", repo=repo)
        self.assertEqual((repo / "agent.yaml").read_bytes(), before)


class CompleterFor(unittest.TestCase):
    def test_hermes_route_uses_guarded_factory_and_exec_seam(self):
        repo = temp_repo(openai_key=None)
        seen = {}

        def fake_exec(prompt, model, max_tokens):
            seen.update(prompt=prompt, model=model, max_tokens=max_tokens)
            return "ok"

        fn = llm_routes.completer_for("review", repo=repo, exec_fn=fake_exec)
        self.assertEqual(fn("judge"), "ok")
        self.assertEqual(seen["prompt"], "judge")
        self.assertEqual(seen["model"], "default")

    def test_preexisting_external_route_is_rejected_before_exec_or_secret(self):
        for provider in ("claude", "codex", "grok", "xai", "openrouter", "openai"):
            with self.subTest(provider=provider):
                repo = temp_repo(openai_key=None)
                text = (repo / "agent.yaml").read_text()
                text = text.replace("provider: hermes", f"provider: {provider}", 1)
                (repo / "agent.yaml").write_text(text)
                called = []

                def forbidden_exec(*args, **kwargs):
                    called.append((args, kwargs))
                    return "BYPASS"

                with self.assertRaises(runtime_policy.RuntimePolicyError):
                    llm_routes.completer_for("chat", repo=repo, exec_fn=forbidden_exec)
                self.assertEqual(called, [])

    def test_unknown_route_is_rejected(self):
        repo = temp_repo()
        with self.assertRaises(ValueError):
            llm_routes.completer_for("missing", repo=repo)


class Probe(unittest.TestCase):
    def test_external_completion_route_reports_policy_error_without_constructor(self):
        repo = temp_repo(openai_key=None)
        text = (repo / "agent.yaml").read_text().replace(
            "provider: hermes", "provider: xai", 1
        )
        (repo / "agent.yaml").write_text(text)
        out = llm_routes.probe_route("chat", repo=repo)
        self.assertFalse(out["ok"])
        self.assertIn("forbidden", out["detail"])

    def test_embedding_probe_uses_embedding_factory(self):
        repo = temp_repo()
        fake_client = mock.Mock()
        fake_client.embeddings.create.return_value.data = [mock.Mock(embedding=[0.1, 0.2])]
        with mock.patch.object(_llm, "make_embedding_client", return_value=fake_client) as make:
            out = llm_routes.probe_route("embedding", repo=repo)
        self.assertTrue(out["ok"])
        make.assert_called_once()


if __name__ == "__main__":
    unittest.main()
