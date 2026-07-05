"""Ticket D — acordar o semântico + as pontes Entity (docs/agencia/implementacao/02-D).

Three seams, one navigation win ("pra tudo se misturar"):
  1. `relate.sync` — the caller relate.py never had: nominate (mutual-kNN + relative floor)
     → route (NLI-first) → wipe-rebuild the cosine-nominated RELATES_TO edges between
     Artefatos, stamped provenance_class='extracted' (a navigable HYPOTHESIS — never
     aggregates, CX-1). Contradiction offers are RETURNED, never persisted (C2c).
  2. `relate.extract_mentions` / `relate.project_mentions` — MENTIONS extracted from the
     PUBLISHED TEXT itself at publish (the artefato DE FATO menciona → 'asserted'),
     conservative exact-name match against existing :Entity (sem fuzzy-inventivo — never
     fabricate a mention). Runs inside project_artefato's already-open session.
  3. the sweep caller — the semantic layer re-nominates on EVERY canonical sweep (the floor
     and the kNN are corpus-relative: periodic global recompute is the correct semantics);
     a non-canonical log (tests, dry-runs) NEVER touches the install graph.

All graph interaction is a fake session — no live neo4j in this suite (CONTRACT C1).
"""
import inspect
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_provenance  # noqa: E402
import relate  # noqa: E402


