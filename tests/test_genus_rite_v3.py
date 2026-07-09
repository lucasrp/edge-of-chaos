"""Genus rite v6 is roster-wide, not report-specific.

The shared Artefato genus carries lineage, reader model, mechanism trace, Mundo
fit/mismatch, old-edge equivalent draft, post-gate grounding, visible rewrite delta,
fact-audit, and canonical form grammar.
"""
import sys
import unittest
import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import genus_rite  # noqa: E402


FIXTURES = REPO / "tests/fixtures/genus_rite"


def _stage(stage_id, file_name, inputs, summary):
    path = FIXTURES / file_name
    return {
        "id": stage_id,
        "path": str(path.relative_to(REPO)),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "input_stage_ids": list(inputs),
        "summary": summary,
    }


def _stage_trace():
    return [
        _stage("old_edge_draft", "old_edge_draft.md", [],
               "old Edge subrite material: derived thesis, live question, worked example, unknowns, landing"),
        _stage("gap_gate", "gap_gate.md", ["old_edge_draft"],
               "gate names actionable lacunas from the old-edge draft"),
        _stage("post_gate_grounding", "post_gate_grounding.md", ["old_edge_draft", "gap_gate"],
               "directed grounding answers the named gate lacuna"),
        _stage("final_rewrite", "final_rewrite.md", ["old_edge_draft", "post_gate_grounding"],
               "rewrite preserves the thesis while showing grounding delta"),
        _stage("fact_audit", "fact_audit.md", ["final_rewrite"],
               "fact audit narrows overclaim before close"),
    ]


def _developed_spec():
    return {"sections": [{"title": "A tese operacional", "blocks": [
        {"type": "paragraph", "text": "Because the old result already showed the symptom, this report derives the missing cause."},
        {"type": "paragraph", "text": "The reader needs the mechanism, not another scoreboard."},
        {"type": "paragraph", "text": "The decision now is whether to make the rite executable before another blind report."},
        {"type": "derivation", "text": "If the approved example came from a sequence, the sequence must become the unit under test."},
        {"type": "gap-table", "gaps": [
            {"description": "Whether the final draft reran the post-gate grounding", "need": "trace", "status": "open"}]},
    ]}], "bibliography": [{"text": "outside frame", "url": "https://example.com"}]}


def _rite_trace():
    return {
        "version": "old-edge-grounded@1",
        "old_edge_draft": {
            "derived_thesis": "the sequence, not the final page, is the reproduced unit",
            "live_question": "whether the deploy reproduced the rite or only the final look",
            "worked_example": "approved exp072 arm starts from product question, setup, arms, result, and mechanism",
            "unknowns": "whether the deploy reproduced the rite or only the final look",
            "actionable_landing": "run a gate over this draft and ground the named gaps before rewriting",
        },
        "stage_trace": _stage_trace(),
        "reader_model": {
            "reader": "operator",
            "leveling": "knows the experiment and can detect house-style drift",
            "interests": "make the approved artifact genus reproducible",
            "growth_target": "ship a default that improves judgment instead of passing a local rubric",
        },
        "narrative_arc": {
            "throughline": "from visible mismatch to executable rite",
            "opening_stakes": "a blind report can look published while missing the approved cognition",
            "turning_point": "the unit under test becomes the rite, not the HTML",
            "landing_decision": "require a proof-bound trace before publish",
        },
        "gap_gate": [
            {"id": "g1",
             "gap": "the publisher cannot tell whether post-gate grounding happened",
             "grounding_task": "bind the rite trace into close proof and event payload"},
        ],
        "post_gate_grounding": [
            {"gap_id": "g1",
             "source_ref": "docs/genus-rite-v6-canonical-form.md",
             "finding": "the approved movement is old-edge draft -> gap gate -> directed grounder -> rewrite",
             "changed": "the implementation now validates that sequence as a payload trace"},
        ],
        "rewrite_delta": [
            {"gap_id": "g1",
             "before": "reviewer prompt mentions old-edge-with-grounding",
             "after": "publisher refuses developed synthesis without a trace",
             "effect": "the rite is reproducible instead of aspirational",
             "final_anchor": "make the rite executable"},
        ],
        "canonical_journey": [
            {"move": "thesis", "where": "A tese operacional"},
            {"move": "live_question", "where": "whether to make the rite executable"},
            {"move": "setup", "where": "old result already showed the symptom"},
            {"move": "lineage", "where": "approved example came from a sequence"},
            {"move": "result", "where": "the symptom"},
            {"move": "mechanism", "where": "missing cause"},
            {"move": "interpretation", "where": "sequence must become the unit under test"},
            {"move": "mundo", "where": "outside frame"},
            {"move": "grounding_effect", "where": "make the rite executable"},
            {"move": "limits", "where": "whether the final draft reran"},
            {"move": "decision", "where": "decision now"},
            {"move": "references", "where": "outside frame"},
        ],
        "fact_audit": {
            "external_claims_checked": "outside references position the rite; they do not validate local lift",
            "overclaim_guard": "no source is allowed to prove the deployment worked without a blind run",
        },
    }


