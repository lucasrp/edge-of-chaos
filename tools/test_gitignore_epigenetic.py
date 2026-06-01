"""Guards that nested epigenetic state paths stay out of the genotype repo.

Each host produces private runtime output under nested `state/` and `reports/`
paths. The top-level `.gitignore` patterns (`state/*.md`, `reports/*.yaml`) are
non-recursive and let the *nested* artifact paths leak into shared commits.
These tests pin the operator-named nested paths as git-ignored so new per-host
output can never be tracked.
"""
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Operator-named nested epigenetic paths (issue #563). Representative files.
LEAKING_PATHS = [
    "state/blog/entries/some-entry.md",
    "state/reports/some-report.yaml",
    "state/reports/some-report.html",
    "state/audits/some-entry.state-audit.yaml",
]


class NestedEpigeneticStateIgnored(unittest.TestCase):
    def assert_ignored(self, path):
        result = subprocess.run(
            ["git", "check-ignore", path],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"{path!r} is NOT git-ignored — nested epigenetic state leaks into genotype",
        )

    def test_named_nested_paths_are_ignored(self):
        for path in LEAKING_PATHS:
            with self.subTest(path=path):
                self.assert_ignored(path)


if __name__ == "__main__":
    unittest.main()
