"""Story S13 — the producer-skills (report / map / plan).

The producer roster is open; these three are the producer-skills the beat round-robins
(roster = ["report", "map", "plan"], agreed with S12). Each is a THIN specialization
(ADR-0012): it does not write its own loop. It references the shared scaffold
(`skills/_shared/scaffold.md`, the loop1/loop2 role-slots) and the shared pipeline
(`skills/_shared/pipeline.md`, the close at exit), declares its own SLOT MAPPING
(what its gather-grounding / converge / diverge are) and its visual idiom, draws blocks
from the canonical palette (tools/render.py) and publishes through the close
(tools/publisher.py) — never an inline eventlog.publish_artefato snippet.

The load-bearing invariants this test pins:
  * each producer SKILL.md exists, references the scaffold + the pipeline (the shared docs)
    and the publisher (tools/publisher.py);
  * each declares a slot mapping (mentions gather-grounding / converge / diverge or the
    slot idea), so report-specifics live HERE, not welded into the scaffold;
  * report/SKILL.md NO LONGER mandates a fixed section order — sections are FREE (the
    welded "first / penultimate / last" section phrases are forbidden);
  * map declares a visual-by-nature idiom (diagram / graph) so the visualization dim never
    false-fails it; plan declares a next-steps-grid / flow idiom;
  * the rename is honored everywhere: "evidence", never "insumos".

Grep-based, case-insensitive: the docs are prose, so the test reads them and asserts
presence/absence of the load-bearing tokens.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"

# The open producer roster the beat round-robins (agreed with S12). Expanded to the full
# TEXT roster for the genus-wide rito rollout (docs/rito-runtime.md §Producer adoption):
# every prose Artefato exits through the same rite. `prototype` (interactive single-file JS)
# is NOT here — its artefato does not fit the rite's pinned markdown renderer (see the
# "Interactive producers" open decision in docs/rito-runtime.md) and stays on the legacy close.
PRODUCERS = ("report", "map", "plan", "research", "discovery")

# The rito split (docs/rito-runtime.md): the report exemplar led; the genus-wide rollout wired
# every TEXT producer through the rito runtime (tools/rito.py — the experiment's rite as the
# production path; publication inside the rite, form pinned to the approved markdown renderer).
# "o edge deve soar o mesmo across artefatos". Legacy is now empty for the text roster — the
# interactive producers (prototype, lazer) stay legacy but are pinned elsewhere.
RITO_PRODUCERS = ("report", "map", "plan", "research", "discovery")
LEGACY_PRODUCERS = tuple(p for p in PRODUCERS if p not in RITO_PRODUCERS)

# The shared contracts every producer conforms to.
SCAFFOLD_REF = "scaffold"      # skills/_shared/scaffold.md (loop1/loop2 role-slots)
PIPELINE_REF = "pipeline"      # skills/_shared/pipeline.md (the close at exit)
PUBLISHER_REF = "tools/publisher.py"  # publish through the close, not an inline snippet

# The ENFORCED close path: publish only ever happens via close.run_close (it runs the genus
# + both blind reviewers, then publishes on pass with the minted proof). A bare
# `publisher.publish(` call is now the FORBIDDEN back door — publish_fn refuses without the
# proof only run_close mints, so a direct publisher.publish raises.
ENFORCED_CLOSE_REF = "close.run_close"
FORBIDDEN_BARE_PUBLISH = "publisher.publish("

# The slot idea a producer's mapping must declare (role-defined slots from the scaffold).
SLOT_TOKENS = ("gather-grounding", "converge", "diverge")

# The fixed-section mandates report/SKILL.md must NO LONGER carry — sections are FREE.
# (Only positive welds: a NAMED/ORDERED section requirement. The de-welding prose may
# still say "never mandatory sections" / "sections are FREE" — that is the negation, not
# a mandate, so we forbid only the order/position welds, never the bare word "section".)
FORBIDDEN_SECTION_MANDATES = (
    "first section",
    "primeira seção",
    "penultimate",
    "section (first)",
    "glossário (last)",
    "glossary (last)",
    "fixed section order",
    "in this order",
    "section order",
)


def _path(producer):
    return SKILLS / producer / "SKILL.md"


class ProducersFillSlotsAndExitThroughClose(unittest.TestCase):
    def setUp(self):
        self.texts = {}
        for p in PRODUCERS:
            path = _path(p)
            self.assertTrue(path.exists(), f"missing producer skill: {path}")
            self.texts[p] = path.read_text(encoding="utf-8").lower()

    def test_each_producer_references_the_shared_contracts(self):
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn(SCAFFOLD_REF, t, f"{p} does not reference the shared scaffold")
            self.assertIn(PIPELINE_REF, t, f"{p} does not reference the shared pipeline")

    def test_each_producer_publishes_through_the_publisher(self):
        for p in LEGACY_PRODUCERS:
            self.assertIn(PUBLISHER_REF, self.texts[p],
                          f"{p} does not publish via {PUBLISHER_REF}")
        for p in RITO_PRODUCERS:
            self.assertIn("tools/rito.py", self.texts[p],
                          f"{p} does not exit through the rito runtime (tools/rito.py)")

    def test_each_producer_does_not_inline_publish_artefato(self):
        # publish through the close, NOT an inline eventlog.publish_artefato snippet.
        for p in PRODUCERS:
            self.assertNotIn("eventlog.publish_artefato", self.texts[p],
                             f"{p} inlines an eventlog.publish_artefato snippet")

    def test_each_producer_routes_through_the_enforced_close(self):
        # LEGACY producers: publish happens ONLY via close.run_close (it mints the
        # passing-review proof publisher.publish requires). RITO producers route through
        # rito.run_rito — the rite IS the enforced path (publication inside it).
        for p in LEGACY_PRODUCERS:
            self.assertIn(ENFORCED_CLOSE_REF, self.texts[p].replace(" ", ""),
                          f"{p} does not route through the enforced close ({ENFORCED_CLOSE_REF})")
        for p in RITO_PRODUCERS:
            self.assertIn("rito.run_rito", self.texts[p].replace(" ", ""),
                          f"{p} does not route through the rito runtime (rito.run_rito)")
            self.assertNotIn("close.run_close(", self.texts[p].replace(" ", ""),
                             f"{p} still shows a close.run_close(...) call — the rito replaced "
                             "that exit (cycle-2 regression guard)")

    def test_no_producer_shows_a_bare_publisher_publish_call(self):
        # a direct publisher.publish(...) now RAISES (no passing-review proof) — the skill
        # must never show that forbidden back door; it publishes via close.run_close.
        for p in PRODUCERS:
            self.assertNotIn(FORBIDDEN_BARE_PUBLISH, self.texts[p].replace(" ", ""),
                             f"{p} shows a forbidden bare publisher.publish( call")

    def test_each_producer_declares_a_slot_mapping(self):
        # mentions the slot idea (gather-grounding / converge / diverge or "slot").
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn("slot", t, f"{p} declares no slot mapping")
            self.assertTrue(any(s in t for s in SLOT_TOKENS),
                            f"{p} names none of the role slots {SLOT_TOKENS}")

    def test_each_producer_draws_from_the_canonical_palette(self):
        # LEGACY: blocks come from the one palette (tools/render.py), not freeform HTML.
        # RITO: the authoring format is Markdown, rendered by the PINNED approved renderer.
        for p in LEGACY_PRODUCERS:
            self.assertIn("tools/render.py", self.texts[p],
                          f"{p} does not draw blocks from the canonical palette")
        for p in RITO_PRODUCERS:
            self.assertIn("renderer_id", self.texts[p],
                          f"{p} does not name the pinned renderer (render.RENDERER_ID)")
            self.assertIn("markdown", self.texts[p],
                          f"{p} does not declare Markdown as the rite's authoring format")

    def test_report_no_longer_mandates_a_fixed_section_order(self):
        # sections are FREE — the welded section-order mandate is gone.
        report = self.texts["report"]
        for mandate in FORBIDDEN_SECTION_MANDATES:
            self.assertNotIn(mandate, report,
                             f"report still mandates a fixed section: {mandate!r}")

    def test_map_declares_a_visual_by_nature_idiom(self):
        # map is visual by nature (so the visualization dim never false-fails it).
        m = self.texts["map"]
        self.assertTrue("diagram" in m or "graph" in m,
                        "map declares no visual idiom (diagram/graph)")

    def test_plan_declares_a_next_steps_grid_or_flow_idiom(self):
        plan = self.texts["plan"]
        self.assertTrue("next-steps-grid" in plan or "flow" in plan,
                        "plan declares no next-steps-grid / flow idiom")

    def test_uses_evidence_not_insumos_in_every_producer(self):
        for p in PRODUCERS:
            t = self.texts[p]
            self.assertIn("evidence", t, f"{p} does not use 'evidence'")
            self.assertNotIn("insumos", t, f"{p} still uses 'insumos'")


# The proof is bound to a sha256 digest of the EXACT publish payload (close.proof_digest):
# slug + spec(content) + intent + cites + proposes + distills + skill. run_close mints the
# digest from the `artefato` dict it is handed (artefato.get(field) per field); verify_proof
# (at the publish seam) recomputes it from what is actually published. So the `artefato` dict
# the snippet passes to run_close MUST carry EVERY proof-bound field — including `skill` and
# `distills` — or the minted digest is over None/None while the publisher verifies the real
# values → mismatch → publish raises. And the publish_fn must publish FROM its `art` argument
# (read the fields off `art`), not from separately-captured locals, so the published payload
# is provably the one the proof was minted over. S2 (E1b): `dispatch_id` joined the bound set —
# same class as slug (persisted field = digested field), read from the wake's DISPATCH_ID line.
# `lineage` has been digest-bound since Cortex-v1 brick-1 but was missing from this helper set
# (pre-existing test gap, closed at the S2 codex gate).
PROOF_BOUND_ARTEFATO_FIELDS = ("skill", "distills", "slug", "intent", "cites", "proposes",
                               "dispatch_id", "lineage")


class ProducerCloseSnippetMintsOverPublishPayload(unittest.TestCase):
    """The producer close snippet must mint the proof over the EXACT payload it publishes:
    every proof-bound field is in the `artefato` dict run_close digests, and the publish_fn
    reads from its `art` argument (not separately-captured values)."""

    def setUp(self):
        # raw (case-preserving) text — we assert on the literal snippet code, not prose.
        # RITO producers carry no run_close snippet (publication rides inside the rite).
        self.texts = {p: _path(p).read_text(encoding="utf-8") for p in LEGACY_PRODUCERS}

    def _artefato_literal(self, text):
        """Return the `artefato={...}` dict literal passed to run_close (the snippet builds it
        once as a name, then hands it to close.run_close)."""
        marker = "artefato={"
        start = text.find(marker)
        self.assertNotEqual(start, -1, "no artefato={...} literal in snippet")
        # match to the closing brace of the literal
        i = start + len(marker)
        depth = 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        return text[start:i]

    def test_artefato_carries_every_proof_bound_field(self):
        # run_close mints from artefato.get(field); the dict must carry all proof-bound fields
        # (skill, distills, slug, intent, content, cites, proposes) so the mint digest == the
        # verified digest. `content` is the artefato dict's name for the digest's `spec`.
        for p in LEGACY_PRODUCERS:
            lit = self._artefato_literal(self.texts[p])
            for field in ("skill", "distills", "slug", "intent", "content", "cites", "proposes",
                          "dispatch_id", "lineage"):
                self.assertIn(f"'{field}'", lit,
                              f"{p}'s run_close artefato omits proof-bound field {field!r} "
                              f"(minted digest would not bind to the publish payload)")

    def test_publish_fn_reads_payload_from_its_art_argument(self):
        # the publish_fn must publish FROM `art` (its received artefato), reading the
        # proof-bound fields off it — not from separately-captured locals — so the published
        # payload is provably the one the proof was minted over.
        for p in LEGACY_PRODUCERS:
            t = self.texts[p]
            for field in PROOF_BOUND_ARTEFATO_FIELDS:
                self.assertIn(f"art['{field}']", t,
                              f"{p}'s publish_fn does not read {field!r} off its `art` "
                              f"argument (must publish from the minted artefato)")
            # the proof rides as verdict=
            self.assertIn("verdict=proof", t.replace(" ", ""),
                          f"{p}'s publish_fn does not pass verdict=proof")


class ProducersWireRealReProduction(unittest.TestCase):
    """#30 — the rich-rite gate must FORCE depth, not only hard-fail. The producer close snippet
    must wire `improve_fn` into `close.run_close` (run_close already loops IMPROVE_ROUNDS=2): so a
    genus/reviewer strike (incl. a rich-rite floor violation) re-PRODUCES a richer draft from the
    feedback, rather than dead-ending in a hard-fail. A `produce_fn` that just returns the static
    artefato is no longer enough on its own."""

    def setUp(self):
        # RITO producers have no run_close improve loop — the rite's own stages revise.
        self.texts = {p: _path(p).read_text(encoding="utf-8") for p in LEGACY_PRODUCERS}

    def test_each_producer_wires_improve_fn(self):
        for p in LEGACY_PRODUCERS:
            self.assertIn("improve_fn", self.texts[p].replace(" ", ""),
                          f"{p} does not wire improve_fn into run_close (a strike would only "
                          "hard-fail, never re-produce richer — #30)")

    def test_each_producer_improve_fn_takes_feedback(self):
        # improve_fn(artefato, feedback) — run_close hands it the reviewers' rationales+strikes,
        # which it uses to REVISE the draft. The signature must accept the feedback.
        for p in LEGACY_PRODUCERS:
            t = self.texts[p].replace(" ", "")
            self.assertTrue("improve_fn=lambda" in t or "defimprove_fn" in t,
                            f"{p}'s improve_fn is not defined to receive the feedback")
            self.assertIn("feedback", self.texts[p].lower(),
                          f"{p} does not mention the feedback the improve_fn revises from")


class ReportExitsThroughTheRito(unittest.TestCase):
    """The rito exemplar (docs/rito-runtime.md): report's way out is the rite runtime — the
    whole causal execution as code, publication inside it, form pinned. Generalized to EVERY
    rito producer (genus-wide rollout): each carries the same load-bearing tokens so none can
    silently drift back to the legacy exit (cycle-1/2 guard) — "o edge deve soar o mesmo"."""

    def setUp(self):
        self.texts = {p: _path(p).read_text(encoding="utf-8") for p in RITO_PRODUCERS}

    def test_report_routes_through_run_rito(self):
        for p, text in self.texts.items():
            self.assertIn("rito.run_rito", text.replace(" ", ""),
                          f"{p} does not route through rito.run_rito")

    def test_report_names_the_detector_command(self):
        for p, text in self.texts.items():
            self.assertIn("tools/rito.py verify", text,
                          f"{p} does not name the detector command")

    def test_report_carries_the_product_spine_via_publish_meta(self):
        for p, t in self.texts.items():
            self.assertIn("publish_meta", t, f"{p} omits publish_meta")
            for field in ("proposes", "distills", "cites", "lineage", "bears_on", "para",
                          "reports_on"):
                self.assertIn(f"'{field}'", t,
                              f"{p}'s publish_meta omits {field!r} — the rite replaces the "
                              "path, not the ontology")

    def test_report_shows_no_legacy_close_snippet(self):
        for p, text in self.texts.items():
            t = text.replace(" ", "")
            self.assertNotIn("close.run_close(", t,
                             f"{p} still shows a close.run_close( call")
            self.assertNotIn("artefato={", t, f"{p} still builds a legacy artefato dict")
            self.assertNotIn("publish_fn=lambdaart,proof", t,
                             f"{p} still shows the legacy publish_fn lambda")

    def test_report_preserves_the_blind_readable_first_draft(self):
        for p, text in self.texts.items():
            self.assertIn("blind", text.lower(), f"{p} loses the blind-readable draft note")
            self.assertIn("first authorial draft", text.lower(),
                          f"{p} does not name the sealed first authorial draft")


class PipelineDocumentsTheReProductionWiring(unittest.TestCase):
    """#30 — the shared pipeline must document that the producer wires `improve_fn` so the close's
    improve stage (IMPROVE_ROUNDS) actually re-produces from feedback — the gate forces depth, not
    only a hard-fail. Pin the load-bearing tokens so the wiring cannot go dormant in prose."""

    def setUp(self):
        self.text = (REPO / "skills" / "_shared" / "pipeline.md").read_text(encoding="utf-8").lower()

    def test_pipeline_states_the_producer_wires_improve_fn(self):
        self.assertIn("improve_fn", self.text)

    def test_pipeline_ties_re_production_to_the_gate_forcing_depth(self):
        # the WHY: without the wiring a gate violation only hard-fails; with it, the close
        # re-produces a richer draft. The rich-rite floor is named as a strike source.
        self.assertIn("rich-rite", self.text)
        self.assertTrue("hard-fail" in self.text or "hard fail" in self.text,
                        "pipeline must contrast re-production against a bare hard-fail")


class PedagogicalRewriteIntegration(unittest.TestCase):
    """exp-feynman-pedagogico (operator-ratified: "pode integrar no genotipo"): the winning arm
    was a rewrite in the PEDAGOGUE's Feynman-Lectures voice, ONE review round that reaches for
    NEW grounding, length EMERGENT (no target), and the table-wall killed (prose carries the
    argument; a table only for a genuine A-vs-B comparison). This pins the genotype change on the
    two exemplar producers (report + research), across BOTH prompt-carriers: the authoring prose
    sections AND the rito prompts-dict placeholder strings."""

    EXEMPLARS = ("report", "research")

    def setUp(self):
        self.texts = {p: _path(p).read_text(encoding="utf-8").lower() for p in self.EXEMPLARS}

    def test_authoring_carries_the_feynman_lectures_pedagogical_voice(self):
        # the PEDAGOGUE's Feynman (build from the concrete, motivate WHY before formalism, one
        # vivid handle, address the reader, anticipate confusion, explain-don't-label).
        for p in self.EXEMPLARS:
            t = self.texts[p]
            self.assertIn("feynman lectures", t,
                          f"{p} does not name the Feynman-Lectures pedagogical voice")
            self.assertTrue("motivate why" in t or "why before" in t,
                            f"{p} does not carry motivate-WHY-before-formalism")
            self.assertIn("vivid handle", t, f"{p} does not carry the one-vivid-handle move")
            self.assertTrue("explain" in t and "label" in t,
                            f"{p} does not carry explain-don't-label")

    def test_length_is_emergent_no_word_target(self):
        # length EMERGENT — it grows because contextualization was added, never a word target.
        for p in self.EXEMPLARS:
            t = self.texts[p]
            self.assertIn("emergent", t, f"{p} does not declare length EMERGENT")
            self.assertNotIn("word count", t, f"{p} still names a word count target")
            self.assertNotIn("word target", t, f"{p} still names a word target")

    def test_table_wall_killed_prose_carries_the_argument(self):
        # kill the table-wall default: prose carries the argument; a table ONLY for a genuine
        # A-vs-B comparison (the winner went from 45 table-rows to 5).
        for p in self.EXEMPLARS:
            t = self.texts[p]
            self.assertTrue("prose carries the argument" in t or "prose carries" in t,
                            f"{p} does not say prose carries the argument")
            self.assertTrue("table-wall" in t or "table wall" in t,
                            f"{p} does not name the table-wall it must kill")

    def test_gap_critique_is_pedagogical(self):
        # gap_critique asks: where does this fail to TEACH? where is it cryptic / thin?
        for p in self.EXEMPLARS:
            t = self.texts[p]
            self.assertTrue("fail to teach" in t or "fails to teach" in t or "does not teach" in t,
                            f"{p}'s gap_critique is not a teaches-check")

    def test_grounding2_carries_new_grounding_reach_with_fidelity_guard(self):
        # grounding2 fetches NEW grounding (world/domain beyond G1) to fill the pedagogical gaps
        # — with the fidelity guard: FETCHED + cited, NEVER invented.
        for p in self.EXEMPLARS:
            t = self.texts[p]
            self.assertIn("new grounding", t,
                          f"{p}'s grounding2 does not carry the new-grounding reach")
            self.assertTrue("fetched" in t and ("cited" in t or "cite" in t),
                            f"{p}'s new-grounding reach lacks the fetched+cited fidelity guard")
            self.assertTrue("never invent" in t or "not invent" in t or "not fabricat" in t,
                            f"{p}'s new-grounding reach does not forbid inventing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
