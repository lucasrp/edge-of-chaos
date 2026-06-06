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


if __name__ == "__main__":
    unittest.main(verbosity=2)
