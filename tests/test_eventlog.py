"""Tier-0 event log — the append-only source of truth (ADR-0006, issue #9).

The log is truth: `state/events/log.jsonl`, one JSON event per line, never mutated.
`direction_at` folds `direction.set` events to the plan as-of-a-cursor — deterministic
replay IS the strategic-versioning feature. These tests pin the append/read/fold core
(pure Python, no graph).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402


class AppendThenReadRoundTrips(unittest.TestCase):
    """The tracer bullet: an appended event lands as one JSONL line, stamped with a
    monotonic seq and an ISO ts, and reads back with its type/subject/payload intact."""

    def test_append_returns_and_reads_back_stamped_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "events" / "log.jsonl"
            ev = eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            self.assertEqual(ev["seq"], 1)
            self.assertEqual(ev["type"], "direction.set")
            self.assertEqual(ev["subject"], "direction")
            self.assertEqual(ev["payload"], {"plan": "X"})
            self.assertIn("ts", ev)
            self.assertEqual(eventlog.read(log=log), [ev])


class ReadReturnsEventsInSeqOrderFilteredByType(unittest.TestCase):
    """seq is monotonic across appends; read replays in order; `types=` keeps only those
    event types (issue #9 acceptance: read(types=["direction.set"]) returns both, in order)."""

    def test_monotonic_seq_and_type_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            eventlog.append("grill.curated", "term:foo", {"outcome": "renamed"}, log=log)
            eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            self.assertEqual([e["seq"] for e in eventlog.read(log=log)], [1, 2, 3])
            sets = eventlog.read(types=["direction.set"], log=log)
            self.assertEqual([e["payload"]["plan"] for e in sets], ["X", "Y"])
            self.assertEqual([e["seq"] for e in sets], [1, 3])


class LogOnlyEverGrows(unittest.TestCase):
    """Append-only by construction: every append extends the file; earlier bytes are never
    rewritten (issue #9 acceptance: the log file only ever grows)."""

    def test_existing_bytes_are_a_prefix_after_more_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            before = log.read_bytes()
            eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            after = log.read_bytes()
            self.assertTrue(after.startswith(before))
            self.assertGreater(len(after), len(before))


class ReadStopsAtACursor(unittest.TestCase):
    """A cursor bounds the replay: until_seq keeps events with seq<=n; until_ts keeps events
    with ts<=t. This bounded window is what direction_at folds to reconstruct a past state."""

    def test_until_seq_and_until_ts(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog.append("direction.set", "direction", {"plan": "X"}, log=log)
            b = eventlog.append("direction.set", "direction", {"plan": "Y"}, log=log)
            self.assertEqual([e["seq"] for e in eventlog.read(until_seq=1, log=log)], [1])
            self.assertEqual([e["seq"] for e in eventlog.read(until_seq=2, log=log)], [1, 2])
            self.assertEqual([e["seq"] for e in eventlog.read(until_ts=a["ts"], log=log)], [1])
            self.assertEqual([e["seq"] for e in eventlog.read(until_ts=b["ts"], log=log)], [1, 2])


class DirectionFoldsPerIdIntoTwoTiers(unittest.TestCase):
    """ADR-0007: direction.proposed/set/dropped fold per id into two tiers — `set` (curated, Voz)
    and `proposed` (non-curated, grill achados). set outranks proposed for the same id; dropped
    removes it (persist-until-dropped); replay to a past cursor reconstructs both tiers."""

    def test_two_tiers_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "explore X", log=log)
            eventlog.set_direction("b", "ship Y", log=log)
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["proposed"]], ["a"])
            self.assertEqual([i["id"] for i in d["set"]], ["b"])

    def test_set_outranks_proposed_same_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "maybe X", log=log)
            eventlog.set_direction("a", "X ratified", log=log)
            eventlog.propose("a", "waffle", log=log)  # cannot demote a set id
            d = eventlog.direction_at(log=log)
            self.assertEqual([i["id"] for i in d["set"]], ["a"])
            self.assertEqual(d["proposed"], [])

    def test_dropped_removes_and_stays_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.propose("a", "X", log=log)
            eventlog.drop("a", "noise", log=log)
            self.assertEqual(eventlog.direction_at(log=log), {"set": [], "proposed": []})

    def test_replay_to_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            p = eventlog.propose("a", "X", log=log)              # seq 1
            eventlog.set_direction("a", "X ratified", log=log)   # seq 2
            past = eventlog.direction_at(seq=p["seq"], log=log)
            self.assertEqual([i["id"] for i in past["proposed"]], ["a"])
            self.assertEqual(past["set"], [])
            self.assertEqual([i["id"] for i in eventlog.direction_at(log=log)["set"]], ["a"])

    def test_empty_log_has_no_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(eventlog.direction_at(log=Path(tmp) / "log.jsonl"))


