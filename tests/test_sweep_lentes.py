"""Coordinator contract for bounded, resumable session rationalization in sweep."""

import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402
import sweep  # noqa: E402


HUMAN_TEXT = "decisão substancial sobre a atividade corrente e seu próximo passo " * 5
RATIONALIZER_VERSION = "racionalizador-v3-session-provenance"


def write_session(directory, session_id, *, human_turns=5, mtime=None):
    lines = []
    for index in range(human_turns):
        lines.append(json.dumps({
            "type": "user",
            "message": {"content": f"{HUMAN_TEXT} ({index})"},
        }))
        lines.append(json.dumps({
            "type": "assistant",
            "message": {"content": f"continuação {index}"},
        }))
    path = Path(directory) / f"{session_id}.jsonl"
    path.write_text("\n".join(lines) + "\n")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def checkpoint(log, item, version=RATIONALIZER_VERSION):
    identity = sweep.rationalization_identity(
        item["id"], item["turns"], surface=item["surface"],
        watermark=item["watermark"], racionalizador_version=version,
    )
    return eventlog.append(
        "sessao.racionalizada",
        f"sessao:{item['id']}",
        {
            "sessao_id": item["id"],
            "surface": item["surface"],
            "watermark": item["watermark"],
            "racionalizador_version": version,
            "source_hash": identity["source_hash"],
            "rationalization_id": identity["rationalization_id"],
        },
        log=log,
    )


