"""Seeds de doutrina — o purge de 2026-07-25 tirou memory/ do genótipo e levou
method/personality/canone junto; o wake exige (space-0). Genótipo carrega
seeds/memory/, bootstrap copia pro install com {name} rendido, nunca sobrescreve.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


class DoctrineSeeds(unittest.TestCase):
    def test_bootstrap_seeds_doctrine_with_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="zeca", backfill_days=3,
                                     provision_skills=False)
            for f in ("method.md", "personality.md", "canone.md"):
                self.assertTrue((Path(tmp) / "memory" / f).is_file(), f)
            persona = (Path(tmp) / "memory" / "personality.md").read_text()
            self.assertIn("You are **zeca**", persona)
            self.assertNotIn("{name}", persona)

    def test_existing_doctrine_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "memory").mkdir(parents=True)
            (Path(tmp) / "memory" / "method.md").write_text("meu método próprio")
            onboarding.run_bootstrap(home=tmp, name="zeca", backfill_days=3,
                                     provision_skills=False)
            self.assertEqual((Path(tmp) / "memory" / "method.md").read_text(),
                             "meu método próprio")


if __name__ == "__main__":
    unittest.main()
