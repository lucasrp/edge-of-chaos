"""Slice 7 — the #37 fleet front-end contract (PLAN.md Slice 7, FRONTEND.md / docs/frontend.md).

Converts the hand-rolled f-string HTML to a Flask+Jinja template architecture
(base/partials/components/pages), self-hosts the JS supply chain (no CDN <script src>),
adopts Tabler as the component vocabulary over the PRESERVED dark identity, and ships a
living /ux-catalog. These tests pin the contract; the existing per-surface suites
(test_blog, test_cortex, …) keep pinning the SAME render markers (they must stay green —
the templates emit the same markers).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BLOG = Path(__file__).resolve().parent.parent / "blog"
sys.path.insert(0, str(BLOG))
sys.path.insert(0, str(BLOG.parent / "tools"))


def _client():
    os.environ["EDGE_DASH_AUTH"] = "test:mentee"
    import importlib
    import server
    importlib.reload(server)
    return server


class TemplateArchitecture(unittest.TestCase):
    """The Jinja scaffold exists: base.html + the shared nav partial + the head partial +
    per-surface pages. (docs/frontend.md: base.html, components/, partials/, pages/.)"""

    TPL = BLOG / "templates"

    def test_base_and_scaffold_dirs_exist(self):
        self.assertTrue((self.TPL / "base.html").is_file(), "templates/base.html missing")
        for sub in ("partials", "components", "pages"):
            self.assertTrue((self.TPL / sub).is_dir(), f"templates/{sub}/ missing")

    def test_shared_nav_is_a_partial(self):
        nav = self.TPL / "partials" / "nav.html"
        self.assertTrue(nav.is_file(), "templates/partials/nav.html missing")
        text = nav.read_text()
        self.assertIn("site-nav", text)

    def test_base_defines_head_and_block(self):
        base = (self.TPL / "base.html").read_text()
        self.assertIn("<!DOCTYPE html", base)
        self.assertIn("{% block", base)
        # the head (and thus the dark-identity stylesheet) is pulled in as a shared partial
        self.assertIn("partials/head.html", base)
        head = (self.TPL / "partials" / "head.html").read_text()
        self.assertIn("/static/style.css", head)


class FlaskUsesJinja(unittest.TestCase):
    """The app is configured with a real template folder and routes render through it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        log = Path(self.tmp.name) / "log.jsonl"
        log.write_text("")
        os.environ["EDGE_BLOG_LOG"] = str(log)
        self.server = _client()
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_BLOG_LOG", None)

    def test_app_has_jinja_template_folder(self):
        # the app resolves templates/ (the scaffold), not just inline strings.
        self.assertTrue(self.server.app.jinja_loader is not None)
        # base.html is loadable through the configured loader
        src = self.server.app.jinja_env.loader.get_source(self.server.app.jinja_env, "base.html")
        self.assertTrue(src)

    def test_index_renders_through_template(self):
        body = self.client.get("/").data.decode()
        self.assertIn("<!DOCTYPE html", body)
        self.assertIn("edge — artefatos", body)
        self.assertIn("site-nav", body)


