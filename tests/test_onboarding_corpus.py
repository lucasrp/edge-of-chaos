"""The corpus declaration reaches the phenotype at finish: an install joining an existing
project KB (modo avançado) emits agent.yaml with the `corpus:` block the runtime reads.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import onboarding  # noqa: E402


class EmitPersistsCorpus(unittest.TestCase):
    def test_emit_writes_corpus_block_into_agent_yaml(self):
        import yaml
        with tempfile.TemporaryDirectory() as tmp:
            onboarding.run_bootstrap(home=tmp, name="gtm", backfill_days=3,
                                     provision_skills=False)
            path = onboarding.emit_phenotype(tmp, corpus={
                "group": "edge-of-chaos", "uri": "bolt://10.0.0.5:7687", "role": "member"})
            cfg = yaml.safe_load(Path(path).read_text())
            self.assertEqual(cfg["corpus"]["group"], "edge-of-chaos")
            self.assertEqual(cfg["corpus"]["role"], "member")


if __name__ == "__main__":
    unittest.main()
