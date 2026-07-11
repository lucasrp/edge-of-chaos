"""Provisionamento de skills globais do Grok.

Sucesso: edge-apply/_grok_provision escreve GROK_HOME/skills/{prefix}-{slug}/SKILL.md
para os dois prefixos declarados em agent.yaml: tool_prefix (edge) e skill_prefix (ed).
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _grok_provision as gp  # noqa: E402

CFG = {
    "name": "ed",
    "codename": "ed",
    "skill_prefix": "ed",
    "tool_prefix": "edge",
}


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class TestGrokProvision(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.edge_home = self.root / "edge"
        self.grok_home = self.root / ".grok"

    def tearDown(self):
        self._tmp.cleanup()

    def test_prefixes_come_from_agent_yaml(self):
        self.assertEqual(gp.grok_prefixes(CFG), ["edge", "ed"])

    def test_provisions_all_public_skills_for_both_prefixes(self):
        gp.provision_grok(CFG, REPO, self.edge_home, self.grok_home)
        for skill_dir in sorted((REPO / "skills").iterdir()):
            if skill_dir.name == "_shared" or not (skill_dir / "SKILL.md").exists():
                continue
            for prefix in ("edge", "ed"):
                dst = self.grok_home / "skills" / f"{prefix}-{skill_dir.name}" / "SKILL.md"
                self.assertTrue(dst.exists(), f"missing {dst}")
                text = dst.read_text()
                self.assertIn(f"name: {prefix}-{skill_dir.name}", text)
                self.assertIn(f"@{prefix}-{skill_dir.name}", text)
                self.assertIn(str(self.edge_home / "skills" / skill_dir.name / "SKILL.md"), text)
                self.assertNotIn(f"/{prefix}-{skill_dir.name}", text)

    def test_shared_skill_is_not_global_invocable(self):
        gp.provision_grok(CFG, REPO, self.edge_home, self.grok_home)
        self.assertFalse((self.grok_home / "skills" / "edge-_shared").exists())
        self.assertFalse((self.grok_home / "skills" / "ed-_shared").exists())

    def test_idempotent_byte_identical(self):
        gp.provision_grok(CFG, REPO, self.edge_home, self.grok_home)
        first = _snapshot(self.grok_home)
        gp.provision_grok(CFG, REPO, self.edge_home, self.grok_home)
        second = _snapshot(self.grok_home)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
