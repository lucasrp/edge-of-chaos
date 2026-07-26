"""edge-apply must make stage-(i) validation AUTHORITATIVE.

The Codex gate finding: after provisioning, edge-apply called `validate_install` WITHOUT the applied
`args.yaml` (so identity validated the checkout-default agent.yaml, not the applied config), stored
`_healthy`, and exited 0 UNCONDITIONALLY — a fresh install "finished successfully" even when identity
validation FAILED. The `--validate` path had the same missing agent_yaml arg.

This guards the fix on the `--validate` path (offline — no venv/docker provisioned):
  • a THIN applied agent.yaml (no declared sources → briefing fail-closed) makes the IDENTITY check
    FAIL, and edge-apply exits NONZERO (today it would read the checkout default and pass);
  • a COMPLETE applied agent.yaml plus target-home doctrine keeps identity OK;
  • the otherwise empty substrate remains unhealthy and exits nonzero.

Invoked via subprocess (the test_beat_launch.py pattern). `--home` defaults to the real edge_home
(genuinely healthy substrate); only `--claude-home` is pointed at a tmp dir so the run never touches
the real ~/.claude. The applied agent.yaml is the only variable — proving identity now validates the
APPLIED config, not the checkout default.
"""
import subprocess
import sys
import os
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPLY = REPO / "tools" / "edge-apply"

# A THIN applied config: declares no sources → briefing source_roster is fail-closed → identity FAIL.
THIN_YAML = "name: probe\n"

# A COMPLETE applied config: name/mission/voice (tattoos) + a declared source (roster) → identity OK.
COMPLETE_YAML = """\
name: probe
codename: probe
mission: "probe mission line."
voice: "probe voice, direct."
sources:
  - name: hn
    kind: api
    description: "Hacker News front page — the world's pulse."
"""


def _run_validate(yaml_text):
    """Run read-only validation against a synthetic target with minimal doctrine."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        memory = home / "memory"
        state = home / "state"
        memory.mkdir()
        state.mkdir()
        (memory / "personality.md").write_text("# Personality — probe" + chr(10) * 2 + "Analytical.")
        (memory / "method.md").write_text("# Feynman Method" + chr(10) * 2 + "Derive first.")
        (memory / "canone.md").write_text("# O cânone" + chr(10) * 2 + "Evidence before claims.")
        (state / "idiom.md").write_text("# Idiom" + chr(10) * 2 + "**beat** — work cycle.")
        y = home / "agent.yaml"
        y.write_text(yaml_text)
        env = {k: v for k, v in os.environ.items() if k != "HERMES_HOME"}
        return subprocess.run(
            [sys.executable, str(APPLY), "--yaml", str(y), "--home", str(home), "--validate"],
            capture_output=True, text=True, env=env,
        )


class ValidateIsAuthoritativeOverAppliedConfig(unittest.TestCase):
    def test_thin_applied_yaml_fails_identity_and_exits_nonzero(self):
        res = _run_validate(THIN_YAML)
        # Identity validated the APPLIED thin config (not the checkout default) → it FAILS.
        self.assertIn("[XX] identity:", res.stdout, res.stdout + res.stderr)
        self.assertIn("INSTALL INCOMPLETE", res.stdout)
        # AUTHORITATIVE: an unhealthy report exits NONZERO.
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_complete_applied_yaml_passes_identity_on_target_home(self):
        res = _run_validate(COMPLETE_YAML)
        self.assertIn("[OK] identity:", res.stdout, res.stdout + res.stderr)
        self.assertIn("INSTALL INCOMPLETE", res.stdout)
        self.assertNotEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
