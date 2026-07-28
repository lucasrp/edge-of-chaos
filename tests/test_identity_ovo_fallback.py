"""Pre-phenotype life runs from the ovo: agent.yaml is born at the mentor's finish and ONLY
there — before it exists, _identity resolves the mechanical facts (name/group, edge_home) from
state/bootstrap.json. Without this fallback the runtime pressures installers into creating
agent.yaml early, which is the doctrine violation (identity before the mentor conversation).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity  # noqa: E402


class IdentityFromOvo(unittest.TestCase):
    def test_group_resolves_from_bootstrap_json_when_agent_yaml_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "state" / "bootstrap.json").write_text(
                json.dumps({"name": "t", "edge_home": str(root)}))
            old = os.environ.pop("EDGE_GROUP", None)
            try:
                self.assertEqual(_identity.group(agent_yaml=root / "agent.yaml"), "t")
            finally:
                if old is not None:
                    os.environ["EDGE_GROUP"] = old

    def test_agent_yaml_still_wins_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            (root / "state" / "bootstrap.json").write_text(json.dumps({"name": "ovo"}))
            (root / "agent.yaml").write_text("name: fenotipo\n")
            old = os.environ.pop("EDGE_GROUP", None)
            try:
                self.assertEqual(_identity.group(agent_yaml=root / "agent.yaml"), "fenotipo")
            finally:
                if old is not None:
                    os.environ["EDGE_GROUP"] = old


if __name__ == "__main__":
    unittest.main()
