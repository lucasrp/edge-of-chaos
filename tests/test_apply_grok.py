"""Integração: edge-apply provisiona skills globais do Grok."""
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
from _grok_provision import grok_prefixes  # noqa: E402


def run_apply(edge_home: Path, claude_home: Path, codex_home: Path, grok_home: Path):
    return subprocess.run(
        [
            sys.executable, str(APPLY),
            "--yaml", str(YAML),
            "--home", str(edge_home),
            "--claude-home", str(claude_home),
            "--codex-home", str(codex_home),
            "--grok-home", str(grok_home),
        ],
        capture_output=True, text=True,
    )


class ApplyGrok(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.edge_home = root / "edge"
        self.claude_home = root / ".claude"
        self.codex_home = root / ".codex"
        self.grok_home = root / ".grok"
        self.res = run_apply(self.edge_home, self.claude_home, self.codex_home, self.grok_home)

    def tearDown(self):
        self._tmp.cleanup()

    def test_apply_succeeds(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)

    def test_grok_skills_installed_with_tool_and_skill_prefixes(self):
        cfg = yaml.safe_load(YAML.read_text()) or {}
        for prefix in grok_prefixes(cfg):
            name = f"{prefix}-wake"
            skill = self.grok_home / "skills" / name / "SKILL.md"
            self.assertTrue(skill.exists(), f"missing {skill}")
            text = skill.read_text()
            self.assertIn(f"name: {name}", text)
            self.assertIn(f"@{name}", text)
            self.assertIn(str(self.edge_home / "skills" / "wake" / "SKILL.md"), text)
            # O Grok invoca skill por SLASH — ao contrário do Codex, que é @ (palavra do
            # operador, 2026-08-16). Este assertNotIn exigia o contrário do produto.
            self.assertIn(f"/{name}", text)

    def test_stdout_reports_grok_home(self):
        self.assertIn("provisionando Grok skills", self.res.stdout)
        self.assertIn(str(self.grok_home), self.res.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
