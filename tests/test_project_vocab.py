"""wiki_render — the cluster synthesis must frame in the projects' own vocabulary (their CONTEXT.md),
not only the Idiom. These pin the vocabulary gatherer: collect the available CONTEXT.md glossaries
across the mentee's native projects, deduped (clone worktrees share a CONTEXT.md)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import wiki_render


class ProjectVocabGathersContextMd(unittest.TestCase):
    def _mk(self, root, name, text):
        (root / name).mkdir(parents=True)
        (root / name / "CONTEXT.md").write_text(text)

    def test_gathers_and_dedups_context_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._mk(root, "alpha", "Alpha glossary: Foo means bar.")
            self._mk(root, "beta", "Beta glossary: Baz means qux.")
            self._mk(root, "beta-clone", "Beta glossary: Baz means qux.")  # worktree dup
            v = wiki_render.project_vocab(root=root)
            self.assertIn("Alpha glossary", v)
            self.assertIn("Beta glossary", v)
            self.assertEqual(v.count("Baz means qux"), 1)  # deduped


if __name__ == "__main__":
    unittest.main(verbosity=2)
