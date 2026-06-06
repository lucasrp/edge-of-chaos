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
    source_yield_at. "no source signals yet" when there are none."""

    def test_renders_yield_highest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "github:abc", "atividade", 0.9, log=log)
            eventlog.source_signal("r", "mundo:arxiv", "mundo", 0.3, log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("github:abc", text)
            self.assertIn("mundo:arxiv", text)
            self.assertLess(text.index("github:abc"), text.index("mundo:arxiv"))  # higher yield first

    def test_no_source_signals_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("no source signals yet", text.lower())


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
