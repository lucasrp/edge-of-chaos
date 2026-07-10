"""Cortex-v1 (brick-1, slice lineage-producer-docs) — the DOC-PRESENCE proof that authored typed
lineage is REACHABLE from every producer's publish path.

The mechanism is already bound: `close.make_digest` mints over `lineage`, `publisher.publish`
materializes the DIRECTED edges, and the rich-rite floor accepts an authored lineage edge. The last
unbound seam is the producer SKILL.md publish snippets themselves — a producer can only author a
lineage edge if its snippet SHOWS the field.

The digest binds the artefato DICT, so a dict-only edit fails closed at the publisher: the published
payload must carry the same `lineage` the proof was minted over. Therefore BOTH are required and both
are asserted here — `lineage` in the artefato dict AND `lineage=art['lineage']` threaded through the
publish_fn lambda.

This is the STRUCTURAL form of test_recall_brief.py's SKILL.md token checks (mirroring
test_producers.py:170-207): a bare whole-file `assertIn` would pass if the tokens merely appear in
prose/comments. So we EXTRACT the `artefato={...}` literal (brace-matched) and the `publish_fn=lambda`
region (paren-matched) and assert the lineage tokens live INSIDE those structures — proving the field
is in the dict the digest binds and the arg the publish lambda forwards, not just somewhere in the
file. We also pin that the proof-payload PROSE is consistent with the snippet: the digest-payload
description must name `lineage` (it is a persisted publish arg), so doc and code cannot drift.
"""
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

# the producer skills whose LEGACY close snippet authors a lineage edge. The genus-wide rito
# rollout (docs/rito-runtime.md §Producer adoption) moved every TEXT producer to the rite: its
# lineage rides `publish_meta` into `publisher.publish_rito` — pinned by RitoLineageRidesTheRito
# below, not by the run_close-snippet structure checks. What stays LEGACY here: `mentor` (its
# three-steers `grill_gate` close is untouched; only the insight-artefato leg moved — pinned by
# MentorInsightLegRidesTheRito below: run_rito present, NO legacy close.run_close( back door,
# publish_meta lineage reachable) and `prototype` (interactive single-file JS — its artefato does
# not fit the rite's pinned markdown renderer; the open decision lives in docs/rito-runtime.md
# §Interactive producers).
PRODUCERS = ("prototype",)

# the TEXT producers now exiting through the rito — lineage must still be REACHABLE via publish_meta.
RITO_PRODUCERS = ("report", "map", "plan", "research", "discovery")


