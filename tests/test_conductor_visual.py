"""The conductor emits visually-rich artefatos (D1-D4 / plan Steps 3-5), fixture-based.

The success criterion (the audit): `run_conductor` on a fixture seed enumerating EVERY type->format
trigger yields each trigger's matching block type with a SUBSTANTIVE payload; ZERO scaffold-prefixed
headings; and the strengthened `check_genus` is [] on the rich output but flags "visual-coverage" on
a flat-prose control of the same seed.

The model calls are INJECTED and OFFLINE/DETERMINISTIC: `_fake_writer` reads the finding-id in the
writer prompt and returns prose + ONE fenced json envelope {"title","blocks","digest"} with the
correct typed block; `_fake_conciliator` (a SEPARATE injected call) returns {"blocks":[...]}.
"""
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import conductor  # noqa: E402
import close  # noqa: E402


_OBJECTIVE = "spec the retrieval gate off the mined findings"


def _fixture_seed():
    """A seed whose findings each carry ONE type->format trigger (F1..F6). The finding `claim` is
    the anti-drop checklist; the fake writer keys its typed block off the finding-id position."""
    return {
        # Slice 3: each finding ROUTES to a form via its probe/claim; the writer follows that per-node
        # form guidance (de-collision spreads collisions across forms). NO finding routes to a chart —
        # the visual invariant makes chart/diagram Slice-4-only.
        "findings": [
            # F0 — surprise probe -> comparison-table
            {"claim": "the expected store ordering did not hold under load",
             "bears_on": "the throughput bet", "citation": "bench p.1", "probe": "surprise"},
            # F1 — contradiction probe -> comparison-table -> de-collides to diff-block
            {"claim": "the evidence undercuts the summary's own recall claim",
             "bears_on": "the strategy choice", "citation": "bench p.2", "probe": "contradiction"},
            # F2 — lineage probe -> derivation
            {"claim": "the blocking gate idea traces back to the close protocol",
             "bears_on": "the enforcement rail", "citation": "ADR-0012", "probe": "lineage"},
            # F3 — before/after claim -> diff-block -> de-collides to table
            {"claim": "the close gate was advisory before the rewrite and blocking after",
             "bears_on": "the gate rail", "citation": "audit D6", "probe": "relevance"},
            # F4 — an open boundary (prose; the writer's gap block is consolidated by reconcile)
            {"claim": "the live lag at 50 entities remains unmeasured",
             "bears_on": "the eviction rail", "citation": "open", "probe": "relevance"},
            # F5 — plain prose finding (no structured form owed)
            {"claim": "the read path dominates the write path in this workload",
             "bears_on": "the read:write bet", "citation": "bench p.3", "probe": "relevance"},
        ],
        "residuals": ["is the lag live at 50 entities?"],
        "enabled": True,
        "passthrough": False,
    }


# Slice 3: a SUBSTANTIVE block of the form the node's guidance asked for — the fake writer FOLLOWS
# its per-node target_form (like a real subagent), so whatever de-collision assigned, the writer
# emits it and it survives the form gate. None for prose-only / an unknown form.
def _block_for_form(form: str) -> dict | None:
    return {
        "metrics-grid": {"type": "metrics-grid", "items": [
            {"value": "42%", "label": "cost"}, {"value": "3x", "label": "throughput"}]},
        "comparison-table": {"type": "comparison-table", "headers": ["dim", "dense", "sparse"], "rows": [
            {"cells": ["cost", "high", "low"]}, {"cells": ["recall", "0.9", "0.7"]}]},
        "diff-block": {"type": "diff-block", "header": "advisory -> blocking", "lines": [
            {"type": "delete", "text": "the gate was advisory, computed and ignored"},
            {"type": "insert", "text": "the gate now bounces a flat spec through improve_fn"}]},
        "derivation": {"type": "derivation",
                       "bullets": ["type-only is payload-blind", "therefore read the payload"]},
        "table": {"type": "table", "headers": ["k", "v"], "rows": [["a", "1"], ["b", "2"]]},
        "gap-table": {"type": "gap-table", "gaps": [{"description": "an open thread on scale"}]},
    }.get(form)


