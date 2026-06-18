"""S3 (R8): internal-evidence cite — a content-addressed runstore ref grounds an internal numeric claim
without an external snippet, verified by attest; never counts toward rich-rite:external-frame."""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import close  # noqa: E402

_OK = lambda a, m, v: (True, "ok")            # noqa: E731 — injected attest stub
_NO = lambda a, m, v: (False, "no match")     # noqa: E731


_CLAIM = "the V8 retrieval run scored AUC 85.0 on the held-out set"


def _art(cites, content=None):
    # the grounding claim is its OWN prose UNIT (S3 #7 whole-unit binding: a claim must equal a full
    # reader-visible paragraph, not a sub-fragment); a neighbour paragraph proves binding works amid
    # other prose.
    return {
        "slug": "s",
        "content": content or {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "We measured retrieval quality on the held-out set."},
            {"type": "paragraph", "text": f"{_CLAIM}."}]}]},
        "cites": cites,
        "proposes": [{"body": "name the budget", "kind": "constraint"}],
        "intent": "open: x; bet: y",
    }


def _ie_cite(kind="atividade", address="abc", metric="AUC", value=85.0, claim=_CLAIM, extra=None):
    c = {"kind": kind, "ref": f"runstore:{address}",
         "internal_evidence": {"address": address, "metric": metric, "value": value, "claim": claim}}
    if extra is not None:
        c["internal_evidence"] = extra
    return c


def _developed_prose():
    # >= RICH_RITE_PROSE_THRESHOLD prose blocks → a developed synthesis that OWES external-frame.
    n = close.RICH_RITE_PROSE_THRESHOLD + 1
    return {"sections": [{"title": "Body", "blocks": [
        {"type": "paragraph", "text": f"developed paragraph number {i} carrying real synthesis."}
        for i in range(n)]}]}


