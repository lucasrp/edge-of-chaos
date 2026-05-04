from __future__ import annotations

import os
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from edge_core.rite import verify_rite
from edge_core.config import load_config
from edge_core.publication import validate_report_spec
from edge_core.report_shape import validate_report_markdown
from edge_core.threads import choose_primary_thread, initial_seed_thread, primary_thread_from_review


ROOT = Path(__file__).resolve().parents[1]


class MentorCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="edge-v2-test-"))
        for name in ["edge_core", "tools", "agent.yaml.example", "blog", "reports", "state", "config"]:
            source = ROOT / name
            target = self.tmp / name
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copy2(source, target)
        shutil.rmtree(self.tmp / "blog", ignore_errors=True)
        shutil.rmtree(self.tmp / "reports", ignore_errors=True)
        shutil.rmtree(self.tmp / "state", ignore_errors=True)
        for path in [self.tmp / "blog", self.tmp / "reports", self.tmp / "state", self.tmp / "config"]:
            path.mkdir(parents=True, exist_ok=True)
        (self.tmp / "agent.yaml").write_text(
            """
name: test
codename: tst
language: en-US
mission: "Mentor test"
domain: "tests"
workspaces:
  - name: fixture
    path: "."
    kind: repo
context:
  claude_sessions:
    enabled: false
sources:
  - name: hackernews
    enabled: false
first_steps:
  - "Read context"
interests:
  - area: "Testing"
    connection: "Verify mentor core"
""",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def run_edge(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("OPENAI_API_KEY", None)
        env["EDGE_DISABLE_LOCAL_ENV"] = "1"
        env["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        return subprocess.run(
            ["python3", "tools/edge", *args],
            cwd=self.tmp,
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )

    def test_render_apply_doctor_and_report(self) -> None:
        self.assertEqual(self.run_edge("render").returncode, 0)
        self.assertEqual(self.run_edge("apply").returncode, 0)
        doctor = self.run_edge("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        report = self.run_edge("report", "testar continuidade")
        self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        self.assertTrue(list((self.tmp / "reports").glob("*.md")))
        self.assertTrue(list((self.tmp / "reports").glob("*.yaml")))
        self.assertTrue(list((self.tmp / "reports").glob("*.html")))
        self.assertTrue(list((self.tmp / "blog" / "entries").glob("*.md")))
        self.assertTrue(list((self.tmp / "blog" / "entries").glob("*.html")))
        self.assertTrue(list((self.tmp / "blog" / "reports").glob("*.html")))
        self.assertTrue((self.tmp / "blog" / "index.html").exists())
        self.assertTrue((self.tmp / "state" / "events.jsonl").exists())
        self.assertTrue(list((self.tmp / "state" / "threads").glob("*.md")))
        self.assertTrue((self.tmp / "state" / "report-utility.jsonl").exists())
        ledger = (self.tmp / "state" / "events.jsonl").read_text(encoding="utf-8")
        events = [json.loads(line) for line in ledger.splitlines() if line.strip()]
        self.assertIn("StateLoaded", ledger)
        self.assertIn("ChatDigestRefreshed", ledger)
        self.assertIn("ContinuitySearchReviewed", ledger)
        self.assertIn("BroadSearchCompleted", ledger)
        self.assertIn("ReportDrafted", ledger)
        self.assertIn("ReportShapeReviewed", ledger)
        self.assertIn("AdversarialSearchReviewed", ledger)
        self.assertIn("AdversarialReviewed", ledger)
        self.assertIn("FeynmanReviewed", ledger)
        self.assertIn("ArtifactBundleValidated", ledger)
        self.assertIn("ReportUtilityClassified", ledger)
        self.assertIn("RiteVerified", ledger)
        self.assertIn("CycleClosed", ledger)
        drafted = next(event for event in events if event["type"] == "ReportDrafted")
        final = next(event for event in events if event["type"] == "FinalReportPrepared")
        written = next(event for event in events if event["type"] == "ReportWritten")
        self.assertEqual(drafted["mode"], "deterministic-scaffold")
        self.assertEqual(drafted["llm_error"], "claude:disabled")
        self.assertEqual(final["mode"], "unchanged")
        self.assertEqual(final["llm_error"], "claude:disabled")
        self.assertTrue(written["path"].endswith(".html"))
        self.assertTrue(written["markdown_path"].endswith(".md"))
        self.assertTrue(written["spec_path"].endswith(".yaml"))
        report_html = next((self.tmp / "reports").glob("*.html"))
        report_text = report_html.read_text(encoding="utf-8")
        self.assertIn("Problem Framing and Open Gaps", report_text)
        self.assertIn("Feynman Derivation", report_text)
        self.assertIn("Why This Matters Now", report_text)

    def test_rite_requires_two_context_search_reviews(self) -> None:
        events = [
            {"type": "CycleOpened"},
            {"type": "ChatDigestRefreshed"},
            {"type": "StateLoaded"},
            {"type": "DeliveryCompleted", "stage": "context-pack"},
            {"type": "ContinuitySearchReviewed", "reviewer": "llm:context-search"},
            {"type": "BroadSearchCompleted", "results": 1},
            {"type": "DeliveryCompleted", "stage": "evidence-pack-v1"},
            {"type": "BroadSearchCompleted", "results": 1},
            {"type": "DeliveryCompleted", "stage": "evidence-pack-v2"},
            {"type": "ReportDrafted"},
            {"type": "ReportShapeReviewed"},
            {"type": "DeliveryCompleted", "stage": "draft-v1"},
            {"type": "AdversarialSearchReviewed", "reviewer": "llm:adversarial"},
            {"type": "BroadSearchCompleted", "results": 1},
            {"type": "ReportRevised"},
            {"type": "ReportShapeReviewed"},
            {"type": "DeliveryCompleted", "stage": "draft-v2"},
            {"type": "AdversarialReviewed", "reviewer": "llm:adversarial"},
            {"type": "ReportRevised"},
            {"type": "ReportShapeReviewed"},
            {"type": "DeliveryCompleted", "stage": "draft-v3"},
            {"type": "FeynmanReviewed", "reviewer": "llm:feynman-review"},
            {"type": "FinalReportPrepared"},
            {"type": "ReportShapeReviewed"},
            {"type": "ArtifactBundleValidated", "report_spec_passed": True, "blog_post_passed": True},
            {"type": "ReportWritten"},
            {"type": "ReportUtilityClassified"},
            {"type": "ThreadUpdated"},
            {"type": "DigestRebuilt"},
            {"type": "BlogBuilt"},
        ]
        check = verify_rite(events)
        self.assertFalse(check.passed)
        self.assertIn("ContinuitySearchReviewed", check.missing)
        self.assertIn("continuity-search:rounds", check.missing)

    def test_primary_thread_accepts_llm_string(self) -> None:
        primary = primary_thread_from_review({"primary_thread": "Persistent private mentorship"}, "heartbeat")
        self.assertEqual(primary["thread_id"], "persistent-private-mentorship")
        self.assertEqual(primary["title"], "Persistent private mentorship")

    def test_single_thread_candidate_is_continued_directly(self) -> None:
        primary = choose_primary_thread(
            {"primary_thread": {"action": "create", "thread_id": "wrong", "title": "Wrong"}},
            "heartbeat",
            [{"id": "judge-calibration", "title": "Judge Calibration", "summary": "..."},],
        )
        self.assertEqual(primary["action"], "continue")
        self.assertEqual(primary["thread_id"], "judge-calibration")
        self.assertEqual(primary["title"], "Judge Calibration")

    def test_initial_seed_thread_is_fixed_fallback(self) -> None:
        config = load_config(self.tmp)
        primary = initial_seed_thread(config)
        self.assertEqual(primary["title"], "Help the mentee in the best possible way with their current work")
        self.assertEqual(primary["thread_id"], "help-the-mentee-in-the-best-possible-way-with-their-current-work")

    def test_report_shape_rejects_truncated_tail(self) -> None:
        report = """# Private Mentor Report

## Lineage

This section has enough content to pass the minimum threshold and ends cleanly.

## Situated Delta

This section has enough content to pass the minimum threshold and ends cleanly.

## Problem Framing and Open Gaps

This section has enough content to pass the minimum threshold and ends cleanly.

## Simple Model

This section has enough content to pass the minimum threshold and ends cleanly.

## Feynman Derivation

This section has enough content to pass the minimum threshold and ends cleanly.

## Why This Matters Now

This section has enough content to pass the minimum threshold and ends cleanly.

## Broad Search

This section has enough content to pass the minimum threshold and ends cleanly.

## Adversarial Pushback

This section has enough content to pass the minimum threshold and ends cleanly.

## Recommended Next Steps

This section has enough content to pass the minimum threshold and ends cleanly.

## What I Don't Know

This section has enough content to pass the minimum threshold and ends cleanly.

## Contextualization and Glossary

This section has enough content to pass the minimum threshold.

Wheth
"""
        check = validate_report_markdown(report)
        self.assertFalse(check.passed)
        self.assertIn("suspicious short tail: Contextualization and Glossary", check.issues)

    def test_report_spec_requires_thread_read_for_continue(self) -> None:
        spec = {
            "title": "Private Mentor Report",
            "subtitle": "Heartbeat beat",
            "date": "2026-05-04",
            "thread": {"id": "judge-calibration", "title": "Judge Calibration", "action": "continue"},
            "executive_summary": ["one", "two", "three"],
            "metrics": [{"value": "1", "label": "a"}, {"value": "2", "label": "b"}, {"value": "3", "label": "c"}],
            "sections": [{"title": title, "markdown": f"{title} section has enough content to pass the minimum threshold and ends cleanly."} for title in [
                "Lineage",
                "Situated Delta",
                "Problem Framing and Open Gaps",
                "Simple Model",
                "Feynman Derivation",
                "Why This Matters Now",
                "Broad Search",
                "Adversarial Pushback",
                "Recommended Next Steps",
                "What I Don't Know",
                "Contextualization and Glossary",
            ]],
            "bibliography": [{"text": "local-state", "url": "file:///tmp/local", "source": "local-state"}],
            "evidence": {"thread_read_confirmed": False, "authoritative_paths": ["/tmp/state/events.jsonl"]},
            "blog_post": {"title": "Heartbeat", "paragraphs": ["Paragraph one.", "Paragraph two."]},
        }
        check = validate_report_spec(spec)
        self.assertFalse(check.passed)
        self.assertIn("continued thread lacks authoritative in-beat read", check.issues)


if __name__ == "__main__":
    unittest.main()
