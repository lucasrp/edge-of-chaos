"""Subprocess tests for the edge-rite-check CLI (candidate #2b-1).

Exercises the IO shell + exit-code contract around validate_rite.
"""
import copy
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CLI = REPO / "tools" / "edge-rite-check"

VALID = {
    "executive_summary": ["summary point"],
    "metrics": [{"value": "1", "label": "thing"}],
    "bibliography": [{"title": "a source"}],
    "sections": [
        {"role": "lineage", "title": "Linhagem", "blocks": [{"type": "paragraph", "text": "x"}]},
        {"title": "Body", "blocks": [{"type": "bar-chart", "title": "c", "items": []}]},
        {"role": "gaps", "title": "O que Não Sei", "blocks": [{"type": "paragraph", "text": "x"}]},
        {"role": "glossary", "title": "Glossário", "blocks": [{"type": "glossary", "terms": []}]},
    ],
}


def _run(path, *flags):
    return subprocess.run(
        [sys.executable, str(CLI), str(path), *flags],
        capture_output=True, text=True,
    )


class EdgeRiteCheckCLI(unittest.TestCase):
    _tmp = []

    def _write(self, spec, suffix=".yaml"):
        fd, name = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(yaml.safe_dump(spec))
        self._tmp.append(name)
        return name

    def _write_raw(self, text, suffix=".html"):
        fd, name = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self._tmp.append(name)
        return name

    @classmethod
    def tearDownClass(cls):
        for p in cls._tmp:
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_valid_exit_0(self):
        r = _run(self._write(copy.deepcopy(VALID)))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("RITE_OK", r.stdout)

    def test_violation_exit_1(self):
        s = copy.deepcopy(VALID); del s["metrics"]
        r = _run(self._write(s))
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing_metrics", r.stderr)

    def test_warn_does_not_block(self):
        s = copy.deepcopy(VALID); del s["metrics"]
        r = _run(self._write(s), "--warn")
        self.assertEqual(r.returncode, 0)
        self.assertIn("missing_metrics", r.stderr)

    def test_non_yaml_skips(self):
        r = _run(self._write_raw("<html><body>report</body></html>"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("RITE_SKIP", r.stdout)


if __name__ == "__main__":
    unittest.main()
