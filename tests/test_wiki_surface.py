"""Slice 5b — the emergent-knowledge surface (`GET /wiki` index + `GET /wiki/<cluster>` drill-down).

AUDIT.md gap C / PLAN.md Slice 5b: the edge's emergent Knowledge clusters (the llm-wiki) live as
rendered pages (`state/wiki/index.html` + `cluster-*.html`) but `blog/server.py` exposes no wiki
route — the mentee reaches them only as files. This surfaces them in-dashboard: a wiki index and a
cluster-thread drill-down, in the shared dark theme + nav.

THE SECURITY REQUIREMENT (PLAN.md, do not skip): the wiki pages are EDGE-GENERATED, SOURCE-DERIVED
HTML — a `<script>` / `on*=` handler / `javascript:` URL injected from a source could otherwise
execute SAME-ORIGIN in the authed dashboard, read state, and fire an authenticated log-mutating POST
(defeating the Slice-1 write gate). So a cluster page renders INERT: the raw HTML is isolated in a
`sandbox`ed iframe (no `allow-scripts`, no `allow-same-origin`) served with a `default-src 'none'`
CSP — scripts never run, handlers never fire, and even if one did it cannot reach the parent origin.

These tests point the wiki root at a throwaway temp tree (CONTRACT C1 — never the real state/wiki as
the system under test), so the surface is exercised hermetically.
"""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _ev(seq, ts, type_, payload):
    import json
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "payload": payload})


# A minimal, well-formed wiki tree: an index that lists two clusters + the two cluster pages, in the
# same shape the real wiki_render emits (a complete HTML doc with relative cluster-*.html links).
_INDEX = (
    "<!doctype html><html><head><title>edge-next wiki</title></head><body>"
    "<h1>edge-next wiki</h1><p class=meta>2 clusters</p>"
    '<p>• <a href="cluster-introspectivememory.html">Introspective memory</a> '
    '<span class=meta>(3)</span></p>'
    '<p>• <a href="cluster-noncurated.html">Non-curated (hypothesis)</a> '
    '<span class=meta>(47)</span></p></body></html>'
)
_CLUSTER_A = (
    "<!doctype html><html><head><title>Introspective memory</title></head><body>"
    "<h1>Introspective memory</h1><p class=meta>knowledge cluster · 3 entities</p>"
    "<div>Introspective memory is the durable trail of the beat's own history.</div>"
    "<h3>entities</h3><p>• ADR-0007</p>"
    '<p><a href="index.html">← index</a></p></body></html>'
)
_CLUSTER_B = (
    "<!doctype html><html><head><title>Non-curated</title></head><body>"
    "<h1>Non-curated (hypothesis)</h1><div>raw hypothesis cloud.</div>"
    '<p><a href="index.html">← index</a></p></body></html>'
)


class _WikiBase(unittest.TestCase):
    """A hermetic blog server whose wiki root points at a throwaway tree of index + cluster pages."""

    INDEX = _INDEX
    CLUSTERS = {
        "cluster-introspectivememory.html": _CLUSTER_A,
        "cluster-noncurated.html": _CLUSTER_B,
    }
    LOG_LINES = []

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "entries").mkdir()
        (root / "static").mkdir()

        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "index.html").write_text(self.INDEX)
        for name, body in self.CLUSTERS.items():
            (wiki / name).write_text(body)

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join(self.LOG_LINES) + ("\n" if self.LOG_LINES else ""))

        os.environ["EDGE_BLOG_ENTRIES"] = str(root / "entries")
        os.environ["EDGE_BLOG_STATIC"] = str(root / "static")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_WIKI_ROOT"] = str(wiki)

        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        os.environ.pop("EDGE_WIKI_ROOT", None)
        self.tmp.cleanup()


class TestWikiIndexListsClusters(_WikiBase):
    """GET /wiki lists every Knowledge cluster as a navigable in-dashboard link — none forces the
    mentee back to a file path, and the relative cluster-*.html links are rewritten to /wiki/<id>."""

    def test_index_renders_200(self):
        self.assertEqual(self.client.get("/wiki").status_code, 200)

    def test_index_lists_each_cluster_as_a_dashboard_link(self):
        html = self.client.get("/wiki").get_data(as_text=True)
        # the relative cluster file links are rewritten to in-dashboard drill-down routes
        self.assertIn("/wiki/introspectivememory", html)
        self.assertIn("/wiki/noncurated", html)
        # …never the raw file path the mentee would otherwise open
        self.assertNotIn('href="cluster-introspectivememory.html"', html)

    def test_index_shows_cluster_titles(self):
        html = self.client.get("/wiki").get_data(as_text=True)
        self.assertIn("Introspective memory", html)
        self.assertIn("Non-curated", html)

    def test_index_carries_the_shared_nav_and_theme(self):
        html = self.client.get("/wiki").get_data(as_text=True)
        self.assertIn('class="site-nav"', html)
        self.assertIn("/static/style.css", html)
        self.assertIn('aria-current="page"', html)  # /wiki marked current on its own page


