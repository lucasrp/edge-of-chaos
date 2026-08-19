"""#154 — install em host ocupado NUNCA clobbera outro install.

(1) bootstrap recusa --home que já contém identidade de OUTRO nome (bootstrap.json
ou agent.yaml); mesmo nome = re-bootstrap idempotente, segue. (2) provision_claude
recusa sobrescrever CLAUDE.md de codename diferente — fail loud, nunca overwrite
(caso ed×turing 2026-07-25: 3 colonizações no mesmo dia).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402
import _claude_provision  # noqa: E402


class BootstrapRefusesOccupiedHome(unittest.TestCase):
    def test_other_install_bootstrap_json_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state").mkdir()
            (Path(tmp) / "state" / "bootstrap.json").write_text(json.dumps({"name": "ed"}))
            with self.assertRaisesRegex(ValueError, "ed"):
                onboarding.run_bootstrap(home=tmp, name="turing", backfill_days=3,
                                         provision_skills=False)

    def test_other_install_agent_yaml_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent.yaml").write_text("name: ed\n")
            with self.assertRaisesRegex(ValueError, "ed"):
                onboarding.run_bootstrap(home=tmp, name="turing", backfill_days=3,
                                         provision_skills=False)

    def test_same_name_rebootstrap_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state").mkdir()
            (Path(tmp) / "state" / "bootstrap.json").write_text(json.dumps({"name": "turing"}))
            out = onboarding.run_bootstrap(home=tmp, name="turing", backfill_days=3,
                                           provision_skills=False)
            self.assertEqual(out["name"], "turing")


class ProvisionRefusesForeignHarness(unittest.TestCase):
    def test_foreign_claude_md_refuses(self):
        """Um CLAUDE.md gerenciado por OUTRO install não é sobrescrito (#154).

        A fixture tem que carregar o marcador que templates/CLAUDE.md.tpl renderiza
        ('Codename: **…**'); sem ele o guarda entra pelo ramo 'não é gerenciado pelo edge'
        e o teste passaria pelo motivo errado — foi o que aconteceu enquanto ele esteve
        vermelho, com o regex 'ed' casando no 'edge' da OUTRA mensagem."""
        with tempfile.TemporaryDirectory() as tmp:
            ch = Path(tmp) / ".claude"
            ch.mkdir()
            (ch / "CLAUDE.md").write_text(
                "# ed\n\n## Identity\n\n**My name is ed.** Codename: **ed**.\n")
            with self.assertRaisesRegex(RuntimeError, r"pertence ao install 'ed'"):
                _claude_provision.provision_claude(
                    {"name": "turing", "codename": "turing"}, REPO, ch)

    def test_unmanaged_claude_md_refuses_with_its_own_reason(self):
        """O CLAUDE.md do próprio operador (sem marcador) tem recusa DISTINTA da de dono alheio.

        Confundir as duas foi o falso positivo do #154: '# CLAUDE.md' virava owner='CLAUDE.md'
        e travava todo install num host com CLAUDE.md próprio."""
        with tempfile.TemporaryDirectory() as tmp:
            ch = Path(tmp) / ".claude"
            ch.mkdir()
            (ch / "CLAUDE.md").write_text("# CLAUDE.md\n\nminhas regras\n")
            with self.assertRaisesRegex(RuntimeError, "não é gerenciado pelo edge"):
                _claude_provision.provision_claude(
                    {"name": "turing", "codename": "turing"}, REPO, ch)

    def test_same_codename_overwrites_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            ch = Path(tmp) / ".claude"
            ch.mkdir()
            (ch / "CLAUDE.md").write_text(
                "# turing\n\n**My name is turing.** Codename: **turing**.\n\nvelho\n")
            rows = _claude_provision.provision_claude(
                {"name": "turing", "codename": "turing"}, REPO, ch)
            self.assertTrue(any("CLAUDE.md" in r for r in rows))

    def test_owner_matching_name_but_not_codename_is_same_install(self):
        """Caso de campo (petertosh 2026-07-28): header rendered do NAME ('peter tosh'),
        guard comparava só o codename ('petertosh') → falso positivo no PRÓPRIO install."""
        with tempfile.TemporaryDirectory() as tmp:
            ch = Path(tmp) / ".claude"
            ch.mkdir()
            (ch / "CLAUDE.md").write_text(
                "# peter tosh\n\n## Identity\n\n"
                "**My name is peter tosh.** Codename: **peter tosh**.\n")
            rows = _claude_provision.provision_claude(
                {"name": "peter tosh", "codename": "petertosh"}, REPO, ch)
            self.assertTrue(any("CLAUDE.md" in r for r in rows))


if __name__ == "__main__":
    unittest.main()
