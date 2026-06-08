"""Story S5 — operator-sanctioned Idiom rename: ``insumos`` -> ``evidence``.

Guards two things at once:

1. The term ``insumos`` is gone from every file under ``skills/`` (the rename
   landed everywhere it occurred).
2. The CONTEXT.md glossary keeps **exactly** the same number of glossary entity
   headers it had before the rename — a count-preserving rename adds no NEW
   glossary entity (the no-new-entity fence). A rename keeps the count; an
   addition would bump it.
"""

import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(REPO, "skills")
CONTEXT = os.path.join(REPO, "CONTEXT.md")

# A glossary entity header is a line that *starts* with a bold span immediately
# followed by a colon at end-of-line, e.g. ``**Mentee**:`` — the term, then its
# definition on the lines below. Sentence fragments that merely begin with a
# bold span (a wrapped paragraph) have text after the colon and are excluded.
GLOSSARY_HEADER = re.compile(r"^\*\*[^*]+\*\*:\s*$", re.MULTILINE)

# Count captured at test-write time, AFTER auditing CONTEXT.md: 30 headers.
# CONTEXT.md does not define ``insumos`` as a glossary entry, so the rename
# touches no header here; this number must stay put.
EXPECTED_GLOSSARY_COUNT = 30


def _glossary_header_count(text):
    return len(GLOSSARY_HEADER.findall(text))


class NoInsumosRemain(unittest.TestCase):
    def test_no_insumos_in_skills_tree(self):
        offenders = []
        for root, _dirs, files in os.walk(SKILLS):
            for name in files:
                path = os.path.join(root, name)
                try:
                    with open(path, encoding="utf-8") as fh:
                        if "insumos" in fh.read():
                            offenders.append(path)
                except (UnicodeDecodeError, OSError):
                    # Binary or unreadable file cannot carry the term.
                    continue
        self.assertEqual(
            offenders,
            [],
            "files still contain 'insumos': %s" % offenders,
        )

    def test_glossary_entity_count_unchanged(self):
        with open(CONTEXT, encoding="utf-8") as fh:
            count = _glossary_header_count(fh.read())
        self.assertEqual(
            count,
            EXPECTED_GLOSSARY_COUNT,
            "CONTEXT.md glossary entity count changed (no NEW entity allowed): "
            "got %d, expected %d" % (count, EXPECTED_GLOSSARY_COUNT),
        )


if __name__ == "__main__":
    unittest.main()
