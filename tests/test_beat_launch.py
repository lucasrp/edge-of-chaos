"""The autonomous beat launcher — a single-shot `claude -p -` fed the /ed-beat skill body.

The beat runs entirely inside Claude Code (ADR-0003): the launcher does no cognition. It
resolves the claude binary, loads the beat skill's prompt (home wins over repo), and pipes it
into one `claude -p -` invocation — no envelope, no retry. Cognition lives in the skill.
"""
import json
import importlib.machinery
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HEARTBEAT = REPO / "tools" / "edge-heartbeat"
sys.path.insert(0, str(REPO / "tools"))
import _beat  # noqa: E402
import eventlog  # noqa: E402


def _heartbeat_module(name="edge_heartbeat_process_test"):
    return importlib.machinery.SourceFileLoader(name, str(HEARTBEAT)).load_module()


def _skill_home(tmp: str, body: str) -> Path:
    home = Path(tmp)
    d = home / "skills" / "beat"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: beat\n---\n{body}")
    return home


class BeatCommandIsSingleShotClaudeP(unittest.TestCase):
    """One beat = one `claude -p -` invocation, permissions bypassed, no retry flags."""

    def test_command_shape(self):
        cmd = _beat.build_beat_command("/opt/claude")
        self.assertEqual(cmd, ["/opt/claude", "-p", "-", "--dangerously-skip-permissions"])

    def test_model_flag_for_opus_or_fable(self):
        # Operator mix: claude CLI hosts both Anthropic aliases (opus / fable).
        cmd = _beat.build_beat_command("/opt/claude", model="opus")
        self.assertEqual(
            cmd,
            ["/opt/claude", "-p", "-", "--dangerously-skip-permissions", "--model", "opus"],
        )
        cmd_f = _beat.build_beat_command("/opt/claude", model="fable",
                                         mcp_config_path="/x/cortex.mcp.json")
        self.assertEqual(
            cmd_f,
            ["/opt/claude", "-p", "-", "--dangerously-skip-permissions",
             "--mcp-config", "/x/cortex.mcp.json", "--model", "fable"],
        )


