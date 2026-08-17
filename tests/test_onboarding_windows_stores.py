"""Onboarding under WSL: the mentee's CLI sessions may live on the Windows side (native Claude
Code/Codex/Grok write to C:\\Users\\<user>\\..., seen from WSL as /mnt/c/Users/<user>/...). The
onboarding detects those stores and proposes pointing at them — apps/cloud are server-side and not
detectable from disk. Scan root is injected; nothing depends on a real WSL host.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


class DetectWindowsStores(unittest.TestCase):
    def test_finds_windows_claude_store_under_mnt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = root / "c" / "Users" / "bob" / ".claude" / "projects"
            store.mkdir(parents=True)
            found = onboarding.detect_windows_session_stores(mnt_root=root)
            self.assertEqual(found.get("claude"), store,
                             "must surface the Windows Claude store so onboarding can point at it")

    def test_empty_when_no_mnt(self):
        self.assertEqual(onboarding.detect_windows_session_stores(mnt_root="/no-such-mnt-xyz"), {})


class EmitPersistsProjectDir(unittest.TestCase):
    """The confirmed Windows store (proposed by the onboarding under WSL) is written into agent.yaml
    `project_dir`, so project_dir() reads it durably — the phenotype carries the pointer."""

    def test_emit_writes_project_dir_into_agent_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3, provision_skills=False)
            path = onboarding.emit_phenotype(tmp, project_dir="/mnt/c/Users/bob/.claude/projects")
            cfg = yaml.safe_load(Path(path).read_text())
            self.assertEqual(cfg["project_dir"], "/mnt/c/Users/bob/.claude/projects")

    def test_emit_writes_confirmed_windows_surface_homes(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3,
                                     provision_skills=False)
            path = onboarding.emit_phenotype(
                tmp,
                surface_homes={
                    "codex": "/mnt/c/Users/bob/.codex",
                    "grok": "/mnt/c/Users/bob/.grok",
                },
            )
            cfg = yaml.safe_load(Path(path).read_text())
            self.assertEqual(cfg["surfaces"]["codex"]["home"], "/mnt/c/Users/bob/.codex")
            self.assertEqual(cfg["surfaces"]["grok"]["home"], "/mnt/c/Users/bob/.grok")
            self.assertTrue(cfg["surfaces"]["codex"]["enabled"])
            self.assertTrue(cfg["surfaces"]["grok"]["enabled"])


if __name__ == "__main__":
    unittest.main()
