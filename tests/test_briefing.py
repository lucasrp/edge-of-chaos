"""briefing — the deterministic composer of Memento's tattoo (ADR-0009, issue capstone).

The agent has anterograde amnesia: it orients **entirely** from the briefing and trusts
nothing that isn't inscribed there. So the load-bearing lines (the curated Direction, what is
open / the next bet, the source yield, what it already did) are **deterministically inscribed
from the log** — only the Recap is synthesized fresh. These tests pin that composition on bare
`python3` (Tier-0, no graph), each from a throwaway temp log (CONTRACT C1 — never real state/).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import briefing  # noqa: E402


class DirectionInscribedCuratedFirst(unittest.TestCase):
    """Section 1 (highest tattoo authority): the curated `set` tier is inscribed before the
    non-curated `proposed` tier; both bodies appear. None → "no direction set yet."""

    def test_set_appears_before_proposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("a", "ship the briefing composer", log=log)
            eventlog.propose("b", "explore Tier-1 clusters", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("ship the briefing composer", text)
            self.assertIn("explore Tier-1 clusters", text)
            self.assertLess(text.index("ship the briefing composer"),
                            text.index("explore Tier-1 clusters"))

    def test_no_direction_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("no direction set yet", text.lower())


class ContinuityInscribesTheLatestKernel(unittest.TestCase):
    """Section 2 — the literal tattoo: a cold agent reads here what it was mid-doing. Derived from
    the *intent* (the why) of the most-recent corpus item — publish an artefato + kernel and the
    kernel's "what is open / next bet" must appear under the open/next-bet section."""

    def test_latest_kernel_intent_is_the_open_next_bet(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("recall-report", log=log)
            eventlog.kernel("recall-report",
                            "open: read-budget unnamed; bet: name it next beat", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("open / the next bet", text.lower())
            self.assertIn("open: read-budget unnamed; bet: name it next beat", text)

    def test_most_recent_kernel_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("older", log=log)
            eventlog.kernel("older", "old intent", log=log)
            eventlog.publish_artefato("newer", log=log)
            eventlog.kernel("newer", "fresh intent — the live continuity", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("fresh intent — the live continuity", text)


class CorpusListsRecentStepsAndC3Debt(unittest.TestCase):
    """Section 3 — what I already did: recent Artefato slugs (+ their why), most-recent-first, so
    the agent builds rather than repeats. A kernel-less Artefato is surfaced as C3 debt (the gap is
    shown, not hidden) via artefatos_without_kernel."""

    def test_recent_slugs_most_recent_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("older-report", log=log)
            eventlog.kernel("older-report", "why older", log=log)
            eventlog.publish_artefato("newer-report", log=log)
            eventlog.kernel("newer-report", "why newer", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("older-report", text)
            self.assertIn("newer-report", text)
            self.assertLess(text.index("newer-report"), text.index("older-report"))

    def test_kernel_less_artefato_shows_as_c3_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.publish_artefato("bare-report", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("bare-report", text)
            self.assertIn("C3 debt", text)


class SourceOrientationRendersYield(unittest.TestCase):
    """Section 4 — per-source yield (ref · kind · count · mean sim), highest yield first, from
    source_yield_at, layered ON the declared roster floor."""

    def test_renders_yield_highest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "github:abc", "atividade", 0.9, log=log)
            eventlog.source_signal("r", "mundo:arxiv", "mundo", 0.3, log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("github:abc", text)
            self.assertIn("mundo:arxiv", text)
            self.assertLess(text.index("github:abc"), text.index("mundo:arxiv"))  # higher yield first


class SourceRosterIsTheNeverBlankFloor(unittest.TestCase):
    """Slice 1 (ADR-0011): the source section renders the declared roster (← Source roadmap, seeded
    from agent.yaml) as the floor that is **never blank**, even with zero source.signal events. The
    old "no source signals yet" blank is the bug this fixes. Per-entry label: description→via→name."""

    def test_roster_floor_lists_entries_when_log_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            roster = [{"name": "exa", "kind": "api", "label": "exa"},
                      {"name": "github", "kind": "cli", "label": "github"}]
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", roster=roster)
            self.assertNotIn("no source signals yet", text.lower())
            self.assertIn("exa", text)
            self.assertIn("github", text)

    def test_source_roster_helper_reads_agent_yaml_and_native_source(self):
        roster = briefing.source_roster()
        names = [r["name"] for r in roster]
        self.assertIn("exa", names)        # from agent.yaml sources:
        self.assertIn("github", names)     # the cli source
        # the native Claude-sessions source is a constant floor entry, always present
        self.assertTrue(any("session" in r["name"].lower() for r in roster))

    def test_label_fallback_chain_description_then_via_then_name(self):
        roster = [{"name": "s1", "kind": "api", "label": "a transcript on the Drive"},  # description
                  {"name": "s2", "kind": "api", "label": "GET https://api…"},            # via
                  {"name": "s3", "kind": "api", "label": "s3"}]                           # bare name
        text = briefing.compose_briefing(log=Path("/nonexistent"), roster=roster)
        self.assertIn("a transcript on the Drive", text)
        self.assertIn("GET https://api", text)
        self.assertIn("s3", text)


class SourceCuratedStratumRendersAboveYield(unittest.TestCase):
    """Slice 2 (ADR-0011): the curated source stratum (← source.curated, the grill-distilled mentee
    opinion) renders ABOVE the non-curated yield, mirroring _section_direction (set over proposed).
    source.dropped removes it. Cursor-aware: a past cursor reconstructs the past stratum."""

    def test_curated_opinion_surfaces_above_the_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "exa", "mundo", 0.7, log=log)
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("valued: recent-paper recall", text)
            # curated stratum is above the per-source yield line
            self.assertLess(text.index("valued: recent-paper recall"),
                            text.index("mean sim"))

    def test_dropped_removes_curated_from_briefing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)
            eventlog.source_dropped("exa", "went cold", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertNotIn("valued: recent-paper recall", text)

    def test_replay_to_past_cursor_shows_past_curated_stratum(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            c = eventlog.source_curated("exa", "valued: recall", log=log)   # seq 1
            eventlog.source_dropped("exa", "cold", log=log)                 # seq 2
            past = briefing.compose_briefing(log=log, seq=c["seq"])
            self.assertIn("valued: recall", past)
            now = briefing.compose_briefing(log=log)
            self.assertNotIn("valued: recall", now)


class ClustersDegradeOnTier0(unittest.TestCase):
    """Section 5 — Knowledge clusters (← graph). clusters=None (Tier-0, no graph runtime) → a clear
    degrade note, and it must NOT crash. clusters=[...] (Tier-1) → they render."""

    def test_none_renders_tier0_degrade_note_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=None)
            self.assertIn("Tier-0", text)
            self.assertIn("clusters unavailable", text.lower())

    def test_provided_clusters_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl",
                                             clusters=["recall budget", "source feedback"])
            self.assertIn("recall budget", text)
            self.assertIn("source feedback", text)


class RecapSlotOrInscribedText(unittest.TestCase):
    """Section 6 — Recap (← corpus, synthesized fresh). recap=None → a clear slot marker so the
    assemble LLM fills it; recap="..." → the text is inscribed verbatim."""

    def test_none_renders_slot_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", recap=None)
            self.assertIn("Recap synthesized at compose-time", text)

    def test_recap_text_is_inscribed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl",
                recap="Your recall-report relates to the mentee's cursor refactor commit.")
            self.assertIn("Your recall-report relates to the mentee's cursor refactor commit.", text)


class BriefingIsBannered(unittest.TestCase):
    """The whole tattoo is banner-marked as generated orientation (house style — the projections
    in eventlog.py carry the same do-not-edit banner)."""

    def test_banner_marks_generated_orientation(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("generated", text.lower())


class FactsLegNavigatesTheCortex(unittest.TestCase):
    """Section 5 (ADR-0011) — the Facts leg navigates the graph for grill-curated Knowledge
    clusters. graph_clusters degrades to None (never crashes) without a group, without the neo4j
    driver, or when the graph is unreachable; [] is the honest 'graph up, none yet' state distinct
    from the outage note. Hermetic: no group / a dead port → never touches real state (CONTRACT C1)."""

    def test_no_group_degrades_to_none(self):
        self.assertIsNone(briefing.graph_clusters(None))
        self.assertIsNone(briefing.graph_clusters(""))

    def test_unreachable_graph_degrades_to_none_without_crashing(self):
        # dead port → connection error inside the leg → None, never an exception
        self.assertIsNone(briefing.graph_clusters("any-group", uri="bolt://127.0.0.1:1"))

    def test_empty_clusters_is_a_distinct_state_from_outage(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=[])
            self.assertIn("no curated clusters yet", text.lower())
            self.assertNotIn("clusters unavailable", text.lower())

    def test_auto_fetch_with_no_group_renders_the_degrade_note(self):
        # the sentinel path resolves group→graph_clusters→None when no group is declared
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", group="")
            self.assertIn("clusters unavailable", text.lower())

    def test_provided_clusters_with_counts_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl",
                                             clusters=["Beat lifecycle (8)", "Dev practice (6)"])
            self.assertIn("Beat lifecycle (8)", text)
            self.assertIn("Dev practice (6)", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
