"""S-SPLITMERGE (conductor integration, Goal 3 slice 6) — the living-outline adjudication: merge
near-duplicate sibling deliver nodes, split an overflowing node. Pure + conservative (a no-op on a
varied, right-sized outline)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "tests"))
import conductor  # noqa: E402
from test_conductor_circuit_breaker import _SEED, _OBJECTIVE, _writer  # noqa: E402 — known-good harness


def _deliver(node_id, text, fids):
    return {"id": node_id, "role": "deliver", "status": "final",
            "contract": {"intent": "i", "finding_ids": list(fids)},
            "blocks": [{"type": "paragraph", "text": text}]}


class Merge(unittest.TestCase):
    def test_near_duplicate_deliver_siblings_merge_unioning_findings(self):
        a = _deliver("n-deliver-0", "The retrieval gate earns its cost at scale, as the evidence shows.", ["f0"])
        b = _deliver("n-deliver-1", "The retrieval gate earns its cost at scale, as the evidence shows!", ["f1"])
        out = conductor.merge_duplicate_nodes([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["contract"]["finding_ids"], ["f0", "f1"])   # no finding dropped
        self.assertEqual(out[0]["merged_from"], ["n-deliver-1"])
        # codex: the merged node KEEPS both nodes' blocks, so the unioned finding's claim/evidence (which
        # may have lived only in b's prose) survives for contract_gate/discharge — content never lost.
        self.assertEqual(len(out[0]["blocks"]), 2)

    def test_different_form_obligations_block_merge(self):
        # codex: near-identical prose but DIFFERENT structured-form obligations are NOT redundant — merging
        # would lose the merged-away finding's form contract, so they stay separate.
        a = _deliver("n-deliver-0", "The retrieval gate earns its cost at scale, as the evidence shows.", ["f0"])
        b = _deliver("n-deliver-1", "The retrieval gate earns its cost at scale, as the evidence shows!", ["f1"])
        a["target_form"] = ["comparison-table"]
        b["target_form"] = ["metrics-grid"]
        self.assertEqual(len(conductor.merge_duplicate_nodes([a, b])), 2)

    def test_distinct_deliver_nodes_are_not_merged(self):
        a = _deliver("n-deliver-0", "Latency falls because the cache is warm before the read.", ["f0"])
        b = _deliver("n-deliver-1", "Memory grows because nothing is evicted by default ever.", ["f1"])
        self.assertEqual(len(conductor.merge_duplicate_nodes([a, b])), 2)

    def test_frame_nodes_never_merge(self):
        # two motivate nodes with identical prose must NOT merge (only fanned deliver bodies collide).
        m1 = {"id": "n-motivate", "role": "motivate", "contract": {"finding_ids": []},
              "blocks": [{"type": "paragraph", "text": "Why this synthesis, why now."}]}
        m2 = {"id": "n-change", "role": "change-the-course", "contract": {"finding_ids": []},
              "blocks": [{"type": "paragraph", "text": "Why this synthesis, why now."}]}
        self.assertEqual(len(conductor.merge_duplicate_nodes([m1, m2])), 2)


class Split(unittest.TestCase):
    def test_overflowing_finding_less_node_splits_into_continuations(self):
        blocks = [{"type": "paragraph", "text": f"para {i}"} for i in range(conductor._NODE_MAX_BLOCKS + 3)]
        node = {"id": "n-deliver-0", "role": "deliver", "contract": {"finding_ids": []}, "blocks": blocks}
        parts = conductor.split_overflowing_node(node)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0]["id"], "n-deliver-0")
        self.assertEqual(parts[1]["id"], "n-deliver-0-cont1")
        self.assertEqual(sum(len(p["blocks"]) for p in parts), len(blocks))  # no block lost

    def test_overflowing_finding_owning_node_is_left_whole(self):
        # codex: never carve a finding-owning node across chunks — it would orphan the finding from its
        # claim echo and mis-fire contract_gate/discharge. One finding, one node.
        blocks = [{"type": "paragraph", "text": f"para {i}"} for i in range(conductor._NODE_MAX_BLOCKS + 3)]
        node = {"id": "n-deliver-0", "role": "deliver", "contract": {"finding_ids": ["f0"]}, "blocks": blocks}
        self.assertEqual(conductor.split_overflowing_node(node), [node])

    def test_right_sized_node_is_unchanged(self):
        node = _deliver("n-deliver-0", "fits", [])
        self.assertEqual(conductor.split_overflowing_node(node), [node])


class Adjudicate(unittest.TestCase):
    def test_no_op_on_a_varied_right_sized_outline(self):
        nodes = [
            {"id": "n-motivate", "role": "motivate", "contract": {"finding_ids": []},
             "blocks": [{"type": "paragraph", "text": "the frame"}]},
            _deliver("n-deliver-0", "Latency falls because the cache is warm.", ["f0"]),
            _deliver("n-deliver-1", "Memory grows because nothing evicts.", ["f1"]),
            {"id": "n-change", "role": "change-the-course", "contract": {"finding_ids": []},
             "blocks": [{"type": "paragraph", "text": "the next bet"}]},
        ]
        self.assertEqual(conductor.adjudicate_outline(nodes), nodes)


class FlagGatesTheLivePass(unittest.TestCase):
    def test_splitmerge_is_dark_by_default_and_opt_in(self):
        # the adjudication is UNCALIBRATED (over-merges shared-template prose), so it ships off; the live
        # pass runs only when the producer opts in with splitmerge=True.
        calls = []
        orig = conductor.adjudicate_outline
        conductor.adjudicate_outline = lambda nodes: (calls.append(1) or orig(nodes))
        try:
            conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True, splitmerge=False)
            self.assertEqual(calls, [])
            conductor.run_conductor(_SEED, _OBJECTIVE, _writer, is_enabled=True, splitmerge=True)
            self.assertEqual(calls, [1])
        finally:
            conductor.adjudicate_outline = orig


if __name__ == "__main__":
    unittest.main()
