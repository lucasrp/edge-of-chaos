"""grill_writeback's durable path — the grill always persists to the log (ADR-0006).

A grill that cannot reach Neo4j must still persist its decision: append_event lands the event
on the Tier-0 log via eventlog, with no graph/driver involved. The graph catches up later by
projection. This pins the stranded-grill fix (issue #9 item 3).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import grill_writeback  # noqa: E402


class AppendEventPersistsWithoutNeo4j(unittest.TestCase):
    """append_event delegates to the log (no driver), so a grill persists even offline-from-graph."""

    def test_grill_decision_lands_on_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            ev = grill_writeback.append_event("direction.set", "direction", {"plan": "Z"}, log=log)
            self.assertEqual(ev["type"], "direction.set")
            self.assertEqual(eventlog.read(types=["direction.set"], log=log)[0]["payload"],
                             {"plan": "Z"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