def _form_in_prompt(prompt: str) -> str:
    """Recover the per-node form the writer guidance asked for (Slice 3) — a real writer reads this
    same line and emits exactly that block. '' when the node is prose-only."""
    m = re.search(r"owes ONE structured block: a ([\w-]+)", prompt)
    return m.group(1) if m else ""


def _finding_id_in_prompt(prompt: str, seed: dict) -> str:
    """Recover which finding the writer prompt is ASSIGNED by matching its claim text against the
    anti-drop CHECKLIST section only (the assigned claims, one per line). The whole-outline map
    lists EVERY node's intent (so every finding's claim appears there) — keying off the checklist,
    not the whole prompt, is what makes a per-node fake deterministic."""
    # the checklist is the block between "do not drop the tail):" and "Open tensions you may surface:".
    m = re.search(r"do not drop the tail\):\n(.*?)\n\nOpen tensions", prompt, re.DOTALL)
    checklist = m.group(1) if m else ""
    for i, f in enumerate(seed.get("findings") or []):
        claim = f.get("claim", "")
        if claim and claim in checklist:
            return conductor.finding_id(i)
    return ""


def _digest(fid: str) -> dict:
    return {"bullets": [f"key point of {fid}"],
            "assumed_prior": f"upstream set the frame for {fid}",
            "contribution": f"this node develops finding {fid} to plenitude with its visual",
            "cross_refs": [f"leans on the seed for {fid}"]}


def _make_fake_writer(seed: dict):
    """A deterministic OFFLINE complete_fn: reads the finding-id in the writer prompt and returns
    prose + ONE fenced json envelope {"title","blocks","digest"} carrying the correct typed block.
    For a node with no assigned finding (motivate / change-the-course) it returns prose + a
    paragraph block (and still echoes any claim text present so the contract gate is satisfied)."""
    def complete_fn(prompt: str) -> str:
        fid = _finding_id_in_prompt(prompt, seed)
        # echo every claim line present so contract_gate (verbatim claim echo) is satisfied
        claim_echo = " ".join(
            f.get("claim", "") for f in (seed.get("findings") or [])
            if f.get("claim") and f.get("claim") in prompt)
        prose = (f"Because the evidence shows it, it follows that {claim_echo} "
                 "— what i don't know: the open question of scale; this builds on prior work.")
        if fid:
            claim = conductor._finding_by_id(seed, fid).get("claim", "")
            blocks = [{"type": "paragraph", "text": prose}]
            fb = _block_for_form(_form_in_prompt(prompt))   # follow the per-node form guidance
            if fb:
                blocks.append(fb)
            digest = _digest(fid)
            title = f"How {claim[:40]}"
        else:
            blocks = [{"type": "paragraph", "text": prose}]
            digest = {"bullets": ["frames the arc"], "assumed_prior": "",
                      "contribution": "frames the synthesis for a busy operator",
                      "cross_refs": []}
            title = "Why this synthesis matters now"
        envelope = {"title": title, "blocks": blocks, "digest": digest}
        return prose + "\n\n```json\n" + json.dumps(envelope) + "\n```"
    return complete_fn


def _make_recording_conciliator():
    """A SEPARATE injected conciliator call: records the prompt it saw and returns a fenced
    {"blocks":[...]} synthesis spec carrying a real typed block (a comparison-table) so the
    conciliator's own output is visually rich."""
    rec = {"prompts": []}

    def conciliate_fn(prompt: str) -> str:
        rec["prompts"].append(prompt)
        spec = {"blocks": [
            {"type": "paragraph",
             "text": "The single argument: the gate must bite on substance. Because the evidence "
                     "shows it, it follows; what i don't know is the live lag; this builds on prior."},
            {"type": "comparison-table", "headers": ["dim", "advisory", "blocking"], "rows": [
                {"cells": ["effect", "computed, ignored", "bounces the spec"]}]},
        ]}
        return "```json\n" + json.dumps(spec) + "\n```"
    conciliate_fn.rec = rec
    return conciliate_fn