class HeartbeatProcessTreeIsFailClosed(unittest.TestCase):
    def test_keyboard_interrupt_kills_descendant_before_propagating(self):
        mod = _heartbeat_module("edge_heartbeat_interrupt_process_test")
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late-child-write"
            child = (
                "import pathlib,sys,time; "
                "time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('survived')"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
                "time.sleep(10)"
            )

            with self.assertRaises(KeyboardInterrupt):
                mod._run_runtime(
                    [sys.executable, "-c", parent, child, str(marker)],
                    cwd=Path(tmp),
                    runtime_env=None,
                    prompt="",
                    use_stdin=False,
                    timeout_seconds=5,
                    terminal_failure_check=lambda: (_ for _ in ()).throw(
                        KeyboardInterrupt()
                    ),
                )
            time.sleep(1.0)
            self.assertFalse(marker.exists(), "a descendant survived KeyboardInterrupt")

    def test_timeout_kills_descendant_before_returning(self):
        mod = _heartbeat_module()
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late-child-write"
            child = (
                "import pathlib,sys,time; "
                "time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('survived')"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
                "time.sleep(10)"
            )
            with self.assertRaises(subprocess.TimeoutExpired):
                mod._run_runtime(
                    [sys.executable, "-c", parent, child, str(marker)],
                    cwd=Path(tmp),
                    runtime_env=None,
                    prompt="",
                    use_stdin=False,
                    timeout_seconds=0.2,
                )
            time.sleep(1.0)
            self.assertFalse(marker.exists(), "a descendant survived the heartbeat timeout")

    def test_terminal_rite_failure_kills_descendant_before_returning(self):
        mod = _heartbeat_module("edge_heartbeat_terminal_process_test")
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "late-child-write"
            child = (
                "import pathlib,sys,time; "
                "time.sleep(0.8); pathlib.Path(sys.argv[1]).write_text('survived')"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
                "time.sleep(10)"
            )
            checks = iter([None, "terminal rite failure: run:final_review_acceptance"])

            with self.assertRaisesRegex(mod.RuntimeRiteTerminal, "final_review_acceptance"):
                mod._run_runtime(
                    [sys.executable, "-c", parent, child, str(marker)],
                    cwd=Path(tmp),
                    runtime_env=None,
                    prompt="",
                    use_stdin=False,
                    timeout_seconds=5,
                    terminal_failure_check=lambda: next(checks, "terminal"),
                )
            time.sleep(1.0)
            self.assertFalse(marker.exists(), "a descendant survived terminal rite failure")

    def test_only_first_final_review_rejection_is_repairable(self):
        mod = _heartbeat_module("edge_heartbeat_terminal_manifest_test")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            run = home / "state" / "rito" / "one-run"
            run.mkdir(parents=True)
            manifest = run / "00_MANIFEST.json"
            base = {
                "dispatch_id": "beat-repair",
                "status": "failed",
                "failed_stage": "final_review_acceptance",
                "final_review_repair_count": 0,
                "stages": [],
            }
            manifest.write_text(json.dumps(base))
            self.assertIsNone(mod._terminal_rite_failure(home, "beat-repair"))

            base["status"] = "running"
            base["final_review_repair_count"] = 1
            manifest.write_text(json.dumps(base))
            self.assertIsNone(mod._terminal_rite_failure(home, "beat-repair"))

            base["status"] = "failed"
            manifest.write_text(json.dumps(base))
            self.assertIn(
                "one-run:final_review_acceptance",
                mod._terminal_rite_failure(home, "beat-repair"),
            )

    def test_double_detached_descendant_is_adopted_reaped_and_fails_run(self):
        mod = _heartbeat_module("edge_heartbeat_subreaper_test")
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "detached-grandchild-write"
            grandchild = (
                "import pathlib,sys,time; time.sleep(1.2); "
                "pathlib.Path(sys.argv[1]).write_text('survived')"
            )
            child = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]], "
                "start_new_session=True); time.sleep(0.1)"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2], "
                "sys.argv[3]], start_new_session=True); time.sleep(0.2)"
            )

            with self.assertRaisesRegex(mod.RuntimeDetachedChildren, "reaped pids"):
                mod._run_runtime(
                    [sys.executable, "-c", parent, child, grandchild, str(marker)],
                    cwd=Path(tmp), runtime_env=None, prompt="", use_stdin=False,
                    timeout_seconds=5,
                )
            time.sleep(1.4)
            self.assertFalse(marker.exists(), "double-detached grandchild survived")

    def test_already_exited_adopted_helper_is_reaped_without_failure(self):
        mod = _heartbeat_module("edge_heartbeat_exited_helper_test")
        with tempfile.TemporaryDirectory() as tmp:
            grandchild = "pass"
            child = (
                "import subprocess,sys; "
                "subprocess.Popen([sys.executable, '-c', sys.argv[1]], "
                "start_new_session=True)"
            )
            parent = (
                "import subprocess,sys,time; "
                "subprocess.run([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
                "time.sleep(0.3)"
            )
            code = mod._run_runtime(
                [sys.executable, "-c", parent, child, grandchild],
                cwd=Path(tmp), runtime_env=None, prompt="", use_stdin=False,
                timeout_seconds=5,
            )
            self.assertEqual(code, 0)

    def test_timeout_budget_is_global_across_acts_and_continuations(self):
        ticks = iter([10.0, 35.0, 80.0])
        mod = _heartbeat_module("edge_heartbeat_global_budget_test")
        budget = mod._HeartbeatBudget(100, clock=lambda: next(ticks))

        self.assertEqual(budget.started, 10.0)
        self.assertEqual(budget.remaining(), 75.0)
        self.assertEqual(
            budget.remaining(), 30.0,
            "a later act must consume the same original heartbeat budget",
        )


class CodexBeatCommandIsSingleShotExec(unittest.TestCase):
    """One beat on codex = `codex exec` headless, approvals bypassed, prompt on stdin (`-`)."""

    def test_command_shape(self):
        cmd = _beat.build_codex_beat_command("/opt/codex", Path("/home/x/edge"))
        self.assertEqual(
            cmd,
            [
                "/opt/codex", "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", "/home/x/edge",
                "-",
            ],
        )


