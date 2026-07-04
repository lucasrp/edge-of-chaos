"""S7 (grounding iteration) — the yield join + rendered table (design-yield + E1).

The fold `fold_grounding_yield`/`grounding_yield_at` joins the grounding manifest (attempts,
faceta 1) to the `source.signal` reward half over the two hops: Salto 1 (slug→dispatch, the
S2 `dispatch_id`, legacy interval fallback) and Salto 2 (ref→attempt, host→source via the
agent.yaml via-seam + dispatch-cell-uniqueness, the exact/coarse/ambiguous/orphan ladder).
Graduated reward (PURPLE): cited-with-score / cited-without-score (no-embedder 0.0 excluded) /
hit-without-citation. Policy as DATA (min_attempts→EXPLORE, empirical-Bayes shrink, cite prior).
THE FORBIDDEN INTERFACE (§6): the module exports fold + render and NOTHING ELSE — no
choose_source/route/argmax. A test ASSERTS the absence.
"""
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import eventlog          # noqa: E402
import grounding_yield   # noqa: E402

HSMAP = {"api.exa.ai": "exa", "api.twitter.com": "x", "hn.algolia.com": "hn"}


def _mani(log, raw_ref, source, interface, dispatch_id, *, lens="mundo", geometry="gather",
          attribution="mapped", hits=3, intent=None):
    p = {"raw_ref": list(raw_ref), "source": source, "interface": interface, "lens": lens,
         "geometry": geometry, "attribution": attribution, "hits": hits,
         "dispatch_id": dispatch_id, "intent": intent, "recognizer_rev": 1}
    if hits == 0:
        p["dry"] = "suspect"
    return eventlog.append("grounding.manifest", "grounding", p, log=log)


def _open(log, dispatch_id, intent=None, geometry="themed"):
    return eventlog.append("dispatch.open", "dispatch",
                           {"dispatch_id": dispatch_id, "intent": intent, "geometry": geometry},
                           log=log)


def _pub(log, slug, dispatch_id, skill="research"):
    return eventlog.append("artefato.published", f"artefato:{slug}",
                           {"slug": slug, "dispatch_id": dispatch_id, "skill": skill}, log=log)


def _sig(log, slug, ref, similarity, kind="mundo"):
    return eventlog.append("source.signal", f"artefato:{slug}",
                           {"slug": slug, "ref": ref, "kind": kind, "similarity": similarity},
                           log=log)


def _fold(log):
    return grounding_yield.grounding_yield_at(log=log, hsmap=HSMAP)


class TwoConcurrentDispatches(unittest.TestCase):
    def test_each_ref_lands_in_its_own_dispatchs_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _open(log, "d2", intent="discovery")
            _mani(log, ("sA", 1, "t1", 0), "exa", "search-deep", "d1")
            _mani(log, ("sB", 1, "t2", 0), "exa", "search-deep", "d2")
            _pub(log, "artA", "d1", skill="research")
            _pub(log, "artB", "d2", skill="discovery")
            _sig(log, "artA", "https://api.exa.ai/x", 0.8)
            _sig(log, "artB", "https://api.exa.ai/y", 0.6)
            y = _fold(log)
            ka = ("research", "exa", "search-deep", "mundo", "gather")
            kb = ("discovery", "exa", "search-deep", "mundo", "gather")
            self.assertIn(ka, y["cells"])
            self.assertIn(kb, y["cells"])
            self.assertEqual(y["cells"][ka]["cited"], 1)
            self.assertEqual(y["cells"][ka]["mean_sim"], 0.8)
            self.assertEqual(y["cells"][kb]["cited"], 1)
            self.assertEqual(y["cells"][kb]["mean_sim"], 0.6)
            self.assertEqual(y["orphans"], 0)


