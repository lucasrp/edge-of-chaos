"""Integração: edge-apply provisiona ~/.claude além de ~/edge (issue #10).

Sucesso: `edge-apply --yaml agent.yaml --home <tmp_edge> --claude-home <tmp_claude>`
  - mantém o contrato existente (~/edge: layout, Caddyfile, server.py);
  - escreve ~/.claude/CLAUDE.md e ~/.claude/skills/{prefix}-*/SKILL.md;
  - é idempotente (segunda rodada byte-idêntica no ~/.claude).

SEGURANÇA: --claude-home/--codex-home apontam SEMPRE para tmp. Nunca toca homes reais.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parent.parent
APPLY = REPO / "tools" / "edge-apply"
YAML = REPO / "agent.yaml"


def load_cfg() -> dict:
    return yaml.safe_load(YAML.read_text(encoding="utf-8"))


def run_apply(edge_home: Path, claude_home: Path, codex_home: Path):
    return subprocess.run(
        [sys.executable, str(APPLY), "--yaml", str(YAML),
         "--home", str(edge_home), "--claude-home", str(claude_home),
         "--codex-home", str(codex_home)],
        capture_output=True, text=True,
    )


def snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


class ApplyClaude(unittest.TestCase):
    def setUp(self):
        self._t1 = tempfile.TemporaryDirectory()
        self._t2 = tempfile.TemporaryDirectory()
        self.edge_home = Path(self._t1.name)
        self.claude_home = Path(self._t2.name) / ".claude"
        self.codex_home = Path(self._t2.name) / ".codex"
        self.cfg = load_cfg()
        self.res = run_apply(self.edge_home, self.claude_home, self.codex_home)

    def tearDown(self):
        self._t1.cleanup()
        self._t2.cleanup()

    def test_apply_succeeds(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)

    def test_edge_contract_preserved(self):
        # ~/edge ainda é provisionado (não quebramos o contrato existente)
        self.assertTrue((self.edge_home / "Caddyfile").exists())
        self.assertTrue((self.edge_home / "blog" / "server.py").exists())
        self.assertTrue((self.edge_home / "state").is_dir())

    def test_claude_md_written(self):
        claude_md = self.claude_home / "CLAUDE.md"
        self.assertTrue(claude_md.exists(), self.res.stdout + self.res.stderr)
        # mission from the real agent.yaml is rendered into CLAUDE.md
        mission = str(self.cfg.get("mission", "")).strip().splitlines()[0]
        self.assertIn(mission, claude_md.read_text())

    def test_skills_rendered_prefixed(self):
        prefix = str(self.cfg.get("skill_prefix", self.cfg.get("codename", "")))
        beat = self.claude_home / "skills" / f"{prefix}-beat" / "SKILL.md"
        self.assertTrue(beat.exists())
        self.assertIn(f"name: {prefix}-beat", beat.read_text())
        self.assertIn("user-invocable: true", beat.read_text())

    def test_idempotent(self):
        first = snapshot(self.claude_home)
        run_apply(self.edge_home, self.claude_home, self.codex_home)
        second = snapshot(self.claude_home)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
