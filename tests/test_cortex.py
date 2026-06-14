"""Cortex graph — surf the agent's brain (SURFACE.md §"Cortex graph").

A read-only fold of the whole Cortex (group_id-scoped, fail-dark) shipped as a {nodes, edges}
JSON payload to a Cytoscape JS island: a dark, force-directed constellation centered on space-0,
trust-weighted brightness (space-0 brightest → asserted spine bright → extracted Entity/Source dim
→ Episodic faintest). Read-only, pan/zoom/click. The TDD seam is EDGE_CORTEX_FIXTURE (a {nodes,
edges} JSON file): set → the fold reads the fixture; unset → live neo4j. Tests inject the fixture
and exercise the fail-dark path; production reads neo4j.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BLOG = Path(__file__).resolve().parent.parent / "blog"


# A small whole-Cortex fixture: space-0 + one of each trust tier + edges.
FIXTURE = {
    "nodes": [
        {"id": "g0", "label": "Genesis", "title": "ed", "trust": "space0"},
        {"id": "o1", "label": "Objective", "title": "the hub", "trust": "asserted"},
        {"id": "d1", "label": "Direction", "title": "a bet", "trust": "asserted"},
        {"id": "a1", "label": "Artefato", "title": "a-post", "trust": "asserted"},
        {"id": "e1", "label": "Entity", "title": "human", "trust": "extracted"},
        {"id": "s1", "label": "Source", "title": "arxiv", "trust": "extracted"},
        {"id": "ep1", "label": "Episodic", "title": "session-x", "trust": "episodic"},
    ],
    "edges": [
        {"id": "r0", "source": "g0", "target": "o1", "type": "GROUNDS"},
        {"id": "r1", "source": "o1", "target": "d1", "type": "ANCHORS"},
        {"id": "r2", "source": "a1", "target": "o1", "type": "SERVES"},
        {"id": "r3", "source": "a1", "target": "e1", "type": "DISTILLS"},
        {"id": "r4", "source": "e1", "target": "s1", "type": "MENTIONS"},
        {"id": "r5", "source": "ep1", "target": "e1", "type": "RELATES_TO"},
    ],
}


def _load_server(env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    sys.path.insert(0, str(BLOG))
    import server
    importlib.reload(server)
    return server


class TestCortexFold(unittest.TestCase):
    """The fold reads the fixture when EDGE_CORTEX_FIXTURE is set (no live neo4j needed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fix = Path(self.tmp.name) / "cortex.json"
        self.fix.write_text(json.dumps(FIXTURE))
        self.server = _load_server({
            "EDGE_CORTEX_FIXTURE": str(self.fix),
            "EDGE_GROUP": "edge-next",
        })

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_CORTEX_FIXTURE", None)

    def test_fold_returns_nodes_and_edges_from_fixture(self):
        payload = self.server.cortex_fold()
        self.assertIsNotNone(payload)
        ids = {n["id"] for n in payload["nodes"]}
        self.assertEqual(ids, {"g0", "o1", "d1", "a1", "e1", "s1", "ep1"})
        self.assertEqual(len(payload["edges"]), 6)

    def test_fold_carries_the_trust_tier_per_node(self):
        payload = self.server.cortex_fold()
        trust = {n["id"]: n["trust"] for n in payload["nodes"]}
        self.assertEqual(trust["g0"], "space0")        # space-0 brightest
        self.assertEqual(trust["o1"], "asserted")      # asserted spine
        self.assertEqual(trust["e1"], "extracted")     # extracted dim
        self.assertEqual(trust["ep1"], "episodic")     # episodic faintest

    def test_each_edge_carries_a_stable_id_distinct_from_node_ids(self):
        # edge ids must not collide with node ids (Cytoscape shares one id namespace) — a
        # synthetic e<index> scheme aliased node "e1"; the fold carries the relationship id.
        payload = self.server.cortex_fold()
        node_ids = {n["id"] for n in payload["nodes"]}
        edge_ids = [e["id"] for e in payload["edges"]]
        self.assertEqual(len(edge_ids), len(set(edge_ids)))       # unique
        self.assertTrue(node_ids.isdisjoint(edge_ids))            # no collision with nodes

    def test_node_mapping_surfaces_the_earmarked_flag(self):
        # the Earmarked overlay (harm overrides the dim) is wired end-to-end: a node carrying the
        # earmark signal in its props surfaces earmarked=True so the island can highlight it.
        plain = self.server._map_node("4:x:0", "Entity", {"name": "human"})
        self.assertFalse(plain["earmarked"])
        marked = self.server._map_node("4:x:1", "Entity", {"name": "harm", "earmarked": True})
        self.assertTrue(marked["earmarked"])

    def test_source_inspect_title_falls_back_to_key(self):
        # CITES-projected Source nodes carry their ref in `key` (name/source_description are null);
        # the inspect title must surface it, not the generic "Source" label.
        node = self.server._map_node("4:x:2", "Source", {"key": "arXiv:2304.03442"})
        self.assertEqual(node["title"], "arXiv:2304.03442")


class TestCortexRoute(unittest.TestCase):
    """GET /cortex renders the graph container + the Cytoscape island wired to the payload."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fix = Path(self.tmp.name) / "cortex.json"
        self.fix.write_text(json.dumps(FIXTURE))
        self.server = _load_server({
            "EDGE_CORTEX_FIXTURE": str(self.fix),
            "EDGE_GROUP": "edge-next",
        })
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_CORTEX_FIXTURE", None)

    def test_route_renders_graph_container_and_island(self):
        r = self.client.get("/cortex")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        # the graph mount point the island draws into
        self.assertIn('id="cortex"', body)
        # the Cytoscape lib is loaded ONLY on this view (a JS island, not the app shell)
        self.assertIn("cytoscape", body)
        # the fold's nodes are shipped into the page (one payload, client-side nav)
        self.assertIn('"g0"', body)
        self.assertIn('"Genesis"', body)
        # trust tiers reach the client so brightness can be weighted
        self.assertIn("space0", body)
        self.assertIn("episodic", body)

    def test_route_centers_on_space0(self):
        # space-0 is the gravitational core — flagged so the island can pin/center + brighten it
        body = self.client.get("/cortex").data.decode()
        self.assertIn("space0", body)
        # the Genesis node id is present to be centered on
        self.assertIn('"g0"', body)

    def test_index_links_to_cortex(self):
        body = self.client.get("/").data.decode()
        self.assertIn('href="/cortex"', body)


class TestCortexFailDark(unittest.TestCase):
    """No group or neo4j down → a dark state, NEVER an unscoped query (cross-install leak)."""

    def setUp(self):
        # no fixture → the fold must resolve a group_id from identity to read live neo4j
        self.server = _load_server({"EDGE_CORTEX_FIXTURE": None})
        # Force the group resolver dark (this host's agent.yaml otherwise resolves edge-next):
        # we are testing the fail-dark branch, so the group must be unresolvable.
        self._orig_group = self.server._group
        self.server._group = lambda: None
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.server._group = self._orig_group

    def test_fold_is_dark_without_a_group(self):
        # cortex_fold returns None (dark) rather than running a graph-wide MATCH
        self.assertIsNone(self.server.cortex_fold(group=None))

    def test_fold_is_dark_when_group_unresolved(self):
        # auto-group resolves to None → dark, never an unscoped live query
        self.assertIsNone(self.server.cortex_fold())

    def test_route_renders_dark_state_not_a_crash(self):
        r = self.client.get("/cortex")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        # an honest dark marker, not a graph and not a 500
        self.assertIn("dark", body.lower())
        # no node payload leaked into the dark page
        self.assertNotIn('"nodes"', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
