"""cortex usage signal (Slice 3) — the implicit, OFF-TRUTH-PATH feedback + the EDGE_CORTEX_USAGE A/B
toggle + the ephemeral read-time re-rank (REQUISITES F7/N3/N4, glossary "Usage signal").

OFF (default): no telemetry write, no re-rank — a clean side-effect-free baseline.
ON: append {ts, tool, refs, run_id} to state/cortex/usage.jsonl (a SEPARATE, NON-AUTHORITATIVE store,
EXCLUDED from log replay and every fold) AND apply an ephemeral recency+frequency re-rank to
surf/search results, computed over PRIOR telemetry ONLY (the current write never affects its own
ordering — N3). Cold store → ON == OFF. The store is reconcilable-to-zero against the log (N4): it is
never self-state, never a graph write.
"""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_usage  # noqa: E402


class _TmpUsage(unittest.TestCase):
    """Each test gets an isolated usage store via EDGE_CORTEX_USAGE_PATH (the injectable store path),
    so no test ever touches the real state/cortex/usage.jsonl (truth-tree cleanliness)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name) / "usage.jsonl"
        os.environ["EDGE_CORTEX_USAGE_PATH"] = str(self.store)
        os.environ.pop("EDGE_CORTEX_USAGE", None)

    def tearDown(self):
        self.tmp.cleanup()
        for k in ("EDGE_CORTEX_USAGE", "EDGE_CORTEX_USAGE_PATH"):
            os.environ.pop(k, None)


class ToggleGatesTheWrite(_TmpUsage):
    """F7 — the toggle is the operator's A/B switch over the WRITE."""

    def test_off_is_the_default_and_writes_nothing(self):
        self.assertFalse(cortex_usage.enabled())
        cortex_usage.record("cortex_surf", ["a", "b"])
        self.assertFalse(self.store.exists(), "OFF must write no telemetry at all")

    def test_on_appends_one_line_per_read(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        self.assertTrue(cortex_usage.enabled())
        cortex_usage.record("cortex_surf", ["a", "b"], run_id="r1")
        cortex_usage.record("cortex_search", ["c"], run_id="r1")
        lines = self.store.read_text().strip().splitlines()
        self.assertEqual(len(lines), 2)
        rec = json.loads(lines[0])
        self.assertEqual(set(rec), {"ts", "tool", "refs", "run_id"})
        self.assertEqual(rec["tool"], "cortex_surf")
        self.assertEqual(rec["refs"], ["a", "b"])
        self.assertEqual(rec["run_id"], "r1")

    def test_on_with_no_refs_writes_nothing(self):
        # a read that surfaced nothing has no refs to reinforce — no empty line.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        cortex_usage.record("cortex_surf", [])
        self.assertFalse(self.store.exists())


class ReRankIsRecencyAndFrequency(_TmpUsage):
    """F7/R5/N3 — ON re-orders the SAME result set by a usage score over PRIOR telemetry; recency +
    frequency (a half-life decays a stale-hot ref), never a raw count. OFF leaves base order."""

    def _seed(self, ref, n, ago_s):
        # write n prior usages of `ref`, all `ago_s` seconds in the past.
        ts = time.time() - ago_s
        with self.store.open("a") as f:
            for _ in range(n):
                f.write(json.dumps({"ts": ts, "tool": "cortex_surf", "refs": [ref], "run_id": "x"}) + "\n")

    def test_off_leaves_base_order_untouched(self):
        results = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        self._seed("c", 10, ago_s=1)            # c is hot, but OFF must ignore it
        out = cortex_usage.rerank(results, key="slug")   # toggle OFF
        self.assertEqual([r["slug"] for r in out], ["a", "b", "c"])

    def test_on_promotes_a_ref_with_more_prior_usage(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        results = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        self._seed("c", 5, ago_s=1)             # c has frequent recent usage
        out = cortex_usage.rerank(results, key="slug")
        self.assertEqual(out[0]["slug"], "c", "a frequently/recently used ref sorts ahead")

    def test_recency_breaks_ties_against_frequency_via_a_half_life(self):
        # a stale-hot ref (many uses long ago) must decay below a fresh-warm ref (few uses just now).
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        results = [{"slug": "stale"}, {"slug": "fresh"}]
        self._seed("stale", 20, ago_s=30 * 24 * 3600)   # 20 uses, a month ago
        self._seed("fresh", 2, ago_s=1)                  # 2 uses, just now
        out = cortex_usage.rerank(results, key="slug")
        self.assertEqual(out[0]["slug"], "fresh",
                         "recency is first-class — a month-old hot ref decays below a fresh one")

    def test_cold_store_is_a_noop_on_equals_off(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        results = [{"slug": "a"}, {"slug": "b"}, {"slug": "c"}]
        out = cortex_usage.rerank(results, key="slug")   # no prior telemetry
        self.assertEqual([r["slug"] for r in out], ["a", "b", "c"],
                         "with no overlapping prior usage, ON == OFF (cold start)")

    def test_rerank_is_stable_for_unused_refs(self):
        # refs with equal (zero) usage keep their base relative order (a stable sort).
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        results = [{"slug": "a"}, {"slug": "b"}, {"slug": "d"}]
        self._seed("nonmatching", 5, ago_s=1)   # usage exists but for a ref not in the result set
        out = cortex_usage.rerank(results, key="slug")
        self.assertEqual([r["slug"] for r in out], ["a", "b", "d"])


class CorruptRecordsNeverBlockTheReadDoor(_TmpUsage):
    """C1/N4 hardening (codex Slice-3 [high]) — a JSON-valid but schema-CORRUPT telemetry line must
    never raise out of _scores/rerank: it is skipped, never a blocking dependency. The store stays
    reconcilable-to-zero telemetry, never the read door's failure mode."""

    def test_schema_corrupt_lines_are_skipped_not_raised(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        self.store.write_text(
            "[]\n"                                   # not a dict
            '"x"\n'                                   # a bare string
            '{"ts": "nope", "refs": ["a"]}\n'        # non-numeric ts
            '{"ts": 1, "refs": [{}]}\n'              # an unhashable ref (dict)
            '{"ts": 1, "refs": "a"}\n'               # refs not a list
            + json.dumps({"ts": time.time(), "refs": ["good"]}) + "\n"   # ONE valid line
        )
        # must not raise — and the one good ref still scores.
        scores = cortex_usage._scores()
        self.assertIn("good", scores)
        # rerank over a result set must also be total (no raise), promoting the valid ref.
        out = cortex_usage.rerank([{"slug": "x"}, {"slug": "good"}], key="slug")
        self.assertEqual(out[0]["slug"], "good")

    def test_a_deeply_nested_json_valid_line_does_not_raise(self):
        # codex Slice-3 [medium]: a JSON-valid but deeply-nested line can raise RecursionError on
        # parse — it must be skipped, never escape rerank. A later valid line still scores.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        nested = "[" * 4000 + "]" * 4000      # valid JSON, pathologically nested
        self.store.write_text(nested + "\n" + json.dumps({"ts": time.time(), "refs": ["good"]}) + "\n")
        out = cortex_usage.rerank([{"slug": "x"}, {"slug": "good"}], key="slug")  # must not raise
        self.assertEqual(out[0]["slug"], "good")

    def test_a_fully_corrupt_store_is_a_cold_noop(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        self.store.write_text("[]\n{}\nnotjson\n42\n")
        out = cortex_usage.rerank([{"slug": "a"}, {"slug": "b"}], key="slug")
        self.assertEqual([r["slug"] for r in out], ["a", "b"], "a corrupt store == cold == base order")

    def test_unhashable_result_refs_do_not_crash_rerank(self):
        # codex Slice-3 [medium]: a RESULT row whose rerank key is unhashable (list/dict) must not
        # crash rerank even with prior usage present — it scores 0, base order preserved, never raises.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        with self.store.open("w") as f:
            f.write(json.dumps({"ts": time.time(), "refs": ["b"], "run_id": "x"}) + "\n")
        results = [{"slug": []}, {"slug": {}}, {"slug": "b"}]   # two unhashable + one valid
        out = cortex_usage.rerank(results, key="slug")          # must not raise
        self.assertEqual(out[0]["slug"], "b", "the valid scored ref still ranks; bad rows score 0")


class WriteAndTimeHardening(_TmpUsage):
    """codex Slice-3 [medium] — symmetric write-side normalization + future-ts rejection."""

    def test_future_dated_usage_is_not_treated_as_fresh(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        with self.store.open("w") as f:
            f.write(json.dumps({"ts": time.time() + 3600, "refs": ["future"], "run_id": "x"}) + "\n")
        out = cortex_usage.rerank([{"slug": "a"}, {"slug": "future"}], key="slug")
        self.assertEqual([r["slug"] for r in out], ["a", "future"],
                         "a future-dated ts must be skipped, never lifted as fresh signal")

    def test_write_drops_non_string_and_oversized_refs(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        big = "x" * (cortex_usage.USAGE_MAX_REF_LEN + 10)
        cortex_usage.record("cortex_surf", ["ok", [], {}, big, ""])   # only "ok" survives
        rec = json.loads(self.store.read_text().strip())
        self.assertEqual(rec["refs"], ["ok"],
                         "write normalizes refs the same way the read scores (non-empty bounded str)")

    def test_write_drops_a_record_with_no_valid_refs(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        cortex_usage.record("cortex_surf", [[], {}, ""])   # nothing valid → no line
        self.assertFalse(self.store.exists())


class TruthPathIsolation(_TmpUsage):
    """N4 — the governance invariant: the usage store is NOT self-state. It lives off the eventlog,
    is reconcilable-to-zero, and the current call's own write never affects its own ordering."""

    def test_current_write_does_not_affect_its_own_ordering(self):
        # N3: rank reads telemetry written BEFORE this call; the append (record) happens AFTER ranking.
        # So ranking the SAME set twice in one run — record between — must be deterministic per the
        # PRIOR store, never self-referential.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        results = [{"slug": "a"}, {"slug": "b"}]
        first = cortex_usage.rerank(results, key="slug")     # cold → base order
        self.assertEqual([r["slug"] for r in first], ["a", "b"])
        cortex_usage.record("cortex_surf", ["b"])            # the write comes AFTER the rank
        # a SECOND rank now sees b's prior usage and promotes it — but the FIRST rank was unaffected.
        second = cortex_usage.rerank(results, key="slug")
        self.assertEqual(second[0]["slug"], "b")

    def test_usage_store_path_is_under_state_cortex_not_the_eventlog(self):
        # the default store is state/cortex/usage.jsonl — a SEPARATE store, never state/events/log.jsonl.
        os.environ.pop("EDGE_CORTEX_USAGE_PATH", None)
        p = cortex_usage.usage_path()
        self.assertEqual(p.parent.name, "cortex")
        self.assertEqual(p.parent.parent.name, "state")
        self.assertNotIn("events", str(p))
        self.assertEqual(p.name, "usage.jsonl")

    def test_eventlog_never_reads_the_usage_store(self):
        # the eventlog module must not reference the usage store (it is off the truth path, N4).
        import inspect
        import eventlog
        src = inspect.getsource(eventlog)
        self.assertNotIn("usage.jsonl", src, "the eventlog must never read the usage store (N4)")
        self.assertNotIn("cortex_usage", src)


class PathValidationFailsClosed(_TmpUsage):
    """N4 hardening (codex Slice-3 [high]) — the usage path can NEVER be the Tier-0 event log. A
    path pointing into state/events is REFUSED, so a mis-set env can't corrupt replay."""

    def test_a_path_under_state_events_is_refused(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        os.environ["EDGE_CORTEX_USAGE_PATH"] = str(REPO / "state" / "events" / "log.jsonl")
        # record must NOT write into the event log — it fails closed (telemetry disabled), never appends.
        before = (REPO / "state" / "events" / "log.jsonl")
        before_size = before.stat().st_size if before.exists() else 0
        cortex_usage.record("cortex_surf", ["a"])
        after_size = before.stat().st_size if before.exists() else 0
        self.assertEqual(before_size, after_size, "telemetry must NEVER append to the Tier-0 event log")

    def test_a_path_named_log_jsonl_under_events_is_refused_even_via_usage_path(self):
        os.environ["EDGE_CORTEX_USAGE_PATH"] = str(REPO / "state" / "events" / "anything.jsonl")
        with self.assertRaises(Exception):
            cortex_usage.usage_path()   # an events-dir path is rejected at resolution

    def test_any_foreign_state_events_path_is_refused_not_only_this_repo(self):
        # codex Slice-3 [medium]: the guard must reject ANY state/events target, including another
        # install's checkout outside this repo — not only REPO/state/events.
        os.environ["EDGE_CORTEX_USAGE_PATH"] = "/tmp/some-other-install/state/events/log.jsonl"
        with self.assertRaises(Exception):
            cortex_usage.usage_path()

    def test_a_hardlink_to_the_event_log_is_refused_by_samefile(self):
        # codex Slice-3 [high]: a hard link OUTSIDE state/events pointing at the same inode as the
        # Tier-0 log must still be refused (the segment guard alone misses it). Skips if hardlink unsupported.
        import eventlog
        log = Path(eventlog.LOG)
        if not log.exists():
            self.skipTest("no event log to hardlink in this checkout")
        link = Path(self.tmp.name) / "sneaky-usage.jsonl"
        try:
            os.link(log, link)
        except OSError:
            self.skipTest("hardlink not supported here")
        os.environ["EDGE_CORTEX_USAGE_PATH"] = str(link)
        with self.assertRaises(Exception):
            cortex_usage.usage_path()


class BoundedReadNeverBlocks(_TmpUsage):
    """C1/off-truth-path hardening (codex Slice-3 [medium]) — the re-rank reads only a BOUNDED recent
    tail, so a large append-only store never becomes the read door's blocking dependency."""

    def test_rerank_reads_only_a_bounded_tail(self):
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        # write FAR more than the cap; only the recent tail should inform the score.
        with self.store.open("w") as f:
            for i in range(cortex_usage.USAGE_READ_CAP + 5000):
                f.write(json.dumps({"ts": time.time(), "tool": "cortex_surf",
                                    "refs": [f"old-{i}"], "run_id": "x"}) + "\n")
            f.write(json.dumps({"ts": time.time(), "tool": "cortex_surf",
                                "refs": ["recent"], "run_id": "x"}) + "\n")
        scores = cortex_usage._scores()
        self.assertIn("recent", scores, "the most-recent line must be in the bounded tail")
        self.assertLessEqual(len(scores), cortex_usage.USAGE_READ_CAP + 1,
                             "the re-rank must not load the whole unbounded store")

    def test_tail_reader_returns_exactly_the_last_n_records(self):
        # the bounded tail reader (codex Slice-3 [high]): read backwards, return only the last N
        # lines, WITHOUT loading the whole file into memory.
        with self.store.open("w") as f:
            for i in range(100):
                f.write(f"line-{i}\n")
        tail = cortex_usage._read_tail_lines(self.store, 10)
        self.assertEqual(tail, [f"line-{i}" for i in range(90, 100)])

    def test_tail_reader_handles_a_file_shorter_than_the_cap(self):
        self.store.write_text("a\nb\nc\n")
        self.assertEqual(cortex_usage._read_tail_lines(self.store, 50), ["a", "b", "c"])

    def test_tail_reader_is_byte_bounded_against_a_pathological_single_line(self):
        # codex Slice-3 [high]: a corrupt/huge single line (no newlines) must NOT be read into memory
        # wholesale — the backward scan stops at the byte budget, returning a no-signal result.
        self.store.write_bytes(b"x" * (cortex_usage.USAGE_READ_BYTES + 5_000_000))
        tail = cortex_usage._read_tail_lines(self.store, cortex_usage.USAGE_READ_CAP)
        # bounded: it must not have accumulated more than the byte budget (+ one chunk slack)
        total = sum(len(l) for l in tail)
        self.assertLessEqual(total, cortex_usage.USAGE_READ_BYTES + 70000,
                             "the tail read must be byte-bounded, never load a pathological line whole")

    def test_record_caps_refs_per_line(self):
        # legitimate writes cannot create pathological lines: refs are capped per record.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        cortex_usage.record("cortex_surf", [f"r{i}" for i in range(10_000)])
        rec = json.loads(self.store.read_text().strip().splitlines()[0])
        self.assertLessEqual(len(rec["refs"]), cortex_usage.USAGE_MAX_REFS)

    def test_recent_line_wins_even_with_a_huge_prefix(self):
        # the actual harm case: a huge old prefix must NOT drown the recent tail's signal, AND the
        # read must stay bounded. The most-recent ref must score and rank.
        os.environ["EDGE_CORTEX_USAGE"] = "on"
        with self.store.open("w") as f:
            for i in range(cortex_usage.USAGE_READ_CAP + 2000):
                f.write(json.dumps({"ts": time.time() - 10 * 24 * 3600, "tool": "cortex_surf",
                                    "refs": ["ancient"], "run_id": "x"}) + "\n")
            f.write(json.dumps({"ts": time.time(), "tool": "cortex_surf",
                                "refs": ["b"], "run_id": "x"}) + "\n")
        out = cortex_usage.rerank([{"slug": "a"}, {"slug": "b"}], key="slug")
        self.assertEqual(out[0]["slug"], "b", "the fresh tail ref must rank despite a huge old prefix")


class HalfLifeConfigIsHardened(_TmpUsage):
    """R5 hardening (codex Slice-3 [medium]) — a bad EDGE_CORTEX_USAGE_HALFLIFE_S must never crash the
    import or invert recency; it falls back to the safe default."""

    def test_nonnumeric_zero_negative_halflife_fall_back_to_default(self):
        for bad in ("abc", "0", "-100", ""):
            with self.subTest(value=bad):
                os.environ["EDGE_CORTEX_USAGE_HALFLIFE_S"] = bad
                try:
                    hl = cortex_usage._halflife_s()
                    self.assertGreater(hl, 0, "a bad half-life must fall back to a positive default")
                finally:
                    os.environ.pop("EDGE_CORTEX_USAGE_HALFLIFE_S", None)

    def test_a_valid_halflife_is_honored(self):
        os.environ["EDGE_CORTEX_USAGE_HALFLIFE_S"] = "3600"
        try:
            self.assertEqual(cortex_usage._halflife_s(), 3600.0)
        finally:
            os.environ.pop("EDGE_CORTEX_USAGE_HALFLIFE_S", None)


if __name__ == "__main__":
    unittest.main()