class RationalizationPlanning(unittest.TestCase):
    def test_exclusion_reconciliation_is_structured_and_idempotent(self):
        with tempfile.TemporaryDirectory() as project, \
                tempfile.TemporaryDirectory() as state, \
                tempfile.TemporaryDirectory() as codex_root:
            log = Path(state) / "events.jsonl"
            codex_dir = Path(codex_root) / "2026" / "07" / "19"
            codex_dir.mkdir(parents=True)

            def write_codex(filename, session_id, source, originator):
                rows = [{"type": "session_meta", "payload": {
                    "id": session_id, "thread_source": "user",
                    "source": source, "originator": originator,
                }}, {
                    "type": "response_item", "payload": {
                        "type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "conteúdo arbitrário"}],
                    },
                }]
                (codex_dir / filename).write_text(
                    "\n".join(json.dumps(row) for row in rows) + "\n")

            write_codex("operator.jsonl", "operator", "cli", "codex-tui")
            write_codex("delegated.jsonl", "delegated", "exec", "codex_exec")

            first = sweep.record_session_exclusions(
                project, log=log, codex_dir=codex_root, grok_dir=False)
            second = sweep.record_session_exclusions(
                project, log=log, codex_dir=codex_root, grok_dir=False)

            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["payload"], {
                "sessao_id": "codex:delegated", "surface": "codex",
                "reason": "codex-source:exec",
            })
            self.assertEqual(second, [])

    def test_pending_is_substantial_uncheckpointed_current_input_oldest_first(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            old = write_session(project, "old", mtime=100)
            write_session(project, "middle", mtime=200)
            write_session(project, "thin", human_turns=1, mtime=50)
            write_session(project, "new", mtime=300)

            initial = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=None)
            checkpoint(log, next(item for item in initial if item["id"] == "middle"))

            pending = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=None)
            self.assertEqual([item["id"] for item in pending], ["old", "new"])

            # A persisted session is append-only. When it grows, the watermark changes and the
            # old checkpoint no longer covers its current input.
            with old.open("a") as fh:
                fh.write(json.dumps({"type": "user", "message": {"content": HUMAN_TEXT}}) + "\n")
            os.utime(old, (400, 400))
            checkpoint(log, next(item for item in pending if item["id"] == "old"))
            grown = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=None)
            self.assertEqual([item["id"] for item in grown], ["new", "old"])

    def test_plan_uses_mentee_dialogue_pre_process_across_three_surfaces(self):
        """M2.MIN.1 — plan_rationalizations consumes mentee_dialogue only (no workers, no tools)."""
        import sessions  # noqa: E402 — plan seam; fixtures mirror real Claude/Codex/Grok stores

        with tempfile.TemporaryDirectory() as project, \
                tempfile.TemporaryDirectory() as state, \
                tempfile.TemporaryDirectory() as codex_root, \
                tempfile.TemporaryDirectory() as grok_root:
            log = Path(state) / "events.jsonl"

            # Claude operator + interleaved tools (must not appear in plan turns).
            claude_lines = []
            for index in range(5):
                claude_lines.append(json.dumps({
                    "type": "user",
                    "message": {"content": f"{HUMAN_TEXT} (c{index})"},
                }))
                claude_lines.append(json.dumps({
                    "type": "assistant",
                    "message": {"role": "assistant",
                                "content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
                }))
                claude_lines.append(json.dumps({
                    "type": "assistant",
                    "message": {"content": f"edge c{index}"},
                }))
            (Path(project) / "op-claude.jsonl").write_text("\n".join(claude_lines) + "\n")

            # Claude sidechain worker — must not be planned.
            worker = Path(project) / "subagents" / "worker.jsonl"
            worker.parent.mkdir(parents=True)
            worker.write_text("\n".join(claude_lines) + "\n")

            # Codex operator (thread_source=user) + function_call noise.
            codex_dir = Path(codex_root) / "2026" / "07" / "13"
            codex_dir.mkdir(parents=True)
            codex_rows = [
                {"type": "session_meta",
                 "payload": {"id": "codex-op", "thread_source": "user",
                             "source": "cli", "originator": "codex-tui"}},
            ]
            for index in range(5):
                codex_rows.append({
                    "type": "response_item",
                    "payload": {"type": "message", "role": "user",
                                "content": [{"type": "input_text",
                                             "text": f"{HUMAN_TEXT} (x{index})"}]},
                })
                codex_rows.append({
                    "type": "response_item",
                    "payload": {"type": "function_call", "name": "exec_command"},
                })
                codex_rows.append({
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant",
                                "content": [{"type": "output_text",
                                             "text": f"edge x{index}"}]},
                })
            (codex_dir / "rollout-op.jsonl").write_text(
                "\n".join(json.dumps(r) for r in codex_rows) + "\n")

            # Codex subagent — must not be planned.
            codex_worker = [
                {"type": "session_meta",
                 "payload": {"id": "codex-w", "thread_source": "subagent",
                             "parent_thread_id": "codex-op"}},
            ]
            for index in range(5):
                codex_worker.append({
                    "type": "response_item",
                    "payload": {"type": "message", "role": "user",
                                "content": [{"type": "input_text",
                                             "text": f"{HUMAN_TEXT} (w{index})"}]},
                })
                codex_worker.append({
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant",
                                "content": [{"type": "output_text", "text": f"ww{index}"}]},
                })
            (codex_dir / "rollout-w.jsonl").write_text(
                "\n".join(json.dumps(r) for r in codex_worker) + "\n")

            # Codex delegated exec may misleadingly say thread_source=user. Structured source
            # provenance, not prompt vocabulary, must still keep it out of the operator film.
            codex_exec = [
                {"type": "session_meta",
                 "payload": {"id": "codex-exec", "thread_source": "user",
                             "source": "exec", "originator": "codex_exec"}},
            ]
            for index in range(5):
                codex_exec.extend([{
                    "type": "response_item",
                    "payload": {"type": "message", "role": "user",
                                "content": [{"type": "input_text",
                                             "text": f"{HUMAN_TEXT} (e{index})"}]},
                }, {
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant",
                                "content": [{"type": "output_text", "text": f"ee{index}"}]},
                }])
            (codex_dir / "rollout-exec.jsonl").write_text(
                "\n".join(json.dumps(r) for r in codex_exec) + "\n")

            # Grok operator + backend tools; worker via session_kind.
            grok_op = Path(grok_root) / "%2Fhome" / "g-op"
            grok_op.mkdir(parents=True)
            grok_lines = []
            for index in range(5):
                body = f"<user_query>\n{HUMAN_TEXT} (g{index})\n</user_query>"
                grok_lines.append(json.dumps({
                    "type": "user",
                    "content": [{"type": "text", "text": body}],
                }))
                grok_lines.append(json.dumps({
                    "type": "backend_tool_call", "name": "bash",
                }))
                grok_lines.append(json.dumps({
                    "type": "assistant",
                    "content": [{"type": "text", "text": f"edge g{index}"}],
                }))
            (grok_op / "chat_history.jsonl").write_text("\n".join(grok_lines) + "\n")
            (grok_op / "summary.json").write_text(json.dumps({
                "info": {"id": "g-op", "cwd": "/tmp"},
            }))

            grok_w = Path(grok_root) / "%2Fhome" / "g-w"
            grok_w.mkdir(parents=True)
            (grok_w / "chat_history.jsonl").write_text("\n".join(grok_lines) + "\n")
            (grok_w / "summary.json").write_text(json.dumps({
                "info": {"id": "g-w"},
                "session_kind": "subagent",
            }))

            pending = sweep.plan_rationalizations(
                project, log=log, codex_dir=codex_root, grok_dir=grok_root,
                backfill_days=None,
            )
            by_id = {item["id"]: item for item in pending}
            self.assertEqual(
                set(by_id),
                {"op-claude", "codex:codex-op", "grok:g-op"},
                "workers/sidechains must not enter rationalization plan",
            )
            for item in pending:
                roles = {t.role for t in item["turns"]}
                self.assertEqual(roles, {"human", "edge"})
                for turn in item["turns"]:
                    self.assertIsInstance(turn, sessions.Turn)
                    self.assertNotIn("tool_use", turn.text)
                    self.assertNotIn("function_call", turn.text)
                    self.assertNotIn("backend_tool", turn.text)
                self.assertGreaterEqual(item["watermark"], len(item["turns"]),
                                        "watermark is raw line count (CAS), not turn count")

    def test_checkpoint_authority_is_recomputed_rationalization_id_not_matching_metadata(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "session", mtime=100)
            item = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=None)[0]
            eventlog.append(
                "sessao.racionalizada", "sessao:session",
                {"sessao_id": "session", "surface": "claude",
                 "watermark": item["watermark"],
                 "racionalizador_version": RATIONALIZER_VERSION,
                 "source_hash": "0" * 64, "rationalization_id": "f" * 64},
                log=log,
            )
            self.assertEqual(
                [pending["id"] for pending in sweep.plan_rationalizations(
                    project, log=log, codex_dir=False, backfill_days=None)],
                ["session"],
            )
            checkpoint(log, item)
            self.assertEqual(sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=None), [])

    def test_backfill_days_filters_cost_without_deleting_the_raw_store(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            now = datetime(2026, 7, 11, tzinfo=timezone.utc)
            old = write_session(project, "old", mtime=now.timestamp() - 40 * 86400)
            write_session(project, "recent", mtime=now.timestamp() - 2 * 86400)

            bounded = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=30, now=now)
            self.assertEqual([item["id"] for item in bounded], ["recent"])
            self.assertTrue(old.exists(), "backfill is a cost horizon, never raw-store decay")

            expanded = sweep.plan_rationalizations(
                project, log=log, codex_dir=False, backfill_days=60, now=now)
            self.assertEqual([item["id"] for item in expanded], ["old", "recent"])


