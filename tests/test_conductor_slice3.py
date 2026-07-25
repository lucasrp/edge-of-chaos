"""Slice 3 (plan-then-write) — kill structural monotony (D-A) at the SOURCE + reconcile gaps (D-B).
Unit-level, deterministic, no model calls:
  - per-finding form routing + sibling DE-COLLISION (distinct forms across siblings — the D-A crux);
  - the GLOBAL VISUAL INVARIANT (no chart/diagram in any target_form) + the post-fill form gate that
    drops out-of-form and drawn-visual blocks (empty -> flagged, never faked);
  - deterministic gap dedup -> ONE consolidated gap-table (D-B);
  - the distinct-signature diversity gate (fails on all-identical, passes on varied)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import conductor  # noqa: E402
import close      # noqa: E402
import render     # noqa: E402


class FormRouting(unittest.TestCase):
    def test_probe_routes(self):
        self.assertEqual(conductor._route_form({"probe": "surprise"}), "comparison-table")
        self.assertEqual(conductor._route_form({"probe": "contradiction"}), "comparison-table")
        self.assertEqual(conductor._route_form({"probe": "lineage"}), "derivation")

    def test_numeric_dense_claim_routes_metrics_grid(self):
        f = {"claim": "lag hit 200ms at 50 entities, 3x slower", "probe": "relevance"}
        self.assertEqual(conductor._route_form(f), "metrics-grid")

    def test_before_after_routes_diff_block(self):
        f = {"claim": "the gate was advisory before the rewrite and blocking after", "probe": "relevance"}
        self.assertEqual(conductor._route_form(f), "diff-block")

    def test_numeric_before_after_prefers_diff_block(self):
        # codex P3: a before/after claim that is ALSO numeric-dense routes to diff-block, not metrics-grid.
        f = {"claim": "latency was 200ms before and 80ms after the rewrite", "probe": "relevance"}
        self.assertEqual(conductor._route_form(f), "diff-block")

    def test_compare_word_routes_comparison_table(self):
        f = {"claim": "dense retrieval beats sparse rather than the reverse", "probe": "relevance"}
        self.assertEqual(conductor._route_form(f), "comparison-table")

    def test_plain_claim_is_prose_only(self):
        self.assertEqual(conductor._route_form({"claim": "the read path dominates", "probe": "relevance"}), "")

    def test_route_never_returns_a_drawn_visual(self):
        for probe in conductor_probes():
            for claim in ("plot the cost curve across sizes", "draw the dependency graph", "42% 3x 9ms"):
                self.assertNotIn(conductor._route_form({"claim": claim, "probe": probe}),
                                 conductor._DRAWN_VISUALS)


def conductor_probes():
    return ("relevance", "contradiction", "surprise", "lineage", "")


class SiblingDeCollision(unittest.TestCase):
    def test_two_comparison_siblings_get_distinct_forms(self):
        # both surprise+contradiction route to comparison-table; de-collision must split them.
        seed = {"findings": [{"claim": "a", "bears_on": "x", "citation": "c", "probe": "surprise"},
                             {"claim": "b", "bears_on": "x", "citation": "c", "probe": "contradiction"}]}
        nodes = conductor.author_outline(seed, "obj")
        forms = [tuple(f for f in n["target_form"] if f not in conductor._PROSE)
                 for n in nodes if n["role"] == "deliver"]
        non_prose = [f[0] for f in forms if f]
        self.assertEqual(len(non_prose), len(set(non_prose)),
                         f"sibling forms must be distinct, got {non_prose}")

    def test_no_target_form_contains_a_drawn_visual(self):
        seed = {"findings": [{"claim": "plot it 42% 3x", "bears_on": "x", "citation": "c",
                              "probe": p} for p in ("surprise", "contradiction", "lineage", "relevance")]}
        nodes = conductor.author_outline(seed, "obj")
        for n in nodes:
            self.assertFalse(set(n["target_form"]) & conductor._DRAWN_VISUALS)

    def test_motivate_and_change_are_prose_only(self):
        seed = {"findings": [{"claim": "a", "bears_on": "x", "citation": "c", "probe": "surprise"}]}
        for n in conductor.author_outline(seed, "obj"):
            if n["role"] in ("motivate", "change-the-course"):
                self.assertEqual(n["target_form"], list(conductor._PROSE))


class FormGate(unittest.TestCase):
    def test_keeps_in_form_block(self):
        node = {"target_form": ["paragraph", "comparison-table"], "blocks": [
            {"type": "paragraph", "text": "x"},
            {"type": "comparison-table", "headers": ["a"], "rows": [{"cells": ["1"]}]}]}
        self.assertEqual(len(conductor.enforce_form(node)["blocks"]), 2)

    def test_drops_out_of_form_block(self):
        node = {"target_form": ["paragraph", "derivation"], "blocks": [
            {"type": "paragraph", "text": "x"},
            {"type": "metrics-grid", "items": [{"value": "3x", "label": "lag"}]}]}
        kept = [render.canonical_block(b)[0] for b in conductor.enforce_form(node)["blocks"]]
        self.assertEqual(kept, ["paragraph"])

    def test_drops_drawn_visuals_always(self):
        for vt in ("chart", "diagram", "ascii-diagram", "raw-html", "svg"):
            node = {"target_form": list(conductor._FORM_VOCAB),
                    "blocks": [{"type": vt, "content": "<svg/>", "chart": "bar", "data": [1]}]}
            self.assertEqual(conductor.enforce_form(node)["blocks"], [], f"{vt} must be dropped")

    def test_keeps_gap_family_for_reconcile(self):
        # the gap family is always allowed through (reconcile consolidates it afterward).
        node = {"target_form": ["paragraph", "derivation"], "blocks": [
            {"type": "gap-marker", "text": "an open tension"}]}
        self.assertEqual(len(conductor.enforce_form(node)["blocks"]), 1)

    def test_empty_after_gate_is_flagged_not_faked(self):
        node = {"id": "n", "contract": {"finding_ids": []}, "target_form": ["paragraph"],
                "blocks": [{"type": "chart", "chart": "bar", "data": [1]}]}
        out = conductor.enforce_form(node)
        self.assertEqual(out["blocks"], [])
        self.assertNotEqual(conductor.contract_gate(out, {}), [])


class FormContractEnforced(unittest.TestCase):
    def test_owed_form_but_only_prose_is_flagged(self):
        # codex P2: a writer that emits only prose when a structured form was owed must be FLAGGED —
        # else a monotone all-prose report ships (the gate drops wrong blocks, can't conjure one).
        node = {"id": "n1", "target_form": ["paragraph", "comparison-table"],
                "blocks": [{"type": "paragraph", "text": "just prose, ignored the contract"}]}
        self.assertNotEqual(conductor.form_violations(node), [])

    def test_owed_form_delivered_is_clean(self):
        node = {"id": "n1", "target_form": ["paragraph", "derivation"],
                "blocks": [{"type": "paragraph", "text": "x"}, {"type": "derivation", "bullets": ["a"]}]}
        self.assertEqual(conductor.form_violations(node), [])

    def test_hollow_owed_form_is_flagged(self):
        # codex P2: a {type: derivation, title: ...} shell satisfies the TYPE but delivers no payload —
        # the form contract must check for a SUBSTANTIVE owed-form block, not just its presence.
        node = {"id": "n1", "target_form": ["paragraph", "derivation"],
                "blocks": [{"type": "paragraph", "text": "x"}, {"type": "derivation", "title": "Reasoning"}]}
        self.assertNotEqual(conductor.form_violations(node), [], "a hollow derivation must be flagged")
        # a table with headers but no rows is likewise hollow
        node2 = {"id": "n2", "target_form": ["paragraph", "table"],
                 "blocks": [{"type": "paragraph", "text": "x"}, {"type": "table", "headers": ["a", "b"]}]}
        self.assertNotEqual(conductor.form_violations(node2), [])

    def test_blank_owed_form_payload_is_flagged(self):
        # codex P2: blank-but-truthy payloads (bullets:[""], rows:[[]]) must NOT clear the contract.
        n1 = {"id": "n1", "target_form": ["paragraph", "derivation"],
              "blocks": [{"type": "paragraph", "text": "x"}, {"type": "derivation", "bullets": [""]}]}
        self.assertNotEqual(conductor.form_violations(n1), [])
        n2 = {"id": "n2", "target_form": ["paragraph", "table"],
              "blocks": [{"type": "paragraph", "text": "x"},
                         {"type": "table", "headers": ["a"], "rows": [[]]}]}
        self.assertNotEqual(conductor.form_violations(n2), [])

    def test_prose_only_node_never_flagged(self):
        node = {"id": "n1", "target_form": list(conductor._PROSE),
                "blocks": [{"type": "paragraph", "text": "x"}]}
        self.assertEqual(conductor.form_violations(node), [])

    def test_run_conductor_surfaces_form_flags(self):
        # a lazy writer (prose only) on a seed that routes to a structured form surfaces a form_flag.
        seed = {"findings": [{"claim": "a vs b clearly", "bears_on": "x", "citation": "c",
                              "probe": "contradiction"}], "residuals": []}
        lazy = lambda prompt: ('prose only.\n```json\n{"title":"t","blocks":[{"type":"paragraph",'
                               '"text":"a vs b clearly stated as prose"}],'
                               '"digest":{"bullets":[],"assumed_prior":"","contribution":"c develops",'
                               '"cross_refs":[]}}\n```')
        result = conductor.run_conductor(seed, "obj", lazy, is_enabled=True,
                                         conciliate_fn=lambda p: '```json\n{"blocks":[]}\n```')
        self.assertTrue(result["form_flags"], "a prose-only node owing a form must be flagged")


class ReconcilePreservesUnconsumableGaps(unittest.TestCase):
    def test_headers_rows_gap_table_is_not_lost(self):
        # codex P2: a headers+rows gap-table has no clean description field, so it is NOT consumed;
        # reconcile must LEAVE it in place rather than strip its only-boundary content into the void.
        nodes = [{"blocks": [{"type": "gap-table", "headers": ["g", "need"],
                              "rows": [["open lag", "a load test"]]}]}]
        stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        kept_types = [render.canonical_block(b)[0] for n in stripped for b in n["blocks"]]
        self.assertIn("gap-table", kept_types, "the un-consumable gap-table must be preserved")
        self.assertIsNone(gap, "nothing consumable to consolidate")

    def test_dict_list_gap_table_is_consumed_and_stripped(self):
        nodes = [{"blocks": [{"type": "gap-table", "gaps": [{"description": "open lag"}]}]}]
        stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        self.assertEqual([b for n in stripped for b in n["blocks"]], [])
        self.assertEqual(gap["gaps"], [{"description": "open lag"}])

    def test_descriptionless_gap_table_preserved(self):
        # codex P2: gaps with only need/status (no string description) yield nothing to consolidate —
        # the block must NOT be consumed/stripped (its content would vanish), but left in place.
        nodes = [{"blocks": [{"type": "gap-table", "gaps": [{"need": "a test", "status": "open"}]}]}]
        stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        kept = [render.canonical_block(b)[0] for n in stripped for b in n["blocks"]]
        self.assertIn("gap-table", kept, "a description-less gap-table must be preserved")
        self.assertIsNone(gap)

    def test_mixed_gap_table_is_not_partially_stripped(self):
        # codex P2 + ed-research: a MIXED table (some rows described, some only need/status) is NOT
        # fully consumable — strip-and-rebuild would lose the description-less rows. Leave it in place.
        nodes = [{"blocks": [{"type": "gap-table", "gaps": [
            {"description": "a real gap"}, {"need": "a test", "status": "open"}]}]}]
        stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        kept = [render.canonical_block(b)[0] for n in stripped for b in n["blocks"]]
        self.assertIn("gap-table", kept, "a mixed table must be preserved whole, not partially stripped")
        self.assertIsNone(gap)

    def test_consolidated_gap_preserves_need_status_metadata(self):
        # codex P2: the consolidated gap-table must keep need/status/id, not reduce to description only.
        nodes = [{"blocks": [{"type": "gap-table", "gaps": [
            {"description": "live lag at 50 entities", "need": "a load test", "status": "open"}]}]}]
        _stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        self.assertEqual(gap["gaps"][0]["need"], "a load test")
        self.assertEqual(gap["gaps"][0]["status"], "open")

    def test_gap_marker_id_preserved_in_consolidation(self):
        # codex P2: a gap-marker's id (a gap-resolution.gap_id may reference it) must survive into the
        # consolidated gap-table, else linked cross-references render broken.
        nodes = [{"blocks": [{"type": "gap-marker", "id": "G7", "text": "the live lag at 50 entities"}]}]
        _stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        self.assertEqual(gap["gaps"][0].get("id"), "G7")
        self.assertEqual(gap["gaps"][0]["description"], "the live lag at 50 entities")

    def test_dedup_merges_metadata_regardless_of_order(self):
        # codex P2: a bare gap-marker seen FIRST then a richer gap-table row must MERGE the metadata —
        # the bare-first representative must not drop the later need/status.
        nodes = [
            {"blocks": [{"type": "gap-marker", "text": "live lag at 50 entities"}]},  # bare, first
            {"blocks": [{"type": "gap-table", "gaps": [
                {"description": "live lag at 50 entities", "need": "a load test", "status": "open"}]}]},
        ]
        _stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        self.assertEqual(len(gap["gaps"]), 1, "the two must dedup to one")
        self.assertEqual(gap["gaps"][0].get("need"), "a load test", "later metadata must be merged in")
        self.assertEqual(gap["gaps"][0].get("status"), "open")

    def test_headers_rows_with_gaps_list_preserved_not_consumed(self):
        # codex P2: the renderer uses ROWS and ignores `gaps`; reconcile must NOT consume the ignored
        # descriptions while stripping the rendered rows — leave the whole block in place.
        nodes = [{"blocks": [{"type": "gap-table", "headers": ["g", "need"],
                              "rows": [["open lag", "a test"]],
                              "gaps": [{"description": "ignored desc"}]}]}]
        stripped, gap = conductor.reconcile(nodes, {"residuals": []})
        kept = [render.canonical_block(b)[0] for n in stripped for b in n["blocks"]]
        self.assertIn("gap-table", kept, "the rendered headers+rows table must be preserved")
        self.assertIsNone(gap, "its ignored `gaps` list must NOT be consumed")


class GateRecomputedAfterReconcile(unittest.TestCase):
    def test_finding_surviving_only_in_stripped_gap_is_flagged(self):
        # codex P2: a finding whose claim lives ONLY in a consumed gap block must register as a DROP —
        # the gate is computed AFTER reconcile strips that block, not on the pre-strip text.
        seed = {"findings": [{"claim": "the eviction never fires", "bears_on": "x",
                              "citation": "c", "probe": "relevance"}], "residuals": []}

        def writer(prompt):
            env = {"title": "t", "blocks": [
                {"type": "paragraph", "text": "generic prose that does not echo the assigned claim."},
                {"type": "gap-marker", "text": "the eviction never fires"}],  # claim ONLY here
                "digest": {"bullets": [], "assumed_prior": "",
                           "contribution": "this develops the point fully", "cross_refs": []}}
            return "generic prose.\n```json\n" + json.dumps(env) + "\n```"

        result = conductor.run_conductor(seed, "obj", writer, is_enabled=True,
                                         conciliate_fn=lambda p: '```json\n{"blocks":[]}\n```')
        deliver = [n for n in result["outline"] if n["role"] == "deliver"][0]
        self.assertNotEqual(deliver["gate"], [],
                            "a finding surviving only in a stripped gap block must be flagged")


class ReconcileGaps(unittest.TestCase):
    def test_one_consolidated_gap_table_unique_rows(self):
        nodes = [
            {"blocks": [{"type": "gap-table", "gaps": [{"description": "is the lag live at 50 entities?"}]}]},
            {"blocks": [{"type": "gap-marker", "text": "Is lag live at 50 entities"}]},  # paraphrase
            {"blocks": [{"type": "gap-table", "gaps": [{"description": "does eviction ever fire?"}]}]},
        ]
        seed = {"residuals": ["is the lag live at 50 entities?"]}  # dup of node 0
        stripped, gap = conductor.reconcile(nodes, seed)
        # per-node gaps stripped (D-B can't recur)
        self.assertTrue(all(render.canonical_block(b)[0] not in conductor._GAP_TYPES
                            for n in stripped for b in n["blocks"]))
        self.assertEqual(gap["type"], "gap-table")
        self.assertEqual(len(gap["gaps"]), 2)  # the lag-trio collapsed; eviction separate

    def test_no_gaps_returns_none(self):
        stripped, gap = conductor.reconcile([{"blocks": [{"type": "paragraph", "text": "x"}]}],
                                            {"residuals": []})
        self.assertIsNone(gap)


class DiversityGate(unittest.TestCase):
    def test_fails_on_all_identical_sections(self):
        spec = {"sections": [{"blocks": [{"type": "paragraph"}, {"type": "metrics-grid"}]}
                             for _ in range(5)]}
        self.assertNotEqual(conductor.diversity_report(spec)["violations"], [])

    def test_passes_on_varied_sections(self):
        spec = {"sections": [
            {"blocks": [{"type": "paragraph"}, {"type": "comparison-table", "headers": ["a"], "rows": [{"cells": ["1"]}]}]},
            {"blocks": [{"type": "paragraph"}, {"type": "derivation", "bullets": ["x"]}]},
            {"blocks": [{"type": "paragraph"}, {"type": "diff-block", "lines": [{"text": "x"}]}]},
            {"blocks": [{"type": "paragraph"}]},
        ]}
        self.assertEqual(conductor.diversity_report(spec)["violations"], [])

    def test_form_vocab_excludes_drawn_visuals(self):
        self.assertEqual(set(conductor._FORM_VOCAB) & conductor._DRAWN_VISUALS, set())

    def test_closing_scaffold_cannot_mask_monotone_node_bodies(self):
        # codex P2: when every authored node section uses the same template, the appended derivation/
        # gap closing sections must NOT lift the score above the gate — run_conductor scores node
        # sections only. All-prose nodes (no routed form) => identical [paragraph] signatures => flagged.
        seed = {"findings": [{"claim": "a plain narrative claim here", "bears_on": "x",
                              "citation": "c", "probe": "relevance"}],
                "residuals": ["an open thread on scale"]}

        def prose_writer(prompt):
            env = {"title": "t", "blocks": [
                {"type": "paragraph", "text": "a plain narrative claim here, developed as pure prose."}],
                "digest": {"bullets": [], "assumed_prior": "",
                           "contribution": "this develops the claim as plain prose", "cross_refs": []}}
            return "a plain narrative claim here.\n```json\n" + json.dumps(env) + "\n```"

        result = conductor.run_conductor(seed, "obj", prose_writer, is_enabled=True,
                                         conciliate_fn=lambda p: '```json\n{"blocks":[]}\n```')
        self.assertNotEqual(result["diversity"]["violations"], [],
                            "monotone all-prose node bodies must be flagged despite closing sections")


class FormGuidanceCarriesSchema(unittest.TestCase):
    def test_guidance_includes_required_fields(self):
        # codex P2: naming the form alone isn't enough — a correctly-typed block missing a required
        # field is dropped by normalization. The guidance must carry the field contract.
        g = conductor._form_guidance(["paragraph", "comparison-table"])
        self.assertIn("headers", g)
        self.assertIn("rows", g)
        self.assertIn("comparison-table", g)

    def test_every_vocab_form_has_a_shape(self):
        for f in conductor._FORM_VOCAB:
            self.assertIn(f, conductor._FORM_SHAPE, f"{f} needs a field-shape contract in the prompt")

    def test_prose_only_guidance_has_no_schema(self):
        g = conductor._form_guidance(list(conductor._PROSE))
        self.assertIn("PROSE", g)


class SyntheticProsePreserved(unittest.TestCase):
    def test_loose_prose_survives_visual_strip(self):
        # codex P2: the conciliator wrote loose prose + a fenced envelope holding ONLY a chart; after
        # the visual strip the parsed blocks are empty — the loose prose must still carry the synthesis.
        nodes = [{"role": "deliver", "title": "t",
                  "blocks": [{"type": "paragraph", "text": "node prose."}],
                  "digest": {"bullets": [], "assumed_prior": "",
                             "contribution": "develops the central claim to full plenitude",
                             "cross_refs": []}}]

        def conc(prompt):
            return ("The single through-line is that the gate must bite on substance.\n"
                    '```json\n{"blocks":[{"type":"chart","chart":"bar",'
                    '"data":[{"label":"a","value":1}]}]}\n```')

        _deep, synthetic, _shape = conductor.conciliate(nodes, [], "obj", conc, seed={"residuals": []})
        syn_text = " ".join(b.get("text", "") for s in synthetic["sections"] for b in s["blocks"])
        self.assertIn("through-line", syn_text, "loose prose must survive the visual strip")
        types = [b.get("type") for s in synthetic["sections"] for b in s["blocks"]]
        self.assertNotIn("chart", types, "the drawn visual must be stripped")


if __name__ == "__main__":
    unittest.main()
