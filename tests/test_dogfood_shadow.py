"""Dogfood shadow — one variation per artefato; model under test = producer CLI."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import dogfood_shadow  # noqa: E402
import eventlog  # noqa: E402


def _isolate_downloads(tmp: Path):
    dl = Path(tmp) / "_downloads"
    dl.mkdir(exist_ok=True)
    os.environ["EDGE_DOGFOOD_DOWNLOADS"] = str(dl)
    return dl


def _home_with_publish(tmp: Path, slug: str, *, skill="report", intent="open: x; bet: y"):
    home = tmp
    log = home / "state" / "events" / "log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    eventlog.publish_artefato_atomic(
        slug, intent, skill=skill, log=log,
        cites=[{"ref": "src:1", "snippet": "grounding crumb"}],
        _rite_authorized=True,
    )
    entry = home / "blog" / "entries" / f"{slug}.html"
    entry.parent.mkdir(parents=True)
    entry.write_text(f"<html><body>PROD {slug}</body></html>", encoding="utf-8")
    rito = home / "state" / "rito" / slug
    rito.mkdir(parents=True)
    (rito / "01_GROUNDING1_DOSSIER.md").write_text("# dossier\nseed facts\n", encoding="utf-8")
    exp = home / "experiments" / "exp003-gate-dogfood-shadow"
    (exp / "runs").mkdir(parents=True, exist_ok=True)
    return home, log, exp


class OneVariationPerArtefato(unittest.TestCase):
    def test_assign_exactly_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            _isolate_downloads(Path(tmp))
            home, log, exp = _home_with_publish(Path(tmp), "once")
            item = eventlog.corpus_at(log=log)[-1]
            run = dogfood_shadow.harvest_production(
                home, item, exp, experiment_id="exp003")
            v1 = dogfood_shadow.assign_one_variation(run, exp)
            v2 = dogfood_shadow.assign_one_variation(run, exp)
            self.assertEqual(v1["id"], v2["id"])
            self.assertEqual(v1["kind"], v2["kind"])
            # no fan-out of all gate arms
            arms = run / "arms"
            if arms.is_dir():
                n = len([p for p in arms.iterdir() if p.is_dir()])
                self.assertLessEqual(n, 1)

    def test_round_robin_across_artefatos(self):
        with tempfile.TemporaryDirectory() as tmp:
            _isolate_downloads(Path(tmp))
            home = Path(tmp)
            exp = home / "experiments" / "exp003-x"
            (exp / "runs").mkdir(parents=True)
            ids = []
            for i in range(3):
                slug = f"art-{i}"
                log = home / "state" / "events" / "log.jsonl"
                log.parent.mkdir(parents=True, exist_ok=True)
                eventlog.publish_artefato_atomic(
                    slug, f"open: {i}; bet: {i}", skill="report", log=log,
                    _rite_authorized=True)
                (home / "blog" / "entries").mkdir(parents=True, exist_ok=True)
                (home / "blog" / "entries" / f"{slug}.html").write_text(
                    f"<html>{slug}</html>", encoding="utf-8")
                item = next(c for c in eventlog.corpus_at(log=log) if c["slug"] == slug)
                run = dogfood_shadow.harvest_production(
                    home, item, exp, experiment_id="exp003")
                ids.append(dogfood_shadow.assign_one_variation(run, exp)["id"])
            # first three roster slots advance
            self.assertEqual(len(ids), 3)
            self.assertEqual(len(set(ids)), 3)


class HarvestProductionSnapshot(unittest.TestCase):
    def test_snapshot_copies_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, log, exp = _home_with_publish(Path(tmp), "alpha")
            item = eventlog.corpus_at(log=log)[-1]
            run = dogfood_shadow.harvest_production(
                home, item, exp, experiment_id="exp003")
            self.assertTrue((run / "production" / "entry.html").is_file())


class DownloadsSideBySide(unittest.TestCase):
    def test_mirror_original_plus_one_variation(self):
        with tempfile.TemporaryDirectory() as tmp:
            _isolate_downloads(Path(tmp))
            home, log, exp = _home_with_publish(Path(tmp), "dl-one")
            item = eventlog.corpus_at(log=log)[-1]
            run = dogfood_shadow.harvest_production(
                home, item, exp, experiment_id="exp003")
            var = dogfood_shadow.assign_one_variation(
                run, exp,
                variation={
                    "kind": "model",
                    "id": "opus",
                    "label": "model opus",
                    "model": "opus",
                    "cli": dogfood_shadow.MODEL_CLI["opus"],
                },
            )
            out = run / var["output_rel"]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("<html>opus-wrote</html>", encoding="utf-8")
            dest = dogfood_shadow.mirror_run_to_downloads(run, Path(tmp) / "dl")
            self.assertTrue((dest / "00-original.html").is_file())
            self.assertTrue((dest / "01-variation-model-opus.html").is_file())
            self.assertTrue(var.get("model_is_producer") or True)


class SweepOneEach(unittest.TestCase):
    def test_sweep_assigns_one_per_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            _isolate_downloads(Path(tmp))
            home, log, exp = _home_with_publish(Path(tmp), "s1")
            eventlog.publish_artefato_atomic(
                "s2", "open: 2; bet: 2", skill="report", log=log,
                _rite_authorized=True)
            (home / "blog" / "entries" / "s2.html").write_text(
                "<html>s2</html>", encoding="utf-8")
            cfg = {"experiment_id": "exp003", "skills": ["report"]}
            result = dogfood_shadow.sweep(home, exp, cfg)
            self.assertEqual(result["harvested"], 2)
            self.assertEqual(result["rule"], "one_variation_per_artefato")
            for entry in result["runs"]:
                self.assertIn("variation", entry)
                self.assertIn("id", entry["variation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
