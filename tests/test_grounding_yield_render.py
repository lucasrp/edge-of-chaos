"""S7 render surfaces — the briefing advisory block (never-blank via seed rows, NOT pseudo-events)
and the /sources panel adapter (E8: the roster is DATA — a never-seen declared source is a visible
dead leg with zero code change). Sibling of test_grounding_yield.py (the fold) — this pins §4/§5.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog          # noqa: E402
import grounding_yield   # noqa: E402
from _blog_env import guard_blog_env


class BriefingNeverBlank(unittest.TestCase):
    def test_empty_log_renders_seed_rows_not_pseudo_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            log.write_text("")  # no manifest, no cells
            roadmap = Path(tmp) / "roadmap.md"
            roadmap.write_text(
                "## exa — neural search\n\n"
                "- **yield notes**:\n"
                "  - 2026-07-01 [seed:loopR-2026-07-01] deep excellent on NAMED ENTITIES\n")
            block = grounding_yield.briefing_yield_block(log=log, roadmap=roadmap,
                                                         hsmap={})
            self.assertIn("seed", block.lower())
            self.assertIn("NAMED ENTITIES", block)
            # SEED is prose — it must NEVER have written an event into the log (ADR-0006)
            self.assertEqual(log.read_text(), "")

    def test_crossed_cell_replaces_the_seed_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("dispatch.open", "dispatch",
                            {"dispatch_id": "d1", "intent": "research", "geometry": "themed"}, log=log)
            for i in range(5):
                eventlog.append("grounding.manifest", "grounding",
                                {"raw_ref": ["s", i, f"t{i}", 0], "source": "exa",
                                 "interface": "search-deep", "lens": "mundo", "geometry": "gather",
                                 "attribution": "mapped", "hits": 3, "dispatch_id": "d1",
                                 "recognizer_rev": 1}, log=log)
            eventlog.append("artefato.published", "artefato:a",
                            {"slug": "a", "dispatch_id": "d1", "skill": "research"}, log=log)
            eventlog.append("source.signal", "artefato:a",
                            {"slug": "a", "ref": "https://api.exa.ai/x", "kind": "mundo",
                             "similarity": 0.9}, log=log)
            block = grounding_yield.briefing_yield_block(
                log=log, hsmap={"api.exa.ai": "exa"})
            self.assertIn("research → exa/search-deep", block)
            self.assertIn("util", block)

    def test_below_min_cell_backs_off_to_source_marginal_floor(self):
        # a cell with 2 attempts (< min 5) is EXPLORE, but its source HAS a populated marginal
        # (its own cited sim) → the advice degrades to the source-level floor, not silence.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("dispatch.open", "dispatch",
                            {"dispatch_id": "d1", "intent": "research", "geometry": "themed"},
                            log=log)
            for i in range(2):
                eventlog.append("grounding.manifest", "grounding",
                                {"raw_ref": ["s", i, f"t{i}", 0], "source": "exa",
                                 "interface": "search-deep", "lens": "mundo", "geometry": "gather",
                                 "attribution": "mapped", "hits": 3, "dispatch_id": "d1",
                                 "recognizer_rev": 1}, log=log)
            eventlog.append("artefato.published", "artefato:a",
                            {"slug": "a", "dispatch_id": "d1", "skill": "research"}, log=log)
            eventlog.append("source.signal", "artefato:a",
                            {"slug": "a", "ref": "https://api.exa.ai/x", "kind": "mundo",
                             "similarity": 0.5}, log=log)
            block = grounding_yield.briefing_yield_block(log=log, hsmap={"api.exa.ai": "exa"})
            self.assertIn("EXPLORE (n=2<5)", block)   # the cell label stays honest
            self.assertIn("fonte: util", block)        # …but the source-marginal floor is visible

    def test_below_min_cell_with_no_marginal_falls_to_seed(self):
        # the only cell is a seca-suspeita (hits=0) → no scoring attempt → the source marginal is
        # unpopulated (mean_sim None). No bare EXPLORE line; the advice falls to the seed roster.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("dispatch.open", "dispatch",
                            {"dispatch_id": "d1", "intent": "research", "geometry": "themed"},
                            log=log)
            eventlog.append("grounding.manifest", "grounding",
                            {"raw_ref": ["s", 1, "t1", 0], "source": "exa",
                             "interface": "search-deep", "lens": "mundo", "geometry": "gather",
                             "attribution": "mapped", "hits": 0, "dry": "suspect",
                             "dispatch_id": "d1", "recognizer_rev": 1}, log=log)
            roadmap = Path(tmp) / "roadmap.md"
            roadmap.write_text(
                "## exa — neural search\n\n"
                "- **yield notes**:\n"
                "  - 2026-07-01 [seed:loopR-2026-07-01] deep excellent on NAMED ENTITIES\n")
            block = grounding_yield.briefing_yield_block(
                log=log, roadmap=roadmap, hsmap={"api.exa.ai": "exa"})
            self.assertIn("seed", block.lower())      # backed off to the roster floor
            self.assertNotIn("fonte: util", block)    # no source-level floor to give
            self.assertNotIn("EXPLORE", block)         # and no bare cell line either

    def test_source_less_explore_cell_renders_no_arrow_none(self):
        # a manifest with no source → a source-less cell must never render `→ None` (cosmetic).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.append("dispatch.open", "dispatch",
                            {"dispatch_id": "d1", "intent": "research", "geometry": "themed"},
                            log=log)
            eventlog.append("grounding.manifest", "grounding",
                            {"raw_ref": ["s", 1, "t1", 0], "source": None,
                             "interface": "search-deep", "lens": "mundo", "geometry": "gather",
                             "attribution": "mapped", "hits": 3, "dispatch_id": "d1",
                             "recognizer_rev": 1}, log=log)
            block = grounding_yield.briefing_yield_block(log=log, hsmap={})
            self.assertNotIn("→ None", block)


_AGENT_YAML = """\
name: tester
mission: test the yield panel
voice: dry
sources:
  - name: exa
    kind: api
    description: >-
      Neural search. Lens Mundo.
    interfaces:
      - interface_id: search-deep
        via: "POST https://api.exa.ai/search"
  - name: overleaf
    kind: api
    description: >-
      A NEVER-SEEN declared source (the E8 Overleaf test). Lens Atividade.
    interfaces:
      - interface_id: read
        via: "GET https://api.overleaf.com/v1/projects"
        installed: false
