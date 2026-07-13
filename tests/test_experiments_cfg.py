"""Genotype experiments/ workspace — path resolution + seed stubs."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import experiments_cfg  # noqa: E402
import eventlog  # noqa: E402


class ExperimentsRoot(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "custom-exps"
            root.mkdir()
            with mock.patch.dict(os.environ, {"EDGE_EXPERIMENTS_DIR": str(root)}):
                self.assertEqual(experiments_cfg.experiments_root(), root.resolve())

    def test_default_under_edge_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            home.mkdir()
            yaml = Path(tmp) / "agent.yaml"
            yaml.write_text(
                "edge_home: " + str(home) + "\n"
                "name: test\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("EDGE_EXPERIMENTS_DIR", None)
                got = experiments_cfg.experiments_root(agent_yaml=yaml)
            self.assertEqual(got, (home / "experiments").resolve())

    def test_phenotype_relative_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "edge"
            home.mkdir()
            yaml = Path(tmp) / "agent.yaml"
            yaml.write_text(
                f"edge_home: {home}\n"
                "name: test\n"
                "experiments:\n"
                "  root: writing\n",
                encoding="utf-8",
            )
            os.environ.pop("EDGE_EXPERIMENTS_DIR", None)
            got = experiments_cfg.experiments_root(agent_yaml=yaml)
            self.assertEqual(got, (home / "writing").resolve())


class ExperimentWorkspace(unittest.TestCase):
    def test_ensure_seeds_projeto_and_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "experiments"
            with mock.patch.dict(os.environ, {"EDGE_EXPERIMENTS_DIR": str(root)}):
                path = experiments_cfg.ensure_experiment_workspace(
                    "exp001",
                    title="Activation and churn",
                    hypothesis="Early activation cuts 90-day churn.",
                )
                self.assertTrue(path.is_dir())
                self.assertTrue((path / "projeto.md").is_file())
                self.assertTrue((path / "timeline.md").is_file())
                self.assertTrue((path / "arms").is_dir())
                self.assertIn("exp001", path.name)
                self.assertIn("activation", path.name)
                body = (path / "projeto.md").read_text(encoding="utf-8")
                self.assertIn("exp001", body)
                self.assertIn("Early activation", body)

    def test_reuse_existing_prefix_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "experiments"
            existing = root / "exp002-old-slug"
            existing.mkdir(parents=True)
            (existing / "projeto.md").write_text("# keep\n", encoding="utf-8")
            with mock.patch.dict(os.environ, {"EDGE_EXPERIMENTS_DIR": str(root)}):
                path = experiments_cfg.experiment_dir("exp002", title="New Title", create=True)
            self.assertEqual(path, existing)
            self.assertEqual((existing / "projeto.md").read_text(encoding="utf-8"), "# keep\n")

    def test_slugify(self):
        self.assertEqual(experiments_cfg.slugify_title("Hello, World!"), "hello-world")
        self.assertEqual(experiments_cfg.slugify_title(""), "untitled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
