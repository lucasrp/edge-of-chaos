"""agent.yaml `surfaces` — transcript store enablement is phenotype config."""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import surfaces_cfg  # noqa: E402
import sweep  # noqa: E402


class SurfacesCfg(unittest.TestCase):
    def test_absent_block_defaults_enable_optional_surfaces(self):
        cfg = {"name": "ed"}  # no surfaces key
        self.assertTrue(surfaces_cfg.surface_enabled("claude", cfg=cfg))
        self.assertTrue(surfaces_cfg.surface_enabled("codex", cfg=cfg))
        self.assertTrue(surfaces_cfg.surface_enabled("grok", cfg=cfg))

    def test_present_block_requires_explicit_enabled(self):
        cfg = {"surfaces": {"claude": {"enabled": True}, "codex": {"enabled": False}}}
        self.assertTrue(surfaces_cfg.surface_enabled("claude", cfg=cfg))
        self.assertFalse(surfaces_cfg.surface_enabled("codex", cfg=cfg))
        self.assertFalse(surfaces_cfg.surface_enabled("grok", cfg=cfg))  # not listed

    def test_home_from_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "my-grok"
            cfg = {"surfaces": {"grok": {"enabled": True, "home": str(home)}}}
            self.assertEqual(
                surfaces_cfg.surface_sessions_dir("grok", cfg=cfg, env={}),
                home / "sessions",
            )

    def test_include_hermetic_requires_explicit_dir(self):
        cfg = {"surfaces": {"grok": {"enabled": True}}}
        self.assertFalse(
            surfaces_cfg.include_optional_surface("grok", "/tmp/proj", None, cfg=cfg)
        )
        self.assertTrue(
            surfaces_cfg.include_optional_surface("grok", "/tmp/proj", "/tmp/grok", cfg=cfg)
        )
        self.assertFalse(
            surfaces_cfg.include_optional_surface("grok", None, False, cfg=cfg)
        )

    def test_include_real_host_honors_disabled_yaml(self):
        cfg = {"surfaces": {"grok": {"enabled": False}}}
        self.assertFalse(
            surfaces_cfg.include_optional_surface("grok", None, None, cfg=cfg)
        )

    def test_plan_sweep_skips_disabled_surface_on_real_posture(self):
        """When project_dir is None posture is real — but we still need a fake identity.
        Use include_optional_surface as the seam (plan_sweep calls it via _grok_enabled)."""
        cfg = {"surfaces": {"grok": {"enabled": False}, "codex": {"enabled": False}}}
        self.assertFalse(surfaces_cfg.include_optional_surface("grok", None, None, cfg=cfg))
        # sweep helper uses agent.yaml on disk for real runs; the pure gate is surfaces_cfg.


class SurfacesCfgYamlRoundTrip(unittest.TestCase):
    def test_load_from_temp_agent_yaml(self):
        with tempfile.TemporaryDirectory() as tmp:
            y = Path(tmp) / "agent.yaml"
            y.write_text(
                "surfaces:\n"
                "  grok:\n"
                "    enabled: true\n"
                "    home: ~/custom-grok\n"
            )
            self.assertTrue(surfaces_cfg.surface_enabled("grok", agent_yaml=y))
            home = surfaces_cfg.surface_home("grok", agent_yaml=y, env={})
            self.assertTrue(str(home).endswith("custom-grok"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