def _fake_writer_hollow(prompt: str) -> str:
    """A writer that emits a HOLLOW metrics-grid (no value/label items) — it must be dropped by
    normalization and must NOT clear visual-coverage."""
    seed = _fixture_seed()
    claim_echo = " ".join(
        f.get("claim", "") for f in seed["findings"] if f.get("claim") and f.get("claim") in prompt)
    prose = (f"Because it follows that {claim_echo}; what i don't know is scale; builds on prior. "
             "Cost fell 42%, latency hit 30ms, throughput rose 3x.")  # dense numbers, no real visual
    envelope = {"title": "Hollow", "blocks": [
        {"type": "paragraph", "text": prose},
        {"type": "metrics-grid", "items": []}],  # hollow
        "digest": {"bullets": ["x"], "assumed_prior": "", "contribution": "develops it",
                   "cross_refs": []}}
    return prose + "\n\n```json\n" + json.dumps(envelope) + "\n```"


def _fake_flat(prompt: str) -> str:
    """A flat-prose control: numeric-dense prose, NO typed blocks at all (the conductor's actual
    failure mode). The strengthened gate must FLAG this."""
    seed = _fixture_seed()
    claim_echo = " ".join(
        f.get("claim", "") for f in seed["findings"] if f.get("claim") and f.get("claim") in prompt)
    prose = (f"Because it follows that {claim_echo}; what i don't know is scale; builds on prior. "
             "Cost fell 42%, latency dropped to 30ms, and throughput rose 3x across the corpus.")
    digest = {"bullets": ["flat"], "assumed_prior": "", "contribution": "states it flatly",
              "cross_refs": []}
    envelope = {"title": "Flat", "blocks": [{"type": "paragraph", "text": prose}], "digest": digest}
    return prose + "\n\n```json\n" + json.dumps(envelope) + "\n```"


def _flat_conciliator(prompt: str) -> str:
    """A flat conciliator — numeric-dense prose, no blocks."""
    return ("```json\n" + json.dumps({"blocks": [
        {"type": "paragraph",
         "text": "Cost fell 42%, latency dropped to 30ms, throughput rose 3x; because it follows, "
                 "what i don't know is the lag, this builds on prior work."}]}) + "\n```")


def _block_types(spec: dict) -> set:
    types = set()
    for section in spec.get("sections", []):
        for b in section.get("blocks", []):
            types.add(b.get("type"))
    return types


def _all_blocks(spec: dict) -> list:
    return [b for s in spec.get("sections", []) for b in s.get("blocks", [])]


def _envelope(spec: dict) -> dict:
    """Wrap a content spec in the producer's minimal genus envelope (mirrors conductor._genus_violations)."""
    return {"content": spec, "intent": _OBJECTIVE,
            "cites": [{"ref": "(probe)", "kind": "mundo", "snippet": "the external frame"}],
            "proposes": [{"body": _OBJECTIVE, "kind": "thread"}],
            "distills": ["cluster:conductor"]}


