"""Smoke: theme suggestions use dual metric (Δ mente first), not activity redigest.

Locks the policy discussed with the operator (2026-07-24):
- primary metric = abertura / bom-para-mim (mind_open), not code utility alone
- themes look like portable world / strategic vision applied at human altitude
- Direction/open-bet vocabulary is denylist, not seed
- recent self-corpus stems filter overlap; they do not generate titles
- code-only apply lines are rejected
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import theme_suggest as ts  # noqa: E402


class RedigestDetection(unittest.TestCase):
    def test_ticket_vocabulary_is_redigest(self):
        self.assertTrue(ts.is_activity_redigest("exp003 G0 placar sitting-par1 hard-stop"))
        self.assertTrue(ts.is_activity_redigest("open-compare arm_id output.html thrash"))
        self.assertTrue(ts.is_activity_redigest("o que se liga no próximo ciclo experimental"))

    def test_world_title_is_not_redigest(self):
        self.assertFalse(
            ts.is_activity_redigest(
                "How modern LLM prompt caching actually works (and when it silently dies)"
            )
        )
        self.assertFalse(
            ts.is_activity_redigest(
                "The end of search as product: navigation + explanation as the real unit"
            )
        )


class CodeOnlyApply(unittest.TestCase):
    def test_path_apply_is_code_only(self):
        self.assertTrue(ts.is_code_only_apply("Patch tools/close.py and add unit test"))
        self.assertTrue(ts.is_code_only_apply("Continue the open bet next arm"))

    def test_human_altitude_apply_is_not_code_only(self):
        self.assertFalse(
            ts.is_code_only_apply(
                "Whether the operator's identity is ranker-builder or navigator-for-signed-trust."
            )
        )


class SelfCorpusOverlap(unittest.TestCase):
    def test_overlap_with_recent_stems(self):
        stems = ["exp003-fase-flip-eval-e-o-ticket", "mapa-g0-nao-e-aresta-do-beat"]
        self.assertTrue(
            ts.overlaps_self_corpus("exp003 fase flip eval ticket again", stems, min_shared=3)
        )
        self.assertFalse(
            ts.overlaps_self_corpus("prompt caching unit economics", stems, min_shared=3)
        )


class SuggestSmoke(unittest.TestCase):
    def test_default_pool_yields_enough_world_themes(self):
        cards = ts.suggest_themes(edge_home=None, n=8)
        self.assertGreaterEqual(len(cards), 4)
        for c in cards:
            self.assertEqual(ts.validate_card(c, stems=[]), [])
            self.assertFalse(ts.is_activity_redigest(c["title"]))
            self.assertTrue(c["world_hook"].strip())
            self.assertTrue(c["unknown"].strip())
            self.assertTrue(c.get("mind_open", "").strip(), "dual metric requires mind_open")
            self.assertFalse(ts.is_code_only_apply(c["apply"]))
            self.assertIn(c["form"], ("report", "research", "map", "plan", "discovery"))
            self.assertEqual(c["policy"]["primary_metric"], "mind-open-bom-para-mim")

    def test_prefer_mind_open_surfaces_strategic_first(self):
        cards = ts.suggest_themes(edge_home=None, n=6, prefer_mind_open=True)
        self.assertGreaterEqual(len(cards), 4)
        # First cards should lean strategic / operator / field, not only mechanism
        top_shapes = {c["shape"] for c in cards[:4]}
        self.assertTrue(
            top_shapes & {"strategic_bet", "operator_self", "field_pattern", "product_altitude"},
            f"expected mind-open shapes early, got {top_shapes}",
        )

    def test_recent_g0_corpus_does_not_seed_redigest(self):
        """Even with a G0-heavy blog dir, suggestions stay world-first (denylist only)."""
        with tempfile.TemporaryDirectory() as tmp:
            entries = Path(tmp) / "blog" / "entries"
            entries.mkdir(parents=True)
            for stem in (
                "exp003-g0-agora",
                "exp003-sitting-par1-placar",
                "mapa-g0-nao-e-aresta-do-beat",
                "hstar-existe-so-no-disco",
                "open-compare-par1-natural-g-r0",
            ):
                (entries / f"{stem}.html").write_text("<html></html>\n", encoding="utf-8")
            cards = ts.suggest_themes(edge_home=Path(tmp), n=8)
            self.assertGreaterEqual(len(cards), 4)
            for c in cards:
                self.assertFalse(ts.is_activity_redigest(c["title"] + " " + c["apply"]))
                self.assertNotIn("placar", c["title"].lower())
                self.assertNotIn("g0", c["title"].lower())

    def test_poisoned_pool_card_is_rejected(self):
        poison = [{
            "shape": "mechanism",
            "form": "report",
            "title": "exp003 G0 placar hard-stop thrash sitting-par1",
            "unknown": "x",
            "world_hook": "arxiv paper on nothing",
            "apply": "continue the open bet",
            "mind_open": "none",
        }]
        cards = ts.suggest_themes(edge_home=None, n=5, pool=poison)
        self.assertEqual(cards, [])

    def test_code_only_apply_card_is_rejected(self):
        poison = [{
            "shape": "mechanism",
            "form": "research",
            "title": "A clean world mechanism about retrieval fusion",
            "unknown": "something new about fusion",
            "world_hook": "public paper on fusion methods",
            "apply": "Edit tools/close.py and land the next arm unit test",
            "mind_open": "would have been good but apply is code-only",
        }]
        cards = ts.suggest_themes(edge_home=None, n=5, pool=poison)
        self.assertEqual(cards, [])
        self.assertIn("code-only-apply", ts.validate_card(poison[0], stems=[]))

    def test_markdown_and_cli_smoke_on_real_edge_home(self):
        """Live install smoke: denylist real entries, still emit dual-metric themes."""
        cards = ts.suggest_themes(edge_home=REPO, n=6)
        self.assertGreaterEqual(len(cards), 4, "real blog denylist wiped the world pool")
        md = ts.format_markdown(cards)
        self.assertIn("dual metric", md.lower())
        self.assertIn("mind_open", md.lower())
        self.assertIn("world hook", md.lower())
        # CLI exit 0
        rc = ts.main(["--edge-home", str(REPO), "-n", "6"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
