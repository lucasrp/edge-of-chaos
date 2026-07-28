"""Sources exist without secrets — auth is a property of a source, never its existence
condition. detect_cli_sources finds the keyless ones (gh CLI auth, rclone remotes) as machine
facts for the interview; the mentor proposes, the mentee authorizes, and emit_phenotype(sources=)
is where the authorized roster lands in agent.yaml. Runner injected; nothing touches this host.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


class _Res:
    def __init__(self, rc=0, stdout=""):
        self.returncode = rc
        self.stdout = stdout


class DetectCliSources(unittest.TestCase):
    def test_finds_gh_auth_and_rclone_remotes(self):
        def run(cmd, **kw):
            if cmd[:2] == ["gh", "auth"]:
                return _Res(0)
            if cmd[:2] == ["rclone", "listremotes"]:
                return _Res(0, "gdrive:\nbackup:\n")
            raise AssertionError(f"unexpected {cmd}")
        found = onboarding.detect_cli_sources(run=run)
        names = {s["name"] for s in found}
        self.assertIn("github", names)
        self.assertIn("rclone:gdrive", names)
        self.assertIn("rclone:backup", names)
        gh = next(s for s in found if s["name"] == "github")
        self.assertEqual(gh["kind"], "cli")

    def test_missing_binaries_yield_empty(self):
        def run(cmd, **kw):
            raise FileNotFoundError(cmd[0])
        self.assertEqual(onboarding.detect_cli_sources(run=run), [])

    def test_unauthenticated_gh_is_not_a_source(self):
        def run(cmd, **kw):
            return _Res(1)
        self.assertEqual(onboarding.detect_cli_sources(run=run), [])


class EmitPersistsMentorSources(unittest.TestCase):
    """The mentor-authorized roster (a local folder has no key and no detector — only the
    conversation can declare it) reaches agent.yaml at finish, alongside the secrets-derived."""

    def test_emit_writes_authorized_sources_into_agent_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="t", backfill_days=3, provision_skills=False)
            path = onboarding.emit_phenotype(tmp, sources=[
                {"name": "notas", "kind": "path", "path": "~/notas",
                 "description": "Pasta local de notas (Mundo + Atividade)."},
            ])
            cfg = yaml.safe_load(Path(path).read_text())
            names = {s["name"] for s in cfg.get("sources") or []}
            self.assertIn("notas", names)


if __name__ == "__main__":
    unittest.main()
