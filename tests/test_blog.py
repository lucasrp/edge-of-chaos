"""Blog v0 — smoke: index lista os artefatos e serve o .html."""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


class TestBlog(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        entries = Path(self.tmp.name) / "entries"
        entries.mkdir()
        (entries / "foo-bar.html").write_text("<html><body><h1>Foo Bar</h1></body></html>")
        os.environ["EDGE_BLOG_ENTRIES"] = str(entries)
        os.environ["EDGE_BLOG_STATIC"] = str(Path(self.tmp.name))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blog"))
        import server
        importlib.reload(server)
        self.client = server.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_lists_entry(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"foo-bar", r.data)

    def test_entry_served(self):
        r = self.client.get("/e/foo-bar.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Foo Bar", r.data)

    def test_missing_entry_404(self):
        self.assertEqual(self.client.get("/e/nope.html").status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
