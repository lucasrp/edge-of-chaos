"""Blog v0 — the index is projected from the eventlog (blog-style), and entries are served.

Slice 1 of the dashboard: posts are described blog-style (title, date, blurb) with links to the
artifacts each dispatch created (cites/distills/proposes), newest-first. Entry-serving + 404 unchanged.
"""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


def _ev(seq, ts, type_, slug, payload_extra=None):
    payload = {"slug": slug}
    payload.update(payload_extra or {})
    return json.dumps({"seq": seq, "ts": ts, "type": type_, "subject": f"artefato:{slug}",
                       "payload": payload})


class TestBlogSplitHomePaths(unittest.TestCase):
    def test_edge_home_is_default_for_installed_runtime(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "installed-edge"
            env = {"EDGE_HOME": str(runtime)}
            with unittest.mock.patch.dict(os.environ, env, clear=False):
                for key in ("EDGE_BLOG_ENTRIES", "EDGE_BLOG_STATIC", "EDGE_BLOG_LOG"):
                    os.environ.pop(key, None)
                self.assertEqual(server._entries(), runtime / "blog" / "entries")
                self.assertEqual(server._static(), server.BASE / "static")
                self.assertEqual(server._log(), runtime / "state" / "events" / "log.jsonl")
                response = server.app.test_client().get("/static/style.css")
                self.assertEqual(response.status_code, 200)
                self.assertGreater(len(response.data), 0)

    def test_explicit_paths_override_edge_home(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            explicit = root / "explicit"
            with unittest.mock.patch.dict(os.environ, {
                "EDGE_HOME": str(root / "installed-edge"),
                "EDGE_BLOG_ENTRIES": str(explicit / "entries"),
                "EDGE_BLOG_STATIC": str(explicit / "static"),
                "EDGE_BLOG_LOG": str(explicit / "log.jsonl"),
            }):
                self.assertEqual(server._entries(), explicit / "entries")
                self.assertEqual(server._static(), explicit / "static")
                self.assertEqual(server._log(), explicit / "log.jsonl")


class TestBlog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()
        for slug in ("alpha-post", "beta-post", "foo-bar"):
            (entries / f"{slug}.html").write_text(f"<html><body><h1>{slug}</h1></body></html>")

        # fixture log: alpha published first (older), beta second (newer)
        log = root / "log.jsonl"
        log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "alpha-post",
                {"cites": ["source:arxiv:2606.06448"], "distills": ["cluster:foo"],
                 "proposes": [{"body": "do the X thing", "kind": "thread"}]}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel", "alpha-post",
                {"intent": "open: alpha — resolved alpha. next bet: ship it."}),
            _ev(3, "2026-06-12T15:30:00+00:00", "artefato.published", "beta-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(4, "2026-06-12T15:30:01+00:00", "intent.kernel", "beta-post",
                {"intent": "open: beta — resolved beta. next bet: the dashboard."}),
            _ev(5, "2026-06-12T15:30:02+00:00", "artefato.teaser", "beta-post",
                {"text": "First teaser paragraph.\n\nSecond teaser paragraph."}),
        ]) + "\n")

        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(log)
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server
        importlib.reload(server)
        self.client = server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_is_blog_style_from_log(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        body = r.data.decode()
        # titles (slug → words) for both published artefatos
        self.assertIn("alpha post", body)
        self.assertIn("beta post", body)
        # blog-style: each post links to its entry page
        self.assertIn('/e/beta-post.html', body)
        self.assertIn('/e/alpha-post.html', body)
        # date is shown
        self.assertIn("2026-06-12", body)
        # layout A: a post with a teaser shows its paragraphs as separate <p>
        self.assertIn("<p>First teaser paragraph.</p>", body)
        self.assertIn("<p>Second teaser paragraph.</p>", body)
        # a post without a teaser falls back to the kernel blurb
        self.assertIn("resolved alpha", body)
        # layout A: the read-more link is present; the artifact chips are gone
        self.assertIn("ler o artefato", body)
        self.assertNotIn("cluster:foo", body)
        self.assertNotIn("do the X thing", body)
        self.assertNotIn("source:arxiv:2606.06448", body)

    def test_index_newest_first(self):
        body = self.client.get("/").data.decode()
        self.assertLess(body.index("beta-post"), body.index("alpha-post"))

    def test_entry_served(self):
        r = self.client.get("/e/beta-post.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"beta-post", r.data)

    def test_missing_entry_404(self):
        self.assertEqual(self.client.get("/e/nope.html").status_code, 404)


class TestVozRail(unittest.TestCase):
    """Slice 2 — the Voz rail: comments, votes, replies. Every read is a fold over the log,
    every write appends an event (no parallel store)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        entries = root / "entries"
        entries.mkdir()
        for slug in ("alpha-post", "beta-post"):
            (entries / f"{slug}.html").write_text(f"<html><body><h1>{slug}</h1></body></html>")

        self.log = root / "log.jsonl"
        self.log.write_text("\n".join([
            _ev(1, "2026-06-10T09:00:00+00:00", "artefato.published", "alpha-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(2, "2026-06-10T09:00:01+00:00", "intent.kernel", "alpha-post",
                {"intent": "open: alpha."}),
            _ev(3, "2026-06-12T15:30:00+00:00", "artefato.published", "beta-post",
                {"cites": [], "distills": [], "proposes": []}),
            _ev(4, "2026-06-12T15:30:01+00:00", "intent.kernel", "beta-post",
                {"intent": "open: beta."}),
        ]) + "\n")

        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(root)
        os.environ["EDGE_BLOG_LOG"] = str(self.log)
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server
        importlib.reload(server)
        self.server = server
        self.client = server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def _events(self, type_):
        out = []
        for line in self.log.read_text().splitlines():
            if line.strip():
                e = json.loads(line)
                if e.get("type") == type_:
                    out.append(e)
        return out

    def test_post_comment_appends_event_and_shows_body(self):
        r = self.client.post("/e/alpha-post/comment", data={"body": "tighten the framing"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("tighten the framing", r.data.decode())
        # it appended exactly one voz.comment, targeted at the slug
        comments = self._events("voz.comment")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["payload"]["target_ref"], "alpha-post")
        self.assertEqual(comments[0]["payload"]["body"], "tighten the framing")

    def test_vote_is_a_toggle_capped_at_one(self):
        # first 👍 → recorded as +1, shown active
        r = self.client.post("/e/alpha-post/vote", data={"value": "1"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._events("voz.vote")[-1]["payload"], {"slug": "alpha-post", "value": 1})
        self.assertIn('aria-pressed="true"', r.data.decode())  # the like is active
        # 👍 again toggles it OFF (value 0) — never accumulates past 1
        r = self.client.post("/e/alpha-post/vote", data={"value": "1"})
        self.assertEqual(self._events("voz.vote")[-1]["payload"]["value"], 0)
        self.assertNotIn('aria-pressed="true"', r.data.decode())  # nothing active after unlike
        # 👎 from neutral switches cleanly to -1 (mutually exclusive)
        r = self.client.post("/e/alpha-post/vote", data={"value": "-1"})
        self.assertEqual(self._events("voz.vote")[-1]["payload"]["value"], -1)

    def test_open_comments_are_those_without_a_terminal_resolved(self):
        # two comments; only the first reaches a TERMINAL voz.resolved (ADR-0017: openness keys on
        # voz.resolved absence, NOT voz.reply — a reply is presentation only).
        self.client.post("/e/alpha-post/comment", data={"body": "first"})
        cid = self._events("voz.comment")[0]["payload"]["comment_id"]
        self.client.post("/e/beta-post/comment", data={"body": "second"})
        self.server._append("voz.reply", "voz:alpha-post",
                             {"comment_id": cid, "body": "answered"})
        self.server._append("voz.resolved", "voz:alpha-post",
                             {"comment_id": cid, "outcome": "replied", "grill_run_id": "g1"})
        opens = self.server.open_comments()
        bodies = [c["body"] for c in opens]
        self.assertEqual(bodies, ["second"])

    def test_reply_renders_inline_under_its_comment(self):
        self.client.post("/e/alpha-post/comment", data={"body": "first"})
        cid = self._events("voz.comment")[0]["payload"]["comment_id"]
        self.server._append("voz.reply", "voz:alpha-post",
                            {"comment_id": cid, "body": "edge answered here"})
        thread = self.server._render_thread("alpha-post")
        self.assertIn("first", thread)
        self.assertIn("edge answered here", thread)
        # an answered comment is not flagged "responds next beat"; an open one is
        self.client.post("/e/alpha-post/comment", data={"body": "still open"})
        thread = self.server._render_thread("alpha-post")
        self.assertIn("responde no próximo beat", thread)

    def test_general_comment_has_null_target_and_shows_in_chat(self):
        r = self.client.post("/chat/comment", data={"body": "a general directive"})
        self.assertEqual(r.status_code, 200)
        comments = self._events("voz.comment")
        self.assertEqual(len(comments), 1)
        self.assertIsNone(comments[0]["payload"]["target_ref"])
        self.assertIn("a general directive", r.data.decode())

    def test_chat_is_unfiltered_timeline_labelled_by_target(self):
        self.client.post("/e/alpha-post/comment", data={"body": "targeted at alpha"})
        self.client.post("/chat/comment", data={"body": "general one"})
        body = self.client.get("/chat").data.decode()
        self.assertEqual(self.client.get("/chat").status_code, 200)
        # both the targeted and the general comment appear in one timeline
        self.assertIn("targeted at alpha", body)
        self.assertIn("general one", body)
        # the targeted item is labelled with its post context
        self.assertIn("alpha-post", body)

    def test_chat_empty_state(self):
        body = self.client.get("/chat").data.decode()
        self.assertIn("sem mensagens", body)

    def test_index_renders_voz_rail_under_each_post(self):
        # seed one comment so the thread is non-empty
        self.client.post("/e/alpha-post/comment", data={"body": "rail comment"})
        body = self.client.get("/").data.decode()
        # vote control + comment composer wired to the per-slug endpoints
        self.assertIn('hx-post="/e/alpha-post/vote"', body)
        self.assertIn('hx-post="/e/alpha-post/comment"', body)
        # the seeded comment renders in the thread under the post
        self.assertIn("rail comment", body)
        # htmx is loaded so the fragment swaps work — self-hosted (Slice 7 #37: no CDN supply chain)
        self.assertIn("htmx", body)
        self.assertIn("/static/vendor/htmx.min.js", body)
        self.assertNotIn("unpkg.com", body)
        # a link to the standalone chat exists
        self.assertIn('href="/chat"', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
