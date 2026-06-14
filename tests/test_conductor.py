"""The conductor — multi-agent artefato production, SLICE 1 (EDGE_CONDUCTOR, dark by default).

The conductor (issue #36) divides one over-large synthesis into a state-tracked outline of
nodes authored FROM the excavate seed, fills each node via the existing producer cognition
(the model call INJECTED as `complete_fn`, like close.py's reviewers), gates each node with a
deterministic mechanical contract (check_genus-style — never an LLM), and assembles the filled
nodes into one `content` block-spec that passes `close.check_genus`.

Slice 1 covers ONLY: outline-from-seed, per-node lifecycle state, injected fill, the mechanical
contract gate, and assembly. The scoped LLM review stack and the living split/merge outline are
slices 2-3 and are NOT exercised here.

The load-bearing guarantees under test (mirroring tests/test_excavate.py):
  - OFF (dark default) is a true no-op AND never spends a token (complete_fn untouched).
  - a seed of N findings authors a MULTI-node outline whose three-part arc (motivate → deliver
    → change-the-course) is covered, every finding assigned to exactly one node.
  - the per-node lifecycle transitions empty→draft→revised→final are pure and total.
  - the mechanical gate flags a node whose assigned finding was not discharged, and an empty node.
  - assembly of the filled nodes is a `content` spec that passes close.check_genus.
"""
import os
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import conductor  # noqa: E402
import close  # noqa: E402
import render  # noqa: E402


# A realistic excavate seed (the shape tools/excavate.py emits): findings + residuals.
_SEED = {
    "findings": [
        {"claim": "store cost rises with corpus size", "citation": "p.4 fig.2",
         "bears_on": "the read:write bet", "probe": "surprise"},
        {"claim": "nothing forgets by default", "citation": "sec.3",
         "bears_on": "the eviction rail", "probe": "contradiction"},
        {"claim": "the briefing re-derives core memory", "citation": "Letta docs",
         "bears_on": "the field frame", "probe": "lineage"},
    ],
    "residuals": ["is the lag live at 50 entities?"],
    "enabled": True,
    "passthrough": False,
}
_OBJECTIVE = "spec the dashboard read panels off the briefing registry"


def _spy_filler():
    """A stub complete_fn that records its calls and returns node prose that DISCHARGES
    whatever finding claims the writer prompt carries — so the mechanical gate passes. It
    echoes every `claim` substring it sees in the prompt, which is exactly what the gate
    scans for (the offline analogue of a writer that developed its assigned findings)."""
    calls = {"count": 0, "prompts": []}

    def complete_fn(prompt):
        calls["count"] += 1
        calls["prompts"].append(prompt)
        # Echo back the assigned claims so the node discharges them, plus a derivation/boundary/
        # lineage marker so the assembled whole clears the rich-rite floor.
        claims = [ln for ln in prompt.splitlines() if ln.strip()]
        body = ("Because the evidence shows it, it follows that " + " ".join(claims) +
                " — what i don't know: the open question of scale; this builds on prior work.")
        return body

    complete_fn.calls = calls
    return complete_fn


