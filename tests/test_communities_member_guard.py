"""corpus_role host|member: the corpus host runs consolidation; a member never does — the rule
that keeps N agents from consolidating the same corpus concurrently, with zero locking.
"""
import contextlib
import io
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import _identity  # noqa: E402
import communities  # noqa: E402


class MemberDoesNotConsolidate(unittest.TestCase):
    def test_member_role_skips_before_touching_the_graph(self):
        old = _identity.corpus
        _identity.corpus = lambda *a, **k: {"group": "t", "uri": "bolt://nope:1",
                                            "role": "member", "film_stores": []}
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                res = communities.consolidate(group="t")
        finally:
            _identity.corpus = old
        self.assertIsNone(res)
        self.assertIn("member", out.getvalue(),
                      "the skip must be DECLARED (never silent) and name the role")


if __name__ == "__main__":
    unittest.main()
