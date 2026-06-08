"""The Artefato genus conformance contract (Close architecture, S6, ADR-0012/0013).

The genus is the OUTPUT contract every producer's Artefato must satisfy — enforced,
not advisory. `check_genus` reads a finished artefato and returns the list of genus
violations ([] iff conformant). It pins the field shapes against the real
`eventlog.publish_artefato` + `kernel` signatures (cites / proposes / distills / intent)
and checks **visual-coverage**: quantitative/multi-value content with no visual element.

SECTIONS ARE FREE — `check_genus` never checks for a named or ordered section. Visual-
coverage is CONTENT-RELATIVE: an artefato with no quantitative material needs no visual
and must not be flagged. The shapes mirror tools/eventlog.py; the visual palette mirrors
tools/render.py.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _wellformed():
    """A fully conformant artefato: snippeted cite, bodied proposes, intent set,
    no quantitative material (so no visual is owed)."""
    return {
        "slug": "recall-report",
        "content": {
            "sections": [
                {"title": "What I found", "blocks": [
                    {"type": "paragraph", "text": "the read budget is unnamed"},
                ]},
            ],
        },
        "cites": [
            {"ref": "github:abc123", "kind": "atividade", "relevant": True,
             "snippet": "switched the cursor to a per-session watermark"},
        ],
        "proposes": [
            {"body": "name the full-read budget", "kind": "constraint"},
        ],
        "distills": ["cluster:recall"],
        "intent": "open: budget unnamed; bet: name it next beat",
    }


class GenusContractEnforced(unittest.TestCase):
    """The genus is enforced on the output: missing cite snippet, bodyless proposes,
    empty intent, and quantitative-content-without-a-visual each surface a violation;
    content with no quantitative material owes no visual; a well-formed artefato is clean."""

    def test_cite_without_snippet_is_a_violation_naming_the_cite(self):
        art = _wellformed()
        art["cites"] = [{"ref": "github:abc123", "kind": "atividade", "relevant": True}]
        violations = close.check_genus(art)
        self.assertTrue(any("github:abc123" in v for v in violations),
                        f"expected a violation naming the cite, got {violations}")

    def test_proposes_item_without_body_is_a_violation(self):
        art = _wellformed()
        art["proposes"] = [{"kind": "constraint"}]
        violations = close.check_genus(art)
        self.assertTrue(any("proposes" in v.lower() or "body" in v.lower() for v in violations),
                        f"expected a proposes/body violation, got {violations}")

    def test_empty_intent_is_a_violation(self):
        art = _wellformed()
        art["intent"] = ""
        violations = close.check_genus(art)
        self.assertTrue(any("intent" in v.lower() for v in violations),
                        f"expected an intent violation, got {violations}")

    def test_table_of_three_rows_with_no_visual_flags_visual_coverage(self):
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "table", "headers": ["metric", "value"],
             "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]}
        )
        violations = close.check_genus(art)
        self.assertIn("visual-coverage", violations)

    def test_no_quantitative_material_owes_no_visual(self):
        art = _wellformed()  # prose only, no table/metrics
        violations = close.check_genus(art)
        self.assertNotIn("visual-coverage", violations)

    def test_table_of_three_rows_with_a_visual_present_is_clean(self):
        """Content-relative: the same quantitative material is fine once a visual is present."""
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].extend([
            {"type": "table", "headers": ["metric", "value"],
             "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]},
            {"type": "metrics-grid", "items": [{"value": "0.8", "label": "recall"}]},
        ])
        violations = close.check_genus(art)
        self.assertNotIn("visual-coverage", violations)

    def test_wellformed_artefato_returns_empty(self):
        self.assertEqual(close.check_genus(_wellformed()), [])


class GenusRejectsMalformedCiteShapes(unittest.TestCase):
    """Codex round-5 — a malformed cite shape must be a genus violation, never silently
    accepted. `cites` must be a LIST; every entry must be a dict carrying non-empty
    `ref` AND `snippet`. A genus-invalid cite shape can NEVER mint a proof."""

    def test_non_dict_cite_entry_is_a_violation_naming_the_cite(self):
        art = _wellformed()
        art["cites"] = ["github:abc"]
        violations = close.check_genus(art)
        self.assertTrue(any("github:abc" in v for v in violations),
                        f"expected a violation naming the cite, got {violations}")

    def test_non_list_cites_is_a_violation(self):
        art = _wellformed()
        art["cites"] = "notalist"
        violations = close.check_genus(art)
        self.assertTrue(any("cites" in v.lower() for v in violations),
                        f"expected a cites violation, got {violations}")

    def test_cite_missing_snippet_is_a_violation(self):
        art = _wellformed()
        art["cites"] = [{"ref": "x"}]
        violations = close.check_genus(art)
        self.assertTrue(any("snippet" in v.lower() for v in violations),
                        f"expected a missing-snippet violation, got {violations}")

    def test_wellformed_cites_list_has_no_cite_violation(self):
        art = _wellformed()
        violations = close.check_genus(art)
        self.assertFalse(any("cite" in v.lower() for v in violations),
                         f"expected no cite violation, got {violations}")


class GenusCoversTheFullRenderTree(unittest.TestCase):
    """#7 — the genus traverses EVERY part render.spec_to_html renders, not just
    `sections[*].blocks`. A dense table buried in `additional_sections` with no visual still
    triggers visual-coverage; a top-level `metrics` grid counts as the visual that satisfies
    a dense table elsewhere. And every block's required fields are validated against
    render.BLOCK_SCHEMAS, so a malformed block is flagged here instead of crashing render."""

    def test_dense_table_in_additional_sections_triggers_visual_coverage(self):
        art = _wellformed()
        art["content"]["additional_sections"] = [
            {"title": "Appendix", "blocks": [
                {"type": "table", "headers": ["metric", "value"],
                 "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]},
            ]},
        ]
        violations = close.check_genus(art)
        self.assertIn("visual-coverage", violations)

    def test_top_level_metrics_grid_satisfies_a_dense_table(self):
        """A dense table in additional_sections is covered by a top-level `metrics` grid (a
        visual render touches) — visual-coverage must SEE it, not just sections[*].blocks."""
        art = _wellformed()
        art["content"]["metrics"] = [{"value": "0.8", "label": "recall"}]
        art["content"]["additional_sections"] = [
            {"title": "Appendix", "blocks": [
                {"type": "table", "headers": ["metric", "value"],
                 "rows": [["recall", "0.8"], ["latency", "120ms"], ["cost", "$3"]]},
            ]},
        ]
        violations = close.check_genus(art)
        self.assertNotIn("visual-coverage", violations)

    def test_block_missing_a_required_field_is_flagged(self):
        art = _wellformed()
        # a paragraph with no `text` (a BLOCK_SCHEMAS-required field) would crash render
        art["content"]["sections"][0]["blocks"].append({"type": "paragraph"})
        violations = close.check_genus(art)
        self.assertTrue(any("paragraph" in v.lower() and "text" in v.lower()
                            for v in violations),
                        f"expected a missing-required-field violation, got {violations}")

    def test_required_field_satisfied_by_a_synonym_is_clean(self):
        """render maps synonyms (content→text for paragraph); a block carrying the synonym is
        well-formed and must NOT be flagged."""
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "paragraph", "content": "carried via the content synonym"})
        violations = close.check_genus(art)
        self.assertEqual(violations, [])

    def test_malformed_block_in_additional_sections_is_flagged(self):
        art = _wellformed()
        art["content"]["additional_sections"] = [
            {"title": "Appendix", "blocks": [{"type": "flow-example", "label": "x"}]},
        ]
        violations = close.check_genus(art)
        self.assertTrue(any("flow-example" in v.lower() for v in violations),
                        f"expected a flow-example required-field violation, got {violations}")


class GenusCanonicalizesAliasBlocksBeforeSchemaCheck(unittest.TestCase):
    """Codex round-6 [medium] — alias blocks bypass genus schema validation. `_check_block_schemas`
    looked up BLOCK_SCHEMAS by the RAW block type and skipped types not found, so renderer aliases
    (text→paragraph, note→callout) skipped required-field validation; render_block later canonicalizes
    them and the canonical renderer requires fields. So `{"type":"text"}` (no text) passed genus, got a
    proof, then CRASHED at render. The genus must normalize each block's type to its CANONICAL form
    (via render's shared alias map) BEFORE the BLOCK_SCHEMAS lookup + required-field check."""

    def test_alias_block_missing_canonical_required_field_is_flagged(self):
        art = _wellformed()
        # `text` is an alias for `paragraph`; paragraph requires the `text` field. A bare
        # {"type": "text"} carries no text → would crash render. It must be a genus violation.
        art["content"]["sections"][0]["blocks"].append({"type": "text"})
        violations = close.check_genus(art)
        self.assertTrue(any("text" in v.lower() for v in violations),
                        f"expected an alias→paragraph missing-text violation, got {violations}")

    def test_wellformed_alias_block_passes(self):
        """A well-formed alias block (text→paragraph carrying the canonical `text`) is clean."""
        art = _wellformed()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "text", "text": "carried via the text alias"})
        violations = close.check_genus(art)
        self.assertEqual(violations, [])


