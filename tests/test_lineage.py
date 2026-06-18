"""lineage.normalize_lineage — the single sanitizer for authored typed lineage (Cortex v1 brick-1),
matching MAIN's shape: a LIST of typed-edge dicts [{type, slug, target?}]. Pure/offline. It drops any
malformed item (never str()-coerces it) so junk can never ride into the proof-digest binding or the
durable publish event."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from lineage import normalize_lineage  # noqa: E402


class NormalizeLineage(unittest.TestCase):
    def test_none_and_non_list_become_empty(self):
        self.assertEqual(normalize_lineage(None), [])
        self.assertEqual(normalize_lineage("builds_on"), [])
        self.assertEqual(normalize_lineage({"builds_on": ["a"]}), [])  # the OLD dict shape is not main's
        self.assertEqual(normalize_lineage([]), [])

    def test_wellformed_edge_kept_verbatim(self):
        self.assertEqual(normalize_lineage([{"type": "builds_on", "slug": "alpha"}]),
                         [{"type": "builds_on", "slug": "alpha"}])

    def test_target_only_edge_kept(self):
        # the publisher's primary prior reference is `target` (slug optional) — this main-shape item rides.
        self.assertEqual(normalize_lineage([{"type": "supersedes", "target": "thread-7"}]),
                         [{"type": "supersedes", "target": "thread-7"}])

    def test_item_with_neither_slug_nor_target_dropped(self):
        self.assertEqual(normalize_lineage([{"type": "builds_on"}]), [])

    def test_all_three_types_kept(self):
        edges = [{"type": "builds_on", "slug": "a"},
                 {"type": "supersedes", "slug": "b"},
                 {"type": "contradicts", "slug": "c"}]
        self.assertEqual(normalize_lineage(edges), edges)

    def test_non_dict_items_dropped(self):
        self.assertEqual(normalize_lineage([{"type": "builds_on", "slug": "a"}, "junk", 5, None]),
                         [{"type": "builds_on", "slug": "a"}])

    def test_unknown_type_dropped(self):
        self.assertEqual(normalize_lineage([{"type": "relates_to", "slug": "a"},
                                            {"type": "", "slug": "b"},
                                            {"slug": "c"}]), [])

    def test_blank_or_nonstring_slug_dropped_never_coerced(self):
        self.assertEqual(normalize_lineage([{"type": "builds_on", "slug": "   "},
                                            {"type": "builds_on", "slug": 5},
                                            {"type": "builds_on", "slug": None},
                                            {"type": "builds_on"}]), [])

    def test_slug_stripped(self):
        self.assertEqual(normalize_lineage([{"type": "builds_on", "slug": "  a  "}]),
                         [{"type": "builds_on", "slug": "a"}])

    def test_target_carried_when_valid_else_omitted(self):
        self.assertEqual(normalize_lineage([{"type": "supersedes", "slug": "a", "target": " b "}]),
                         [{"type": "supersedes", "slug": "a", "target": "b"}])
        self.assertEqual(normalize_lineage([{"type": "supersedes", "slug": "a", "target": 7}]),
                         [{"type": "supersedes", "slug": "a"}])

    def test_dupes_collapse_order_preserving(self):
        self.assertEqual(
            normalize_lineage([{"type": "builds_on", "slug": "b"},
                               {"type": "builds_on", "slug": "a"},
                               {"type": "builds_on", "slug": "b"}]),
            [{"type": "builds_on", "slug": "b"}, {"type": "builds_on", "slug": "a"}])

    def test_extra_fields_dropped(self):
        # only the system-meaningful fields (type/slug/target) survive — no junk rides into the digest.
        self.assertEqual(normalize_lineage([{"type": "builds_on", "slug": "a", "evil": object()}]),
                         [{"type": "builds_on", "slug": "a"}])


if __name__ == "__main__":
    unittest.main()