class ProjectDirectionRendersBothTiers(unittest.TestCase):
    """The Direction page is a fold OUTPUT (ADR-0006/0007), banner-marked, with Set and Proposed
    sections; `from_artefato` provenance is shown. Projecting a past cursor writes that past."""

    def test_renders_both_tiers_marked_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.set_direction("b", "ship Y", kind="priority", log=log)
            eventlog.propose("c", "name the full-read budget", from_artefato="recall-report", log=log)
            eventlog.project_direction(log=log, out=out)
            text = out.read_text()
            self.assertIn("do not edit", text.lower())
            self.assertIn("## Set", text)
            self.assertIn("ship Y", text)
            self.assertIn("## Proposed", text)
            self.assertIn("name the full-read budget", text)
            self.assertIn("recall-report", text)  # provenance survives

    def test_projects_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "direction.md"
            eventlog.propose("a", "alpha", log=log)
            eventlog.set_direction("a", "omega", log=log)
            eventlog.project_direction(seq=1, log=log, out=out)
            text = out.read_text()
            self.assertIn("alpha", text)
            self.assertNotIn("omega", text)


class ArtefatoProposalsConsolidateIntoProposedTier(unittest.TestCase):
    """ADR-0007/#14: artefato.published declares `proposes`; consolidation fans each into the
    non-curated `proposed` tier with from_artefato provenance, idempotently (deterministic id);
    a dropped candidate is never resurrected."""

    def test_candidates_become_proposed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("recall-report", proposes=[
                {"body": "name the full-read budget", "kind": "constraint"},
                {"body": "watch read:write ratio"}], log=log)
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 2)
            prop = eventlog.direction_at(log=log)["proposed"]
            self.assertEqual({i["from_artefato"] for i in prop}, {"recall-report"})
            self.assertIn("name the full-read budget", [i["body"] for i in prop])
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 0)  # idempotent

    def test_dropped_candidate_not_resurrected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("r", proposes=[{"body": "X"}], log=log)
            eventlog.consolidate_artefato_proposals(log=log)
            eventlog.drop("r:0", "rejected", log=log)
            self.assertEqual(eventlog.consolidate_artefato_proposals(log=log), 0)
            self.assertEqual(eventlog.direction_at(log=log)["proposed"], [])


class IntentKernelPairsToItsArtefato(unittest.TestCase):
    """CONTRACT C3 / ADR-0009: every dispatch that produces an Artefato emits an `intent.kernel`
    event at close — the durable *why* (what is open, the next bet). It pairs to its Artefato by
    slug (subject `artefato:<slug>`), so the corpus fold can join published + kernel by slug."""

    def test_kernel_appends_intent_kernel_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.kernel("recall-report",
                                 "open: read-budget unnamed; bet: name it next beat", log=log)
            self.assertEqual(ev["type"], "intent.kernel")
            self.assertEqual(ev["subject"], "artefato:recall-report")
            self.assertEqual(ev["payload"]["slug"], "recall-report")
            self.assertIn("bet", ev["payload"]["intent"])
            self.assertEqual(eventlog.read(types=["intent.kernel"], log=log), [ev])


class ArtefatosWithoutKernelAreFlagged(unittest.TestCase):
    """The C3 invariant as a pure fold — "no Artefato closes without an intent.kernel" made
    mechanically checkable: `artefatos_without_kernel` returns published slugs that have no
    matching kernel, in publish order. A slug is cleared the moment its kernel is emitted."""

    def test_published_without_kernel_is_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("kerneled", log=log)
            eventlog.kernel("kerneled", "why", log=log)
            eventlog.publish_artefato("bare", log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), ["bare"])

    def test_clean_when_every_artefato_has_a_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("a", log=log)
            eventlog.kernel("a", "why a", log=log)
            self.assertEqual(eventlog.artefatos_without_kernel(log=log), [])


