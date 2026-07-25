"""eventlog.winning_manifest_rows — the ONE dedup/supersede + canary reader.

Deepening: it merged the near-identical logic that lived in both `fold_grounding` and
`grounding_yield._winners_and_canaries` (the 'must not drift' duplication). The existing
test_eventlog + test_grounding_yield suites guard the two call sites; this pins the helper's
own contract (E2b supersede rank + canary validation + corrupt tally).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog  # noqa: E402

# a valid raw_ref is the E2b 4-tuple: (session_id:str, line:int, tool_use_id:str, occ:int)
R1 = ("s", 10, "t1", 0)
R2 = ("s", 20, "t2", 0)


def _mani(ref, source, rev, seq, supersedes=None):
    p = {"raw_ref": list(ref), "source": source, "interface": "x",
         "recognizer_rev": rev, "hits": 3}
    if supersedes is not None:
        p["supersedes"] = list(supersedes)
    return {"type": "grounding.manifest", "payload": p, "seq": seq}


def _canary(source, ok, seq):
    return {"type": "canary.result",
            "payload": {"pass": ok, "source": source, "interface": "x"}, "seq": seq}


class WinningManifestRows(unittest.TestCase):
    def test_first_emission_wins_no_supersede(self):
        rows, canaries, corrupt = eventlog.winning_manifest_rows([_mani(R1, "exa", 1, 1)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1]["source"], "exa")
        self.assertEqual((canaries, corrupt), ([], 0))

    def test_higher_rev_supersede_wins(self):
        rows, _, _ = eventlog.winning_manifest_rows(
            [_mani(R1, "exa", 1, 1), _mani(R2, "twitter", 2, 5, supersedes=R1)])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1]["source"], "twitter")

    def test_lower_rev_supersede_never_defeats_healthier_original(self):
        rows, _, _ = eventlog.winning_manifest_rows(
            [_mani(R1, "exa", 2, 1), _mani(R2, "bad", 1, 5, supersedes=R1)])
        self.assertEqual(rows[0][1]["source"], "exa")

    def test_corrupt_manifest_counted_not_folded(self):
        rows, _, corrupt = eventlog.winning_manifest_rows(
            [{"type": "grounding.manifest", "payload": None, "seq": 1}])
        self.assertEqual((rows, corrupt), ([], 1))

    def test_valid_canary_parsed_invalid_counted_corrupt(self):
        rows, canaries, corrupt = eventlog.winning_manifest_rows(
            [_canary("exa", True, 1), _canary("", True, 2)])
        self.assertEqual(len(canaries), 1)
        self.assertTrue(canaries[0]["passed"])
        self.assertEqual(corrupt, 1)


if __name__ == "__main__":
    unittest.main()