class TestClusterDrillDown(_WikiBase):
    """GET /wiki/<cluster> renders one cluster thread in-dashboard, isolated in a sandboxed iframe."""

    def test_cluster_renders_200(self):
        self.assertEqual(self.client.get("/wiki/introspectivememory").status_code, 200)

    def test_cluster_page_embeds_the_content_in_a_sandboxed_iframe(self):
        html = self.client.get("/wiki/introspectivememory").get_data(as_text=True)
        # the boundary: the edge-generated HTML is isolated in a sandboxed iframe (no allow-scripts,
        # no allow-same-origin) — scripts never run, and it cannot reach the parent origin.
        self.assertIn("<iframe", html.lower())
        self.assertIn("sandbox", html.lower())
        # the iframe points at the raw-content sub-route, not at the parent doc.
        self.assertIn("/wiki/introspectivememory/raw", html)

    def test_cluster_page_carries_the_shared_nav_and_theme(self):
        html = self.client.get("/wiki/introspectivememory").get_data(as_text=True)
        self.assertIn('class="site-nav"', html)
        self.assertIn("/static/style.css", html)

    def test_raw_route_serves_the_cluster_html_with_a_locking_csp(self):
        r = self.client.get("/wiki/introspectivememory/raw")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn("Introspective memory", body)
        # the raw content ships with a CSP that forbids ALL active content + a sandbox directive, so
        # even loaded directly it executes nothing same-origin.
        csp = r.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("sandbox", csp)

    def test_unknown_cluster_is_404(self):
        self.assertEqual(self.client.get("/wiki/ghost").status_code, 404)
        self.assertEqual(self.client.get("/wiki/ghost/raw").status_code, 404)

    def test_cluster_id_traversal_is_404_not_a_filesystem_read(self):
        # the cluster id resolves over the on-disk allowlist (cluster-<id>.html within the wiki root),
        # so a traversal attempt reaches no file → 404, never an arbitrary read.
        self.assertEqual(self.client.get("/wiki/..%2f..%2fetc%2fpasswd").status_code, 404)
        self.assertEqual(self.client.get("/wiki/index/raw").status_code, 404)  # not a cluster file


# A malicious cluster page: a <script>, an onerror= handler, and a javascript: URL — the three
# same-origin code-execution vectors an injected source could smuggle into an edge-generated page.
_MALICIOUS_CLUSTER = (
    "<!doctype html><html><head><title>Pwned cluster</title></head><body>"
    "<h1>Pwned cluster</h1>"
    "<script>fetch('/chat/comment',{method:'POST',body:'body=pwned'})</script>"
    "<img src=x onerror=\"fetch('/e/x/vote',{method:'POST'})\">"
    "<a href=\"javascript:fetch('/chat/comment',{method:'POST',body:'body=js'})\">win</a>"
    "<div>legible cluster prose.</div></body></html>"
)


class TestMaliciousClusterIsInertAndCannotAppend(_WikiBase):
    """ACCEPTANCE (PLAN.md Slice 5b): a malicious cluster page — a `<script>`, an `onerror=` handler,
    a `javascript:` URL — renders INERT (sandboxed) and CANNOT perform an authenticated append. The
    threat: a handler executing same-origin in the authed dashboard fires a log-mutating POST,
    defeating the Slice-1 write gate. Auth is ON (the real posture) and the test_client is loopback —
    so a write WOULD be authorized; the page must be inert because nothing CAN execute the POST."""

    CLUSTERS = {"cluster-pwned.html": _MALICIOUS_CLUSTER}

    def setUp(self):
        os.environ["EDGE_DASH_AUTH"] = "on"
        super().setUp()

    def tearDown(self):
        os.environ.pop("EDGE_DASH_AUTH", None)
        super().tearDown()

    def _count(self):
        return len([ln for ln in self.log.read_text().splitlines() if ln.strip()])

    def test_drilldown_page_does_not_inline_the_script(self):
        # the drill-down wrapper page embeds an iframe, NOT the raw HTML — the script never lands in
        # the authed parent document where it would execute same-origin.
        html = self.client.get("/wiki/pwned").get_data(as_text=True)
        self.assertNotIn("<script>fetch", html)

    def test_raw_route_is_sandboxed_so_the_script_cannot_execute_same_origin(self):
        # the raw route DOES carry the literal cluster HTML (it is the iframe src), but it ships under
        # default-src 'none' + sandbox, so the browser executes none of it and it has no same-origin
        # access to the dashboard — the injected POSTs are dead.
        r = self.client.get("/wiki/pwned/raw")
        csp = r.headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("sandbox", csp)
        # the sandbox must NOT re-enable scripts or same-origin (that would defeat the boundary).
        self.assertNotIn("allow-scripts", csp)
        self.assertNotIn("allow-same-origin", csp)
        # X-Frame-Options / nosniff harden the response too.
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")

    def test_serving_the_malicious_cluster_performs_no_append(self):
        # the strong property: serving the malicious cluster (both the wrapper AND the raw route)
        # cannot mutate the authoritative log — the injected POSTs are inert, so the count is steady.
        before = self._count()
        self.assertEqual(self.client.get("/wiki/pwned").status_code, 200)
        self.assertEqual(self.client.get("/wiki/pwned/raw").status_code, 200)
        self.assertEqual(self._count(), before)

    def test_legible_cluster_prose_still_reaches_the_mentee(self):
        # the boundary isolates the attack but keeps the readable cluster — not a blanket reject.
        raw = self.client.get("/wiki/pwned/raw").get_data(as_text=True)
        self.assertIn("legible cluster prose.", raw)


