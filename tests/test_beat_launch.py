"""The autonomous beat launcher — a single-shot `claude -p -` fed the /ed-beat skill body.

The beat runs entirely inside Claude Code (ADR-0003): the launcher does no cognition. It
resolves the claude binary, loads the beat skill's prompt (home wins over repo), and pipes it
into one `claude -p -` invocation — no envelope, no retry. Cognition lives in the skill.
"""
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


class CodexBeatCommandIsSingleShotExec(unittest.TestCase):
    """One beat on codex = `codex exec` headless, approvals bypassed, prompt on stdin (`-`)."""

    def test_command_shape(self):
        cmd = _beat.build_codex_beat_command("/opt/codex", Path("/home/x/edge"))
        self.assertEqual(
            cmd,
            [
                "/opt/codex", "exec",
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


class HeartbeatPublicLauncherIsDark(unittest.TestCase):
    """The public launcher must fail before reading a skill or constructing a command."""

    def test_dry_run_is_still_blocked_before_home_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "not-created"
            res = subprocess.run(
                [sys.executable, str(HEARTBEAT), "--home", str(home), "--dry-run"],
                capture_output=True, text=True,
            )
            self.assertEqual(res.returncode, 2, res.stdout + res.stderr)
            self.assertEqual(res.stdout, "")
            self.assertIn("blocked until Hermes-native parity", res.stderr)
            self.assertFalse(home.exists())


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