class HeartbeatCliRandomMix(unittest.TestCase):
    """Operator 2026-07-13: heartbeat CLI is a weighted random draw —
    33% grok · 33% codex · 16.5% opus · 16.5% fable (claude --model)."""

    def test_default_mix_weights(self):
        mix = dict(_beat.DEFAULT_HEARTBEAT_CLI_MIX)
        self.assertAlmostEqual(mix["grok"], 33.0)
        self.assertAlmostEqual(mix["codex"], 33.0)
        self.assertAlmostEqual(mix["opus"], 16.5)
        self.assertAlmostEqual(mix["fable"], 16.5)
        self.assertAlmostEqual(sum(mix.values()), 99.0)

    def test_pick_respects_weights_under_seeded_rng(self):
        # Seeded RNG is deterministic: over many draws the empirical rates track the mix.
        import random
        rng = random.Random(42)
        n = 10_000
        counts = {"grok": 0, "codex": 0, "opus": 0, "fable": 0}
        for _ in range(n):
            counts[_beat.pick_heartbeat_cli(rng=rng)] += 1
        self.assertAlmostEqual(counts["grok"] / n, 33 / 99, delta=0.02)
        self.assertAlmostEqual(counts["codex"] / n, 33 / 99, delta=0.02)
        self.assertAlmostEqual(counts["opus"] / n, 16.5 / 99, delta=0.02)
        self.assertAlmostEqual(counts["fable"] / n, 16.5 / 99, delta=0.02)

    def test_cli_random_resolves_via_agent_yaml(self):
        import random
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text(
                "heartbeat:\n  cli: random\n", encoding="utf-8")
            # Fixed rng → reproducible pick (not the fixed string "random").
            picked = _beat.heartbeat_cli(home, rng=random.Random(0))
            self.assertIn(picked, ("grok", "codex", "opus", "fable"))

    def test_fixed_cli_still_honored(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text(
                "heartbeat:\n  cli: codex\n", encoding="utf-8")
            self.assertEqual(_beat.heartbeat_cli(home), "codex")


class BeatPromptLoadsSkillBody(unittest.TestCase):
    """The launcher pipes the /ed-beat skill BODY (frontmatter stripped) as the prompt —
    the mechanism the original edge-runner used (render the skill, pipe to claude -p -)."""

    def test_body_without_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _skill_home(tmp, "RUN-THE-BEAT-MARKER")
            prompt = _beat.load_beat_prompt(home)
            self.assertIn("RUN-THE-BEAT-MARKER", prompt)
            self.assertNotIn("name: beat", prompt)
            self.assertNotIn("---", prompt)

    def test_home_skill_wins_over_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _skill_home(tmp, "HOME-OVERRIDE")
            self.assertIn("HOME-OVERRIDE", _beat.load_beat_prompt(home))

    def test_falls_back_to_repo_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            # home has no skills/beat — falls back to the repo's real /ed-beat skill.
            prompt = _beat.load_beat_prompt(Path(tmp))
            self.assertIn("one Artefato", prompt)


class HeartbeatDryRunShowsTheLaunch(unittest.TestCase):
    """`edge-heartbeat --dry-run` shows the exact single-shot command and the piped prompt
    without invoking claude — so the autonomous launch is inspectable and tests never bill."""

    def test_dry_run_prints_command_and_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _skill_home(tmp, "RUN-THE-BEAT-MARKER")
            # Pin claude: without agent.yaml home falls through to the repo phenotype (often grok).
            res = subprocess.run(
                [sys.executable, str(HEARTBEAT), "--home", str(home),
                 "--cli", "claude", "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("-p", res.stdout)
            self.assertIn("--dangerously-skip-permissions", res.stdout)
            self.assertIn("RUN-THE-BEAT-MARKER", res.stdout)

    def test_supervised_broker_dry_run_is_token_free_and_never_starts_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _skill_home(tmp, "RUN-THE-BEAT-MARKER")
            env = {**__import__("os").environ, "XDG_RUNTIME_DIR": "/run/user/1000",
                   "EDGE_BROKER_CAPABILITY": "must-not-appear"}
            res = subprocess.run(
                [sys.executable, str(HEARTBEAT), "--home", str(home),
                 "--cli", "codex", "--supervised-cortex-broker",
                 "--dispatch-id", "dry-run-broker", "--dry-run"],
                capture_output=True, text=True, env=env,
            )
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn("mcp_servers.cortex.env_vars", res.stdout)
            self.assertIn("EDGE_BROKER_CAPABILITY", res.stdout)
            self.assertNotIn("must-not-appear", res.stdout + res.stderr)
            self.assertIn("stop in finally", res.stdout)

    def test_supervised_broker_rejects_non_codex_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = _skill_home(tmp, "RUN-THE-BEAT-MARKER")
            res = subprocess.run(
                [sys.executable, str(HEARTBEAT), "--home", str(home),
                 "--cli", "claude", "--supervised-cortex-broker", "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(res.returncode, 2)
            self.assertIn("requires --cli codex", res.stderr)


class HeartbeatOnboardingGateUsesInstallIdentity(unittest.TestCase):
    def test_log_is_anchored_to_home_even_when_launcher_is_reached_by_symlink(self):
        import importlib.machinery
        mod = importlib.machinery.SourceFileLoader(
            "edge_heartbeat_identity_test", str(HEARTBEAT)).load_module()
        self.assertEqual(
            mod._install_event_log(Path("/srv/mentorzao")),
            Path("/srv/mentorzao/state/events/log.jsonl"),
        )

    def test_explicit_runtime_root_moves_only_heartbeat_outputs(self):
        import importlib.machinery
        mod = importlib.machinery.SourceFileLoader(
            "edge_heartbeat_runtime_root_test", str(HEARTBEAT)).load_module()
        runtime = Path("/var/lib/edge-codex-heartbeat/runtime-output")
        self.assertEqual(
            mod._install_event_log(Path("/srv/mentorzao"), runtime),
            runtime / "state" / "events" / "log.jsonl",
        )


class HeartbeatTerminalFailureReceipt(unittest.TestCase):
    def test_nonterminal_rite_is_discovered_and_continuation_is_localized(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            run = home / "state" / "rito" / "same-run"
            run.mkdir(parents=True)
            manifest = run / "00_MANIFEST.json"
            manifest.write_text(json.dumps({
                "dispatch_id": "beat-resume", "status": "running",
                "stages": [{"name": "grounding", "status": "completed"},
                           {"name": "fact_audit", "status": "running"}],
            }))
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_resume_test", str(HEARTBEAT)).load_module()
            found = mod._rite_manifests(home, "beat-resume")
            self.assertEqual([p for p, _ in found], [manifest])
            prompt = mod._continuation_prompt("beat-resume", found)
            self.assertIn("resume=True", prompt)
            self.assertIn(str(run), prompt)
            self.assertIn("Do NOT rerun Ato 1", prompt)

    def test_incomplete_ato1_gets_one_localized_continuation_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "beat-ato1", "origin": "beat"}, log=log)
            eventlog.append("pauta.phase_receipt", "pauta", {
                "dispatch_id": "beat-ato1", "phase": "shortlist", "status": "completed",
            }, log=log)
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_ato1_resume_test", str(HEARTBEAT)).load_module()
            self.assertTrue(mod._ato1_is_incomplete(eventlog, log, "beat-ato1"))
            prompt = mod._ato1_continuation_prompt("beat-ato1")
            self.assertIn("Do NOT mint or open another dispatch", prompt)
            self.assertIn("phase receipt", prompt)
            self.assertIn("TaskOutput/Monitor", prompt)
            self.assertIn("Do not open Ato-2", prompt)

    def test_checkpoint_prompts_split_ato1_from_ato2(self):
        import importlib.machinery
        mod = importlib.machinery.SourceFileLoader(
            "edge_heartbeat_checkpoint_prompt_test", str(HEARTBEAT)).load_module()
        ato1 = mod._ato1_checkpoint_prompt("SIGNED SKILL", "beat-split")
        self.assertIn("ONLY Ato-1", ato1)
        self.assertIn("Do not open Ato-2", ato1)
        self.assertIn("SIGNED SKILL", ato1)
        ato2 = mod._ato2_start_prompt("beat-split")
        self.assertIn("already survived", ato2)
        self.assertIn("Do NOT rerun Ato-1", ato2)
        self.assertIn("same dispatch_id", ato2)

    def test_dispatch_event_types_are_identity_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "ours", "origin": "beat"}, log=log)
            eventlog.append("pauta.proposta", "pauta", {"dispatch_id": "ours"}, log=log)
            eventlog.append("dispatch.failed", "dispatch", {"dispatch_id": "other"}, log=log)
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_checkpoint_state_test", str(HEARTBEAT)).load_module()
            self.assertEqual(
                mod._dispatch_event_types(eventlog, log, "ours"),
                {"dispatch.open", "pauta.proposta"},
            )

    def test_ato1_continuation_refuses_terminal_or_unopened_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_ato1_terminal_test", str(HEARTBEAT)).load_module()
            self.assertFalse(mod._ato1_is_incomplete(eventlog, log, "never-opened"))

            for index, terminal_type in enumerate(
                    ("pauta.proposta", "pauta.silencio", "dispatch.failed")):
                dispatch_id = f"terminal-{index}"
                eventlog.dispatch_open({"dispatch_id": dispatch_id, "origin": "beat"}, log=log)
                eventlog.append(terminal_type, "dispatch", {
                    "dispatch_id": dispatch_id,
                }, log=log)
                self.assertFalse(
                    mod._ato1_is_incomplete(eventlog, log, dispatch_id), terminal_type)

    def test_ato1_receipt_derives_durations_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            log.parent.mkdir(parents=True)
            seeded = [
                {"seq": 1, "ts": "2026-01-01T00:00:00+00:00", "type": "dispatch.open",
                 "subject": "dispatch", "payload": {"dispatch_id": "beat-t"}},
                {"seq": 2, "ts": "2026-01-01T00:00:02+00:00", "type": "dispatch.grounding",
                 "subject": "grounding", "payload": {"dispatch_id": "beat-t"}},
                {"seq": 3, "ts": "2026-01-01T00:00:07+00:00", "type": "pauta.silencio",
                 "subject": "pauta", "payload": {"dispatch_id": "beat-t"}},
            ]
            log.write_text("".join(json.dumps(e) + "\n" for e in seeded))
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_timing_test", str(HEARTBEAT)).load_module()
            mod._record_ato1_receipt(eventlog, log, "beat-t")
            mod._record_ato1_receipt(eventlog, log, "beat-t")
            receipts = eventlog.read(types=["dispatch.phase_receipt"], log=log)
            self.assertEqual(len(receipts), 1)
            payload = receipts[0]["payload"]
            self.assertEqual(payload["open_to_grounding_seconds"], 2.0)
            self.assertEqual(payload["grounding_to_pauta_seconds"], 5.0)
            self.assertEqual(payload["ato1_total_seconds"], 7.0)

    def test_timeout_records_dispatch_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            eventlog.dispatch_open({"dispatch_id": "beat-timeout"}, log=log)
            _beat_eventlog = eventlog
            HEARTBEAT_MODULE = REPO / "tools" / "edge-heartbeat"
            # Exercise the small deterministic receipt seam directly; process timing is tested
            # by subprocess.run's standard TimeoutExpired contract.
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader("edge_heartbeat_test", str(HEARTBEAT_MODULE)).load_module()
            mod._record_failure(_beat_eventlog, log, "beat-timeout", reason="timeout",
                                cli="codex", detail="hard limit 1s exceeded", elapsed_seconds=1.2)
            failed = eventlog.read(types=["dispatch.failed"], log=log)
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["payload"]["dispatch_id"], "beat-timeout")
            self.assertEqual(failed[0]["payload"]["reason"], "timeout")
            self.assertFalse(eventlog.wake_fresh_for("beat-timeout", log=log),
                             "a failed dispatch must never retain publication authority")

    def test_interruption_makes_matching_running_manifest_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            run = home / "state" / "rito" / "draft"
            run.mkdir(parents=True)
            manifest = run / "00_MANIFEST.json"
            manifest.write_text(json.dumps({
                "dispatch_id": "beat-stopped",
                "status": "running",
                "stages": [
                    {"name": "grounding", "status": "completed"},
                    {"name": "rewrite", "status": "running", "finished_at": None},
                ],
            }))
            import importlib.machinery
            mod = importlib.machinery.SourceFileLoader(
                "edge_heartbeat_manifest_test", str(HEARTBEAT)).load_module()
            changed = mod._mark_running_rites_failed(
                home, "beat-stopped", "heartbeat_interrupted")
            self.assertEqual(changed, [str(manifest)])
            data = json.loads(manifest.read_text())
            self.assertEqual(data["status"], "failed")
            self.assertEqual(data["failed_stage"], "rewrite")
            self.assertEqual(data["stages"][1]["error"], "heartbeat_interrupted")


class BeatEnvCarriesInstallSecrets(unittest.TestCase):
    """The dispatch env must carry the install's secrets so the beat's AGENTIC via-spec source
    calls (exa/x/hn/arxiv/github) and the graph leg have credentials — else the world-leg darkens
    (root cause of the cert's substrate-only beats). ADR-0011: missing secrets never blocks."""

    def test_build_beat_env_loads_install_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "secrets").mkdir()
            (home / "secrets" / "test.env").write_text("EDGE_TEST_CERT_KEY=abc123\n")
            env = _beat.build_beat_env(home)
            self.assertEqual(env.get("EDGE_TEST_CERT_KEY"), "abc123")

    def test_build_beat_env_binds_live_install_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text("name: mentor-test\n")
            env = _beat.build_beat_env(home)
            self.assertEqual(env["EDGE_HOME"], str(home.resolve()))
            self.assertEqual(env["EDGE_GROUP"], "mentor-test")

    def test_missing_secrets_dir_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _beat.build_beat_env(Path(tmp))  # no secrets/ — must not raise
            self.assertIsInstance(env, dict)


