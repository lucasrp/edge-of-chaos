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

    def test_node_mapping_surfaces_a_recency_ts(self):
        # Slice 6 — the recency filter axis. _map_node carries a per-node `ts` from the graph props
        # (Graphiti stamps created_at/valid_at; the asserted spine may carry a plain `ts`), coerced
        # to a string so the client can order/threshold by recency. No extra query — it is already in
        # properties(n), kept cheap. Absent stamp → None (the node simply has no recency position).
        stamped = self.server._map_node("4:x:7", "Episodic", {"name": "s", "created_at": "2026-06-01T00:00:00Z"})
        self.assertEqual(stamped["ts"], "2026-06-01T00:00:00Z")
        valid = self.server._map_node("4:x:8", "Entity", {"name": "e", "valid_at": "2026-05-09T10:00:00Z"})
        self.assertEqual(valid["ts"], "2026-05-09T10:00:00Z")
        plain = self.server._map_node("4:x:9", "Entity", {"name": "e"})
        self.assertIsNone(plain["ts"])


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

    def test_route_renders_search_and_filter_controls(self):
        # Slice 6 — navigate the brain. The page ships the find-and-jump search box + the filter
        # controls (by node type, Earmarked-only, recency) the island wires up client-side. They are
        # present in the static markup so the controls exist even before the island mounts.
        body = self.client.get("/cortex").data.decode()
        # the find-and-jump search box
        self.assertIn('id="cortex-search"', body)
        # a node-type filter for each trust-class label (deterministic over the loaded payload)
        for label in ("Genesis", "Objective", "Direction", "Artefato", "Entity", "Source", "Episodic"):
            self.assertIn(f'value="{label}"', body)
        # the Earmarked-only toggle (harm subset)
        self.assertIn('id="cortex-earmarked"', body)
        # the recency control
        self.assertIn('id="cortex-recency"', body)

    def test_search_and_filter_controls_absent_on_the_dark_page(self):
        # fail-dark stays clean — no controls leak onto the dark page (nothing to navigate).
        server = _load_server({"EDGE_CORTEX_FIXTURE": None})
        server._group = lambda: None
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertNotIn('id="cortex-search"', body)
        self.assertIn("dark", body.lower())

    def test_island_script_is_loaded_for_the_filter_logic(self):
        # the controls are wired by the island (cortex.js) — present so the filter/search logic runs.
        body = self.client.get("/cortex").data.decode()
        self.assertIn("/static/cortex.js", body)

    def test_node_title_cannot_break_out_of_the_json_script_tag(self):
        # graph node titles derive from Direction/Source/Entity content — a crafted title with a
        # mixed-case </SCRIPT> must NOT break out of the <script type="application/json"> data block
        # and execute same-origin (it could fire POST /grill/drain, defeating the Slice-1 gate).
        poison = "</SCRIPT><script>fetch('/grill/drain',{method:'POST'})//"
        fix = {"nodes": [{"id": "g0", "label": "Genesis", "title": poison, "trust": "space0"}],
               "edges": []}
        self.fix.write_text(json.dumps(fix))
        server = _load_server({"EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next"})
        body = server.app.test_client().get("/cortex").data.decode()
        # the raw closing tag (any case) must not appear verbatim — it is escaped, so the browser
        # never sees a real </script> inside the data block and cannot execute the injected script.
        self.assertNotIn("</SCRIPT>", body)
        self.assertNotIn("</script><script>", body.lower())


