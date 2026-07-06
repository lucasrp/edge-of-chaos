"""Codex repo-local skill wrappers.

The Edge skill contract stays canonical under skills/<slug>/SKILL.md. Codex discovers repo-local
skills from .agents/skills, so every user-facing Edge skill gets a small edge-* wrapper that points
back to the canonical file instead of duplicating it.
"""
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent


class CodexSkillWrappers(unittest.TestCase):
    def test_every_edge_skill_has_an_edge_prefixed_codex_wrapper(self):
        missing = []
        for skill_file in sorted((REPO / "skills").glob("*/SKILL.md")):
            slug = skill_file.parent.name
            if slug == "_shared":
                continue
            wrapper = REPO / ".agents" / "skills" / f"edge-{slug}" / "SKILL.md"
            if not wrapper.exists():
                missing.append(str(wrapper.relative_to(REPO)))
                continue
            text = wrapper.read_text()
            self.assertIn(f"name: edge-{slug}", text)
            self.assertIn(f"skills/{slug}/SKILL.md", text)
        self.assertEqual(missing, [])

    def test_shared_skill_is_not_invocable_in_codex(self):
        self.assertFalse((REPO / ".agents" / "skills" / "edge-_shared").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