class BeatPostDispatchGateAssertsCorpusProgress(unittest.TestCase):
    """A beat that exits 0 has NOT necessarily done stage-(iii) work: `claude -p` returning 0 only
    proves the subprocess ran, not that a kerneled Artefato was published. `assert_beat_produced`
    is the deterministic post-dispatch gate — given the corpus count BEFORE the beat, it folds the
    log AFTER and returns gaps (empty == produced) when the corpus did NOT grow by >=1 OR there is
    C3 debt (a published Artefato with no intent kernel). edge-heartbeat consults it to turn a
    'succeeded-but-produced-nothing' beat into a NONZERO exit (Codex gate finding [high])."""

    def _log(self, tmp):
        return Path(tmp) / "events" / "log.jsonl"

    def test_no_new_artefato_is_a_gap(self):
        # before == after (corpus stayed at N): the beat produced nothing.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log(tmp)
            eventlog.publish_artefato_atomic("pre", "why-pre", log=log)
            before = len(eventlog.corpus_at(log=log))  # N = 1
            gaps = _beat.assert_beat_produced(log, before)  # corpus unchanged
            self.assertTrue(gaps, "stagnant corpus must report a gap")

    def test_c3_debt_is_a_gap_even_when_corpus_grew(self):
        # corpus grew by 1, but the new Artefato has NO intent kernel (C3 debt).
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log(tmp)
            before = len(eventlog.corpus_at(log=log))  # N = 0
            eventlog._append_orphan_published_for_test("kernel-less", log=log)
            gaps = _beat.assert_beat_produced(log, before)
            self.assertTrue(gaps, "a kernel-less Artefato is C3 debt — a gap")
            self.assertIn("kernel-less", " ".join(gaps))

    def test_new_kerneled_artefato_passes(self):
        # corpus grew by exactly 1 AND the new Artefato carries its kernel: no gaps.
        with tempfile.TemporaryDirectory() as tmp:
            log = self._log(tmp)
            before = len(eventlog.corpus_at(log=log))  # N = 0
            eventlog.publish_artefato_atomic("fresh", "why-fresh", log=log)
            gaps = _beat.assert_beat_produced(log, before)
            self.assertEqual(gaps, [], f"a new kerneled Artefato is a produced beat: {gaps}")


