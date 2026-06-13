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
        # blurb from the intent kernel
        self.assertIn("resolved beta", body)
        # links to the artifacts the post created
        self.assertIn("cluster:foo", body)
        self.assertIn("do the X thing", body)
        self.assertIn("source:arxiv:2606.06448", body)

    def test_index_newest_first(self):
        body = self.client.get("/").data.decode()
        self.assertLess(body.index("beta-post"), body.index("alpha-post"))

    def test_entry_served(self):
        r = self.client.get("/e/beta-post.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"beta-post", r.data)

    def test_missing_entry_404(self):
        self.assertEqual(self.client.get("/e/nope.html").status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
