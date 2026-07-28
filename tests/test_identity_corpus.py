"""Corpus é do PROJETO; agente é da PESSOA×projeto. agent.yaml `corpus:` declares which KB this
install inhabits ({group, uri, role: host|member, film.stores}); every field defaults to the
degenerate single-agent case — private corpus named after the install, local bolt, host role,
film = the whole-life store — so existing installs never notice the model exists.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity  # noqa: E402

_ENV = ("EDGE_GROUP", "EDGE_AGENT", "EDGE_NEO4J_URI")


def _clean_env():
    saved = {k: os.environ.pop(k, None) for k in _ENV}
    return saved


def _restore_env(saved):
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v


class DegenerateDefaults(unittest.TestCase):
    def test_no_corpus_block_collapses_to_today(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text(f"name: t\nedge_home: {tmp}\n")
            saved = _clean_env()
            try:
                c = _identity.corpus(agent_yaml=ay)
                self.assertEqual(c["group"], "t")
                self.assertEqual(c["uri"], "bolt://localhost:7687")
                self.assertEqual(c["role"], "host")
                self.assertEqual(_identity.agent_id(agent_yaml=ay), "t")
            finally:
                _restore_env(saved)


class DeclaredCorpus(unittest.TestCase):
    def test_shared_corpus_group_uri_role_and_film(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text(
                f"name: gtm\nedge_home: {tmp}\n"
                "corpus:\n"
                "  group: edge-of-chaos\n"
                "  uri: bolt://10.0.0.5:7687\n"
                "  role: member\n"
                "  film:\n"
                "    stores:\n"
                "      - ~/proj-a-store\n")
            saved = _clean_env()
            try:
                c = _identity.corpus(agent_yaml=ay)
                self.assertEqual(c["role"], "member")
                # corpus group is the tenancy key the whole runtime reads
                self.assertEqual(_identity.group(agent_yaml=ay), "edge-of-chaos")
                # but the agent keeps its OWN identity (regime key) inside the shared corpus
                self.assertEqual(_identity.agent_id(agent_yaml=ay), "gtm")
                # bolt connection reaches the corpus host, not localhost
                uri, _u, _p = _identity.neo4j_conn(agent_yaml=ay)
                self.assertEqual(uri, "bolt://10.0.0.5:7687")
                stores = _identity.film_stores(agent_yaml=ay)
                self.assertEqual(stores, [Path("~/proj-a-store").expanduser()])
            finally:
                _restore_env(saved)


if __name__ == "__main__":
    unittest.main()
