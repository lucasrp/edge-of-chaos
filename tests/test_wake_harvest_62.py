"""edge-next #62 — identity precedes grounding, harvest is bounded/non-blocking/incremental.

The wake bug (#62): predispatch ran the O(store) harvest BEFORE stamping `dispatch.open` and
before the id was emitted, under a BLOCKING exclusive flock held across the whole walk, reading
every up-to-45MB transcript EVERY walk, flushing the cursor ONCE at the end — so a timeout lost
all progress, never stamped, and the wake never finished.

The fix, pinned here:
  - predispatch mints the id + stamps `dispatch.open` (identity-only) + writes DISPATCH_ID to the
    id_sink BEFORE any grounding leg; harvested/ambient_rows move to a separate `dispatch.grounding`
    event AFTER the stamp. A raising sweep/briefing writes NO id and no stamp.
  - harvest() takes the cursor lock NON-BLOCKING (dark-and-retry on contention), is BOUNDED by
    EDGE_HARVEST_BUDGET_S (fail-loud on a non-numeric budget), STAT-SKIPS unchanged files, and
    flushes the cursor INCREMENTALLY so a cap/crash keeps every completed file's watermark.

These tests use tmp stores/fixtures only — NEVER the real wake over ~/.claude.
"""
import contextlib
import fcntl
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog       # noqa: E402
import harvest        # noqa: E402
import predispatch    # noqa: E402


# --- store fixtures (the real transcript shape, mirrors test_harvest.py) ----------------------

X_STDOUT = '{"data":[{"id":"1","text":"t"}],"meta":{"newest_id":"1","result_count":4}}'
X_CMD = ('curl -s "https://api.twitter.com/2/tweets/search/recent?query=ai%20agents&max_results=10" '
         '-H "Authorization: Bearer $X_BEARER_TOKEN"')


def _tool_pair(sid, tuid, ts, command=X_CMD, name="Bash", inp=None, stdout=X_STDOUT):
    use = {"type": "assistant", "sessionId": sid, "timestamp": ts,
           "message": {"role": "assistant", "content": [
               {"type": "tool_use", "id": tuid, "name": name,
                "input": inp if inp is not None else {"command": command}}]}}
    res = {"type": "user", "sessionId": sid, "timestamp": ts,
           "message": {"role": "user", "content": [
               {"type": "tool_result", "tool_use_id": tuid, "content": stdout}]},
           "toolUseResult": {"stdout": stdout, "stderr": "", "interrupted": False}}
    return [use, res]


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o) + "\n" for o in lines))


def _many_files(store, n, mtime_base=1_700_000_000):
    """n one-row transcript files with DETERMINISTIC, distinct mtimes (os.utime)."""
    files = []
    for i in range(n):
        f = store / "-p" / f"s{i}.jsonl"
        _write(f, _tool_pair(f"s{i}", f"t{i}", "2026-07-01T10:00:00.000Z"))
        os.utime(f, (mtime_base + i, mtime_base + i))
        files.append(f)
    return files


def _tick_clock():
    """A fake time.monotonic: 1st call (the deadline base) = 0, then 1, 2, 3, ... — so with
    EDGE_HARVEST_BUDGET_S=3 the walk caps at the 4th loop-top check (3 files completed)."""
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return 0 if calls["n"] == 1 else calls["n"] - 1
    return fake


# =============================================================================================
# A — predispatch: identity precedes grounding
# =============================================================================================

