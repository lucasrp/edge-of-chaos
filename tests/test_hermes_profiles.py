import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import hermes_profiles


class HermesProfilesTest(unittest.TestCase):
    def test_membership_tri_state_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertFalse(hermes_profiles.membership(root, "default").enabled)
            (root / "config.yaml").write_text("edge_group: hive\n")
            self.assertEqual(hermes_profiles.membership(root, "work").edge_group, "hive")
            local = root / "profiles" / "work"
            local.mkdir(parents=True)
            (local / "config.yaml").write_text("edge_group:\n")
            self.assertEqual(hermes_profiles.membership(root, "work").edge_group, "work")


if __name__ == "__main__":
    unittest.main()
