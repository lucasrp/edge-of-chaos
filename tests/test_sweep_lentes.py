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


def checkpoint(log, item, version="racionalizador-v1"):
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
                 "racionalizador_version": "racionalizador-v1",
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
