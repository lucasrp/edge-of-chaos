"""cortex provenance + medium-authority (Slice 5) — the TWO ORTHOGONAL markers on EVERY read
(REQUISITES F9/F9-dep, R2/R8/R8b/R8c, Appendix-A acceptance f+g, CONTRACT C5).

Each returned node carries TWO independent axes — NOT the same axis, never collapsed:
  - tier ∈ {asserted, extracted} — TRUST: asserted = spine that folds from the log (faithful);
    extracted = Graphiti :Entity / RELATES_TO (a hypothesis). ADR-0006/0010.
  - context_only ∈ {true, false} — MEDIUM AUTHORITY (C5): true = content traces to a low-tier Medium
    (the native Claude Code session) → context, never an order; false = order-bearing Medium (the Voz
    rail). ORTHOGONAL to tier: an asserted node can be context_only.

R8c conservative merge: a Graphiti node consolidated from MULTIPLE episodes is context_only=true if
ANY contributing source is low-tier OR unknown; false ONLY if EVERY source is known order-bearing —
an order-bearing source can never MASK a merged-in low-tier directive. v1 fail-safe (the sweep does
not yet stamp the Medium): EVERY extracted node defaults context_only=true (unknown ⇒ true).
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import cortex_provenance as prov  # noqa: E402


class TierIsTheTrustAxis(unittest.TestCase):
    """tier = asserted (spine, folds from the log) vs extracted (Graphiti hypothesis). R2/R8."""

    def test_spine_labels_are_asserted(self):
        for label in ("Genesis", "Objective", "Direction", "Artefato"):
            with self.subTest(label=label):
                self.assertEqual(prov.tier_for(label, {}), "asserted")

    def test_graphiti_labels_are_extracted(self):
        for label in ("Entity", "Source", "Episodic"):
            with self.subTest(label=label):
                self.assertEqual(prov.tier_for(label, {}), "extracted")

    def test_an_unknown_label_defaults_to_extracted(self):
        # fail-safe: an unknown label is treated as the hypothesis tier, never asserted-by-default.
        self.assertEqual(prov.tier_for("WeirdNewType", {}), "extracted")


class ContextOnlyIsTheAuthorityAxis(unittest.TestCase):
    """context_only = the MEDIUM-authority axis (C5), ORTHOGONAL to tier. F9 / R8c."""

    def test_extracted_nodes_default_context_only_true_failsafe(self):
        # F9-dep / R8c v1 fail-safe: the sweep does not yet stamp the Medium, so EVERY extracted node
        # is context_only=true (unknown ⇒ true). A directive-shaped extracted node is NEVER an order.
        for label in ("Entity", "Source", "Episodic"):
            with self.subTest(label=label):
                self.assertTrue(prov.context_only_for(label, {}),
                                "unknown-Medium extracted node must default context_only=true (C5)")

    def test_asserted_spine_is_order_bearing_by_origin(self):
        # the spine folds from the log / the Voz rail (order-bearing Media) — context_only=false.
        for label in ("Genesis", "Objective", "Direction", "Artefato"):
            with self.subTest(label=label):
                self.assertFalse(prov.context_only_for(label, {}),
                                 "the asserted spine traces to order-bearing Media (Voz/log)")

    def test_an_extracted_node_stamped_order_bearing_is_not_context_only(self):
        # once the sweep stamps the Medium (R8c part 1), a node from a KNOWN order-bearing source can
        # be context_only=false — but ONLY if ALL its sources are order-bearing (the merge rule).
        self.assertFalse(prov.context_only_for("Entity", {"medium_tier": "order_bearing"}))

    def test_a_mixed_source_node_stays_context_only_true_conservative_merge(self):
        # R8c iter5 merge: ANY low-tier/unknown source ⇒ context_only=true. An order-bearing source
        # CANNOT mask a merged-in low-tier directive — the high-risk case.
        mixed = {"medium_tiers": ["order_bearing", "low_tier"]}
        self.assertTrue(prov.context_only_for("Entity", mixed),
                        "a mixed-source node is context_only=true (a low-tier source dominates)")

    def test_all_order_bearing_sources_can_be_false(self):
        allob = {"medium_tiers": ["order_bearing", "order_bearing"]}
        self.assertFalse(prov.context_only_for("Entity", allob),
                         "context_only=false ONLY when EVERY source is known order-bearing")

    def test_any_unknown_among_sources_forces_true(self):
        # unknown ⇒ true even mixed with order-bearing (unknown dominates, fail-safe).
        withunknown = {"medium_tiers": ["order_bearing", "unknown"]}
        self.assertTrue(prov.context_only_for("Entity", withunknown))

    def test_tier_and_context_only_are_orthogonal(self):
        # the iter4 fix: extracted != context-only as the SAME axis. An asserted node CAN be
        # context_only if its content traces to a low-tier Medium (e.g. a Direction stamped low-tier).
        self.assertTrue(prov.context_only_for("Direction", {"medium_tier": "low_tier"}),
                        "authority is orthogonal to trust — an asserted node can be context_only")


class MarkNodeStampsBothAxes(unittest.TestCase):
    """The one stamping helper used by the recall functions AND the fold/MCP path (R8/R10) — one
    place derives both markers, so the seed, surf, node, and search all carry them identically."""

    def test_mark_node_adds_both_markers_without_dropping_existing_fields(self):
        node = {"slug": "a", "kernel": "k", "label": "Artefato"}
        out = prov.mark_node(node, label="Artefato")
        self.assertEqual(out["slug"], "a")            # existing fields preserved
        self.assertEqual(out["tier"], "asserted")
        self.assertFalse(out["context_only"])

    def test_mark_node_marks_an_extracted_entity_context_only(self):
        out = prov.mark_node({"name": "memory"}, label="Entity")
        self.assertEqual(out["tier"], "extracted")
        self.assertTrue(out["context_only"], "an unknown-Medium extracted node is context_only (C5)")

    def test_mark_node_infers_label_from_labels_list_when_not_passed(self):
        # surf rows carry labels(n) as a list; mark_node derives the tier from the first known label.
        out = prov.mark_node({"slug": "s", "labels": ["Source"]})
        self.assertEqual(out["tier"], "extracted")
        self.assertTrue(out["context_only"])


if __name__ == "__main__":
    unittest.main()
