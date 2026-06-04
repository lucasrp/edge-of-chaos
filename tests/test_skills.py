"""Skills dispatch — logic lives in skills, the runtime loads + renders them."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import _pipeline  # noqa: E402


class TestSkills(unittest.TestCase):
    def test_load_skill_strips_frontmatter(self):
        # repo skills exist (research/report/quality); body has no frontmatter delimiters
        body = _pipeline.load_skill("/nonexistent-home", "research")
        self.assertNotIn("name:", body.split("\n")[0])
        self.assertIn("Research", body)

    def test_home_skill_wins_over_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "skills" / "research").mkdir(parents=True)
            (home / "skills" / "research" / "SKILL.md").write_text("---\nname: research\n---\nHOME OVERRIDE {title}")
            body = _pipeline.load_skill(home, "research")
            self.assertIn("HOME OVERRIDE", body)

    def test_render_substitutes(self):
        out = _pipeline.render("about: {title} / {intent}", title="X", intent="Y")
        self.assertEqual(out, "about: X / Y")

    def test_missing_skill_raises(self):
        with self.assertRaises(FileNotFoundError):
            _pipeline.load_skill("/nonexistent-home", "does-not-exist")


if __name__ == "__main__":
    unittest.main(verbosity=2)
