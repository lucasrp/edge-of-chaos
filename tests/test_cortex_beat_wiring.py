"""Beat wiring (Slice 6) — the lead beat (and the self-reading fan it dispatches) DISCOVER the standing
`cortex` MCP via --mcp-config on the parent claude -p (REQUISITES F1, R6 beat-wiring). The world-reading
delta subagent is denied via its skill disallowed-tools (Slice 4); here the LEAD path is wired so the
door is actually pullable mid-turn — the user-visible capability, not just a unit-tested server.

A genotype/template path: the lead config is generated per-install (group from agent.yaml/_identity at
runtime, subject=lead), so it deploys to the fleet without baking an identity literal.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import _beat  # noqa: E402


class BuildBeatCommandRegistersTheCortexDoor(unittest.TestCase):
    """build_beat_command gains an optional --mcp-config: with a config path, the lead beat is launched
    with the cortex server registered so it (and its Task-fanned self-reading subagents) can pull
    cortex_*. WITHOUT a path the base single-shot command is unchanged (backward-compatible)."""

    def test_base_command_unchanged_without_a_config(self):
        cmd = _beat.build_beat_command("/opt/claude")
        self.assertEqual(cmd, ["/opt/claude", "-p", "-", "--dangerously-skip-permissions"])

    def test_command_registers_the_mcp_config_when_given(self):
        cmd = _beat.build_beat_command("/opt/claude", mcp_config_path="/x/cortex.mcp.json")
        self.assertIn("--mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--mcp-config") + 1], "/x/cortex.mcp.json")
        # the base invocation is preserved
        self.assertEqual(cmd[:4], ["/opt/claude", "-p", "-", "--dangerously-skip-permissions"])


class EnsureCortexConfigGeneratesTheLeadConfig(unittest.TestCase):
    """The genotype path: the launcher generates the LEAD config per-install (subject=lead, group from
    identity) into a per-install state path, idempotently — so the door deploys to the fleet."""

    def test_ensure_writes_a_lead_scoped_cortex_config(self):
        with tempfile.TemporaryDirectory() as home:
            path = _beat.ensure_cortex_config(home, group="edge-test")
            self.assertTrue(Path(path).is_file())
            cfg = json.loads(Path(path).read_text())
            self.assertIn("cortex", cfg["mcpServers"])
            srv = cfg["mcpServers"]["cortex"]
            self.assertEqual(srv["args"], ["tools/cortex_mcp.py"])
            self.assertEqual(srv["env"]["EDGE_GROUP"], "edge-test")
            # the lead is the granted subject — the server env bakes it for the server-side guard
            self.assertEqual(srv["env"]["EDGE_CORTEX_SUBJECT"], "lead")

    def test_ensure_is_idempotent(self):
        with tempfile.TemporaryDirectory() as home:
            p1 = _beat.ensure_cortex_config(home, group="g")
            p2 = _beat.ensure_cortex_config(home, group="g")
            self.assertEqual(p1, p2)

    def test_config_path_is_under_the_install_state_not_committed(self):
        # the generated config is a runtime artifact under state/ (gitignored alongside usage), never
        # a tracked genotype file — it derives from identity at run, per install.
        with tempfile.TemporaryDirectory() as home:
            path = _beat.ensure_cortex_config(home, group="g")
            self.assertIn("state", str(path))


class TheHeartbeatLaunchesWithTheDoor(unittest.TestCase):
    """The live launch path wires it end-to-end: edge-heartbeat --dry-run shows the cortex door
    registered on the lead command (the user-visible capability)."""

    def test_dry_run_shows_the_mcp_config_on_the_command(self):
        import subprocess
        HEARTBEAT = REPO / "tools" / "edge-heartbeat"
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "skills" / "beat").mkdir(parents=True)
            (home / "skills" / "beat" / "SKILL.md").write_text(
                "---\nname: beat\n---\nRUN-THE-BEAT-MARKER\n")
            res = subprocess.run(
                [sys.executable, str(HEARTBEAT), "--home", str(home), "--dry-run",
                 "--group", "edge-test"],
                capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("--mcp-config", res.stdout,
                          "the lead beat must launch with the cortex door registered (F1)")


if __name__ == "__main__":
    unittest.main()