class TestNodeSourceHref(unittest.TestCase):
    """Slice 5b — link Cortex nodes to their source (AUDIT.md gap C, PLAN.md accept): clicking an
    Artefato/Direction/Source/cluster node drills into its real surface. The fold carries a per-node
    `href` so the island's inspect panel surfaces a WORKING link — the graph stops being an island."""

    def setUp(self):
        self.server = _load_server({"EDGE_CORTEX_FIXTURE": None, "EDGE_GROUP": "edge-next"})

    def test_artefato_node_links_to_its_blog_entry(self):
        node = self.server._map_node("4:x:1", "Artefato", {"slug": "alpha-post"})
        self.assertEqual(node["href"], "/e/alpha-post.html")

    def test_direction_node_links_to_the_direction_surface(self):
        # a Direction graph node is keyed by body (no event id on the node), so the robust, working
        # target is the Direction surface itself — a real route the steer is scannable on.
        node = self.server._map_node("4:x:2", "Direction", {"body": "surface the self-state"})
        self.assertEqual(node["href"], "/direction")

    def test_source_node_links_to_its_source_doc(self):
        node = self.server._map_node("4:x:3", "Source", {"key": "arXiv:2304.03442"})
        self.assertEqual(node["href"], "/docs/source-roadmap")

    def test_cluster_bearing_entity_links_to_its_wiki_cluster(self):
        # clusters are not separate graph nodes in v1 (Community=0) — an Entity carrying a
        # curated_cluster IS the cluster's graph presence, so it drills into /wiki/<cluster-slug>
        # (the slug is the letters-only rule the wiki projection names cluster-*.html by).
        node = self.server._map_node("4:x:4", "Entity",
                                     {"name": "Zep", "curated_cluster": "Introspective memory"})
        self.assertEqual(node["href"], "/wiki/introspectivememory")

    def test_plain_entity_and_episodic_carry_no_href(self):
        # a node with no source surface (a bare Entity, an Episodic, Genesis/Objective) carries no
        # href — the panel simply shows no drill-down link, never a dead one.
        self.assertIsNone(self.server._map_node("4:x:5", "Entity", {"name": "human"})["href"])
        self.assertIsNone(self.server._map_node("4:x:6", "Episodic", {"name": "session"})["href"])

    def test_payload_node_hrefs_target_real_routes(self):
        # the strong property: every node href the fold ships resolves to a REAL route on the app
        # (a 200/redirect, never a 404) — the graph links into surfaces that exist, not dead anchors.
        fixture = {
            "nodes": [
                {"id": "a1", "label": "Artefato", "title": "t",
                 "href": "/e/alpha-post.html", "trust": "asserted"},
                {"id": "d1", "label": "Direction", "title": "t",
                 "href": "/direction", "trust": "asserted"},
                {"id": "s1", "label": "Source", "title": "t",
                 "href": "/docs/source-roadmap", "trust": "extracted"},
            ],
            "edges": [],
        }
        # the route-existence check is over the app's URL map (no live neo4j / no doc files needed):
        # each href must match a registered rule.
        rules = [r.rule for r in self.server.app.url_map.iter_rules()]
        for n in fixture["nodes"]:
            href = n["href"].split("#")[0]
            # /e/<slug>.html, /docs/<id>, /wiki/<id>, /direction are all registered routes.
            matched = any(
                href == "/direction"
                or (rule.startswith("/e/") and href.startswith("/e/"))
                or (rule.startswith("/docs/") and href.startswith("/docs/"))
                or (rule.startswith("/wiki/") and href.startswith("/wiki/"))
                for rule in rules)
            self.assertTrue(matched, f"{href} targets no real route")