class HeartbeatLockSerializesTheCriticalSection(unittest.TestCase):
    """Codex gate round-4 [medium]: the heartbeat captures before_count BEFORE dispatch and accepts
    ANY corpus increase after `claude -p` returns — so two overlapping heartbeats let one invocation
    produce nothing yet pass (another producer appended a kerneled Artefato during its window). The
    fix serializes the WHOLE critical section {before_count -> claude -p -> assert_beat_produced} on
    an exclusive flock so a corpus increase is attributable to the invocation that produced it.

    `_beat.heartbeat_lock(home)` is the context manager holding that flock. Two threads contending
    for it are MUTUALLY EXCLUSIVE: the second cannot enter while the first holds it (no overlapping
    window). Mirrors test_beat_round_robin's barrier + concurrency check."""

    def test_two_contending_threads_never_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            inside = 0          # how many threads are inside the critical section right now
            max_inside = 0      # the high-water mark — must never exceed 1 if mutually exclusive
            mu = threading.Lock()
            start = threading.Barrier(2)

            def worker():
                nonlocal inside, max_inside
                start.wait()  # maximize contention on the lock
                with _beat.heartbeat_lock(home):
                    with mu:
                        inside += 1
                        max_inside = max(max_inside, inside)
                    time.sleep(0.05)  # hold the section so an overlap would be observed
                    with mu:
                        inside -= 1

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # If the lock serializes, only ever one thread is inside the section at a time.
            self.assertEqual(max_inside, 1,
                             "heartbeat_lock must serialize: the second thread entered the "
                             "critical section while the first still held the lock")

    def test_lock_can_live_in_separate_runtime_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "install"
            runtime = root / "runtime"
            home.mkdir()
            with _beat.heartbeat_lock(home, runtime_root=runtime):
                self.assertTrue(
                    (runtime / "state" / "beat" / "heartbeat.lock").is_file()
                )
            self.assertFalse((home / "state" / "beat" / "heartbeat.lock").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
