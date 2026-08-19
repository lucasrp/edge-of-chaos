"""Integração: edge-apply provisiona skills globais do Codex."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
APPLY = REPO / "tools" / "edge-apply"
# O fenotipo NAO existe no genotipo (contrato: agent.yaml e output do onboarding, e
# gitignored). Apontar para REPO/agent.yaml fazia estes testes falharem por construcao com
# FileNotFoundError — sobre o edge-apply, nada. A fixture versionada e um agent.yaml completo
# e igual em qualquer host.
YAML = REPO / "tests" / "fixtures" / "roster.agent.yaml"
sys.path.insert(0, str(REPO / "tools"))
from _codex_provision import codex_prefixes  # noqa: E402


def run_apply(edge_home: Path, claude_home: Path, codex_home: Path):
    return subprocess.run(
        [
            sys.executable, str(APPLY),
            "--yaml", str(YAML),
            "--home", str(edge_home),
            "--claude-home", str(claude_home),
            "--codex-home", str(codex_home),
        ],
        capture_output=True, text=True,
    )


class ApplyCodex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.edge_home = root / "edge"
        self.claude_home = root / ".claude"
        self.codex_home = root / ".codex"
        self.res = run_apply(self.edge_home, self.claude_home, self.codex_home)

    def tearDown(self):
        self._tmp.cleanup()

    def test_apply_succeeds(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)

    def test_codex_skills_installed_with_tool_and_skill_prefixes(self):
        cfg = yaml.safe_load(YAML.read_text()) or {}
        for prefix in codex_prefixes(cfg):
            name = f"{prefix}-wake"
            skill = self.codex_home / "skills" / name / "SKILL.md"
            self.assertTrue(skill.exists(), f"missing {skill}")
            text = skill.read_text()
            self.assertIn(f"name: {name}", text)
            self.assertIn(f"@{name}", text)
            self.assertIn(str(self.edge_home / "skills" / "wake" / "SKILL.md"), text)
            self.assertNotIn(f"/{name}", text)

    def test_stdout_reports_codex_home(self):
        self.assertIn("provisionando Codex skills", self.res.stdout)
        self.assertIn(str(self.codex_home), self.res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
