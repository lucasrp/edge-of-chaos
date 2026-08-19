"""ADR-0014 — recall is a THIRD INDEPENDENT BRIEF at pre-dispatch, fanned beside assemble and
delta, never fused with either. The recall-push leaves the assemble briefing (4428c64 superseded):
`tools/recall.py` owns the salient-subgraph read AND the brief render; `compose_briefing` no longer
emits a recall section; the wake/pipeline fan THREE briefs; a `skills/recall` subagent exists.
The push seeds, navigation deepens (ADR-0011 reaffirmed: on-demand navigation is the loop's)."""

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import briefing   # noqa: E402
import recall     # noqa: E402

ROSTER_FIXTURE = REPO / "tests" / "fixtures" / "roster.agent.yaml"
MEMORY_FIXTURE = REPO / "seeds" / "memory"
"""A identidade DECLARADA destes testes — a fixture de roster e a doutrina canônica de seeds/.

`compose_briefing` é fail-closed (ADR-0009): sem personality/method/canone inscritos ele levanta
`BriefingIdentityError`. Por default ele lê o `memory/` e o `agent.yaml` DA CASA de quem roda a
suíte — e o genótipo, por contrato, não tem nenhum dos dois. Os dois testes abaixo, que só querem
saber se a perna de recall SAIU do briefing, morriam nessa recusa antes de olhar o texto. Com as
fixtures versionadas eles medem o composer, igual em qualquer host."""


class RecallSubgraphLivesInRecallModule(unittest.TestCase):
    """The salient-subgraph read moves out of briefing.py into tools/recall.py, keeping its
    degrade contract (None — never a crash) and its salience guards (cap, recency, retired-cluster
    filter) exactly as they were (Codex P2)."""

    def test_no_group_degrades_to_none(self):
        self.assertIsNone(recall.recall_subgraph(None))
        self.assertIsNone(recall.recall_subgraph(""))

    def test_unreachable_graph_degrades_to_none_without_crashing(self):
        self.assertIsNone(recall.recall_subgraph("any-group", uri="bolt://127.0.0.1:1"))

    def test_caps_and_orders_artefatos_by_recency(self):
        # the guards are asserted on the QUERY CONSTANTS the runtime executes — not on function
        # source, where a prose comment once satisfied the substring while the live query
        # regressed (review-proven mutation escape)
        self.assertTrue(recall.RECALL_ARTEFATO_LIMIT >= 1)
        self.assertLessEqual(recall.RECALL_ARTEFATO_LIMIT, 12,
                             "the recall slice must be a SMALL, salient slice, not the whole corpus")
        self.assertIn("LIMIT $lim", recall.ARTEFATOS_QUERY, "the cap must be in the live query")
        self.assertIn("ORDER BY coalesce(a.projected_at,'') DESC", recall.ARTEFATOS_QUERY,
                      "recency order must be in the live query, not a comment")
        self.assertIn("a.projection_complete = true", recall.ARTEFATOS_QUERY,
                      "only complete projections are reliable memory")
        self.assertIn("coalesce(a.kind,'published') <> 'asset'", recall.ARTEFATOS_QUERY,
                      "generated HTML/JS/data assets must not pollute salient Artefatos as no-kernel rows")
        import inspect
        src = inspect.getsource(recall.recall_subgraph)
        self.assertIn("s.run(_q(ARTEFATOS_QUERY)", src,
                      "recall_subgraph must execute the guarded constant (timeout-wrapped, N1/R3), "
                      "not an inline copy")

    def test_cluster_query_filters_retired_clusters(self):
        self.assertIn("coalesce(e.archived,false)=false", recall.CLUSTERS_QUERY)
        self.assertIn("e.merged_into IS NULL", recall.CLUSTERS_QUERY)
        import inspect
        src = inspect.getsource(recall.recall_subgraph)
        self.assertIn("s.run(_q(CLUSTERS_QUERY)", src,
                      "recall_subgraph must execute the guarded constant (timeout-wrapped, N1/R3), "
                      "not an inline copy")

    def test_experiment_query_orders_by_projected_sort_key_after_aggregation(self):
        # Regression: ORDER BY x.curated_at after collect(DISTINCT a.slug) is invalid Cypher because
        # x is no longer accessible after aggregation. The query must project the sort key first.
        self.assertIn("AS sort_key", recall.EXPERIMENTS_QUERY)
        self.assertIn("ORDER BY sort_key DESC, id", recall.EXPERIMENTS_QUERY)

    def test_recall_assets_are_companions_not_orphan_asset_noise(self):
        # The wake push should show assets as navigable companions of a parent Artefato. Full orphan/
        # standalone inventory stays available through cortex_assets.
        self.assertIn("MATCH (p:Artefato {group_id:$g})-[:HAS_ASSET]->(a)", recall.ASSETS_QUERY)

    def test_atividade_query_is_open_employment_spine_from_graph(self):
        """Agentic cortex-as-graph: open Atividade nodes ride the salient push (not only portfolio_at).

        Seam: ATIVIDADES_QUERY constant + recall_subgraph execution (same pattern as ARTEFATOS).
        Open/reaberta only — abandonada/cumprida stay out of the default spine.
        """
        self.assertTrue(hasattr(recall, "ATIVIDADES_QUERY"))
        self.assertTrue(hasattr(recall, "RECALL_ATIVIDADE_LIMIT"))
        self.assertGreaterEqual(recall.RECALL_ATIVIDADE_LIMIT, 1)
        self.assertLessEqual(recall.RECALL_ATIVIDADE_LIMIT, 16)
        q = recall.ATIVIDADES_QUERY
        self.assertIn(":Atividade", q)
        self.assertIn("group_id:$g", q)
        self.assertIn("aberta", q)
        self.assertIn("reaberta", q)
        self.assertIn("LIMIT $lim", q)
        self.assertIn("finalidade", q)
        import inspect
        src = inspect.getsource(recall.recall_subgraph)
        self.assertIn("s.run(_q(ATIVIDADES_QUERY)", src,
                      "recall_subgraph must execute ATIVIDADES_QUERY (graph employment spine)")


