"""_envconf — repo-root .env loader + typed EDGE_* reads (slice S1 tunables-to-.env)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _envconf  # noqa: E402


class EnvConf(unittest.TestCase):
    def test_load_dotenv_sets_missing_keys_and_strips_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text('EDGE_TEST_A=5\n# a comment\n\nEDGE_TEST_B = "x"\n')
            os.environ.pop("EDGE_TEST_A", None)
            os.environ.pop("EDGE_TEST_B", None)
            keys = _envconf.load_dotenv(p)
            self.assertIn("EDGE_TEST_A", keys)
            self.assertEqual(os.environ["EDGE_TEST_A"], "5")
            self.assertEqual(os.environ["EDGE_TEST_B"], "x")   # surrounding quotes + spaces stripped

    def test_existing_env_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("EDGE_TEST_C=fromfile\n")
            os.environ["EDGE_TEST_C"] = "fromenv"
            _envconf.load_dotenv(p)
            self.assertEqual(os.environ["EDGE_TEST_C"], "fromenv")  # process env wins

    def test_non_edge_keys_are_ignored(self):
        # Codex S1 #23: the .env loader only sets EDGE_* tunables — never injects unrelated process
        # config (API keys, db urls) that belongs to secrets/*.env or the real environment.
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("EDGE_OK=1\nSECRET_API_KEY=leak\nDATABASE_URL=postgres://x\n")
            for k in ("EDGE_OK", "SECRET_API_KEY", "DATABASE_URL"):
                os.environ.pop(k, None)
            keys = _envconf.load_dotenv(p)
            self.assertIn("EDGE_OK", keys)
            self.assertNotIn("SECRET_API_KEY", os.environ)
            self.assertNotIn("DATABASE_URL", os.environ)
            os.environ.pop("EDGE_OK", None)

    def test_missing_file_is_noop(self):
        self.assertEqual(_envconf.load_dotenv(Path("/nonexistent/dir/.env")), [])

    def test_env_int_default_malformed_and_value(self):
        os.environ.pop("EDGE_TEST_INT", None)
        self.assertEqual(_envconf.env_int("EDGE_TEST_INT", 7), 7)         # missing → default
        os.environ["EDGE_TEST_INT"] = "not-an-int"
        self.assertEqual(_envconf.env_int("EDGE_TEST_INT", 7), 7)         # malformed → default
        os.environ["EDGE_TEST_INT"] = "12"
        self.assertEqual(_envconf.env_int("EDGE_TEST_INT", 7), 12)        # parsed
        os.environ.pop("EDGE_TEST_INT", None)


if __name__ == "__main__":
    unittest.main()
