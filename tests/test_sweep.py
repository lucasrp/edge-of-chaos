"""sweep — the pull-at-open digestion sweep (ADR-0008, issue #15).

These pin the PURE half: cursor-guarded delta selection, idempotency, and the log/cursor
side effects of `execute` — with an injected fake `ingest_fn`, so no Neo4j or OpenAI is touched.
The Graphiti ingest + re-projection are exercised live in the deploy/verify step, not here.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import sweep      # noqa: E402
import eventlog   # noqa: E402

BODY = "a substantive design decision about the edge-next architecture and its direction " * 4


def write_session(d, sid, n_human=3, text=BODY):
    lines = []
    for i in range(n_human):
        lines.append(json.dumps({"type": "user", "message": {"content": f"{text} ({i})"}}))
        lines.append(json.dumps({"type": "assistant", "message": {"content": f"reply {i}: {text}"}}))
    p = Path(d) / f"{sid}.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return p


class PlanSweepSelectsDeltas(unittest.TestCase):
    """plan_sweep returns each session's new-since-cursor delta; a session already at its
    watermark plans nothing (idempotent); a thin delta is marked skip (left to grow)."""

    def test_new_session_then_idempotent_at_watermark(self):
        with tempfile.TemporaryDirectory() as proj:
            write_session(proj, "sessA")
            plan = sweep.plan_sweep(proj, {})
            self.assertEqual([p["id"] for p in plan], ["sessA"])
            self.assertFalse(plan[0]["skip"])
            self.assertEqual(sweep.plan_sweep(proj, {"sessA": plan[0]["watermark"]}), [])

    def test_thin_session_marked_skip(self):
        with tempfile.TemporaryDirectory() as proj:
            write_session(proj, "tiny", n_human=1, text="hi")
            plan = sweep.plan_sweep(proj, {})
            self.assertTrue(all(p["skip"] for p in plan))

    def test_large_delta_digested_in_full_not_capped(self):
        # a delta far over the old 12k cap must digest IN FULL — a head-cap silently drops the
        # most-recent turns while the cursor advances past them (data loss). No cap now.
        with tempfile.TemporaryDirectory() as proj:
            write_session(proj, "big", n_human=10, text="x" * 1500)   # ~30k+ chars of dialogue
            plan = sweep.plan_sweep(proj, {})
            body = plan[0]["body"]
            self.assertGreater(len(body), 20000, "delta must not be truncated to a fixed cap")
            self.assertIn("reply 9", body, "the most-recent turn must survive (a head-cap would drop it)")


class MalformedTranscriptLinesAreSkipped(unittest.TestCase):
    """A corrupt/truncated raw line (a session written mid-sweep, a crashed writer — the
    petertosh backfill hit one) must NOT kill the whole sweep: parseable turns are kept, the bad
    line is dropped as noise (the raw store stays non-lossy; the sweep just doesn't choke)."""

    def test_plan_survives_a_corrupt_line_and_keeps_valid_turns(self):
        with tempfile.TemporaryDirectory() as proj:
            p = write_session(proj, "sessA")
            lines = p.read_text().splitlines()
            lines.insert(1, '{"type": "user", "message": {"content": TRUNCATED')   # corrupt
            p.write_text("\n".join(lines) + "\n")
            plan = sweep.plan_sweep(proj, {})
            self.assertEqual([x["id"] for x in plan], ["sessA"])
            self.assertFalse(plan[0]["skip"])
            self.assertEqual(plan[0]["body"].count("human:"), 3,
                             "the valid turns around the corrupt line must survive")


class ExecuteIngestsLogsAdvances(unittest.TestCase):
    """execute ingests qualifying deltas (one episode event each), advances their cursors, and
    leaves thin deltas untouched (not ingested, cursor not advanced)."""

    def test_qualifying_ingested_and_cursor_advanced(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            log = Path(st) / "log.jsonl"
            seen = []
            cur, n = sweep.execute(sweep.plan_sweep(proj, {}),
                                   lambda items: seen.extend(i["id"] for i in items), {}, log=log)
            self.assertEqual((n, seen), (1, ["sessA"]))
            self.assertIn("sessA", cur)
            eps = eventlog.read(types=["episode"], log=log)
            self.assertEqual(len(eps), 1)
            self.assertEqual(eps[0]["payload"]["session"], "sessA")

    def test_thin_not_ingested_or_advanced(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "tiny", n_human=1, text="hi")
            log = Path(st) / "log.jsonl"
            seen = []
            cur, n = sweep.execute(sweep.plan_sweep(proj, {}),
                                   lambda items: seen.extend(i["id"] for i in items), {}, log=log)
            self.assertEqual((n, seen, cur), (0, [], {}))


class RunIsIdempotent(unittest.TestCase):
    """The whole-sweep guarantee: two back-to-back runs ingest the session once; the second is a
    no-op because the cursor advanced (re-running is safe under multiple triggers)."""

    def test_second_run_ingests_nothing(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"
            calls = []
            fake = lambda items: calls.append(len(items))
            n1 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log,
                          graph_recover_fn=False)
            n2 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log,
                          graph_recover_fn=False)
            self.assertEqual((n1, n2, calls), (1, 0, [1]))

    def test_growing_session_digests_only_new_delta(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"
            write_session(proj, "sessA")
            ingested = []
            fake = lambda items: ingested.append([i["id"] for i in items])
            sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log,
                          graph_recover_fn=False)
            # the session grows; a second sweep sees only the new tail
            write_session(proj, "sessA", n_human=6)  # rewrites longer (append-only in spirit)
            n2 = sweep.run(proj, ingest_fn=fake, cursors_path=cp, reproject_fn=False, log=log,
                          graph_recover_fn=False)
            self.assertEqual(n2, 1)  # the new delta re-qualified
            self.assertEqual(ingested, [["sessA"], ["sessA"]])

    def test_graph_recovery_runs_even_on_a_no_delta_sweep(self):
        # Codex P2: graph recovery is NOT gated by new ingest — a no-delta sweep (n==0) after Neo4j
        # comes back must still heal a publish-time-missed projection. The graph_recover_fn fires
        # regardless of `n`; reproject (the `if n` path) does not.
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"
            # no sessions → n == 0 (no delta)
            recovered = []
            n = sweep.run(proj, ingest_fn=lambda items: None, cursors_path=cp,
                          reproject_fn=False, log=log,
                          graph_recover_fn=lambda lg: recovered.append(lg))
            self.assertEqual(n, 0)             # no delta ingested
            self.assertEqual(recovered, [log])  # graph recovery ran, with the run's log threaded


class ReprojectFoldsCorpusAndReadsTheC3Gate(unittest.TestCase):
    """ADR-0009: reproject folds the corpus to state/corpus.md alongside Direction (pure, always —
    a log fold, so it runs Tier-0 with no graph), and finally gives the C3 gate a reader: it warns
    (non-fatal) about any published Artefato missing its intent.kernel — surfacing debt, not crashing.
    The eventlog projections are redirected to a temp log/out, and the graph wiki render is stubbed,
    so neither real state/ nor Neo4j is touched (CONTRACT C1)."""

    def _isolate(self, st):
        """Redirect eventlog's folds/projections to temp paths and stub the graph wiki render, so
        reproject() exercises the real corpus wiring + C3 read without writing real state/ or Neo4j."""
        self.log = Path(st) / "log.jsonl"
        self.corpus_out = Path(st) / "corpus.md"
        self.dir_out = Path(st) / "direction.md"
        o = self._orig
        eventlog.consolidate_artefato_proposals = lambda *a, **k: o["consolidate"](log=self.log)
        eventlog.project_direction = lambda *a, **k: o["direction"](log=self.log, out=self.dir_out)
        eventlog.project_corpus = lambda *a, **k: o["corpus"](log=self.log, out=self.corpus_out)
        eventlog.artefatos_without_kernel = lambda *a, **k: o["awk"](log=self.log)
        sweep.wiki_render = type("X", (), {"main": staticmethod(lambda *a, **k: None)})()
        # stub the graph reproject so the sweep test never touches Neo4j (CONTRACT C1, #30)
        import publisher
        publisher.reproject_graph = lambda *a, **k: None
        return self.log

    def setUp(self):
        import publisher
        self._orig = {"consolidate": eventlog.consolidate_artefato_proposals,
                      "direction": eventlog.project_direction,
                      "corpus": eventlog.project_corpus,
                      "awk": eventlog.artefatos_without_kernel,
                      "wiki": getattr(sweep, "wiki_render", None),
                      "reproject_graph": publisher.reproject_graph}

    def tearDown(self):
        import publisher
        o = self._orig
        eventlog.consolidate_artefato_proposals = o["consolidate"]
        eventlog.project_direction = o["direction"]
        eventlog.project_corpus = o["corpus"]
        eventlog.artefatos_without_kernel = o["awk"]
        if o["wiki"] is not None:
            sweep.wiki_render = o["wiki"]
        publisher.reproject_graph = o["reproject_graph"]

    def test_reproject_writes_corpus_md(self):
        with tempfile.TemporaryDirectory() as st:
            log = self._isolate(st)
            eventlog._append_orphan_published_for_test("recall-report",
                                      proposes=[{"body": "name the budget"}], log=log)
            eventlog.kernel("recall-report", "open: budget unnamed; bet: name it", log=log)
            sweep.reproject()
            text = self.corpus_out.read_text()
            self.assertIn("do not edit", text.lower())
            self.assertIn("recall-report", text)
            self.assertIn("open: budget unnamed; bet: name it", text)  # the why is inscribed

    def test_missing_kernel_warning_fires(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as st:
            log = self._isolate(st)
            eventlog._append_orphan_published_for_test("bare", log=log)  # published, no intent.kernel
            buf = io.StringIO()
            with redirect_stdout(buf):
                sweep.reproject()
            out = buf.getvalue()
            self.assertIn("bare", out)
            self.assertIn("C3", out)

    def test_no_warning_when_every_artefato_has_a_kernel(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as st:
            log = self._isolate(st)
            eventlog._append_orphan_published_for_test("a", log=log)
            eventlog.kernel("a", "why a", log=log)
            buf = io.StringIO()
            with redirect_stdout(buf):
                sweep.reproject()
            self.assertNotIn("C3", buf.getvalue())


class GraphIngestIsBestEffort(unittest.TestCase):
    """ADR-0006: the Tier-0 log is the source of truth. A graph ingest failure (no graphiti_core /
    Neo4j down on a fleet host like petertosh) is skipped, not fatal — episodes are still logged and
    cursors still advance, so digestion is current and the graph stays rebuildable from the log."""

    def test_ingest_failure_still_logs_and_advances(self):
        with tempfile.TemporaryDirectory() as proj, tempfile.TemporaryDirectory() as st:
            write_session(proj, "sessA")
            cp, log = Path(st) / "cursors.json", Path(st) / "log.jsonl"

            def boom(items):
                raise ModuleNotFoundError("No module named 'graphiti_core'")

            n = sweep.run(proj, ingest_fn=boom, cursors_path=cp, reproject_fn=False, log=log,
                          graph_recover_fn=False)
            self.assertEqual(n, 1)                                    # logged despite graph failure
            self.assertEqual(len(eventlog.read(types=["episode"], log=log)), 1)
            self.assertIn("sessA", sweep.load_cursors(cp))           # cursor advanced


class EmbedAndSignalScoresSnippettedCites(unittest.TestCase):
    """ADR-0009 source-feedback (hypothesis tier), the impure boundary: for each cite carrying a
    snippet, emit one `source.signal` scoring cosine(embed(snippet), embed(body)). `embed_fn` is
    injectable so this is testable on bare python3 with a fake embedder — no openai, no key."""

    def test_one_signal_per_snippetted_cite_with_right_similarity(self):
        with tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            vecs = {"BODY": [1.0, 0.0], "near": [1.0, 0.0], "far": [0.0, 1.0]}
            cites = [{"ref": "github:abc", "kind": "atividade", "snippet": "near"},
                     {"ref": "mundo:arxiv", "kind": "mundo", "snippet": "far"},
                     {"ref": "mundo:hn", "kind": "mundo"}]  # no snippet — skipped
            sweep.embed_and_signal("rep", "BODY", cites, embed_fn=lambda s: vecs[s], log=log)
            sigs = eventlog.read(types=["source.signal"], log=log)
            self.assertEqual([s["payload"]["ref"] for s in sigs], ["github:abc", "mundo:arxiv"])
            self.assertAlmostEqual(sigs[0]["payload"]["similarity"], 1.0)
            self.assertAlmostEqual(sigs[1]["payload"]["similarity"], 0.0)


class EmbedAndSignalDegradesWithoutEmbedder(unittest.TestCase):
    """Degrade-safe (the graphiti_ingest spirit, mirrored by GraphIngestIsBestEffort's injected
    `boom`): an unavailable embedder — no openai / no key, here simulated by an embedder that raises
    ModuleNotFoundError — makes `embed_and_signal` emit NOTHING and NOT raise, logging a skip line.
    The log stays current; embedding attribution is simply absent until a runtime is present.
    (Injected rather than relying on openai's absence — `embed_fn=None`'s live path is exercised in
    deploy/verify, not on bare python3, where openai/the key may in fact be present.)"""

    def test_unavailable_embedder_emits_nothing_and_does_not_raise(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as st:
            log = Path(st) / "log.jsonl"
            cites = [{"ref": "github:abc", "kind": "atividade", "snippet": "near"}]

            def unavailable(text):
                raise ModuleNotFoundError("No module named 'openai'")

            buf = io.StringIO()
            with redirect_stdout(buf):
                n = sweep.embed_and_signal("rep", "BODY", cites, embed_fn=unavailable, log=log)
            self.assertEqual(n, 0)
            self.assertEqual(eventlog.read(types=["source.signal"], log=log), [])
            self.assertIn("source.signal skipped", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