class ComposeRecallBriefIsTheThirdBrief(unittest.TestCase):
    """`compose_recall_brief` renders the memory-salient brief — a standalone surface, peer to the
    briefing and the delta. A pinned subgraph renders the salient spine; a dark graph renders an
    honest marker, never a crash (CONTRACT C1)."""

    def test_pinned_subgraph_renders_the_salient_spine(self):
        sub = {
            "codename": "ed", "voice": "direct, skeptical",
            "objective": "ship the producer floor",
            "bets": ["rich-rite property gates", "recall-push"],
            "artefatos": [{"slug": "recall-report", "kernel": "open: budget unnamed"}],
            "clusters": ["Introspective memory"],
            "experiments": [{"id": "exp040", "title": "Agentic navigation", "status": "closed",
                             "report_slug": "experiment-final-report"}],
            "assets": [{"slug": "experiment-final-report-html", "kind": "html",
                        "parent_slug": "experiment-final-report",
                        "page": "blog/entries/experiment-final-report.html"}],
            "atividades": [{"ref": "edge/atv-021", "num": "atv-021", "estado": "aberta",
                            "finalidade": "retomar assemble em artefatos", "tier": "llm_judged"}],
        }
        text = recall.compose_recall_brief(subgraph=sub)
        low = text.lower()
        self.assertIn("recall", low)
        self.assertIn("space 0", low)                          # rooted at space-0 / identity
        self.assertIn("ship the producer floor", text)         # objective
        self.assertIn("rich-rite property gates", text)        # a bet
        self.assertIn("recall-report", text)                   # a salient artefato
        self.assertIn("introspective memory", low)             # a salient cluster
        self.assertIn("exp040", text)                           # a native Experiment
        self.assertIn("experiment-final-report-html", text)      # a generated asset companion
        self.assertIn("memory.md", low)                        # recall-MORE-on-demand affordance
        self.assertIn("atv-021", text)                         # graph employment spine
        self.assertIn("retomar assemble em artefatos", text)
        self.assertIn("atividade", low)

    def test_dark_graph_renders_an_honest_marker_not_a_crash(self):
        text = recall.compose_recall_brief(subgraph=None)
        low = text.lower()
        self.assertIn("dark", low)
        self.assertIn("memory.md", low)

    def test_auto_fetch_degrades_to_the_dark_marker_without_a_group(self):
        # no group resolvable → subgraph None → dark marker; NEVER an exception
        text = recall.compose_recall_brief(group="")
        self.assertIn("dark", text.lower())


class BriefingNoLongerCarriesTheRecallLeg(unittest.TestCase):
    """ADR-0014 amends ADR-0009: the briefing returns to its four parts. compose_briefing emits no
    recall section and owns no subgraph leg — the fattest surface stops growing a fifth view."""

    def test_compose_briefing_emits_no_recall_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl", clusters=None, roster=[],
                agent_yaml=ROSTER_FIXTURE, memory=MEMORY_FIXTURE)
            self.assertNotIn("recall — your own memory", text.lower())

    def test_briefing_module_no_longer_owns_the_subgraph_leg(self):
        self.assertFalse(hasattr(briefing, "recall_subgraph"),
                         "recall_subgraph must move to tools/recall.py (ADR-0014)")
        self.assertFalse(hasattr(briefing, "_section_recall"),
                         "the recall section renderer must leave briefing.py (ADR-0014)")

    def test_briefing_is_not_thinned_otherwise(self):
        # the four parts all survive the extraction — only the recall leg leaves
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl", clusters=None, roster=[],
                agent_yaml=ROSTER_FIXTURE, memory=MEMORY_FIXTURE)
            low = text.lower()
            for marker in ("objective — the anchor", "1. direction", "2. what is open",
                           "3. corpus", "4. source orientation", "5. knowledge clusters", "recap"):
                self.assertIn(marker, low, f"the extraction thinned the briefing: missing {marker!r}")