"""


class SourcesPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "agent.yaml").write_text(_AGENT_YAML)
        (root / "entries").mkdir()
        (root / "secrets").mkdir()
        log = root / "log.jsonl"
        rows = []
        seq = 0

        def ev(t, subj, payload):
            nonlocal seq
            seq += 1
            rows.append(json.dumps({"seq": seq, "ts": f"2026-07-01T00:00:{seq:02d}+00:00",
                                    "type": t, "subject": subj, "payload": payload}))
        ev("dispatch.open", "dispatch", {"dispatch_id": "d1", "intent": "research",
                                         "geometry": "themed"})
        ev("grounding.manifest", "grounding",
           {"raw_ref": ["s", 1, "t1", 0], "source": "exa", "interface": "search-deep",
            "lens": "mundo", "geometry": "gather", "attribution": "mapped", "hits": 3,
            "dispatch_id": "d1", "recognizer_rev": 1})
        ev("artefato.published", "artefato:a", {"slug": "a", "dispatch_id": "d1",
                                                "skill": "research"})
        ev("source.signal", "artefato:a", {"slug": "a", "ref": "https://api.exa.ai/x",
                                            "kind": "mundo", "similarity": 0.7})
        log.write_text("\n".join(rows) + "\n")

        guard_blog_env(self)
        os.environ["EDGE_BLOG_ENTRIES"] = str(root / "entries")
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(log)
        os.environ["EDGE_REPO"] = str(root)
        os.environ["EDGE_DASH_AUTH"] = "test:operator"
        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.client = server.app.test_client()
        self.root = root

    def tearDown(self):
        for k in ("EDGE_REPO", "EDGE_DASH_AUTH", "EDGE_BLOG_LOG", "EDGE_BLOG_ENTRIES",
                  "EDGE_BLOG_STATIC"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_panel_renders_the_source_interface_row(self):
        r = self.client.get("/sources")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        for needle in ("exa", "search-deep", "tentativas", "citadas", "score", "canário"):
            self.assertIn(needle, body)

    def test_e8_never_seen_declared_source_is_a_visible_dead_leg(self):
        body = self.client.get("/sources").data.decode()
        # Overleaf was NEVER referenced in code — it appears purely from the operator's agent.yaml
        self.assertIn("overleaf", body)
        self.assertIn("DEAD LEG", body)

    def test_footer_carries_orphans_ambiguous_unconsumed(self):
        body = self.client.get("/sources").data.decode()
        for needle in ("orphans", "ambiguous", "unconsumed", "excluídas"):
            self.assertIn(needle, body)


if __name__ == "__main__":
    unittest.main()
