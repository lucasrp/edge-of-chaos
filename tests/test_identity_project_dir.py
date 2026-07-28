"""project_dir resolves the mentee's transcript store: EDGE_PROJECT_DIR env → agent.yaml
`project_dir` → the $HOME convention. The agent.yaml field lets a WSL install point at the Windows
store (/mnt/c/Users/<user>/.claude/projects) durably, without env plumbing into the runtime.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity  # noqa: E402


class ProjectDirFromAgentYaml(unittest.TestCase):
    def test_agent_yaml_project_dir_is_used_when_env_unset(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "win" / "Users" / "bob" / ".claude" / "projects"
            store.mkdir(parents=True)
            ay = Path(tmp) / "agent.yaml"
            ay.write_text(f"name: t\nproject_dir: {store}\n")
            old = os.environ.pop("EDGE_PROJECT_DIR", None)
            try:
                self.assertEqual(_identity.project_dir(agent_yaml=ay), store)
            finally:
                if old is not None:
                    os.environ["EDGE_PROJECT_DIR"] = old


if __name__ == "__main__":
    unittest.main()
