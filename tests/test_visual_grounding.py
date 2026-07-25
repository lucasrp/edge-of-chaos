"""S7 (R2/R3) — the grounding boundary for DRAWN visuals. Every reader-visible chart/diagram/ascii-diagram
must carry a valid unforgeable grounding attestation (minted only when its data is attributable to the
evidence); a `raw-html`/svg authored visual is BANNED (ungroundable); a visual drawn DIRECTLY in the spec
is rejected by the SAME close.check_genus the publisher runs. ascii-edge grounding is capability-independent
(R3). Structured data visuals (metrics-grid/comparison-table) are NOT HMAC-attested here — instead R2-structured
gives them the partial sound close: every numeric value they show must also appear in the prose (R0-for-values),
so a number can't hide silently in a grid. Per-datum provenance grounding of structured values is the open follow-on."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import visual_grounding  # noqa: E402


def _art(blocks, cites=None):
    return {"slug": "s", "content": {"sections": [{"title": "B", "blocks": blocks}]},
            "cites": cites or [], "proposes": [], "intent": ""}


def _ground(blocks):
    return [v for v in close.check_genus(_art(blocks)) if v.startswith("visual-grounding")]


_CHART = {"type": "chart", "chart": "bar", "data": [{"label": "alpha", "value": 42}]}
_CITES = [{"ref": "r", "kind": "mundo", "relevant": True, "snippet": "alpha measured 42 in the v8 run"}]


class Attestation(unittest.TestCase):
    def test_sign_then_verify(self):
        self.assertTrue(visual_grounding.verify(visual_grounding.sign(_CHART)))

    def test_unsigned_fails(self):
        self.assertFalse(visual_grounding.verify(_CHART))

    def test_tamper_after_sign_fails(self):
        s = visual_grounding.sign(_CHART)
        s = {**s, "data": [{"label": "BOGUS", "value": 9}]}     # swap the data after signing
        self.assertFalse(visual_grounding.verify(s))

    def test_forged_token_fails(self):
        self.assertFalse(visual_grounding.verify({**_CHART, "_grounding": "deadbeef"}))


class GroundingBoundaryGate(unittest.TestCase):
    def test_directly_drawn_ungrounded_chart_is_rejected(self):
        self.assertIn("visual-grounding:ungrounded:chart", _ground([_CHART]))

    def test_signed_chart_passes(self):
        self.assertEqual(_ground([visual_grounding.sign(_CHART)]), [])

    def test_raw_html_authored_visual_is_ungroundable(self):
        # svg/html/custom-html all canonicalize to raw-html → ungroundable authored visual, rejected.
        for t in ("raw-html", "svg", "html", "custom-html"):
            self.assertIn("visual-grounding:ungroundable-authored-visual:raw-html",
                          _ground([{"type": t, "content": "<svg><rect/></svg>"}]), t)

    def test_ascii_diagram_is_an_ungroundable_authored_visual(self):
        # operator decision (S7): ascii-diagram is dropped — a free-form ascii relation can't be soundly
        # grounded and the renderable diagram/chart recipes supersede it. An authored ascii-diagram is
        # rejected; use a renderable diagram or grounded prose.
        self.assertIn("visual-grounding:ungroundable-authored-visual:ascii-diagram",
                      _ground([{"type": "ascii-diagram", "content": "alpha --> beta"}]))

    def test_signed_ungroundable_type_is_still_rejected(self):
        # a (self-impossible) signature can't launder an ungroundable-by-TYPE visual.
        for b in ({"type": "raw-html", "content": "<svg/>"}, {"type": "ascii-diagram", "content": "a --> b"}):
            self.assertTrue(any(v.startswith("visual-grounding:ungroundable-authored-visual")
                                for v in _ground([visual_grounding.sign(b)])), b["type"])

    def test_structured_and_palette_blocks_are_out_of_scope(self):
        # the deterministic boundary covers the DRAWN visuals (chart/diagram) + bans raw-html/svg/ascii.
        # Structured data visuals (metrics-grid/comparison/comparison-table) and structural/explanatory
        # blocks (table/next-steps-grid/card) are NOT hard-grounded here — governed by R0/R8/visual-coverage
        # (a dedicated structured-visual attestation is the documented R2-structured follow-on).
        for b in ({"type": "metrics-grid", "items": [{"value": "1", "label": "x"}]},
                  {"type": "comparison", "before": {"title": "A"}, "after": {"title": "B"}},
                  {"type": "comparison-table", "headers": ["A"], "rows": [{"cells": ["x"]}]},
                  {"type": "table", "headers": ["m"], "rows": [["x"]]},
                  {"type": "next-steps-grid", "items": ["a", "b"]},
                  {"type": "card", "title": "T", "text": "body"}):
            self.assertEqual(_ground([b]), [], b["type"])


class StructuredVisualValuesMustAppearInProse(unittest.TestCase):
    """Codex S7 (R2-structured, the sound close): a numeric magnitude in a BARE DATA CELL (metrics-grid /
    comparison / comparison-table / table-and-aliases / risk-table probability / the top-level executive
    metrics dashboard) and NEVER stated in the reader-visible explanatory corpus is REJECTED — a fabricated
    number cannot hide in a cell where R0 (labels) and R8 (prose-only) never reach it. The corpus is the
    completeness counterpart: paragraphs + executive_summary + narrative-block sentences (cards, lists,
    next-steps, concepts, gaps) + data-block sentence subfields (risk/mitigation/note). Code literals are
    exempt; drawn chart/diagram data is bound to evidence by the stronger HMAC grounding seam."""

    def _vv(self, blocks):
        return [v for v in close.check_genus(_art(blocks)) if v.startswith("r0:visual-value-not-in-prose")]

    def test_metrics_grid_value_absent_from_prose_is_rejected(self):
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      self._vv([{"type": "metrics-grid", "items": [{"value": "99", "label": "win"}]}]))

    def test_comparison_table_value_absent_from_prose_is_rejected(self):
        self.assertIn("r0:visual-value-not-in-prose:7.5",
                      self._vv([{"type": "comparison-table", "headers": ["d", "a", "b"],
                                 "rows": [{"cells": ["recall", "7.5", "lo"]}]}]))

    def test_value_echoed_in_prose_is_accepted(self):
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "Win rate hit 99 this run, as the grid shows."},
            {"type": "metrics-grid", "items": [{"value": "99", "label": "win"}]}]))

    def test_percent_value_only_needs_its_magnitude_in_prose(self):
        # '42%' → magnitude 42 must be in prose; the unit glyph is not required.
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "Cost fell to 42 of the prior baseline, as shown."},
            {"type": "metrics-grid", "items": [{"value": "42%", "label": "cost"}]}]))

    def test_unusual_numeric_forms_absent_from_prose_are_rejected(self):
        # Codex S7 re-gate: a fabricated value in a rendered form OUTSIDE the strict prose grammar
        # (plus-signed, leading-decimal, exponent) must still be caught — the extractor is generous.
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      self._vv([{"type": "metrics-grid", "items": [{"value": "+99", "label": "x"}]}]))
        self.assertIn("r0:visual-value-not-in-prose:0.75",
                      self._vv([{"type": "comparison-table", "headers": ["d", "a", "b"],
                                 "rows": [{"cells": ["recall", ".75", "lo"]}]}]))
        self.assertIn("r0:visual-value-not-in-prose:1000.0",
                      self._vv([{"type": "metrics-grid", "items": [{"value": "1e3", "label": "n"}]}]))

    def test_unusual_numeric_forms_echoed_in_prose_are_accepted(self):
        # stating the same magnitude in ANY equivalent form clears it (numeric comparison): +99≡99, .75≡0.75.
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "It rose by 99 and recall held at 0.75, with 1000 runs, as shown."},
            {"type": "metrics-grid", "items": [{"value": "+99", "label": "delta"},
                                               {"value": ".75", "label": "recall"},
                                               {"value": "1e3", "label": "runs"}]}]))

    def test_comparison_side_title_value_absent_from_prose_is_rejected(self):
        # Codex S7 re-gate #4: a number in a reader-visible LABEL/TITLE of a data block (a comparison side
        # title 'AUC 99') is a data claim, not free chrome — value-checked, so absence from prose fails.
        v = self._vv([{"type": "comparison",
                       "before": {"title": "AUC 85", "items": ["a"]},
                       "after": {"title": "AUC 99", "items": ["b"]}}])
        self.assertIn("r0:visual-value-not-in-prose:85.0", v)
        self.assertIn("r0:visual-value-not-in-prose:99.0", v)

    def test_comparison_side_title_value_echoed_in_prose_is_accepted(self):
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "AUC rose from 85 to 99 across the run."},
            {"type": "comparison", "before": {"title": "AUC 85", "items": ["a"]},
             "after": {"title": "AUC 99", "items": ["b"]}}]))

    def test_explanatory_block_outside_a_narrow_allowlist_is_corpus(self):
        # the corpus is a DENYLIST, not an allowlist — a number in ANY readable non-data block (here a
        # callout) counts as explained and satisfies a data cell showing the same magnitude.
        self.assertEqual([], self._vv([
            {"type": "callout", "text": "We measured a 50 point lift this run."},
            {"type": "metrics-grid", "items": [{"value": "50", "label": "lift"}]}]))

    def test_unrendered_metadata_cannot_launder_a_value(self):
        # Codex S7 re-gate #6: the corpus is RENDER-TRUTH, so a number in an UNRENDERED field cannot satisfy
        # a data cell. metrics-grid renders only items/metrics — a sibling `description:'99'` is never shown;
        # a paragraph renders only its text — a `hidden_note:'99'` is never shown. Both must still FAIL.
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      self._vv([{"type": "metrics-grid", "items": [{"value": "99", "label": "x"}],
                                 "description": "99"}]))
        self.assertIn("r0:visual-value-not-in-prose:99.0", self._vv([
            {"type": "metrics-grid", "items": [{"value": "99", "label": "x"}]},
            {"type": "paragraph", "text": "no number in the visible prose", "hidden_note": "99"}]))

    def test_style_hidden_text_cannot_launder_a_value(self):
        # render-truth also drops EXPLICITLY hidden text (display:none) — a value 'explained' only in a
        # producer-hidden paragraph is not reader-visible, so it cannot satisfy the data cell.
        self.assertIn("r0:visual-value-not-in-prose:88.0", self._vv([
            {"type": "metrics-grid", "items": [{"value": "88", "label": "x"}]},
            {"type": "paragraph", "text": "we hit 88", "style": "display:none"}]))

    def test_safe_style_permitted_hiders_cannot_launder_a_value(self):
        # Codex S7 re-gate #7: safe_style PRESERVES content-visibility:hidden / zoom:0 / offscreen position;
        # the corpus hider check is FAIL-CLOSED (every non-benign prop), so each still drops the text.
        for hide in ("content-visibility:hidden", "zoom:0", "position:absolute;left:-9999px"):
            self.assertIn("r0:visual-value-not-in-prose:88.0", self._vv([
                {"type": "metrics-grid", "items": [{"value": "88", "label": "x"}]},
                {"type": "paragraph", "text": "we hit 88", "style": hide}]), hide)

    def test_clip_to_zero_overflow_combo_cannot_launder_a_value(self):
        # Codex S7 re-gate #8: each declaration is benign alone, but a zero dimension + a clipping overflow
        # collapses the text — must be treated as hidden, not credited.
        for hide in ("height:0;overflow:hidden", "max-height:0;overflow:hidden", "width:0;overflow-x:hidden"):
            self.assertIn("r0:visual-value-not-in-prose:88.0", self._vv([
                {"type": "metrics-grid", "items": [{"value": "88", "label": "x"}]},
                {"type": "paragraph", "text": "we hit 88", "style": hide}]), hide)

    def test_collapsed_spacing_styles_cannot_launder_a_value(self):
        # Codex S7 re-gate #9: safe-listed spacing/line metrics can still collapse text — zero line-height
        # with clipping overflow, or extreme-negative letter/word spacing. None may credit the value.
        for hide in ("line-height:0;overflow:hidden", "letter-spacing:-9999px", "word-spacing:-9999px"):
            self.assertIn("r0:visual-value-not-in-prose:88.0", self._vv([
                {"type": "metrics-grid", "items": [{"value": "88", "label": "x"}]},
                {"type": "paragraph", "text": "we hit 88", "style": hide}]), hide)

    def test_benign_line_height_and_positive_spacing_are_credited(self):
        # normal line-height / positive tracking are reader-visible — not dropped.
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "we hit 42", "style": "line-height:1.55;letter-spacing:1px"},
            {"type": "metrics-grid", "items": [{"value": "42", "label": "x"}]}]))

    def test_author_overflow_clip_cannot_launder_a_value(self):
        # Codex S7 re-gate #10: author-controlled `overflow` is NOT in the corpus safe set (same as the R0
        # prose floor), so a clipped-to-a-sliver paragraph (width:1px;overflow:hidden — non-zero, so the old
        # zero-only combo missed it) fail-closes and cannot credit the value. The corpus is no weaker than R0.
        for hide in ("width:1px;overflow:hidden", "overflow:hidden", "overflow-x:hidden"):
            self.assertIn("r0:visual-value-not-in-prose:42.0", self._vv([
                {"type": "paragraph", "text": "we hit 42", "style": hide},
                {"type": "metrics-grid", "items": [{"value": "42", "label": "x"}]}]), hide)

    def test_numeric_headings_are_corpus(self):
        # Codex S7 re-gate #8: a numeric section title / executive_summary title renders as a reader-visible
        # heading → harvested into the corpus, so it satisfies a matching data value.
        a1 = {"slug": "s", "cites": [], "proposes": [], "intent": "",
              "content": {"sections": [{"title": "Results 7",
                                        "blocks": [{"type": "metrics-grid", "items": [{"value": "7", "label": "x"}]}]}]}}
        self.assertEqual([], [v for v in close.check_genus(a1) if v.startswith("r0:visual-value-not-in-prose")])
        a2 = {"slug": "s", "cites": [], "proposes": [], "intent": "",
              "content": {"executive_summary_title": "The 9 Findings", "metrics": [{"value": "9", "label": "n"}],
                          "sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": "x"}]}]}}
        self.assertEqual([], [v for v in close.check_genus(a2) if v.startswith("r0:visual-value-not-in-prose")])

    def test_executive_summary_is_render_truth_not_raw(self):
        # Codex S7 re-gate #7: a number in a Markdown link URL of the executive_summary is an href (never
        # reader-visible) — it must not launder a data value. The corpus renders the summary first.
        art = {"slug": "s", "cites": [], "proposes": [], "intent": "",
               "content": {"metrics": [{"value": "99", "label": "win"}],
                           "executive_summary": ["See the [source run](https://example.test/run/99)."],
                           "sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": "no figure"}]}]}}
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      [v for v in close.check_genus(art) if v.startswith("r0:visual-value-not-in-prose")])

    def test_reader_visible_identifier_fields_are_corpus(self):
        # Codex S7 re-gate #5: name / id / input_label / output_label DO render to the reader (concept-grid
        # item.name, gap-marker id tag, flow-example labels) — they are harvested into the corpus, so each
        # satisfies a data cell showing the same magnitude (none lands in "no bucket").
        self.assertEqual([], self._vv([
            {"type": "metrics-grid", "items": [{"value": "99", "label": "x"}]},
            {"type": "concept-grid", "items": [{"name": "AUC 99", "description": "the score"}]}]))
        self.assertEqual([], self._vv([
            {"type": "metrics-grid", "items": [{"value": "5", "label": "x"}]},
            {"type": "gap-marker", "id": "5", "text": "open question five"}]))
        self.assertEqual([], self._vv([
            {"type": "metrics-grid", "items": [{"value": "7", "label": "x"}]},
            {"type": "flow-example", "input": "a", "output": "b", "input_label": "Step 7 input"}]))

    def test_risk_table_probability_absent_from_prose_is_rejected(self):
        # Codex S7 re-gate #3: a risk-table `probability` is a bare data cell (a badge under a column) — a
        # numeric probability not echoed in the explanatory corpus is rejected.
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      self._vv([{"type": "risk-table",
                                 "rows": [{"risk": "drift", "probability": "99%", "mitigation": "watch it"}]}]))

    def test_risk_table_probability_echoed_in_prose_is_accepted(self):
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "Drift probability is 99, so we watch it closely."},
            {"type": "risk-table",
             "rows": [{"risk": "drift", "probability": "99%", "mitigation": "watch it"}]}]))

    def test_risk_table_sentence_subfield_number_is_corpus_not_a_data_cell(self):
        # the risk/mitigation lines are readable SENTENCES (the blind reviewer reads them) — a number there
        # is explanatory text, not a bare data cell, so it does NOT itself owe a separate prose echo.
        self.assertEqual([], self._vv([{"type": "risk-table",
                                        "rows": [{"risk": "p95 latency near 300ms under load",
                                                  "probability": "media",
                                                  "mitigation": "shed load above 300ms"}]}]))

    def test_narrative_block_sentence_explains_a_data_cell(self):
        # a number stated in a narrative block's readable sentence (a next-step description) is part of the
        # explanatory corpus — it satisfies a data cell showing the same magnitude.
        self.assertEqual([], self._vv([
            {"type": "next-steps-grid", "items": [{"description": "drive p95 latency to 300ms"}]},
            {"type": "metrics-grid", "items": [{"value": "300ms", "label": "p95"}]}]))

    def test_narrative_block_number_alone_is_not_a_data_cell(self):
        # a number living only in a narrative sentence (no data cell) is reader-visible explanation, not a
        # hidden value — it is the blind reviewer's to judge, not the structural floor's.
        self.assertEqual([], self._vv([
            {"type": "next-steps-grid", "items": [{"description": "drive p95 latency to 300ms"}]}]))

    def test_code_block_literals_are_exempt(self):
        # code literals / line numbers are not claimed data — a code-block number owes no prose echo.
        self.assertEqual([], self._vv([{"type": "code-block", "content": "timeout = 30000  # ms"}]))

    def test_plain_table_cell_value_absent_from_prose_is_rejected(self):
        # Codex S7 re-gate #2: a plain data `table` renders numeric cells too — a value living only in a
        # table cell is rejected just like a comparison-table cell, across the unusual forms.
        self.assertIn("r0:visual-value-not-in-prose:99.0",
                      self._vv([{"type": "table", "headers": ["k", "v"], "rows": [["delta", "+99"]]}]))
        self.assertIn("r0:visual-value-not-in-prose:0.75",
                      self._vv([{"type": "table", "headers": ["k", "v"], "rows": [["recall", ".75"]]}]))
        self.assertIn("r0:visual-value-not-in-prose:1000.0",
                      self._vv([{"type": "table", "headers": ["k", "v"], "rows": [["runs", "1e3"]]}]))
        self.assertIn("r0:visual-value-not-in-prose:300.0",
                      self._vv([{"type": "table", "headers": ["k", "v"], "rows": [["latency", "300ms"]]}]))

    def test_plain_table_cell_value_echoed_in_prose_is_accepted(self):
        self.assertEqual([], self._vv([
            {"type": "paragraph", "text": "Delta rose 99, recall held 0.75, latency 300 over 1000 runs."},
            {"type": "table", "headers": ["k", "v"],
             "rows": [["delta", "+99"], ["recall", ".75"], ["latency", "300ms"], ["runs", "1e3"]]}]))

    def test_top_level_executive_metrics_value_absent_from_prose_is_rejected(self):
        # the executive dashboard (top-level `metrics`) is not block-shaped but renders as a grid — a
        # value hiding ONLY there is rejected just like a section-level grid.
        art = {"slug": "s", "cites": [], "proposes": [], "intent": "",
               "content": {"metrics": [{"value": "73", "label": "win"}],
                           "sections": [{"title": "B", "blocks": [
                               {"type": "paragraph", "text": "Prose that omits the figure."}]}]}}
        self.assertIn("r0:visual-value-not-in-prose:73.0",
                      [v for v in close.check_genus(art) if v.startswith("r0:visual-value-not-in-prose")])


class GroundVisualsSigningPass(unittest.TestCase):
    def test_cite_grounded_chart_is_signed_and_clean(self):
        art = _art([dict(_CHART)], _CITES)
        close.ground_visuals(art)
        self.assertEqual([v for v in close.check_genus(art) if v.startswith("visual-grounding")], [])

    def test_chart_not_in_cites_stays_ungrounded(self):
        art = _art([dict(_CHART)], [{"ref": "r", "kind": "mundo", "relevant": True,
                                     "snippet": "unrelated text about something else entirely"}])
        close.ground_visuals(art)
        self.assertTrue(any(v == "visual-grounding:ungrounded:chart"
                            for v in close.check_genus(art)))

    def test_ascii_diagram_is_never_grounded(self):
        # ascii is dropped — even with supporting cites, ground_visuals never signs it; it stays rejected.
        art = _art([{"type": "ascii-diagram", "content": "alpha --> beta"}],
                   [{"ref": "r", "kind": "mundo", "relevant": True,
                     "snippet": "alpha leads to beta in the pipeline"}])
        close.ground_visuals(art)
        self.assertIn("visual-grounding:ungroundable-authored-visual:ascii-diagram", close.check_genus(art))

    def test_ground_visuals_never_signs_raw_html(self):
        art = _art([{"type": "raw-html", "content": "<svg/>"}], _CITES)
        close.ground_visuals(art)
        self.assertIn("visual-grounding:ungroundable-authored-visual:raw-html", close.check_genus(art))

    def test_replayed_transplanted_attestation_is_stripped_and_rechecked(self):
        # Codex S7 #1: a GENUINELY-signed chart transplanted into an artefato whose cites do NOT support it
        # must not ride its old token through — ground_visuals strips the incoming attestation and
        # re-grounds against THIS artefato's evidence, so it ends up flagged.
        signed = visual_grounding.sign(dict(_CHART))           # validly signed once (data: alpha=42)
        self.assertTrue(visual_grounding.verify(signed))
        art = _art([signed], [{"ref": "r", "kind": "mundo", "relevant": True,
                               "snippet": "totally unrelated evidence about something else"}])
        close.ground_visuals(art)
        self.assertIn("visual-grounding:ungrounded:chart", close.check_genus(art))

    def test_reground_keeps_a_supported_visual_signed(self):
        # the same chart in an artefato whose cites DO support it is re-grounded and stays clean.
        art = _art([visual_grounding.sign(dict(_CHART))], _CITES)
        close.ground_visuals(art)
        self.assertEqual([v for v in close.check_genus(art) if v.startswith("visual-grounding")], [])


if __name__ == "__main__":
    unittest.main()
