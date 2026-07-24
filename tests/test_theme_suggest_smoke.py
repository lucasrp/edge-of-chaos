"""Smoke: dual metric + install-domain ranking for theme choice.

Operator 2026-07-24: Δ mente first; themes ranked in *this* install's domain
(mission + Direction set); Direction is denylist/profile not ticket seed.
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


class DomainRanking(unittest.TestCase):
    def test_legal_mission_prefers_legal_ir_over_unrelated(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text(
                'name: roberto\nmission: "Mentor for legal retrieval and jurisprudential search systems"\n',
                encoding="utf-8",
            )
            (home / "state").mkdir()
            (home / "state" / "direction.md").write_text(
                "## Set — curated (Voz)\n\n"
                "- **[phase]** Agent UX for legal search navigation and explanation\n"
                "- **[priority]** Retrieval index quality for rare high-stakes queries\n",
                encoding="utf-8",
            )
            (home / "blog" / "entries").mkdir(parents=True)
            ctx = ts.load_install_context(home)
            self.assertIn("legal_ir", ctx["facets"])
            cards = ts.suggest_themes(edge_home=home, n=6)
            self.assertGreaterEqual(len(cards), 3)
            top = " ".join(c["title"].lower() for c in cards[:3])
            # legal/search/judge/retrieval family should surface early
            self.assertTrue(
                any(
                    k in top
                    for k in ("search", "judge", "retrieval", "containment", "legal", "mean", "individualization")
                ),
                f"legal domain should rank domain themes early, got: {top}",
            )
            for c in cards:
                self.assertIn("roberto", c["apply"].lower())
                self.assertIn("mission:", c["apply"].lower())

    def test_mentor_mission_prefers_memory_mentor_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text(
                'name: ed\nmission: "Mentor to the edge-of-chaos PM: compare intended behavior with runtime evidence"\n',
                encoding="utf-8",
            )
            (home / "state").mkdir()
            (home / "state" / "direction.md").write_text(
                "## Set — curated (Voz)\n\n"
                "- **[phase]** Build introspective memory and cortex recall\n"
                "- **[priority]** Mentor knows-years continuity, not PM ticket collapse\n",
                encoding="utf-8",
            )
            (home / "blog" / "entries").mkdir(parents=True)
            ctx = ts.load_install_context(home)
            self.assertTrue(ctx["facets"] & {"mentor", "agent_memory", "rite_agency"})
            cards = ts.suggest_themes(edge_home=home, n=6)
            top = " ".join(c["title"].lower() for c in cards[:4])
            self.assertTrue(
                any(
                    k in top
                    for k in ("memory", "mentor", "mentee", "staleness", "operator", "eval theater", "draft", "context")
                ),
                f"mentor domain should rank memory/mentor themes early, got: {top}",
            )

    def test_direction_ticket_lines_do_not_enter_domain_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "agent.yaml").write_text('name: x\nmission: "general product mentor"\n', encoding="utf-8")
            (home / "state").mkdir()
            (home / "state" / "direction.md").write_text(
                "## Set — curated (Voz)\n\n"
                "- **[priority]** exp003 G0 placar thrash sitting-par1 hard-stop\n"
                "- **[phase]** Shipável mentor continuity for the operator\n",
                encoding="utf-8",
            )
            (home / "blog" / "entries").mkdir(parents=True)
            ctx = ts.load_install_context(home)
            # redigest line dropped from direction_set text
            self.assertNotIn("placar", ctx["direction_set"].lower())
            self.assertIn("shipável", ctx["direction_set"].lower() + ctx["direction_set"].lower())


class SuggestSmoke(unittest.TestCase):
    def test_default_pool_yields_enough_world_themes(self):
        cards = ts.suggest_themes(edge_home=None, n=8)
        self.assertGreaterEqual(len(cards), 4)
        for c in cards:
            self.assertEqual(ts.validate_card(c, stems=[]), [])
            self.assertFalse(ts.is_activity_redigest(c["title"]))
            self.assertTrue(c.get("mind_open", "").strip())
            self.assertEqual(c["policy"]["primary_metric"], "mind-open-bom-para-mim")

    def test_prefer_mind_open_surfaces_strategic_first(self):
        cards = ts.suggest_themes(edge_home=None, n=6, prefer_mind_open=True)
        top_shapes = {c["shape"] for c in cards[:4]}
        self.assertTrue(
            top_shapes & {"strategic_bet", "operator_self", "field_pattern", "product_altitude"},
        )

    def test_recent_g0_corpus_does_not_seed_redigest(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = Path(tmp) / "blog" / "entries"
            entries.mkdir(parents=True)
            (Path(tmp) / "agent.yaml").write_text('name: ed\nmission: "mentor"\n', encoding="utf-8")
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
        self.assertEqual(ts.suggest_themes(edge_home=None, n=5, pool=poison), [])

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
        self.assertEqual(ts.suggest_themes(edge_home=None, n=5, pool=poison), [])
        self.assertIn("code-only-apply", ts.validate_card(poison[0], stems=[]))

    def test_markdown_and_cli_smoke_on_real_edge_home(self):
        cards = ts.suggest_themes(edge_home=REPO, n=6)
        self.assertGreaterEqual(len(cards), 4, "real blog denylist wiped the world pool")
        md = ts.format_markdown(cards, ctx=ts.load_install_context(REPO))
        self.assertIn("Δ mente", md)
        self.assertIn("domain", md.lower())
        self.assertEqual(ts.main(["--edge-home", str(REPO), "-n", "6"]), 0)

    def test_form_filter_research(self):
        cards = ts.suggest_themes(edge_home=None, n=5, form="research")
        self.assertTrue(cards)
        for c in cards:
            self.assertEqual(c["form"], "research")


if __name__ == "__main__":
    unittest.main()
