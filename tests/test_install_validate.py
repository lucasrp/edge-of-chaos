"""Install hardening + validation.

Two faults this guards:
  1. edge-apply assumed the genotype checkout (REPO) and the install home (edge_home) are DIFFERENT
     trees, and `shutil.copy(REPO/.. -> home/..)` raised SameFileError on the "checkout IS the home"
     topology. `place_file`/`place_tree` must no-op a self-copy instead of crashing.
  2. There was no install validation — a broken install (no venv, missing secret, empty graph group)
     was only discovered mid-beat. `validate_install` reports each check as (name, ok, detail) and
     NEVER raises; `format_report` renders it and tells the caller whether the install is healthy.

Pure: tmp dirs only; no real venv / neo4j.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _provision  # noqa: E402
import _validate    # noqa: E402


class PlaceSkipsSelfCopy(unittest.TestCase):
    def test_place_file_same_path_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "server.py"
            f.write_text("x = 1\n")
            self.assertFalse(_provision.place_file(f, f))   # src == dst: no copy, no SameFileError
            self.assertEqual(f.read_text(), "x = 1\n")

    def test_place_file_copies_when_different(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "src.py"; src.write_text("hi\n")
            dst = Path(d) / "sub" / "dst.py"
            self.assertTrue(_provision.place_file(src, dst))  # creates parent + copies
            self.assertEqual(dst.read_text(), "hi\n")

    def test_place_tree_same_dir_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            sk = Path(d) / "skills"; sk.mkdir(); (sk / "a.md").write_text("a")
            self.assertFalse(_provision.place_tree(sk, sk))   # src == dst: no-op, no crash
            self.assertTrue((sk / "a.md").exists())

    def test_place_tree_copies_when_different(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "skills"; src.mkdir(); (src / "a.md").write_text("a")
            dst = Path(d) / "home" / "skills"
            self.assertTrue(_provision.place_tree(src, dst))
            self.assertTrue((dst / "a.md").exists())


class ValidateNotifies(unittest.TestCase):
    CFG = {"sources": [], "routers": {}}

    def test_missing_venv_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            checks = {c[0]: c for c in _validate.validate_install(
                Path(d), self.CFG, Path(d) / "secrets", provisioned=True)}
            self.assertIn("venv", checks)
            self.assertFalse(checks["venv"][1])               # ok is False
            self.assertIn("missing", checks["venv"][2].lower())

    def test_layout_pass_and_fail(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            bad = {c[0]: c for c in _validate.validate_install(
                home, self.CFG, home / "secrets", provisioned=False)}
            self.assertFalse(bad["layout"][1])                # dirs absent → fail
            for sub in ("blog/entries", "state", "memory", "threads", "secrets"):
                (home / sub).mkdir(parents=True, exist_ok=True)
            good = {c[0]: c for c in _validate.validate_install(
                home, self.CFG, home / "secrets", provisioned=False)}
            self.assertTrue(good["layout"][1])

    def test_format_report_flags_failure(self):
        report, healthy = _validate.format_report([("layout", True, "ok"), ("venv", False, "missing")])
        self.assertIn("venv", report)
        self.assertFalse(healthy)                             # any ok==False → not healthy
        _, healthy_ok = _validate.format_report([("layout", True, "ok"), ("graph", None, "skipped")])
        self.assertTrue(healthy_ok)                           # None is advisory, not a failure


class ClassifyGraph(unittest.TestCase):
    def test_populated_group_is_ok(self):
        ok, detail = _validate._classify_graph("edge-next", 85, 143)
        self.assertTrue(ok)
        self.assertIn("85", detail)

    def test_fresh_empty_is_advisory_not_fail(self):
        ok, detail = _validate._classify_graph("edge-next", 0, 0)
        self.assertIsNone(ok)                                  # fresh install — not a failure
        self.assertIn("fresh", detail.lower())

    def test_orphaned_group_fails(self):
        ok, detail = _validate._classify_graph("ed", 0, 89)    # empty here, data under another group
        self.assertFalse(ok)
        self.assertIn("orphan", detail.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
