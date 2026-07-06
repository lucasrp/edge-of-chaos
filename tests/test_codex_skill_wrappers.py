"""Codex repo-local skill wrappers.

The Edge skill contract stays canonical under skills/<slug>/SKILL.md. Codex discovers
repo-local skills from .agents/skills, so every user-facing Edge skill gets small prefixed
wrappers that point back to the canonical file instead of duplicating it. These are Codex
skills selected with @ / /skills, not slash commands.
"""
from pathlib import Path
import re
import unittest

REPO = Path(__file__).resolve().parent.parent


def _agent_yaml_value(key: str) -> str:
    text = (REPO / "agent.yaml").read_text()
    match = re.search(rf"(?m)^\s*{re.escape(key)}:\s*[\"']?([^\"'\n#]+)", text)
    if not match:
        return ""
    return match.group(1).strip()


class CodexSkillWrappers(unittest.TestCase):
    def test_every_edge_skill_has_prefixed_codex_wrappers(self):
        prefixes = {
            _agent_yaml_value("tool_prefix") or "edge",
            _agent_yaml_value("skill_prefix") or _agent_yaml_value("codename") or "edge",
        }

        missing = []
        for skill_file in sorted((REPO / "skills").glob("*/SKILL.md")):
            slug = skill_file.parent.name
            if slug == "_shared":
                continue
            for prefix in sorted(prefixes):
                wrapper = REPO / ".agents" / "skills" / f"{prefix}-{slug}" / "SKILL.md"
                if not wrapper.exists():
                    missing.append(str(wrapper.relative_to(REPO)))
                    continue
                text = wrapper.read_text()
                self.assertIn(f"name: {prefix}-{slug}", text)
                self.assertIn(f"skills/{slug}/SKILL.md", text)
                self.assertIn(f"@{prefix}-{slug}", text)
                self.assertNotIn(f"/{prefix}-{slug}", text)
                self.assertNotIn("Use when invoking /", text)
        self.assertEqual(missing, [])

    def test_shared_skill_is_not_invocable_in_codex(self):
        prefixes = {
            _agent_yaml_value("tool_prefix") or "edge",
            _agent_yaml_value("skill_prefix") or _agent_yaml_value("codename") or "edge",
        }
        for prefix in prefixes:
            self.assertFalse((REPO / ".agents" / "skills" / f"{prefix}-_shared").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