def _skill_text(name):
    return (REPO / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _balanced_span(text, marker, opener, closer):
    """Return the substring starting at `marker` and running to the matching `closer`,
    counting `opener`/`closer` nesting. The snippets use `\\` line continuations, so the
    literal/region spans several lines — depth-matching is what makes the assertion
    structural rather than a whole-file string search (mirrors test_producers.py)."""
    start = text.find(marker)
    if start == -1:
        return None
    i = text.find(opener, start)
    if i == -1:
        return None
    depth = 0
    while i < len(text):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1
    return None


class EveryProducerSnippetCarriesLineageInBothPlaces(unittest.TestCase):
    """For each producer SKILL.md publish snippet: `lineage` lives in the artefato dict (so the digest
    binds it) AND `lineage=art['lineage']` is threaded through the publish_fn lambda (so the published
    payload equals what the proof was minted over). Either alone fails closed at the publisher. The
    tokens are asserted INSIDE the extracted structures, not anywhere in the file."""

    def setUp(self):
        self.texts = {p: _skill_text(p) for p in PRODUCERS}

    def _artefato_literal(self, name):
        """The bounded structure that enumerates the artefato fields the digest binds — NOT the whole
        file. Most producers hand close.run_close a `artefato={...}` dict literal (brace-matched across
        the `\\`-continued lines). mentor expresses the same fields inline as the paren-matched
        `every proof-bound field (...)` list. Either way we assert on the enumerated-field structure,
        so `'lineage':lineage` must live AMONG the fields — not merely somewhere in prose."""
        lit = _balanced_span(self.texts[name], "artefato={", "{", "}")
        if lit is None:
            lit = _balanced_span(self.texts[name], "every proof-bound field", "(", ")")
        self.assertIsNotNone(
            lit, f"{name}/SKILL.md: no brace-matched artefato={{...}} literal nor proof-bound-field "
                 f"list to anchor the artefato fields")
        return lit

    def _publish_lambda(self, name):
        """The `publish_fn=lambda art, proof: pub(...)` region (paren-matched from the `pub(` call),
        so we assert the lineage arg is FORWARDED by the lambda, not merely present in the file."""
        region = _balanced_span(self.texts[name], "publish_fn=lambda", "(", ")")
        self.assertIsNotNone(region, f"{name}/SKILL.md: no paren-matched publish_fn=lambda pub(...) region")
        return region

    def test_artefato_dict_declares_the_lineage_field(self):
        for name in PRODUCERS:
            lit = self._artefato_literal(name)
            self.assertIn("'lineage':lineage", lit,
                          f"{name}/SKILL.md: the artefato={{...}} literal must carry 'lineage':lineage "
                          f"so the close digest binds the authored lineage (found in dict, not prose)")

    def test_snippet_offers_a_builds_on_lineage_default(self):
        # the producer is shown how to author the edge R1's surf OFFERS it — a builds_on/<prior-slug>,
        # [] if none — bound to the `lineage` local the artefato dict reads, so it reaches the digest.
        for name in PRODUCERS:
            text = self.texts[name]
            self.assertIn("lineage=[{'type':'builds_on','slug':", text,
                          f"{name}/SKILL.md: the snippet must show the authored builds_on lineage "
                          f"the surf offers (slug = the prior the producer builds on)")

    def test_publish_fn_lambda_threads_lineage_off_the_minted_artefato(self):
        for name in PRODUCERS:
            region = self._publish_lambda(name)
            self.assertIn("lineage=art['lineage']", region,
                          f"{name}/SKILL.md: the publish_fn lambda must FORWARD lineage=art['lineage'] "
                          f"so the published payload equals the proof-bound dict (else fails closed)")


class ProofPayloadProseNamesLineage(unittest.TestCase):
    """The prose that describes the proof's digest payload must NOT drift from the snippet. Every
    producer doc enumerates the persisted publish args the digest binds (slug + spec + intent + cites
    + proposes + distills + skill + …); since the snippet now also publishes `lineage`, the payload
    prose must name it too — otherwise the doc claims a smaller digest than the code mints (the exact
    inconsistency the prior review flagged across five docs)."""

    def setUp(self):
        self.texts = {p: _skill_text(p) for p in PRODUCERS}

    def test_digest_payload_prose_enumerates_lineage(self):
        # the payload enumeration is the phrase ending in "EVERY persisted publish arg" — find it and
        # assert `lineage` is one of the named persisted args (it is, the snippet publishes it).
        for name in PRODUCERS:
            text = self.texts[name]
            m = re.search(r"\(slug.{0,400}?EVERY persisted publish arg\)", text, re.DOTALL)
            self.assertIsNotNone(
                m, f"{name}/SKILL.md: could not locate the digest-payload enumeration prose")
            payload_prose = m.group(0)
            self.assertIn("lineage", payload_prose,
                          f"{name}/SKILL.md: the digest-payload prose omits `lineage` while the snippet "
                          f"publishes it — doc claims a smaller digest than the code mints (drift)")

    def test_proof_bound_field_list_prose_enumerates_lineage(self):
        # the "build the artefato carrying every proof-bound field (slug, intent, content=spec, cites,
        # proposes, distills, skill, …)" list must also name lineage — same anti-drift invariant.
        for name in PRODUCERS:
            text = self.texts[name]
            m = re.search(r"every proof-bound field.{0,300}?\)", text, re.DOTALL)
            self.assertIsNotNone(
                m, f"{name}/SKILL.md: could not locate the proof-bound-field list prose")
            field_list = m.group(0)
            self.assertIn("lineage", field_list,
                          f"{name}/SKILL.md: the proof-bound-field list prose omits `lineage` while the "
                          f"snippet carries it in the artefato dict (doc/code drift)")


class RitoLineageRidesTheRito(unittest.TestCase):
    """Every rito producer exits through rito.run_rito; the authored lineage must still be
    REACHABLE — it rides the `publish_meta` dict the runtime forwards to publisher.publish_rito,
    which passes it to the same atomic publish seam the legacy path used."""

    def setUp(self):
        self.texts = {p: _skill_text(p) for p in RITO_PRODUCERS}

    def test_publish_meta_carries_lineage(self):
        for name, text in self.texts.items():
            meta = _balanced_span(text, "publish_meta={", "{", "}")
            self.assertIsNotNone(meta, f"{name}/SKILL.md: no publish_meta={{...}} literal")
            self.assertIn("'lineage'", meta,
                          f"{name}/SKILL.md: publish_meta omits 'lineage' — the authored edge "
                          "would be unreachable from the rito publish path")


class MentorInsightLegRidesTheRito(unittest.TestCase):
    """mentor is NOT a pure producer (it is absent from the test_producers roster and keeps its
    own three-steers `grill_gate` close), so the generalized rito pins never inspect it. But the
    codex adversarial pass found the gap: its insight-artefato PUBLICATION leg moved to the rite,
    and nothing forbade a stray legacy `close.run_close(` publication back door alongside the rito
    call, nor pinned the leg's publish_meta lineage. This closes both."""

    def setUp(self):
        self.text = _skill_text("mentor")

    def test_insight_leg_routes_through_run_rito(self):
        self.assertIn("rito.run_rito", self.text.replace(" ", ""),
                      "mentor's insight leg does not exit through rito.run_rito")

    def test_no_legacy_close_run_close_publication_call(self):
        # the three-steers close is grill_gate.py (a CLI), not close.run_close — so a
        # close.run_close( CALL in mentor could ONLY be a stray legacy publication back door.
        self.assertNotIn("close.run_close(", self.text.replace(" ", ""),
                         "mentor shows a close.run_close( call — a legacy publication back door "
                         "the insight leg was supposed to replace with the rite")

    def test_insight_leg_publish_meta_carries_lineage(self):
        meta = _balanced_span(self.text, "publish_meta={", "{", "}")
        self.assertIsNotNone(meta, "mentor/SKILL.md: no publish_meta={...} literal on the insight leg")
        self.assertIn("'lineage'", meta,
                      "mentor/SKILL.md: the insight leg's publish_meta omits 'lineage' — the "
                      "authored edge would be unreachable from the rito publish path")


if __name__ == "__main__":
    unittest.main(verbosity=2)