class GenusRiteV6ReviewRubric(unittest.TestCase):
    def test_new_dimensions_are_in_the_shared_rubric(self):
        for dim in ("lineage_and_reader_model", "mechanism_trace", "grounding_audit",
                    "old_edge_grounded_rite", "canonical_form_grammar"):
            self.assertIn(dim, close.DIMENSIONS)
            self.assertIn(dim, close.DIMENSION_WEIGHTS)

    def test_lineage_dimension_is_visible_not_hidden_metadata(self):
        dim = close.DIMENSIONS["lineage_and_reader_model"].lower()
        self.assertIn("visible", dim)
        self.assertIn("inherits", dim)
        self.assertIn("reject", dim)
        self.assertIn("numbered", dim)
        self.assertIn("leveling", dim)
        self.assertIn("interests", dim)
        self.assertIn("growth", dim)
        self.assertIn("hidden publish metadata is not lineage", dim)

    def test_mechanism_dimension_requires_a_concrete_trace(self):
        dim = close.DIMENSIONS["mechanism_trace"].lower()
        self.assertIn("worked example", dim)
        self.assertIn("how the result happened", dim)
        self.assertIn("decorative", dim)

    def test_grounding_audit_dimension_blocks_external_overclaim(self):
        dim = close.DIMENSIONS["grounding_audit"].lower()
        self.assertIn("fit/mismatch", dim)
        self.assertIn("do not validate", dim)
        self.assertIn("studies", dim)
        self.assertIn("best practices", dim)
        self.assertIn("where the topic deserves", dim)
        self.assertIn("magnitude", dim)
        self.assertIn("overextended external grounding is a strike", dim)

    def test_prompt_carries_the_genus_rite_to_blind_reviewers(self):
        prompt = close._build_prompt(close._REGULAR_FOCUS,
                                     {"slug": "x", "content": {}, "cites": []})
        self.assertIn("GENUS RITE V6", prompt)
        self.assertIn("concrete mechanism trace", prompt)
        self.assertIn("fit/mismatch", prompt)
        self.assertIn("numbered lineage", prompt)
        self.assertIn("maximize utility and growth", prompt)
        self.assertIn("old-edge-with-grounding movement", prompt)
        self.assertIn("visible rewrite delta", prompt)
        self.assertIn("canonical-form miss", prompt)
        self.assertIn("canonical house journey", prompt)
        self.assertIn("next-steps-grid", prompt)

    def test_rubric_version_is_v9(self):
        self.assertEqual(close.GATE_RUBRIC_VERSION, "gate_rubric@9")

    def test_developed_synthesis_owes_executable_rite_trace(self):
        art = {
            "intent": "open: rite reproduction; bet: bind the process",
            "content": _developed_spec(),
            "cites": [{"ref": "docs/genus-rite-v6-canonical-form.md", "kind": "mundo", "snippet": "movement"}],
            "proposes": [{"body": "make genus rite trace proof-bound"}],
            "lineage": [{"type": "builds_on", "target": "approved-old-edge-grounded-arm"}],
            "skill": "report",
        }
        self.assertIn("genus-rite:missing-trace", close.check_genus(art))

        clean = {**art, "genus_rite": _rite_trace()}
        self.assertFalse(
            [v for v in close.check_genus(clean) if v.startswith("genus-rite:")],
            "a complete executable rite trace must clear the material rite gate",
        )

    def test_rite_trace_rejects_grounding_source_not_in_cites(self):
        trace = _rite_trace()
        trace["post_gate_grounding"][0]["source_ref"] = "missing-source"
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:post-gate-grounding", violations)

    def test_rite_trace_rejects_delta_without_visible_anchor(self):
        trace = _rite_trace()
        trace["rewrite_delta"][0]["final_anchor"] = "not in the final artefato"
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:visible-rewrite-delta", violations)

    def test_rite_trace_rejects_arbitrary_journey_moves(self):
        trace = _rite_trace()
        trace["canonical_journey"] = [
            {"move": f"arbitrary_{i}", "where": "somewhere"} for i in range(7)
        ]
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:canonical-journey", violations)

    def test_rite_trace_rejects_missing_material_stage_trace(self):
        trace = _rite_trace()
        del trace["stage_trace"]
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:stage-trace", violations)

    def test_rite_trace_rejects_old_edge_draft_without_subrite(self):
        trace = _rite_trace()
        trace["old_edge_draft"] = {
            "throughline": "reason first, then source",
            "unknowns": "deployment drift",
        }
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:old-edge-draft", violations)

    def test_rite_trace_rejects_wrong_stage_hash(self):
        trace = _rite_trace()
        trace["stage_trace"][0]["sha256"] = "0" * 64
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:stage-hash:old_edge_draft", violations)

    def test_rite_trace_rejects_stage_dependency_skip(self):
        trace = _rite_trace()
        trace["stage_trace"][2]["input_stage_ids"] = ["old_edge_draft"]
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:stage-deps:post_gate_grounding", violations)

    def test_rite_trace_rejects_unlinked_grounding_gap(self):
        trace = _rite_trace()
        trace["post_gate_grounding"][0]["gap_id"] = "other-gap"
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:post-gate-grounding", violations)

    def test_rite_trace_rejects_partially_grounded_gap_set(self):
        trace = _rite_trace()
        trace["gap_gate"].append({
            "id": "g2",
            "gap": "the canonical journey can still be label-only",
            "grounding_task": "bind each journey move to visible content",
        })
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:post-gate-grounding", violations)

    def test_rite_trace_rejects_grounded_gap_without_visible_rewrite(self):
        trace = _rite_trace()
        trace["gap_gate"].append({
            "id": "g2",
            "gap": "the canonical journey can still be label-only",
            "grounding_task": "bind each journey move to visible content",
        })
        trace["post_gate_grounding"].append({
            "gap_id": "g2",
            "source_ref": "docs/genus-rite-v6-canonical-form.md",
            "finding": "journey moves need visible anchors",
            "changed": "the implementation should reject label-only journey maps",
        })
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:visible-rewrite-delta", violations)

    def test_rite_trace_rejects_journey_where_not_in_final_content(self):
        trace = _rite_trace()
        trace["canonical_journey"][0]["where"] = "not in the artefato"
        violations = genus_rite.rite_violations(
            trace,
            content=_developed_spec(),
            cites=[{"ref": "docs/genus-rite-v6-canonical-form.md"}],
        )
        self.assertIn("genus-rite:canonical-journey", violations)


