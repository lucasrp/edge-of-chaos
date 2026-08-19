"""S6 — the close's genus floor + publish-with-residuals (design-close.md, plan §S6/§E8).

TWO deliverables, both OPT-IN (default OFF → byte-compat):
  A. GENUS FLOOR — a themed dispatch with zero recognized source-reads is a genus-class
     violation (blocking-first, never a residual). The mechanism lives HARVEST-side
     (`harvest.close_floor`, a wrapper over the pure `session_floor`); close.py only consumes a
     `floor_fn: () -> list[str]`. Fail-OPEN (inverse of genus): darkness → [] + a counted
     `grounding.floor_dark` event, never a block.
  B. PUBLISH-WITH-RESIDUALS — bounce exhaustion with genus-clean + REAL reviewer strikes publishes
     the draft WITH a "Crítica não endereçada" section appended BEFORE the mint (so the proof
     digest binds it) instead of hard-failing. Infra (transport re-raise) and synthetic strikes
     never residual-publish; genus-dirty-post-append never publishes.

SECURITY: with the knobs at default (EDGE_PUBLISH_WITH_RESIDUALS=0, EDGE_GENUS_BOUNCE_MAX=
BOUNCE_MAX) run_close is byte-identical to today — the existing close suite (test_close_loop /
test_close_infra) is the byte-compat oracle. Ticket B (B.4) raised EDGE_GROUNDING_FLOOR's
default 0→1=OBSERVE: env-unset now COUNTS (grounding.floor/floor_dark) but still NEVER blocks;
explicit 0 stays fully off (see tests/test_gate_metadata.py for the env-unset contract).
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
# two tests below reuse test_harvest's golden transcript shapes (`from test_harvest import …`).
# That import only resolves when the tests dir is importable, which `-m unittest tests.<mod>`
# does NOT arrange — same fix test_publisher_floor_split.py already carries for the same reuse.
sys.path.insert(0, str(REPO / "tests"))
import close      # noqa: E402
import harvest    # noqa: E402
import eventlog   # noqa: E402


# --- shared fixtures (mirroring test_close_loop.py) ------------------------------------------

def _conformant_artefato(slug="s6-artefato"):
    """A genus-conformant artefato that reaches the reviewers + the mint. Rich-rite-COMPLETE
    (derivation marker 'therefore', boundary marker 'uncertain', cites=external-frame, distills=
    lineage), so appending the residual section — which pushes prose past the rich-rite trigger —
    keeps genus CLEAN (the realistic production case: a developed report already carries the four
    moves)."""
    return {
        "slug": slug,
        "content": {"sections": [{"title": "Body", "blocks": [
            {"type": "paragraph",
             "text": "the proof is bound to this exact payload; therefore the gate holds, "
                     "though the calibration remains uncertain."},
        ]}]},
        "cites": [{"ref": "arXiv:2507.02778", "kind": "mundo", "relevant": True,
                   "snippet": "the cursor became a watermark"}],
        "proposes": [{"body": "name the budget", "kind": "constraint"}],
        "intent": "open: x; bet: y",
        "distills": ["cluster:prior-thread"],
    }


def _genus_invalid_artefato(slug="genus-bad"):
    art = _conformant_artefato(slug)
    art["cites"] = [{"ref": "github:abc", "kind": "atividade", "relevant": True}]  # no snippet
    return art


def _passing_reviewer(identity):
    def r(artefato, complete_fn=None):
        return {"pass": True, "scores": {"rigor": 4}, "strikes": [], "overall": 4.0}
    r.identity = identity
    return r


def _striking_reviewer(identity, strike="a claim overstates the evidence"):
    """A canonical-identity reviewer that ALWAYS strikes with a REAL (non-synthetic) strike and a
    non-empty scores dict — the authentic-criticism shape residual-publish requires (§4)."""
    def r(artefato, complete_fn=None):
        return {"pass": False, "scores": {"rigor": 3}, "rationales": {"rigor": "overstates"},
                "strikes": [strike], "overall": 3.0}
    r.identity = identity
    return r


def _both_striking(strike="a claim overstates the evidence"):
    return (_striking_reviewer(close.FEYNMAN_REVIEWER_ID, strike),
            _striking_reviewer(close.REGULAR_REVIEWER_ID, strike))


def _cosmetic_judge(prompt, *a, **k):
    """Stand-in for the issue-#65 semantic cosmetic meta-gate (codex/gpt-5.5): the injected
    reviewers here strike a purely presentational nit ('overstates the evidence'), so the agent
    judges it cosmetic and the residual (graded-publish) path proceeds."""
    return '{"all_cosmetic": true, "rationale": "presentational nit"}'


class _KnobEnv:
    """Context manager: set/clear EDGE_* env knobs and restore them (env-driven, read live)."""
    def __init__(self, **knobs):
        self.knobs = knobs
        self.saved = {}

    def __enter__(self):
        for k, v in self.knobs.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        return self

    def __exit__(self, *a):
        for k, old in self.saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


# =========================================================================================
# A. GENUS FLOOR
# =========================================================================================

class GenusBounceMaxIsItsOwnCounter(unittest.TestCase):
    """EDGE_GENUS_BOUNCE_MAX is a SEPARATE counter from the reviewers' BOUNCE_MAX (design §7 / E6).
    Its DEFAULT is BOUNCE_MAX (E6, BINDING amendment — a default of 15 would change knobs-off
    behavior and break the byte-compat the verify demands), so the split only manifests when an
    operator raises the genus backstop."""

    def test_genus_bounce_max_defaults_to_bounce_max_for_byte_compat(self):
        self.assertEqual(close.GENUS_BOUNCE_MAX, close.BOUNCE_MAX)

    def test_genus_uses_its_own_budget_distinct_from_reviewer_bounce_max(self):
        with mock.patch.object(close, "GENUS_BOUNCE_MAX", 3):
            calls = {"n": 0}

            def produce_fn():
                calls["n"] += 1
                return _genus_invalid_artefato()   # persistently invalid

            result = close.run_close(
                _genus_invalid_artefato(), produce_fn=produce_fn,
                reviewers=(_passing_reviewer(close.FEYNMAN_REVIEWER_ID),
                           _passing_reviewer(close.REGULAR_REVIEWER_ID)),
                complete_fn=lambda *a, **k: "")
            self.assertFalse(result["pass"])
            self.assertEqual(calls["n"], 3)         # genus's OWN budget, not BOUNCE_MAX
        self.assertEqual(close.BOUNCE_MAX, 1)       # reviewers' counter unchanged

    def test_knobs_off_genus_and_reviewer_share_one_pool_byte_compat(self):
        # BYTE-COMPAT (the reviewer's exact repro): at the default (GENUS_BOUNCE_MAX == BOUNCE_MAX)
        # a genus bounce DEBITS the single shared pool. Draft starts genus-dirty; produce_fn returns
        # a genus-CLEAN draft; reviewers strike on the produced draft then would pass on a re-produce.
        # Pre-S6/HEAD: the genus bounce consumes the single BOUNCE_MAX budget, so the reviewer strike
        # HARD-FAILS with no extra reproduce → pass=False, published=0. The disjoint-pool S6 bug gave
        # the producer a fresh reviewer bounce (pass=True, published=1); the fix restores HEAD.
        self.assertEqual(close.GENUS_BOUNCE_MAX, close.BOUNCE_MAX)   # knobs off
        self.assertEqual(close.BOUNCE_MAX, 1)
        produce_calls = {"n": 0}
        review_calls = {"n": 0}

        def produce_fn():
            produce_calls["n"] += 1
            return _conformant_artefato()           # genus-CLEAN after the bounce

        def strike_then_pass(identity):
            state = {"first": True}

            def r(artefato, complete_fn=None):
                review_calls["n"] += 1
                if state["first"]:
                    state["first"] = False
                    return {"pass": False, "scores": {"rigor": 3},
                            "strikes": ["overstates"], "overall": 3.0}
                return {"pass": True, "scores": {"rigor": 4}, "strikes": [], "overall": 4.0}
            r.identity = identity
            return r

        published = []
        result = close.run_close(
            _genus_invalid_artefato(), produce_fn=produce_fn,
            reviewers=(strike_then_pass(close.FEYNMAN_REVIEWER_ID),
                       strike_then_pass(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a))
        self.assertFalse(result["pass"])            # genus bounce consumed the shared budget
        self.assertEqual(published, [])             # HEAD behavior — never published
        self.assertNotIn("residual_publish", result)

    def test_knobs_off_count_drift_is_one_produce_one_reviewer_round(self):
        # BYTE-COMPAT count-drift: reviewers ALWAYS strike, genus clean throughout. The shared pool
        # caps the loop at exactly ONE re-produce and TWO reviewer rounds (initial + the bounce),
        # NOT the disjoint-pool double-spend. Asserts produce_fn is called once and each reviewer
        # runs exactly twice (one full extra round), matching HEAD's single-pool loop.
        self.assertEqual(close.GENUS_BOUNCE_MAX, close.BOUNCE_MAX)
        self.assertEqual(close.BOUNCE_MAX, 1)
        produce_calls = {"n": 0}

        def produce_fn():
            produce_calls["n"] += 1
            return _conformant_artefato()

        review_calls = {"n": 0}

        def counting_striker(identity):
            def r(artefato, complete_fn=None):
                review_calls["n"] += 1
                return {"pass": False, "scores": {"rigor": 3},
                        "strikes": ["overstates"], "overall": 3.0}
            r.identity = identity
            return r

        result = close.run_close(
            _conformant_artefato(), produce_fn=produce_fn,
            reviewers=(counting_striker(close.FEYNMAN_REVIEWER_ID),
                       counting_striker(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "")
        self.assertFalse(result["pass"])
        self.assertEqual(produce_calls["n"], 1)     # exactly ONE re-produce (not 2)
        # two reviewers × two rounds (initial + one bounce) = 4 reviewer calls; NOT 6 (the S6 bug's
        # extra round). "one produce, one bounce round" in HEAD's single-pool terms.
        self.assertEqual(review_calls["n"], 4)


class MalformedScoresPrefixIsSynthetic(unittest.TestCase):
    """Finding 2 (defense-in-depth): `_normalize_verdict` wraps a non-dict `scores` as a
    'malformed scores:' strike (no `(s)`), so that prefix MUST be synthetic → residual-ineligible."""

    def test_malformed_scores_strike_is_ineligible_for_residual_publish(self):
        self.assertIn("malformed scores:", close._SYNTHETIC_STRIKE_PREFIXES)
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            def bad_scores(art, complete_fn=None):
                return {"pass": False, "scores": "not-a-dict", "strikes": ["overstates"],
                        "overall": 0.0}
            bad_scores.identity = close.FEYNMAN_REVIEWER_ID
            published = []
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=(bad_scores, _striking_reviewer(close.REGULAR_REVIEWER_ID)),
                complete_fn=lambda *a, **k: "",
                publish_fn=lambda a, p: published.append(a))
            self.assertFalse(result["pass"])
            self.assertNotIn("residual_publish", result)
            self.assertEqual(published, [])


class FloorIsGenusClassBlocking(unittest.TestCase):
    """A floor violation is genus-class: it runs BEFORE the reviewers, bounces the genus path, and
    never publishes-with-residuals. A raising floor_fn is DARK → [] (never crashes the close)."""

    def test_floor_violation_hard_fails_before_reviewers_and_never_publishes(self):
        reviewer_calls = {"n": 0}

        def counting_passer(art, complete_fn=None):
            reviewer_calls["n"] += 1
            return {"pass": True, "scores": {"x": 4}, "strikes": [], "overall": 4.0}
        counting_passer.identity = close.FEYNMAN_REVIEWER_ID
        published = []
        result = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewers=(counting_passer, _passing_reviewer(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "",
            publish_fn=lambda a, p: published.append(a),
            floor_fn=lambda: [harvest.FLOOR_VIOLATION])
        self.assertFalse(result["pass"])
        self.assertIn("genus_violations", result)
        self.assertIn(harvest.FLOOR_VIOLATION, result["genus_violations"])
        self.assertEqual(reviewer_calls["n"], 0)   # reviewers never ran (genus-first)
        self.assertEqual(published, [])            # floor never publishes

    def test_raising_floor_fn_is_dark_treated_as_empty_never_crashes(self):
        def floor_fn():
            raise RuntimeError("floor blew up")
        proof = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewers=(_passing_reviewer(close.FEYNMAN_REVIEWER_ID),
                       _passing_reviewer(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "", floor_fn=floor_fn)
        self.assertTrue(proof["pass"])             # dark floor → [] → normal pass

    def test_none_floor_fn_is_byte_compat_no_floor(self):
        proof = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewers=(_passing_reviewer(close.FEYNMAN_REVIEWER_ID),
                       _passing_reviewer(close.REGULAR_REVIEWER_ID)),
            complete_fn=lambda *a, **k: "")   # floor_fn defaults to None
        self.assertTrue(proof["pass"])


class CloseFloorWrapperKnobLogic(unittest.TestCase):
    """`harvest.close_floor` — the injected floor_fn. Reads EDGE_GROUNDING_FLOOR (0=off, 1=observe,
    2=gate), decides THEMED via the last dispatch.open geometry, runs session_floor's recognize.
    Fail-OPEN dark is COUNTED (grounding.floor_dark), never silent; ambient NEVER gates."""

    def _store_with_transcript(self, tmp, session_id, *, recognized):
        store = Path(tmp) / "projects"
        if recognized:
            from test_harvest import _tool_pair, _write, X_CMD  # reuse golden shapes
            _write(store / "-slug" / f"{session_id}.jsonl",
                   _tool_pair(session_id, "t1", "2026-07-01T10:00:00.000Z", X_CMD))
        else:
            # a present transcript with NO recognized read (dark=False, reads=0)
            line = {"type": "assistant", "sessionId": session_id,
                    "timestamp": "2026-07-01T10:00:00.000Z",
                    "message": {"role": "assistant",
                                "content": [{"type": "text", "text": "just thinking"}]}}
            store / "-slug"
            p = store / "-slug" / f"{session_id}.jsonl"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(line) + "\n")
        return store

    def _fixture_recognizers(self):
        """O roster DECLARADO deste teste — a fixture versionada, nunca o agent.yaml do host.

        `harvest.close_floor` cai em `build_recognizers()` sem argumento, que lê
        `sources.load_sources()` — o agent.yaml de quem roda a suíte. Num genótipo (que POR
        CONTRATO não tem agent.yaml) a tabela nasce VAZIA, o X_CMD do transcript golden não é
        reconhecido e o teste do caminho "themed COM leitura reconhecida" falha por instalação,
        não por código. Mesma injeção que test_harvest._seam_sources já faz."""
        import sources as sources_mod
        import harvest as harvest_mod
        srcs, findings = sources_mod.load_sources(
            Path(__file__).resolve().parent / "fixtures" / "roster.agent.yaml")
        errors = [f for f in findings if f.get("level") == "error"]
        assert srcs and not errors, f"fixture de roster inválida: {errors}"
        return harvest_mod.build_recognizers(sources=srcs)

    def _log_with_open(self, tmp, session_id, geometry):
        log = Path(tmp) / "log.jsonl"
        if geometry is not None:
            eventlog.append("dispatch.open", "dispatch",
                            {"session_id": session_id, "dispatch_id": "d1", "geometry": geometry},
                            log=log)
        return log

    def test_knob_off_returns_empty_and_logs_nothing(self):
        # explicit 0 = fully OFF (B.4 moved the env-unset default to 1=observe, so "off" is
        # now a DECLARED choice — the env-unset observe contract lives in test_gate_metadata).
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=0):
            log = self._log_with_open(tmp, "sX", "themed")
            store = self._store_with_transcript(tmp, "sX", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sX",
                                      child_session="")
            self.assertEqual(out, [])
            self.assertEqual(eventlog.read(types=harvest.eventlog.GROUNDING_TYPES, log=log), [])

    def test_gate_blocks_themed_dispatch_with_zero_recognized_reads(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = self._log_with_open(tmp, "sT", "themed")
            store = self._store_with_transcript(tmp, "sT", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sT",
                                      child_session="",
                                      recognizers=self._fixture_recognizers())
            self.assertEqual(out, [harvest.FLOOR_VIOLATION])

    def test_gate_passes_themed_dispatch_with_a_recognized_read(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = self._log_with_open(tmp, "sR", "themed")
            store = self._store_with_transcript(tmp, "sR", recognized=True)
            out = harvest.close_floor(log=log, store_root=store, session_id="sR",
                                      child_session="",
                                      recognizers=self._fixture_recognizers())
            self.assertEqual(out, [])

    def test_observe_counts_the_would_be_violation_but_never_blocks(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=1):
            log = self._log_with_open(tmp, "sO", "themed")
            store = self._store_with_transcript(tmp, "sO", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sO",
                                      child_session="")
            self.assertEqual(out, [])   # observe never blocks
            floor_evs = eventlog.read(types=["grounding.floor"], log=log)
            self.assertEqual(len(floor_evs), 1)

    def test_ambient_geometry_never_gates(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = self._log_with_open(tmp, "sA", "ambient")
            store = self._store_with_transcript(tmp, "sA", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sA",
                                      child_session="")
            self.assertEqual(out, [])   # ambient never gates (R3.2)
            # not dark either — ambient is a deliberate non-gate, not an instrument failure
            self.assertEqual(eventlog.read(types=["grounding.floor_dark"], log=log), [])

    def test_undeclared_geometry_is_dark_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = self._log_with_open(tmp, "sU", None)   # NO dispatch.open at all
            store = self._store_with_transcript(tmp, "sU", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sU",
                                      child_session="")
            self.assertEqual(out, [])   # fail-open
            self.assertEqual(len(eventlog.read(types=["grounding.floor_dark"], log=log)), 1)

    def test_child_session_is_dark_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = self._log_with_open(tmp, "sC", "themed")
            store = self._store_with_transcript(tmp, "sC", recognized=False)
            out = harvest.close_floor(log=log, store_root=store, session_id="sC",
                                      child_session="1")
            self.assertEqual(out, [])
            self.assertEqual(len(eventlog.read(types=["grounding.floor_dark"], log=log)), 1)

    def test_absent_session_id_is_dark_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            log = Path(tmp) / "log.jsonl"
            out = harvest.close_floor(log=log, store_root=Path(tmp) / "projects",
                                      session_id="", child_session="")
            self.assertEqual(out, [])
            self.assertEqual(len(eventlog.read(types=["grounding.floor_dark"], log=log)), 1)

    def test_e8_floor_works_for_a_never_seen_declared_source(self):
        # E8 (the "Overleaf test"): the floor's recognize() is 100% DERIVED from the source table —
        # NO source is hardcoded. A source never seen by the floor code, declared only in the
        # operator's yaml (here a synthetic `overleaf` interface), gets recognized WITHOUT a code
        # change: its read under a themed dispatch satisfies the floor.
        with tempfile.TemporaryDirectory() as tmp, _KnobEnv(EDGE_GROUNDING_FLOOR=2):
            from test_harvest import _tool_pair, _write
            synthetic = [{"name": "overleaf", "lens": "mundo", "interfaces": [
                {"interface_id": "read", "idiom": None, "dry_semantics": None,
                 "via": "GET https://api.overleaf.example/v1/projects"}]}]
            recs = harvest.build_recognizers(synthetic)
            store = Path(tmp) / "projects"
            cmd = 'curl -s "https://api.overleaf.example/v1/projects?query=grounding"'
            _write(store / "-slug" / "sE.jsonl",
                   _tool_pair("sE", "t9", "2026-07-01T10:00:00.000Z", cmd))
            log = self._log_with_open(tmp, "sE", "themed")
            out = harvest.close_floor(log=log, store_root=store, session_id="sE",
                                      child_session="", recognizers=recs)
            self.assertEqual(out, [])   # a never-seen DECLARED source's read satisfies the floor


# =========================================================================================
# B. PUBLISH-WITH-RESIDUALS
# =========================================================================================

class ResidualPublishHappyPath(unittest.TestCase):
    """Knob ON + bounce exhausted + genus-clean + 2 canonical verdicts with REAL strikes →
    publish WITH a 'Crítica não endereçada' section appended BEFORE the mint. The proof gains
    `residual_publish: True` + `unaddressed`; the published artefato carries the section."""

    def test_publishes_with_section_and_unaddressed_in_proof(self):
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            captured = {}

            def publish_fn(art, proof):
                captured["art"] = art
                captured["proof"] = proof

            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=_both_striking(), complete_fn=_cosmetic_judge,
                publish_fn=publish_fn)
            # returned the residual proof
            self.assertTrue(result.get("residual_publish"))
            self.assertEqual(len(result["unaddressed"]), 2)
            self.assertIn("a claim overstates the evidence",
                          result["unaddressed"][0]["strikes"])
            # published the APPENDED artefato (section inside content)
            titles = [s.get("title") for s in
                      captured["art"]["content"].get("additional_sections", [])]
            self.assertIn("Crítica não endereçada", titles)
            # the strike rides VERBATIM on the page section
            blob = json.dumps(captured["art"]["content"], ensure_ascii=False)
            self.assertIn("a claim overstates the evidence", blob)

    def test_digest_covers_the_appended_section(self):
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            captured = {}
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=_both_striking(), complete_fn=_cosmetic_judge,
                publish_fn=lambda a, p: captured.update(art=a, proof=p))
            art, proof = captured["art"], captured["proof"]
            # verify_proof BINDS to the APPENDED content (digest covers the section)
            close.verify_proof(proof, slug=art["slug"], spec=art["content"],
                               intent=art["intent"], cites=art["cites"],
                               proposes=art["proposes"], distills=art.get("distills"),
                               reviewer_count=2)
            # tamper: the ORIGINAL (un-appended) content no longer binds → digest mismatch
            original = _conformant_artefato()["content"]
            with self.assertRaises(ValueError):
                close.verify_proof(proof, slug=art["slug"], spec=original,
                                   intent=art["intent"], cites=art["cites"],
                                   proposes=art["proposes"], distills=art.get("distills"),
                                   reviewer_count=2)

    def test_verify_proof_refuses_residual_proof_when_knob_off_at_verify(self):
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            captured = {}
            close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=_both_striking(), complete_fn=_cosmetic_judge,
                publish_fn=lambda a, p: captured.update(art=a, proof=p))
        art, proof = captured["art"], captured["proof"]
        # knob now OFF at verify time → a struck (residual) proof is refused immediately
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=None):
            with self.assertRaises(ValueError):
                close.verify_proof(proof, slug=art["slug"], spec=art["content"],
                                   intent=art["intent"], cites=art["cites"],
                                   proposes=art["proposes"], reviewer_count=2)


class ResidualPublishRefusals(unittest.TestCase):
    """The fail-closed boundaries: knob-off, genus-dirty-post-append, transport re-raise, and
    synthetic strikes ALL fall through to the existing HARD-FAIL — never a residual publish."""

    def test_knob_off_is_byte_compat_hard_fail(self):
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=None):
            published = []
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=_both_striking(), complete_fn=_cosmetic_judge,
                publish_fn=lambda a, p: published.append(a))
            self.assertFalse(result["pass"])
            self.assertNotIn("residual_publish", result)
            self.assertEqual(published, [])

    def test_genus_dirty_after_append_hard_fails_never_publishes(self):
        # a genus check that is CLEAN on the base draft but DIRTY once the residual section lands
        real_check = close.check_genus

        def dirty_on_residual(artefato, attest=None):
            base = real_check(artefato, attest=attest)
            titles = [s.get("title") for s in
                      (artefato.get("content", {}).get("additional_sections") or [])
                      if isinstance(s, dict)]
            if "Crítica não endereçada" in titles:
                return base + ["residual-section-broke-genus"]
            return base

        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1), \
                mock.patch.object(close, "check_genus", dirty_on_residual):
            published = []
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=_both_striking(), complete_fn=_cosmetic_judge,
                publish_fn=lambda a, p: published.append(a))
            self.assertFalse(result["pass"])
            self.assertNotIn("residual_publish", result)
            self.assertEqual(published, [])   # NEVER publish genus-dirty, even for a residual

    def test_transport_error_raises_never_residual(self):
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            def boom(art, complete_fn=None):
                raise close._llm.LLMTransportError("quota dead", status=429)
            boom.identity = close.FEYNMAN_REVIEWER_ID
            published = []
            with self.assertRaises(close._llm.LLMTransportError):
                close.run_close(
                    _conformant_artefato(), produce_fn=_conformant_artefato,
                    reviewers=(boom, _striking_reviewer(close.REGULAR_REVIEWER_ID)),
                    complete_fn=lambda *a, **k: "",
                    publish_fn=lambda a, p: published.append(a))
            self.assertEqual(published, [])   # infra ≠ residual — never publishes

    def test_synthetic_strike_disqualifies_hard_fail(self):
        # a reviewer that RAISES a generic exception → wrapped into a synthetic `reviewer raised:`
        # strike; §4 disqualifies it (crash/drift, not criticism) → hard-fail, never residual.
        with _KnobEnv(EDGE_PUBLISH_WITH_RESIDUALS=1):
            def crasher(art, complete_fn=None):
                raise RuntimeError("reviewer internal boom")
            crasher.identity = close.FEYNMAN_REVIEWER_ID
            published = []
            result = close.run_close(
                _conformant_artefato(), produce_fn=_conformant_artefato,
                reviewers=(crasher, _striking_reviewer(close.REGULAR_REVIEWER_ID)),
                complete_fn=lambda *a, **k: "",
                publish_fn=lambda a, p: published.append(a))
            self.assertFalse(result["pass"])
            self.assertNotIn("residual_publish", result)
            self.assertEqual(published, [])


if __name__ == "__main__":
    unittest.main()