class JoinLadder(unittest.TestCase):
    def test_ambiguous_two_cells_credits_source_marginal_not_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _mani(log, ("s", 2, "t2", 0), "exa", "contents", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.9)
            y = _fold(log)
            # neither cell got the per-cell credit
            for k, c in y["cells"].items():
                self.assertEqual(c["cited"], 0, k)
            self.assertEqual(y["marginals"]["exa"]["ambiguous"], 1)
            self.assertEqual(y["marginals"]["exa"]["coarse"], 0)

    def test_coarse_host_maps_but_no_cell_credits_source_marginal(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "x", "v2-recent", "d1")   # only x in this dispatch
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.7)           # cite exa — no exa cell in d1
            y = _fold(log)
            self.assertEqual(y["marginals"]["exa"]["coarse"], 1)
            self.assertEqual(y["marginals"]["exa"]["ambiguous"], 0)

    def test_orphan_unmatched_host_and_recall_cite(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://unknown.example.com/z", 0.5)  # host maps to no source
            _sig(log, "art", "cluster:memory-note", 0.4)           # recall/self cite — no host
            y = _fold(log)
            self.assertEqual(y["orphans"], 2)
            # the exact-eligible cell never received the orphan cites
            self.assertEqual(y["cells"][("research", "exa", "search-deep", "mundo", "gather")]["cited"], 0)

    def test_cite_from_unmapped_artefato_is_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _sig(log, "ghost", "https://api.exa.ai/x", 0.9)  # no published artefato 'ghost'
            y = _fold(log)
            self.assertEqual(y["orphans"], 1)


class GraduatedReward(unittest.TestCase):
    def test_no_embedder_zero_is_excluded_from_mean_sim(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.0)   # publisher with no embedder → 0.0
            y = _fold(log)
            c = y["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["cited"], 1)          # counted in cited
            self.assertIsNone(c["mean_sim"])         # but NOT folded into the mean (no poison)

    def test_real_similarity_feeds_mean_sim(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.5)
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["mean_sim"], 0.5)

    def test_genuine_negative_similarity_counts_in_mean_sim(self):
        # §2 excludes EXACTLY the no-embedder 0.0; a GENUINE negative similarity is a real
        # dis-similarity signal and must COUNT (previously `sim > 0.0` wrongly dropped it).
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", -0.3)
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["cited"], 1)
            self.assertAlmostEqual(c["mean_sim"], -0.3)   # counts, not excluded

    def test_nan_similarity_is_skipped_never_crashes(self):
        # a NaN similarity is not a measure (NaN != 0.0) — it must NOT reach fmean; it is routed
        # to the excluded pool (counted in `cited`, off the mean), and never crashes the fold.
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", float("nan"))
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["cited"], 1)           # visible, counted
            self.assertIsNone(c["mean_sim"])          # but never folded into the mean

    def test_hit_without_citation_pulls_the_mean_toward_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            for i in range(4):
                _mani(log, ("s", i, f"t{i}", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.8)   # 1 cite, 4 attempts
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["cited"], 1)
            self.assertAlmostEqual(c["mean_sim"], 0.8 / 4)  # [0.8,0,0,0] — revealed utility


