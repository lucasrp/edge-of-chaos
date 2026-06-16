"""Cortex-v1 (brick-1, slice lineage-producer-docs) — the DOC-PRESENCE proof that authored typed
lineage is REACHABLE from every producer's publish path.

The mechanism is already bound: `close.make_digest` mints over `lineage`, `publisher.publish`
materializes the DIRECTED edges, and the rich-rite floor accepts an authored lineage edge. The last
unbound seam is the producer SKILL.md publish snippets themselves — a producer can only author a
lineage edge if its snippet SHOWS the field.

The digest binds the artefato DICT, so a dict-only edit fails closed at the publisher: the published
payload must carry the same `lineage` the proof was minted over. Therefore BOTH are required and both
are asserted here — `lineage` in the artefato dict AND `lineage=art['lineage']` threaded through the
publish_fn lambda — mirroring test_recall_brief.py's SKILL.md token checks.
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# the six producer skills whose publish snippet authors a lineage edge
PRODUCERS = ("report", "research", "map", "plan", "discovery", "grill")


def _skill_text(name):
    return (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


class EveryProducerSnippetCarriesLineageInBothPlaces(unittest.TestCase):
    """For each producer SKILL.md publish snippet: `lineage` lives in the artefato dict (so the digest
    binds it) AND `lineage=art['lineage']` is threaded through the publish_fn lambda (so the published
    payload equals what the proof was minted over). Either alone fails closed at the publisher."""

    def test_artefato_dict_declares_the_lineage_field(self):
        for name in PRODUCERS:
            text = _skill_text(name)
            self.assertIn("'lineage':lineage", text,
                          f"{name}/SKILL.md: artefato dict must carry 'lineage':lineage so the "
                          f"close digest binds the authored lineage")

    def test_snippet_offers_a_builds_on_lineage_default(self):
        # the producer is shown how to author the edge R1's surf OFFERS it — a builds_on/<prior-slug>,
        # [] if none — not a bare empty hint that never reaches the dict.
        for name in PRODUCERS:
            text = _skill_text(name)
            self.assertIn("lineage=[{'type':'builds_on','slug':", text,
                          f"{name}/SKILL.md: the snippet must show the authored builds_on lineage "
                          f"the surf offers (slug = the prior the producer builds on)")

    def test_publish_fn_lambda_threads_lineage_off_the_minted_artefato(self):
        for name in PRODUCERS:
            text = _skill_text(name)
            self.assertIn("lineage=art['lineage']", text,
                          f"{name}/SKILL.md: publish_fn lambda must pass lineage=art['lineage'] so "
                          f"the published payload equals the proof-bound dict (else fails closed)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