class IdentityPrecedesGrounding(unittest.TestCase):
    def test_R1a_id_written_even_when_harvest_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()

            def boom():
                raise RuntimeError("store gone")

            with contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=boom,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1", id_sink=buf)
            self.assertIn("DISPATCH_ID=d1", buf.getvalue(),
                          "a raising harvest must NOT stop the id — it is written before grounding")
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_R1a_id_flushed_before_a_long_harvest_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()

            def slow():
                time.sleep(3.0)
                return 0

            t = threading.Thread(target=lambda: predispatch.run(
                sweep_fn=lambda: 0, briefing_fn=lambda: "B", recall_fn=lambda: "R",
                harvest_fn=slow, probe_fn=lambda s: True, log=log,
                dispatch_id="d1", id_sink=buf), daemon=True)
            with contextlib.redirect_stdout(io.StringIO()):
                t.start()
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline and "DISPATCH_ID=" not in buf.getvalue():
                    time.sleep(0.02)
            self.assertIn("DISPATCH_ID=d1", buf.getvalue(),
                          "the id must be flushed WELL before the 3s harvest returns")
            t.join(timeout=6)
            self.assertFalse(t.is_alive())

    def test_R1b_raising_sweep_writes_no_id_and_no_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()

            def loud():
                raise RuntimeError("transcript store not found")

            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=loud, briefing_fn=lambda: "B", recall_fn=lambda: "R",
                                harvest_fn=lambda: 0, probe_fn=lambda s: True, log=log,
                                dispatch_id="d1", id_sink=buf)
            self.assertEqual(buf.getvalue(), "", "a sweep that raises writes NO id")
            self.assertEqual(eventlog.read(types=["dispatch.open"], log=log), [],
                             "a dispatch that could not wake must not stamp")

    def test_R1b_raising_briefing_writes_no_id_and_no_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()

            def lobotomy():
                raise RuntimeError("BriefingIdentityError: thin agent.yaml")

            with self.assertRaises(RuntimeError), contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lobotomy, recall_fn=lambda: "R",
                                harvest_fn=lambda: 0, probe_fn=lambda s: True, log=log,
                                dispatch_id="d1", id_sink=buf)
            self.assertEqual(buf.getvalue(), "", "a briefing that raises writes NO id")
            self.assertEqual(eventlog.read(types=["dispatch.open"], log=log), [])

    def test_id_sink_carries_only_the_id_never_floor_noise(self):
        # the id sink is the REAL stream; floor legs print to the CAPTURED floor — no interleave
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            real_out, floor_out = io.StringIO(), io.StringIO()

            def noisy_harvest():
                print("harvest: some floor noise")
                return 0

            with contextlib.redirect_stdout(floor_out):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=noisy_harvest,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1",
                                id_sink=real_out)
            self.assertEqual(real_out.getvalue(), "DISPATCH_ID=d1\n",
                             "the id sink carries the id line and nothing else")
            self.assertIn("floor noise", floor_out.getvalue())

    def test_main_orders_the_id_before_all_floor_output(self):
        # main() captures real_out BEFORE redirect, passes it as id_sink, flushes floor AFTER
        def fake_run(id_sink=None, dispatch_id=None, **kw):
            if id_sink:
                id_sink.write(f"DISPATCH_ID={dispatch_id}\n")
                id_sink.flush()
            print("harvest leg DARK — floor noise")   # a grounding leg's stderr-ish floor print
            return "BRIEFING", "RECALL"

        buf = io.StringIO()
        with mock.patch.object(predispatch, "run", fake_run), contextlib.redirect_stdout(buf):
            predispatch.main([])
        lines = [l for l in buf.getvalue().splitlines() if l.strip()]
        self.assertTrue(lines[0].startswith("DISPATCH_ID="),
                        f"the machine-readable id must be FIRST on the real stream, got {lines[0]!r}")
        self.assertIn("harvest leg DARK — floor noise", lines,
                      "the floor noise is preserved, ordered after the id")


class GroundingCountsMovedToTheirOwnEvent(unittest.TestCase):
    def test_harvested_and_ambient_rows_are_on_dispatch_grounding_not_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            with contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=lambda: 7,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1")
            stamp = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertNotIn("harvested", stamp, "the stamp is identity-only now")
            self.assertNotIn("ambient_rows", stamp)
            g = eventlog.read(types=["dispatch.grounding"], log=log)
            self.assertEqual(len(g), 1)
            self.assertEqual(g[0]["payload"]["harvested"], 7)
            self.assertIn("ambient_rows", g[0]["payload"])
            self.assertEqual(g[0]["payload"]["dispatch_id"], "d1")

    def test_a_dark_harvest_still_emits_the_grounding_event_with_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def boom():
                raise RuntimeError("store gone")

            with contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=boom,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1")
            g = eventlog.read(types=["dispatch.grounding"], log=log)
            self.assertEqual(g[0]["payload"]["harvested"], 0)
            self.assertTrue(eventlog.wake_fresh(log=log))