class CorpusFoldsPublishedArtefatosWithTheirWhy(unittest.TestCase):
    """ADR-0009: the corpus is a pure fold of `{artefato.published, intent.kernel}` paired by slug —
    the edge's own steps + their *why*. Each item carries slug, intent (from its kernel, None if none
    yet), the Artefato's proposes/distills/cites, and its published ts; in publish order. Cursor-aware:
    replaying to a past cursor reconstructs that past corpus (strategic versioning, as direction_at)."""

    def test_kernel_pairs_to_its_artefato_by_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("recall-report", proposes=[{"body": "name the budget"}],
                                      distills=["cluster:recall"], cites=["mundo:arxiv"], log=log)
            eventlog.kernel("recall-report", "open: budget unnamed; bet: name it next", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["recall-report"])
            self.assertEqual(corpus[0]["intent"], "open: budget unnamed; bet: name it next")
            self.assertEqual(corpus[0]["proposes"], [{"body": "name the budget"}])
            self.assertEqual(corpus[0]["distills"], ["cluster:recall"])
            self.assertEqual(corpus[0]["cites"], ["mundo:arxiv"])
            self.assertIn("ts", corpus[0])

    def test_artefato_without_kernel_folds_with_intent_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("bare", log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in corpus], ["bare"])
            self.assertIsNone(corpus[0]["intent"])

    def test_empty_log_has_empty_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(eventlog.corpus_at(log=Path(tmp) / "log.jsonl"), [])

    def test_replay_to_past_cursor_reconstructs_past_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            a = eventlog.publish_artefato("first", log=log)          # seq 1
            eventlog.kernel("first", "why first", log=log)           # seq 2
            eventlog.publish_artefato("second", log=log)             # seq 3
            past = eventlog.corpus_at(seq=a["seq"], log=log)
            self.assertEqual([c["slug"] for c in past], ["first"])
            self.assertIsNone(past[0]["intent"])                     # kernel not yet emitted at seq 1
            now = eventlog.corpus_at(log=log)
            self.assertEqual([c["slug"] for c in now], ["first", "second"])
            self.assertEqual(now[0]["intent"], "why first")


class ProjectCorpusInscribesEachStepsWhy(unittest.TestCase):
    """ADR-0009: state/corpus.md is the corpus projection — part of Memento's tattoo, the zero-memory
    agent reads it to know what it already did and *why*. A fold OUTPUT (banner-marked, never hand-
    edited): each Artefato's slug, its intent (the why), and its proposed steers. Most-recent-first.
    Projecting a past cursor writes that past corpus."""

    def test_renders_banner_marked_with_slug_why_and_proposes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "corpus.md"
            eventlog.publish_artefato("recall-report",
                                      proposes=[{"body": "name the full-read budget"}], log=log)
            eventlog.kernel("recall-report", "open: budget unnamed; bet: name it next beat", log=log)
            eventlog.project_corpus(log=log, out=out)
            text = out.read_text()
            self.assertIn("do not edit", text.lower())
            self.assertIn("recall-report", text)
            self.assertIn("open: budget unnamed; bet: name it next beat", text)  # the why is inscribed
            self.assertIn("name the full-read budget", text)                     # its proposed steer

    def test_projects_past_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            out = Path(tmp) / "corpus.md"
            eventlog.publish_artefato("alpha", log=log)
            eventlog.publish_artefato("omega", log=log)
            eventlog.project_corpus(seq=1, log=log, out=out)
            text = out.read_text()
            self.assertIn("alpha", text)
            self.assertNotIn("omega", text)


class CitesCarryOptionalSnippet(unittest.TestCase):
    """ADR-0009 source-feedback (hypothesis tier): a cite may carry the snippet the agent used —
    `{ref, kind, relevant, snippet}` — so embedding attribution can score snippet-vs-body. Back-
    compatible: a plain string cite (or a cite with no snippet) still round-trips and the corpus
    fold still reads `cites` verbatim — the new fields are never forced."""

    def test_snippetted_and_plain_cites_round_trip_through_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            cites = [{"ref": "github:abc123", "kind": "atividade", "relevant": True,
                      "snippet": "switched the cursor to a per-session watermark"},
                     "mundo:arxiv"]  # legacy plain cite, no snippet — must still work
            eventlog.publish_artefato("recall-report", cites=cites, log=log)
            corpus = eventlog.corpus_at(log=log)
            self.assertEqual(corpus[0]["cites"], cites)
            self.assertEqual(corpus[0]["cites"][0]["snippet"],
                             "switched the cursor to a per-session watermark")


