"""Secrets reach the runtime env, and the graph group is resolvable explicitly.

The install writes secrets/*.env; nothing loaded them into os.environ, so the graph went dark with
EDGE_NEO4J_PASSWORD sitting on disk. _secrets.load_env sources them (env already set wins). And
_identity resolves an explicit `graph_group` before name/codename, so a mentor named 'ed' can own a
corpus in the 'edge-next' group without orphaning it; neo4j_password falls back to the install's
secret file when the env is unset.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _secrets   # noqa: E402
import _identity  # noqa: E402


class LoadEnv(unittest.TestCase):
    KEYS = ("EDGE_NEO4J_PASSWORD", "FOO_X", "BAZ_X")

    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in self.KEYS}

    def tearDown(self):
        for k in self.KEYS:
            os.environ.pop(k, None)
            if self._saved.get(k) is not None:
                os.environ[k] = self._saved[k]

    def test_loads_without_clobbering_existing(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=pw123\n")
            (Path(d) / "x.env").write_text('export FOO_X="bar"\n# comment\nBAZ_X=qux\n')
            os.environ["FOO_X"] = "preset"
            loaded = _secrets.load_env(d)
            self.assertEqual(os.environ["EDGE_NEO4J_PASSWORD"], "pw123")
            self.assertEqual(os.environ["BAZ_X"], "qux")
            self.assertEqual(os.environ["FOO_X"], "preset")        # env already set wins
            self.assertIn("EDGE_NEO4J_PASSWORD", loaded)

    def test_missing_dir_is_noop(self):
        self.assertEqual(_secrets.load_env("/no/such/dir/xyz"), [])


class IdentityGroup(unittest.TestCase):
    def setUp(self):
        self._grp = os.environ.pop("EDGE_GROUP", None)

    def tearDown(self):
        if self._grp is not None:
            os.environ["EDGE_GROUP"] = self._grp

    def _yaml(self, d, body):
        p = Path(d) / "agent.yaml"
        p.write_text(body)
        return p

    def test_graph_group_beats_name(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._yaml(d, "name: ed\ncodename: ed\ngraph_group: edge-next\n")
            self.assertEqual(_identity.group(agent_yaml=p), "edge-next")

    def test_falls_back_to_name_without_graph_group(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._yaml(d, "name: ed\n")
            self.assertEqual(_identity.group(agent_yaml=p), "ed")

    def test_env_group_wins(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._yaml(d, "graph_group: edge-next\n")
            os.environ["EDGE_GROUP"] = "override"
            self.assertEqual(_identity.group(agent_yaml=p), "override")


class Neo4jPasswordFallback(unittest.TestCase):
    def setUp(self):
        self._pw = os.environ.pop("EDGE_NEO4J_PASSWORD", None)

    def tearDown(self):
        if self._pw is not None:
            os.environ["EDGE_NEO4J_PASSWORD"] = self._pw

    def test_env_wins_over_file(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "secrets").mkdir()
            (Path(d) / "secrets" / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=fromfile\n")
            p = Path(d) / "agent.yaml"
            p.write_text(f'edge_home: "{d}"\n')
            os.environ["EDGE_NEO4J_PASSWORD"] = "fromenv"
            self.assertEqual(_identity.neo4j_password(agent_yaml=p), "fromenv")

    def test_reads_secret_file_when_env_unset(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "secrets").mkdir()
            (Path(d) / "secrets" / "neo4j.env").write_text("EDGE_NEO4J_PASSWORD=fromfile\n")
            p = Path(d) / "agent.yaml"
            p.write_text(f'edge_home: "{d}"\nname: ed\n')
            self.assertEqual(_identity.neo4j_password(agent_yaml=p), "fromfile")


if __name__ == "__main__":
    unittest.main(verbosity=2)