class PerTriggerBlockPresent(unittest.TestCase):
    def setUp(self):
        self.seed = _fixture_seed()
        self.result = conductor.run_conductor(
            self.seed, _OBJECTIVE, _make_fake_writer(self.seed),
            is_enabled=True, conciliate_fn=_make_recording_conciliator())
        self.deep = self.result["deep_spec"]

    def test_forms_varied_and_no_drawn_visual(self):
        # Slice 3: findings route to DISTINCT forms (de-collision) and the writer follows guidance,
        # so the report is structurally VARIED — and the visual invariant holds: NO chart/diagram
        # appears per-node (those are Slice-4-only, grounded). The consolidated gap-table (the
        # boundary) and the digest derivation are always present.
        types = _block_types(self.deep)
        self.assertNotIn("chart", types, "visual invariant: no per-node chart")
        self.assertNotIn("diagram", types, "visual invariant: no per-node diagram")
        self.assertIn("gap-table", types, "the consolidated boundary must be present")
        self.assertIn("derivation", types, "the digest derivation move must be present")
        structured = types - {"paragraph", "callout", "list"}
        self.assertGreaterEqual(len(structured), 3,
                                f"the report must be structurally varied, got {structured}")

    def test_diversity_gate_passes_on_varied_report(self):
        # run_conductor scores only the authored node sections; the varied fixture must clear it.
        self.assertEqual(self.result["diversity"]["violations"], [],
                         "the varied report must clear the structural diversity gate")

    def test_blocks_substantive(self):
        for b in _all_blocks(self.deep):
            t = b.get("type")
            if t == "metrics-grid":
                items = b.get("items") or b.get("metrics") or []
                self.assertTrue(items, "metrics-grid must carry items")
                for it in items:
                    self.assertIn("value", it)
                    self.assertIn("label", it)
            elif t == "comparison-table":
                self.assertTrue(any(r.get("cells") for r in b.get("rows", [])),
                                "comparison-table must carry a row with cells")
            elif t == "diff-block":
                self.assertTrue(any(ln.get("text") for ln in b.get("lines", [])),
                                "diff-block must carry a line with text")
            elif t == "chart":
                self.assertTrue(b.get("data"), "chart must carry data")

    def test_no_scaffold_headings(self):
        scaffold = re.compile(r"^(Motivate|Deliver|Change-the-course)\b")
        for section in self.deep.get("sections", []):
            title = section.get("title") or ""
            self.assertIsNone(scaffold.match(title),
                              f"section title leaks the scaffold prefix: {title!r}")
            self.assertNotIn("develop the finding to plenitude", title)

    def test_gate_passes_rich(self):
        self.assertEqual(close.check_genus(_envelope(self.deep)), [])


class GateFlagsFlat(unittest.TestCase):
    def test_flat_run_flags_visual_coverage(self):
        seed = _fixture_seed()
        result = conductor.run_conductor(
            seed, _OBJECTIVE, _fake_flat, is_enabled=True, conciliate_fn=_flat_conciliator)
        violations = close.check_genus(_envelope(result["deep_spec"]))
        self.assertIn("visual-coverage", violations,
                      "a flat-prose conductor spec must be flagged by the strengthened gate")


class ConciliatorSeesDigests(unittest.TestCase):
    def test_conciliator_prompt_carries_digest_contributions(self):
        seed = _fixture_seed()
        conc = _make_recording_conciliator()
        conductor.run_conductor(seed, _OBJECTIVE, _make_fake_writer(seed),
                                is_enabled=True, conciliate_fn=conc)
        self.assertTrue(conc.rec["prompts"], "the conciliator must have been called")
        prompt = conc.rec["prompts"][-1]
        # the writers' digest CONTRIBUTIONS reach the conciliator (finding 1: nested digest parsed)
        self.assertIn("develops finding f0 to plenitude", prompt)
        self.assertIn("develops finding f5 to plenitude", prompt)
        # and NOT the scaffold contract.intent
        self.assertNotIn("develop the finding to plenitude", prompt)


class HollowBlockDropped(unittest.TestCase):
    def test_hollow_metrics_grid_dropped_and_does_not_clear_coverage(self):
        seed = _fixture_seed()
        result = conductor.run_conductor(
            seed, _OBJECTIVE, _fake_writer_hollow, is_enabled=True,
            conciliate_fn=_make_recording_conciliator())
        deep = result["deep_spec"]
        # the hollow metrics-grid must be dropped by normalization — no empty-items grid survives
        for b in _all_blocks(deep):
            if b.get("type") == "metrics-grid":
                self.assertTrue(b.get("items") or b.get("metrics"),
                                "a hollow (empty-items) metrics-grid must be dropped")
        # and the numeric-dense prose with no real visual must be flagged
        self.assertIn("visual-coverage", close.check_genus(_envelope(deep)))


