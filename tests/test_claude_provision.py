"""Provisionamento de ~/.claude (issue #10).

TDD: define o sucesso da fase ~/.claude do edge-apply.
Sucesso:
  - cada skills/{name}/SKILL.md → ~/.claude/skills/{prefix}-{name}/SKILL.md
    com frontmatter (name: {prefix}-{name}, description, user-invocable: true)
    e {prefix} substituído no corpo;
  - CLAUDE.md renderizado contém name/codename/mission do agent.yaml;
  - rodar duas vezes é byte-idêntico (idempotente).

NUNCA escreve no ~/.claude real: claude_home aponta sempre para um tmp.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _claude_provision as cp  # noqa: E402

CFG = {
    "name": "ed",
    "codename": "ed",
    "language": "en",
    "mission": "Mentor to the edge-of-chaos PM.",
    "voice": "Direct, technical, skeptical.",
    "skill_prefix": "ed",
    "heartbeat_interval": "3h",
}


class TestRenderSkill(unittest.TestCase):
    def test_frontmatter_and_prefix_substitution(self):
        src = (
            "---\n"
            "name: beat\n"
            "description: The beat loop.\n"
            "---\n"
            "Invoked as /{prefix}-beat. See /{prefix}-report.\n"
        )
        out = cp.render_skill(src, name="beat", prefix="ed")
        # frontmatter: name fica prefixado
        self.assertIn("name: ed-beat", out)
        # descrição preservada
        self.assertIn("description: The beat loop.", out)
        # user-invocable adicionado dentro do frontmatter (antes do fechamento)
        self.assertIn("user-invocable: true", out)
        idx_ui = out.index("user-invocable: true")
        idx_close = out.index("\n---\n")
        self.assertLess(idx_ui, idx_close, "user-invocable deve estar dentro do frontmatter")
        # corpo: {prefix} substituído
        self.assertIn("/ed-beat", out)
        self.assertIn("/ed-report", out)
        self.assertNotIn("{prefix}", out)


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestProvisionClaudeHome(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.claude_home = Path(self._tmp.name) / ".claude"

    def tearDown(self):
        self._tmp.cleanup()

    def test_provisions_claude_md_and_skills(self):
        cp.provision_claude(CFG, REPO, self.claude_home)
        # CLAUDE.md written
        claude_md = self.claude_home / "CLAUDE.md"
        self.assertTrue(claude_md.exists())
        self.assertIn("Mentor to the edge-of-chaos PM.", claude_md.read_text())
        # every repo skill rendered to {prefix}-{name}/SKILL.md
        for skill_dir in sorted((REPO / "skills").iterdir()):
            if not (skill_dir / "SKILL.md").exists():
                continue
            dst = self.claude_home / "skills" / f"ed-{skill_dir.name}" / "SKILL.md"
            self.assertTrue(dst.exists(), f"missing {dst}")
            rendered = dst.read_text()
            self.assertIn(f"name: ed-{skill_dir.name}", rendered)
            self.assertIn("user-invocable: true", rendered)
            self.assertNotIn("{prefix}", rendered)

    def test_provisions_shared_skill_support_files_unprefixed(self):
        cp.provision_claude(CFG, REPO, self.claude_home)
        shared = self.claude_home / "skills" / "_shared"
        self.assertTrue(shared.is_dir())
        self.assertEqual(
            (REPO / "skills" / "_shared" / "scaffold.md").read_text(encoding="utf-8"),
            (shared / "scaffold.md").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8"),
            (shared / "pipeline.md").read_text(encoding="utf-8"),
        )
        self.assertFalse((self.claude_home / "skills" / "ed-_shared").exists())

    def test_idempotent_byte_identical(self):
        cp.provision_claude(CFG, REPO, self.claude_home)
        first = _snapshot(self.claude_home)
        cp.provision_claude(CFG, REPO, self.claude_home)
        second = _snapshot(self.claude_home)
        self.assertEqual(first, second, "second run must be byte-identical (no drift/dupes)")
        # no prefix-of-prefix drift
        for rel in second:
            self.assertNotIn("ed-ed-", rel, f"double-prefixed path: {rel}")

    def test_seeds_memory_only_if_absent(self):
        cp.provision_claude(CFG, REPO, self.claude_home)
        mem_dir = self.claude_home / "projects" / cp.memory_project_dir(CFG) / "memory"
        self.assertTrue(mem_dir.is_dir(), "memory dir seeded")
        marker = mem_dir / "MEMORY.md"
        marker.write_text("# my custom memory\n")
        cp.provision_claude(CFG, REPO, self.claude_home)
        self.assertEqual(marker.read_text(), "# my custom memory\n",
                         "existing memory must not be overwritten")


class TestRenderClaudeMd(unittest.TestCase):
    def test_contains_identity_fields(self):
        out = cp.render_claude_md(CFG)
        self.assertIn("ed", out)                       # name/codename
        self.assertIn("Mentor to the edge-of-chaos PM.", out)   # mission
        # codename surfaced explicitly
        self.assertIn("Codename", out)
        # mission section present
        self.assertIn("Mission", out)

    def test_voice_and_memory_linkage(self):
        out = cp.render_claude_md(CFG)
        self.assertIn("Direct, technical, skeptical.", out)     # voice
        self.assertIn("memory/", out)                          # memory linkage

    def test_no_unrendered_placeholders(self):
        out = cp.render_claude_md(CFG)
        self.assertNotIn("{{", out)
        self.assertNotIn("}}", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
