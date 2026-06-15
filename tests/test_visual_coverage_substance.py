"""The visual-coverage gate bites on SUBSTANCE, not on a block's mere type (D5 + D6 / plan Steps 1-2).

Two strengthenings, asserted as the gate VERDICT (the no-raise guarantee lives in
tests/test_render_failclosed.py):

  D6 — a visual satisfies coverage only if its PAYLOAD is substantive (excludes
       title/label/header/headers/chrome). A hollow/header-only/chrome-only/mixed-invalid block, a
       raw-html with no visible substantive payload, or a hollow top-level `metrics` does NOT clear
       a dense table.
  D5 — quantitative *prose* (numeric density: >=3 distinct magnitudes, EXCLUDING years and version
       tokens) over ANY non-visual block triggers the coverage owe, not only a dense table.

For each VISUAL_BLOCK_TYPES member: its CANONICAL substantive shape + a dense table => [];
a hollow variant + a dense table => ["visual-coverage"]. Plus the D5 negatives and positives.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402
import render  # noqa: E402


# A dense table — the quantitative trigger the visual must satisfy (>= QUANTITATIVE_ROW_THRESHOLD).
def _dense_table():
    return {"type": "table", "headers": ["k", "v"],
            "rows": [["a", "1"], ["b", "2"], ["c", "3"], ["d", "4"]]}


def _spec(*blocks):
    return {"sections": [{"title": "S", "blocks": list(blocks)}]}


def _coverage(*blocks):
    """The visual-coverage verdict on a content spec built from these blocks."""
    return close._check_visual_coverage(_spec(*blocks))


# --- The canonical SUBSTANTIVE shape per visual type (renderable + payload-bearing). --------------
# Keyed by the type as it appears in VISUAL_BLOCK_TYPES (aliases canonicalize internally).
_SUBSTANTIVE = {
    "metrics-grid": {"type": "metrics-grid", "items": [
        {"value": "42%", "label": "win rate"}, {"value": "3x", "label": "speedup"}]},
    "metrics": {"type": "metrics", "metrics": [{"value": "9", "label": "nodes"}]},
    "metric-card": {"type": "metric-card", "items": [{"value": "1", "label": "x"}]},
    "metric-cards": {"type": "metric-cards", "items": [{"value": "1", "label": "x"}]},
    "kpi-row": {"type": "kpi-row", "items": [{"value": "1", "label": "x"}]},
    "kpi-grid": {"type": "kpi-grid", "items": [{"value": "1", "label": "x"}]},
    "stats": {"type": "stats", "items": [{"value": "1", "label": "x"}]},
    "comparison-table": {"type": "comparison-table", "headers": ["dim", "A", "B"], "rows": [
        {"cells": ["latency", "10ms", "20ms"]}, {"cells": ["cost", "low", "high"]}]},
    "diff-block": {"type": "diff-block", "header": "the change", "lines": [
        {"type": "delete", "text": "old approach"}, {"type": "insert", "text": "new approach"}]},
    "comparison": {"type": "comparison",
                   "before": {"title": "Before", "bullets": ["slow", "manual"]},
                   "after": {"title": "After", "bullets": ["fast", "automatic"]}},
    "pros-cons": {"type": "pros-cons",
                  "before": {"title": "Pros", "bullets": ["cheap"]},
                  "after": {"title": "Cons", "bullets": ["risky"]}},
    "compare": {"type": "compare",
                "before": {"title": "X", "bullets": ["a"]},
                "after": {"title": "Y", "bullets": ["b"]}},
    "next-steps-grid": {"type": "next-steps-grid", "steps": [
        {"title": "ship the gate", "description": "wire it into close"},
        {"title": "measure", "description": "A/B the producers"}]},
    "steps": {"type": "steps", "steps": [
        {"title": "do it", "description": "concretely"}]},
    "concept-grid": {"type": "concept-grid", "items": [
        {"name": "throughput", "text": "items per second"},
        {"name": "latency", "definition": "time to first byte"}]},
    "flow-example": {"type": "flow-example", "input": "raw seed",
                     "output": "rendered artefato"},
    "ascii-diagram": {"type": "ascii-diagram", "title": "pipeline",
                      "content": "seed -> outline -> nodes -> close"},
    "diagram": {"type": "diagram", "layout": "dag",
                "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                "edges": [{"source": "a", "target": "b"}]},
    "chart": {"type": "chart", "chart": "bar", "data": [
        {"label": "a", "value": 1}, {"label": "b", "value": 2}, {"label": "c", "value": 3}]},
    # raw-html escape hatches — real visible substantive payload.
    "raw-html": {"type": "raw-html",
                 "content": "<svg><rect x='0' y='0' width='10' height='10'/></svg>"},
    "svg": {"type": "svg",
            "content": "<svg><circle cx='5' cy='5' r='4'/></svg>"},
    "html": {"type": "html", "content": "<table><tr><td>real cell content here</td></tr></table>"},
    "custom-html": {"type": "custom-html", "content": "<aside class='card'>real text payload</aside>"},
}

# Hollow / header-only / chrome-only / mixed-invalid variants per type — each MUST FLAG.
_HOLLOW = {
    "metrics-grid": [
        {"type": "metrics-grid", "items": []},                       # empty
        {"type": "metrics-grid", "items": [{"value": "10"}]},        # no label (partial/hollow)
        {"type": "metrics-grid", "items": [{"label": "x"}]},         # no value
    ],
    "comparison-table": [
        {"type": "comparison-table", "headers": ["A", "B"], "rows": []},        # header-only
        {"type": "comparison-table", "headers": ["A", "B"], "rows": [{}]},      # row w/o cells
        # mixed valid+invalid: a cells-less row + a non-dict score_row + non-list classes.
        {"type": "comparison-table", "headers": ["A"], "rows": [{"classes": "nope"}],
         "score_row": "not a dict"},
    ],
    "diff-block": [
        {"type": "diff-block", "header": "only a header"},                      # header-only
        {"type": "diff-block", "lines": []},
        {"type": "diff-block", "lines": [{"type": "insert"}]},                  # line missing text
    ],
    "next-steps-grid": [
        {"type": "next-steps-grid", "steps": []},
        # chrome only — a phase/owner badge but no real action/title/description payload.
        {"type": "next-steps-grid", "steps": [{"phase": "now"}, {"priority": "P1"}]},
    ],
    "concept-grid": [
        {"type": "concept-grid", "items": []},
        {"type": "concept-grid", "items": [{"name": "throughput"}]},            # name w/o text
        {"type": "concept-grid", "items": ["not a dict"]},                      # non-dict item
    ],
    "comparison": [
        {"type": "comparison"},                                                # nothing
        {"type": "comparison", "before": {"title": "X"}, "after": {"title": "Y"}},  # titles only
    ],
    "flow-example": [
        {"type": "flow-example", "input": "x"},                                 # no output
        {"type": "flow-example", "output": "y"},                               # no input
        {"type": "flow-example", "label": "only chrome"},
    ],
    "ascii-diagram": [
        {"type": "ascii-diagram", "title": "only a title"},                    # no content
    ],
    "raw-html": [
        {"type": "raw-html", "content": ""},                                   # empty
        {"type": "raw-html", "content": "<script>x()</script>"},               # script-only
        {"type": "raw-html", "content": "{svg}"},                              # literal {svg}
        {"type": "raw-html", "content": "<div></div>"},                        # wrapper-only
        {"type": "raw-html", "content": "<aside class='card'></aside>"},       # card chrome only
        {"type": "raw-html", "content": "<svg></svg>"},                        # empty svg
    ],
}


class VisualCoverageBitesOnSubstance(unittest.TestCase):
    def test_canonical_substantive_visual_clears_dense_table(self):
        for vtype, block in _SUBSTANTIVE.items():
            with self.subTest(vtype=vtype):
                self.assertEqual(
                    _coverage(_dense_table(), block), [],
                    f"a substantive {vtype} must clear the dense-table owe")

    def test_hollow_variant_does_not_clear_dense_table(self):
        for vtype, variants in _HOLLOW.items():
            for block in variants:
                with self.subTest(vtype=vtype, block=block):
                    self.assertEqual(
                        _coverage(_dense_table(), block), ["visual-coverage"],
                        f"a hollow {vtype} must NOT clear the dense-table owe: {block!r}")

    def test_empty_content_owes_nothing(self):
        self.assertEqual(_coverage(), [])

    def test_hollow_top_level_metrics_does_not_clear(self):
        # top-level content.metrics is itself a "visual"; a hollow one must NOT clear a dense table.
        for metrics in ([], [{"value": "10"}], [{"label": "x"}], [{}], ["not a dict"]):
            with self.subTest(metrics=metrics):
                content = {"metrics": metrics,
                           "sections": [{"title": "S", "blocks": [_dense_table()]}]}
                self.assertEqual(close._check_visual_coverage(content), ["visual-coverage"])

    def test_substantive_top_level_metrics_clears(self):
        content = {"metrics": [{"value": "42%", "label": "win"}, {"value": "3x", "label": "fast"}],
                   "sections": [{"title": "S", "blocks": [_dense_table()]}]}
        self.assertEqual(close._check_visual_coverage(content), [])


# --- D5: numeric-density quant-prose trigger -----------------------------------------------------

class NumericDenseProseTriggersCoverage(unittest.TestCase):
    # Negatives — must NOT flag (no real numeric density once years/versions/single strays excluded).
    def test_years_do_not_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "We shipped in 2024, again in 2025, and once more in 2026."}),
            [])

    def test_versions_do_not_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "Upgrade from v1.9.0 to v2.0.1 then v2.1.0 landed."}),
            [])

    def test_before_after_words_do_not_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "Before close and after publish the posture is qualitatively different."}),
            [])

    def test_single_stray_number_does_not_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "There is exactly 1 caveat worth naming in this prose."}),
            [])

    def test_full_dates_do_not_trigger(self):  # Codex P2 (review r5): day/month must not count
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "Milestones landed on 2024-01-15, 2025-02-20, and 2026-03-10."}),
            [])
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "Due dates: 01/15/2024, 02/20/2025, 03/10/2026 across the program."}),
            [])

    # Positives — 3 distinct magnitudes with no visual, in each prose-bearing form, MUST flag.
    def test_three_magnitudes_in_paragraph_triggers(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "Cost fell 42%, latency dropped to 30ms, and throughput rose 3x."}),
            ["visual-coverage"])

    def test_three_magnitudes_in_list_triggers(self):
        self.assertEqual(
            _coverage({"type": "list", "items": ["cost 42%", "latency 30ms", "throughput 3x"]}),
            ["visual-coverage"])

    def test_three_magnitudes_in_derivation_triggers(self):
        self.assertEqual(
            _coverage({"type": "derivation", "title": "Why",
                       "bullets": ["it fell 42%", "latency hit 30ms", "throughput 3x"]}),
            ["visual-coverage"])

    def test_three_magnitudes_cleared_by_a_real_metrics_grid(self):
        # the numbers carried in a SUBSTANTIVE metrics-grid do not self-trip (the visual is excluded
        # from the prose scan and credited as the satisfying visual).
        grid = {"type": "metrics-grid", "items": [
            {"value": "42%", "label": "cost"}, {"value": "30ms", "label": "latency"},
            {"value": "3x", "label": "throughput"}]}
        self.assertEqual(_coverage(grid), [])

    # Codex P2 (review r2): DECIMAL magnitudes must count — the version scrub must not eat them.
    def test_decimal_magnitudes_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "precision 0.91, recall 0.83, and F1 0.76 on the held-out set."}),
            ["visual-coverage"])

    def test_decimal_percentages_trigger(self):
        self.assertEqual(
            _coverage({"type": "paragraph",
                       "text": "error fell to 1.5% from 2.3%, now holding at 0.4%."}),
            ["visual-coverage"])


class NumericZeroMetricIsSubstantive(unittest.TestCase):
    # Codex P2 (review r2): a metric whose value is numeric 0 is REAL data, not hollow.
    def test_zero_value_metric_clears_dense_table(self):
        grid = {"type": "metrics-grid", "items": [{"value": 0, "label": "errors"}]}
        self.assertEqual(_coverage(_dense_table(), grid), [])

    def test_blank_string_metric_still_hollow(self):
        grid = {"type": "metrics-grid", "items": [{"value": "", "label": "x"}]}
        self.assertEqual(_coverage(_dense_table(), grid), ["visual-coverage"])


class RawHtmlPayloadSubstance(unittest.TestCase):
    # Codex P2 (review r4): empty leaf/wrapper markup is NOT a substantive visual.
    def test_empty_leaf_raw_html_does_not_clear(self):
        for c in ("<svg><g></g></svg>", "<table><tr><td></td></tr></table>",
                  "<div></div>", "<svg></svg>"):
            with self.subTest(c=c):
                self.assertEqual(
                    _coverage(_dense_table(), {"type": "raw-html", "content": c}),
                    ["visual-coverage"])

    def test_substantive_raw_html_clears(self):
        for c in ('<svg><rect width="10" height="10"/></svg>',
                  "<table><tr><td>data</td></tr></table>", '<img src="chart.png">'):
            with self.subTest(c=c):
                self.assertEqual(
                    _coverage(_dense_table(), {"type": "raw-html", "content": c}), [])


if __name__ == "__main__":
    unittest.main()
