"""assembly.content_digest — stable digest of content with close-owned _grounding stripped."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import assembly  # noqa: E402


def _spec(text="alpha", with_grounding=False):
    block = {"type": "paragraph", "text": text}
    if with_grounding:
        block = {**block, "_grounding": {"sig": "x"}}
    return {"sections": [{"heading": "h", "blocks": [block]}], "additional_sections": []}


class ContentDigest(unittest.TestCase):
    def test_stable(self):
        self.assertEqual(assembly.content_digest(_spec()), assembly.content_digest(_spec()))

    def test_ignores_close_owned_grounding(self):
        self.assertEqual(
            assembly.content_digest(_spec(with_grounding=False)),
            assembly.content_digest(_spec(with_grounding=True)),
        )

    def test_moves_when_prose_moves(self):
        self.assertNotEqual(assembly.content_digest(_spec("alpha")),
                            assembly.content_digest(_spec("beta")))


if __name__ == "__main__":
    unittest.main()