class SourceSignalAppendsTheScore(unittest.TestCase):
    """ADR-0009: the hypothesis tier lands in the Tier-0 log as `source.signal` events — the
    *score* (similarity), never the vectors (no separate DB, no vector store). Payload pins the
    cited source (slug, ref, kind) so the yield fold can aggregate per source."""

    def test_source_signal_appends_event_with_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.source_signal("recall-report", "github:abc123", "atividade", 0.81, log=log)
            self.assertEqual(ev["type"], "source.signal")
            self.assertEqual(ev["payload"], {"slug": "recall-report", "ref": "github:abc123",
                                             "kind": "atividade", "similarity": 0.81})
            self.assertEqual(eventlog.read(types=["source.signal"], log=log), [ev])


class SourceYieldFoldsPerSourceCountAndMean(unittest.TestCase):
    """ADR-0009: the source-orientation leg the briefing reads and the grill consults — a pure fold
    of `source.signal` events into **per-source (ref) yield**: count + mean similarity, carrying
    kind. Cursor-aware (replay reconstructs a past yield); empty when there are no signals yet."""

    def test_aggregates_count_and_mean_per_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r1", "github:abc", "atividade", 0.8, log=log)
            eventlog.source_signal("r2", "github:abc", "atividade", 0.6, log=log)
            eventlog.source_signal("r1", "mundo:arxiv", "mundo", 0.4, log=log)
            y = eventlog.source_yield_at(log=log)
            self.assertEqual(y["github:abc"], {"ref": "github:abc", "kind": "atividade",
                                               "count": 2, "mean_similarity": 0.7})
            self.assertEqual(y["mundo:arxiv"], {"ref": "mundo:arxiv", "kind": "mundo",
                                                "count": 1, "mean_similarity": 0.4})

    def test_empty_when_no_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(eventlog.source_yield_at(log=Path(tmp) / "log.jsonl"), {})


class SourceFeedbackFoldsTwoTiersCuratedOverNonCurated(unittest.TestCase):
    """Slice 2 (ADR-0011): source feedback is two-tier, mirroring Direction (set over proposed).
    `source.curated` is the grill-distilled mentee opinion (curated tier); `source.signal` aggregates
    into the non-curated yield. `source_feedback_at` folds both, curated keyed per source, outranking
    the non-curated yield. `source.dropped` removes a curated entry (Voz-only). Cursor-aware: replay
    to a past cursor reconstructs that past — strategic versioning, as direction_at."""

    def test_curated_event_appends_and_folds_into_curated_tier(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = eventlog.source_curated("exa", "values exa for recent-paper recall", log=log)
            self.assertEqual(ev["type"], "source.curated")
            self.assertEqual(ev["payload"]["source"], "exa")
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            self.assertEqual(fb["curated"][0]["opinion"], "values exa for recent-paper recall")

    def test_curated_outranks_non_curated_yield_for_same_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "exa", "mundo", 0.7, log=log)         # non-curated yield
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)  # curated opinion
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            # the non-curated yield is still folded (a separate event, no promotion) but exa is curated
            self.assertIn("exa", fb["non_curated"])

    def test_dropped_removes_curated_entry_and_stays_gone(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "valued", log=log)
            eventlog.source_dropped("exa", "went cold", log=log)
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual(fb["curated"], [])

    def test_latest_curated_opinion_wins_per_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "first take", log=log)
            eventlog.source_curated("exa", "sharper take", log=log)
            fb = eventlog.source_feedback_at(log=log)
            self.assertEqual([c["source"] for c in fb["curated"]], ["exa"])
            self.assertEqual(fb["curated"][0]["opinion"], "sharper take")

    def test_replay_to_past_cursor_reconstructs_past_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            c = eventlog.source_curated("exa", "valued", log=log)        # seq 1
            eventlog.source_dropped("exa", "cold", log=log)              # seq 2
            past = eventlog.source_feedback_at(seq=c["seq"], log=log)
            self.assertEqual([x["source"] for x in past["curated"]], ["exa"])
            now = eventlog.source_feedback_at(log=log)
            self.assertEqual(now["curated"], [])

    def test_empty_log_has_empty_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            fb = eventlog.source_feedback_at(log=Path(tmp) / "log.jsonl")
            self.assertEqual(fb, {"curated": [], "non_curated": {}})


class CosineIsPureSimilarity(unittest.TestCase):
    """ADR-0009 source-feedback (hypothesis tier): cosine of two equal-length numeric vectors —
    the pure math behind embedding attribution (the actual OpenAI call lives in sweep, never here).
    Orthogonal → 0, identical → 1, a zero vector → 0.0 (no NaN — degrade, never crash)."""

    def test_orthogonal_identical_and_zero_vector(self):
        self.assertAlmostEqual(eventlog.cosine([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(eventlog.cosine([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertEqual(eventlog.cosine([0, 0], [1, 1]), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
