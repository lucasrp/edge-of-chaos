"""S6 (R1) subordination — the visual floor is SUBORDINATE to R0 and to S7 grounding at the close gate:
- it does NOT fire as a failure while R0 (storytelling) fails — don't fight render-vs-degradation on an
  artefato that already lost its storytelling; the floor re-surfaces once R0 is clean;
- a renderable-but-UNGROUNDED visual still fails (S7) — satisfying the form floor is not enough."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402


def _art(skill, blocks):
    return {"slug": "s", "skill": skill,
            "content": {"sections": [{"title": "s", "blocks": blocks}]},
            "cites": [{"ref": "r", "kind": "mundo", "relevant": True, "snippet": "x"}],
            "proposes": [{"body": "b", "kind": "thread"}], "intent": "open: x; bet: y"}


class R1SubordinateToR0(unittest.TestCase):
    def test_presentation_floor_suppressed_while_r0_fails(self):
        # a `plan` missing its framed_steps WOULD raise presentation:has_structure(framed_steps); but the
        # section also has a visual (metrics-grid) with no prose → R0 fails, which SUPPRESSES the
        # presentation floor. The genus shows R0, not the presentation violation.
        v = close.check_genus(_art("plan", [
            {"type": "metrics-grid", "items": [{"value": "1", "label": "x"}]}]))   # visual, no prose, no steps
        self.assertIn("r0:visual-without-prose", v)
        self.assertFalse(any(x.startswith("presentation:") for x in v),
                         f"R1 floor must not fire while R0 fails: {v}")

    def test_presentation_floor_surfaces_once_r0_is_clean(self):
        # add explanatory prose that also states the grid's value (R0-for-values) → R0 clean → the plan's
        # framed_steps presentation floor now surfaces.
        v = close.check_genus(_art("plan", [
            {"type": "paragraph", "text": "The plan is explained here in prose, framing the 1 step."},
            {"type": "metrics-grid", "items": [{"value": "1", "label": "x"}]}]))
        self.assertNotIn("r0:visual-without-prose", v)
        self.assertIn("presentation:has_structure(framed_steps)", v)


if __name__ == "__main__":
    unittest.main()
