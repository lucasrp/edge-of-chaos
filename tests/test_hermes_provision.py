"""Hermes é a 4ª CLI padrão (operador 2026-07-25) — paridade com claude/codex/grok.

Hermes descobre user-skills de HERMES_HOME/skills/<name>/SKILL.md (mesma convenção
SKILL.md). Os wrappers são finos e apontam pro contrato canônico do install — mesmo
shape dos wrappers grok/codex. Genérico: nada de ed — qualquer install de qualquer
usuário do hermes provisiona igual.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _hermes_provision  # noqa: E402
import surfaces_cfg  # noqa: E402


class WrapperRender(unittest.TestCase):
    def test_wrapper_points_to_canonical_contract(self):
        out = _hermes_provision.render_hermes_skill(
            slug="wake", prefix="ed", canonical_skill=Path("/x/skills/wake/SKILL.md"))
        self.assertIn("name: ed-wake", out)
        self.assertIn("/x/skills/wake/SKILL.md", out)
        self.assertIn("canonical contract", out)


class ProvisionTree(unittest.TestCase):
    def test_provisions_prefixed_wrappers_under_hermes_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "skills" / "wake").mkdir(parents=True)
            (repo / "skills" / "wake" / "SKILL.md").write_text("---\nname: wake\n---\nx")
            (repo / "skills" / "_shared").mkdir()
            (repo / "skills" / "_shared" / "pipeline.md").write_text("y")
            edge_home = root / "home"
            hermes_home = root / ".hermes"
            cfg = {"skill_prefix": "ed", "tool_prefix": "edge"}
            _hermes_provision.provision_hermes(cfg, repo, edge_home, hermes_home)
            self.assertTrue(
                (hermes_home / "skills" / "ed-wake" / "SKILL.md").is_file())
            self.assertTrue(
                (hermes_home / "skills" / "edge-wake" / "SKILL.md").is_file())
            # _shared não vira wrapper
            self.assertFalse((hermes_home / "skills" / "ed-_shared").exists())


class SurfaceDetection(unittest.TestCase):
    def test_hermes_detected_by_home_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".hermes").mkdir()
            out = surfaces_cfg.detect_installed_surfaces(env={}, home=home)
            self.assertTrue(out["hermes"])
            self.assertFalse(out["grok"])

    def test_hermes_home_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            alt = Path(tmp) / "alt-hermes"
            alt.mkdir()
            out = surfaces_cfg.detect_installed_surfaces(
                env={"HERMES_HOME": str(alt)}, home=Path(tmp))
            self.assertTrue(out["hermes"])

    def test_installed_hermes_enters_the_surfaces_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".hermes").mkdir()
            block = surfaces_cfg.surfaces_block_for_installed(env={}, home=home)
            self.assertEqual(block["hermes"], {"enabled": True, "home": "~/.hermes"})


if __name__ == "__main__":
    unittest.main()
