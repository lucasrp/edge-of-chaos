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

    def test_ovo_is_found_through_real_resolution_when_home_is_not_the_repo(self):
        """The regression: the two tests above inject agent_yaml= and so never exercise
        identity_path(), which is where the ovo was actually being lost. In the documented
        geno/home-separated layout, pre-phenotype identity_path() falls back to REPO (it only
        honours EDGE_HOME when agent.yaml is ALREADY there) while the ovo lives in the HOME —
        so the fallback was unreachable exactly when it is the only identity there is, and no
        separated-home install could ever reach the mentor that emits the phenotype."""
        if (_identity.REPO / "agent.yaml").exists():
            self.skipTest("this tree is itself a home==repo install; resolution case N/A")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "state").mkdir()
            (home / "state" / "bootstrap.json").write_text(
                json.dumps({"name": "regressao", "edge_home": str(home)}))
            old_home = os.environ.get("EDGE_HOME")
            old_group = os.environ.pop("EDGE_GROUP", None)
            os.environ["EDGE_HOME"] = str(home)
            try:
                resolved = _identity.identity_path("agent.yaml")
                self.assertEqual(resolved, _identity.REPO / "agent.yaml",
                                 "pre-phenotype identity_path must fall back to the genotype")
                self.assertEqual(_identity.group(agent_yaml=resolved), "regressao")
                self.assertEqual(_identity.edge_home(agent_yaml=resolved), home)
            finally:
                if old_home is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old_home
                if old_group is not None:
                    os.environ["EDGE_GROUP"] = old_group

    def test_explicit_path_wins_over_edge_home(self):
        """The HOME leg must never override a tree a caller named outright."""
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            named, home = Path(tmp), Path(other)
            for root, name in ((named, "nomeado"), (home, "do-home")):
                (root / "state").mkdir()
                (root / "state" / "bootstrap.json").write_text(json.dumps({"name": name}))
            old_home = os.environ.get("EDGE_HOME")
            old_group = os.environ.pop("EDGE_GROUP", None)
            os.environ["EDGE_HOME"] = str(home)
            try:
                self.assertEqual(_identity.group(agent_yaml=named / "agent.yaml"), "nomeado")
            finally:
                if old_home is None:
                    os.environ.pop("EDGE_HOME", None)
                else:
                    os.environ["EDGE_HOME"] = old_home
                if old_group is not None:
                    os.environ["EDGE_GROUP"] = old_group


if __name__ == "__main__":
    unittest.main()
