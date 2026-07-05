"""briefing — the deterministic composer of Memento's tattoo (ADR-0009, issue capstone).

The agent has anterograde amnesia: it orients **entirely** from the briefing and trusts
nothing that isn't inscribed there. So the load-bearing lines (the curated Direction, what is
open / the next bet, the source yield, what it already did) are **deterministically inscribed
from the log** — only the Recap is synthesized fresh. These tests pin that composition on bare
`python3` (Tier-0, no graph), each from a throwaway temp log (CONTRACT C1 — never real state/).
"""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import eventlog  # noqa: E402
import briefing  # noqa: E402


def _complete_yaml(p):
    """A genotype agent.yaml with full identity + a valid declared source — the stage-(i) floor."""
    p.write_text(textwrap.dedent("""\
        name: ed
        mission: "Mentor to the edge-of-chaos PM."
        voice: "Direct, technical, skeptical."
        sources:
          - name: exa
            kind: api
            description: "Neural/semantic web + paper search."
        """))
    return p


def _yaml_with_ground_truth(p, documents):
    """An agent.yaml declaring `ground_truth.documents` pointing at the given paths (the per-install
    consequence whose CONTEXT.md glossaries are the briefing's glossary floor)."""
    docs = "\n".join(f"    - \"{d}\"" for d in documents)
    p.write_text(textwrap.dedent("""\
        name: ed
        ground_truth:
          inject_into_load: true
          documents:
        """) + docs + "\n")
    return p


def _genotype(memory, idiom=True, personality=True, method=True):
    """A throwaway genotype tree: memory/ docs + a state/idiom.md, fail-closed inputs the
    composer requires. Toggle a doc off to drive the fail-closed assertions."""
    memory.mkdir(parents=True, exist_ok=True)
    if personality:
        (memory / "personality.md").write_text("# Personality — ed\n\nAnalytical and skeptical.")
    if method:
        (memory / "method.md").write_text("# Feynman Method\n\nDerive before researching.")
    state = memory.parent / "state"
    state.mkdir(parents=True, exist_ok=True)
    if idiom:
        (state / "idiom.md").write_text("# Idiom\n\n**beat** — the work cycle.")
    return memory


