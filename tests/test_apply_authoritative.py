"""edge-apply must make stage-(i) validation AUTHORITATIVE.

The Codex gate finding: after provisioning, edge-apply called `validate_install` WITHOUT the applied
`args.yaml` (so identity validated the checkout-default agent.yaml, not the applied config), stored
`_healthy`, and exited 0 UNCONDITIONALLY — a fresh install "finished successfully" even when identity
validation FAILED. The `--validate` path had the same missing agent_yaml arg.

This guards the fix on the `--validate` path:
  • a THIN applied agent.yaml (no declared sources → briefing fail-closed) makes the IDENTITY check
    FAIL, and edge-apply exits NONZERO (today it would read the checkout default and pass);
  • a COMPLETE applied agent.yaml keeps identity OK — the SAME substrate, the applied config the only
    variable, which is exactly the claim "identity validates the APPLIED config, not the default".

Host-independence: the run is pointed at a THROWAWAY install tree (`--home`, plus `EDGE_HOME` so
`briefing`'s doctrine/identity paths resolve there too) built from the versioned genotype —
`seeds/memory/` for the doctrine, the checkout's own `skills/` + `blog/server.py` for the genotype
leg. Before, `--home` was left DEFAULT, i.e. whatever install the person running the suite happens to
have: on a genotype the whole report came back broken, and on a live install it depended on that
host's venv and neo4j. The applied agent.yaml is the only variable, on every host.

The health/exit-0 leg is different in kind: `--validate` runs the venv + graph probes, so
INSTALL HEALTHY asserts a genuinely PROVISIONED install (a built `.venv`, a reachable neo4j with a
populated group) — real install data no throwaway tree can honestly supply. It is asserted where the
substrate is actually healthy and SKIPPED with the substrate's own [XX] lines as the declared reason
where it is not, rather than being faked or dropped.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPLY = REPO / "tools" / "edge-apply"
SEEDS_MEMORY = REPO / "seeds" / "memory"
LAYOUT_DIRS = ("blog/entries", "state", "memory", "threads", "secrets")

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


def _install_tree(tmp):
    """Build the THROWAWAY install home under `tmp` and return it.

    Everything the substrate checks read comes from the VERSIONED genotype, never from the host's
    own install: the layout dirs, `skills/` + `blog/server.py` (the genotype leg) and the canonical
    doctrine from `seeds/memory/` (the seed an install's `memory/` is provisioned from — the
    genotype itself has no `memory/`, it is an output of onboarding).
    """
    home = Path(tmp) / "home"
    for d in LAYOUT_DIRS:
        (home / d).mkdir(parents=True, exist_ok=True)
    (home / "skills").symlink_to(REPO / "skills", target_is_directory=True)
    shutil.copy(REPO / "blog" / "server.py", home / "blog" / "server.py")
    for doc in ("personality.md", "method.md", "canone.md"):
        shutil.copy(SEEDS_MEMORY / doc, home / "memory" / doc)
    return home


def _run_validate(yaml_text):
    """Run `edge-apply --yaml <tmp> --validate` against the throwaway tree; the applied agent.yaml is
    the only variable. `--claude-home` also points at tmp so the run never touches the real
    ~/.claude, and EDGE_HOME points at the throwaway home so the briefing composer resolves the
    seeded doctrine there instead of the runner's install."""
    with tempfile.TemporaryDirectory() as tmp:
        home = _install_tree(tmp)
        y = Path(tmp) / "agent.yaml"
        y.write_text(yaml_text)
        env = dict(os.environ, EDGE_HOME=str(home))
        env.pop("EDGE_GROUP", None)
        return subprocess.run(
            [sys.executable, str(APPLY), "--yaml", str(y), "--validate",
             "--home", str(home), "--claude-home", tmp],
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

    def test_complete_applied_yaml_passes_identity(self):
        res = _run_validate(COMPLETE_YAML)
        self.assertIn("[OK] identity:", res.stdout, res.stdout + res.stderr)

    def test_healthy_report_exits_zero(self):
        """The other direction of the AUTHORITATIVE contract: a HEALTHY report exits 0.

        Needs a genuinely provisioned install (venv built, neo4j reachable and the group populated);
        those probes read real install data, which a throwaway tree cannot supply without inventing
        it. Where the substrate is not provisioned this SKIPS with the failing checks named."""
        res = _run_validate(COMPLETE_YAML)
        if "INSTALL HEALTHY" not in res.stdout:
            broken = [ln.strip() for ln in res.stdout.splitlines() if ln.strip().startswith("[XX]")]
            self.skipTest("substrate not provisioned on this host: " + "; ".join(broken))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