class SharedDocsCarryTheRite(unittest.TestCase):
    def test_scaffold_declares_the_rite_as_genus_not_report(self):
        text = (REPO / "skills/_shared/scaffold.md").read_text(encoding="utf-8")
        self.assertIn("Genus default rite v6", text)
        self.assertIn("not `report`", text)
        self.assertIn("docs/genus-rite-v6-canonical-form.md", text)
        for phrase in ("Lineage ledger", "Reader growth model",
                       "Post-gate grounder", "Mundo deepening",
                       "Old-edge equivalent first draft", "Actionable gap gate",
                       "Rewrite with visible grounding effect",
                       "canonical form grammar", "canonical block palette",
                       "numbered", "leveling", "interests"):
            self.assertIn(phrase, text)

    def test_canonical_rite_doc_preserves_the_experiment_content(self):
        text = (REPO / "docs/genus-rite-v6-canonical-form.md").read_text(encoding="utf-8")
        for phrase in (
            "old-edge draft -> actionable gap gate -> directed grounder",
            "The Canonical Form Grammar",
            "The Canonical Block Palette",
            "Skill Translation Rule",
            "External sources can position a local result",
            "They do not validate local",
        ):
            self.assertIn(phrase, text)

    def test_pipeline_routes_substantive_gaps_back_to_author(self):
        text = (REPO / "skills/_shared/pipeline.md").read_text(encoding="utf-8")
        self.assertIn("genus rite v6", text)
        self.assertIn("skill-independent", text)
        self.assertIn("old-edge-with-grounding rite", text)
        self.assertIn("grounding effect is visible", text)
        self.assertIn("canonical form", text)
        self.assertIn("canonical journey", text)
        self.assertIn("before the final gating review", text)
        self.assertIn("fact-audit", text)


if __name__ == "__main__":
    unittest.main()