class ObjectiveIsTheBriefingSpine(unittest.TestCase):
    """The grill's anchor surfaces as the briefing **spine** — a top section the agent orients from
    every dispatch, ABOVE Direction (the objective is what Direction is measured against). Inscribed
    from the log fold (objective_at); cursor-aware. No objective yet → an honest empty marker, never
    a crash (the briefing still composes on a fresh log)."""

    def test_objective_renders_as_a_top_section_above_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("ship durable steer before tuning the grill", log=log)
            eventlog.set_direction("a", "ship the briefing composer", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("ship durable steer before tuning the grill", text)
            self.assertLess(text.index("ship durable steer before tuning the grill"),
                            text.index("ship the briefing composer"))  # spine above Direction

    def test_objective_rationale_is_inscribed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_objective("revealed objective B",
                                   rationale="says mission A, behavior shows B", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("says mission A, behavior shows B", text)

    def test_no_objective_yet_renders_marker_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("no confirmed objective yet", text.lower())


class DirecionamentoReportInjectedAsMentoring(unittest.TestCase):
    """The rolling steer ("o direcionamento") is **injected** as the mentoring section, present every
    wake — the flesh on Direction's skeleton. Only the LATEST report shows (the present steer; the
    lineage is for the grill to read, not the briefing). Inscribed from the log fold (report_at);
    cursor-aware. No report yet → an honest marker (the briefing still composes on a fresh log)."""

    def test_latest_report_is_injected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.report_direction("the steer toward the objective, live", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("the steer toward the objective, live", text)

    def test_only_latest_report_shows_not_the_whole_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.report_direction("stale prior steer", log=log)
            eventlog.report_direction("the current live steer", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("the current live steer", text)
            self.assertNotIn("stale prior steer", text)

    def test_no_report_yet_renders_marker_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("no direcionamento report yet", text.lower())


class DirectionInscribedCuratedFirst(unittest.TestCase):
    """Section 1 (highest tattoo authority): the curated `set` tier is inscribed before the
    non-curated `proposed` tier; both bodies appear. None → "no direction set yet."""

    def test_set_appears_before_proposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.set_direction("a", "ship the briefing composer", log=log)
            eventlog.propose("b", "explore Tier-1 clusters", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("ship the briefing composer", text)
            self.assertIn("explore Tier-1 clusters", text)
            self.assertLess(text.index("ship the briefing composer"),
                            text.index("explore Tier-1 clusters"))

    def test_no_direction_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("no direction set yet", text.lower())


class ContinuityInscribesTheLatestKernel(unittest.TestCase):
    """Section 2 — the literal tattoo: a cold agent reads here what it was mid-doing. Derived from
    the *intent* (the why) of the most-recent corpus item — publish an artefato + kernel and the
    kernel's "what is open / next bet" must appear under the open/next-bet section."""

    def test_latest_kernel_intent_is_the_open_next_bet(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("recall-report", log=log)
            eventlog.kernel("recall-report",
                            "open: read-budget unnamed; bet: name it next beat", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("open / the next bet", text.lower())
            self.assertIn("open: read-budget unnamed; bet: name it next beat", text)

    def test_most_recent_kernel_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("older", log=log)
            eventlog.kernel("older", "old intent", log=log)
            eventlog._append_orphan_published_for_test("newer", log=log)
            eventlog.kernel("newer", "fresh intent — the live continuity", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("fresh intent — the live continuity", text)


class CorpusListsRecentStepsAndC3Debt(unittest.TestCase):
    """Section 3 — what I already did: recent Artefato slugs (+ their why), most-recent-first, so
    the agent builds rather than repeats. A kernel-less Artefato is surfaced as C3 debt (the gap is
    shown, not hidden) via artefatos_without_kernel."""

    def test_recent_slugs_most_recent_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("older-report", log=log)
            eventlog.kernel("older-report", "why older", log=log)
            eventlog._append_orphan_published_for_test("newer-report", log=log)
            eventlog.kernel("newer-report", "why newer", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("older-report", text)
            self.assertIn("newer-report", text)
            self.assertLess(text.index("newer-report"), text.index("older-report"))

    def test_kernel_less_artefato_shows_as_c3_debt(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog._append_orphan_published_for_test("bare-report", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("bare-report", text)
            self.assertIn("C3 debt", text)


class SourceOrientationRendersYield(unittest.TestCase):
    """Section 4 — per-source yield (ref · kind · count · mean sim), highest yield first, from
    source_yield_at, layered ON the declared roster floor."""

    def test_renders_yield_highest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "github:abc", "atividade", 0.9, log=log)
            eventlog.source_signal("r", "mundo:arxiv", "mundo", 0.3, log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("github:abc", text)
            self.assertIn("mundo:arxiv", text)
            self.assertLess(text.index("github:abc"), text.index("mundo:arxiv"))  # higher yield first


class SourceRosterIsTheNeverBlankFloor(unittest.TestCase):
    """Slice 1 (ADR-0011): the source section renders the declared roster (← Source roadmap, seeded
    from agent.yaml) as the floor that is **never blank**, even with zero source.signal events. The
    old "no source signals yet" blank is the bug this fixes. Per-entry label: description→via→name."""

    def test_roster_floor_lists_entries_when_log_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            roster = [{"name": "exa", "kind": "api", "label": "exa"},
                      {"name": "github", "kind": "cli", "label": "github"}]
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", roster=roster)
            self.assertNotIn("no source signals yet", text.lower())
            self.assertIn("exa", text)
            self.assertIn("github", text)

    def test_source_roster_helper_reads_agent_yaml_and_native_source(self):
        roster = briefing.source_roster()
        names = [r["name"] for r in roster]
        self.assertIn("exa", names)        # from agent.yaml sources:
        self.assertIn("github", names)     # the cli source
        # the native Claude-sessions source is a constant floor entry, always present
        self.assertTrue(any("session" in r["name"].lower() for r in roster))

    def test_label_fallback_chain_description_then_via_then_name(self):
        roster = [{"name": "s1", "kind": "api", "label": "a transcript on the Drive"},  # description
                  {"name": "s2", "kind": "api", "label": "GET https://api…"},            # via
                  {"name": "s3", "kind": "api", "label": "s3"}]                           # bare name
        text = briefing.compose_briefing(log=Path("/nonexistent"), roster=roster)
        self.assertIn("a transcript on the Drive", text)
        self.assertIn("GET https://api", text)
        self.assertIn("s3", text)


class SourceCuratedStratumRendersAboveYield(unittest.TestCase):
    """Slice 2 (ADR-0011): the curated source stratum (← source.curated, the grill-distilled mentee
    opinion) renders ABOVE the non-curated yield, mirroring _section_direction (set over proposed).
    source.dropped removes it. Cursor-aware: a past cursor reconstructs the past stratum."""

    def test_curated_opinion_surfaces_above_the_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_signal("r", "exa", "mundo", 0.7, log=log)
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertIn("valued: recent-paper recall", text)
            # curated stratum is above the per-source yield line
            self.assertLess(text.index("valued: recent-paper recall"),
                            text.index("mean sim"))

    def test_dropped_removes_curated_from_briefing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            eventlog.source_curated("exa", "valued: recent-paper recall", log=log)
            eventlog.source_dropped("exa", "went cold", log=log)
            text = briefing.compose_briefing(log=log)
            self.assertNotIn("valued: recent-paper recall", text)

    def test_replay_to_past_cursor_shows_past_curated_stratum(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            c = eventlog.source_curated("exa", "valued: recall", log=log)   # seq 1
            eventlog.source_dropped("exa", "cold", log=log)                 # seq 2
            past = briefing.compose_briefing(log=log, seq=c["seq"])
            self.assertIn("valued: recall", past)
            now = briefing.compose_briefing(log=log)
            self.assertNotIn("valued: recall", now)


class ClustersDegradeOnTier0(unittest.TestCase):
    """Section 5 — Knowledge clusters (← graph). clusters=None (Tier-0, no graph runtime) → a clear
    degrade note, and it must NOT crash. clusters=[...] (Tier-1) → they render."""

    def test_none_renders_tier0_degrade_note_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=None)
            self.assertIn("Tier-0", text)
            self.assertIn("clusters unavailable", text.lower())

    def test_provided_clusters_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl",
                                             clusters=["recall budget", "source feedback"])
            self.assertIn("recall budget", text)
            self.assertIn("source feedback", text)

    def test_none_note_is_actionable_not_just_offline(self):
        # The degrade note must give the agent concrete checks (secrets-load, group, validate),
        # not just "graph offline" — so a claude -p dispatch stops mis-narrating an outage.
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=None)
            low = text.lower()
            self.assertIn("_secrets", text)
            self.assertIn("edge_group", low)
            self.assertIn("validate", low)


class RecapSlotOrInscribedText(unittest.TestCase):
    """Section 6 — Recap (← corpus, synthesized fresh). recap=None → a clear slot marker so the
    assemble LLM fills it; recap="..." → the text is inscribed verbatim."""

    def test_none_renders_slot_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", recap=None)
            self.assertIn("Recap synthesized at compose-time", text)

    def test_recap_text_is_inscribed(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl",
                recap="Your recall-report relates to the mentee's cursor refactor commit.")
            self.assertIn("Your recall-report relates to the mentee's cursor refactor commit.", text)


class BriefingIsBannered(unittest.TestCase):
    """The whole tattoo is banner-marked as generated orientation (house style — the projections
    in eventlog.py carry the same do-not-edit banner)."""

    def test_banner_marks_generated_orientation(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl")
            self.assertIn("generated", text.lower())


class FactsLegNavigatesTheCortex(unittest.TestCase):
    """Section 5 — the Facts leg now reads the AUTO-consolidated communities through the Módulo-2
    door (cortex.communities; the grill-curated curated_cluster rail is RETIRED — it never carried
    a cluster). Same degrade contract: None sem grupo / porta morta; [] = honest empty. Hermetic."""

    def test_no_group_degrades_to_none(self):
        import communities
        self.assertIsNone(communities.communities(None))
        self.assertIsNone(communities.communities(""))

    def test_unreachable_graph_degrades_to_none_without_crashing(self):
        import communities
        self.assertIsNone(communities.communities("any-group", uri="bolt://127.0.0.1:1"))

    def test_empty_clusters_is_a_distinct_state_from_outage(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=[])
            self.assertIn("no clusters yet", text.lower())
            self.assertNotIn("clusters unavailable", text.lower())

    def test_auto_fetch_with_no_group_renders_the_degrade_note(self):
        # the sentinel path resolves group→graph_clusters→None when no group is declared
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", group="")
            self.assertIn("clusters unavailable", text.lower())

    def test_provided_clusters_with_counts_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl",
                                             clusters=["Beat lifecycle (8)", "Dev practice (6)"])
            self.assertIn("Beat lifecycle (8)", text)
            self.assertIn("Dev practice (6)", text)

    def test_communities_render_with_summary_and_recency(self):
        # §5 = as communities auto-consolidadas: nome + tamanho + last_touched (navegação pelo
        # tempo) + sumário; rótulo tier-HIPÓTESE presente. (O shape velho label/entities morreu
        # com o rail curated_cluster — trilho órfão aposentado.)
        rows = [{"name": "Beat lifecycle", "summary": "o pulso e seus atos", "size": 8,
                 "last_touched": "2026-07-01T00:00:00Z"}]
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=rows)
            self.assertIn("**Beat lifecycle** (8 · tocado 2026-07-01", text)
            self.assertIn("o pulso e seus atos", text)
            self.assertIn("HIPÓTESE", text)


class HotCutoffTempoDivideDonos(unittest.TestCase):
    """hot_cutoff no compose_briefing (o gancho dormente ganha o caller): cluster tocado DENTRO
    da janela do quente DEFERE ('→ coberto no quente'); sem hot_cutoff, EXPANDE — o wake nunca
    conta a mesma história 2×."""

    ROWS = [{"name": "Agência", "summary": "o resumo frio do tema", "size": 4,
             "last_touched": "2026-07-05T01:00:00Z"},
            {"name": "Cortex", "summary": "consolidação antiga", "size": 6,
             "last_touched": "2026-06-20T00:00:00Z"}]

    def test_cluster_inside_hot_window_defers_to_quente(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=self.ROWS,
                                             hot_cutoff="2026-07-04T00:00:00Z")
            self.assertIn("coberto no quente", text)
            self.assertNotIn("o resumo frio do tema", text)   # o quente é o dono da história
            self.assertIn("consolidação antiga", text)        # fora da janela → expande normal

    def test_without_hot_cutoff_everything_expands(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=self.ROWS)
            self.assertIn("o resumo frio do tema", text)
            self.assertNotIn("coberto no quente", text)


class ImmutableTattoosAreTheBriefingHead(unittest.TestCase):
    """Personality + Method — the *initial tattoos* — are inscribed as the IMMUTABLE head of the
    briefing: loaded only at the edge's wake (the briefing), never the global CLAUDE.md system prompt
    (that would change Claude, not the edge). They are the **current** doctrine from memory/, not
    cursor-versioned — so they appear even on a fresh, empty log, ABOVE all the mutable state."""

    def test_immutable_head_carries_personality_and_method_above_the_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"  # empty log — the tattoos do not depend on state
            out = briefing.compose_briefing(log=log, clusters=None, roster=[])
        self.assertIn("Initial tattoos", out)
        self.assertIn("### Personality", out)
        self.assertIn("### Method", out)
        self.assertIn("Feynman Method", out)                                   # the method doctrine
        self.assertIn("distrust the rationality, not the person", out)         # the curated principle
        self.assertIn("## Idiom", out)                                         # the mentee's terms, required
        # the immutable head sits ABOVE the mutable state (the objective spine, Direction)
        self.assertLess(out.index("Initial tattoos"), out.index("## Objective"))
        self.assertLess(out.index("## Idiom"), out.index("## Objective"))      # idiom is identity-head

    def test_present_even_on_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = briefing.compose_briefing(log=Path(tmp) / "log.jsonl", clusters=None, roster=[])
        self.assertNotIn("_no doctrine inscribed yet._", out)  # docs exist → inscribed, not the marker


class GenotypeIdentityIsFailClosed(unittest.TestCase):
    """Gate root-cause #1 (audit): the identity head (Personality, Method, Idiom) is REQUIRED at
    ALL stages. A thin agent.yaml or an absent doctrine must FAIL LOUD (a detectable
    BriefingIdentityError `_validate` can catch) — never a silent blank that masks a lobotomy."""

    def test_thin_agent_yaml_makes_personality_tpl_fail_closed_not_blank(self):
        # personality.md.tpl references {{name}}/{{voice}}; a thin agent.yaml (no name/mission/voice)
        # must NOT silently substitute empty — it must raise the detectable failure.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("graph_group: x\n")  # thin: no name/mission/voice
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing._render_tpl("# Personality — {{name}}\n\n{{voice}}", agent_yaml=ay)

    def test_complete_agent_yaml_renders_the_tpl(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            out = briefing._render_tpl("# Personality — {{name}}\n\n{{voice}}", agent_yaml=ay)
            self.assertIn("ed", out)
            self.assertIn("Direct, technical, skeptical", out)

    def test_missing_personality_doc_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = _genotype(Path(tmp) / "memory", personality=False)
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing._section_tattoos(memory=mem, agent_yaml=ay)

    def test_missing_method_doc_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = _genotype(Path(tmp) / "memory", method=False)
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing._section_tattoos(memory=mem, agent_yaml=ay)

    def test_complete_genotype_renders_personality_and_method_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = _genotype(Path(tmp) / "memory")
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            out = briefing._section_tattoos(memory=mem, agent_yaml=ay)
            self.assertIn("### Personality", out)
            self.assertIn("### Method", out)
            self.assertIn("Analytical and skeptical", out)
            self.assertIn("Derive before researching", out)


class GlossaryFloorIsGroundTruthDocuments(unittest.TestCase):
    """Corrected source (operator clarification): the glossaries are NOT genotype — they are a
    CONSEQUENCE of `agent.yaml` `ground_truth.documents` (the mentee's projects' CONTEXT.md, the
    authored canon / Voz ground-truth). `_section_idiom` reads that declared list (paths, `~`-expanded),
    reads each EXISTING file, and INJECTS its content as the glossary floor — the real gap #26 names is
    INJECTION never done. The edge's curated `state/idiom.md` MAY layer on top (grilling-accreted)."""

    def test_ground_truth_documents_content_is_injected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "p1-CONTEXT.md"
            d2 = Path(tmp) / "p2-CONTEXT.md"
            d1.write_text("# Project One canon\n\n**alpha** — the first term.")
            d2.write_text("# Project Two canon\n\n**beta** — the second term.")
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", [str(d1), str(d2)])
            out = briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")
            self.assertIn("## Idiom", out)
            self.assertIn("the first term", out)   # project-one glossary injected
            self.assertIn("the second term", out)  # project-two glossary injected

    def test_compose_injects_ground_truth_glossaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "CONTEXT.md"
            d1.write_text("# Canon\n\n**confrontação** — the act that yields a decision.")
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", [str(d1)])
            mem = _genotype(Path(tmp) / "memory")
            out = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl", clusters=None, roster=[],
                agent_yaml=ay, memory=mem)
            self.assertIn("## Idiom", out)
            self.assertIn("the act that yields a decision", out)  # the glossary appears in the briefing

    def test_tilde_in_document_paths_is_expanded(self):
        # a `~/...` path must expand to $HOME, not be read literally
        import os
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            (home / "CONTEXT.md").write_text("# Canon\n\n**tilded** — read via ~ expansion.")
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", ["~/CONTEXT.md"])
            old = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                out = briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")
            finally:
                if old is not None:
                    os.environ["HOME"] = old
            self.assertIn("read via ~ expansion", out)

    def test_curated_idiom_layers_on_top_of_the_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1 = Path(tmp) / "CONTEXT.md"
            d1.write_text("# Canon\n\n**floor-term** — the ground-truth floor.")
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", [str(d1)])
            state = Path(tmp) / "state"
            state.mkdir()
            (state / "idiom.md").write_text("# Idiom\n\n**accreted-term** — grilled on top.")
            out = briefing._section_idiom(agent_yaml=ay, state_dir=state)
            self.assertIn("the ground-truth floor", out)   # the required floor
            self.assertIn("grilled on top", out)            # the curated layer accreted over it

    def test_some_present_some_missing_injects_present_and_notes_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            present = Path(tmp) / "present-CONTEXT.md"
            present.write_text("# Canon\n\n**present-term** — here.")
            missing = Path(tmp) / "missing-CONTEXT.md"  # never created
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", [str(present), str(missing)])
            out = briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")
            self.assertIn("present-term", out)              # the present one injected
            self.assertIn(str(missing), out)               # the missing one noted, never silently dropped

    def test_all_documents_absent_fails_closed(self):
        # ground_truth declared but EVERY document absent/empty → a real config failure, fail-closed
        with tempfile.TemporaryDirectory() as tmp:
            ay = _yaml_with_ground_truth(
                Path(tmp) / "agent.yaml",
                [str(Path(tmp) / "nope1.md"), str(Path(tmp) / "nope2.md")])
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")

    def test_all_documents_empty_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty-CONTEXT.md"
            empty.write_text("   \n\n")  # present but blank
            ay = _yaml_with_ground_truth(Path(tmp) / "agent.yaml", [str(empty)])
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")

    def test_no_ground_truth_declared_renders_honest_marker_no_crash(self):
        # an agent.yaml CONFIG gap (ground_truth not declared at all) — NOT a genotype lobotomy.
        # An honest marker, NOT a raise, NOT fake content.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\n")  # no ground_truth: block
            out = briefing._section_idiom(agent_yaml=ay, state_dir=Path(tmp) / "state")
            self.assertIn("## Idiom", out)
            self.assertIn("no ground_truth declared", out.lower())

    def test_no_ground_truth_does_not_raise_even_in_compose(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\n")
            mem = _genotype(Path(tmp) / "memory")
            out = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl", clusters=None, roster=[],
                agent_yaml=ay, memory=mem)
            self.assertIn("no ground_truth declared", out.lower())


class IdiomSectionIsRequired(unittest.TestCase):
    """Gate root-cause #1 (audit): the Idiom section (the mentee's terms ← ground_truth.documents
    glossaries) is a REQUIRED part of the compose list at ALL stages. Present + non-empty (the real
    install declares ground_truth), or it renders honestly — never absent, never a silent blank."""

    def test_idiom_section_is_in_the_compose_output(self):
        out = briefing.compose_briefing(log=Path("/nonexistent"), clusters=None, roster=[])
        self.assertIn("## Idiom", out)
        self.assertIn("beat", out)  # a live term from the real ground_truth CONTEXT.md glossary


class SourceRosterFailsClosedWithoutRealRoster(unittest.TestCase):
    """Gate root-cause #2 (audit): the source roster is the REAL declared roster — the native
    claude-sessions source is ADDITIVE, never a substitute. A missing agent.yaml, an empty
    `sources`, or a malformed entry (no name/kind/description) must FAIL LOUD, never yield a
    silently-non-empty section (the native floor masking a missing declared roster)."""

    def test_missing_agent_yaml_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=Path(tmp) / "agent.yaml")  # absent

    def test_empty_sources_list_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources: []\n")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_missing_sources_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\n")  # no sources: at all
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_malformed_source_entry_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources:\n  - {kind: api, description: d}\n")  # no name
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_whitespace_only_field_fails_closed(self):
        # a declared source whose name is whitespace-only is THIN, not a real roster — it must
        # FAIL LOUD naming the offending source, never render a blank/generic row to HEALTHY.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text('name: ed\nsources:\n  - name: " "\n    kind: api\n    description: d\n')
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_non_string_field_fails_closed(self):
        # a non-string truthy field (e.g. name: 123) passed the old truthiness check, rendering a
        # generic row — it must FAIL LOUD as a malformed (non-string) field.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources:\n  - name: 123\n    kind: api\n    description: d\n")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_roster_carries_stripped_field_values(self):
        # a valid-but-padded declared source: the roster stores the STRIPPED name/kind/label.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text('name: ed\nsources:\n  - name: "  exa  "\n    kind: "  api  "\n'
                          '    description: "  semantic search  "\n')
            roster = briefing.source_roster(agent_yaml=ay)
            entry = next(r for r in roster if r["name"] == "exa")
            self.assertEqual(entry["kind"], "api")
            self.assertEqual(entry["label"], "semantic search")

    def test_string_sources_fails_closed_not_attributeerror(self):
        # a non-list `sources:` (a bare string) is a malformed roster SHAPE — it must raise the
        # typed BriefingIdentityError (the fail-closed path), NOT an AttributeError.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources: just-a-string\n")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_dict_sources_fails_closed_not_attributeerror(self):
        # a mapping `sources:` (not a list) is a malformed roster SHAPE → typed BriefingIdentityError.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources:\n  exa:\n    kind: api\n    description: d\n")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_non_mapping_entry_fails_closed_not_attributeerror(self):
        # a list whose entry is a scalar (not a mapping) → typed BriefingIdentityError, not AttributeError.
        with tempfile.TemporaryDirectory() as tmp:
            ay = Path(tmp) / "agent.yaml"
            ay.write_text("name: ed\nsources:\n  - just-a-string\n")
            with self.assertRaises(briefing.BriefingIdentityError):
                briefing.source_roster(agent_yaml=ay)

    def test_valid_roster_includes_native_source_additively(self):
        with tempfile.TemporaryDirectory() as tmp:
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            roster = briefing.source_roster(agent_yaml=ay)
            names = [r["name"] for r in roster]
            self.assertIn("exa", names)                                       # the declared roster
            self.assertTrue(any("session" in n.lower() for n in names))      # native, additive
            self.assertGreater(len(roster), 1)


class FullGenotypeComposesEverySectionNonEmpty(unittest.TestCase):
    """Gate stage-(i) acceptance (audit): a complete agent.yaml + present docs → the four
    REQUIRED genotype-identity sections (Personality, Method, Idiom, the real Source roster) all
    render non-empty, while the log-fed sections still render their honest empty markers."""

    def test_complete_genotype_renders_all_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            mem = _genotype(Path(tmp) / "memory")
            ay = _complete_yaml(Path(tmp) / "agent.yaml")
            out = briefing.compose_briefing(
                log=Path(tmp) / "log.jsonl", clusters=None,
                agent_yaml=ay, memory=mem)
        # genotype identity — REQUIRED, non-empty
        self.assertIn("### Personality", out)
        self.assertIn("### Method", out)
        self.assertIn("## Idiom", out)
        self.assertIn("**exa**", out)                      # the REAL declared source
        self.assertTrue(any(s in out.lower() for s in ("session",)))  # native, additive
        # log-fed sections — honest empty markers on a fresh log (NOT fail-closed)
        self.assertIn("no confirmed objective yet", out.lower())
        self.assertIn("no direction set yet", out.lower())
        self.assertIn("no direcionamento report yet", out.lower())
        self.assertIn("no corpus yet", out.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
