"""render-chrome i18n (structure not strings): block renderers must NOT emit hardcoded-language chrome.
A producer supplies any label in the content's language; absent → no label (the styling carries it).
So a report in ANY language renders with zero leaked English/Portuguese chrome."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import render  # noqa: E402

_BANNED = ("O que preciso saber", ">Gap<", "GAP", "Resumo Executivo", "Input:", "Output:",
           "ABERTO", "Derivacao")


def _clean(html):
    for b in _BANNED:
        assert b not in html, f"hardcoded-language chrome leaked: {b!r} in {html[:200]!r}"


class GapFamilyNoHardcodedChrome(unittest.TestCase):
    def test_gap_table_no_headers_renders_no_pt_chrome(self):
        h = render.render_block({"type": "gap-table", "gaps": [
            {"description": "a semântica de partial não está fixada"},
            {"description": "falta a fórmula de similaridade"}]})
        _clean(h)
        self.assertIn("semântica de partial", h)   # the in-language content is there
        self.assertNotIn("<th>", h)                 # no header row when none provided

    def test_gap_table_dict_shape_renders_all_fields_no_misalignment(self):
        # Shape (1): semantic dicts → a clean list. No columns to misalign; every field is shown,
        # the status text is the producer's own in-language value (only the CSS color is mapped).
        h = render.render_block({"type": "gap-table",
                                 "gaps": [{"description": "a desc", "need": "o need", "status": "aberto"}]})
        self.assertIn("a desc", h)
        self.assertIn("o need", h)
        self.assertIn("ABERTO", h)                  # status badge (in-language text, mapped color)
        self.assertNotIn("O que preciso saber", h)  # no hardcoded column chrome

    def test_gap_table_headers_without_rows_are_ignored_gaps_still_render(self):
        # REGRESSION (codex P2): NO headers+gaps(dicts) hybrid — positional mapping misaligns on an
        # id column. Headers without rows are dropped; the gaps still render in full as the list.
        h = render.render_block({"type": "gap-table",
                                 "headers": ["ID", "Lacuna", "Need", "Estado"],
                                 "gaps": [{"id": "7", "description": "a desc", "need": "o need",
                                           "status": "aberto"}]})
        self.assertIn("a desc", h)                  # the gap content is never dropped
        self.assertIn("o need", h)
        self.assertNotIn("<th>", h)                 # the unusable headers are ignored, not mis-mapped

    def test_gap_table_list_preserves_ids(self):
        # REGRESSION (codex P2): an `id` is language-neutral and pairs with gap-resolution.gap_id —
        # the list renderer must keep it (as "#id"), not drop it.
        h = render.render_block({"type": "gap-table",
                                 "gaps": [{"id": "G2", "description": "a lacuna"}]})
        self.assertIn("#G2", h)
        self.assertIn("a lacuna", h)

    def test_gap_table_custom_rows_win(self):
        # Shape (2): headers+rows is the custom-table escape hatch — cells are pre-laid-out, never misaligned.
        h = render.render_block({"type": "gap-table", "headers": ["A", "B"],
                                 "rows": [["x", "y"]], "gaps": [{"description": "ignored"}]})
        self.assertIn("<th>", h)
        self.assertIn("x", h)
        self.assertNotIn("ignored", h)              # rows win; the gaps dict is not double-rendered

    def test_gap_marker_no_hardcoded_label(self):
        h = render.render_block({"type": "gap-marker", "text": "uma lacuna em aberto"})
        self.assertNotIn("GAP", h)
        self.assertIn("uma lacuna em aberto", h)

    def test_gap_marker_label_synonym_renders_as_body_no_collision(self):
        # REGRESSION (codex P2): `label` is a SYNONYM for the gap body `text` (BLOCK_SCHEMAS) — it is
        # canonicalized into `text`, so it renders as the body and does NOT vanish into a dead badge.
        h = render.render_block({"type": "gap-marker", "label": "uma lacuna real"})
        self.assertIn("uma lacuna real", h)
        self.assertNotIn("GAP", h)

    def test_gap_marker_id_is_structural_tag(self):
        h = render.render_block({"type": "gap-marker", "text": "corpo", "id": "3"})
        self.assertIn("#3", h)                       # language-neutral structural tag
        self.assertIn("corpo", h)

    def test_gap_resolution_no_hardcoded_label(self):
        h = render.render_block({"type": "gap-resolution", "gap": "a dúvida", "answer": "a resposta"})
        self.assertNotIn(">Gap<", h)
        self.assertNotIn("Gap #", h)


class OtherChromeIsOptional(unittest.TestCase):
    def test_flow_example_no_hardcoded_input_output(self):
        h = render.render_block({"type": "flow-example", "input": "entrada", "output": "saída"})
        self.assertNotIn("Input:", h)
        self.assertNotIn("Output:", h)

    def test_executive_summary_no_hardcoded_heading(self):
        h = render.render_executive_summary(["um ponto", "outro ponto"])
        self.assertNotIn("Resumo Executivo", h)
        h2 = render.render_executive_summary(["x"], title="Resumo")  # producer label honored
        self.assertIn("Resumo", h2)

    def test_derivation_no_default_label(self):
        h = render.render_block({"type": "derivation", "bullets": ["um passo do raciocínio"]})
        self.assertNotIn("Derivacao", h)
        self.assertIn("raciocínio", h)


if __name__ == "__main__":
    unittest.main()