class GenusRejectsMalformedCiteFieldTypes(unittest.TestCase):
    """Codex round-6 [medium] — malformed cite fields still pass. The cite check only tested
    truthiness of `ref`/`snippet`, so a dict snippet, a whitespace-only string, or a non-string ref
    passed. Both `ref` and `snippet` must be STRINGS with non-empty `.strip()` content."""

    def test_non_string_snippet_is_a_violation(self):
        art = _wellformed()
        art["cites"] = [{"ref": "github:abc123", "snippet": {"text": "x"}}]
        violations = close.check_genus(art)
        self.assertTrue(any("snippet" in v.lower() for v in violations),
                        f"expected a snippet violation, got {violations}")

    def test_whitespace_only_snippet_is_a_violation(self):
        art = _wellformed()
        art["cites"] = [{"ref": "github:abc123", "snippet": "   "}]
        violations = close.check_genus(art)
        self.assertTrue(any("snippet" in v.lower() for v in violations),
                        f"expected a snippet violation, got {violations}")

    def test_non_string_ref_is_a_violation(self):
        art = _wellformed()
        art["cites"] = [{"ref": 123, "snippet": "a real snippet"}]
        violations = close.check_genus(art)
        self.assertTrue(any("ref" in v.lower() for v in violations),
                        f"expected a ref violation, got {violations}")

    def test_normal_string_cite_passes(self):
        art = _wellformed()
        violations = close.check_genus(art)
        self.assertFalse(any("cite" in v.lower() for v in violations),
                         f"expected no cite violation, got {violations}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