class FakeResult:
    def __init__(self, rows=None):
        self.rows = rows or []

    def data(self):
        return self.rows

    def single(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    """Records every (query, params) run; serves canned rows keyed by a substring match."""

    def __init__(self, rows_by_marker=None):
        self.calls = []
        self.rows_by_marker = rows_by_marker or {}

    def run(self, query, **params):
        self.calls.append((query, params))
        for marker, rows in self.rows_by_marker.items():
            if marker in query:
                return FakeResult(rows)
        return FakeResult()


class ExtractMentionsIsConservative(unittest.TestCase):
    """The guard-rail (spec 02-D): match é conservador — nome exato, word-boundary,
    case-insensitive; NUNCA fabricar menção (sem fuzzy/plural/substring)."""

    def test_exact_name_matches_case_insensitive(self):
        found = relate.extract_mentions(
            "The sweep hands the episode to Graphiti for extraction.", ["graphiti", "neo4j"])
        self.assertEqual(found, ["graphiti"])

    def test_substring_inside_a_word_never_matches(self):
        # "rag" lives inside "storage" — a word-boundary match must NOT see it.
        self.assertEqual(relate.extract_mentions("the storage layer", ["rag"]), [])

    def test_no_fuzzy_plural(self):
        # "graphiti" != "graphitis" — exact name only, never a stem/fuzzy expansion.
        self.assertEqual(relate.extract_mentions("all the graphitis", ["graphiti"]), [])

    def test_regex_metachars_in_names_are_escaped(self):
        found = relate.extract_mentions("served by node.js runtime", ["node.js"])
        self.assertEqual(found, ["node.js"])
        # the dot is a literal — "nodeXjs" must not match
        self.assertEqual(relate.extract_mentions("served by nodeXjs runtime", ["node.js"]), [])

    def test_short_names_are_skipped(self):
        # 1-2 char names ("ed", "AI") false-positive all over prose — conservador = skip.
        self.assertEqual(relate.extract_mentions("ed said AI is here", ["ed", "AI"]), [])

    def test_returns_graph_cased_names_deduped(self):
        found = relate.extract_mentions(
            "Neo4j here, neo4j there", ["Neo4j", "neo4j"])
        self.assertEqual(len(found), 1)  # one mention edge, whatever the case duplicates

    def test_degrades_on_empty_input(self):
        self.assertEqual(relate.extract_mentions("", ["graphiti"]), [])
        self.assertEqual(relate.extract_mentions("text", []), [])
        self.assertEqual(relate.extract_mentions(None, None), [])


class SyncMintsRelatesToAsExtractedHypotheses(unittest.TestCase):
    """relate.sync = the missing MERGE: nominate → route → RELATES_TO artefato↔artefato,
    provenance_class='extracted' (navigable hypothesis, never aggregates — CX-1)."""

    # a corpus where (a,b) are near-identical (mutual top-k, above any floor) and c is far.
    CORPUS = [("art-a", "kernel a", [1.0, 0.0, 0.0]),
              ("art-b", "kernel b", [0.999, 0.04, 0.0]),
              ("art-c", "kernel c", [0.0, 1.0, 0.0])]

    def test_sync_mints_the_mutual_pair_with_extracted_class(self):
        s = FakeSession()
        out = relate.sync(group="g1", corpus=self.CORPUS, session=s)
        self.assertEqual(out["minted"], [("art-a", "art-b")])
        merges = [(q, p) for q, p in s.calls if "MERGE" in q and "RELATES_TO" in q]
        self.assertEqual(len(merges), 1)
        q, p = merges[0]
        # deterministic direction: min slug -> max slug; reads stay direction-agnostic
        self.assertEqual((p["a"], p["b"]), ("art-a", "art-b"))
        # the plane comes through as an edge property — extracted, the CX-1 guard-rail
        self.assertEqual(p["pc"], "extracted")
        self.assertIn(":Artefato", q)

    def test_provenance_class_is_the_one_derivation_never_a_fork(self):
        # no-keyword-classifier cousin: the class is derived via cortex_provenance, not a literal fork
        src = inspect.getsource(relate.sync)
        self.assertIn("provenance_class_for", src,
                      "sync must derive the plane from cortex_provenance.provenance_class_for")
        self.assertEqual(cortex_provenance.provenance_class_for("relates_to"), "extracted")

    def test_wipe_rebuild_is_scoped_to_cosine_origin_and_runs_first(self):
        # the rebuild may ONLY touch its own edges: cosine-nominated Artefato↔Artefato —
        # never graphiti's Entity↔Entity RELATES_TO, never an author-confirmed edge.
        s = FakeSession()
        relate.sync(group="g1", corpus=self.CORPUS, session=s)
        deletes = [(i, q) for i, (q, _) in enumerate(s.calls)
                   if "DELETE" in q and "RELATES_TO" in q]
        self.assertEqual(len(deletes), 1)
        i, q = deletes[0]
        self.assertIn("cosine-nominated", q)
        self.assertEqual(q.count(":Artefato"), 2, "both endpoints scoped to :Artefato")
        first_merge = next(j for j, (mq, _) in enumerate(s.calls)
                           if "MERGE" in mq and "RELATES_TO" in mq)
        self.assertLess(i, first_merge, "the wipe precedes the rebuild")

    def test_minted_edges_carry_the_origin_marker(self):
        # the origin marker is what scopes the NEXT wipe — an unmarked edge would be orphaned
        s = FakeSession()
        relate.sync(group="g1", corpus=self.CORPUS, session=s)
        q, _ = next((q, p) for q, p in s.calls if "MERGE" in q and "RELATES_TO" in q)
        self.assertIn("cosine-nominated", q)

    def test_contradiction_offer_is_returned_never_minted(self):
        # C2c: the machine never auto-writes a directed claim — a calibrated contradiction
        # becomes an OFFER in the return, and the pair is NOT minted.
        s = FakeSession()
        nli = lambda a, b: {"label": "contradiction", "score": 0.9}  # noqa: E731
        out = relate.sync(group="g1", corpus=self.CORPUS, session=s, nli_fn=nli)
        self.assertEqual(out["minted"], [])
        self.assertEqual(len(out["offers"]), 1)
        self.assertEqual(out["offers"][0]["pair"], ("art-a", "art-b"))
        self.assertFalse([q for q, _ in s.calls if "MERGE" in q and "RELATES_TO" in q])

    def test_sync_degrades_dark(self):
        # CONTRACT C1: no group / raising session → None, never a raise.
        self.assertIsNone(relate.sync(group=None, corpus=self.CORPUS, session=FakeSession()))

        class Boom:
            def run(self, *a, **k):
                raise RuntimeError("graph down")
        self.assertIsNone(relate.sync(group="g1", corpus=self.CORPUS, session=Boom()))

    def test_thin_corpus_is_a_noop_not_a_crash(self):
        s = FakeSession()
        out = relate.sync(group="g1", corpus=[("only", "k", [1.0, 0.0])], session=s)
        self.assertEqual(out["minted"], [])
        # the wipe still runs: a corpus that SHRANK below 2 clears stale nominations honestly
        self.assertTrue([q for q, _ in s.calls if "DELETE" in q])


class ProjectMentionsWritesAssertedEdges(unittest.TestCase):
    """MENTIONS at publish: extracted from the published text, matched against EXISTING
    entities only, stamped 'asserted' (o artefato DE FATO menciona)."""

    ENTITIES = [{"name": "graphiti"}, {"name": "neo4j"}, {"name": "conductor"}]

    def test_matches_merge_with_asserted_class(self):
        s = FakeSession(rows_by_marker={":Entity": self.ENTITIES})
        n = relate.project_mentions(s, "g1", "my-slug", "graphiti feeds neo4j nightly")
        self.assertEqual(n, 2)
        merges = [(q, p) for q, p in s.calls if "MERGE" in q and "MENTIONS" in q]
        self.assertEqual(sorted(p["n"] for _, p in merges), ["graphiti", "neo4j"])
        for q, p in merges:
            self.assertEqual(p["pc"], "asserted")
        self.assertEqual(cortex_provenance.provenance_class_for("mentions"), "asserted")

    def test_old_artefato_mentions_cleared_before_rebuild(self):
        # a republish whose text dropped a mention must not strand the stale edge; the wipe is
        # scoped to THIS artefato's outgoing MENTIONS (episodic MENTIONS are graphiti's, untouched)
        s = FakeSession(rows_by_marker={":Entity": self.ENTITIES})
        relate.project_mentions(s, "g1", "my-slug", "only graphiti now")
        deletes = [(i, q) for i, (q, _) in enumerate(s.calls) if "DELETE" in q]
        self.assertEqual(len(deletes), 1)
        i, q = deletes[0]
        self.assertIn(":Artefato", q)
        self.assertIn("MENTIONS", q)
        first_merge = next(j for j, (mq, _) in enumerate(s.calls) if "MERGE" in mq)
        self.assertLess(i, first_merge)

    def test_no_matches_still_wipes_but_merges_nothing(self):
        s = FakeSession(rows_by_marker={":Entity": self.ENTITIES})
        n = relate.project_mentions(s, "g1", "my-slug", "nothing named here")
        self.assertEqual(n, 0)
        self.assertFalse([q for q, _ in s.calls if "MERGE" in q])
        self.assertTrue([q for q, _ in s.calls if "DELETE" in q])

    def test_never_raises_into_the_publish(self):
        class Boom:
            def run(self, *a, **k):
                raise RuntimeError("graph down")
        self.assertEqual(relate.project_mentions(Boom(), "g1", "s", "text"), 0)


class PublishAndSweepAreTheCallers(unittest.TestCase):
    """The fiação: publisher extracts MENTIONS at publish (inline, hot context — the offline
    curator was CUT by the operator); the sweep re-nominates the semantic layer every
    canonical run. Source-pinned like the house's other projection guarantees."""

    def test_project_artefato_extracts_mentions_from_the_published_text(self):
        import publisher
        src = inspect.getsource(publisher.project_artefato)
        self.assertIn("project_mentions", src,
                      "project_artefato must extract MENTIONS at publish (ticket D)")
        self.assertIn("emb_input", src[src.find("project_mentions"):][:200],
                      "mentions read the SAME published text the embedding reads")

    def test_sweep_renominated_on_canonical_log_only(self):
        import sweep

        calls = {"sync": 0, "publisher": 0}
        orig_sync = relate.sync
        import publisher
        orig_rg = publisher.reproject_graph
        relate.sync = lambda *a, **k: calls.__setitem__("sync", calls["sync"] + 1) or {
            "minted": [], "offers": []}
        publisher.reproject_graph = lambda *a, **k: calls.__setitem__(
            "publisher", calls["publisher"] + 1)
        try:
            import eventlog
            sweep.reproject_graph(log=eventlog.LOG)          # canonical → sync runs
            self.assertEqual(calls["sync"], 1)
            sweep.reproject_graph(log="/tmp/other-log.jsonl")  # custom → NEVER the install graph
            self.assertEqual(calls["sync"], 1)
            self.assertEqual(calls["publisher"], 2)  # graph recovery itself runs regardless
        finally:
            relate.sync = orig_sync
            publisher.reproject_graph = orig_rg

    def test_sweep_semantic_leg_is_best_effort(self):
        import sweep
        import publisher

        orig_sync, orig_rg = relate.sync, publisher.reproject_graph

        def boom(*a, **k):
            raise RuntimeError("relate leg down")
        relate.sync = boom
        publisher.reproject_graph = lambda *a, **k: None
        try:
            import eventlog
            sweep.reproject_graph(log=eventlog.LOG)  # must not raise
        finally:
            relate.sync = orig_sync
            publisher.reproject_graph = orig_rg


if __name__ == "__main__":
    unittest.main()