class SelfHostedJS(unittest.TestCase):
    """The supply-chain fix: htmx + Cytoscape are vendored under /static/vendor and served
    locally — NO CDN <script src="https://…"> anywhere. (Closes the standing CDN finding.)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        log = Path(self.tmp.name) / "log.jsonl"
        log.write_text("")
        os.environ["EDGE_BLOG_LOG"] = str(log)
        self.fix = Path(self.tmp.name) / "cortex.json"
        self.fix.write_text(json.dumps(
            {"nodes": [{"id": "g0", "label": "Genesis", "title": "edge", "trust": "space0"}],
             "edges": []}))
        os.environ["EDGE_CORTEX_FIXTURE"] = str(self.fix)
        os.environ["EDGE_GROUP"] = "edge-next"
        self.server = _client()
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_BLOG_LOG", None)
        os.environ.pop("EDGE_CORTEX_FIXTURE", None)
        os.environ.pop("EDGE_GROUP", None)

    def test_vendor_files_on_disk(self):
        vendor = BLOG / "static" / "vendor"
        self.assertTrue((vendor / "htmx.min.js").is_file(), "vendored htmx missing")
        self.assertTrue((vendor / "cytoscape.min.js").is_file(), "vendored cytoscape missing")

    def test_no_cdn_script_src_on_any_page(self):
        for path in ("/", "/chat", "/briefing", "/direction", "/docs", "/wiki", "/cortex"):
            body = self.client.get(path).data.decode()
            self.assertNotIn("unpkg.com", body, f"{path} still loads from unpkg CDN")
            self.assertNotIn('src="https://', body, f"{path} loads a script over a remote URL")

    def test_htmx_served_locally(self):
        body = self.client.get("/").data.decode()
        self.assertIn("htmx", body)  # the marker the existing suite pins
        self.assertIn("/static/vendor/htmx.min.js", body)
        r = self.client.get("/static/vendor/htmx.min.js")
        self.assertEqual(r.status_code, 200)

    def test_cytoscape_served_locally(self):
        body = self.client.get("/cortex").data.decode()
        self.assertIn("cytoscape", body)  # the marker the existing suite pins
        self.assertIn("/static/vendor/cytoscape.min.js", body)
        r = self.client.get("/static/vendor/cytoscape.min.js")
        self.assertEqual(r.status_code, 200)


class UxCatalog(unittest.TestCase):
    """A living /ux-catalog: the design tokens + the Jinja macros/components, self-documenting."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        log = Path(self.tmp.name) / "log.jsonl"
        log.write_text("")
        os.environ["EDGE_BLOG_LOG"] = str(log)
        self.server = _client()
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_BLOG_LOG", None)

    def test_ux_catalog_route_lists_tokens_and_macros(self):
        r = self.client.get("/ux-catalog")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        self.assertIn("ux-catalog", body)
        # the design tokens are documented
        self.assertIn("--accent", body)
        self.assertIn("--bg", body)
        # the shared component vocabulary is shown
        self.assertIn("composer", body)
        self.assertIn("site-nav", body)
        # it is in the shared chrome (one app)
        self.assertIn("<!DOCTYPE html", body)

    def test_ux_catalog_is_in_the_nav(self):
        body = self.client.get("/").data.decode()
        self.assertIn('href="/ux-catalog"', body)


class TablerOverDarkIdentity(unittest.TestCase):
    """Tabler/Bootstrap-5 is the component vocabulary, but the dark identity is PRESERVED:
    the style.css :root tokens still own the palette and load AFTER Tabler so they win."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        log = Path(self.tmp.name) / "log.jsonl"
        log.write_text("")
        os.environ["EDGE_BLOG_LOG"] = str(log)
        self.server = _client()
        self.client = self.server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("EDGE_BLOG_LOG", None)

    def test_tabler_vendored_and_loaded(self):
        vendor = BLOG / "static" / "vendor"
        self.assertTrue((vendor / "tabler.min.css").is_file(), "vendored tabler css missing")
        body = self.client.get("/").data.decode()
        self.assertIn("/static/vendor/tabler.min.css", body)

    def test_dark_identity_tokens_load_after_tabler(self):
        # the edge dark theme (style.css) must come AFTER tabler so the :root palette wins —
        # the operator-approved dark identity does not regress under the component framework.
        body = self.client.get("/").data.decode()
        self.assertLess(body.index("tabler.min.css"), body.index("/static/style.css"),
                        "style.css (dark identity) must load AFTER tabler to win the cascade")


class DefaultLogNotPollutedBySmokeTests(unittest.TestCase):
    """CONTRACT C1 guard (codex Slice-7 round-1 [high]): the DEFAULT committed authoritative log
    (state/events/log.jsonl) must never gain ad-hoc Voz smoke-test events. A `git add -A` once swept
    live browser-test voz.* events into it — unresolved voz.comment events fold as REAL open
    Directives, poisoning shipped state. Auth/browser coverage belongs in hermetic tests that point
    EDGE_BLOG_LOG at a tmp file; the committed log must stay clean. This tripwire fails if a known
    smoke-test body (or the manual-test shape) reappears in the committed log."""

    LOG = BLOG.parent / "state" / "events" / "log.jsonl"

    def test_committed_log_has_no_smoke_test_voz_bodies(self):
        if not self.LOG.is_file():
            self.skipTest("no committed default log in this checkout")
        text = self.LOG.read_text()
        for body in ("teste-do-browser", "via-localhost", "sem-porta", "pwned"):
            self.assertNotIn(body, text,
                             f"smoke-test Voz body {body!r} leaked into the committed authoritative log")

    def test_committed_log_is_intact(self):
        # the committed default log must satisfy the SAME strict integrity check the drain gates on —
        # contiguous int seqs, dict envelopes, no poisoned payload (a polluted/seq-gapped commit fails).
        if not self.LOG.is_file():
            self.skipTest("no committed default log in this checkout")
        import grill_drain
        self.assertTrue(grill_drain.log_is_intact(self.LOG),
                        "the committed default authoritative log is not intact")


if __name__ == "__main__":
    unittest.main(verbosity=2)
