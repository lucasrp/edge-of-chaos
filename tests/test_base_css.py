"""Shared Artefato rendering layer — the neutralized base.css (Story S3, ADR-0012 model).

The Close-architecture rewrite ports the legacy 763-line base.css NEUTRALIZED: the
institutional brand (Google-font @import, tricolor stripe, the #26247B/#008C44/#FFCB05
tokens, the logo path-fill selectors) is stripped to a neutral slate/gray scale + a
system font stack — fully self-contained, branding deferred. The SEMANTIC colors
(status callouts, the Feynman derivation-purple / gap-amber) and EVERY component class
name render.py emits are KEPT (functional, not brand). These tests pin that contract.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSS = REPO / "tools" / "assets" / "base.css"


class NeutralizedNoBrand(unittest.TestCase):
    """The institutional brand is gone; the functional/semantic palette + the system
    font stack remain. Brand stripped: no Google-font @import, none of the three
    institutional tokens (#26247B/#008C44/#FFCB05), no tricolor .header-stripe, no
    logo path-fill selectors. Kept: the Feynman derivation-purple (#7C3AED) and
    gap-amber (#D97706), the .derivation block, the gap status badges, the danger
    callout, and a system font stack (-apple-system)."""

    def test_brand_stripped_semantics_and_system_font_kept(self):
        css = CSS.read_text()
        # REMOVED — institutional brand
        for token in ("@import", "#26247B", "#008C44", "#FFCB05",
                      ".header-stripe", "path[fill="):
            self.assertNotIn(token, css, f"brand artifact still present: {token!r}")
        # KEPT — functional / semantic palette + Feynman blocks
        for token in ("#7C3AED", "#D97706", ".derivation",
                      ".gap-status-open", ".callout-danger"):
            self.assertIn(token, css, f"functional style missing: {token!r}")
        # KEPT — system font stack (neutral, self-contained)
        self.assertTrue("system" in css or "-apple-system" in css,
                        "system font stack missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
