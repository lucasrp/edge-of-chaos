"""Codex repo-local skill wrappers.

The Edge skill contract stays canonical under skills/<slug>/SKILL.md. Codex discovers
repo-local skills from .agents/skills, so every user-facing Edge skill gets small prefixed
wrappers that point back to the canonical file instead of duplicating it. These are Codex
skills selected with @ / /skills, not slash commands.

Prefix: `.agents/skills/` is REPO-LOCAL, versioned genotype content — it ships with the
checkout, unlike CODEX_HOME/skills which `_codex_provision` renders per install from the
phenotype's tool_prefix/skill_prefix. So the prefix this file checks is the **stable family
alias** `edge-*` (`_grok_provision.grok_prefixes`: "tool_prefix keeps the stable family alias
(edge-*)"), not whatever the person running the suite happens to have in their agent.yaml.
Before, both prefixes were read from `REPO/agent.yaml` with an `or "edge"` genotype fallback —
but the read was `.read_text()`, which RAISES on the genotype (no agent.yaml by contract)
instead of falling back, so both tests here errored at that line and the coverage check they
exist for never ran on any clean checkout.
"""
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parent.parent

# The stable family alias every versioned repo-local wrapper carries (install-specific aliases
# like ed-*/roberto-* are rendered per host by _codex_provision, not required of the checkout).
PREFIXES = ("edge",)


class CodexSkillWrappers(unittest.TestCase):
    def test_every_edge_skill_has_prefixed_codex_wrappers(self):
        prefixes = PREFIXES

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
        for prefix in PREFIXES:
            self.assertFalse((REPO / ".agents" / "skills" / f"{prefix}-_shared").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
