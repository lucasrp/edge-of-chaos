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

    def test_artefato_recency_uses_its_projected_at_stamp(self):
        # codex round-3 [medium]: the live Artefato projection stamps recency as `projected_at`
        # (tools/publisher.py — the recency signal recall-push orders by), NOT created_at/valid_at.
        # Without it a live Artefato serializes ts:null and the recency filter would DROP recent
        # published work. _node_ts must read projected_at so an Artefato survives recency ranking.
        node = self.server._map_node("4:x:a", "Artefato",
                                     {"slug": "alpha-post", "projected_at": "2026-06-10T12:00:00Z"})
        self.assertEqual(node["ts"], "2026-06-10T12:00:00Z")


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
        # the Episodic-collapse perf lever (Slice 6) — folds the faint haze out of the RENDERED set
        self.assertIn('id="cortex-collapse"', body)

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


class TestCortexRenderSlice2(unittest.TestCase):
    """Slice 2 — the 3D cloud render + the M21 fallback ladder, wired by the cortex() route.

    The route now emits BOTH vendored island scripts (3d-force-graph for the default render +
    cytoscape for the auto-fallback rung) island-only, plus a server-rendered searchable list
    fallback (M21 rung 3) drawn from the SAME payload so it works even if JS is dead. The fold,
    _map_node, _json_for_script, group scoping and fail-dark are UNCHANGED (front-end envelope only).
    """

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

    def test_route_emits_the_3d_force_graph_bundle_island_only(self):
        # M1/M18/M19 — the 3D bundle is the default renderer, self-hosted, loaded ONLY on /cortex.
        body = self.client.get("/cortex").data.decode()
        self.assertIn("/static/vendor/3d-force-graph.min.js", body)

    def test_route_still_emits_the_cytoscape_fallback_bundle(self):
        # M21 rung 2 — the 2D Cytoscape island is the mandated WebGL/init-failure fallback, never
        # deleted. Both lib scripts ship island-only so the ladder can fall through client-side.
        body = self.client.get("/cortex").data.decode()
        self.assertIn("/static/vendor/cytoscape.min.js", body)
        self.assertIn("/static/cortex.js", body)

    def test_neither_3d_nor_cytoscape_load_on_the_app_shell(self):
        # M19 — the heavy three.js bundle must never touch the read-mostly pages, only the island.
        for path in ("/", "/direction", "/docs", "/ux-catalog"):
            body = self.client.get(path).data.decode()
            self.assertNotIn("3d-force-graph.min.js", body,
                             f"{path} loads the 3D bundle (must be /cortex-only — M19)")
            self.assertNotIn("cytoscape.min.js", body,
                             f"{path} loads cytoscape (must be /cortex-only — M19)")

    def test_route_ships_a_server_rendered_searchable_list_fallback(self):
        # M21 rung 3 — a server-rendered node/edge list from the SAME payload, so the Cortex stays
        # navigable even if BOTH WebGL renderers and JS are dead. It carries each node's title + a
        # source-drill link when the node has an href.
        body = self.client.get("/cortex").data.decode()
        self.assertIn("cortex-list", body)            # the list fallback container
        self.assertIn("the hub", body)                # a node title rendered server-side
        self.assertIn("Genesis", body)                # the node-type label is shown

    def test_list_fallback_is_visible_when_js_is_dead(self):
        # codex round-1 [high]: the list is the JS-DEAD navigable fallback (M21 "works even if JS is
        # dead"). If the server emitted it `hidden`, a failed/absent cortex.js leaves a blank graph
        # area — the exact regression M21 prevents. So the server renders it VISIBLE (no `hidden`
        # attribute); the island HIDES it only AFTER a graph rung successfully paints (progressive
        # enhancement). The JS therefore carries the hide-on-mount call, not the server the hide.
        body = self.client.get("/cortex").data.decode()
        # the list block must NOT carry a `hidden` attribute on its container (would blank a no-JS client)
        idx = body.index('id="cortex-list"')
        container = body[idx - 40:idx + 80]
        self.assertNotIn(" hidden", container,
                         "the server hid the list — a no-JS client gets a blank graph area (M21 fail)")
        # the island hides the list once a graph renderer mounts (so it does not double-render under 3D)
        js = (Path(__file__).resolve().parent.parent / "blog" / "static" / "cortex.js").read_text()
        self.assertIn("cortex-list", js)
        self.assertIn("hideList", js)

    def test_list_fallback_links_only_to_internal_node_sources(self):
        # the list's drill links reuse the same internal-path provenance the panel does — a node
        # with an internal href links to it; a node without one carries no dead link.
        self.fix.write_text(json.dumps({
            "nodes": [
                {"id": "a1", "label": "Artefato", "title": "alpha",
                 "href": "/e/alpha-post.html", "trust": "asserted"},
                {"id": "e1", "label": "Entity", "title": "bare", "trust": "extracted"},
            ],
            "edges": [],
        }))
        server = _load_server({"EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next"})
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertIn('href="/e/alpha-post.html"', body)   # the node with a source drills in
        # the bare Entity has no href → it is listed but carries no anchor of its own
        self.assertIn(">bare<", body)

    def test_list_fallback_escapes_a_poisoned_title(self):
        # the server-rendered list is built with Jinja autoescaping (html.escape), so a node title
        # carrying an HTML/attribute breakout payload is inert in the list rung too (M17/R5).
        poison = '<img src=x onerror="fetch(\'/grill/drain\',{method:\'POST\'})">'
        self.fix.write_text(json.dumps({
            "nodes": [{"id": "g0", "label": "Genesis", "title": poison, "trust": "space0"}],
            "edges": [],
        }))
        server = _load_server({"EDGE_CORTEX_FIXTURE": str(self.fix), "EDGE_GROUP": "edge-next"})
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertNotIn("<img src=x onerror=", body)   # never a live element
        self.assertIn("&lt;img", body)                  # escaped, inert

    def test_list_fallback_absent_on_the_dark_page(self):
        # fail-dark (M16) stays distinct from the M21 chain — no list/scripts leak onto the dark page.
        server = _load_server({"EDGE_CORTEX_FIXTURE": None})
        server._group = lambda: None
        body = server.app.test_client().get("/cortex").data.decode()
        self.assertNotIn("cortex-list", body)
        self.assertNotIn("3d-force-graph.min.js", body)
        self.assertIn("dark", body.lower())


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

    def test_graph_mount_overlay_is_scoped_to_an_attached_renderer(self):
        # codex round-2 [high]: the full-canvas absolute #cortex mount must apply ONLY once a graph
        # renderer attaches (data-renderer). An EMPTY #cortex (JS dead) must not overlay the in-flow
        # list fallback and intercept its clicks. Pin the scoped selector, and that the unscoped
        # `#cortex { position: absolute` form is gone.
        css = self.STYLE.read_text()
        self.assertIn("#cortex[data-renderer]", css)
        self.assertNotIn("#cortex { position: absolute", css)


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
        # recencyFraction 0 → all; the cutoff ranks ONLY stamped nodes (an unstamped node has "no
        # recency position" per the server contract, so it is dropped whenever recency is engaged —
        # never fabricated as recent). 1 → the single most-recent STAMPED node. Deterministic over ts.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const all = CortexFilters.visible(p, {{recencyFraction: 0}});
            assert.strictEqual(all.size, 8);                  // 0 → everything (recency off)
            const newest = CortexFilters.visible(p, {{recencyFraction: 1}});
            assert.deepStrictEqual([...newest], ['ep1']);     // ts 2026-06-01 is the most recent
            const half = CortexFilters.visible(p, {{recencyFraction: 0.5}});
            assert.ok(half.has('ep1') && half.has('s1'));     // recent kept
            assert.ok(!half.has('g0'));                       // oldest stamped dropped
            assert.ok(!half.has('ep2'));                      // unstamped has no recency position
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_recency_on_an_all_unstamped_payload_drops_everything(self):
        # codex round-1 [medium]: an all-unstamped graph must NOT fabricate a "newest" node from the
        # last payload entry. With recency engaged and no stamped nodes, the kept set is empty.
        proc = _run_island_logic("""
            const p = {nodes: [
              {id:'x', label:'Entity', title:'a', trust:'extracted', ts:null},
              {id:'y', label:'Entity', title:'b', trust:'extracted', ts:null},
            ], edges: []};
            assert.strictEqual(CortexFilters.visible(p, {recencyFraction: 1}).size, 0);
            assert.strictEqual(CortexFilters.visible(p, {recencyFraction: 0.5}).size, 0);
            // recency OFF still shows them (they exist, they just have no recency position)
            assert.strictEqual(CortexFilters.visible(p, {recencyFraction: 0}).size, 2);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_recency_on_a_mixed_payload_ranks_only_stamped_nodes(self):
        # codex round-1 [medium]: when unstamped nodes outnumber stamped ones, a moderate threshold
        # must keep only real stamped recents — never an arbitrary unstamped node.
        proc = _run_island_logic("""
            const p = {nodes: [
              {id:'u1', label:'Entity', title:'u', trust:'extracted', ts:null},
              {id:'u2', label:'Entity', title:'u', trust:'extracted', ts:null},
              {id:'u3', label:'Entity', title:'u', trust:'extracted', ts:null},
              {id:'s_old', label:'Entity', title:'s', trust:'extracted', ts:'2026-01-01'},
              {id:'s_new', label:'Entity', title:'s', trust:'extracted', ts:'2026-09-01'},
            ], edges: []};
            const r = CortexFilters.visible(p, {recencyFraction: 0.5}); // keep most-recent ceil(.5*2)=1
            assert.deepStrictEqual([...r], ['s_new']);
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


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestIslandEpisodicCollapse(unittest.TestCase):
    """Slice 6 — the Episodic-collapse perf lever (SURFACE.md's own suggestion). A CLIENT-SIDE render
    decision over the EXISTING payload (the fold / cortex_fold / _map_node are UNCHANGED): when
    engaged, the faint `episodic` haze (~91 nodes + their MENTIONS edges) folds out of the RENDERED
    set so it stops costing render budget beyond the Slice-2 M22 floor. It is one more independent AND
    predicate in `visible()` — pure over (payload, control-state), recomputed from scratch, so it
    composes with type/Earmarked/recency/search and toggling it off restores the haze cleanly (the
    no-stale-state contract). It NEVER touches the data — only which nodes the renderer draws."""

    PAYLOAD = json.dumps(ISLAND_PAYLOAD)

    def test_collapse_drops_the_episodic_haze_from_the_rendered_set(self):
        # engaged → the episodic-tier nodes leave the visible set; every other tier stays.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const vis = CortexFilters.visible(p, {{collapseEpisodic: true}});
            assert.ok(!vis.has('ep1'));                 // episodic folded out
            assert.ok(!vis.has('ep2'));                 // including the unstamped episodic
            assert.ok(vis.has('g0') && vis.has('e1') && vis.has('s1'));  // every non-episodic stays
            assert.strictEqual(vis.size, 6);            // 8 nodes − 2 episodic
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_collapse_off_keeps_the_full_haze(self):
        # the lever is opt-in: absent / false → the episodic haze is rendered (the v1 surf posture).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            assert.strictEqual(CortexFilters.visible(p, {{collapseEpisodic: false}}).size, 8);
            assert.strictEqual(CortexFilters.visible(p, {{}}).size, 8);    // default off
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_collapse_is_pure_no_stale_state_when_toggled_off(self):
        # the no-stale-state contract: engaging then disengaging recovers the FULL set (recomputed
        # from the immutable payload, never a stale hidden remainder).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const collapsed = CortexFilters.visible(p, {{collapseEpisodic: true}});
            assert.strictEqual(collapsed.size, 6);
            const restored = CortexFilters.visible(p, {{collapseEpisodic: false}});
            assert.strictEqual(restored.size, 8);       // the haze is back, no stale remainder
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_collapse_composes_with_the_other_filters(self):
        # an independent AND with type/Earmarked/recency — intersect, never resurrect. Type-select
        # Episodic AND collapse → the empty set (the predicates intersect, collapse wins on episodic).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const onlyEp = CortexFilters.visible(p, {{types: ['Episodic']}});
            assert.strictEqual(onlyEp.size, 2);          // both episodics with the type filter alone
            const collapsedEp = CortexFilters.visible(
              p, {{types: ['Episodic'], collapseEpisodic: true}});
            assert.strictEqual(collapsedEp.size, 0);     // collapse folds them out of the type set too
            // and it composes with Earmarked: collapse leaves the non-episodic harm node visible
            const harm = CortexFilters.visible(p, {{earmarkedOnly: true, collapseEpisodic: true}});
            assert.deepStrictEqual([...harm], ['e1']);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_collapse_never_hides_an_earmarked_episodic_node(self):
        # the harm-surfacing contract (M4 / SURFACE.md): an Earmarked node is NEVER buried regardless
        # of its tier — so the perf lever must KEEP an Earmarked episodic node visible (and thus its
        # correction composer reachable), even while it folds the rest of the episodic haze. Harm
        # overrides the collapse exactly as it overrides the trust-dim. [codex adversarial-review #1]
        proc = _run_island_logic("""
            const p = {nodes: [
              {id:'g0', label:'Genesis', title:'ed', trust:'space0', earmarked:false},
              {id:'ep_plain', label:'Episodic', title:'session-x', trust:'episodic', earmarked:false},
              {id:'ep_harm',  label:'Episodic', title:'harmful session', trust:'episodic', earmarked:true},
            ], edges: []};
            const vis = CortexFilters.visible(p, {collapseEpisodic: true});
            assert.ok(!vis.has('ep_plain'));   // the plain episodic haze folds out
            assert.ok(vis.has('ep_harm'));     // the Earmarked episodic is NEVER buried
            assert.ok(vis.has('g0'));          // non-episodic stays
            // and search can still locate it — the correction path stays reachable under the lever
            const r = CortexFilters.render(p, {collapseEpisodic: true, query: 'harmful'});
            assert.strictEqual(r.searchHit, 'ep_harm');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_render_search_does_not_resurrect_a_collapsed_episodic(self):
        # the combined render() authority: a query that matches a collapsed episodic node must NOT
        # resurrect it as the hit (search never overrides a not-rendered node — same as the filters).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.render(p, {{collapseEpisodic: true, query: 'session-x'}});
            assert.ok(!r.visibleIds.has('ep1'));         // ep1 (session-x) is folded out
            assert.strictEqual(r.searchHit, null);       // no resurrection of a collapsed node
            assert.strictEqual(r.searchCount, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_control_state_reads_the_collapse_toggle(self):
        # the DOM control state must read a collapse toggle into the render state (the lever is wired,
        # not dead markup) — pin the wiring so the perf lever actually reaches visible()/render().
        js = CORTEX_JS.read_text()
        self.assertIn("collapseEpisodic", js)
        self.assertIn("cortex-collapse", js)


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestIslandRender(unittest.TestCase):
    """Slice 6, codex round-1 [medium] — ONE combined search+filter state. render(payload, state) is
    the single authority the DOM renders from: the search hit is the first node that matches the
    query AND survives the active filters (search must NOT resurrect a filtered-out node), and the
    reported count reflects only visible matches. Both empty-result paths (filter-then-search and
    search-then-filter) resolve cleanly with no stale visible state."""

    PAYLOAD = json.dumps(ISLAND_PAYLOAD)

    def test_search_respects_the_active_filters_no_resurrection(self):
        # filter to Source-only, then search the Artefato — the Artefato is filtered out, so it must
        # NOT become the (visible) hit. The hit is null and the count is 0 (empty-result).
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.render(p, {{types: ['Source'], query: 'alpha'}});
            assert.ok(!r.visibleIds.has('a1'));        // the filtered-out Artefato stays hidden
            assert.strictEqual(r.searchHit, null);     // no resurrection of a hidden node
            assert.strictEqual(r.searchCount, 0);      // empty-result over the visible set
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_search_hit_is_the_first_visible_match(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.render(p, {{types: ['Artefato','Source'], query: 'a'}});
            // 'a' matches several titles; the hit is the FIRST in payload order among VISIBLE nodes
            assert.ok(r.visibleIds.has(r.searchHit));
            assert.strictEqual(r.searchHit, 'a1');     // alpha-post, first visible match
            assert.ok(r.searchCount >= 1);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_changing_a_filter_recomputes_the_search_count(self):
        # search-then-filter: a result that the new filter hides must drop to empty — the count is
        # recomputed from the combined state, never stale.
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const before = CortexFilters.render(p, {{query: 'alpha'}});
            assert.strictEqual(before.searchHit, 'a1');
            assert.strictEqual(before.searchCount, 1);
            const after = CortexFilters.render(p, {{query: 'alpha', earmarkedOnly: true}});
            assert.strictEqual(after.searchHit, null);   // alpha-post is not Earmarked → hidden
            assert.strictEqual(after.searchCount, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_empty_query_leaves_the_filtered_set_with_no_hit(self):
        proc = _run_island_logic(f"""
            const p = {self.PAYLOAD};
            const r = CortexFilters.render(p, {{types: ['Genesis'], query: ''}});
            assert.deepStrictEqual([...r.visibleIds], ['g0']);  // the filter still applies
            assert.strictEqual(r.searchHit, null);              // no query → no hit
            assert.strictEqual(r.searchCount, 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_default_all_checked_keeps_a_schema_drifted_unknown_label_visible(self):
        # codex round-2 [medium]: the type controls are a fixed label list, but the live fold tolerates
        # UNKNOWN labels (_map_node maps them to `extracted`). With every control checked (the default),
        # typeSelection → null (no type filter) so an unknown-label node stays VISIBLE + SEARCHABLE —
        # not silently dropped on the first control event. Only an actual UNCHECK narrows.
        proc = _run_island_logic("""
            const labels = ['Genesis','Objective','Direction','Artefato','Entity','Source','Episodic'];
            const p = {nodes: [
              {id:'k', label:'Community', title:'a cluster node', trust:'extracted', earmarked:false, ts:'2026-07-01'},
              {id:'a1', label:'Artefato', title:'alpha', trust:'asserted', earmarked:false, ts:'2026-04-01'},
            ], edges: []};
            // all checked → no type filter; the unknown-label node is visible by default
            const allChecked = CortexFilters.typeSelection(labels, labels);
            assert.strictEqual(allChecked, null);
            const r = CortexFilters.render(p, {types: allChecked, query: 'cluster'});
            assert.ok(r.visibleIds.has('k'));            // schema-drifted node visible by default
            assert.strictEqual(r.searchHit, 'k');        // and searchable (a locator over the WHOLE graph)
            // an actual narrowing (uncheck one) becomes an explicit allow-list
            const narrowed = CortexFilters.typeSelection(labels, ['Artefato']);
            assert.deepStrictEqual(narrowed, ['Artefato']);
            assert.ok(!CortexFilters.render(p, {types: narrowed}).visibleIds.has('k'));
            // empty selection is still distinct: hide all
            assert.deepStrictEqual(CortexFilters.typeSelection(labels, []), []);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_control_state_uses_type_selection_not_raw_checked_list(self):
        # the DOM control state must route the checked boxes through typeSelection (so all-checked →
        # null), not pass the raw fixed-label list as an allow-list (the round-2 schema-drift bug).
        js = CORTEX_JS.read_text()
        self.assertIn("CortexFilters.typeSelection", js)

    def test_island_render_drives_the_dom_no_filtered_out_bypass(self):
        # the DOM island must render from render()/visible() and must NOT carry the bypass that
        # removed `filtered-out` from a search hit (which resurrected a filtered node).
        js = CORTEX_JS.read_text()
        self.assertIn("CortexFilters.render", js)
        self.assertNotIn('hit.removeClass("filtered-out")', js)


def _run_probe_logic(js_body):
    """Drive the exported webglSupported() probe under Node (no DOM). cortex.js exports it alongside
    CortexFilters; the probe takes an injectable canvas factory so it is testable headless (the same
    Node-export pattern as CortexFilters). `js_body` asserts via `assert` then the harness prints OK."""
    harness = textwrap.dedent("""
        const assert = require('assert');
        const { webglSupported } = require(%r);
        %s
        console.log('OK');
    """) % (str(CORTEX_JS), js_body)
    return subprocess.run([NODE, "-e", harness], capture_output=True, text=True)


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestWebglProbe(unittest.TestCase):
    """Slice 1 — the WebGL capability seam (G4 / prereq for the M-GATE). webglSupported() is a pure,
    exported, side-effect-free try/catch probe: it asks a throwaway <canvas> for a webgl /
    experimental-webgl context and returns a boolean. It takes an injectable canvas factory so it is
    testable headless under Node (no `document`); the DOM island guard still gates real browser use.
    NO render swap here — /cortex still renders the 2D Cytoscape island (Slice 2 wires the renderer)."""

    def test_probe_is_exported_for_node(self):
        proc = _run_probe_logic("assert.strictEqual(typeof webglSupported, 'function');")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_true_when_a_context_is_available(self):
        # a stubbed canvas factory whose getContext returns a (fake) context → the probe reports true.
        proc = _run_probe_logic("""
            const factory = () => ({ getContext: (kind) => (kind === 'webgl' ? {} : null) });
            assert.strictEqual(webglSupported(factory), true);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_falls_back_to_experimental_webgl(self):
        # some contexts only answer to 'experimental-webgl' — the probe must try it too.
        proc = _run_probe_logic("""
            const factory = () => ({
              getContext: (kind) => (kind === 'experimental-webgl' ? {} : null) });
            assert.strictEqual(webglSupported(factory), true);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_false_when_no_context(self):
        # getContext returns null for every kind (WebGL blocked / unavailable) → the probe reports false.
        proc = _run_probe_logic("""
            const factory = () => ({ getContext: () => null });
            assert.strictEqual(webglSupported(factory), false);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_is_false_not_a_throw_when_getContext_throws(self):
        # a hardened context that THROWS on getContext must be caught — the probe returns false, never
        # propagates (a throw here would crash the island before the fallback ladder can engage).
        proc = _run_probe_logic("""
            const factory = () => ({ getContext: () => { throw new Error('blocked'); } });
            assert.strictEqual(webglSupported(factory), false);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_is_callable_in_node_without_document(self):
        # with no factory AND no `document` (Node), the probe must be callable and return a boolean
        # (false), never throw — the DOM island guard gates the real browser path.
        proc = _run_probe_logic("""
            const v = webglSupported();
            assert.strictEqual(typeof v, 'boolean');
            assert.strictEqual(v, false);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_releases_the_context_it_acquires(self):
        # SIDE-EFFECT-FREE (codex Slice-1 round-1 [medium]): WebGL context quotas are low on
        # constrained browsers / VMs, so the probe must RELEASE the throwaway context it creates —
        # else it can starve the real Slice-2 renderer it is meant to gate. It releases via the
        # WEBGL_lose_context extension's loseContext().
        proc = _run_probe_logic("""
            let lost = 0;
            const gl = { getExtension: (n) =>
              (n === 'WEBGL_lose_context' ? { loseContext: () => { lost++; } } : null) };
            const factory = () => ({ getContext: () => gl });
            assert.strictEqual(webglSupported(factory), true);  // still reports true
            assert.strictEqual(lost, 1);                        // and released exactly once
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_probe_tolerates_missing_or_throwing_cleanup_api(self):
        # the cleanup is best-effort: a context with no WEBGL_lose_context (extension absent) or whose
        # loseContext throws must NOT break the probe — it still returns true, never propagates.
        proc = _run_probe_logic("""
            const noExt = () => ({ getContext: () => ({ getExtension: () => null }) });
            assert.strictEqual(webglSupported(noExt), true);
            const throwsExt = () => ({ getContext: () => ({
              getExtension: () => ({ loseContext: () => { throw new Error('x'); } }) }) });
            assert.strictEqual(webglSupported(throwsExt), true);
            const noGetExt = () => ({ getContext: () => ({}) });   // context lacks getExtension entirely
            assert.strictEqual(webglSupported(noGetExt), true);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)


def _run_render_logic(js_body):
    """Drive the exported CortexRender pure logic under Node (no DOM): the trust-weighted 3D node /
    edge style mappers (M3/M3b/M4) and the M21 fallback-ladder DECISION (chooseRenderer) are factored
    out of the DOM island so the ladder's hierarchy + the trust legibility are testable headless,
    exactly as CortexFilters / webglSupported are."""
    harness = textwrap.dedent("""
        const assert = require('assert');
        const { CortexRender } = require(%r);
        %s
        console.log('OK');
    """) % (str(CORTEX_JS), js_body)
    return subprocess.run([NODE, "-e", harness], capture_output=True, text=True)


@unittest.skipIf(NODE is None, "node not available to drive the island logic")
class TestCortexRenderLogic(unittest.TestCase):
    """Slice 2 — the pure, exported render logic the DOM island uses:
      * the M21 fallback LADDER decision (chooseRenderer) — a strict hierarchy, tested headless;
      * the trust-weighted 3D node style (M3/M4) + edge style (M3b) mappers — trust stays the sole
        size+brightness axis, and the Earmarked harm overlay overrides the dim.
    """

    def test_chooseRenderer_picks_3d_when_webgl_and_init_succeed(self):
        proc = _run_render_logic("""
            assert.strictEqual(
              CortexRender.chooseRenderer({webgl: true, force3dOk: true}), '3d');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_chooseRenderer_falls_to_cytoscape_when_webgl_absent(self):
        # M21 rung 2 — WebGL unavailable → the 2D Cytoscape island, NOT a list, NOT a message.
        proc = _run_render_logic("""
            assert.strictEqual(
              CortexRender.chooseRenderer({webgl: false, cytoscapeOk: true}), 'cytoscape');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_chooseRenderer_falls_to_cytoscape_when_3d_init_fails_despite_webgl(self):
        # the init-failure rung (the regression M21 prevents): the probe passing is NOT sufficient —
        # a 3D constructor throw / blank first paint / lost context still drops to the 2D island.
        proc = _run_render_logic("""
            assert.strictEqual(
              CortexRender.chooseRenderer({webgl: true, force3dOk: false, cytoscapeOk: true}),
              'cytoscape');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_chooseRenderer_falls_to_list_when_both_graph_renderers_fail(self):
        # M21 rung 3 — Cytoscape also fails to render → the searchable list.
        proc = _run_render_logic("""
            assert.strictEqual(
              CortexRender.chooseRenderer(
                {webgl: true, force3dOk: false, cytoscapeOk: false, listOk: true}), 'list');
            assert.strictEqual(
              CortexRender.chooseRenderer(
                {webgl: false, cytoscapeOk: false, listOk: true}), 'list');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_chooseRenderer_falls_to_message_when_even_the_list_fails(self):
        # M21 rung 4 — the floor: the honest message.
        proc = _run_render_logic("""
            assert.strictEqual(
              CortexRender.chooseRenderer(
                {webgl: false, cytoscapeOk: false, listOk: false}), 'message');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_node3d_style_is_trust_weighted_brightest_at_space0(self):
        # M3 — trust is the SOLE size+brightness axis: space-0 brightest+biggest, episodic faintest.
        proc = _run_render_logic("""
            const s0 = CortexRender.node3dStyle({trust: 'space0'});
            const ep = CortexRender.node3dStyle({trust: 'episodic'});
            const as = CortexRender.node3dStyle({trust: 'asserted'});
            const ex = CortexRender.node3dStyle({trust: 'extracted'});
            // brightness (opacity) strictly falls space0 > asserted > extracted > episodic
            assert.ok(s0.opacity > as.opacity);
            assert.ok(as.opacity > ex.opacity);
            assert.ok(ex.opacity > ep.opacity);
            // size falls the same way (trust is the sole size axis)
            assert.ok(s0.size > as.size && as.size > ex.size && ex.size > ep.size);
            // a color is assigned per tier
            assert.ok(typeof s0.color === 'string' && s0.color.length > 0);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_node3d_style_earmarked_overrides_the_trust_dim(self):
        # M4 — the Earmarked harm overlay: a harm node is NEVER dimmed regardless of its trust tier,
        # and reads with the red harm cue (the red-border treatment survives the 3D port).
        proc = _run_render_logic("""
            // a faint episodic node that is Earmarked must NOT stay faint — harm overrides the dim
            const plain = CortexRender.node3dStyle({trust: 'episodic', earmarked: false});
            const harm  = CortexRender.node3dStyle({trust: 'episodic', earmarked: true});
            assert.ok(harm.opacity > plain.opacity);   // never dimmed
            assert.strictEqual(harm.opacity, 1);        // full brightness
            assert.ok(harm.earmarked === true);         // carries the harm cue for the red overlay
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_node3d_color_bakes_luminosity_brightest_at_space0(self):
        # M3/R4 — the vendored bundle does not expose THREE, so per-node material opacity is not
        # reachable; the tier luminosity is baked into the COLOR (blended toward the dark bg by
        # 1-opacity). A bright tier stays near its hue; a faint tier collapses toward #0a0c11. space-0
        # reads brightest, episodic dimmest — the same trust-luminosity legibility via nodeColor.
        proc = _run_render_logic("""
            const lum = (hex) => { const h = hex.replace('#',''); return (
              parseInt(h.slice(0,2),16) + parseInt(h.slice(2,4),16) + parseInt(h.slice(4,6),16)); };
            const s0 = CortexRender.node3dColor({trust:'space0'});
            const as = CortexRender.node3dColor({trust:'asserted'});
            const ex = CortexRender.node3dColor({trust:'extracted'});
            const ep = CortexRender.node3dColor({trust:'episodic'});
            // luminosity (summed channels, against the dark bg) strictly falls with trust
            assert.ok(lum(s0) > lum(as), 'space0 not brighter than asserted');
            assert.ok(lum(as) > lum(ex), 'asserted not brighter than extracted');
            assert.ok(lum(ex) > lum(ep), 'extracted not brighter than episodic');
            // an Earmarked node is full red, never blended toward the bg (M4)
            assert.strictEqual(CortexRender.node3dColor({trust:'episodic', earmarked:true}), '#f87171');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_edge3d_style_follows_the_source_tier_asserted_stronger(self):
        # M3b — trust-weighted EDGES: an asserted-spine edge reads STRONGER than an extracted/episodic
        # one (the curated-vs-hypothesis channel), tied to the per-tier TIER.edge values.
        proc = _run_render_logic("""
            const asserted = CortexRender.edge3dStyle({trust: 'asserted'});
            const extracted = CortexRender.edge3dStyle({trust: 'extracted'});
            const episodic = CortexRender.edge3dStyle({trust: 'episodic'});
            assert.ok(asserted.opacity > extracted.opacity);
            assert.ok(extracted.opacity > episodic.opacity);
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_edge3d_color_bakes_source_tier_luminosity(self):
        # codex round-3 [medium] — the M3b channel must reach the RENDERED edge brightness, not only a
        # coarse width threshold. edge3dColor bakes the source-tier edge opacity into the COLOR
        # (blended toward the dark bg), so an asserted-spine edge reads BRIGHTER than an extracted, and
        # extracted brighter than episodic — extracted vs episodic are NO LONGER identical.
        proc = _run_render_logic("""
            const lum = (hex) => { const h = hex.replace('#',''); return (
              parseInt(h.slice(0,2),16) + parseInt(h.slice(2,4),16) + parseInt(h.slice(4,6),16)); };
            const a = CortexRender.edge3dColor({trust:'asserted'});
            const e = CortexRender.edge3dColor({trust:'extracted'});
            const p = CortexRender.edge3dColor({trust:'episodic'});
            assert.ok(lum(a) > lum(e), 'asserted edge not brighter than extracted');
            assert.ok(lum(e) > lum(p), 'extracted edge not brighter than episodic (channel lost)');
        """)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_3d_link_render_consumes_per_link_luminosity_not_uniform(self):
        # codex round-3 [medium] next-step — prove the SHIPPED 3D chain wires the per-link source-tier
        # luminosity into the rendered edge color (linkColor reads l.__color), not a uniform color +
        # global opacity. A pure edge3dColor passing is not enough; the render chain must consume it.
        js = CORTEX_JS.read_text()
        self.assertIn("edge3dColor", js)
        self.assertIn("__color: CortexRender.edge3dColor", js)
        self.assertIn(".linkColor(function (l) { return l.__color; })", js)
        # the old uniform link color + 0.5 global opacity must be gone (it dropped the M3b channel)
        self.assertNotIn('.linkColor(function () { return "#3a4154"; })', js)

    def test_control_listeners_bound_once_to_a_mutable_current_adapter(self):
        # codex round-4 [medium]: a late 3D demotion (context loss / blank paint) re-enters the ladder
        # at the Cytoscape rung. The control listeners must be bound ONCE and dispatch to a mutable
        # currentAdapter — NOT re-bound per mount (which would leave a stale 3D adapter firing against
        # a destroyed Graph after the failure it is meant to survive). Pin the single-bind structure.
        js = CORTEX_JS.read_text()
        self.assertIn("currentAdapter", js)
        self.assertIn("wireControls", js)
        self.assertIn("controlsWired", js)             # the idempotent one-time-bind guard
        self.assertNotIn("bindControls", js)           # the per-mount re-bind pattern is gone
        # the demotion path swaps the adapter, not re-binds: currentAdapter is assigned in the driver
        self.assertIn("currentAdapter = adapter", js)
        # codex round-6 [medium]: the post-swap replay is CONDITIONAL on a non-default control state —
        # an unconditional render() on the DEFAULT first 3D mount would push the full graph a 2nd time
        # (reheating the sim + racing the first-paint check). Pin the guard.
        self.assertIn("isDefaultControlState", js)
        self.assertIn("if (!isDefaultControlState(controlState())) render();", js)

    def test_render_logic_is_exported_and_wired_in_the_island(self):
        # the DOM island must USE the exported decision + mappers (not an inline parallel copy) so the
        # headless tests actually gate the shipped behavior.
        js = CORTEX_JS.read_text()
        self.assertIn("CortexRender", js)
        self.assertIn("chooseRenderer", js)
        # the M22 freeze contract is wired: the force tick is bounded (cooldown), never unbounded.
        self.assertIn("cooldownTicks", js)
        self.assertIn("cooldownTime", js)
        # nodes are not draggable in 3D (the read-only camera, the analog of autoungrabify)
        self.assertIn("enableNodeDrag", js)
        # M6 labels are TEXT-only HTML overlays positioned via the lib's graph2ScreenCoords and set
        # with .textContent — NEVER the lib's HTML nodeLabel tooltip fed payload content (R5 /
        # cross-cutting #3): a poisoned title is inert (text, not raw HTML). Pin the safe mechanism.
        self.assertIn("graph2ScreenCoords", js)
        self.assertIn("cortex-label", js)
        # the lib's HTML nodeLabel tooltip is NOT fed payload content (it would render as raw HTML)
        self.assertNotIn(".nodeLabel(", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
