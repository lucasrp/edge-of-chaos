"""A32 — map state describes work; it never authorizes the beat dispatcher."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import _beat  # noqa: E402
import cortex_config  # noqa: E402
import eventlog  # noqa: E402


class DispatchNonInterference(unittest.TestCase):
    def test_map_only_mutations_cannot_change_decision_tools_or_permissions_a32(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "events.jsonl"
            cursor = root / "cursor.json"
            voz = {"live": "mentor skeptical"}
            session = {"id": "session-fixed", "request": "continue"}
            contract = {"read_only_world": True, "budget": 3}

            def plan():
                with mock.patch.object(
                        eventlog, "read", side_effect=AssertionError("dispatch read portfolio")):
                    return _beat.dispatch_plan(
                        voz, session, contract, "lead", "dispatch-fixed",
                        roster=["report", "map", "plan"], state_path=cursor,
                        runtime_command=["/opt/claude", "-p", "-",
                                         "--dangerously-skip-permissions",
                                         "--mcp-config", "/tmp/cortex.json"],
                    )

            outputs = [plan()]
            opened_map = eventlog.open_map(
                operacao="edge", titulo="Mapa", rationale="Describe only",
                dispatch_id="map-open", author="grill", log=log,
            )
            outputs.append(plan())
            map_ref = f"edge/{opened_map['payload']['num']}"
            ticket = eventlog.open_ticket(
                map=map_ref, titulo="Ticket", question="Q?", rationale="Describe only",
                dispatch_id="ticket-open", author="grill", log=log,
            )
            outputs.append(plan())
            eventlog.set_map_state(
                ref=map_ref, estado="pausado", rationale="Pause description",
                dispatch_id="map-pause", author="grill", log=log,
            )
            outputs.append(plan())
            eventlog.set_map_state(
                ref=map_ref, estado="ativado", rationale="Resume description",
                dispatch_id="map-resume", author="grill", log=log,
            )
            eventlog.append(
                "ticket.closed", f"ticket:{ticket['payload']['ulid']}",
                {"ref": ticket["payload"]["ulid"], "resolucao": "Closed",
                 "valencia": "supports",
                 "bears_on": [{"alvo": "evidence", "valencia": "supports"}],
                 "rationale": "Move frontier", "tier": "asserted", "author": "grill",
                 "dispatch_id": "ticket-close"},
                log=log,
            )
            outputs.append(plan())

            canonical = json.dumps(outputs[0], sort_keys=True, separators=(",", ":"))
            self.assertTrue(all(
                json.dumps(output, sort_keys=True, separators=(",", ":")) == canonical
                for output in outputs[1:]
            ))
            self.assertEqual(outputs[0]["decision"]["producer"], "report")
            self.assertEqual(set(outputs[0]), {"decision", "tools", "permissions"})
            rotation = json.loads(cursor.read_text())
            self.assertEqual(rotation["next"], 1, "retry must not spend a second rotation slot")
            self.assertEqual(list(rotation["plans"]), ["dispatch-fixed"])

    def test_dispatch_surface_uses_real_command_and_subject_allowlist(self):
        surface = cortex_config.dispatch_surface(
            subject="lead",
            runtime_command=["/opt/claude", "-p", "-", "--dangerously-skip-permissions",
                             "--mcp-config", "/tmp/cortex.json"])
        self.assertNotIn("command", surface["tools"])
        self.assertEqual(surface["tools"]["runtime"], "claude-code")
        self.assertEqual(surface["tools"]["cortex"], ["mcp__cortex__*"])
        self.assertEqual(surface["permissions"]["mode"], "dangerously-skip-permissions")
        self.assertEqual(surface["permissions"]["runtime_scope"], "all")

    def test_real_beat_skill_invokes_dispatch_plan_cli(self):
        skill = (REPO / "skills" / "beat" / "SKILL.md").read_text()
        self.assertIn("EDGE_DISPATCH_PLAN", skill)
        self.assertLess(skill.index("EDGE_DISPATCH_PLAN"), skill.index("Grounding INICIAL"))
        self.assertIn("mapa descreve", skill.lower())

    def test_dispatch_plan_cli_executes_the_same_live_seam(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([
                sys.executable, str(REPO / "tools" / "_beat.py"), "dispatch-plan",
                "--home", tmp, "--subject", "lead", "--dispatch-id", "cli-fixed",
                "--claude-bin", "/opt/claude", "--mcp-config", "/tmp/cortex.json",
            ], capture_output=True, text=True, check=True)
            result = json.loads(out.stdout)
            self.assertEqual(result["decision"]["producer"], "report")
            self.assertEqual(result["decision"]["dispatch_id"], "cli-fixed")

    def test_edge_heartbeat_injects_authoritative_plan_before_fake_claude_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / "skills" / "beat"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: beat\n---\nFAKE-BEAT")
            (home / "agent.yaml").write_text(
                'name: test\nvoice: "fixed voice"\nmission: "fixed contract"\n')
            fake = home / "fake-claude"
            capture = home / "capture.json"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                f"sys.path.insert(0, {str(REPO / 'tools')!r})\n"
                "import eventlog\n"
                "prompt = sys.stdin.read()\n"
                "plan = json.loads(os.environ['EDGE_DISPATCH_PLAN'])\n"
                "Path(os.environ['CAPTURE']).write_text(json.dumps({"
                "'prompt': prompt, 'plan': os.environ.get('EDGE_DISPATCH_PLAN')}))\n"
                "home = Path(os.environ['EDGE_TEST_HOME'])\n"
                "eventlog.publish_artefato_atomic('fake-beat', 'why', "
                "skill=plan['decision']['producer'], _rite_authorized=True, "
                "log=home/'state/events/log.jsonl')\n"
            )
            fake.chmod(0o755)
            env = dict(os.environ)
            env.update({"EDGE_CLAUDE_BIN": str(fake), "CAPTURE": str(capture),
                        "EDGE_TEST_HOME": str(home)})
            heartbeat = subprocess.run([
                sys.executable, str(REPO / "tools" / "edge-heartbeat"),
                "--home", str(home), "--group", "test-group",
                "--dispatch-id", "heartbeat-fixed",
            ], capture_output=True, text=True, env=env)
            self.assertEqual(heartbeat.returncode, 0, heartbeat.stderr)
            captured = json.loads(capture.read_text())
            plan = json.loads(captured["plan"])
            self.assertEqual(plan["decision"]["dispatch_id"], "heartbeat-fixed")
            self.assertEqual(plan["decision"]["producer"], "report")
            self.assertIn("AUTHORITATIVE DISPATCH PLAN", captured["prompt"])
            self.assertIn('"producer": "report"', captured["prompt"])

    def test_post_gate_rejects_an_artifact_from_a_non_authorized_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato_atomic(
                "wrong-producer", "why", skill="map", _rite_authorized=True, log=log)
            gaps = _beat.assert_beat_produced(
                log, before_count=0, expected_producer="report")
            self.assertTrue(any("producer" in gap and "report" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