# =============================================================================================
# B — harvest: bounded, non-blocking, incremental, stat-skip
# =============================================================================================

class HarvestLockIsNonBlocking(unittest.TestCase):
    def test_R2_held_lock_darks_and_returns_zero_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl", _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z"))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            cursors.parent.mkdir(parents=True, exist_ok=True)
            lock_path = cursors.with_name(cursors.name + ".lock")
            held = lock_path.open("w")
            fcntl.flock(held, fcntl.LOCK_EX)   # a second instance already holds the cursor lock
            try:
                err = io.StringIO()
                t0 = time.monotonic()
                with contextlib.redirect_stderr(err):
                    n = harvest.harvest(log=log, cursors_path=cursors, store_root=store)
                self.assertEqual(n, 0, "a contended harvest is DARK, not blocked")
                self.assertLess(time.monotonic() - t0, 5, "must NOT block on the held lock")
                self.assertIn("DARK", err.getvalue(), "the dark-and-retry is LOUD on stderr")
                self.assertEqual(eventlog.read(types=["grounding.manifest"], log=log), [],
                                 "the dark instance writes nothing")
            finally:
                fcntl.flock(held, fcntl.LOCK_UN)
                held.close()


class HarvestIsBudgetBounded(unittest.TestCase):
    def test_R2b_walk_stops_at_deadline_capped_loud_cursor_only_for_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _many_files(store, 6)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            out = io.StringIO()
            with mock.patch.dict(os.environ, {"EDGE_HARVEST_BUDGET_S": "3"}), \
                 mock.patch.object(harvest.time, "monotonic", _tick_clock()), \
                 contextlib.redirect_stdout(out):
                n = harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            self.assertIn("CAPPED", out.getvalue(), "the cap is LOUD")
            self.assertEqual(n, 3, "only the 3 completed files emitted")
            saved = json.loads(cursors.read_text())
            self.assertEqual(len(saved), 3, f"cursor advanced only for completed files, got {saved}")
            for v in saved.values():
                self.assertIsInstance(v, dict)
                self.assertIn("lines", v)

    def test_non_numeric_budget_fails_loud(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _write(store / "-p" / "s1.jsonl", _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z"))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            with mock.patch.dict(os.environ, {"EDGE_HARVEST_BUDGET_S": "soon"}):
                with self.assertRaises(ValueError):
                    harvest.harvest(log=log, cursors_path=cursors, store_root=store)


class HarvestResumesWithoutReappend(unittest.TestCase):
    def test_R4_partial_walk_cursors_completed_and_resume_does_not_reappend(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _many_files(store, 6)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            with mock.patch.dict(os.environ, {"EDGE_HARVEST_BUDGET_S": "3"}), \
                 mock.patch.object(harvest.time, "monotonic", _tick_clock()), \
                 contextlib.redirect_stdout(io.StringIO()):
                n1 = harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            self.assertEqual(n1, 3)
            self.assertEqual(len(json.loads(cursors.read_text())), 3, "K watermarks persisted")
            self.assertEqual(len(eventlog.read(types=["grounding.manifest"], log=log)), 3)
            # resume with the real clock (no cap): the 3 completed are stat-skipped, the rest emit
            with contextlib.redirect_stdout(io.StringIO()):
                n2 = harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            self.assertEqual(n2, 3, "the resume emits ONLY the not-yet-completed files")
            self.assertEqual(len(eventlog.read(types=["grounding.manifest"], log=log)), 6,
                             "no re-append of the already-cursored K files")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(harvest.harvest(log=log, cursors_path=cursors, store_root=store), 0,
                                 "a third run stat-skips everything")


class StatSkipAvoidsRereadingUnchangedFiles(unittest.TestCase):
    def test_only_the_changed_file_is_reread(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            fa = store / "-p" / "a.jsonl"
            fb = store / "-p" / "b.jsonl"
            fc = store / "-p" / "c.jsonl"
            _write(fa, _tool_pair("a", "ta", "2026-07-01T10:00:00.000Z"))
            _write(fb, _tool_pair("b", "tb", "2026-07-01T10:00:00.000Z"))
            _write(fc, _tool_pair("c", "tc", "2026-07-01T10:00:00.000Z"))
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            with contextlib.redirect_stdout(io.StringIO()):
                harvest.harvest(log=log, cursors_path=cursors, store_root=store)   # reads all 3
            # append one row to ONE file and bump its mtime deterministically
            with fb.open("a") as fh:
                for o in _tool_pair("b", "tb2", "2026-07-01T11:00:00.000Z"):
                    fh.write(json.dumps(o) + "\n")
            st = fb.stat()
            os.utime(fb, (st.st_mtime + 10, st.st_mtime + 10))
            # spy on _scan_file — only harvest() drives it here (session_floor, start=0, is untouched)
            seen = []
            orig = harvest._scan_file

            def spy(path, start, recognizers):
                seen.append(Path(path))
                return orig(path, start, recognizers)

            with mock.patch.object(harvest, "_scan_file", spy), \
                 contextlib.redirect_stdout(io.StringIO()):
                n = harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            self.assertEqual(seen, [fb], f"only the changed file is re-read, got {seen}")
            self.assertEqual(n, 1, "only the appended row is emitted; unchanged files not read")


class ConcurrentHarvestsEmitEachRowOnce(unittest.TestCase):
    def test_R5_R6_two_concurrent_harvests_one_walks_one_darks(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _many_files(store, 5)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            results = {}
            start = threading.Barrier(2)

            def worker(name):
                start.wait()
                # no stdout/stderr redirect in a thread (it is process-global) — noise is harmless
                results[name] = harvest.harvest(log=log, cursors_path=cursors, store_root=store)

            ts = [threading.Thread(target=worker, args=(f"w{i}",)) for i in range(2)]
            for t in ts:
                t.start()
            for t in ts:
                t.join(timeout=30)
            manifests = eventlog.read(types=["grounding.manifest"], log=log)
            self.assertEqual(len(manifests), 5, "each row emitted exactly once (one clean walk)")
            refs = [tuple(m["payload"]["raw_ref"]) for m in manifests]
            self.assertEqual(len(refs), len(set(refs)), "no duplicate raw_refs across the two")
            self.assertEqual(max(results.values()), 5, "the winner walked the whole store")


class CrashBetweenAppendAndFlushIsAbsorbed(unittest.TestCase):
    def test_R7_lost_cursor_after_append_reruns_to_the_single_clean_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "projects"
            _many_files(store, 3)
            log, cursors = Path(tmp) / "log.jsonl", Path(tmp) / "c.json"
            # crash: the cursor flush raises AFTER append_batch has landed events durably
            with mock.patch.object(harvest, "_write_cursors_atomic",
                                   side_effect=RuntimeError("killed mid-flush")), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            self.assertGreater(len(eventlog.read(types=["grounding.manifest"], log=log)), 0,
                               "the appends landed before the cursor flush died")
            self.assertFalse(cursors.exists(), "the cursor was never durably written")
            # re-run clean: the ranked/brute dedup absorbs the re-read
            with contextlib.redirect_stdout(io.StringIO()):
                harvest.harvest(log=log, cursors_path=cursors, store_root=store)
            refs = [tuple(m["payload"]["raw_ref"])
                    for m in eventlog.read(types=["grounding.manifest"], log=log)]
            self.assertEqual(len(refs), len(set(refs)), "no duplicate raw_refs after the re-run")
            self.assertEqual(len(refs), 3, "the final set == one clean walk")


class GroundingLegsNeverGateAStampedWake(unittest.TestCase):
    """#62 codex gate — a leg that is NOT sweep/briefing must never suppress or un-stamp the id."""

    def test_voz_dark_does_not_suppress_the_id(self):
        # voz annotates the briefing; it is NOT an identity viability gate. A raising voz must
        # degrade dark and the wake must still stamp + emit the id.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()
            with mock.patch("voz.brief", side_effect=RuntimeError("voz down")), \
                 contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=lambda: 0,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1", id_sink=buf)
            self.assertIn("DISPATCH_ID=d1", buf.getvalue(),
                          "voz is an annotation, not an identity gate — a raising voz must not stop the id")
            self.assertTrue(eventlog.wake_fresh(log=log))

    def test_voz_hang_does_not_delay_the_id(self):
        # not just a raise: a SLOW/hung voz must not delay the id either — voz runs AFTER the
        # stamp+emit, so the id is on the sink well before a 3s voz returns.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()

            def slow_voz(*a, **k):
                time.sleep(3.0)
                return ""

            with mock.patch("voz.brief", side_effect=slow_voz):
                t = threading.Thread(target=lambda: predispatch.run(
                    sweep_fn=lambda: 0, briefing_fn=lambda: "B", recall_fn=lambda: "R",
                    harvest_fn=lambda: 0, probe_fn=lambda s: True, log=log,
                    dispatch_id="d1", id_sink=buf), daemon=True)
                with contextlib.redirect_stdout(io.StringIO()):
                    t.start()
                    deadline = time.monotonic() + 1.5
                    while time.monotonic() < deadline and "DISPATCH_ID=" not in buf.getvalue():
                        time.sleep(0.02)
                self.assertIn("DISPATCH_ID=d1", buf.getvalue(),
                              "the id must be flushed WELL before the 3s voz returns")
                t.join(timeout=6)
                self.assertFalse(t.is_alive())

    def test_grounding_annotation_dark_does_not_gate_a_stamped_wake(self):
        # the dispatch.grounding summary append runs AFTER the id is durable; if it raises, the
        # wake must not un-stamp or propagate — grounding never gates (only the counts are lost).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            buf = io.StringIO()
            real_append = eventlog.append

            def flaky(kind, *a, **k):
                if kind == "dispatch.grounding":
                    raise RuntimeError("annotation store wedged")
                return real_append(kind, *a, **k)

            with mock.patch.object(eventlog, "append", side_effect=flaky), \
                 contextlib.redirect_stdout(io.StringIO()):
                predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B",
                                recall_fn=lambda: "R", harvest_fn=lambda: 0,
                                probe_fn=lambda s: True, log=log, dispatch_id="d1", id_sink=buf)
            self.assertIn("DISPATCH_ID=d1", buf.getvalue())
            self.assertTrue(eventlog.wake_fresh(log=log),
                            "a failed grounding annotation must not un-stamp a woken dispatch")

    def test_nonfinite_or_negative_budget_fails_loud(self):
        # nan/inf/negative would make `time.monotonic() > deadline` never trip → the walk goes
        # unbounded again (the #62 hang). Each must fail LOUD, never silently un-cap.
        for bad in ("nan", "inf", "-1"):
            with self.subTest(budget=bad), tempfile.TemporaryDirectory() as tmp:
                store = Path(tmp) / "projects"
                _write(store / "-p" / "s1.jsonl", _tool_pair("s1", "t1", "2026-07-01T10:00:00.000Z"))
                with mock.patch.dict(os.environ, {"EDGE_HARVEST_BUDGET_S": bad}):
                    with self.assertRaises(ValueError):
                        harvest.harvest(log=Path(tmp) / "log.jsonl",
                                        cursors_path=Path(tmp) / "c.json", store_root=store)


if __name__ == "__main__":
    unittest.main(verbosity=2)