class TheThreeBriefFanIsPinnedInProse(unittest.TestCase):
    """The skills now match the ADR (its consequences section recorded the lag; this closes it):
    a skills/recall subagent exists, the wake fans FOUR briefs (quente joined as the 4th aperture,
    wake-only — the beat's pipeline stays assemble + delta + recall), and assemble no longer
    claims the push."""

    def test_recall_skill_exists_and_documents_the_push(self):
        skill = (REPO / "skills" / "recall" / "SKILL.md").read_text(encoding="utf-8").lower()
        for token in ("salient subgraph", "space 0", "memory-salient", "read-only",
                      "memory.md", "compose_recall_brief"):
            self.assertIn(token, skill, f"recall SKILL.md missing token: {token!r}")
        self.assertIn("never", skill)  # the delta-fusion ban is stated

    def test_wake_fans_four_briefs(self):
        skill = (REPO / "skills" / "wake" / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertIn("four briefs", skill)
        self.assertIn("recall", skill)
        self.assertIn("quente", skill)
        self.assertIn("adr-0014", skill)

    def test_wake_first_turn_is_bounded_orientation_only(self):
        skill = (REPO / "skills" / "wake" / "SKILL.md").read_text(encoding="utf-8").lower()
        for invariant in (
            "first-turn hard boundary",
            "only the four briefs",
            "do not inspect mentor",
            "exactly one short question",
            "wait for the operator's reply",
        ):
            self.assertIn(invariant, skill)

    def test_wake_must_degrade_and_close_instead_of_auditing_dependencies(self):
        skill = (REPO / "skills" / "wake" / "SKILL.md").read_text(encoding="utf-8").lower()
        for invariant in (
            "bounded execution contract",
            "do not open a dependency audit",
            "neo4j",
            "context compaction",
            "do not repeat discovery",
            "mandatory closure",
            "chosen direction",
            "next action",
        ):
            self.assertIn(invariant, skill)

    def test_pipeline_predispatch_fans_assemble_delta_recall(self):
        pipeline = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8").lower()
        self.assertIn("assemble + delta + recall", pipeline)

    def test_assemble_no_longer_claims_the_push(self):
        skill = (REPO / "skills" / "assemble" / "SKILL.md").read_text(encoding="utf-8").lower()
        self.assertNotIn("recall-push", skill)
        self.assertIn("adr-0014", skill)  # it points to where the leg went


class SemanticSearchIsACommonGraphEntry(unittest.TestCase):
    """Dual entry (operator 2026-07-13): wake defaults at space-0, but any task may jump in via
    common semantic search over projected Artefato embeddings — not only navigate from Genesis."""

    def test_semantic_artefatos_query_is_complete_with_embedding(self):
        self.assertTrue(hasattr(recall, "SEMANTIC_ARTEFATOS_QUERY"))
        q = recall.SEMANTIC_ARTEFATOS_QUERY
        self.assertIn(":Artefato", q)
        self.assertIn("group_id:$g", q)
        self.assertIn("a.embedding IS NOT NULL", q)
        self.assertIn("projection_complete = true", q)
        self.assertIn("RETURN a.slug", q)

    def test_semantic_search_ranks_by_cosine_with_injected_embedder(self):
        # Unit vectors: query matches "hit" exactly; "miss" is orthogonal.
        corpus = [
            {"slug": "hit", "kernel": "graph entry semantic", "embedding": [1.0, 0.0, 0.0]},
            {"slug": "miss", "kernel": "unrelated noise", "embedding": [0.0, 1.0, 0.0]},
        ]

        def embed_fn(_text):
            return [1.0, 0.0, 0.0]

        hits = recall.semantic_search(
            "where is graph entry",
            group="test-group",
            limit=2,
            embed_fn=embed_fn,
            corpus=corpus,
        )
        self.assertIsNotNone(hits)
        self.assertEqual(hits[0]["slug"], "hit")
        self.assertGreater(hits[0]["score"], 0.99)
        self.assertEqual(hits[1]["slug"], "miss")
        self.assertLess(hits[1]["score"], 0.1)

    def test_semantic_search_dark_without_query_or_corpus(self):
        self.assertIsNone(recall.semantic_search("", group="g", corpus=[]))
        self.assertIsNone(recall.semantic_search("x", group="g", corpus=[]))
        self.assertIsNone(recall.semantic_search(None, group="g", corpus=[{"slug": "a", "embedding": [1.0]}]))

    def test_compose_semantic_brief_renders_hits_and_dark(self):
        hits = [{"slug": "hit-report", "kernel": "open: dual entry", "score": 0.91}]
        text = recall.compose_semantic_brief("dual entry", hits=hits)
        self.assertIn("semantic", text.lower())
        self.assertIn("hit-report", text)
        self.assertIn("0.91", text)
        dark = recall.compose_semantic_brief("anything", hits=None)
        self.assertIn("dark", dark.lower())


if __name__ == "__main__":
    unittest.main()
