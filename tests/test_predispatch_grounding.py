"""S5 (grounding iteration) — the predispatch floor GAINS a harvest leg and a canary battery,
both degrade-dark (the wake NEVER raises from grounding — R3.2: it annotates, it never gates),
and the dispatch.open stamp GAINS `harvested` + `ambient_rows`.

The two-factor dry taxonomy itself is a FOLD (eventlog._dry_label, pinned in test_eventlog.py):
`seca-verificada` is never written on a row — it is projected by joining a born-`suspect` manifest
row to a `canary.result` for the same source×interface. These tests pin that the predispatch
canary STEP produces those canary.result attestations for the PENDING dries, iterating the
DECLARED interfaces (agent.yaml) — never a source named in code (E8, the Overleaf test)."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog     # noqa: E402
import predispatch  # noqa: E402
import sources      # noqa: E402


def _suspect_row(source, interface, idiom_conforme=None, dry_semantics=None,
                 geometry="ambient", ref=("s", 1, "t", 0)):
    """A born-suspect `grounding.manifest` payload (0 hits) — the shape harvest emits for a dry
    read (dry: 'suspect' is written by _base_row; verificada is NEVER written, only folded)."""
    return {"raw_ref": list(ref), "source": source, "interface": interface, "lens": "mundo",
            "geometry": geometry, "intent": None, "attribution": "mapped", "hits": 0,
            "dry": "suspect", "idiom_conforme": idiom_conforme, "dry_semantics": dry_semantics,
            "recognizer_rev": 1}


def _seed(log, *rows):
    for i, r in enumerate(rows):
        r = dict(r)
        r["raw_ref"] = [r["raw_ref"][0], r["raw_ref"][1], f"t{i}", i]
        eventlog.append("grounding.manifest", "grounding", r, log=log)


def _run(log, probe_fn, harvest_fn=lambda: 0, **kw):
    return predispatch.run(sweep_fn=lambda: 0, briefing_fn=lambda: "B", recall_fn=lambda: "R",
                           harvest_fn=harvest_fn, probe_fn=probe_fn, log=log, dispatch_id="d1", **kw)


def _dry(log, cell):
    return eventlog.grounding_at(log=log)["cells"][cell]["dry"]


_XCELL = ("x", "v2-recent", "mundo", "ambient", None)   # x/v2-recent carries a real canary spec


class HarvestLegStampsAndDegradesDark(unittest.TestCase):
    def test_harvested_count_is_stamped_on_dispatch_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _run(log, probe_fn=lambda s: True, harvest_fn=lambda: 4)
            p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertEqual(p["harvested"], 4)
            self.assertIn("ambient_rows", p, "the stamp gains ambient_rows too")

    def test_dead_harvest_degrades_dark_and_still_stamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"

            def boom():
                raise RuntimeError("store gone")

            buf = io.StringIO()
            with redirect_stdout(buf):
                _run(log, probe_fn=lambda s: True, harvest_fn=boom)
            p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertEqual(p["harvested"], 0, "a dark harvest stamps 0, never raises")
            self.assertTrue(eventlog.wake_fresh(log=log), "the stamp still lands")
            self.assertIn("harvest leg DARK", buf.getvalue())


class CanaryProbesPendingDriesAndTheFoldProjects(unittest.TestCase):
    """The end-to-end: a prior-session born-suspect row → the canary step probes its interface →
    the appended canary.result makes the fold project the two-factor label."""

    def test_canary_pass_and_idiom_ok_projects_verificada(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("x", "v2-recent", idiom_conforme=True))
            _run(log, probe_fn=lambda s: True)
            self.assertEqual(_dry(log, _XCELL), {"verificada": 1})
            self.assertEqual(eventlog.grounding_at(log=log)["excluded"]["seca-suspeita"], 0)

    def test_canary_pass_but_idiom_violated_is_overspecified(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("x", "v2-recent", idiom_conforme=False))
            _run(log, probe_fn=lambda s: True)
            self.assertEqual(_dry(log, _XCELL), {"suspect:overspecified": 1})

    def test_canary_fail_is_instrumento(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("x", "v2-recent", idiom_conforme=True))
            _run(log, probe_fn=lambda s: False)
            self.assertEqual(_dry(log, _XCELL), {"suspect:instrumento": 1})

    def test_unknown_probe_appends_no_result_and_row_stays_suspect(self):
        # hits None ≠ 0 is sacred (S4): a probe that returns None cannot attest — no canary.result
        # is fabricated, and the dry read honestly stays bare suspect.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("x", "v2-recent", idiom_conforme=True))
            _run(log, probe_fn=lambda s: None)
            self.assertEqual(_dry(log, _XCELL), {"suspect": 1})
            self.assertEqual(eventlog.read(types=["canary.result"], log=log), [])

    def test_no_pending_dry_never_probes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            calls = []
            _run(log, probe_fn=lambda s: calls.append(s) or True)   # empty log → nothing pending
            self.assertEqual(calls, [], "an empty grounding log probes nothing")
            self.assertEqual(eventlog.read(types=["canary.result"], log=log), [])


class NeverDryInterfaceIsNotProbed(unittest.TestCase):
    """dry_semantics: never-dry (exa — the risk is confident filler, not drought) → the fold
    labels its 0-hit reads `nao-aplicavel`, never `suspect`, so it is not pending; the canary
    battery never probes it and the guard is defense in depth."""

    def test_never_dry_source_is_nao_aplicavel_and_never_probed(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("exa", "search-deep", dry_semantics="never-dry"))
            calls = []
            _run(log, probe_fn=lambda s: calls.append(s["source"]) or True)
            cell = ("exa", "search-deep", "mundo", "ambient", None)
            self.assertEqual(_dry(log, cell), {"nao-aplicavel": 1})
            self.assertNotIn("exa", calls, "a never-dry interface is never probed")
            self.assertEqual(eventlog.read(types=["canary.result"], log=log), [])


class WakeNeverRaisesFromADeadSource(unittest.TestCase):
    """A probe that RAISES (a dead source — network down, the instrument unreachable) is caught:
    the wake does NOT raise, the leg is annotated dark, the failure is recorded as
    suspect:instrumento, and the stamp STILL lands."""

    def test_probe_raises_no_wake_raise_dark_annotated_stamp_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("x", "v2-recent", idiom_conforme=True))

            def dead(spec):
                raise ConnectionError("network down")

            buf = io.StringIO()
            with redirect_stdout(buf):
                b, r = _run(log, probe_fn=dead)          # must NOT raise
            self.assertEqual((b, r), ("B", "R"))
            self.assertTrue(eventlog.wake_fresh(log=log), "the stamp still lands")
            self.assertIn("dead source", buf.getvalue())  # the dark leg is annotated
            # a probe that could not run is the instrument being broken → suspect:instrumento
            self.assertEqual(_dry(log, _XCELL), {"suspect:instrumento": 1})


class AmbientRowsAreStamped(unittest.TestCase):
    def test_ambient_read_volume_is_counted_onto_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log,
                  _suspect_row("x", "v2-recent", idiom_conforme=True, geometry="ambient"),
                  _suspect_row("x", "v2-recent", idiom_conforme=True, geometry="ambient"))
            _run(log, probe_fn=lambda s: True)
            p = eventlog.read(types=["dispatch.open"], log=log)[0]["payload"]
            self.assertEqual(p["ambient_rows"], 2, "both ambient attempts count toward the stamp")


class E8CanaryIteratesDeclaredInterfacesNeverASourceByName(unittest.TestCase):
    """E8 — the Overleaf test: a never-seen interface declared ONLY in the operator's agent.yaml,
    carrying a canary spec, is probed by the battery with ZERO code change. The battery iterates
    sources.load_sources() — no source is named in predispatch."""

    _SYNTH = {"sources": [{
        "name": "overleaf", "description": "Overleaf. Lens: Atividade.",
        "interfaces": [{"interface_id": "v2-search",
                        "via": "GET https://api.overleaf.com/v2/search?q=...",
                        "canary": {"query": "lyx export", "params": {"limit": 1}},
                        "dry_semantics": "false-dry-prone"}]}]}

    def test_synthetic_interface_is_probed_and_folds_verificada(self):
        srcs, findings = sources.validate_sources(self._SYNTH)
        self.assertFalse([f for f in findings if f["level"] == "error"], findings)
        seen = []

        def probe(spec):
            seen.append((spec["source"], spec["interface"]))
            return True

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _seed(log, _suspect_row("overleaf", "v2-search", idiom_conforme=True))
            with mock.patch.object(predispatch.sources_mod, "load_sources",
                                   return_value=(srcs, findings)):
                _run(log, probe_fn=probe)
            self.assertIn(("overleaf", "v2-search"), seen,
                          "the never-seen interface was probed straight from agent.yaml")
            cell = ("overleaf", "v2-search", "mundo", "ambient", None)  # lens from the seeded row
            self.assertEqual(_dry(log, cell), {"verificada": 1})

    def test_predispatch_hardcodes_no_declared_source_name(self):
        # the canary battery must derive everything from the yaml — assert no declared source
        # name appears as a literal in predispatch.py (E8 no-hardcode guard for S5)
        src = (REPO / "tools" / "predispatch.py").read_text()
        declared, _ = sources.load_sources()
        names = [s["name"] for s in declared]
        self.assertTrue(names, "guard must not run vacuous — agent.yaml declares sources")
        for n in names:
            self.assertNotIn(f'"{n}"', src, f"source name {n!r} is hardcoded in predispatch.py")
            self.assertNotIn(f"'{n}'", src, f"source name {n!r} is hardcoded in predispatch.py")


class DefaultProbeIsHonestWhenItCannotFormARequest(unittest.TestCase):
    def test_no_url_in_via_is_unknown_not_a_fail(self):
        # UNKNOWN (None), never a fabricated fail — a via with no endpoint cannot be probed
        self.assertIsNone(predispatch._default_probe(
            {"via": "gh api / gh search — read-only", "canary": {"query": "x"}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