class TestMaliciousClusterFilenameCannotXssTheIndex(_WikiBase):
    """SECURITY (codex round-2 [high]): the /wiki INDEX is an unsandboxed authed page. A corrupt /
    drifted wiki tree could carry a cluster FILENAME like `cluster-x" onclick="alert(1).html` — if
    the registry returned that suffix verbatim and the index interpolated it into an `href="..."`, it
    would break out and bind a same-origin handler (an authenticated POST, defeating the Slice-1
    gate). The registry must FAIL CLOSED: only a canonical, letters-only cluster id is accepted (the
    wiki renderer's own naming rule), so a malformed filename is dropped, never linked."""

    CLUSTERS = {
        "cluster-introspectivememory.html": _CLUSTER_A,
        # a poisoned filename: a quote + an event-handler payload smuggled into the stem.
        'cluster-x" onclick="alert(1).html': _CLUSTER_B,
    }

    def test_index_does_not_emit_the_poisoned_filename_as_markup(self):
        html = self.client.get("/wiki").get_data(as_text=True)
        # no live attribute breakout — the handler text never appears as a live `onclick="`.
        self.assertNotIn('onclick="', html)
        # the canonical cluster still lists (the boundary drops only the malformed one).
        self.assertIn("/wiki/introspectivememory", html)

    def test_poisoned_cluster_id_is_not_registered(self):
        ids = {cid for cid, _t, _p in self.server._cluster_registry()}
        self.assertIn("introspectivememory", ids)
        # the malformed id is rejected by the canonical-id gate — it never enters the allowlist.
        self.assertNotIn('x" onclick="alert(1)', ids)
        for cid in ids:
            self.assertRegex(cid, r"^[a-z]+$", f"non-canonical cluster id leaked: {cid!r}")


class TestWikiReachableFromBriefingAndDistills(unittest.TestCase):
    """ACCEPTANCE (PLAN.md Slice 5b): clusters are reachable from /briefing AND from an Artefato's
    `distills` — not just a standalone /wiki route. The blog index renders an Artefato's distilled
    clusters (`distills: ["cluster:<id>"]`) as links into /wiki/<id>; /briefing links to /wiki."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "entries").mkdir()
        (root / "static").mkdir()
        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "index.html").write_text(_INDEX)
        (wiki / "cluster-foo.html").write_text(_CLUSTER_A)

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published",
                {"slug": "alpha-post", "cites": [], "distills": ["cluster:foo"], "proposes": []}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel",
                {"slug": "alpha-post", "intent": "open: alpha."}),
        ]) + "\n")

        os.environ["EDGE_BLOG_ENTRIES"] = str(root / "entries")
        os.environ["EDGE_BLOG_STATIC"] = str(root / "static")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_WIKI_ROOT"] = str(wiki)
        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.client = server.app.test_client()

    def tearDown(self):
        os.environ.pop("EDGE_WIKI_ROOT", None)
        self.tmp.cleanup()

    def test_artefato_distills_a_cluster_link_into_the_wiki(self):
        # an Artefato's distilled cluster (`distills: ["cluster:foo"]`) is a live drill-down into the
        # cluster thread — the graph→knowledge bridge from the work feed.
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("/wiki/foo", html)

    def test_briefing_links_to_the_wiki(self):
        html = self.client.get("/briefing").get_data(as_text=True)
        self.assertIn('href="/wiki"', html)

    def test_nav_includes_a_wiki_entry_on_every_surface(self):
        for path in ("/", "/chat", "/briefing", "/direction", "/docs"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn('href="/wiki"', html, f"{path} nav is missing the wiki link")


if __name__ == "__main__":
    unittest.main()
