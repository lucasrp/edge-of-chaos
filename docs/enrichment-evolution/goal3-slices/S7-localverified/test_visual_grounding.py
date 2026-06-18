"""S7 (R2/R3) — the grounding boundary for DRAWN visuals. Every reader-visible chart/diagram/ascii-diagram
must carry a valid unforgeable grounding attestation (minted only when its data is attributable to the
evidence); a `raw-html`/svg authored visual is BANNED (ungroundable); a visual drawn DIRECTLY in the spec
is rejected by the SAME close.check_genus the publisher runs. ascii-edge grounding is capability-independent
(R3). Structured palette blocks (table/metrics-grid/comparison) are NOT in scope here."""
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
