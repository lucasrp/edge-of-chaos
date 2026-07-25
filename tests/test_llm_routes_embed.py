"""llm_routes.embed_fn — o adapter de embeddings em RUNTIME: routers.embedding do
agent.yaml → callable text→vector via _llm.make_client (base_url explícito vence o
registry — azure/custom entram por aí). Rota ausente ou sem chave = None (caller escurece).
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import llm_routes  # noqa: E402


def _install(tmp, routers_yaml, secret=None):
    root = Path(tmp)
    (root / "agent.yaml").write_text(routers_yaml)
    if secret:
        (root / "secrets").mkdir(exist_ok=True)
        (root / "secrets" / secret[0]).write_text(secret[1])
    return root


class _FakeClient:
    def __init__(self):
        self.calls = []
        outer = self

        class _E:
            def create(self, model, input):
                outer.calls.append((model, input))
                return type("R", (), {"data": [type("D", (), {"embedding": [0.1, 0.2]})()]})()
        self.embeddings = _E()


class EmbedFn(unittest.TestCase):
    def test_absent_route_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _install(tmp, "routers:\n  chat: {provider: claude}\n")
            self.assertIsNone(llm_routes.embed_fn(repo=root))

    def test_route_without_key_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _install(tmp, (
                "routers:\n  embedding:\n    provider: openai\n"
                "    secret_ref: openai.env:OPENAI_API_KEY\n"))
            with mock.patch.dict("os.environ", {}, clear=True):
                self.assertIsNone(llm_routes.embed_fn(repo=root))

    def test_wired_route_builds_client_and_embeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _install(tmp, (
                "routers:\n  embedding:\n    provider: azure\n"
                "    secret_ref: azure.env:AZURE_OPENAI_API_KEY\n"
                "    base_url: https://x.openai.azure.com/openai/v1\n"
                "    model: text-embedding-3-large\n"),
                secret=("azure.env", "AZURE_OPENAI_API_KEY=k1\n"))
            fake = _FakeClient()
            with mock.patch.object(llm_routes._llm_mod(), "make_client",
                                   return_value=fake) as mk:
                fn = llm_routes.embed_fn(repo=root)
                vec = fn("hello")
            self.assertEqual(vec, [0.1, 0.2])
            self.assertEqual(fake.calls, [("text-embedding-3-large", "hello")])
            router_arg, key_arg = mk.call_args[0]
            self.assertEqual(router_arg["base_url"], "https://x.openai.azure.com/openai/v1")
            self.assertEqual(key_arg, "k1")


if __name__ == "__main__":
    unittest.main()
