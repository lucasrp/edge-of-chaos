"""S6 — the close's genus floor (design-close.md, plan §S6/§E8).

GENUS FLOOR — a themed dispatch with zero recognized source-reads is a genus-class violation
(blocking-first). The mechanism lives HARVEST-side (`harvest.close_floor`, a wrapper over the
pure `session_floor`); close.py only consumes a `floor_fn: () -> list[str]`. Fail-OPEN (inverse
of genus): darkness → [] + a counted `grounding.floor_dark` event, never a block. Ticket B (B.4)
raised EDGE_GROUNDING_FLOOR's default 0→1=OBSERVE: env-unset COUNTS but NEVER blocks; explicit 0
stays fully off (see tests/test_gate_metadata.py for the env-unset contract).

(Publish-with-residuals, the cosmetic meta-gate and the split genus/reviewer bounce budget were
removed by ADR-0025: the reviewer only warns, so there is no residual to grade.)
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
    lineage), so it stays genus-CLEAN (the realistic production case: a developed report already
    carries the four moves)."""
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


def _reviewer(calls=None):
    def r(artefato, complete_fn=None):
        if calls is not None:
            calls["n"] += 1
        return {"furos": []}
    r.identity = close.REVIEWER_ID
    return r


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

class FloorIsGenusClassBlocking(unittest.TestCase):
    """A floor violation is genus-class: it runs BEFORE the reviewer and bounces the genus path. A
    raising floor_fn is DARK → [] (never crashes the close)."""

    def test_floor_violation_hard_fails_before_reviewers_and_never_publishes(self):
        reviewer_calls = {"n": 0}
        published = []
        result = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewer=_reviewer(reviewer_calls),
            publish_fn=lambda a, p: published.append(a),
            floor_fn=lambda: [harvest.FLOOR_VIOLATION])
        self.assertFalse(result["pass"])
        self.assertIn("genus_violations", result)
        self.assertIn(harvest.FLOOR_VIOLATION, result["genus_violations"])
        self.assertEqual(reviewer_calls["n"], 0)   # the reviewer never ran (genus-first)
        self.assertEqual(published, [])            # floor never publishes

    def test_raising_floor_fn_is_dark_treated_as_empty_never_crashes(self):
        def floor_fn():
            raise RuntimeError("floor blew up")
        proof = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewer=_reviewer(), floor_fn=floor_fn)
        self.assertTrue(proof["pass"])             # dark floor → [] → normal pass

    def test_none_floor_fn_is_byte_compat_no_floor(self):
        proof = close.run_close(
            _conformant_artefato(), produce_fn=_conformant_artefato,
            reviewer=_reviewer())   # floor_fn defaults to None
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

if __name__ == "__main__":
    unittest.main()
