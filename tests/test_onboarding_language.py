"""Language adapts to the operator — the docs default is en-US, but the rite mirrors the
language the operator speaks, and finish lands that choice in the phenotype via
emit_phenotype(language=). Absent a choice, the default stays en.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


class EmitPersistsLanguage(unittest.TestCase):
    def test_default_language_is_en(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3, provision_skills=False)
            cfg = yaml.safe_load(Path(onboarding.emit_phenotype(tmp)).read_text())
            self.assertEqual(cfg.get("language"), "en")

    def test_operator_language_lands_in_agent_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3, provision_skills=False)
            cfg = yaml.safe_load(
                Path(onboarding.emit_phenotype(tmp, language="pt-BR")).read_text())
            self.assertEqual(cfg.get("language"), "pt-BR")


if __name__ == "__main__":
    unittest.main()
