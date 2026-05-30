"""The canonical Rite example must conform — regression anchor for #2b-2.

If validate_rite or the example drift apart, this fails. It also proves the
reference the report-template/skills point to actually passes the gate.
"""
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
EXAMPLE = REPO / "skills" / "_shared" / "report-rite-example.yaml"
CLI = REPO / "tools" / "edge-rite-check"

sys.path.insert(0, str(REPO))
from tools._shared.artifact_rite import validate_rite  # noqa: E402


class RiteExampleConforms(unittest.TestCase):
    def test_example_passes_validate_rite(self):
        spec = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(validate_rite(spec), [])

    def test_example_passes_cli(self):
        r = subprocess.run(
            [sys.executable, str(CLI), str(EXAMPLE)],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("RITE_OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
