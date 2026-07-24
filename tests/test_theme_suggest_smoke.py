"""Smoke: theme suggestions imitate old edge-of-chaos (world-new), not activity redigest.

Locks the policy discussed with the operator (2026-07-24):
- themes must look like portable world knowledge applied at altitude
- Direction/open-bet vocabulary is denylist, not seed
- recent self-corpus stems filter overlap; they do not generate titles
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

    def test_world_title_is_not_redigest(self):
        self.assertFalse(
            ts.is_activity_redigest(
                "How modern LLM prompt caching actually works (and when it silently dies)"
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
            self.assertIn(c["form"], ("report", "research", "map", "plan", "discovery"))

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
        }]
        cards = ts.suggest_themes(edge_home=None, n=5, pool=poison)
        self.assertEqual(cards, [])

    def test_markdown_and_cli_smoke_on_real_edge_home(self):
        """Live install smoke: denylist real entries, still emit old-edge-shaped themes."""
        cards = ts.suggest_themes(edge_home=REPO, n=6)
        self.assertGreaterEqual(len(cards), 4, "real blog denylist wiped the world pool")
        md = ts.format_markdown(cards)
        self.assertIn("old-edge shape", md)
        self.assertIn("world hook", md.lower())
        # CLI exit 0
        rc = ts.main(["--edge-home", str(REPO), "-n", "6"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
