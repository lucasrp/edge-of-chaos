"""Slice 5a — the design-doc surfaces (`GET /docs` index + `GET /docs/<doc_id>` per-doc view).

AUDIT.md gap C / PLAN.md Slice 5a: the documentation itself must be navigable IN the dashboard, not
read as files. The FOUR design-doc types — glossary (`CONTEXT.md`), the ADRs (`docs/adr/*.md`), the
**Idiom** standing page (`state/idiom.md`), and the **Source roadmap** (`state/source-roadmap.md`) —
each list on an index and render as a per-doc HTML view, in the shared dark theme + nav. None forces
the mentee back to a file path.

THE SECURITY REQUIREMENT (PLAN.md, do not skip): these docs are edge-authored AND source-derived, so
the markdown can carry raw HTML, event handlers, or `javascript:` URLs. Every doc route renders
through the SHARED allowlist sanitizer (`docmd`), so nothing executes same-origin in the authed
dashboard — an injected `<script>` / handler / `javascript:` URL renders INERT and cannot perform an
authenticated append (the negative same-origin test, below).

These tests point the doc roots at a throwaway temp tree (CONTRACT C1 — never the real repo docs as
the system under test), so the surface is exercised hermetically.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class _DocsBase(unittest.TestCase):
    """A hermetic blog server whose doc roots point at a throwaway tree of the four doc types."""

    # subclasses may override to seed extra / malicious doc content
    GLOSSARY = "# Glossary\n\n**Mentee**: the person the edge serves.\n"
    IDIOM = "# Idiom\n\n**beat** — the work cycle.\n"
    ROADMAP = "# Source-roadmap\n\n## NATIVE: Claude sessions\n- locator: `~/.claude/projects/`\n"
    ADRS = {
        "0017-direct-voz.md": "# Direct Voz is a strong guide\n\n## Status\n\naccepted\n",
        "0007-direction-two-tier.md": "# Direction is a two-tier projection\n",
    }
    LOG_LINES = []

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "entries").mkdir()
        (root / "static").mkdir()

        # the four doc roots, env-overridable (CONTRACT C1 — a throwaway tree, never real state/).
        (root / "CONTEXT.md").write_text(self.GLOSSARY)
        state = root / "state"
        state.mkdir()
        (state / "idiom.md").write_text(self.IDIOM)
        (state / "source-roadmap.md").write_text(self.ROADMAP)
        adr = root / "docs" / "adr"
        adr.mkdir(parents=True)
        for name, body in self.ADRS.items():
            (adr / name).write_text(body)

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join(self.LOG_LINES) + ("\n" if self.LOG_LINES else ""))

        os.environ["EDGE_BLOG_ENTRIES"] = str(root / "entries")
        os.environ["EDGE_BLOG_STATIC"] = str(root / "static")
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        os.environ["EDGE_DOCS_GLOSSARY"] = str(root / "CONTEXT.md")
        os.environ["EDGE_DOCS_IDIOM"] = str(state / "idiom.md")
        os.environ["EDGE_DOCS_ROADMAP"] = str(state / "source-roadmap.md")
        os.environ["EDGE_DOCS_ADR_DIR"] = str(adr)

        sys.path.insert(0, str(REPO / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        for k in ("EDGE_DOCS_GLOSSARY", "EDGE_DOCS_IDIOM", "EDGE_DOCS_ROADMAP", "EDGE_DOCS_ADR_DIR"):
            os.environ.pop(k, None)
        self.tmp.cleanup()


class TestEachDocTypeRendersInDashboard(_DocsBase):
    """All four types render as a per-doc HTML view — none forces the mentee back to a file path."""

    def test_glossary_renders(self):
        html = self.client.get("/docs/glossary").get_data(as_text=True)
        self.assertEqual(self.client.get("/docs/glossary").status_code, 200)
        self.assertIn("<h1>Glossary</h1>", html)
        self.assertIn("Mentee", html)

    def test_idiom_renders(self):
        html = self.client.get("/docs/idiom").get_data(as_text=True)
        self.assertIn("<h1>Idiom</h1>", html)
        self.assertIn("the work cycle", html)

    def test_source_roadmap_renders(self):
        html = self.client.get("/docs/source-roadmap").get_data(as_text=True)
        self.assertIn("<h1>Source-roadmap</h1>", html)
        self.assertIn("Claude sessions", html)

    def test_adr_renders(self):
        html = self.client.get("/docs/adr/0017-direct-voz").get_data(as_text=True)
        self.assertEqual(self.client.get("/docs/adr/0017-direct-voz").status_code, 200)
        self.assertIn("Direct Voz is a strong guide", html)
        self.assertIn("accepted", html)

    def test_doc_view_carries_the_shared_nav_and_theme(self):
        html = self.client.get("/docs/glossary").get_data(as_text=True)
        self.assertIn('class="site-nav"', html)
        self.assertIn("/static/style.css", html)

    def test_unknown_doc_id_is_404_not_a_filesystem_read(self):
        # the registry is the allowlist — an unknown/forged id (incl. a traversal attempt) resolves
        # to nothing → 404, never an arbitrary filesystem read.
        self.assertEqual(self.client.get("/docs/nope").status_code, 404)
        self.assertEqual(self.client.get("/docs/adr/0099-ghost").status_code, 404)
        self.assertEqual(self.client.get("/docs/../../../etc/passwd").status_code, 404)


_MALICIOUS_DOC = (
    "# Pwned ADR\n\n"
    "intro paragraph.\n\n"
    "<script>fetch('/chat/comment',{method:'POST',body:'body=pwned'})</script>\n\n"
    '<img src=x onerror="fetch(\'/e/x/vote\',{method:\'POST\'})">\n\n'
    "click [here](javascript:fetch('/chat/comment',{method:'POST',body:'body=js'})) to win.\n"
)


class TestMaliciousDocIsInertAndCannotAppend(_DocsBase):
    """ACCEPTANCE (PLAN.md Slice 5a): a malicious markdown fixture on a design-doc route renders
    INERT — a `<script>`, an `onerror=` handler, a `javascript:` URL stripped/sandboxed — and CANNOT
    perform an authenticated append (the same negative same-origin test as 5b). The threat: an
    injected handler executing same-origin in the authed dashboard could fire a log-mutating POST,
    defeating the Slice-1 write gate. So the doc renders harmless even with auth fully enabled."""

    # the malicious doc rides in as an ADR (a real source-derived doc surface).
    ADRS = {"0099-pwned.md": _MALICIOUS_DOC}

    def setUp(self):
        # auth ON (the dashboard's real posture) — proves the doc cannot ride a same-origin session
        # to mutate the log. A local test_client request is loopback, so a write WOULD be authorized
        # — which is exactly why the doc must be inert: there is nothing to execute the POST.
        os.environ["EDGE_DASH_AUTH"] = "on"
        super().setUp()

    def tearDown(self):
        os.environ.pop("EDGE_DASH_AUTH", None)
        super().tearDown()

    def _count(self):
        return len([ln for ln in self.log.read_text().splitlines() if ln.strip()])

    def test_script_renders_inert(self):
        html = self.client.get("/docs/adr/0099-pwned").get_data(as_text=True)
        # no live <script> tag — the raw script is escaped to inert text.
        self.assertNotIn("<script>fetch", html)
        self.assertIn("&lt;script&gt;", html)  # present, escaped, inert

    def test_event_handler_renders_inert(self):
        html = self.client.get("/docs/adr/0099-pwned").get_data(as_text=True)
        self.assertNotIn("<img", html.lower())
        self.assertNotIn('onerror="', html.lower())

    def test_javascript_url_is_not_a_live_anchor(self):
        html = self.client.get("/docs/adr/0099-pwned").get_data(as_text=True)
        self.assertNotIn('href="javascript:', html.lower())

    def test_rendering_the_malicious_doc_performs_no_append(self):
        # the strong property: serving the malicious doc cannot mutate the authoritative log — the
        # injected POSTs are inert markup, so the log count is unchanged after the render.
        before = self._count()
        r = self.client.get("/docs/adr/0099-pwned")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._count(), before)  # nothing appended — the injection is dead

    def test_legitimate_doc_content_still_renders(self):
        # the boundary strips the attack but keeps the readable doc — it is not a blanket reject.
        html = self.client.get("/docs/adr/0099-pwned").get_data(as_text=True)
        self.assertIn("<h1>Pwned ADR</h1>", html)
        self.assertIn("intro paragraph.", html)


class TestDocsIndexListsAllFourTypes(_DocsBase):
    """GET /docs lists every design-doc type — none forces the mentee to a file path."""

    def test_index_renders_200(self):
        r = self.client.get("/docs")
        self.assertEqual(r.status_code, 200)

    def test_index_lists_all_four_doc_types(self):
        html = self.client.get("/docs").get_data(as_text=True)
        # glossary, Idiom, Source roadmap each appear as a navigable link…
        self.assertIn("/docs/glossary", html)
        self.assertIn("/docs/idiom", html)
        self.assertIn("/docs/source-roadmap", html)
        # …and the ADRs (at least one) appear as links.
        self.assertIn("/docs/adr/0017-direct-voz", html)

    def test_index_carries_the_shared_nav(self):
        html = self.client.get("/docs").get_data(as_text=True)
        self.assertIn('class="site-nav"', html)
        # the docs entry is marked current on its own page
        self.assertIn('aria-current="page"', html)

    def test_nav_includes_a_docs_entry_on_every_surface(self):
        # the shared nav gains a docs link, so every surface can reach the docs (one app, not files).
        for path in ("/", "/chat", "/briefing", "/direction"):
            html = self.client.get(path).get_data(as_text=True)
            self.assertIn('href="/docs"', html, f"{path} nav is missing the docs link")


if __name__ == "__main__":
    unittest.main()
