"""A32 — map state describes work; it never authorizes the beat dispatcher.

Pós-ADR-0024: o producer do plano é a `forma` da pauta.proposta (o dente) — o plano é
leitura pura do eventlog (pauta.*) + superfície estática. Mapas/tickets/frontier no MESMO
log continuam sem poder alterar decision/tools/permissions.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import _beat  # noqa: E402
import cortex_config  # noqa: E402
import eventlog  # noqa: E402
import pauta  # noqa: E402

CMD = ["/opt/claude", "-p", "-", "--dangerously-skip-permissions",
       "--mcp-config", "/tmp/cortex.json"]


def _passa_tudo(prompt):
    return '{"reprova": [], "veredito": "passa", "evidencia": "ok"}'


def _pen_proposta(log, dispatch_id="dispatch-fixed", forma="report"):
    # r3 (adv r2 #1): a via Voz exige dispatch.open comandado no log; estes testes
    # não testam autoridade — a estrada autônoma pena a proposta offline.
    return pauta.propose({"objeto": "mundo", "abordagem": "fog"},
                         [{"tema": "T", "forma": forma, "lastro": "lido: x"}],
                         dispatch_id=dispatch_id, completer=_passa_tudo, log=log)


class DispatchNonInterference(unittest.TestCase):
    def test_map_only_mutations_cannot_change_decision_tools_or_permissions_a32(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events.jsonl"
            _pen_proposta(log)

            def plan():
                return _beat.dispatch_plan("lead", "dispatch-fixed",
                                           runtime_command=CMD, log=log)

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

    def test_dispatch_surface_uses_real_command_and_subject_allowlist(self):
        surface = cortex_config.dispatch_surface(subject="lead", runtime_command=CMD)
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

    def test_dispatch_plan_cli_is_the_dente(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            args = [sys.executable, str(REPO / "tools" / "_beat.py"), "dispatch-plan",
                    "--home", str(home), "--subject", "lead", "--dispatch-id", "cli-fixed",
                    "--claude-bin", "/opt/claude", "--mcp-config", "/tmp/cortex.json"]
            # sem pauta.proposta viva o comando FALHA — Ato-2 não abre (ADR-0024)
            sem = subprocess.run(args, capture_output=True, text=True)
            self.assertNotEqual(sem.returncode, 0)
            self.assertIn("pauta.proposta", sem.stderr)
            # com proposta, o producer é a forma
            log = home / "state" / "events" / "log.jsonl"
            log.parent.mkdir(parents=True)
            _pen_proposta(log, dispatch_id="cli-fixed", forma="map")
            out = subprocess.run(args, capture_output=True, text=True, check=True)
            result = json.loads(out.stdout)
            self.assertEqual(result["decision"]["producer"], "map")
            self.assertEqual(result["decision"]["dispatch_id"], "cli-fixed")

    def test_edge_heartbeat_injects_pending_plan_and_gate_reads_the_pauta(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            skill_dir = home / "skills" / "beat"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("---\nname: beat\n---\nFAKE-BEAT")
            (home / "agent.yaml").write_text(
                'name: test\nvoice: "fixed voice"\nmission: "fixed contract"\n')
            fake = home / "fake-claude"
            capture = home / "capture.json"
            # O fake-beat joga o contrato NOVO: plano pré-lançamento vem pendente; o
            # trunk pena a proposta (aqui via Voz, offline) e publica na forma dela.
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                f"sys.path.insert(0, {str(REPO / 'tools')!r})\n"
                "import eventlog, pauta\n"
                "prompt = sys.stdin.read()\n"
                "plan = json.loads(os.environ['EDGE_DISPATCH_PLAN'])\n"
                "Path(os.environ['CAPTURE']).write_text(json.dumps({"
                "'prompt': prompt, 'plan': os.environ.get('EDGE_DISPATCH_PLAN')}))\n"
                "home = Path(os.environ['EDGE_TEST_HOME'])\n"
                "log = home/'state/events/log.jsonl'\n"
                "did = os.environ['EDGE_DISPATCH_PLAN_ID']\n"
                # r3: o fake-beat joga a estrada AUTÔNOMA (voz num dispatch de
                # heartbeat é autoridade forjada e agora LEVANTA — adv r2 #1)
                "def ok(p):\n"
                "    return json.dumps({'reprova': [], 'veredito': 'passa',"
                " 'evidencia': 'ok'})\n"
                "pauta.propose({'objeto': 'mundo', 'abordagem': 'fog'},"
                " [{'tema': 'T', 'forma': 'report', 'lastro': 'lido: x'}],"
                " dispatch_id=did, completer=ok, log=log)\n"
                # §3 "o nome carrega o setup": o slug publica com o prefixo da célula
                # — o post-gate agora verifica mecanicamente (round2, adv r1 #10).
                "eventlog.publish_artefato_atomic('fog-mundo--fake-beat', 'why', "
                "skill='report', _rite_authorized=True, log=log)\n"
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
            self.assertIsNone(plan["decision"]["producer"])  # pendente até a Pauta
            self.assertIn("pendente", plan["decision"]["pauta"])
            self.assertIn("AUTHORITATIVE DISPATCH PLAN", captured["prompt"])

    def test_post_gate_rejects_an_artifact_from_a_non_authorized_producer(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _pen_proposta(log, dispatch_id="d1", forma="report")
            eventlog.publish_artefato_atomic(
                "wrong-producer", "why", skill="map", _rite_authorized=True, log=log)
            gaps = _beat.assert_beat_produced(log, before_count=0, dispatch_id="d1")
            self.assertTrue(any("producer" in gap and "report" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
