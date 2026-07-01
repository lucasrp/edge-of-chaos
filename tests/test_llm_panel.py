"""Dashboard /llm — o painel de rotas LLM (issue #55).

O painel é um adapter FINO sobre llm_routes: lista cada rota com provider/modelo/credencial,
proba sob demanda, troca o provider sem editar YAML na mão (atrás do authorize_write), exibe
a rota embedding EM SEPARADO com o aviso de não-coberta-pela-assinatura, e mostra os
`llm.infra_error` recentes do log (quota morta visível como infra, não como reprovação).
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

AGENT_YAML = """\
name: tester
routers:
  chat:
    provider: openai
    secret_ref: openai.env:OPENAI_API_KEY
    model: gpt-5.4
  review:
    provider: xai
    secret_ref: xai.env:XAI_API_KEY
    model: grok-4.3
  embedding:
    provider: openai
    secret_ref: openai.env:OPENAI_API_KEY
    model: text-embedding-3-small
sources: []
"""


class TestLLMPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "agent.yaml").write_text(AGENT_YAML)
        (root / "secrets").mkdir()
        (root / "secrets" / "openai.env").write_text("OPENAI_API_KEY=sk-x\n")
        (root / "entries").mkdir()
        log = root / "log.jsonl"
        log.write_text(json.dumps({
            "seq": 1, "ts": "2026-07-01T12:00:00+00:00", "type": "llm.infra_error",
            "subject": "close", "payload": {"status": 429, "detail": "insufficient_quota"},
        }) + "\n")

        os.environ["EDGE_BLOG_ENTRIES"] = str(root / "entries")
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(log)
        os.environ["EDGE_REPO"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "test:operator"
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()
        self.root = root

    def tearDown(self):
        for k in ("EDGE_REPO", "EDGE_DASH_AUTH"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_panel_lists_routes_with_provider_model_credential(self):
        r = self.client.get("/llm")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        for needle in ("chat", "review", "embedding", "gpt-5.4", "grok-4.3", "openai", "xai"):
            self.assertIn(needle, body)

    def test_embedding_route_is_separated_with_subscription_warning(self):
        body = self.client.get("/llm").data.decode()
        self.assertIn("sem endpoint de embedding", body)

    def test_recent_infra_errors_are_shown(self):
        body = self.client.get("/llm").data.decode()
        self.assertIn("insufficient_quota", body)
        self.assertIn("429", body)

    def test_switch_provider_rewrites_agent_yaml(self):
        r = self.client.post("/llm/provider", data={"route": "review", "provider": "codex"})
        self.assertIn(r.status_code, (302, 303))
        self.assertIn("provider: codex", (self.root / "agent.yaml").read_text())

    def test_codex_on_embedding_is_refused_with_400(self):
        r = self.client.post("/llm/provider", data={"route": "embedding", "provider": "codex"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("provider: openai", (self.root / "agent.yaml").read_text())

    def test_probe_renders_result_inline(self):
        self.server.llm_routes.probe_route = (
            lambda route, repo=None: {"ok": True, "status": 200, "detail": "OK (probe fake)"})
        r = self.client.post("/llm/probe", data={"route": "chat"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("OK (probe fake)", r.data.decode())

    def test_writes_require_authorization(self):
        os.environ["EDGE_DASH_AUTH"] = "on"
        try:
            r = self.client.post("/llm/provider", data={"route": "review", "provider": "codex"},
                                 environ_base={"REMOTE_ADDR": "10.9.9.9"})
            self.assertin_403_family(r.status_code)
        finally:
            os.environ["EDGE_DASH_AUTH"] = "test:operator"

    def assertin_403_family(self, code):
        self.assertIn(code, (401, 403))


if __name__ == "__main__":
    unittest.main()