class InternalEvidenceCite(unittest.TestCase):
    def _cite_violations(self, art, attest):
        return [v for v in close.check_genus(art, attest=attest) if "cite" in v or "internal-evidence" in v]

    def test_verified_internal_evidence_grounds_without_snippet(self):
        self.assertEqual(self._cite_violations(_art([_ie_cite()]), _OK), [])

    def test_unverifiable_internal_evidence_is_a_violation(self):
        v = close.check_genus(_art([_ie_cite()]), attest=_NO)
        self.assertTrue(any("internal-evidence not verifiable" in x for x in v))

    def test_internal_evidence_must_be_atividade_kind(self):
        # a mundo-kind internal-evidence cite would wrongly count toward external-frame → rejected.
        v = close.check_genus(_art([_ie_cite(kind="mundo")]), attest=_OK)
        self.assertTrue(any("must be kind 'atividade'" in x for x in v))

    def test_internal_evidence_must_be_a_dict(self):
        v = close.check_genus(_art([_ie_cite(extra="not a dict")]), attest=_OK)
        self.assertTrue(any("internal_evidence must be a dict" in x for x in v))

    def test_divergent_content_number_is_not_grounded(self):
        # Codex S3 #1: a verified runstore value (85.0) attached to a content claim that states a
        # DIFFERENT number must fail — the cite's claim (AUC 85.0) is not in the content (which says 99.9).
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "In summary, the V8 run scored AUC 99.9 on the held-out set."}]}]}
        v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
        self.assertTrue(any("claim not found in content" in x for x in v))

    def test_claim_present_but_value_not_in_claim_is_violation(self):
        # the claim is a full sentence in content, but the attested value isn't stated in the claim → not
        # bound.
        cite = _ie_cite(value=85.0, claim="the run completed without errors")
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "the run completed without errors."}]}]}
        v = close.check_genus(_art([cite], content=content), attest=_OK)
        self.assertTrue(any("not stated in its claim" in x for x in v))

    def test_numeric_substring_does_not_falsely_bind(self):
        # Codex S3 #2: 85.0 must NOT bind to a claim that states 185.0 (substring) or 85th (ordinal) or
        # 0.85 — only a standalone numeric token equal to the value counts.
        for text, claim in (("the run scored AUC 185.0 overall", "the run scored AUC 185.0 overall"),
                            ("it finished in 85th place", "it finished in 85th place"),
                            ("a ratio of 0.85 was seen", "a ratio of 0.85 was seen")):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": text}]}]}
            cite = _ie_cite(value=85.0, claim=claim)
            v = close.check_genus(_art([cite], content=content), attest=_OK)
            self.assertTrue(any("not stated in its claim" in x for x in v),
                            f"85.0 wrongly bound to {claim!r}")

    def test_comma_grouped_number_does_not_falsely_bind(self):
        # Codex S3 #3: 85.0 must NOT bind to a thousands-grouped 1,085.0 or 85,000.
        for text in ("the count was 1,085.0 total", "throughput hit 85,000 ops"):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": text}]}]}
            v = close.check_genus(_art([_ie_cite(value=85.0, claim=text)], content=content), attest=_OK)
            self.assertTrue(any("not stated in its claim" in x for x in v), text)

    def test_runstore_ref_relabeled_as_mundo_is_rejected(self):
        # Codex S3 #3: a runstore: ref on a non-internal-evidence (mundo) cite is rejected — it can't
        # sneak onto the normal external-cite path.
        v = close.check_genus(_art([{"kind": "mundo", "ref": "runstore:abc", "snippet": "x"}]), attest=_OK)
        self.assertTrue(any("runstore ref must be" in x for x in v))

    def test_runstore_mundo_does_not_clear_external_frame(self):
        # defense-in-depth: even counted by external-frame, a runstore ref never clears it.
        cite = {"kind": "mundo", "ref": "runstore:abc", "snippet": "looks external"}
        v = close.check_genus(_art([cite], content=_developed_prose()), attest=_OK)
        self.assertIn("rich-rite:external-frame", v)

    def test_standalone_numeric_token_binds(self):
        # exact standalone match (and int/float equivalence) binds.
        for value, claim in ((85.0, "scored AUC 85.0 overall"), (85, "scored AUC 85 overall"),
                            (0.167, "exact_match was 0.167")):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": claim}]}]}
            cite = _ie_cite(value=value, claim=claim)
            v = [x for x in close.check_genus(_art([cite], content=content), attest=_OK)
                 if "internal-evidence" in x]
            self.assertEqual(v, [], f"{value!r} should bind to {claim!r}")

    def test_claim_hidden_in_nonrendered_field_does_not_bind(self):
        # Codex S3 #4: a claim placed ONLY in a non-rendered block field (the visible paragraph omits it)
        # must not satisfy the binding — the corpus is reader-visible rendered text only.
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "the run completed fine", "hidden_note": _CLAIM}]}]}
        v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
        self.assertTrue(any("claim not found in content" in x for x in v))

    def test_claim_in_raw_html_never_binds(self):
        # Codex S3 #5/#6/#7: a claim present ONLY inside a raw-html block — the sole author-controlled
        # markup vector — must NEVER satisfy the binding, regardless of HIDE MECHANISM. raw-html is
        # stripped from the claim corpus at the source, so this closes the OPEN-ENDED class (display:none,
        # visibility:hidden, aria-hidden, the boolean `hidden` attr, opacity:0, font-size:0, clipped/
        # offscreen layouts, non-rendered <template>, closed <details>, …) in one move — even a fully
        # VISIBLE raw-html claim no longer binds, since grounding must live in trusted rendered prose.
        markups = (f'<span style="display:none">{_CLAIM}</span>',
                   f'<span style="visibility:hidden">{_CLAIM}</span>',
                   f'<span aria-hidden="true">{_CLAIM}</span>',
                   f'<span hidden>{_CLAIM}</span>',           # boolean attr — browser-default display:none
                   f'<span hidden="">{_CLAIM}</span>',
                   f'<div hidden><p>{_CLAIM}</p></div>',      # hidden subtree, claim in a nested child
                   f'<span style="opacity:0">{_CLAIM}</span>',
                   f'<span style="font-size:0">{_CLAIM}</span>',
                   f'<template>{_CLAIM}</template>',          # non-rendered tag
                   f'<details><summary>x</summary>{_CLAIM}</details>',
                   f'<p>{_CLAIM}</p>')                        # even VISIBLE raw-html does not ground
        for markup in markups:
            content = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "the run completed fine"},
                {"type": "raw-html", "content": markup}]}]}
            v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), markup)

    def test_claim_in_raw_html_alias_never_binds(self):
        # the strip is by RESOLVED renderer, so every raw-html alias (html/custom-html/svg) is excluded
        # from the claim corpus too — not just the literal `raw-html` type string.
        for alias in ("html", "custom-html", "svg"):
            content = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "the run completed fine"},
                {"type": alias, "content": f"<p>{_CLAIM}</p>"}]}]}
            v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), alias)

    def test_claim_only_in_non_prose_block_does_not_bind(self):
        # Codex S3 #7 (corpus root): the grounding claim must be EXPLAINED in PROSE — a claim shown only
        # in a table cell, heading, chart label, or list item (a label/visual, not an explanation) must
        # NOT ground (R0 explain-not-label). Each below carries the exact claim in a non-prose block.
        non_prose = (
            {"type": "subsection", "title": _CLAIM},                                  # heading
            {"type": "table", "headers": ["m"], "rows": [[_CLAIM]]},                   # table cell
            {"type": "chart", "title": _CLAIM, "bars": [{"label": _CLAIM, "value": 85.0}]},  # visual label
            {"type": "list", "items": [_CLAIM]},                                       # list item
            {"type": "metrics-grid", "metrics": [{"value": "85.0", "label": _CLAIM}]},  # metric label
        )
        for block in non_prose:
            content = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "the run completed fine"}, block]}]}
            v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), block["type"])

    def test_claim_in_nested_paragraph_metadata_does_not_bind(self):
        # Codex S3 #7 (nested-metadata): a paragraph-shaped dict buried in a NON-prose block's payload
        # field is never rendered by render_section, so it must not enter the corpus. The corpus follows
        # real render topology (sections[].blocks via _iter_blocks), not arbitrary dict recursion — else a
        # hidden nested {"type":"paragraph", "text": claim} could ground a claim the reader never sees.
        nested = {"type": "paragraph", "text": _CLAIM}
        carriers = (
            {"type": "table", "headers": ["m"], "rows": [["x"]], "note_block": nested},
            {"type": "chart", "title": "t", "bars": [{"label": "x", "value": 1}], "caption": nested},
            {"type": "list", "items": ["x"], "meta": [nested]},
        )
        for block in carriers:
            content = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "the run completed fine"}, block]}]}
            v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), block["type"])

    def test_claim_in_styled_trusted_block_does_not_bind(self):
        # Codex S3 #7 (2nd vector): a TRUSTED paragraph still passes author `style` through `safe_style`,
        # which permits opacity:0 / font-size:0 / offscreen / color-hiding / display:none. Any inline style
        # makes the element possibly-invisible → its text must NOT ground a claim (fail-closed), without
        # enumerating CSS declarations.
        for style in ("opacity:0", "font-size:0", "position:absolute; left:-9999px",
                      "color:#fff", "display:none", "visibility:hidden"):
            content = {"sections": [{"title": "B", "blocks": [
                {"type": "paragraph", "text": "the run completed fine"},
                {"type": "paragraph", "text": _CLAIM, "style": style}]}]}
            v = close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), style)

    def test_claim_in_trusted_prose_still_binds(self):
        # the corpus restriction must not over-reach: the claim as its OWN prose unit among other
        # paragraphs (and alongside decorative raw-html) still grounds normally.
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "Here is the headline result."},
            {"type": "paragraph", "text": f"{_CLAIM}."},
            {"type": "raw-html", "content": "<p>decorative chrome, no claim here</p>"}]}]}
        v = [x for x in close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
             if "internal-evidence" in x]
        self.assertEqual(v, [])

    def test_abbreviation_does_not_fabricate_a_bindable_span(self):
        # Codex S3 #7 (sentence-split fabrication): an abbreviation/ellipsis must NOT create a bindable
        # sub-span. The claim must equal the WHOLE unit, so a fragment after `e.g.` cannot ground.
        for text in ("The run did not improve, e.g. scored AUC 85.0 on the held-out set.",
                     "Many caveats apply… scored AUC 85.0 on the held-out set."):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": text}]}]}
            cite = _ie_cite(value=85.0, claim="scored AUC 85.0 on the held-out set")  # fabricated fragment
            v = close.check_genus(_art([cite], content=content), attest=_OK)
            self.assertTrue(any("claim not found in content" in x for x in v), text)

    def test_br_split_digits_do_not_fuse_into_a_number(self):
        # Codex S3 #7 (<br> fusion): producer-authored <br> creates a visual line break, so `1000<br>0`
        # reads as two numbers — it must NOT fuse into a reader-invisible `10000` that a cite could ground.
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "processed 1000<br>0 documents in the run"}]}]}
        cite = _ie_cite(value=10000, claim="processed 10000 documents in the run")
        v = close.check_genus(_art([cite], content=content), attest=_OK)
        self.assertTrue(any("claim not found in content" in x for x in v))

    def test_malformed_comma_number_prefix_does_not_bind(self):
        # Codex S3 #7 (comma-prefix): a value must not bind to the PREFIX of a malformed comma run
        # (`1000,000` / `1,0000` / `12,3456`) — those yield no standalone token.
        for text, value in (("a typo like 1000,000 appeared", 1000),
                            ("a typo like 1,0000 appeared", 1),
                            ("a typo like 12,3456 appeared", 12)):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": f"{text}."}]}]}
            cite = _ie_cite(value=value, claim=text)
            v = close.check_genus(_art([cite], content=content), attest=_OK)
            self.assertTrue(any("not stated in its claim" in x for x in v), text)

    def test_callout_prose_unit_binds(self):
        # Codex S3 #7 (callout): rich-rite counts `callout` as prose and render_callout emits reader-visible
        # prose, so the internal-evidence corpus must too (shared PROSE_BLOCK_TYPES). A whole callout grounds.
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "Context."},
            {"type": "callout", "text": f"{_CLAIM}."}]}]}
        v = [x for x in close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
             if "internal-evidence" in x]
        self.assertEqual(v, [])

    def test_large_ungrouped_value_binds(self):
        # Codex S3 #7 (numeric): ungrouped values >= 1000 stated plainly must bind (they were rejected by
        # the old 1-3-leading-digit token regex).
        for value, claim in ((1000, "processed 1000 documents in the run"),
                             (12345, "the index held 12345 vectors"),
                             (-5000, "the delta was -5000 on the eval"),
                             (10000.0, "p99 latency measured 10000 ms")):
            content = {"sections": [{"title": "B", "blocks": [{"type": "paragraph", "text": f"{claim}."}]}]}
            cite = _ie_cite(value=value, claim=claim)
            v = [x for x in close.check_genus(_art([cite], content=content), attest=_OK)
                 if "internal-evidence" in x]
            self.assertEqual(v, [], f"{value!r} should bind to {claim!r}")

    def test_implicit_paragraph_block_binds(self):
        # Codex S3 #7 (implicit-paragraph): a block with no `type` renders as a paragraph (render default),
        # so it IS reader-visible prose and must ground exactly like an explicit paragraph.
        content = {"sections": [{"title": "B", "blocks": [
            {"text": "We measured retrieval quality."},   # implicit paragraph
            {"text": f"{_CLAIM}."}]}]}                     # implicit paragraph carrying the claim
        v = [x for x in close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
             if "internal-evidence" in x]
        self.assertEqual(v, [])

    def test_claim_fragment_of_negated_sentence_does_not_bind(self):
        # Codex S3 #7 (fragment-binding): the reader-visible sentence NEGATES the value, but the cite picks
        # a sub-fragment that reads as a clean assertion. Span-binding rejects any claim that isn't a FULL
        # sentence span, so the fragment cannot ground.
        content = {"sections": [{"title": "B", "blocks": [
            {"type": "paragraph", "text": "The run did not score AUC 85.0 on the held-out set."}]}]}
        cite = _ie_cite(value=85.0, claim="score AUC 85.0 on the held-out set")  # misleading fragment
        v = close.check_genus(_art([cite], content=content), attest=_OK)
        self.assertTrue(any("claim not found in content" in x for x in v))

    def test_claim_in_executive_summary_binds(self):
        # Codex S3 #7 (exec-summary): render renders top-level `executive_summary` as prose and rich-rite
        # counts it as prose, so the corpus must too — a claim stated as a full summary sentence grounds.
        content = {"executive_summary": [f"{_CLAIM}."],
                   "sections": [{"title": "B", "blocks": [
                       {"type": "paragraph", "text": "Body text that does not carry the claim."}]}]}
        v = [x for x in close.check_genus(_art([_ie_cite()], content=content), attest=_OK)
             if "internal-evidence" in x]
        self.assertEqual(v, [])

    def test_ref_must_bind_to_attested_address(self):
        # Codex S3 #5: the public `ref` MUST be runstore:<address> for the SAME address that is attested.
        # A missing / non-runstore / divergent-address ref must fail even when the hidden internal_evidence
        # address points at a valid run — else the displayed citation dereferences a different run.
        for ref in (None, "runstore:other", "arxiv:1", "runstore:"):
            cite = {"kind": "atividade",
                    "internal_evidence": {"address": "abc", "metric": "AUC", "value": 85.0, "claim": _CLAIM}}
            if ref is not None:
                cite["ref"] = ref
            v = close.check_genus(_art([cite]), attest=_OK)
            self.assertTrue(any("ref must be 'runstore:<address>'" in x for x in v), repr(ref))

    def test_missing_claim_is_violation(self):
        cite = _ie_cite(extra={"address": "abc", "metric": "AUC", "value": 85.0})  # no `claim`
        v = close.check_genus(_art([cite]), attest=_OK)
        self.assertTrue(any("missing `claim`" in x for x in v))

    def test_normal_cite_still_requires_snippet(self):
        v = close.check_genus(_art([{"kind": "mundo", "ref": "arxiv:1", "relevant": True}]), attest=_OK)
        self.assertTrue(any("missing snippet" in x for x in v))

    def test_internal_evidence_does_not_satisfy_external_frame(self):
        # a developed synthesis with ONLY a verified internal-evidence cite still owes external-frame.
        v = close.check_genus(_art([_ie_cite()], content=_developed_prose()), attest=_OK)
        self.assertIn("rich-rite:external-frame", v)

    def test_external_mundo_cite_does_satisfy_external_frame(self):
        # the same developed synthesis WITH a mundo cite clears external-frame (proving the split).
        mundo = {"kind": "mundo", "ref": "arxiv:2401.1", "snippet": "an outside benchmark result"}
        v = close.check_genus(_art([_ie_cite(), mundo], content=_developed_prose()), attest=_OK)
        self.assertNotIn("rich-rite:external-frame", v)


if __name__ == "__main__":
    unittest.main()
