"""embedding_from_inventory multi-provider — o adapter nasce no fenótipo (operador
2026-07-25: "pode ser um openrouter, um azure, um openai direto"). Escolha explícita da
entrevista vence; sem escolha, auto-detecção por var conhecida; sem chave, dark (None).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


def _inv(**by_file):
    vars_ = sorted({v for names in by_file.values() for v in names})
    return {"files": list(by_file), "vars": vars_, "by_file": by_file}


class EmbeddingAdapter(unittest.TestCase):
    def test_openai_autodetect_keeps_todays_contract(self):
        e = onboarding.embedding_from_inventory(_inv(**{"openai.env": ["OPENAI_API_KEY"]}))
        self.assertEqual(e["provider"], "openai")
        self.assertEqual(e["secret_ref"], "openai.env:OPENAI_API_KEY")
        self.assertEqual(e["model"], "text-embedding-3-small")

    def test_openrouter_autodetected_by_var(self):
        e = onboarding.embedding_from_inventory(
            _inv(**{"openrouter.env": ["OPENROUTER_API_KEY"]}))
        self.assertEqual(e["provider"], "openrouter")
        self.assertEqual(e["secret_ref"], "openrouter.env:OPENROUTER_API_KEY")

    def test_explicit_choice_wins_over_autodetect(self):
        inv = _inv(**{"openai.env": ["OPENAI_API_KEY"],
                      "azure.env": ["AZURE_OPENAI_API_KEY"]})
        e = onboarding.embedding_from_inventory(
            inv, provider="azure", var="AZURE_OPENAI_API_KEY",
            base_url="https://meu-rec.openai.azure.com/openai/v1",
            model="text-embedding-3-large")
        self.assertEqual(e["provider"], "azure")
        self.assertEqual(e["secret_ref"], "azure.env:AZURE_OPENAI_API_KEY")
        self.assertEqual(e["base_url"], "https://meu-rec.openai.azure.com/openai/v1")
        self.assertEqual(e["model"], "text-embedding-3-large")

    def test_explicit_var_missing_from_secrets_is_loud(self):
        with self.assertRaises(ValueError):
            onboarding.embedding_from_inventory(
                _inv(**{"openai.env": ["OPENAI_API_KEY"]}),
                provider="openrouter", var="OPENROUTER_API_KEY")

    def test_no_key_is_dark(self):
        self.assertIsNone(onboarding.embedding_from_inventory(_inv()))


class RouterCarriesBaseUrl(unittest.TestCase):
    def test_base_url_flows_into_the_embedding_router(self):
        emb = {"secret_ref": "azure.env:AZURE_OPENAI_API_KEY", "provider": "azure",
               "model": "text-embedding-3-small",
               "base_url": "https://x.openai.azure.com/openai/v1"}
        r = onboarding._routers_for_cfg({"mode": "self", "members": ["self"]},
                                        "claude", emb)
        self.assertEqual(r["embedding"]["base_url"], emb["base_url"])


if __name__ == "__main__":
    unittest.main()
