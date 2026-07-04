"""S2 (R0) — the storytelling floor: EXPLAIN, don't label (DOMINANT). The DETERMINISTIC, content-relative,
genus-relative structural core: a section carrying a visual/labeled structure OWES >=1 non-visual
explanatory prose unit in that section — the visual is ACCOMPANIED by prose, never substitutes it (the
operator's regression: a report that shows the phase siglas in a visual but never explains them). Pure
prose owes nothing; a non-narrative form (map/plan) still owes prose for ITS visuals. The SEMANTIC side
of R0 (is each explanation adequate? are the source's claims preserved?) is the blind reviewer's job
(ADR-0013), enforced via the narrative_depth dimension — not this deterministic gate."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import visible  # noqa: E402

_CHART = {"type": "chart", "chart": "bar", "data": [
    {"label": "a", "value": 1}, {"label": "b", "value": 2}, {"label": "c", "value": 3}]}
_DIAGRAM = {"type": "diagram", "layout": "dag",
            "nodes": [{"id": "a", "label": "Gather"}, {"id": "b", "label": "Synthesize"}],
            "edges": [{"source": "a", "target": "b"}]}


def _r0(content):
    art = {"slug": "s", "content": content, "cites": [], "proposes": [], "intent": ""}
    return [v for v in close.check_genus(art) if v.startswith("r0:")]


class StorytellingFloor(unittest.TestCase):
    def test_visual_section_without_prose_fails(self):
        # a section that shows a visual but carries no explanatory prose → "names without expanding".
        content = {"sections": [{"title": "Results", "blocks": [_CHART]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_visual_section_with_prose_passes(self):
        # the visual ACCOMPANIED by a prose unit that explains it → no R0 violation.
        content = {"sections": [{"title": "Results", "blocks": [
            {"type": "paragraph", "text": "Throughput rose across the three runs, as the bars show."},
            _CHART]}]}
        self.assertEqual(_r0(content), [])

    def test_callout_counts_as_the_accompanying_prose(self):
        # prose can be a callout (shared PROSE_BLOCK_TYPES), not only a paragraph.
        content = {"sections": [{"title": "Results", "blocks": [
            {"type": "callout", "text": "Each bar is one run; the trend is what matters here."},
            _CHART]}]}
        self.assertEqual(_r0(content), [])

    def test_pure_prose_owes_no_visual_floor(self):
        # no visual → nothing owed (content-relative); a prose-only artefato is never failed for R0.
        content = {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph", "text": "All explanation, no visuals at all in this artefato."}]}]}
        self.assertEqual(_r0(content), [])

    def test_map_form_with_diagram_and_prose_passes(self):
        # genus-relative: a non-narrative map (diagram) that explains its nodes in prose passes — it is
        # NOT failed for lacking a narrative arc, only for a visual with no accompanying explanation.
        content = {"sections": [{"title": "Harness map", "blocks": [
            {"type": "paragraph", "text": "Gather collects evidence; Synthesize writes it up. The arrow "
                                          "is the dependency between the two phases."},
            _DIAGRAM]}]}
        self.assertEqual(_r0(content), [])

    def test_map_form_diagram_without_prose_fails(self):
        # the operator's exact regression: a diagram of phase siglas with NO prose explaining them.
        content = {"sections": [{"title": "Harness map", "blocks": [_DIAGRAM]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_heading_only_is_not_the_owed_prose(self):
        # a subsection heading is a label, not explanation — a visual section with only a heading fails.
        content = {"sections": [{"title": "Results", "blocks": [
            {"type": "subsection", "title": "Throughput"}, _CHART]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_additional_sections_are_checked_too(self):
        content = {"sections": [{"title": "Intro", "blocks": [
                       {"type": "paragraph", "text": "Intro prose, no visual."}]}],
                   "additional_sections": [{"title": "Data", "blocks": [_CHART]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_label_only_list_section_fails(self):
        # Codex S2 #1: a section that is just a list of phase labels/siglas (no prose) names without
        # expanding — the regression in list form. `list` and its aliases owe accompanying prose.
        for ltype in ("list", "bullet-list", "ordered-list"):
            content = {"sections": [{"title": "Phases", "blocks": [
                {"type": ltype, "items": ["GATHER", "SYNTH", "REVIEW"]}]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), ltype)

    def test_card_style_labeled_structures_owe_prose(self):
        # Codex S2 #3: card/numbered-card/risk-table/code-block/template-block are reader-facing labeled
        # structures too — a section with only one and no prose fails.
        for block in (
            {"type": "card", "title": "GATHER", "text": "x"},
            {"type": "numbered-card", "items": [{"title": "SYNTH", "text": "y"}]},
            {"type": "risk-table", "rows": [{"risk": "R", "mitigation": "M"}]},
            {"type": "code-block", "code": "run()"},
        ):
            content = {"sections": [{"title": "S", "blocks": [block]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), block["type"])

    def test_card_with_prose_passes(self):
        content = {"sections": [{"title": "S", "blocks": [
            {"type": "paragraph", "text": "The card below summarizes the gather phase and why it leads."},
            {"type": "card", "title": "Gather", "text": "collect evidence"}]}]}
        self.assertEqual(_r0(content), [])

    def test_zero_variant_styles_are_hidden(self):
        # Codex S2 #3: opacity:00 / font-size:00px / opacity:.0 / scale:0 / transform:scale(0) parse as
        # zero (hidden/collapsed) — must not satisfy the prose owe.
        # NOTE: transform:scale(0) is NOT here — safe_style strips paren declarations, so it renders
        # VISIBLE (covered in the benign test). These are the declarations safe_style KEEPS and that hide.
        for style in ("opacity:00", "font-size:00px", "opacity:.0", "opacity:0.00", "font-size:000",
                      "scale:0", "scale:0.0", "font:0px serif", "font: bold 0px serif", "font:0% serif",
                      "font:0/0 serif", "font:0 serif", "font:italic bold 0px/1.5 serif",  # shorthand zero
                      "scale:-0", "scale:1 -0", "opacity:-0",                                # signed zero
                      "text-indent:-9999px", "text-indent:-100px",                          # off-screen indent
                      "text-indent:-50em", "text-indent:-99%", "text-indent:-7rem",          # unit off-screen
                      "font-size:0vw", "font-size:0vh", "font-size:0ch", "font-size:0rem",
                      "opacity:0%", "scale:0%", "font-size:0%", "opacity:00%",
                      "opacity:0e0", "font-size:0e0px", "scale:0e0", "text-indent:-1e3px"):  # exponent zero
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "hidden via a zero variant", "style": style}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), style)

    def test_zero_font_size_unit_does_not_clear_metrics_owe(self):
        # Codex S2 #3: a font-size:0<unit> body is the artefato's only prose → it does NOT clear the
        # top-level metrics owe (the same rendered-visible+hider predicate guards both paths).
        content = {"metrics": [{"value": "42%", "label": "win rate"}],
                   "sections": [{"title": "Body", "blocks": [
                       {"type": "paragraph", "text": "secretly tiny", "style": "font-size:0vw"}]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_empty_styled_block_is_not_prose(self):
        # Codex S2 #3: a paragraph/callout with a `style` but NO body text renders no explanation — its
        # style metadata must NOT pose as prose (the bug: _block_text flattened `style` as if it were text).
        for block in ({"type": "paragraph", "style": "color:#111"},
                      {"type": "callout", "style": "info"}):
            content = {"sections": [{"title": "Results", "blocks": [block, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), block)

    def test_list_with_prose_passes(self):
        content = {"sections": [{"title": "Phases", "blocks": [
            {"type": "paragraph", "text": "The harness runs three phases, each described next."},
            {"type": "list", "items": ["Gather: collect evidence", "Synth: write it", "Review: check it"]}]}]}
        self.assertEqual(_r0(content), [])

    def test_benign_styled_prose_satisfies_the_owe(self):
        # Codex S2 #2/#3: a reader-VISIBLE styled paragraph IS the explanation — R0 must not treat it as
        # hidden. Includes NON-zero values AND paren-bearing transforms (which safe_style STRIPS before
        # render, so the text is shown) and the non-zero `font:` shorthand.
        for style in ("color:#111", "padding-left:20px", "font-weight:600", "text-align:center",
                      "scale:0.5", "opacity:0.5", "font-size:14px", "font:14px serif",
                      "font:14px/0 serif",                              # line-height 0, size visible
                      "text-indent:-1px", "text-indent:-2px", "text-indent:-20px",  # hanging-indent nudge
                      "text-indent:-1.5em", "text-indent:-10%",        # small relative indent, visible
                      "left:-1px", "top:-5px", "left:-9999px",         # offset alone (needs position) → reviewer
                      "opacity:1e0", "font-size:1e1px", "scale:1e0", "text-indent:-9e1px",  # nonzero exponent
                      "transform:scale(0)", "transform:scale(0.5)"):   # parens stripped → visible
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "Throughput rose across the runs, as shown.", "style": style},
                _CHART]}]}
            self.assertEqual(_r0(content), [], style)

    def test_callout_css_looking_style_is_a_variant_not_hidden(self):
        # render_callout uses `style` as a VARIANT (class), never a CSS attr — so a callout is never hidden
        # by its style field; a CSS-looking value must NOT false-fail it.
        content = {"sections": [{"title": "Results", "blocks": [
            {"type": "callout", "text": "This explains the chart below.", "style": "display:none"},
            _CHART]}]}
        self.assertEqual(_r0(content), [])

    def test_transparent_text_does_not_satisfy_the_owe(self):
        # Codex S2 #3: color:transparent / zero-alpha hex / -webkit-text-fill-color:transparent render the
        # text invisible (and safe_style keeps them — no parens) → must not satisfy the prose owe.
        for style in ("color:transparent", "color:#0000", "color:#00000000",
                      "color:#fff0", "color:#ffffff00",            # colored zero-alpha (Codex S2 #3)
                      "-webkit-text-fill-color:transparent"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "invisible explanation", "style": style}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), style)

    def test_opaque_color_prose_satisfies_the_owe(self):
        # guard: an OPAQUE color (black/white-hex/named) is visible text → it DOES satisfy the owe; and a
        # non-text transparent (background/border) must NOT false-fail the prose (exact property match).
        for style in ("color:#000000", "color:#fff", "color:navy", "background:#eee", "color:#ffffff",
                      "background-color:transparent", "border-color:transparent"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "Throughput rose, as the chart shows.", "style": style},
                _CHART]}]}
            self.assertEqual(_r0(content), [], style)

    def test_plus_signed_style_renders_visible_safe_style_strips_it(self):
        # Codex S2 #3 (refuted-but-hardened): render.safe_style DROPS any `+`-signed declaration (`+` is not
        # in its value charset), so an `opacity:+0` paragraph renders with DEFAULT opacity — the text is
        # reader-VISIBLE and correctly counts as prose. No hidden-prose bypass exists on the real pipeline.
        for style in ("opacity:+0", "font-size:+0px", "scale:+0", "font:+0 serif"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "Throughput rose, as shown.", "style": style}, _CHART]}]}
            self.assertEqual(_r0(content), [], style)

    def test_signed_zero_is_caught_at_the_parser_level(self):
        # defense-in-depth: were a signed zero ever to reach the parser (e.g. a future safe_style change),
        # both -0 and +0 are recognized as hidden.
        for decl in ("opacity:-0", "opacity:+0", "scale:-0", "scale:1 +0", "font-size:+0px"):
            self.assertTrue(visible._style_hides_text(decl), decl)

    def test_nonpainting_display_values_fail_closed(self):
        # Codex S2 #3: display is a POSITIVE visible-value allowlist — display:none AND non-painting modes
        # (table-column / table-column-group) hide; common visible modes pass.
        for style in ("display:none", "display:table-column", "display:table-column-group"):
            content = {"sections": [{"title": "S", "blocks": [
                {"type": "paragraph", "text": "hidden via display mode", "style": style}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), style)
        for style in ("display:block", "display:inline-block", "display:flex", "max-height:10rem"):
            content = {"sections": [{"title": "S", "blocks": [
                {"type": "paragraph", "text": "Visible explanation of the chart.", "style": style}, _CHART]}]}
            self.assertEqual(_r0(content), [], style)

    def test_zero_width_only_prose_is_not_prose(self):
        # Codex S2 #3: a paragraph/exec-summary item made only of zero-width / format characters renders no
        # readable glyph — it must NOT satisfy the prose owe even though str.strip() keeps the characters.
        for body in ("​", "​‌‍", "﻿", "  ​  ",
                     "️", "︎", "͏", "ㅤ",   # variation selectors / CGJ / Hangul filler (Codex S2 #3)
                     "⠀", "⠀⠀"):                                              # Braille Pattern Blank U+2800
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": body}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), repr(body))

    def test_real_glyphs_including_emoji_and_accents_are_prose(self):
        # guard against over-strict glyph detection: emoji (symbol) and accented/decomposed text count.
        for body in ("Throughput rose 📊 across runs.", "café results held", "42 runs completed"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": body}, _CHART]}]}
            self.assertEqual(_r0(content), [], repr(body))

    def test_unknown_or_exotic_property_fails_closed(self):
        # Codex S2 #3 (decisive allowlist): an UNKNOWN/exotic single-declaration hider kept by safe_style
        # (content-visibility:hidden, zoom:0) — and any future property not in the safe set — fails closed,
        # so it cannot pose as visible prose next to a visual.
        for style in ("content-visibility:hidden", "zoom:0", "some-future-hider:weird"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "exotic-hidden explanation", "style": style}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), style)

    def test_markup_only_paragraph_is_not_prose(self):
        # Codex S2 #3: a paragraph whose body is markup-only (e.g. "<br>") renders no visible explanation,
        # so it must NOT satisfy the prose owe even though text.strip() is truthy.
        for body in ("<br>", "   <br>  ", "<br><br>"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": body}, _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), repr(body))

    def test_css_hidden_prose_does_not_satisfy_the_owe(self):
        # Codex S2 #1: a paragraph/callout styled invisible renders to no reader-visible text, so it must
        # NOT satisfy the visual's prose owe — the section still fails (reader sees only the chart).
        for style in ("display:none", "opacity:0", "font-size:0", "visibility:hidden",
                      "visibility:collapse"):
            content = {"sections": [{"title": "Results", "blocks": [
                {"type": "paragraph", "text": "secretly hidden explanation", "style": style},
                _CHART]}]}
            self.assertIn("r0:visual-without-prose", _r0(content), style)

    def test_top_level_metrics_without_prose_fails(self):
        # Codex S2 #2: top-level content.metrics is a visual the renderer emits outside any section — it
        # still owes reader-visible prose somewhere in the artefato.
        content = {"metrics": [{"value": "42%", "label": "win rate"}, {"value": "3x", "label": "speedup"}],
                   "sections": [{"title": "Data", "blocks": [
                       {"type": "table", "headers": ["m"], "rows": [["x"], ["y"], ["z"]]}]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_top_level_metrics_with_prose_passes(self):
        # the same top-level metrics WITH an explanatory section paragraph → satisfied.
        content = {"metrics": [{"value": "42%", "label": "win rate"}, {"value": "3x", "label": "speedup"}],
                   "sections": [{"title": "Summary", "blocks": [
                       {"type": "paragraph", "text": "Win rate reached 42% and we saw a 3x speedup; here "
                                                     "is what each metric means and why it moved."}]}]}
        self.assertEqual(_r0(content), [])

    def test_top_level_metrics_with_markup_only_summary_fails(self):
        # Codex S2 #3: a markup-only executive_summary item ("<br>") renders no prose, so a top-level
        # metrics dashboard with only that owes prose and fails — the summary path shares the rendered-
        # visible predicate with the block path.
        content = {"metrics": [{"value": "42%", "label": "win rate"}],
                   "executive_summary": ["<br>"],
                   "sections": [{"title": "Body", "blocks": [
                       {"type": "table", "headers": ["m"], "rows": [["x"], ["y"], ["z"]]}]}]}
        self.assertIn("r0:visual-without-prose", _r0(content))

    def test_top_level_metrics_with_executive_summary_prose_passes(self):
        # exec-summary prose counts as the explanation too (it renders as reader-visible prose), so a
        # top-level metrics grid is cleared by an exec-summary even with no section-level visual.
        content = {"metrics": [{"value": "42%", "label": "win rate"}],
                   "executive_summary": ["Win rate of 42% is the headline; the body unpacks what it means."],
                   "sections": [{"title": "Body", "blocks": [
                       {"type": "paragraph", "text": "The body explains the metric in plain prose."}]}]}
        self.assertEqual(_r0(content), [])


if __name__ == "__main__":
    unittest.main()
