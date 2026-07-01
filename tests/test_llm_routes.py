"""llm_routes — o registry por-rota que o dashboard consome (issue #55).

Pinam a metade PURA: leitura das rotas do agent.yaml + saúde da credencial, a troca de
provider por cirurgia de linha (comentários do yaml preservados), as recusas (rota/provider
desconhecidos, codex na rota embedding) e o completer_for resolvido do yaml — com um repo
temporário, sem tocar API nem CLI. O probe live é exercitado no deploy/verify, não aqui.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _llm        # noqa: E402
import llm_routes  # noqa: E402

AGENT_YAML = """\
name: tester
# --- Routers (LLM) — comentário de bloco que a cirurgia de linha DEVE preservar.
routers:
  chat:                                  # contextualization
    provider: openai
    secret_ref: openai.env:OPENAI_API_KEY
    model: gpt-5.4
  review:                                # judge + adversarial
    provider: xai
    secret_ref: xai.env:XAI_API_KEY
    model: grok-4.3
  embedding:                             # RAG
    provider: openai
    secret_ref: openai.env:OPENAI_API_KEY
    model: text-embedding-3-small
sources: []
"""


def temp_repo(openai_key="sk-live", xai_env=False):
    root = Path(tempfile.mkdtemp())
    (root / "agent.yaml").write_text(AGENT_YAML)
    secrets = root / "secrets"
    secrets.mkdir()
    if openai_key is not None:
        (secrets / "openai.env").write_text(f"OPENAI_API_KEY={openai_key}\n")
    if xai_env:
        (secrets / "xai.env").write_text("XAI_API_KEY=xk\n")
    return root


class Routes(unittest.TestCase):
    def test_lists_every_route_with_provider_and_model(self):
        rs = {r["route"]: r for r in llm_routes.routes(repo=temp_repo())}
        self.assertEqual(set(rs), {"chat", "review", "embedding"})
        self.assertEqual(rs["chat"]["provider"], "openai")
        self.assertEqual(rs["review"]["model"], "grok-4.3")

    def test_credential_present_vs_absent(self):
        # hermético: um XAI_API_KEY no env do host venceria o secrets/ (override explícito
        # vence, como _secrets.load_env) — aqui interessa o caminho do arquivo ausente.
        from unittest import mock
        env = {k: v for k, v in os.environ.items() if k != "XAI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            rs = {r["route"]: r for r in llm_routes.routes(repo=temp_repo(xai_env=False))}
        self.assertEqual(rs["chat"]["credential"], "ok")
        self.assertEqual(rs["review"]["credential"], "ausente")

    def test_embedding_route_is_flagged_not_subscription_capable(self):
        rs = {r["route"]: r for r in llm_routes.routes(repo=temp_repo())}
        self.assertTrue(rs["embedding"]["embedding_route"])
        self.assertFalse(rs["chat"]["embedding_route"])

    def test_codex_route_reports_subscription_not_secret(self):
        repo = temp_repo()
        llm_routes.set_provider("review", "codex", repo=repo)
        rs = {r["route"]: r for r in llm_routes.routes(repo=repo)}
        self.assertTrue(rs["review"]["subscription"])
        self.assertIn(rs["review"]["credential"], ("assinatura", "codex CLI ausente"))


class SetProvider(unittest.TestCase):
    def test_switch_review_to_codex_rewrites_only_that_line(self):
        repo = temp_repo()
        llm_routes.set_provider("review", "codex", repo=repo)
        text = (repo / "agent.yaml").read_text()
        self.assertIn("provider: codex", text)
        self.assertIn("provider: openai", text)          # chat/embedding intactos
        self.assertIn("comentário de bloco que a cirurgia", text)  # comentários preservados
        self.assertIn("# judge + adversarial", text)
        rs = {r["route"]: r for r in llm_routes.routes(repo=repo)}
        self.assertEqual(rs["review"]["provider"], "codex")
        self.assertEqual(rs["chat"]["provider"], "openai")

    def test_switch_with_model_rewrites_model_too(self):
        repo = temp_repo()
        llm_routes.set_provider("chat", "codex", repo=repo, model="gpt-5.2-codex")
        rs = {r["route"]: r for r in llm_routes.routes(repo=repo)}
        self.assertEqual(rs["chat"]["model"], "gpt-5.2-codex")

    def test_codex_on_embedding_route_is_refused(self):
        repo = temp_repo()
        with self.assertRaises(ValueError):
            llm_routes.set_provider("embedding", "codex", repo=repo)

    def test_unknown_provider_and_route_are_refused(self):
        repo = temp_repo()
        with self.assertRaises(ValueError):
            llm_routes.set_provider("review", "nope", repo=repo)
        with self.assertRaises(ValueError):
            llm_routes.set_provider("nope", "openai", repo=repo)


class CompleterFor(unittest.TestCase):
    def test_codex_route_yields_codex_backed_completer(self):
        repo = temp_repo(openai_key=None)   # SEM chave de API nenhuma
        llm_routes.set_provider("review", "codex", repo=repo)
        seen = {}

        def fake_exec(prompt, model, max_tokens):
            seen.update(prompt=prompt, model=model)
            return '{"pass": true}'

        fn = llm_routes.completer_for("review", repo=repo, exec_fn=fake_exec)
        self.assertEqual(fn("judge"), '{"pass": true}')
        self.assertEqual(seen["prompt"], "judge")

    def test_api_route_without_key_raises_transport_error(self):
        repo = temp_repo(openai_key=None)
        with self.assertRaises(_llm.LLMTransportError):
            llm_routes.completer_for("chat", repo=repo)


if __name__ == "__main__":
    unittest.main()
