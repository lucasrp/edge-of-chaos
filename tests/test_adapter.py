"""Adapter LLM — lógica de probe testada com cliente fake (sem rede)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import _llm  # noqa: E402


class Err(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status_code = status


class FakeCompletions:
    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        out = self.behavior(kw)
        if isinstance(out, Exception):
            raise out
        return out


class FakeClient:
    def __init__(self, behavior, emb_behavior=None):
        self.chat = type("C", (), {"completions": FakeCompletions(behavior)})()
        if emb_behavior is not None:
            self.embeddings = FakeCompletions(emb_behavior)


class TestAdapter(unittest.TestCase):
    def test_base_url_registry(self):
        self.assertEqual(_llm.resolve_base_url({"provider": "xai"}), "https://api.x.ai/v1")
        self.assertEqual(_llm.resolve_base_url({"provider": "openai"}), "https://api.openai.com/v1")

    def test_explicit_base_url_wins(self):
        self.assertEqual(_llm.resolve_base_url({"provider": "x", "base_url": "http://b"}), "http://b")

    def test_probe_ok(self):
        r = _llm.probe(FakeClient(lambda kw: object()), "gpt-5.4")
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"], 200)

    def test_probe_403_credit(self):
        cli = FakeClient(lambda kw: Err(403, "team has no permission"))
        r = _llm.probe(cli, "grok-4.3")
        self.assertFalse(r["ok"])
        self.assertEqual(r["status"], 403)

    def test_probe_embedding_uses_embeddings_endpoint(self):
        # se probar embedding como chat, quebra; tem que usar embeddings.create
        cli = FakeClient(
            behavior=lambda kw: Err(404, "not a chat model"),
            emb_behavior=lambda kw: object(),
        )
        r = _llm.probe(cli, "text-embedding-3-small", kind="embedding")
        self.assertTrue(r["ok"], r)

    def test_probe_swaps_token_param(self):
        # provider rejeita max_completion_tokens (400) → deve trocar p/ max_tokens e passar
        def behavior(kw):
            if "max_completion_tokens" in kw:
                return Err(400, "Unsupported parameter: 'max_completion_tokens'")
            return object()
        r = _llm.probe(FakeClient(behavior), "gpt-3.5-turbo")
        self.assertTrue(r["ok"], r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