class ExcludedAndExplore(unittest.TestCase):
    def test_excluded_counted_by_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1", hits=0)      # seca suspeita
            _mani(log, ("s", 2, "t2", 0), "exa", "search-deep", "d1",
                  attribution="inferred")                                            # inferred attr
            y = _fold(log)
            self.assertEqual(y["excluded"]["seca-suspeita"], 1)
            self.assertEqual(y["excluded"]["attribution:inferred"], 1)

    def test_seca_suspeita_row_is_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1", hits=0)  # only a suspect dry
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.9)  # a cite, but the only attempt is excluded
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertIsNone(c["mean_sim"])   # no scoring attempt → the cite lands nowhere scorable
            self.assertEqual(c["score"], None)

    def test_explore_below_min_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            _sig(log, "art", "https://api.exa.ai/x", 0.9)
            c = _fold(log)["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["attempts"], 1)
            self.assertIsNone(c["score"])   # EXPLORE — below min_attempts (5)

    def test_ambient_geometry_has_no_score_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", geometry="ambient")
            for i in range(6):
                _mani(log, ("s", i, f"t{i}", 0), "exa", "search-deep", "d1", geometry="ambient")
            c = _fold(log)["cells"][(None, "exa", "search-deep", "mundo", "ambient")]
            self.assertEqual(c["attempts"], 6)      # health is tracked
            self.assertIsNone(c["score"])           # never a score
            self.assertEqual(c["rewards"], [])


class EmpiricalBayesShrink(unittest.TestCase):
    def test_score_regresses_toward_the_global_mean(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")
            _open(log, "d2", intent="research")
            for i in range(5):
                _mani(log, ("a", i, f"ta{i}", 0), "exa", "search-deep", "d1")
            for i in range(5):
                _mani(log, ("b", i, f"tb{i}", 0), "exa", "contents", "d2")
            _pub(log, "artA", "d1")
            _pub(log, "artB", "d2")
            _sig(log, "artA", "https://api.exa.ai/x", 1.0)   # cell A: [1,0,0,0,0] mean 0.2
            # cell B: no cites → [0,0,0,0,0] mean 0.0 → global mean = 0.1
            y = _fold(log)
            a = y["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertAlmostEqual(a["mean_sim"], 0.2)
            # shrink toward global 0.1: strictly between global and the cell mean
            self.assertGreater(a["score"], 0.1)
            self.assertLess(a["score"], 0.2)
            self.assertAlmostEqual(a["score"], (5 * 0.2 + 3 * 0.1) / 8)


class UnconsumedStratum(unittest.TestCase):
    def test_unconsumed_dispatch_open_counted_out_of_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "d1", intent="research")     # consumed
            _open(log, "d2", intent="research")     # aborted — never published
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "d1")
            _pub(log, "art", "d1")
            y = _fold(log)
            self.assertEqual(y["unconsumed"], 1)


class LegacyTolerance(unittest.TestCase):
    def test_legacy_published_without_dispatch_id_still_folds(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            _open(log, "dLeg", intent="research")
            _mani(log, ("s", 1, "t1", 0), "exa", "search-deep", "dLeg")
            # a legacy publish carries NO dispatch_id — reconstructed by seq interval (the open below)
            eventlog.append("artefato.published", "artefato:old",
                            {"slug": "old", "skill": "research"}, log=log)
            _sig(log, "old", "https://api.exa.ai/x", 0.9)
            y = _fold(log)   # must not crash
            c = y["cells"][("research", "exa", "search-deep", "mundo", "gather")]
            self.assertEqual(c["cited"], 1)    # the cite joined via the reconstructed dispatch
            self.assertEqual(y["orphans"], 0)


class UrlNormalization(unittest.TestCase):
    def test_tracking_params_and_trailing_slash_normalize(self):
        self.assertEqual(grounding_yield.normalize_ref("https://api.exa.ai/x/?utm_source=z"),
                         "https://api.exa.ai/x")
        self.assertEqual(grounding_yield.normalize_ref("HTTPS://API.Exa.AI/x"),
                         "https://api.exa.ai/x")

    def test_non_url_ref_returns_itself_and_orphans(self):
        self.assertEqual(grounding_yield.normalize_ref("cluster:foo"), "cluster:foo")
        self.assertIsNone(grounding_yield._host_of("cluster:foo"))


class ForbiddenInterface(unittest.TestCase):
    def test_no_choose_source_route_or_argmax_exported(self):
        for banned in ("choose_source", "route", "argmax", "router", "pick_source", "select_source"):
            self.assertFalse(hasattr(grounding_yield, banned),
                             f"the yield module must not export {banned!r} (the ROUTING table died of this)")

    def test_public_surface_is_only_fold_and_render(self):
        allowed = {
            # fold
            "fold_grounding_yield", "grounding_yield_at", "normalize_ref", "host_source_map",
            "declared_interfaces", "YIELD_POLICY", "YIELD_FOLD_TYPES",
            # render
            "briefing_yield_block", "render_sources_panel", "sources_panel_html",
        }
        public = {n for n in dir(grounding_yield)
                  if not n.startswith("_") and n not in ("eventlog", "sources_mod", "fmean", "html")}
        self.assertTrue(public <= allowed, f"unexpected public names: {public - allowed}")


if __name__ == "__main__":
    unittest.main()