class WriterProsePreserved(unittest.TestCase):
    # Codex P2 (review r3): the writer wrote real prose before the fence, but the envelope's only
    # prose block is an EMPTY placeholder + a visual. The prose (the finding claim) must survive.
    def test_loose_prose_survives_empty_paragraph_placeholder(self):
        seed = _fixture_seed()
        node = conductor.author_outline(seed, _OBJECTIVE)[1]  # a deliver node
        raw = ('The acquisition cost rises with corpus size — the binding constraint.\n'
               '```json\n{"title":"Cost","blocks":['
               '{"type":"paragraph","text":""},'
               '{"type":"metrics-grid","items":[{"value":"3x","label":"cost"}]}],'
               '"digest":{"bullets":[],"assumed_prior":"","contribution":"c","cross_refs":[]}}\n```')
        filled = conductor.fill_node(node, seed, _OBJECTIVE, lambda _p: raw)
        texts = " ".join(b.get("text", "") for b in filled["blocks"] if isinstance(b, dict))
        self.assertIn("binding constraint", texts)
        self.assertIn("metrics-grid", {b.get("type") for b in filled["blocks"]})

    def test_json_only_envelope_does_not_render_raw_json(self):
        # writer returns ONLY a fenced envelope (no loose prose) whose blocks are non-prose — the
        # node must carry the visual, never the raw JSON as a paragraph (Codex P2, review r5).
        seed = _fixture_seed()
        node = conductor.author_outline(seed, _OBJECTIVE)[1]
        raw = ('```json\n{"title":"T","blocks":[{"type":"metrics-grid","items":['
               '{"value":"3x","label":"cost"}]}],"digest":{}}\n```')
        filled = conductor.fill_node(node, seed, _OBJECTIVE, lambda _p: raw)
        texts = " ".join(b.get("text", "") for b in filled["blocks"] if isinstance(b, dict))
        self.assertNotIn("json", texts.lower())
        self.assertIn("metrics-grid", {b.get("type") for b in filled["blocks"]})


class NodeTextExcludesChrome(unittest.TestCase):
    # Codex P2 (review r6): a claim placed only in block chrome (title/header) must NOT count toward
    # contract discharge; nested payload (prose, bullets, metric labels, cells) must.
    def test_chrome_excluded_payload_counted(self):
        node = {"blocks": [
            {"type": "metrics-grid", "title": "CHROMECLAIM",
             "items": [{"value": "3x", "label": "PAYLOADLABEL"}]},
            {"type": "comparison-table", "header": "ALSO_CHROME",
             "rows": [{"cells": ["CELLPAYLOAD", "x"], "classes": ["CSSCLAIM-spoof"]}]},
            {"type": "paragraph", "text": "PROSEPAYLOAD here"},
        ]}
        txt = conductor._node_text(node)
        self.assertNotIn("CHROMECLAIM", txt)       # block title is chrome
        self.assertNotIn("ALSO_CHROME", txt)       # block header is chrome
        self.assertNotIn("CSSCLAIM-spoof", txt)    # nested CSS classes are styling, not content
        self.assertIn("PAYLOADLABEL", txt)         # nested metric label is data
        self.assertIn("CELLPAYLOAD", txt)          # nested table cell is data
        self.assertIn("PROSEPAYLOAD", txt)         # prose is data


class SyntheticEmptyEnvelopeFlagged(unittest.TestCase):
    # Codex P2 (review r4): a conciliator returning ONLY a fenced envelope whose blocks all drop
    # must flag "synthetic is empty", not render the raw JSON as prose.
    def test_hollow_envelope_flags_synthetic_empty(self):
        seed = _fixture_seed()
        nodes = conductor.author_outline(seed, _OBJECTIVE)
        filled = [conductor.fill_node(n, seed, _OBJECTIVE, _make_fake_writer(seed)) for n in nodes]
        conc = lambda _p: '```json\n{"blocks":[{"type":"metrics-grid","items":[{}]}]}\n```'
        _deep, _syn, shape = conductor.conciliate(filled, nodes, _OBJECTIVE, conc, seed=seed)
        self.assertIn("synthetic is empty", shape)


if __name__ == "__main__":
    unittest.main()
