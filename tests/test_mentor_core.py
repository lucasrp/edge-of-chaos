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
from edge_core.report_shape import report_section_titles, validate_report_markdown
from edge_core.reports import _normalize_report_text, _safe_scaffold_text
from edge_core.search import broad_search
from edge_core.threads import choose_primary_thread, initial_seed_thread, primary_thread_from_review
from edge_core.context import ContextPacket, Observation


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
        (self.tmp / "state" / "operator-pressure.md").write_text(
            "# Operator Pressure\n\nAlways do fresh search in the live beat and check async chat before closing the cycle.\n",
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

    def _valid_section(self, title: str, body: str | None = None, *, evidence: bool = False, risks: bool = False, next_steps: bool = False) -> dict:
        content = body or f"{title} section has enough content to pass the minimum threshold and ends cleanly with a complete sentence about the current domain context."
        section = {
            "title": title,
            "lead": f"{title} explains why this part matters now, what evidence supports it, and how the reader should interpret the structured blocks that follow.",
            "markdown": content,
            "blocks": [{"type": "paragraph", "text": content}],
        }
        if evidence:
            section["blocks"] = [
                {"type": "paragraph", "text": content},
                {
                    "type": "table",
                    "title": "Substantive Evidence",
                    "headers": ["Source", "Artifact", "What It Says", "Why It Matters"],
                    "rows": [["workspace", "fixture", "Concrete evidence was inspected.", "It changes the current judgement."]],
                },
                {"type": "bar-chart", "title": "Evidence by Source", "unit": "", "items": [{"label": "workspace", "value": 3}]},
            ]
        if risks:
            section["blocks"] = [
                {"type": "paragraph", "text": content},
                {"type": "list", "items": ["Unknown one that still needs direct evidence.", "Unknown two that still needs a source-backed answer."]},
                {"type": "callout", "variant": "danger", "title": "Open Gaps", "text": "These gaps should shape the next beat."},
            ]
        if next_steps:
            section["blocks"] = [
                {"type": "paragraph", "text": content},
                {"type": "list", "items": ["Read the decisive artifact directly.", "Update the next artifact with the inspected evidence."]},
            ]
        return section

    def _valid_spec(self, *, continue_thread: bool = True) -> dict:
        sections = []
        for title in report_section_titles("report"):
            sections.append(
                self._valid_section(
                    title,
                    evidence=title == "Evidence",
                    risks=title == "Risks And Unknowns",
                    next_steps=title == "Next Steps",
                )
            )
        return {
            "title": "Private Mentor Report",
            "subtitle": "Discovery beat",
            "date": "2026-05-04",
            "kind": "report",
            "thread": {"id": "judge-calibration", "title": "Judge Calibration", "action": "continue" if continue_thread else "create"},
            "executive_summary": ["one complete summary sentence.", "two complete summary sentence.", "three complete summary sentence."],
            "metrics": [
                {"value": "1", "label": "a"},
                {"value": "2", "label": "b"},
                {"value": "3", "label": "c"},
                {"value": "4", "label": "d"},
            ],
            "sections": sections,
            "bibliography": [{"text": "local-state", "url": "https://example.invalid/local-state", "source": "local-state"}],
            "evidence": {
                "thread_read_confirmed": continue_thread,
                "thread_candidate_count": 1,
                "authoritative_paths": ["/tmp/state/threads/judge-calibration.md"],
                "visualization_count": 1,
                "search_feedback_rounds": 0,
            },
            "blog_post": {
                "title": "Discovery",
                "deck": "This deck gives enough context to explain why the compact entry exists and how it points back to the richer report.",
                "paragraphs": [
                    "Paragraph one with enough detail to stand alone.",
                    "Paragraph two with clear continuation context.",
                    "Paragraph three with enough substance to remain useful.",
                ],
                "highlights": [
                    "Highlight one carries a concrete takeaway.",
                    "Highlight two carries the search delta.",
                ],
                "section_cards": [
                    {"title": "Central Question", "body": "The compact entry still surfaces the live question with enough detail to stay specific and useful."},
                    {"title": "Evidence", "body": "The compact entry preserves the concrete evidence that shifted the current judgement."},
                    {"title": "Next Steps", "body": "The compact entry keeps at least one concrete next step instead of collapsing into pure summary."},
                ],
            },
        }

    def test_render_apply_doctor_and_report(self) -> None:
        self.assertEqual(self.run_edge("render").returncode, 0)
        self.assertEqual(self.run_edge("apply").returncode, 0)
        doctor = self.run_edge("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        seeded = self.run_edge("chat-send", "Please", "check", "the", "async", "chat", "during", "this", "beat.")
        self.assertEqual(seeded.returncode, 0, seeded.stdout + seeded.stderr)
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
        self.assertIn("OperatorContextLoaded", ledger)
        self.assertIn("ContinuitySearchReviewed", ledger)
        self.assertIn("BroadSearchCompleted", ledger)
        self.assertIn("ReportDrafted", ledger)
        self.assertIn("ReportShapeReviewed", ledger)
        self.assertIn("AdversarialSearchReviewed", ledger)
        self.assertIn("AdversarialReviewed", ledger)
        self.assertIn("FeynmanReviewed", ledger)
        self.assertIn("ArtifactBundleValidated", ledger)
        self.assertIn("ReportUtilityClassified", ledger)
        self.assertIn("AsyncChatAcknowledged", ledger)
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
        self.assertIn("Central Question", report_text)
        self.assertIn("Evidence", report_text)
        self.assertIn("Recommendation Or Synthesis", report_text)
        self.assertIn("Substantive Evidence", report_text)
        self.assertNotIn("Search Feedback", report_text)
        self.assertIn("<svg", report_text)
        entry_html = next((self.tmp / "blog" / "entries").glob("*.html")).read_text(encoding="utf-8")
        self.assertIn("Central Question", entry_html)
        self.assertIn("Async Chat", entry_html)
        listed = self.run_edge("chat-list", "--json")
        self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
        messages = json.loads(listed.stdout)
        self.assertTrue(any(item.get("author") == "edge" for item in messages))

    def test_load_config_accepts_agent_yaml_outside_repo(self) -> None:
        (self.tmp / "agent.yaml").unlink()
        (self.tmp.parent / "agent.yaml").write_text(
            """
name: external-test
codename: ext
language: en-US
mission: "External config"
domain: "tests"
workspaces:
  - name: fixture
    path: "."
    kind: repo
context:
  claude_sessions:
    enabled: false
sources: []
first_steps:
  - "Read context"
interests: []
""",
            encoding="utf-8",
        )
        try:
            config = load_config(self.tmp)
            self.assertEqual(config.name, "external-test")
            self.assertEqual(config.agent_path, self.tmp.parent / "agent.yaml")
        finally:
            (self.tmp.parent / "agent.yaml").unlink(missing_ok=True)

    def test_research_command_runs_the_same_rite(self) -> None:
        result = self.run_edge("research", "inspect", "the", "latest", "e2e", "delta")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ledger = (self.tmp / "state" / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn('"kind": "research"', ledger)

    def test_heartbeat_routes_to_real_beat(self) -> None:
        result = self.run_edge("heartbeat")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("kind=discovery", result.stdout)
        ledger = (self.tmp / "state" / "events.jsonl").read_text(encoding="utf-8")
        self.assertIn("HeartbeatRouted", ledger)
        self.assertIn('"requested_kind": "heartbeat-router"', ledger)

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
            {"primary_thread": {"action": "continue", "thread_id": "judge-calibration", "title": "Judge Calibration"}},
            "heartbeat",
            [{"id": "judge-calibration", "title": "Judge Calibration", "summary": "..."},],
        )
        self.assertEqual(primary["action"], "continue")
        self.assertEqual(primary["thread_id"], "judge-calibration")
        self.assertEqual(primary["title"], "Judge Calibration")

    def test_single_thread_candidate_can_be_overridden_by_explicit_create(self) -> None:
        primary = choose_primary_thread(
            {"primary_thread": {"action": "create", "thread_id": "topic-models", "title": "Topic Models"}},
            "heartbeat",
            [{"id": "help-the-mentee-in-the-best-possible-way-with-their-current-work", "title": "Help the mentee in the best possible way with their current work", "summary": "..."}],
        )
        self.assertEqual(primary["action"], "create")
        self.assertEqual(primary["thread_id"], "topic-models")
        self.assertEqual(primary["title"], "Topic Models")

    def test_initial_seed_thread_is_fixed_fallback(self) -> None:
        config = load_config(self.tmp)
        primary = initial_seed_thread(config)
        self.assertEqual(primary["title"], "Help the mentee in the best possible way with their current work")
        self.assertEqual(primary["thread_id"], "help-the-mentee-in-the-best-possible-way-with-their-current-work")

    def test_broad_search_executes_local_workspace_queries(self) -> None:
        os.environ["EDGE_DISABLE_LOCAL_ENV"] = "1"
        os.environ["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        config = load_config(self.tmp)
        packet = ContextPacket(request="inspect the current mentor test configuration", kind="discovery")
        results = broad_search(config, packet, hints=['grep -RIn "Mentor test" agent.yaml'], round_index=1)
        local_hits = [item for item in results if item.source == "workspace-search" and item.status == "retrieved"]
        self.assertTrue(local_hits)
        self.assertTrue(any(item.fetch_status == "fetched" for item in local_hits))
        self.assertTrue(any("Mentor test" in (item.fetched_excerpt or item.summary) for item in local_hits))

    def test_broad_search_reads_recent_workspace_files_without_command_hints(self) -> None:
        os.environ["EDGE_DISABLE_LOCAL_ENV"] = "1"
        os.environ["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        experiment_dir = self.tmp / "experimentos" / "tcu-analise-e2e" / "results" / "v8" / "2026-05-05T000000+0000" / "logs"
        experiment_dir.mkdir(parents=True, exist_ok=True)
        manifest = experiment_dir.parent / "run_manifest.json"
        manifest.write_text('{"experiment":"e2e","status":"ok","budget":"b50000"}', encoding="utf-8")
        (experiment_dir / "aggregate.log").write_text("pass_rate=0.81 latency=2.3 cost=14.2", encoding="utf-8")
        packet = ContextPacket(
            request="investigate the latest e2e experiment",
            kind="research",
            observations=[
                Observation(
                    "filesystem",
                    "fixture: recent files",
                    "\n".join(
                        [
                            "experimentos/tcu-analise-e2e/results/v8/2026-05-05T000000+0000/run_manifest.json",
                            "experimentos/tcu-analise-e2e/results/v8/2026-05-05T000000+0000/logs/aggregate.log",
                        ]
                    ),
                    str(self.tmp),
                ),
            ],
        )
        config = load_config(self.tmp)
        results = broad_search(config, packet, round_index=1)
        recent_reads = [item for item in results if item.source == "workspace-search" and item.fetch_status == "fetched"]
        self.assertTrue(recent_reads)
        joined = "\n".join((item.fetched_excerpt or item.summary) for item in recent_reads)
        self.assertIn("budget", joined)
        self.assertIn("pass_rate", joined)

    def test_broad_search_reads_required_absolute_local_paths_from_review_hints(self) -> None:
        os.environ["EDGE_DISABLE_LOCAL_ENV"] = "1"
        os.environ["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        run_dir = self.tmp / "experimentos" / "tcu-analise-e2e" / "results" / "v8" / "2026-05-05T010000+0000"
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        manifest = run_dir / "run_manifest.json"
        manifest.write_text('{"run_count":8,"status":"complete","pairing_key":"budget"}', encoding="utf-8")
        (logs_dir / "run_v8_b50000.log").write_text("v8 budget=50000 exit_code=0 paired=true", encoding="utf-8")
        (logs_dir / "run_v8_b75000.log").write_text("v8 budget=75000 exit_code=0 paired=true", encoding="utf-8")
        config = load_config(self.tmp)
        packet = ContextPacket(request="latest e2e direct read", kind="research")
        results = broad_search(
            config,
            packet,
            hints=[f"required_local_reads: {manifest} {logs_dir / 'run_v8_*.log'}"],
            round_index=2,
        )
        direct_reads = [item for item in results if item.source == "workspace-read" and item.fetch_status == "fetched"]
        joined = "\n".join((item.fetched_excerpt or item.summary) for item in direct_reads)
        self.assertIn("run_count", joined)
        self.assertIn("budget=50000", joined)
        self.assertIn("budget=75000", joined)

    def test_broad_search_ignores_direct_reads_outside_configured_roots(self) -> None:
        os.environ["EDGE_DISABLE_LOCAL_ENV"] = "1"
        os.environ["EDGE_DISABLE_CLAUDE_FALLBACK"] = "1"
        outside = self.tmp.parent / f"{self.tmp.name}-outside.json"
        outside.write_text('{"secret":"must-not-read"}', encoding="utf-8")
        try:
            config = load_config(self.tmp)
            packet = ContextPacket(request="ignore outside path", kind="research")
            results = broad_search(config, packet, hints=[f"read {outside}"], round_index=1)
            joined = "\n".join((item.fetched_excerpt or item.summary) for item in results)
            self.assertNotIn("must-not-read", joined)
            self.assertFalse(any(item.source == "workspace-read" and item.url == str(outside) for item in results))
        finally:
            outside.unlink(missing_ok=True)

    def test_report_shape_rejects_truncated_tail(self) -> None:
        report = """# Private Mentor Report

## Context

This section has enough content to pass the minimum threshold and ends cleanly.

## Central Question

This section has enough content to pass the minimum threshold and ends cleanly.

## Evidence

This section has enough content to pass the minimum threshold and ends cleanly.

## Analysis

This section has enough content to pass the minimum threshold and ends cleanly.

## Alternatives Or Comparisons

This section has enough content to pass the minimum threshold and ends cleanly.

## Recommendation Or Synthesis

This section has enough content to pass the minimum threshold and ends cleanly.

## Risks And Unknowns

This section has enough content to pass the minimum threshold and ends cleanly.

## Next Steps

This section has enough content to pass the minimum threshold and ends cleanly.

Wheth
"""
        check = validate_report_markdown(report)
        self.assertFalse(check.passed)
        self.assertIn("suspicious short tail: Next Steps", check.issues)

    def test_normalize_report_text_inserts_h1_before_section_heading(self) -> None:
        packet = ContextPacket(request="artifact contract", kind="report")
        text = _normalize_report_text(packet, "## Context\n\nThis section starts immediately with a level-two heading.")
        self.assertTrue(text.startswith("# Private Mentor Report\n\n## Context"))

    def test_safe_scaffold_text_strips_markdown_fence_fragments(self) -> None:
        cleaned = _safe_scaffold_text("```python\n# heading\nvalue=`x`\n**bold**")
        self.assertNotIn("```", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("**", cleaned)

    def test_report_spec_requires_thread_read_for_continue(self) -> None:
        spec = self._valid_spec(continue_thread=True)
        spec["evidence"]["thread_read_confirmed"] = False
        check = validate_report_spec(spec)
        self.assertFalse(check.passed)
        self.assertIn("continued thread lacks authoritative in-beat read", check.issues)

    def test_report_spec_rejects_empty_thread_claim_when_candidates_exist(self) -> None:
        spec = self._valid_spec(continue_thread=True)
        spec["sections"][0]["markdown"] = "This beat says thread_candidates arrived empty even though evidence says otherwise and therefore should fail cleanly."
        check = validate_report_spec(spec)
        self.assertFalse(check.passed)
        self.assertIn("report claims empty thread candidates despite non-empty evidence bundle", check.issues)


if __name__ == "__main__":
    unittest.main()
