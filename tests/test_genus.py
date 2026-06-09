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


def _prose_synthesis():
    """A developed prose synthesis (>= the rich-rite prose threshold of prose blocks) that
    carries ALL four cognitive moves — derivation, the knowledge boundary ("what I don't know"),
    an external frame (a cite), and lineage (a distills thread). The genus floor of the prose
    genus (#30): a report this developed owes the four moves; this one carries them, so it is
    clean."""
    return {
        "slug": "rich-report",
        "content": {
            "sections": [
                {"title": "The argument", "blocks": [
                    {"type": "paragraph",
                     "text": "We derive the read budget from first principles: a session is "
                             "bounded, therefore the cursor must be a per-session watermark."},
                    {"type": "paragraph",
                     "text": "What I don't know: whether the watermark survives a crash — that "
                             "remains unverified."},
                    {"type": "paragraph",
                     "text": "This builds on the prior recall thread, extending its depth."},
                ]},
            ],
        },
        "cites": [
            {"ref": "arXiv:2507.02778", "kind": "mundo", "relevant": True,
             "snippet": "the blind-spot is measured against an external benchmark"},
        ],
        "proposes": [{"body": "name the full-read budget", "kind": "constraint"}],
        "distills": ["cluster:recall"],
        "intent": "open: budget unnamed; bet: name it next beat",
        "skill": "report",
    }


def _shallow_prose():
    """A developed prose synthesis (enough prose to owe the moves) that carries NONE of the
    four cognitive moves: no derivation, no marked knowledge boundary, no external frame
    (no cites), no lineage (no distills). The ~2k-word / 0-figure shallow report the floor
    must reject (#30)."""
    return {
        "slug": "shallow-report",
        "content": {
            "sections": [
                {"title": "Findings", "blocks": [
                    {"type": "paragraph", "text": "The system has three components that interact."},
                    {"type": "paragraph", "text": "Each component holds its own state internally."},
                    {"type": "paragraph", "text": "The components are wired together at startup."},
                ]},
            ],
        },
        "cites": [],
        "proposes": [{"body": "keep wiring at startup", "kind": "constraint"}],
        "distills": [],
        "intent": "open: wiring undocumented; bet: document it",
        "skill": "report",
    }


