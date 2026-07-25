"""S-WIRE (conductor integration, Goal 3 slice 1) — the testable Python glue that bridges a
`run_conductor` result into the `_assembly` provenance the close re-verifies and signs.

The subagent FANNING is the skill/harness layer (the Python cannot dispatch a subagent, #40); what
IS unit-testable is the pure provenance computation:
  - `assembly.content_digest(spec)` — a stable digest of the conductor's conciliated content that
    IGNORES close-owned `_grounding` signatures (so the same content digests identically before and
    after close's `ground_visuals`, the H2 ordering fix).
  - `assembly.assembly_facts(result, seed)` — the `_assembly` dict the producer stamps onto the
    artefato: {assembled, node_count, seed_finding_count, conductor_ship, blocking, conductor_digest}.

These are the units S-WIRE owns; S-ATTEST's close-side re-verify reuses `content_digest`.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import assembly  # noqa: E402
import conductor  # noqa: E402


def _spec(text="alpha", with_grounding=False):
    block = {"type": "paragraph", "text": text}
    if with_grounding:
        block = {**block, "_grounding": "deadbeef-sig"}
    return {"sections": [{"title": "S", "blocks": [block]}]}


class TestContentDigest(unittest.TestCase):
    def test_stable_and_deterministic(self):
        self.assertEqual(assembly.content_digest(_spec()), assembly.content_digest(_spec()))

    def test_ignores_close_owned_grounding(self):
        # close's ground_visuals adds `_grounding` to blocks AFTER the conductor produced them;
        # the conductor-output digest must survive that additive mutation (H2).
        self.assertEqual(
            assembly.content_digest(_spec(with_grounding=False)),
            assembly.content_digest(_spec(with_grounding=True)),
        )

    def test_differs_on_real_content_change(self):
        self.assertNotEqual(assembly.content_digest(_spec("alpha")),
                            assembly.content_digest(_spec("beta")))

    def test_nested_non_block_grounding_is_content_not_stripped(self):
        # `_grounding` only as a BLOCK-level attestation is close-owned; a `_grounding` key nested in a
        # block's DATA is content — a change to it must move the digest (codex S-WIRE review, P2).
        a = {"sections": [{"blocks": [{"type": "chart", "data": {"_grounding": "X"}}]}]}
        b = {"sections": [{"blocks": [{"type": "chart", "data": {"_grounding": "Y"}}]}]}
        self.assertNotEqual(assembly.content_digest(a), assembly.content_digest(b))

    def test_block_level_grounding_still_stripped(self):
        bare = {"sections": [{"blocks": [{"type": "chart", "data": {"v": 1}}]}]}
        signed = {"sections": [{"blocks": [{"type": "chart", "data": {"v": 1}, "_grounding": "sig"}]}]}
        self.assertEqual(assembly.content_digest(bare), assembly.content_digest(signed))

    def test_nested_data_with_type_field_is_content_not_a_block(self):
        # codex edge case: a chart's nested data carrying its OWN `type` (+`_grounding`) is CONTENT, not a
        # section block. A change to it MUST move the digest — the strip is scoped to real section blocks.
        a = {"sections": [{"blocks": [{"type": "chart", "data": {"type": "line", "_grounding": "X"}}]}]}
        b = {"sections": [{"blocks": [{"type": "chart", "data": {"type": "line", "_grounding": "Y"}}]}]}
        self.assertNotEqual(assembly.content_digest(a), assembly.content_digest(b))

    def test_block_data_field_named_blocks_is_content(self):
        # codex edge case: a block whose DATA carries a field literally named `blocks` (with its own
        # `_grounding`) is CONTENT, not section blocks — the strip is scoped to sections[*].blocks[*] only,
        # so a change to that nested value MUST move the digest.
        a = {"sections": [{"blocks": [{"type": "custom", "data": {"blocks": [{"_grounding": "X"}]}}]}]}
        b = {"sections": [{"blocks": [{"type": "custom", "data": {"blocks": [{"_grounding": "Y"}]}}]}]}
        self.assertNotEqual(assembly.content_digest(a), assembly.content_digest(b))

    def test_additional_sections_blocks_also_stripped(self):
        bare = {"additional_sections": [{"blocks": [{"type": "chart", "data": {"v": 1}}]}]}
        signed = {"additional_sections": [{"blocks": [{"type": "chart", "data": {"v": 1}, "_grounding": "s"}]}]}
        self.assertEqual(assembly.content_digest(bare), assembly.content_digest(signed))


class TestAssemblyFacts(unittest.TestCase):
    def _result(self, *, enabled=True, ship=True, blocking=None, n_nodes=3, content=None):
        return {
            "enabled": enabled, "passthrough": not enabled,
            "content": content if content is not None else _spec(),
            "outline": [{"id": f"n{i}"} for i in range(n_nodes)],
            "ship": ship, "blocking": blocking or [],
        }

    def test_conductor_run_facts(self):
        seed = {"findings": [{"claim": "a"}, {"claim": "b"}]}
        result = self._result(n_nodes=4)
        facts = assembly.assembly_facts(result, seed)
        self.assertEqual(facts["assembled"], "conductor")
        self.assertEqual(facts["node_count"], 4)
        self.assertEqual(facts["seed_finding_count"], 2)
        self.assertTrue(facts["conductor_ship"])
        self.assertEqual(facts["blocking"], [])
        self.assertEqual(facts["conductor_digest"], assembly.content_digest(result["content"]))

    def test_blocking_run_carries_its_verdict(self):
        seed = {"findings": [{"claim": "a"}]}
        facts = assembly.assembly_facts(
            self._result(ship=False, blocking=["coherence:contradiction"]), seed)
        self.assertEqual(facts["assembled"], "conductor")
        self.assertFalse(facts["conductor_ship"])
        self.assertEqual(facts["blocking"], ["coherence:contradiction"])

    def test_seed_finding_count_zero(self):
        facts = assembly.assembly_facts(self._result(), {"findings": []})
        self.assertEqual(facts["seed_finding_count"], 0)

    def test_seed_collapse_warning_when_excavate_count_exceeds_seed(self):
        # Q6: a multi-finding excavate result collapsed to a smaller seed logs a soft (non-blocking) warning.
        seed = {"findings": [{"claim": "a"}], "excavate_finding_count": 5}
        facts = assembly.assembly_facts(self._result(), seed)
        self.assertEqual(facts["seed_collapse"], {"excavate": 5, "seed": 1})

    def test_no_seed_collapse_when_counts_match(self):
        seed = {"findings": [{"claim": "a"}, {"claim": "b"}], "excavate_finding_count": 2}
        facts = assembly.assembly_facts(self._result(), seed)
        self.assertNotIn("seed_collapse", facts)


class TestConductorBridgeContract(unittest.TestCase):
    """The contract S-WIRE relies on: the skill calls `node_briefs` to fan subagents, then
    `subagent_completer` to feed the collected prose back into `run_conductor`. Both call
    `author_outline` internally, so the bridge is sound ONLY if author_outline is deterministic on
    the same seed (R2 single-build identity) — characterized here so a future change can't silently
    break the exact-prompt match."""

    SEED = {"findings": [{"claim": "alpha bears on X"}, {"claim": "beta bears on Y"}]}
    OBJ = "a deep-dive objective"

    def test_author_outline_is_deterministic_on_same_seed(self):
        a = conductor.author_outline(self.SEED, self.OBJ)
        b = conductor.author_outline(self.SEED, self.OBJ)
        self.assertEqual([n["id"] for n in a], [n["id"] for n in b])
        self.assertEqual([n["contract"]["finding_ids"] for n in a],
                         [n["contract"]["finding_ids"] for n in b])

    def test_node_briefs_one_per_node_in_arc_order(self):
        briefs = conductor.node_briefs(self.SEED, self.OBJ)
        nodes = conductor.author_outline(self.SEED, self.OBJ)
        self.assertEqual([b["id"] for b in briefs], [n["id"] for n in nodes])
        self.assertTrue(all(b["prompt"] for b in briefs))

    def test_subagent_completer_round_trips_collected_prose(self):
        briefs = conductor.node_briefs(self.SEED, self.OBJ)
        outputs = {b["id"]: f"prose for {b['id']}" for b in briefs}
        complete_fn = conductor.subagent_completer(briefs, outputs)
        for b in briefs:
            self.assertEqual(complete_fn(b["prompt"]), f"prose for {b['id']}")

    def test_fewer_subagents_than_nodes_fails_loud(self):
        # R9/A4: the orchestration dispatched fewer subagents than nodes -> KeyError, never fabricate.
        briefs = conductor.node_briefs(self.SEED, self.OBJ)
        missing = briefs[0]["id"]
        outputs = {b["id"]: "prose" for b in briefs if b["id"] != missing}
        complete_fn = conductor.subagent_completer(briefs, outputs)
        with self.assertRaises(KeyError):
            complete_fn(briefs[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
