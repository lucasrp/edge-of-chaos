"""Slice 1 — STRUCTURE NOT STRINGS (ed-research). The conductor emits its closing rich-rite moves as
BLOCKS (a `derivation` block + a `gap-table` block) satisfied BY TYPE, with NO hardcoded-language
scaffold labels and NO per-language keyword markers — so a report in ANY language clears the gate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import conductor  # noqa: E402
import close  # noqa: E402

# Literals that must NEVER appear (the old hardcoded English scaffold AND any hardcoded label map).
_BANNED_LITERALS = ("Why this holds", "Open questions", "What I don't know", "The through-line",
                    "From the mined findings", "Why this matters", "The finding",
                    "What this changes", "What remains uncertain")
_PT_OBJ = "Estruturar o factor hierarchy jurídico do CASOX para retrieval de jurisprudência do ORGX"


def _nodes():
    return [{"id": "n1", "role": "deliver", "title": "O achado central",
             "contract": {"intent": "x", "finding_ids": ["f0"]},
             "blocks": [{"type": "paragraph", "text": "Prosa em português desenvolvida sobre o tema."}],
             "digest": {"bullets": [], "assumed_prior": "a semântica de partial não está fixada",
                        "contribution": "desenvolve o achado central do factor hierarchy",
                        "cross_refs": []}}]


def _seed():
    return {"findings": [{"claim": "fator é schema discreto", "bears_on": "retrieval", "citation": "doc"}],
            "residuals": ["a semântica de partial não está fixada"]}


def _all_text(spec):
    out = []
    for s in spec["sections"]:
        out.append(s.get("title", ""))
        for b in s["blocks"]:
            for v in b.values():
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, list):
                    out += [x for x in v if isinstance(x, str)]
    return " ".join(out)


class StructureNotStrings(unittest.TestCase):
    def test_no_hardcoded_language_scaffold_literals(self):
        spec = conductor.assemble(_nodes(), _seed(), _PT_OBJ)
        text = _all_text(spec)
        for lit in _BANNED_LITERALS:
            self.assertNotIn(lit, text, f"hardcoded scaffold literal leaked: {lit!r}")

    def test_closing_moves_are_blocks_not_a_callout(self):
        spec = conductor.assemble(_nodes(), _seed(), _PT_OBJ)
        types = [b.get("type") for s in spec["sections"] for b in s["blocks"]]
        self.assertIn("derivation", types)   # derivation move = a derivation BLOCK
        self.assertIn("gap-table", types)    # what-i-dont-know = a gap-table BLOCK (not an EN callout)

    def test_scaffold_section_titles_are_unlabeled(self):
        spec = conductor.assemble(_nodes(), _seed(), _PT_OBJ)
        self.assertEqual(spec["sections"][-1]["title"], "")
        self.assertEqual(spec["sections"][-2]["title"], "")

    def test_rich_rite_satisfied_by_block_type_without_markers(self):
        # >=3 prose blocks TRIGGER the rich-rite floor; the derivation + gap-table BLOCKS then satisfy
        # the moves BY TYPE — the PT content carries NO English markers, proving language-agnostic pass.
        content = {"sections": [{"title": "", "blocks": [
            {"type": "paragraph", "text": "Parágrafo um, prosa desenvolvida em português sobre o tema."},
            {"type": "paragraph", "text": "Parágrafo dois, continuação da prosa em português."},
            {"type": "paragraph", "text": "Parágrafo três, fechando a prosa desenvolvida."},
            conductor._findings_derivation(_seed(), _PT_OBJ),
            conductor._residual_gaps(_seed())]}]}
        art = {"content": content, "intent": _PT_OBJ,
               "cites": [{"ref": "r", "kind": "mundo", "snippet": "s"}],
               "proposes": [{"body": _PT_OBJ, "kind": "thread"}], "distills": ["cluster:conductor"]}
        strikes = close._check_rich_rite(art)
        self.assertFalse(any("derivation" in s for s in strikes), f"derivation strike: {strikes}")
        self.assertFalse(any("what-i-dont-know" in s for s in strikes), f"boundary strike: {strikes}")

    def test_no_lang_detector_or_label_map_exists(self):
        # the hardcoded-language machinery is GONE (ed-research: structure not strings).
        for attr in ("_LABELS", "_lang", "_labels", "_PT_HINT", "_PT_ACCENT"):
            self.assertFalse(hasattr(conductor, attr), f"hardcoded-language artifact still present: {attr}")

    def test_substantive_is_language_agnostic_for_cjk(self):
        # codex P2: a CJK contribution (no inter-word spaces) must count as substantive, else the
        # derivation block is wrongly dropped for non-spaced languages.
        cjk = "知识图谱检索增强生成系统的核心机制与权衡分析"  # >=15 chars, one split() token
        self.assertTrue(conductor._substantive(cjk))
        self.assertFalse(conductor._substantive("D"))           # still drops a fragment
        deriv = conductor._digest_derivation([{"digest": {"contribution": cjk}}])
        self.assertEqual(deriv["type"], "derivation")
        self.assertIn(cjk, deriv["bullets"])

    def test_digest_derivation_returns_none_on_all_junk_digests(self):
        # REGRESSION (codex P2): when every digest contribution is truncated/garbled (fails
        # _substantive), emit NO derivation block — rendering one-letter fragments would reintroduce
        # the junk the filter suppresses. None lets the close gate flag the move honestly.
        junk = [{"id": "n1", "digest": {"contribution": "D"}},
                {"id": "n2", "digest": {"contribution": "."}}]
        self.assertIsNone(conductor._digest_derivation(junk))
        # a real contribution still yields a block
        real = [{"id": "n3", "digest": {"contribution": "desenvolve o achado central do factor hierarchy"}}]
        self.assertEqual(conductor._digest_derivation(real)["type"], "derivation")


if __name__ == "__main__":
    unittest.main()