class TestCortexRouteShipsHref(unittest.TestCase):
    """The /cortex page ships the per-node href into the island so the inspect panel can render the
    drill-down link, AND the island script reads it (the graph→source wiring is live, not latent)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fix = Path(self.tmp.name) / "cortex.json"
        self.fix.write_text(json.dumps({
            "nodes": [{"id": "a1", "label": "Artefato", "title": "alpha",
                       "href": "/e/alpha-post.html", "trust": "asserted"}],
            "edges": [],
        }))
        self.server = _load_server({"EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next"})
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_CORTEX_FIXTURE", None)

    def test_route_ships_the_node_href_into_the_payload(self):
        body = self.client.get("/cortex").data.decode()
        self.assertIn("/e/alpha-post.html", body)

    def test_island_script_consumes_the_href(self):
        # the island reads n.href and renders it as a link in the inspect panel — proves the wiring
        # is live (the payload field is actually surfaced, not just shipped and dropped).
        js = (Path(__file__).resolve().parent.parent / "blog" / "static" / "cortex.js").read_text()
        self.assertIn("href", js)

    def test_panel_link_is_built_via_dom_apis_not_attribute_string_interp(self):
        # SECURITY (codex round-1 [high]): the panel's esc() escapes &<> but NOT quotes, and an
        # Artefato href is built from a graph/log-derived slug. Interpolating href into an
        # `href="..."` attribute string lets a slug carrying `" onclick="fetch(...)"` break out of
        # the attribute and bind a same-origin handler → an authenticated mutating POST, defeating the
        # Slice-1 gate. The link must be built with DOM APIs (createElement + assign a.href), which
        # CANNOT be broken out of by attribute injection. Pin the safe construction.
        js = (Path(__file__).resolve().parent.parent / "blog" / "static" / "cortex.js").read_text()
        self.assertIn('createElement("a")', js)
        # the unsafe pattern (a quoted href attribute built from the dynamic value) must be gone.
        self.assertNotIn("'<a href=\"' + ", js)
        self.assertNotIn("setAttribute(\"href\"", js)  # a string attr is the same breakout surface


class TestNodeHrefIsRouteShaped(unittest.TestCase):
    """SECURITY (codex round-1 [high]): _node_href is built from graph/log-derived props (a slug, a
    cluster label), so its output must be a canonical, route-shaped value — never a vector carrying a
    quote / handler / whitespace that a downstream renderer could mis-handle. The server constrains
    the path segment; the island then renders it via DOM APIs (no attribute interpolation)."""

    def setUp(self):
        self.server = _load_server({"EDGE_CORTEX_FIXTURE": None, "EDGE_GROUP": "edge-next"})

    def test_artefato_href_drops_a_slug_with_quotes_or_handler_chars(self):
        # a poisoned slug (a quote + an event-handler payload) must NOT yield a live href — the
        # server rejects a slug that is not a canonical slug shape (lowercase alnum + hyphen).
        poison = self.server._map_node("4:x:9", "Artefato",
                                       {"slug": 'x" onclick="fetch(\'/grill/drain\')'})
        self.assertIsNone(poison["href"])

    def test_artefato_href_keeps_a_canonical_slug(self):
        ok = self.server._map_node("4:x:10", "Artefato", {"slug": "alpha-post-2"})
        self.assertEqual(ok["href"], "/e/alpha-post-2.html")

    def test_cluster_slug_is_letters_only_so_it_cannot_carry_a_breakout(self):
        # the cluster slug is letters-only by construction (the wiki naming rule), so any quote /
        # handler / path char in the source label is dropped before it reaches a URL.
        node = self.server._map_node("4:x:11", "Entity",
                                     {"name": "z", "curated_cluster": 'a"/onerror=b 0'})
        self.assertEqual(node["href"], "/wiki/aonerrorb")


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


import shutil
import subprocess
import textwrap

CORTEX_JS = Path(__file__).resolve().parent.parent / "blog" / "static" / "cortex.js"
NODE = shutil.which("node")


def _run_island_logic(js_body):
    """Drive the pure island logic (CortexFilters) under Node: cortex.js exports CortexFilters when
    required as a CommonJS module (no DOM / no cytoscape needed for the pure search/filter logic).
    `js_body` asserts via `assert` and prints results; a non-zero exit fails the Python test. This
    keeps the JS island logic factored + testable under the standard `tools/edge-python` gate."""
    harness = textwrap.dedent("""
        const assert = require('assert');
        const { CortexFilters } = require(%r);
        %s
        console.log('OK');
    """) % (str(CORTEX_JS), js_body)
    proc = subprocess.run([NODE, "-e", harness], capture_output=True, text=True)
    return proc


# A pure-logic fixture (no DOM): space-0 + the spine + extracted + episodic, with recency stamps and
# one Earmarked node. Ordered oldest→newest by ts so recency thresholds are unambiguous.
ISLAND_PAYLOAD = {
    "nodes": [
        {"id": "g0", "label": "Genesis", "title": "ed", "trust": "space0", "ts": "2026-01-01", "earmarked": False},
        {"id": "o1", "label": "Objective", "title": "the hub", "trust": "asserted", "ts": "2026-02-01", "earmarked": False},
        {"id": "d1", "label": "Direction", "title": "ship the cortex", "trust": "asserted", "ts": "2026-03-01", "earmarked": False},
        {"id": "a1", "label": "Artefato", "title": "alpha-post", "trust": "asserted", "ts": "2026-04-01", "earmarked": False},
        {"id": "e1", "label": "Entity", "title": "harmful claim", "trust": "extracted", "ts": "2026-05-01", "earmarked": True},
        {"id": "s1", "label": "Source", "title": "arxiv-2304", "trust": "extracted", "ts": "2026-05-15", "earmarked": False},
        {"id": "ep1", "label": "Episodic", "title": "session-x", "trust": "episodic", "ts": "2026-06-01", "earmarked": False},
        {"id": "ep2", "label": "Episodic", "title": "session-y", "trust": "episodic", "ts": None, "earmarked": False},
    ],
    "edges": [],
}


class TestControlsStyling(unittest.TestCase):
    """Cross-cutting (PLAN.md §2 — one design system): the Slice 6 controls reuse the SHARED
    style.css design tokens / component vocabulary, no one-off styling. The controls panel is styled,
    and it draws on the :root tokens (var(--...)) the rest of the dashboard uses."""

    STYLE = (Path(__file__).resolve().parent.parent / "blog" / "static" / "style.css")

    def test_controls_are_styled_with_shared_tokens(self):
        css = self.STYLE.read_text()
        # the controls panel is styled (not unstyled native chrome)
        self.assertIn(".cortex-controls", css)
        # and it reuses the shared design tokens, not one-off literals — pin a few load-bearing ones
        idx = css.index(".cortex-controls")
        block = css[idx:idx + 1400]
        for token in ("var(--surface", "var(--border", "var(--text", "var(--font-mono"):
            self.assertIn(token, block, f"controls do not reuse shared token: {token}")


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestIslandSearch(unittest.TestCase):
    """Slice 6 — find-and-jump search: a deterministic label/type/title match over the loaded
    payload (NOT semantic retrieval — SURFACE.md bans the fetch posture). Returns the matched node
    id to center, and handles empty / no-match cleanly."""

    PAYLOAD = json.dumps(ISLAND_PAYLOAD)

    def test_search_matches_a_node_by_title_and_returns_its_id(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.search(p, 'alpha');
            assert.strictEqual(r.matchId, 'a1');
            assert.strictEqual(r.count, 1);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_search_matches_by_node_type_label(self):
        # typing a node type (e.g. "Direction") finds nodes of that type — deterministic label match.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.search(p, 'Direction');
            assert.strictEqual(r.matchId, 'd1');
            assert.ok(r.count >= 1);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_search_is_case_insensitive(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.search(p, 'ARXIV');
            assert.strictEqual(r.matchId, 's1');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_empty_query_matches_nothing_cleanly(self):
        # an empty / whitespace search is not a match-all — it clears the locator, no node centered.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const blank = CortexFilters.search(p, '   ');
            assert.strictEqual(blank.matchId, null);
            assert.strictEqual(blank.count, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_match_returns_null_not_a_crash(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const miss = CortexFilters.search(p, 'zzz-no-such-node');
            assert.strictEqual(miss.matchId, null);
            assert.strictEqual(miss.count, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestIslandFilter(unittest.TestCase):
    """Slice 6 — filter the loaded payload: by node type, Earmarked-only, recency. `visible()` is a
    PURE function of (payload, control-state) → the set of node ids to show, recomputed from scratch
    each call. No accumulated hidden/visible state: toggling a filter off restores cleanly (the
    no-stale-state contract)."""

    PAYLOAD = json.dumps(ISLAND_PAYLOAD)

    def test_filter_by_type_shows_only_the_selected_classes(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const vis = CortexFilters.visible(p, {{types: ['Artefato','Direction']}});
            assert.deepStrictEqual([...vis].sort(), ['a1','d1']);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_filter_by_type_empty_selection_hides_everything(self):
        # an empty type selection → an empty result set (not a stale match-all). Empty-result behavior.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const vis = CortexFilters.visible(p, {{types: []}});
            assert.strictEqual(vis.size, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_earmarked_only_shows_just_the_harm_subset(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const vis = CortexFilters.visible(p, {{earmarkedOnly: true}});
            assert.deepStrictEqual([...vis], ['e1']);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_recency_threshold_keeps_only_the_most_recent(self):
        # recencyFraction 0 → all; 1 → only the most recent stamped node; an unstamped node is
        # treated as oldest (hidden first as the threshold rises). Deterministic over `ts`.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const all = CortexFilters.visible(p, {{recencyFraction: 0}});
            assert.strictEqual(all.size, 8);                  // 0 → everything
            const newest = CortexFilters.visible(p, {{recencyFraction: 1}});
            assert.deepStrictEqual([...newest], ['ep1']);     // ts 2026-06-01 is the most recent
            const half = CortexFilters.visible(p, {{recencyFraction: 0.5}});
            assert.ok(half.has('ep1') && half.has('s1'));     // recent kept
            assert.ok(!half.has('g0'));                       // oldest dropped
            assert.ok(!half.has('ep2'));                      // unstamped treated as oldest
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_filters_compose_type_and_earmarked(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            // Entity is selected AND earmarked-only → just the earmarked Entity
            const vis = CortexFilters.visible(p, {{types: ['Entity','Source'], earmarkedOnly: true}});
            assert.deepStrictEqual([...vis], ['e1']);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_stale_state_toggling_a_filter_off_restores_the_full_set(self):
        # the no-stale-state contract: visible() is pure over the immutable payload — narrowing then
        # widening recovers the FULL set, never a stale hidden remainder.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const narrowed = CortexFilters.visible(p, {{types: ['Genesis']}});
            assert.strictEqual(narrowed.size, 1);
            const restored = CortexFilters.visible(p, {{}});   // no filters → all nodes
            assert.strictEqual(restored.size, 8);
            // a second narrowing is computed from the payload, not from the prior result
            const reNarrowed = CortexFilters.visible(p, {{earmarkedOnly: true}});
            assert.deepStrictEqual([...reNarrowed], ['e1']);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_default_state_shows_every_node(self):
        # no control state at all → the unfiltered graph (the v1 surf posture is preserved).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const vis = CortexFilters.visible(p, {{}});
            assert.strictEqual(vis.size, 8);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