class EnabledFlag(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(conductor.enabled(env={}))

    def test_truthy_variants_on(self):
        for v in ("1", "true", "TRUE", "yes", "on", " On "):
            self.assertTrue(conductor.enabled(env={"EDGE_CONDUCTOR": v}), v)

    def test_falsy_variants_off(self):
        for v in ("", "0", "false", "no", "off"):
            self.assertFalse(conductor.enabled(env={"EDGE_CONDUCTOR": v}), v)


class DarkByDefault(unittest.TestCase):
    def test_off_is_passthrough_and_spends_nothing(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=False)
        self.assertFalse(result["enabled"])
        self.assertTrue(result["passthrough"])
        self.assertIsNone(result["content"])
        self.assertEqual(spy.calls["count"], 0, "OFF must never call the model")


class OutlineFromSeed(unittest.TestCase):
    def test_n_findings_author_a_multinode_outline(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        # multi-node: more than the bare three-part arc when there are several findings
        self.assertGreater(len(nodes), 3, "N findings should fan into a multi-node outline")
        for n in nodes:
            self.assertEqual(n["status"], "empty")
            self.assertIn("contract", n)
            self.assertIn("intent", n["contract"])
            self.assertIn("finding_ids", n["contract"])

    def test_three_part_arc_is_covered(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        roles = {n["role"] for n in nodes}
        self.assertEqual(roles, set(conductor.ARC_ROLES),
                         "the outline must cover motivate, deliver, and change-the-course")

    def test_every_finding_assigned_exactly_once(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        assigned = [fid for n in nodes for fid in n["contract"]["finding_ids"]]
        all_ids = [conductor.finding_id(i) for i in range(len(_SEED["findings"]))]
        self.assertEqual(sorted(assigned), sorted(all_ids))
        self.assertEqual(len(assigned), len(set(assigned)), "no finding assigned twice")

    def test_empty_seed_still_authors_the_arc(self):
        nodes = conductor.author_outline({"findings": [], "residuals": []}, _OBJECTIVE)
        roles = {n["role"] for n in nodes}
        self.assertEqual(roles, set(conductor.ARC_ROLES))


class LifecycleState(unittest.TestCase):
    """empty → draft → revised → final — pure, total transitions."""

    def test_forward_transitions(self):
        self.assertEqual(conductor.advance("empty"), "draft")
        self.assertEqual(conductor.advance("draft"), "revised")
        self.assertEqual(conductor.advance("revised"), "final")

    def test_final_is_terminal(self):
        self.assertEqual(conductor.advance("final"), "final")

    def test_unknown_status_raises(self):
        with self.assertRaises(ValueError):
            conductor.advance("bogus")

    def test_fill_drives_empty_to_draft(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler()
        filled = conductor.fill_node(nodes[0], _SEED, _OBJECTIVE, spy, outline=nodes)
        self.assertEqual(filled["status"], "draft")
        self.assertEqual(spy.calls["count"], 1)
        self.assertTrue(filled["blocks"], "a filled node carries content blocks")


class MechanicalGate(unittest.TestCase):
    """Deterministic per-node contract gate (check_genus-style) — never an LLM."""

    def test_discharged_node_has_no_violations(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler()
        # fill the deliver node that owns at least one finding
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        filled = conductor.fill_node(deliver, _SEED, _OBJECTIVE, spy, outline=nodes)
        self.assertEqual(conductor.contract_gate(filled, _SEED), [])

    def test_undischarged_finding_is_flagged(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        # a node "filled" with prose that never develops the assigned finding
        starved = {**deliver, "status": "draft",
                   "blocks": [{"type": "paragraph", "text": "unrelated filler prose"}]}
        violations = conductor.contract_gate(starved, _SEED)
        self.assertTrue(violations, "an undischarged assigned finding must be flagged")
        first_claim = _SEED["findings"][deliver["contract"]["finding_ids"][0]
                                         if isinstance(deliver["contract"]["finding_ids"][0], int)
                                         else 0]
        # the violation names the undischarged finding
        self.assertTrue(any("finding" in v.lower() for v in violations), violations)

    def test_empty_node_is_flagged(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        empty = {**nodes[0], "status": "draft", "blocks": []}
        violations = conductor.contract_gate(empty, _SEED)
        self.assertTrue(any("empty" in v.lower() or "non-empty" in v.lower() for v in violations),
                        violations)


class Assembly(unittest.TestCase):
    """The filled nodes assemble into a `content` spec that passes close.check_genus."""

    def test_assembled_content_passes_check_genus(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True)
        self.assertTrue(result["enabled"])
        self.assertFalse(result["passthrough"])
        # one fill call per node, one semantic-discharge call per node that owns findings,
        # plus one conciliator call (the synthetic through-line)
        with_findings = sum(1 for n in result["outline"] if n["contract"]["finding_ids"])
        self.assertEqual(spy.calls["count"], len(result["outline"]) + with_findings + 1)
        content = result["content"]
        self.assertIn("sections", content)
        # wrap in the artefato fields the seed/producer supplies (cites with an outside frame,
        # intent, distills) — the conductor owns `content`; check_genus reads the whole.
        artefato = {
            "slug": "conductor-smoke",
            "content": content,
            "intent": _OBJECTIVE,
            "cites": [{"ref": "Letta docs", "kind": "mundo", "relevant": True,
                       "snippet": "core memory is always-in-context working memory"}],
            "proposes": [{"body": "spec the read panels off the registry", "kind": "thread"}],
            "distills": ["cluster:briefing"],
        }
        self.assertEqual(close.check_genus(artefato), [])

    def test_all_nodes_reach_final(self):
        spy = _spy_filler()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True)
        self.assertTrue(all(n["status"] == "final" for n in result["outline"]),
                        "every gated node should be driven to final")


class EnvPathDefault(unittest.TestCase):
    """The is_enabled=None path actually consults EDGE_CONDUCTOR (the production wiring)."""

    def setUp(self):
        self._saved = os.environ.get("EDGE_CONDUCTOR")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("EDGE_CONDUCTOR", None)
        else:
            os.environ["EDGE_CONDUCTOR"] = self._saved

    def test_env_off_is_passthrough_no_spend(self):
        spy = _spy_filler()
        os.environ["EDGE_CONDUCTOR"] = "off"
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy)  # env decides
        self.assertTrue(result["passthrough"])
        self.assertEqual(spy.calls["count"], 0)

    def test_env_on_runs(self):
        spy = _spy_filler()
        os.environ["EDGE_CONDUCTOR"] = "1"
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy)
        self.assertTrue(result["enabled"])
        self.assertGreater(spy.calls["count"], 0)


# ===========================================================================
# ENRICHMENT (slices 2-3): place-aware orientation, writer digests, semantic
# discharge, conciliation (deep + synthetic), two-altitude output.
# ===========================================================================


class PlaceAwareOrientation(unittest.TestCase):
    """The '23 different intros' fix: each node knows its PLACE in the arc and what
    upstream already established, and the writer prompt is a CONTINUATION directive over
    the WHOLE-outline map — never a standalone intro per node."""

    def test_every_node_carries_its_place(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        for i, n in enumerate(nodes):
            self.assertIn("place", n, f"node {i} must carry its place in the arc")
            place = n["place"]
            self.assertIn("position", place)        # e.g. "2 of 5"
            self.assertIn("established_upstream", place)  # what prior nodes set

    def test_first_node_has_no_upstream(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        self.assertEqual(nodes[0]["place"]["established_upstream"].strip(), "",
                         "the opening node establishes the frame; nothing precedes it")

    def test_downstream_node_summarizes_what_came_before(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        # a later node's established_upstream names the roles/intents that precede it
        last = nodes[-1]
        upstream = last["place"]["established_upstream"].lower()
        self.assertTrue(upstream.strip(), "a downstream node must summarize its upstream")
        self.assertIn("motivate", upstream, "upstream summary names the prior arc roles")

    def test_writer_prompt_is_a_continuation_over_the_whole_map(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        downstream = nodes[-1]
        prompt = conductor._writer_prompt(downstream, nodes, _SEED, _OBJECTIVE)
        low = prompt.lower()
        # the whole-outline MAP (not just this node) — other nodes' intents are present
        self.assertIn(nodes[0]["contract"]["intent"][:30].lower(), low,
                      "the writer must see the WHOLE outline (the map), not just its node")
        # the continuation directive
        self.assertIn("continuation", low)
        self.assertTrue("do not re-establish" in low or "mid-stream" in low
                        or "do not re-introduce" in low,
                        "the writer must be told to open mid-stream, not re-establish context")
        # the upstream context
        self.assertIn(downstream["place"]["established_upstream"][:30].lower(), low)


class WriterDigests(unittest.TestCase):
    """fill_node returns, alongside the body, a structured digest the conciliator works off."""

    def test_digest_parsed_from_model_output(self):
        node = conductor.author_outline(_SEED, _OBJECTIVE)[1]

        def complete_fn(prompt):
            return (
                "BODY: developed prose for this node that earns store cost rises with corpus size.\n"
                '```json\n{"bullets": ["cost rises with corpus", "no eviction"], '
                '"assumed_prior": "the frame is set", '
                '"contribution": "establishes the read:write cost", '
                '"cross_refs": ["the eviction rail"]}\n```'
            )

        filled = conductor.fill_node(node, _SEED, _OBJECTIVE, complete_fn,
                                     outline=conductor.author_outline(_SEED, _OBJECTIVE))
        digest = filled["digest"]
        self.assertEqual(digest["bullets"], ["cost rises with corpus", "no eviction"])
        self.assertEqual(digest["assumed_prior"], "the frame is set")
        self.assertEqual(digest["contribution"], "establishes the read:write cost")
        self.assertEqual(digest["cross_refs"], ["the eviction rail"])
        # the body is still present and carries the prose
        self.assertTrue(filled["blocks"], "the body survives alongside the digest")

    def test_garbage_digest_is_empty_never_crashes(self):
        node = conductor.author_outline(_SEED, _OBJECTIVE)[1]

        def complete_fn(prompt):
            return "just prose, no json at all, the model refused the schema"

        filled = conductor.fill_node(node, _SEED, _OBJECTIVE, complete_fn,
                                     outline=conductor.author_outline(_SEED, _OBJECTIVE))
        digest = filled["digest"]
        self.assertEqual(digest["bullets"], [])
        self.assertEqual(digest["assumed_prior"], "")
        self.assertEqual(digest["contribution"], "")
        self.assertEqual(digest["cross_refs"], [])
        # and the body is still the model's text (prose survives a bad digest)
        self.assertTrue(filled["blocks"])

    def test_parse_digest_direct_tolerance(self):
        # malformed/garbage shapes never crash, always yield the empty digest shape
        for bad in ("", "   ", "not json", "{not: valid}", "[]", "null", "{}"):
            d = conductor._parse_digest(bad)
            self.assertEqual(set(d), {"bullets", "assumed_prior", "contribution", "cross_refs"})
            self.assertIsInstance(d["bullets"], list)
            self.assertIsInstance(d["cross_refs"], list)


class SemanticDischarge(unittest.TestCase):
    """The verbatim-echo fix: a per-finding semantic discharge check via an injected model,
    SEPARATE from the deterministic structural gate (which stays mechanical)."""

    def test_paraphrase_passes_semantic_even_when_mechanical_would_fail(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        # prose that PARAPHRASES the claim (no verbatim echo) — the mechanical gate flags it...
        paraphrased = {**deliver, "status": "draft",
                       "blocks": [{"type": "paragraph",
                                   "text": "storage grows as the corpus expands; the bigger the "
                                           "body of memory, the steeper the bill."}]}
        self.assertTrue(conductor.contract_gate(paraphrased, _SEED),
                        "mechanical gate demands verbatim echo and flags paraphrase")

        # ...but the semantic check (injected judge) passes it per-finding
        def judge(prompt):
            return '{"verdicts": [{"finding_id": "f0", "delivered": true}]}'

        result = conductor.semantic_discharge(paraphrased, _SEED, judge)
        self.assertTrue(all(v["delivered"] for v in result),
                        "the semantic judge passes legitimate paraphrase")
        self.assertEqual(result[0]["finding_id"], "f0")

    def test_semantic_flags_a_dropped_finding(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])
        starved = {**deliver, "status": "draft",
                   "blocks": [{"type": "paragraph", "text": "unrelated filler"}]}

        def judge(prompt):
            return '{"verdicts": [{"finding_id": "f0", "delivered": false}]}'

        result = conductor.semantic_discharge(starved, _SEED, judge)
        self.assertFalse(all(v["delivered"] for v in result))

    def test_semantic_tolerant_of_garbage_judge(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        deliver = next(n for n in nodes if n["contract"]["finding_ids"])

        def judge(prompt):
            return "the model refused, no json"

        # garbage judge => fail-closed per assigned finding (delivered: False), never crashes
        result = conductor.semantic_discharge(deliver, _SEED, judge)
        self.assertTrue(result, "every assigned finding gets a verdict")
        self.assertFalse(any(v["delivered"] for v in result), "garbage judge fails closed")

    def test_node_with_no_findings_returns_empty(self):
        nodes = conductor.author_outline(_SEED, _OBJECTIVE)
        motivate = next(n for n in nodes if not n["contract"]["finding_ids"])

        def judge(prompt):
            raise AssertionError("must not call the judge when there are no findings")

        self.assertEqual(conductor.semantic_discharge(motivate, _SEED, judge), [])


class Conciliation(unittest.TestCase):
    """conciliate works off the DIGESTS to produce a smoothed DEEP spec and a 2-page
    SYNTHETIC spec; both pass close.check_genus; the synthetic is materially shorter."""

    def _filled_nodes(self):
        spy = _spy_filler_with_digest()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True)
        return result["outline"], result

    def test_conciliate_returns_both_specs(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler_with_digest()
        filled = [conductor.fill_node(n, _SEED, _OBJECTIVE, spy, outline=outline) for n in outline]

        def conciliator(prompt):
            return "A flowing executive synthesis: cost rises, nothing forgets, the briefing re-derives."

        deep, synthetic, _shape = conductor.conciliate(filled, outline, _OBJECTIVE, conciliator)
        self.assertIn("sections", deep)
        self.assertIn("sections", synthetic)

    def test_both_specs_pass_check_genus(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler_with_digest()
        filled = [conductor.fill_node(n, _SEED, _OBJECTIVE, spy, outline=outline) for n in outline]

        def conciliator(prompt):
            return ("Because the evidence shows it, it follows that cost rises with corpus size, "
                    "nothing forgets by default, and the briefing re-derives core memory — "
                    "what i don't know: the live lag; this builds on the excavate seed.")

        deep, synthetic, _shape = conductor.conciliate(filled, outline, _OBJECTIVE, conciliator)
        wrap = lambda spec: {
            "slug": "conc", "content": spec, "intent": _OBJECTIVE,
            "cites": [{"ref": "Letta docs", "kind": "mundo", "relevant": True,
                       "snippet": "core memory is always-in-context working memory"}],
            "proposes": [{"body": "spec the read panels", "kind": "thread"}],
            "distills": ["cluster:briefing"],
        }
        self.assertEqual(close.check_genus(wrap(deep)), [], "deep spec must pass genus")
        self.assertEqual(close.check_genus(wrap(synthetic)), [], "synthetic spec must pass genus")

    def test_synthetic_is_materially_shorter_than_deep(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler_with_digest()
        filled = [conductor.fill_node(n, _SEED, _OBJECTIVE, spy, outline=outline) for n in outline]

        def conciliator(prompt):
            return ("A short through-line over the digests — it follows that cost rises; "
                    "what i don't know: the lag; this builds on prior work.")

        deep, synthetic, _shape = conductor.conciliate(filled, outline, _OBJECTIVE, conciliator)
        self.assertLess(_spec_len(synthetic), _spec_len(deep) / 2,
                        "the synthetic must be materially shorter than the deep report")


class TwoAltitudeOutput(unittest.TestCase):
    """run_conductor returns {deep_spec, synthetic_spec}; both render to non-empty HTML."""

    def test_run_returns_both_specs_that_render(self):
        spy = _spy_filler_with_digest()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True,
                                         conciliate_fn=_concise_conciliator)
        self.assertIn("deep_spec", result)
        self.assertIn("synthetic_spec", result)
        deep_html = render.spec_to_html(result["deep_spec"])
        syn_html = render.spec_to_html(result["synthetic_spec"])
        self.assertTrue(deep_html.strip(), "deep spec renders to non-empty HTML")
        self.assertTrue(syn_html.strip(), "synthetic spec renders to non-empty HTML")

    def test_off_still_passthrough_zero_spend(self):
        spy = _spy_filler_with_digest()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=False)
        self.assertTrue(result["passthrough"])
        self.assertIsNone(result["deep_spec"])
        self.assertIsNone(result["synthetic_spec"])
        self.assertEqual(spy.calls["count"], 0, "OFF must never call the model")


# ===========================================================================
# CODEX ROUND (round-7): back-compat fill_node signature, enforced semantic
# discharge, genus-validate-before-return, synthetic shape gate, parser guard.
# ===========================================================================


class FillNodeBackCompat(unittest.TestCase):
    """Finding 1: `outline` is keyword-only with a default, so the old 4-arg
    `fill_node(node, seed, objective, complete_fn)` caller is not broken."""

    def test_fill_node_works_without_outline(self):
        node = conductor.author_outline(_SEED, _OBJECTIVE)[1]
        spy = _spy_filler()
        # old 4-arg call — no outline at all
        filled = conductor.fill_node(node, _SEED, _OBJECTIVE, spy)
        self.assertEqual(filled["status"], "draft")
        self.assertEqual(spy.calls["count"], 1)
        self.assertTrue(filled["blocks"], "a filled node carries content blocks")

    def test_fill_node_with_outline_is_place_aware(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        downstream = outline[-1]
        spy = _spy_filler()
        conductor.fill_node(downstream, _SEED, _OBJECTIVE, spy, outline=outline)
        prompt = spy.calls["prompts"][0].lower()
        # with the outline, the writer sees the WHOLE-outline map (another node's intent)
        self.assertIn(outline[0]["contract"]["intent"][:30].lower(), prompt,
                      "with outline the writer sees the map of the whole arc")


class EnforcedSemanticDischarge(unittest.TestCase):
    """Finding 2: run_conductor RUNS semantic_discharge per node and surfaces
    per-node false verdicts in a `discharge` field so a semantic failure blocks."""

    def test_false_semantic_verdict_surfaces_as_flagged_node(self):
        def complete_fn(prompt):
            # a writer prompt asks for prose+digest; the semantic judge asks for verdicts.
            if "SEMANTIC discharge reviewer" in prompt:
                return '{"verdicts": [{"finding_id": "f0", "delivered": false}, ' \
                       '{"finding_id": "f1", "delivered": false}, ' \
                       '{"finding_id": "f2", "delivered": false}]}'
            claims = [ln for ln in prompt.splitlines() if ln.strip()]
            return ("Because the evidence shows it, it follows that " + " ".join(claims) +
                    " — what i don't know: scale; this builds on prior work.")

        result = conductor.run_conductor(_SEED, _OBJECTIVE, complete_fn, is_enabled=True)
        # every node carries a discharge record; at least one finding is flagged false
        flagged = [n for n in result["outline"]
                   if any(not v["delivered"] for v in n.get("discharge", []))]
        self.assertTrue(flagged, "a FALSE semantic verdict must surface as a flagged node")
        # and the result exposes a top-level discharge summary of the flagged nodes
        self.assertIn("discharge", result)
        self.assertTrue(result["discharge"], "run_conductor flags discharge failures")


class GenusValidateBeforeReturn(unittest.TestCase):
    """Finding 3: run_conductor validates BOTH specs with close.check_genus and
    surfaces violations in a `genus` field rather than returning an invalid spec."""

    def test_clean_run_has_no_genus_violations(self):
        spy = _spy_filler_with_digest()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True,
                                         conciliate_fn=_concise_conciliator)
        self.assertIn("genus", result)
        self.assertEqual(result["genus"]["deep"], [])
        self.assertEqual(result["genus"]["synthetic"], [])

    def test_genus_invalid_spec_surfaces_violations(self):
        # a degraded spec with a structurally MALFORMED block (a paragraph missing its required
        # `text`) must surface a genus violation, not pass through silently — this is the gate
        # run_conductor applies to BOTH the deep and synthetic specs before returning.
        bad_spec = {"title": _OBJECTIVE, "sections": [
            {"title": "Synthesis", "blocks": [{"type": "paragraph", "label": "lag"}]},
        ]}
        violations = conductor._genus_violations(bad_spec, _OBJECTIVE)
        self.assertTrue(violations,
                        "a genus-invalid spec must surface its violations, not pass through")


class SyntheticShapeGate(unittest.TestCase):
    """Finding 4: conciliate flags a synthetic that is empty, too short, or a bare
    bullet dump (no prose paragraphs)."""

    def _filled(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        spy = _spy_filler_with_digest()
        filled = [conductor.fill_node(n, _SEED, _OBJECTIVE, spy, outline=outline)
                  for n in outline]
        return filled, outline

    def test_empty_synthetic_is_flagged(self):
        filled, outline = self._filled()
        _deep, _syn, shape = conductor.conciliate(filled, outline, _OBJECTIVE,
                                                  lambda p: "   ")
        self.assertTrue(shape, "an empty synthetic must be flagged")

    def test_too_short_synthetic_is_flagged(self):
        filled, outline = self._filled()
        _deep, _syn, shape = conductor.conciliate(filled, outline, _OBJECTIVE,
                                                  lambda p: "too short.")
        self.assertTrue(shape, "a too-short synthetic must be flagged")

    def test_bullet_dump_synthetic_is_flagged(self):
        filled, outline = self._filled()
        dump = ("- cost rises with corpus size\n- nothing forgets by default\n"
                "- the briefing re-derives core memory\n- the lag is unknown\n"
                "- this builds on prior work\n- what i don't know: the live lag")

        _deep, _syn, shape = conductor.conciliate(filled, outline, _OBJECTIVE,
                                                  lambda p: dump)
        self.assertTrue(shape, "a bare bullet-dump synthetic must be flagged")

    def test_healthy_synthetic_is_not_flagged(self):
        filled, outline = self._filled()
        _deep, _syn, shape = conductor.conciliate(filled, outline, _OBJECTIVE,
                                                  _concise_conciliator)
        self.assertEqual(shape, [], "a flowing prose synthesis is not flagged")

    def test_run_conductor_surfaces_synthetic_shape(self):
        spy = _spy_filler_with_digest()
        result = conductor.run_conductor(_SEED, _OBJECTIVE, spy, is_enabled=True,
                                         conciliate_fn=lambda p: "- a\n- b\n- c")
        self.assertIn("synthetic_shape", result)
        self.assertTrue(result["synthetic_shape"], "the shape gate surfaces in the result")


class ParserGuard(unittest.TestCase):
    """Finding 5: _parse_digest never crashes on a non-string raw (e.g. a list)."""

    def test_non_string_raw_returns_empty_digest(self):
        for bad in ([], ["a", "b"], {"x": 1}, 42, None, object()):
            d = conductor._parse_digest(bad)
            self.assertEqual(set(d), {"bullets", "assumed_prior", "contribution", "cross_refs"})
            self.assertEqual(d["bullets"], [])
            self.assertEqual(d["cross_refs"], [])


class PlaceAwareCoverageGaps(unittest.TestCase):
    """Coverage gap (Codex): place-aware orientation with a missing/empty `place`."""

    def test_writer_prompt_tolerates_missing_place(self):
        node = conductor.author_outline(_SEED, _OBJECTIVE)[1]
        node = {k: v for k, v in node.items() if k != "place"}  # drop place entirely
        prompt = conductor._writer_prompt(node, [], _SEED, _OBJECTIVE)
        self.assertTrue(prompt.strip(), "a node with no place still yields a prompt")

    def test_writer_prompt_tolerates_empty_place(self):
        node = conductor.author_outline(_SEED, _OBJECTIVE)[1]
        node = {**node, "place": {"position": "", "established_upstream": ""}}
        prompt = conductor._writer_prompt(node, [], _SEED, _OBJECTIVE)
        # empty upstream => treated as the opening node, never a crash
        self.assertIn("opening node", prompt.lower())


class ConciliationGarbage(unittest.TestCase):
    """Coverage gap (Codex): conciliation over garbage filled-node output."""

    def test_conciliate_over_nodes_with_no_digests(self):
        outline = conductor.author_outline(_SEED, _OBJECTIVE)
        # nodes with no blocks and no digest at all (degraded fill)
        garbage = [{**n, "blocks": [], "digest": None} for n in outline]
        deep, synthetic, _shape = conductor.conciliate(garbage, outline, _OBJECTIVE,
                                                       _concise_conciliator)
        # never crashes; both specs are still well-formed dicts with sections
        self.assertIn("sections", deep)
        self.assertIn("sections", synthetic)


def _spec_len(spec: dict) -> int:
    """Total prose length of a content spec (for the materially-shorter assertion)."""
    import json as _json
    return len(_json.dumps(spec, ensure_ascii=False))


def _concise_conciliator(prompt):
    return ("A flowing synthesis over the digests: it follows that cost rises with corpus size "
            "and nothing forgets — what i don't know: the live lag; this builds on prior work.")


def _spy_filler_with_digest():
    """Like _spy_filler but also emits a parseable digest block, so fill_node returns a digest."""
    calls = {"count": 0, "prompts": []}

    def complete_fn(prompt):
        calls["count"] += 1
        calls["prompts"].append(prompt)
        claims = [ln for ln in prompt.splitlines() if ln.strip()]
        body = ("Because the evidence shows it, it follows that " + " ".join(claims) +
                " — what i don't know: the open question of scale; this builds on prior work.")
        digest = ('{"bullets": ["a key point", "another point"], '
                  '"assumed_prior": "the frame is set upstream", '
                  '"contribution": "develops the assigned findings", '
                  '"cross_refs": []}')
        return body + "\n```json\n" + digest + "\n```"

    complete_fn.calls = calls
    return complete_fn


class LiveTestSurfacedBugsFixed(unittest.TestCase):
    """The three defects the live deploy-smoke surfaced (2026-06-14), each fixed here."""

    def test_boundary_block_text_does_not_repeat_its_title(self):
        # bug #2: callout rendered "What I don't knowWhat I don't know:" (title + text mashed)
        b = conductor._boundary_block([])
        self.assertEqual(b["title"], "What I don't know")
        self.assertNotIn("what i don't know", b["text"].lower())

    def test_assemble_boundary_text_does_not_repeat_its_title(self):
        seed = {"findings": [{"claim": "c", "citation": "e", "bears_on": "b", "probe": "relevance"}],
                "residuals": ["r1"]}
        spec = conductor.assemble([], seed, "obj")
        oq = [s for s in spec["sections"] if s["title"] == "Open questions"][0]
        self.assertNotIn("what i don't know", oq["blocks"][0]["text"].lower())

    def test_derivation_drops_degenerate_contributions(self):
        # bug #3: stray fragments ("D", "Esta.") leaked into the derivation bullets
        nodes = [
            {"digest": {"bullets": [], "assumed_prior": "", "contribution": "D", "cross_refs": []}},
            {"digest": {"bullets": [], "assumed_prior": "", "contribution": "Esta.", "cross_refs": []}},
            {"digest": {"bullets": [], "assumed_prior": "",
                        "contribution": "this node establishes the medium boundary", "cross_refs": []}},
        ]
        d = conductor._digest_derivation(nodes, "lead")
        self.assertEqual(d["bullets"], ["this node establishes the medium boundary"])
        self.assertNotIn("D", d["bullets"])
        self.assertNotIn("Esta.", d["bullets"])

    def test_derivation_falls_back_to_lead_when_all_junk(self):
        nodes = [{"digest": {"bullets": [], "assumed_prior": "", "contribution": "x", "cross_refs": []}}]
        d = conductor._digest_derivation(nodes, "the lead clause that is substantive")
        self.assertEqual(d["bullets"], ["the lead clause that is substantive"])

    def test_continuation_directive_discourages_formulaic_openers(self):
        # bug #1: 3 of 4 deliver nodes opened "That X matters more than it first appears to"
        node = {"role": "deliver", "contract": {"intent": "x", "finding_ids": []},
                "place": {"position": "3 of 5", "established_upstream": "the frame is already set upstream"}}
        p = conductor._writer_prompt(node, [], {"findings": [], "residuals": []}, "obj")
        self.assertIn("formulaic", p.lower())

    def test_opening_node_still_establishes_the_frame(self):
        node = {"role": "motivate", "contract": {"intent": "x", "finding_ids": []},
                "place": {"position": "1 of 5", "established_upstream": ""}}
        p = conductor._writer_prompt(node, [], {"findings": [], "residuals": []}, "obj")
        self.assertIn("opening node", p.lower())


if __name__ == "__main__":
    unittest.main()
