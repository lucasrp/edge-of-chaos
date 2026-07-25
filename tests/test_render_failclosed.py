"""render.py is fail-closed — it degrades to a comment, NEVER raises (D6 / plan Step 1).

render.py's own contract is "an unknown block type degrades to an HTML comment — it never
raises." But several renderers dereference optional nested fields directly (`diff-block`
`line["text"]`, `comparison-table` `score_row`/`classes`, `concept-grid`/`next-steps-grid`
items, `_render_metrics_items` `m["value"]`/`m["label"]`), so a malformed LLM-emitted block can
crash render mid-page. Once D2 lets a writer emit typed blocks, these payloads come from an LLM.

This module fuzzes a BATTERY of malformed blocks (one per known offender + a malformed top-level
`metrics`) and asserts `render.render_block` and `render.spec_to_html` NEVER raise — the no-crash
guarantee that Step 1 makes robust-by-construction (the substance VERDICT is asserted separately
in tests/test_visual_coverage_substance.py)."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import render  # noqa: E402


# A battery of malformed blocks — every nested-deref offender the renderers carry, in shapes an
# LLM can plausibly emit. Each MUST render to a string (a comment or degraded HTML), never raise.
_MALFORMED_BLOCKS = [
    # diff-block: a line missing `text` (the known `line["text"]` offender).
    {"type": "diff-block", "lines": [{"type": "insert"}]},
    {"type": "diff-block", "lines": [{}]},
    {"type": "diff-block", "lines": ["not a dict"]},
    {"type": "diff-block", "lines": "not a list"},
    {"type": "diff-block"},  # no lines at all
    # comparison-table: score_row not a dict; classes not a list; rows missing cells.
    {"type": "comparison-table", "headers": ["A", "B"], "rows": [{"cells": ["1", "2"]}],
     "score_row": "not a dict"},
    {"type": "comparison-table", "headers": ["A"], "rows": [{"cells": ["1"], "classes": "nope"}]},
    {"type": "comparison-table", "headers": ["A"], "rows": [{}]},
    {"type": "comparison-table", "headers": ["A"], "rows": ["not a dict"]},
    {"type": "comparison-table", "headers": ["A"]},  # no rows key
    {"type": "comparison-table", "rows": [{"cells": ["x"]}], "score_row": {"classes": "nope",
                                                                          "cells": ["y"]}},
    # concept-grid: a non-dict item.
    {"type": "concept-grid", "items": ["not a dict", 42, None]},
    {"type": "concept-grid", "items": [{"name": "ok"}, "bad"]},
    # next-steps-grid: a non-dict / int step, a now/next/later with junk.
    {"type": "next-steps-grid", "steps": [42, None, {"title": "ok"}]},
    {"type": "next-steps-grid", "now": ["a step", 7], "next": "not a list"},
    # metrics-grid: an item missing value/label (the `_render_metrics_items` offender).
    {"type": "metrics-grid", "items": [{"value": "10"}]},      # no label
    {"type": "metrics-grid", "items": [{"label": "x"}]},       # no value
    {"type": "metrics-grid", "items": [{}]},
    {"type": "metrics-grid", "items": ["not a dict"]},
    {"type": "metrics-grid", "items": [None]},
    # raw-html: literal {svg}, empty, script-only, wrapper-only, empty svg.
    {"type": "raw-html", "content": "{svg}"},
    {"type": "raw-html", "content": ""},
    {"type": "raw-html", "content": "<script>alert(1)</script>"},
    {"type": "raw-html", "content": "<div></div>"},
    {"type": "raw-html", "content": "<svg></svg>"},
    # blocks with the type field missing or non-string.
    {"text": "no type field"},
    {"type": 12345},
    {},
    # table renderer offenders (rows not a list of lists).
    {"type": "table", "headers": ["A"], "rows": "nope"},
    {"type": "table", "headers": ["A"], "rows": [None]},
    # explicit JSON null for list-shaped fields — the `.get(k, [])` default does NOT apply when the
    # key is present-but-null, so iterating it would raise (Codex P2, review r3).
    {"type": "diff-block", "lines": None},
    {"type": "comparison-table", "headers": None, "rows": None},
    {"type": "metrics-grid", "items": None},
    {"type": "concept-grid", "items": None},
    {"type": "next-steps-grid", "steps": None},
    {"type": "table", "headers": None, "rows": None},
    {"type": "list", "items": None},
]


class RenderBlockNeverRaises(unittest.TestCase):
    def test_every_malformed_block_renders_without_raising(self):
        for block in _MALFORMED_BLOCKS:
            with self.subTest(block=block):
                try:
                    out = render.render_block(block)
                except Exception as e:  # noqa: BLE001 — the whole point: it must not raise
                    self.fail(f"render_block raised {type(e).__name__} on {block!r}: {e}")
                self.assertIsInstance(out, str)


class SpecToHtmlNeverRaises(unittest.TestCase):
    def test_malformed_blocks_in_a_spec_render_without_raising(self):
        spec = {
            "sections": [{"title": "Fuzz", "blocks": _MALFORMED_BLOCKS}],
            "additional_sections": [{"title": "More", "blocks": _MALFORMED_BLOCKS}],
        }
        try:
            out = render.spec_to_html(spec)
        except Exception as e:  # noqa: BLE001
            self.fail(f"spec_to_html raised {type(e).__name__}: {e}")
        self.assertIsInstance(out, str)

    def test_malformed_top_level_metrics_renders_without_raising(self):
        # top-level `metrics` is rendered via _render_metrics_items directly — a malformed entry
        # (no value/label, a non-dict) must not crash the whole page.
        for metrics in (
            [{"value": "10"}],            # no label
            [{"label": "x"}],             # no value
            [{}],
            ["not a dict"],
            [None],
            "not a list",
        ):
            with self.subTest(metrics=metrics):
                try:
                    out = render.spec_to_html({"metrics": metrics})
                except Exception as e:  # noqa: BLE001
                    self.fail(f"spec_to_html raised {type(e).__name__} on metrics={metrics!r}: {e}")
                self.assertIsInstance(out, str)


    def test_null_or_nondict_sections_render_without_raising(self):
        # explicit-null / non-dict sections & blocks at the spec level must degrade, not crash.
        for spec in ({"sections": None}, {"sections": [None]}, {"sections": [{"blocks": None}]},
                     {"additional_sections": None}, {"metrics": None}):
            with self.subTest(spec=spec):
                try:
                    out = render.spec_to_html(spec)
                except Exception as e:  # noqa: BLE001
                    self.fail(f"spec_to_html raised {type(e).__name__} on {spec!r}: {e}")
                self.assertIsInstance(out, str)


if __name__ == "__main__":
    unittest.main()
