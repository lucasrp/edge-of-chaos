"""Fase 0 — instalar a partir do yaml. TDD: este teste define o sucesso do apply.

Sucesso: `edge-apply --yaml agent.yaml --home <tmp>` produz um layout instalado,
semeado (threads das initial_threads), com Caddyfile pro domínio, server.py no lugar,
e um relatório do que falta (credenciais).
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPLY = REPO / "tools" / "edge-apply"
YAML = REPO / "agent.yaml"


def run_apply(home: Path):
    return subprocess.run(
        [sys.executable, str(APPLY), "--yaml", str(YAML), "--home", str(home)],
        capture_output=True, text=True,
    )


class Fase0(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.res = run_apply(self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def test_apply_succeeds(self):
        self.assertEqual(self.res.returncode, 0, self.res.stderr)

    def test_layout_dirs(self):
        for d in ("blog/entries", "state", "memory", "threads"):
            self.assertTrue((self.home / d).is_dir(), f"falta dir {d}")

    def test_threads_seeded(self):
        t = self.home / "threads"
        files = list(t.glob("*.md"))
        self.assertEqual(len(files), 2, "deve semear 2 threads das initial_threads")
        baseline = t / "baseline-do-runtime-atual.md"
        self.assertTrue(baseline.exists(), "thread baseline pelo slug do título")
        txt = baseline.read_text()
        self.assertIn("status: active", txt)
        self.assertIn("Baseline do runtime atual", txt)

    def test_caddyfile_domain(self):
        caddy = self.home / "Caddyfile"
        self.assertTrue(caddy.exists(), "Caddyfile renderizado")
        txt = caddy.read_text()
        self.assertIn("edge.edgeofchaos.net", txt)
        self.assertIn("reverse_proxy", txt)
        self.assertIn("8766", txt)

    def test_blog_server_placed(self):
        self.assertTrue((self.home / "blog" / "server.py").exists())

    def test_reports_missing_credentials(self):
        # sem keys no tmp → o apply deve relatar o que falta (substrate-check)
        out = self.res.stdout
        self.assertIn("openai", out.lower())
        self.assertRegex(out.lower(), r"falta|missing|ausente|não encontrado|nao encontrado")


if __name__ == "__main__":
    unittest.main(verbosity=2)
