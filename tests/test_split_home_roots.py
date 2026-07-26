"""Geno/home split (EDGE_HOME): llm_routes e publisher resolvem config/fenótipo no HOME.

Finding do sandbox 2026-07-25 (state/findings/2026-07-25-llm_routes-edge-home-split.md):
llm_routes.REPO assumia home==repo — num split, shortlist/propose/close morriam em
FileNotFoundError no agent.yaml do genótipo. BLOG_DIR idem: o artefato do turing pousou
no clone genótipo em vez do home. Constantes bindam no import ⇒ testes via subprocess.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(code, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True,
        env=env, cwd=str(REPO))


class SplitHomeConfigRoots(unittest.TestCase):
    def test_llm_routes_repo_follows_edge_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent.yaml").write_text("name: split\nedge_home: " + tmp + "\n")
            r = _run(
                "import sys; sys.path.insert(0, 'tools'); import llm_routes; print(llm_routes.REPO)",
                {"EDGE_HOME": tmp})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), tmp)

    def test_llm_routes_repo_stays_genotype_without_edge_home(self):
        r = _run(
            "import sys; sys.path.insert(0, 'tools'); import llm_routes; print(llm_routes.REPO)",
            {"EDGE_HOME": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(REPO))

    def test_publisher_blog_dir_follows_state_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent.yaml").write_text("name: split\nedge_home: " + tmp + "\n")
            r = _run(
                "import sys; sys.path.insert(0, 'tools'); import publisher; print(publisher.BLOG_DIR)",
                {"EDGE_HOME": tmp})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), str(Path(tmp) / "blog" / "entries"))


if __name__ == "__main__":
    unittest.main()
