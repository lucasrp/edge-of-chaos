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
            slug="wake", prefix="ed", canonical_skill=Path("/x/skills/wake/SKILL.md"),
            edge_group="hive")
        self.assertIn("name: ed-wake", out)
        self.assertIn("EDGE_GROUP=hive", out)
        self.assertIn("/x/skills/wake/SKILL.md", out)
        self.assertIn("canonical contract", out)
        self.assertIn("human-facing orientation", out)
        self.assertIn("ask what the operator wants to work on", out)
        self.assertIn("Do not start work before their reply", out)

    def test_terminal_invariant_is_wake_only(self):
     out = _hermes_provision.render_hermes_skill(
      slug="recall", prefix="ed", canonical_skill=Path("/x/skills/recall/SKILL.md"),
      edge_group="hive")
     self.assertNotIn("WAKE TERMINAL INVARIANT", out)

    def test_every_canonical_skill_gets_a_thin_wrapper(self):
     skills = Path(__file__).parents[1] / "skills"
     for canonical in sorted(skills.glob("*/SKILL.md")):
      slug = canonical.parent.name
      with self.subTest(slug=slug):
       out = _hermes_provision.render_hermes_skill(
        slug, "Steve", canonical, edge_group="hive")
       self.assertIn(f"name: Steve-{slug}", out)
       self.assertIn(str(canonical.resolve()), out)
       self.assertLess(len(out), 5_000)

    def test_mentor_wrapper_preserves_cadence_invariants(self):
        out = _hermes_provision.render_hermes_skill(
            slug="mentor", prefix="Steve", canonical_skill=Path("/x/skills/mentor/SKILL.md"),
            edge_group="hive")
        self.assertIn("observe leveling-state and the operator's work first", out)
        self.assertIn("cite one state line", out)
        self.assertIn("opt-in portfolio orientation", out)
        self.assertIn("HERMES MEMORY ADAPTER (mandatory, provider-agnostic)", out)
        self.assertIn("configured memory provider", out)
        self.assertIn("Honcho tools are one implementation, not a requirement", out)
        self.assertIn("session_search", out)
        self.assertIn("HERMES HARD GATE", out)
        self.assertIn("lint agenda as evidence", out)
        self.assertIn("never a menu", out)
        self.assertIn("persona writeback, steers, synthesis, and traceable inscription", out)
        self.assertIn("advice alone is not completion", out)
        self.assertIn("Do not stop and ask them to say continue", out)
        self.assertIn("Do not force a closing question", out)
        self.assertIn("never invent a writeback or inscription", out)


class HermesProvisionTest(unittest.TestCase):
    def test_configure_group_seeds_once_and_preserves_blank_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertTrue(_hermes_provision.configure_hermes_group(root, "hive"))
            self.assertIn("edge_group: hive", (root / "config.yaml").read_text())
            (root / "config.yaml").write_text("edge_group:\nother: kept\n")
            self.assertFalse(_hermes_provision.configure_hermes_group(root, "other-hive"))
            self.assertEqual((root / "config.yaml").read_text(), "edge_group:\nother: kept\n")

    def test_reconcile_installs_only_enabled_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "skills" / "wake").mkdir(parents=True)
            (repo / "skills" / "wake" / "SKILL.md").write_text("---\nname: wake\n---\nx")
            (root / "config.yaml").write_text("edge_group: hive\n")
            off = root / "profiles" / "off"
            off.mkdir(parents=True)
            (off / "config.yaml").write_text("edge_group: null\n")
            # null is origin-only, therefore still enabled.
            result = _hermes_provision.reconcile_hermes_profiles(
                {"skill_prefix": "ed", "tool_prefix": "edge"}, repo, root / "edge", root)
            self.assertIn("hermes skills", result["default"][0])
            self.assertIn("hermes skills", result["off"][0])

    def test_startup_plugin_is_installable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = _hermes_provision.install_hermes_plugin({}, root / "repo", root / "edge", root)
            self.assertTrue((plugin / "plugin.yaml").is_file())
            compile((plugin / "__init__.py").read_text(), str(plugin / "__init__.py"), "exec")

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
            hermes_home.mkdir()
            (hermes_home / "config.yaml").write_text("edge_group: ''\n")
            cfg = {"skill_prefix": "Steve", "tool_prefix": "edge"}
            legacy = hermes_home / "skills" / "edge-wake"
            legacy.mkdir(parents=True)
            installed_skill = edge_home / "skills" / "wake" / "SKILL.md"
            installed_skill.parent.mkdir(parents=True)
            installed_skill.write_text("canonical installed copy")
            (legacy / "SKILL.md").write_text(_hermes_provision.render_hermes_skill(
                "wake", "edge", installed_skill))
            foreign = hermes_home / "skills" / "edge-foreign"
            foreign.mkdir(parents=True)
            (foreign / "SKILL.md").write_text("third-party skill")
            _hermes_provision.provision_hermes(cfg, repo, edge_home, hermes_home)
            _hermes_provision.reconcile_hermes_profiles(cfg, repo, edge_home, hermes_home)
            self.assertTrue(
                (hermes_home / "skills" / "Steve-wake" / "SKILL.md").is_file())
            self.assertFalse((hermes_home / "skills" / "edge-wake").exists())
            self.assertTrue(foreign.exists())
            # _shared não vira wrapper
            self.assertFalse((hermes_home / "skills" / "Steve-_shared").exists())


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