class RichRiteFloorIsContentRelative(unittest.TestCase):
    """#30 — the rich-rite property floor. MIRRORS `_check_visual_coverage`: a DEVELOPED PROSE
    synthesis (the trigger, content-relative — never a word floor, never a named section) owes
    the four cognitive moves the rich old reports forced — derivation-from-first-principles, a
    marked "what I don't know" boundary, an external frame/benchmark, and lineage. A genuinely
    terse or non-prose artefato (a map's diagram, a short plan) owes NONE and is never failed."""

    def test_shallow_prose_missing_all_four_moves_is_flagged(self):
        violations = close.check_genus(_shallow_prose())
        for move in ("derivation", "what-i-dont-know", "external-frame", "lineage"):
            self.assertTrue(any(f"rich-rite:{move}" == v for v in violations),
                            f"expected rich-rite:{move} on a shallow developed report, got {violations}")

    def test_rich_prose_with_all_four_moves_is_clean(self):
        violations = [v for v in close.check_genus(_prose_synthesis()) if v.startswith("rich-rite")]
        self.assertEqual(violations, [], f"a report carrying all four moves owes nothing, got {violations}")

    def test_terse_prose_below_the_threshold_owes_no_moves(self):
        """Content-relative: a SHORT artefato (below the prose threshold) is not a developed
        synthesis and owes none of the moves — exactly as prose-only content owes no visual."""
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"] = [
            {"type": "paragraph", "text": "One terse observation, nothing more."}]
        violations = [v for v in close.check_genus(art) if v.startswith("rich-rite")]
        self.assertEqual(violations, [], f"a terse artefato owes no rich-rite moves, got {violations}")

    def test_diagram_form_map_owes_no_prose_moves(self):
        """A connections-diagram map (ascii-diagram + table, no developed prose) is non-prose
        and owes none of the prose cognitive moves — never failed for lacking them."""
        art = {
            "slug": "rel-map",
            "content": {"sections": [{"title": "Map", "blocks": [
                {"type": "ascii-diagram", "content": "A --applies--> B\nB --rhymes--> C"},
                {"type": "table", "headers": ["From", "Type", "To"],
                 "rows": [["A", "application", "B"], ["B", "rhyme", "C"], ["C", "parallel", "D"]]},
            ]}]},
            "cites": [], "proposes": [], "distills": [],
            "intent": "open: relations untraced; bet: trace them", "skill": "map",
        }
        violations = [v for v in close.check_genus(art) if v.startswith("rich-rite")]
        self.assertEqual(violations, [], f"a diagram map owes no prose moves, got {violations}")

    def test_derivation_block_satisfies_the_derivation_move(self):
        """The move is satisfied by the dedicated palette block OR by content markers — present
        ANYWHERE, never a named section. A `derivation` block satisfies it even without markers."""
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "derivation", "title": "From first principles",
             "bullets": ["premise", "therefore conclusion"]})
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:derivation" for v in violations),
                         f"a derivation block must satisfy the move, got {violations}")

    def test_gap_block_satisfies_the_boundary_move(self):
        """A `gap-marker`/`gap-table`/`gap-resolution` block satisfies the "what I don't know"
        boundary move, regardless of prose markers."""
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "gap-marker", "text": "unknown: does the watermark survive a crash?"})
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:what-i-dont-know" for v in violations),
                         f"a gap block must satisfy the boundary move, got {violations}")

    def test_cites_satisfy_the_external_frame_move(self):
        """The external-frame move extends the sourcing strike: a non-empty `cites` (a sourced
        external benchmark) satisfies it. _shallow_prose has none, so adding one clears it."""
        art = _shallow_prose()
        art["cites"] = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True,
                         "snippet": "an external benchmark the report imported"}]
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:external-frame" for v in violations),
                         f"a cite must satisfy the external-frame move, got {violations}")

    def test_distills_satisfy_the_lineage_move(self):
        """A non-empty `distills` (the threads the synthesis builds on) satisfies the lineage move."""
        art = _shallow_prose()
        art["distills"] = ["cluster:recall"]
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:lineage" for v in violations),
                         f"a distills thread must satisfy the lineage move, got {violations}")

    def test_executive_summary_counts_toward_prose_and_carries_moves(self):
        """Codex P2: render renders top-level `executive_summary`, so the floor must read it too —
        a report whose moves live in the exec summary must not be falsely flagged, and a
        summary-heavy report must not evade the floor by having < threshold section paragraphs."""
        # moves carried ONLY in the executive_summary (with one section paragraph) — must be clean
        art = {
            "slug": "summary-rich",
            "content": {
                "executive_summary": [
                    "We derive the budget from first principles, therefore the watermark is per-session.",
                    "What I don't know: whether it survives a crash (unverified).",
                    "This builds on the prior recall thread.",
                ],
                "sections": [{"title": "Body", "blocks": [
                    {"type": "paragraph", "text": "the load-bearing detail goes here."}]}],
            },
            "cites": [{"ref": "arXiv:1", "kind": "mundo", "relevant": True,
                       "snippet": "an external benchmark"}],
            "proposes": [], "distills": [], "intent": "open: x; bet: y", "skill": "report",
        }
        violations = [v for v in close.check_genus(art) if v.startswith("rich-rite")]
        self.assertEqual(violations, [], f"exec-summary moves must satisfy the floor, got {violations}")

    def test_summary_heavy_report_does_not_evade_the_floor(self):
        """A report whose prose is a long executive_summary (3+ items) but with no moves must be
        flagged — the exec summary counts toward the prose trigger, so the floor still applies."""
        art = {
            "slug": "summary-shallow",
            "content": {
                "executive_summary": [
                    "The system has three components.",
                    "Each holds its own state.",
                    "They are wired at startup.",
                ],
                "sections": [],
            },
            "cites": [], "proposes": [], "distills": [], "intent": "open: x; bet: y", "skill": "report",
        }
        violations = [v for v in close.check_genus(art) if v.startswith("rich-rite")]
        self.assertTrue(any(v == "rich-rite:derivation" for v in violations),
                        f"a summary-heavy shallow report must not evade the floor, got {violations}")

    def test_external_frame_needs_an_external_cite_not_just_an_internal_one(self):
        """Codex P2: an `atividade` (internal provenance) cite is NOT the outside benchmark the
        external-frame move requires — only an external (`mundo`) cite or a bibliography clears it."""
        art = _shallow_prose()
        art["cites"] = [{"ref": "github:abc", "kind": "atividade", "relevant": True,
                         "snippet": "the mentee's own prior commit"}]
        violations = close.check_genus(art)
        self.assertTrue(any(v == "rich-rite:external-frame" for v in violations),
                        f"an internal-only cite must NOT clear external-frame, got {violations}")

    def test_external_frame_cleared_by_a_mundo_cite(self):
        art = _shallow_prose()
        art["cites"] = [{"ref": "arXiv:1", "kind": "mundo", "relevant": True,
                         "snippet": "an external benchmark"}]
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:external-frame" for v in violations),
                         f"a mundo cite must clear external-frame, got {violations}")

    def test_empty_derivation_block_does_not_clear_the_move(self):
        """Codex P2: a placeholder palette block with no payload must NOT clear the move — a bare
        `derivation` block (no title/text/bullets) carries no derivation, so the strike stands."""
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"].append({"type": "derivation"})  # empty
        violations = close.check_genus(art)
        self.assertTrue(any(v == "rich-rite:derivation" for v in violations),
                        f"an empty derivation block must NOT clear the move, got {violations}")

    def test_empty_gap_marker_does_not_clear_the_boundary_move(self):
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"].append({"type": "gap-marker", "text": "   "})
        violations = close.check_genus(art)
        self.assertTrue(any(v == "rich-rite:what-i-dont-know" for v in violations),
                        f"an empty gap-marker must NOT clear the boundary move, got {violations}")

    def test_empty_bibliography_does_not_clear_external_frame(self):
        art = _shallow_prose()
        art["content"]["bibliography"] = []  # empty
        violations = close.check_genus(art)
        self.assertTrue(any(v == "rich-rite:external-frame" for v in violations),
                        f"an empty bibliography must NOT clear external-frame, got {violations}")

    def test_filled_derivation_block_clears_the_move(self):
        # the complement: a derivation block WITH payload clears it (the fix doesn't over-reject)
        art = _shallow_prose()
        art["content"]["sections"][0]["blocks"].append(
            {"type": "derivation", "title": "From first principles",
             "bullets": ["premise", "therefore conclusion"]})
        violations = close.check_genus(art)
        self.assertFalse(any(v == "rich-rite:derivation" for v in violations),
                         f"a filled derivation block must clear the move, got {violations}")

    def test_rich_rite_never_checks_a_named_section(self):
        """Non-procrusto: the same moves carried in arbitrarily-named/ordered sections still
        satisfy the gate — the floor reads the blocks, never the layout (ADR-0012/0013)."""
        art = _prose_synthesis()
        # scramble: one move per oddly-named section, reverse order
        blocks = art["content"]["sections"][0]["blocks"]
        art["content"]["sections"] = [
            {"title": "zzz last", "blocks": [blocks[2]]},
            {"title": "middle thoughts", "blocks": [blocks[1]]},
            {"title": "000 first", "blocks": [blocks[0]]},
        ]
        violations = [v for v in close.check_genus(art) if v.startswith("rich-rite")]
        self.assertEqual(violations, [], f"named/ordered sections must not matter, got {violations}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
