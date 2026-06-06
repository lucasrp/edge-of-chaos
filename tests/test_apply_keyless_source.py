"""verify_credentials must handle a keyless api source (no secret_ref) without crashing.

Regression: an `api` source declared without `secret_ref` (e.g. hn, arxiv — public, keyless)
made `_read_secret("")` resolve to the secrets *directory* → IsADirectoryError, crashing
edge-apply right after it mkdir'd secrets/. A keyless source needs no key: report it as OK,
never crash. Pure (no routers in cfg → no LLM probe, no network).
"""
import importlib.util
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPLY_PATH = REPO / "tools" / "edge-apply"

sys.path.insert(0, str(REPO / "tools"))  # so edge-apply's `import _llm` resolves
# edge-apply has no .py suffix → load it explicitly by source path.
_loader = SourceFileLoader("edge_apply", str(APPLY_PATH))
_spec = importlib.util.spec_from_loader("edge_apply", _loader)
edge_apply = importlib.util.module_from_spec(_spec)
_loader.exec_module(edge_apply)


class KeylessSource(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        (self.home / "secrets").mkdir()  # edge-apply always mkdirs this before verify

    def tearDown(self):
        self._tmp.cleanup()

    def test_keyless_api_source_does_not_crash(self):
        cfg = {"sources": [{"name": "hn", "kind": "api", "via": "GET ..."}]}
        rows = edge_apply.verify_credentials(self.home, cfg)  # must not raise
        row = next(r for r in rows if "hn" in r[0])
        self.assertIsNot(row[2], False, f"keyless source must not be a failure: {row}")

    def test_keyed_api_source_missing_key_reports_falta(self):
        cfg = {"sources": [{"name": "exa", "kind": "api",
                            "secret_ref": "exa.env:EXA_API_KEY"}]}
        rows = edge_apply.verify_credentials(self.home, cfg)
        row = next(r for r in rows if "exa" in r[0])
        self.assertFalse(row[2], f"missing key must report failure: {row}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