class RationalizationCoordinator(unittest.TestCase):
    def test_budget_stops_at_first_session_that_does_not_fit_and_next_sweep_resumes(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            for index, session_id in enumerate(("one", "two", "three"), start=1):
                write_session(project, session_id, mtime=index * 100)

            costs = {"one": 3, "two": 5, "three": 2}
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                budget = kwargs["sweep_token_budget"]
                calls.append((session_id, budget))
                cost = costs[session_id]
                if budget is not None and cost > budget:
                    return {
                        "emitted": [],
                        "skipped_reason": "budget_exhausted",
                        "usage": {"estimated_tokens": 0},
                    }
                item = {
                    "id": session_id,
                    "surface": kwargs["surface"],
                    "watermark": kwargs["watermark"],
                    "turns": turns,
                }
                emitted = [checkpoint(log, item, kwargs["racionalizador_version"])]
                return {
                    "emitted": emitted,
                    "usage": {
                        "input_tokens": cost - 1,
                        "output_tokens": 1,
                        "estimated_tokens": cost,
                    },
                }

            first = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=3,
                sweep_token_budget=6,
                backfill_days=None,
            )
            self.assertEqual(calls, [("one", 6), ("two", 3)])
            self.assertEqual(first["rationalized"], ["one"])
            self.assertEqual(first["pending"], ["two", "three"])
            self.assertEqual(first["usage"]["estimated_tokens"], 3)

            calls.clear()
            second = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=3,
                sweep_token_budget=10,
                backfill_days=None,
            )
            self.assertEqual(calls, [("two", 10), ("three", 5)])
            self.assertEqual(second["rationalized"], ["two", "three"])
            self.assertEqual(second["pending"], [])
            self.assertEqual(second["usage"]["estimated_tokens"], 7)

    def test_max_sessions_per_sweep_leaves_the_rest_pending(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            for index, session_id in enumerate(("one", "two", "three"), start=1):
                write_session(project, session_id, mtime=index * 100)

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                self.assertEqual(kwargs["scene_turn_limit"], 2)
                item = {"id": session_id, "surface": kwargs["surface"],
                        "watermark": kwargs["watermark"], "turns": turns}
                return {"emitted": [checkpoint(log, item, kwargs["racionalizador_version"])],
                        "usage": {"estimated_tokens": 1}}

            result = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=2,
                sweep_token_budget=100,
                backfill_days=None,
                scene_turn_limit=2,
            )
            self.assertEqual(result["rationalized"], ["one", "two"])
            self.assertEqual(result["pending"], ["three"])

    def test_invalid_output_continues_to_next_session_without_stopping(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            for index, session_id in enumerate(("one", "two"), start=1):
                write_session(project, session_id, mtime=index * 100)
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                calls.append(session_id)
                if session_id == "one":
                    return {
                        "emitted": [],
                        "skipped_reason": "invalid_output",
                        "error": "scene[0] output is not valid JSON",
                        "usage": {"estimated_tokens": 1},
                    }
                item = {
                    "id": session_id,
                    "surface": kwargs["surface"],
                    "watermark": kwargs["watermark"],
                    "turns": turns,
                }
                return {
                    "emitted": [checkpoint(log, item, kwargs["racionalizador_version"])],
                    "usage": {"estimated_tokens": 1},
                }

            result = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=5,
                sweep_token_budget=100,
                backfill_days=None,
            )
            self.assertEqual(calls, ["one", "two"])
            self.assertEqual(result["attempted"], ["one", "two"])
            self.assertEqual(result["rationalized"], ["two"])
            self.assertIsNone(result["stopped_reason"])
            self.assertIn(
                {"id": "one", "reason": "invalid_output",
                 "error": "scene[0] output is not valid JSON"},
                result.get("skipped", []),
            )

    def test_max_sessions_counts_invalid_attempts_not_only_successes(self):
        """Finding G: soft failures must consume max_sessions_per_sweep attempts."""
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            for index, session_id in enumerate(("a", "b", "c"), start=1):
                write_session(project, session_id, mtime=index * 100)
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                calls.append(session_id)
                return {
                    "emitted": [],
                    "skipped_reason": "invalid_output",
                    "error": "bad",
                    "usage": {"estimated_tokens": 1},
                }

            result = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=1,
                sweep_token_budget=10_000,
                backfill_days=None,
            )
            self.assertEqual(calls, ["a"])
            self.assertEqual(result["attempted"], ["a"])
            self.assertEqual(result["rationalized"], [])
            self.assertEqual(result["stopped_reason"], "max_sessions_per_sweep")

    def test_rationalize_coordinator_lock_dark_when_held(self):
        """Finding F: held rationalize.lock must not block forever — lock_dark."""
        import fcntl
        import os
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "held", mtime=100)
            lock_path = Path(str(log) + ".rationalize.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            held = open(lock_path, "w")
            fcntl.flock(held, fcntl.LOCK_EX)
            try:
                os.environ["EDGE_RATIONALIZE_LOCK_WAIT_S"] = "0.3"
                os.environ["EDGE_RATIONALIZE_LOCK_POLL_S"] = "0.05"
                result = sweep.rationalize_pending_sessions(
                    project,
                    lambda _prompt: "unused",
                    log=log,
                    codex_dir=False,
                    rationalize_fn=lambda *a, **k: {"emitted": []},
                    max_sessions_per_sweep=5,
                    backfill_days=None,
                )
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()
                os.environ.pop("EDGE_RATIONALIZE_LOCK_WAIT_S", None)
                os.environ.pop("EDGE_RATIONALIZE_LOCK_POLL_S", None)
            self.assertEqual(result["stopped_reason"], "lock_dark")
            self.assertEqual(result["attempted"], [])
            self.assertEqual(result["rationalized"], [])

    def test_output_is_bounded_by_remaining_sweep_budget_and_oversize_stays_pending(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "large-output", mtime=100)
            output_caps = []

            def completer_factory(max_tokens):
                output_caps.append(max_tokens)
                return lambda _prompt: "x" * (max_tokens * 8)

            result = sweep.rationalize_pending_sessions(
                project,
                None,
                completer_factory=completer_factory,
                log=log,
                codex_dir=False,
                max_sessions_per_sweep=1,
                sweep_token_budget=3000,
                backfill_days=None,
                scene_turn_limit=40,
            )
            self.assertTrue(output_caps)
            self.assertLessEqual(max(output_caps), 3000)
            self.assertLessEqual(result["usage"]["estimated_tokens"], 3000)
            self.assertEqual(result["rationalized"], [])
            self.assertEqual(result["pending"], ["large-output"])

    def test_repeated_invalid_output_parks_session_and_frees_budget_for_later(self):
        """Oldest bad session must not thrash the budget forever (G2 soft-fail park)."""
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "bad", mtime=100)
            write_session(project, "good", mtime=200)
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                calls.append(session_id)
                if session_id == "bad":
                    return {
                        "emitted": [],
                        "skipped_reason": "invalid_output",
                        "error": "scene[0] output is not valid JSON",
                        # Burns the whole sweep budget when attempted — the thrash case.
                        "usage": {
                            "estimated_tokens": kwargs["sweep_token_budget"] or 1,
                        },
                    }
                item = {
                    "id": session_id,
                    "surface": kwargs["surface"],
                    "watermark": kwargs["watermark"],
                    "turns": turns,
                }
                return {
                    "emitted": [checkpoint(log, item, kwargs["racionalizador_version"])],
                    "usage": {"estimated_tokens": 1},
                }

            kwargs = dict(
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=5,
                sweep_token_budget=100,
                backfill_days=None,
            )
            threshold = sweep.SOFT_FAIL_PARK_THRESHOLD
            for _ in range(threshold):
                result = sweep.rationalize_pending_sessions(
                    project, lambda _prompt: "unused", **kwargs)
                self.assertEqual(result["attempted"], ["bad"])
                self.assertEqual(result["stopped_reason"], "budget_exhausted")
                self.assertEqual(result["rationalized"], [])

            self.assertEqual(calls, ["bad"] * threshold)
            calls.clear()

            # After park: bad is not attempted; good gets the budget.
            parked = sweep.rationalize_pending_sessions(
                project, lambda _prompt: "unused", **kwargs)
            self.assertNotIn("bad", parked["attempted"])
            self.assertEqual(parked["attempted"], ["good"])
            self.assertEqual(parked["rationalized"], ["good"])
            self.assertEqual(calls, ["good"])
            self.assertIn(
                {"id": "bad", "reason": "soft_fail_parked"},
                parked.get("skipped", []),
            )

    def test_watermark_growth_resets_soft_fail_park(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            bad_path = write_session(project, "bad", mtime=100)
            calls = []

            def always_invalid(session_id, turns, complete_fn, log, **kwargs):
                calls.append((session_id, kwargs["watermark"]))
                return {
                    "emitted": [],
                    "skipped_reason": "invalid_output",
                    "error": "malformed",
                    "usage": {"estimated_tokens": 1},
                }

            kwargs = dict(
                log=log,
                codex_dir=False,
                rationalize_fn=always_invalid,
                max_sessions_per_sweep=5,
                sweep_token_budget=100,
                backfill_days=None,
            )
            for _ in range(sweep.SOFT_FAIL_PARK_THRESHOLD):
                sweep.rationalize_pending_sessions(
                    project, lambda _prompt: "unused", **kwargs)

            calls.clear()
            parked = sweep.rationalize_pending_sessions(
                project, lambda _prompt: "unused", **kwargs)
            self.assertEqual(parked["attempted"], [])
            self.assertEqual(calls, [])

            # Session grows → new watermark unparks / resets the soft-fail counter.
            with bad_path.open("a") as fh:
                fh.write(json.dumps({
                    "type": "user",
                    "message": {"content": HUMAN_TEXT},
                }) + "\n")
            os.utime(bad_path, (150, 150))

            unparked = sweep.rationalize_pending_sessions(
                project, lambda _prompt: "unused", **kwargs)
            self.assertEqual(unparked["attempted"], ["bad"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "bad")

    def test_budget_exhausted_still_hard_stops_without_soft_fail_park(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "big", mtime=100)
            write_session(project, "later", mtime=200)
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                calls.append(session_id)
                return {
                    "emitted": [],
                    "skipped_reason": "budget_exhausted",
                    "usage": {"estimated_tokens": 0},
                }

            result = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=5,
                sweep_token_budget=50,
                backfill_days=None,
            )
            self.assertEqual(calls, ["big"])
            self.assertEqual(result["attempted"], ["big"])
            self.assertEqual(result["stopped_reason"], "budget_exhausted")
            self.assertEqual(result["rationalized"], [])
            # Hard stop must not soft-fail-park; next sweep still tries oldest first.
            calls.clear()
            again = sweep.rationalize_pending_sessions(
                project,
                lambda _prompt: "unused",
                log=log,
                codex_dir=False,
                rationalize_fn=fake_rationalize,
                max_sessions_per_sweep=5,
                sweep_token_budget=50,
                backfill_days=None,
            )
            self.assertEqual(again["attempted"], ["big"])
            self.assertEqual(calls, ["big"])


class RunWiring(unittest.TestCase):
    def test_run_remains_mechanical_and_never_invokes_sleep_time_cognition(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            cursors = Path(state) / "cursors.json"
            log = Path(state) / "events.jsonl"
            with mock.patch.object(sweep, "rationalize_pending_sessions") as coordinator, \
                    mock.patch.object(sweep, "_maybe_propose_topic_directions", return_value=0):
                sweep.run(
                    project,
                    ingest_fn=lambda _items: set(),
                    cursors_path=cursors,
                    reproject_fn=False,
                    log=log,
                    graph_recover_fn=False,
                    group="test-group",
                    codex_dir=False,
                )
            coordinator.assert_not_called()

    def test_explicit_backlog_runner_does_not_construct_completer_when_backlog_empty(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            factory = mock.Mock(side_effect=AssertionError("must stay lazy"))
            result = sweep.run_rationalization_backlog(
                project,
                log=Path(state) / "events.jsonl",
                codex_dir=False,
                completer_factory=factory,
                reconcile_fn=lambda _log: None,
                project_fn=lambda _log, _store: None,
                render_fn=lambda _log: None,
                graph_store=object(),
                lentes_config={
                    "backfill_days": 30,
                    "max_sessions_per_sweep": 2,
                    "sweep_token_budget": 100,
                    "scene_turn_limit": 40,
                },
            )
            self.assertEqual(result["rationalized"], [])
            self.assertEqual(result["pending"], [])
            factory.assert_not_called()

    def test_explicit_worker_orders_reconcile_project_render_after_checkpoint(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "session", mtime=100)
            order = []
            store = object()

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                item = {"id": session_id, "surface": kwargs["surface"],
                        "watermark": kwargs["watermark"], "turns": turns}
                checkpoint(log, item, kwargs["racionalizador_version"])
                order.append("rationalize")
                return {"emitted": ["checkpoint"], "usage": {"estimated_tokens": 1}}

            result = sweep.run_rationalization_backlog(
                project,
                log=log,
                codex_dir=False,
                complete_fn=lambda _prompt: "unused",
                rationalize_fn=fake_rationalize,
                reconcile_fn=lambda actual_log: order.append(("reconcile", actual_log)),
                project_fn=lambda actual_log, actual_store:
                    order.append(("project", actual_log, actual_store)),
                render_fn=lambda actual_log: order.append(("render", actual_log)),
                graph_store=store,
                lentes_config={
                    "backfill_days": None,
                    "max_sessions_per_sweep": 1,
                    "sweep_token_budget": 100,
                    "scene_turn_limit": 40,
                },
            )
            self.assertEqual(order, [
                "rationalize", ("reconcile", log), ("project", log, store),
                ("render", log),
            ])
            self.assertEqual(result["rationalized"], ["session"])
            self.assertEqual(
                len(eventlog.read(types=["sessao.racionalizada"], log=log)), 1)

    def test_downstream_failures_are_isolated_and_checkpoint_remains_durable(self):
        with tempfile.TemporaryDirectory() as project, tempfile.TemporaryDirectory() as state:
            log = Path(state) / "events.jsonl"
            write_session(project, "session", mtime=100)
            calls = []

            def fake_rationalize(session_id, turns, complete_fn, log, **kwargs):
                item = {"id": session_id, "surface": kwargs["surface"],
                        "watermark": kwargs["watermark"], "turns": turns}
                checkpoint(log, item, kwargs["racionalizador_version"])
                return {"emitted": ["checkpoint"], "usage": {"estimated_tokens": 1}}

            def fail(name):
                def invoke(*_args):
                    calls.append(name)
                    raise RuntimeError(name)
                return invoke

            result = sweep.run_rationalization_backlog(
                project,
                log=log,
                codex_dir=False,
                complete_fn=lambda _prompt: "unused",
                rationalize_fn=fake_rationalize,
                reconcile_fn=fail("reconcile"),
                project_fn=fail("project"),
                render_fn=fail("render"),
                graph_store=object(),
                lentes_config={
                    "backfill_days": None, "max_sessions_per_sweep": 1,
                    "sweep_token_budget": 100, "scene_turn_limit": 40,
                },
            )
            self.assertEqual(calls, ["reconcile", "project", "render"])
            self.assertTrue(all(not leg["ok"] for leg in result["downstream"].values()))
            self.assertEqual(
                len(eventlog.read(types=["sessao.racionalizada"], log=log)), 1)

    def test_enqueue_uses_no_shell_nonblocking_systemd_with_short_timeout(self):
        calls = []

        def run_fn(argv, **kwargs):
            calls.append((argv, kwargs))
            return SimpleNamespace(returncode=0)

        self.assertTrue(sweep.enqueue_rationalization(run_fn=run_fn, timeout=2))
        self.assertEqual(calls, [(
            ["systemctl", "--user", "start", "--no-block", "edge-rationalize.service"],
            {"check": False, "capture_output": True, "text": True,
             "timeout": 2, "shell": False},
        )])

        self.assertFalse(sweep.enqueue_rationalization(
            run_fn=lambda *_args, **_kwargs: SimpleNamespace(returncode=1), timeout=1))


if __name__ == "__main__":
    unittest.main()
