from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .context import ContextPacket
from .util import slugify, truncate


@dataclass
class ReviewResult:
    status: str
    reviewer: str
    summary: str
    data: dict[str, Any]


class LLMClient:
    def __init__(self) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = (
            os.environ.get("OPENAI_MODEL")
            or os.environ.get("EDGE_MODEL_DIALOGUE")
            or os.environ.get("EDGE_MODEL_ADVERSARIAL_OPENAI")
            or "gpt-5.4"
        )
        if self.base_url.rstrip("/") == "https://api.openai.com/v1" and self.model.startswith("gpt_"):
            self.model = self.model.replace("gpt_", "gpt-", 1).replace("_", ".")

    def available(self) -> bool:
        return bool(self.api_key)

    def complete_json(self, *, system: str, prompt: str) -> dict[str, Any] | None:
        if not self.available():
            return self._complete_claude_json(system=system, prompt=prompt)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return self._complete_claude_json(system=system, prompt=prompt)
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        parsed = self._parse_json_object(content)
        if parsed is not None:
            return parsed
        return self._complete_claude_json(system=system, prompt=prompt)

    def complete_text(self, *, system: str, prompt: str) -> str | None:
        if not self.available():
            return self._complete_claude_text(system=system, prompt=prompt)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return self._complete_claude_text(system=system, prompt=prompt)
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return content or self._complete_claude_text(system=system, prompt=prompt)

    def _complete_claude_json(self, *, system: str, prompt: str) -> dict[str, Any] | None:
        text = self._complete_claude_text(
            system=system + "\nReturn only one valid JSON object. No Markdown fences.",
            prompt=prompt,
        )
        if not text:
            return None
        return self._parse_json_object(text)

    def _complete_claude_text(self, *, system: str, prompt: str) -> str | None:
        if os.environ.get("EDGE_DISABLE_CLAUDE_FALLBACK") == "1":
            return None
        claude = shutil.which("claude")
        if not claude:
            return None
        full_prompt = f"{system}\n\n{prompt}"
        try:
            result = subprocess.run(
                [claude, "-p", full_prompt, "--max-turns", "1"],
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("EDGE_CLAUDE_TIMEOUT_SEC", "120")),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        return (result.stdout or "").strip() or None

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.S)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                pass
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
        return None


def context_readiness(packet: ContextPacket, *, attempt: int) -> ReviewResult:
    client = LLMClient()
    prompt = json.dumps(packet.as_dict(), ensure_ascii=False)[:18000]
    llm = client.complete_json(
        system=(
            "You are the context readiness reviewer for a private Feynman mentor. "
            "Judge continuity and loader sufficiency. Return JSON with status "
            "pass|repair_needed|fail, primary_thread, missing_context, repair_instructions, reason."
        ),
        prompt=prompt,
    )
    if llm:
        status = str(llm.get("status") or "repair_needed")
        return ReviewResult(status, "llm:context-readiness", str(llm.get("reason") or status), llm)

    has_observations = len(packet.observations) >= 2
    thread_id = "general-continuity"
    title = "General Continuity"
    action = "create"
    default_heartbeat = packet.kind == "heartbeat" and packet.request == "Run a heartbeat beat"
    seed_text = ""
    if packet.seed_threads:
        seed = packet.seed_threads[0]
        seed_text = f"{seed.get('title', '')} {seed.get('context', '')}"
    request_text = (seed_text if default_heartbeat and seed_text else packet.request).lower()
    if packet.thread_candidates:
        scored: list[tuple[int, dict[str, Any]]] = []
        request_terms = {term for term in slugify(request_text).split("-") if len(term) > 3}
        for candidate in packet.thread_candidates:
            haystack = slugify(f"{candidate.get('id', '')} {candidate.get('summary', '')}")
            score = sum(1 for term in request_terms if term in haystack)
            scored.append((score, candidate))
        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] > 0:
            thread_id = str(scored[0][1].get("id") or thread_id)
            title = thread_id.replace("-", " ").title()
            action = "continue"
    if action == "create" and (default_heartbeat or not packet.request) and packet.seed_threads:
        seed = packet.seed_threads[0]
        title = str(seed.get("title") or "Seed Thread")
        thread_id = slugify(title, "seed-thread")[:80]
    elif action == "create" and packet.request:
        thread_id = slugify(packet.request, "general-continuity")[:80]
        title = thread_id.replace("-", " ").title()
    status = "pass" if has_observations else ("repair_needed" if attempt == 1 else "fail")
    data = {
        "status": status,
        "primary_thread": {"action": action, "thread_id": thread_id, "title": title},
        "continuity_assessment": "local fallback continues a thread only on textual overlap; otherwise it creates from request or seed_threads.",
        "loader_sufficiency": {"status": "sufficient" if has_observations else "insufficient"},
        "missing_context": [] if has_observations else ["No workspace or session observations were available."],
        "repair_instructions": [] if has_observations else ["Check configured workspaces and agent.yaml."],
        "reason": "Context has enough observations for a situated mentor beat." if has_observations else "Context is too thin.",
        "mode": "local-fallback",
    }
    return ReviewResult(status, "local:context-readiness", data["reason"], data)


