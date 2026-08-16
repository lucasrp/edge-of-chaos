"""O fenótipo só carrega fonte que já SENTIU — presença de chave não é chave viva.

`_sources_from_inventory` montava o roster a partir dos arquivos presentes em `secrets/`, sem
uma única chamada de verificação. Observado no nascimento de um install real: `x` (xai) entrou
no agent.yaml automaticamente com uma chave que responde HTTP 403 — fonte morta declarada viva —
enquanto `exa` entrou pelo mesmo caminho e, por acaso, respondia.

O dano é assimétrico: uma fonte morta declarada viva transforma um delta silenciosamente vazio
em "nada novo no mundo", que é o pior modo de falha para um órgão cuja função é notar o que
mudou. Por isso "não sei perguntar" (None -> unverified) é um estado DISTINTO de "perguntei e
não respondeu" (False -> dark).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402

INV = {"files": ["exa.env", "xai.env", "github.env"],
       "vars": ["EXA_API_KEY", "XAI_API_KEY", "GITHUB_TOKEN"]}


class SourcesCarryTheirProbedStatus(unittest.TestCase):
    def test_status_distinguishes_alive_dead_and_unknown(self):
        answers = {"exa": True, "x": False, "github": None}
        rows = onboarding._sources_from_inventory(INV, probe=answers.get)
        got = {r["name"]: r["status"] for r in rows}
        self.assertEqual(got, {"exa": "on", "x": "dark", "github": "unverified"})

    def test_without_a_probe_the_historical_behaviour_is_kept(self):
        rows = onboarding._sources_from_inventory(INV)
        self.assertTrue(rows)
        self.assertFalse(any("status" in r for r in rows),
                         "sem probe nenhum status é AFIRMADO — declarar 'on' sem perguntar é "
                         "exatamente o defeito")

    def test_probe_reports_dead_key_as_dark_not_as_unknown(self):
        """Chave presente que não responde é `dark`; sem chave nenhuma, também."""
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp)
            (secrets / "exa.env").write_text('EXA_API_KEY="k"\n')

            class _HTTPError(Exception):
                pass
            import urllib.error
            def opener(req, timeout=None):
                raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
            self.assertIs(onboarding.probe_source("exa", secrets, opener=opener), False)
            self.assertIs(onboarding.probe_source("x", secrets, opener=opener), False,
                          "sem chave no arquivo, a fonte não está viva")

    def test_network_outage_is_unknown_never_dead(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp)
            (secrets / "exa.env").write_text('EXA_API_KEY="k"\n')
            def opener(req, timeout=None):
                raise OSError("rede fora")
            self.assertIsNone(onboarding.probe_source("exa", secrets, opener=opener),
                              "rede indisponível não é chave morta — marcar dark aqui seria "
                              "condenar uma fonte viva por um problema do host")

    def test_secret_value_is_read_but_never_returned_by_the_roster(self):
        with tempfile.TemporaryDirectory() as tmp:
            secrets = Path(tmp)
            (secrets / "exa.env").write_text('export EXA_API_KEY="segredo-real"\n')
            self.assertEqual(onboarding._secret_value(secrets, "exa.env", "EXA_API_KEY"),
                             "segredo-real")
            rows = onboarding._sources_from_inventory(INV, probe=lambda n: True)
            self.assertNotIn("segredo-real", repr(rows), "o roster nunca carrega o valor da chave")


if __name__ == "__main__":
    unittest.main()