def adversarial_review(report: str) -> ReviewResult:
    client = LLMClient()
    llm = client.complete_json(
        system="You are an adversarial reviewer. Find weak assumptions, missing evidence, and overreach. Return JSON.",
        prompt=report[:16000],
    )
    if llm:
        return ReviewResult("completed", "llm:adversarial", str(llm.get("summary") or "adversarial review completed"), llm)
    summary = "Local fallback: challenge generic claims, missing source diversity, weak continuity, and recommendations not tied to the observed delta."
    return ReviewResult("completed", "local:adversarial", summary, {"summary": summary, "mode": "local-fallback"})


def general_review(report: str, packet: ContextPacket) -> ReviewResult:
    client = LLMClient()
    llm = client.complete_json(
        system="You review whether the report answers the real current work context. Return JSON.",
        prompt=json.dumps({"report": report[:14000], "context": packet.as_dict()}, ensure_ascii=False)[:18000],
    )
    if llm:
        return ReviewResult("completed", "llm:general-review", str(llm.get("summary") or "review completed"), llm)
    summary = "Local fallback: report should explicitly cite the current request, observed workspace delta, thread continuity, and next action."
    return ReviewResult("completed", "local:general-review", summary, {"summary": summary, "mode": "local-fallback"})


def feynman_review(report: str) -> ReviewResult:
    client = LLMClient()
    llm = client.complete_json(
        system="You are a Feynman reviewer. Check simplicity, derivation, gaps, and honest uncertainty. Return JSON.",
        prompt=report[:16000],
    )
    if llm:
        return ReviewResult("completed", "llm:feynman-review", str(llm.get("summary") or "Feynman review completed"), llm)
    has_gap = "gap" in report.lower() or "lacuna" in report.lower()
    summary = "Local fallback: explanation is acceptable if it states the simple model, evidence, gaps, and next step."
    if not has_gap:
        summary += " Add an explicit gap section."
    return ReviewResult("completed", "local:feynman-review", summary, {"summary": summary, "mode": "local-fallback", "explicit_gap_seen": has_gap})


def method_review(report: str, packet: ContextPacket, search_sources: list[str]) -> ReviewResult:
    client = LLMClient()
    llm = client.complete_json(
        system=(
            "You are the method reviewer for edge-of-chaos v2. Judge whether this mentor report honored the rite: "
            "situated delta/context, continuity thread, broad search, adversarial posture, Feynman derivation, gaps, "
            "and concrete next steps. Return JSON with status pass|repair_needed|fail, summary, violations, and repair."
        ),
        prompt=json.dumps(
            {
                "report": report[:14000],
                "kind": packet.kind,
                "request": packet.request,
                "observations": [obs.__dict__ for obs in packet.observations[:8]],
                "thread_candidates": packet.thread_candidates[:4],
                "report_candidates": packet.report_candidates[:4],
                "search_sources": search_sources,
            },
            ensure_ascii=False,
        )[:18000],
    )
    if llm:
        status = str(llm.get("status") or "completed")
        return ReviewResult(status, "llm:method-review", str(llm.get("summary") or status), llm)
    has_delta = "delta" in report.lower() or packet.request.lower() in report.lower()
    has_gap = "gap" in report.lower() or "lacuna" in report.lower()
    has_next = "next" in report.lower() or "proxim" in report.lower()
    passed = has_delta and has_gap and has_next and bool(search_sources)
    summary = "Local fallback: method markers present." if passed else "Local fallback: report is missing one or more method markers."
    return ReviewResult(
        "pass" if passed else "repair_needed",
        "local:method-review",
        summary,
        {
            "summary": summary,
            "mode": "local-fallback",
            "checks": {
                "delta_or_request": has_delta,
                "gaps": has_gap,
                "next_steps": has_next,
                "search_sources": bool(search_sources),
            },
        },
    )


def summarize_reviews(reviews: list[ReviewResult]) -> str:
    return "\n".join(f"- **{review.reviewer}:** {truncate(review.summary, 500)}" for review in reviews)
