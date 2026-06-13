"""excavate — the synthetic-excavation stage (EDGE_EXCAVATE, dark by default).

The producer reads loop1's gathered evidence (often hundreds of thousands of tokens) and
writes from one lossy pass with a brevity prior: the non-obvious long tail — exactly the
worthwhile, course-changing material — dies silently in that compression. excavate inserts
between `gather-grounding` (loop1) and synthesis (loop2): it mines the evidence for the
direction-relevant findings the producer's thin summary DROPPED, and hands the producer an
accountable SEED to write from. It operationalizes the scaffold's own plenitude doctrine
(`skills/_shared/scaffold.md`: "synthesis-to-a-bite is a failure").

This is the COLLAPSED single-pass form of the synthetic grill (ADR-pending): the grill's
discipline — four probes aimed by the direction — run as one structured extraction instead
of a multi-turn agent×agent dialogue. The dialogue is the expensive escalation; this is the
cheap first cut whose lift is measurable (seed findings absent from the one-pass summary).

  - relevance     — what bears on the direction that the summary left implicit?
  - contradiction — what in the evidence undercuts the summary's own conclusion?
  - surprise      — what was expected to hold and did NOT? (the probe that earns the
                    worthwhile-test: the unseen dimension)
  - lineage       — where did a load-bearing idea actually come from?

Gated by EDGE_EXCAVATE (off => passthrough, today's behavior byte-for-byte AND zero model
spend). The model call is INJECTED (`complete_fn`) so the logic tests offline, exactly like
close.py's reviewers.
"""
from __future__ import annotations

import json
import os
import re

PROBES = ("relevance", "contradiction", "surprise", "lineage")

# A finding is only admitted if it carries all four — the claim, where it lives in the
# evidence (citation: retrieval, not paraphrase), why it bears on the direction, and which
# probe surfaced it. Anything short of that is the brevity prior leaking back in.
_REQUIRED = ("claim", "citation", "bears_on", "probe")

_TRUTHY = {"1", "true", "yes", "on"}


def enabled(env=None) -> bool:
    """Read EDGE_EXCAVATE. Dark by default — only an explicit truthy value turns it on."""
    env = os.environ if env is None else env
    return env.get("EDGE_EXCAVATE", "").strip().lower() in _TRUTHY


def _build_prompt(evidence: str, summary: str, direction: str) -> str:
    """Assemble the extraction prompt: the grill's four probes as a checklist, AIMED by the
    direction. The producer's thin summary is the map (what already surfaced); the evidence
    is the territory; the model returns only what the summary dropped."""
    probe_lines = "\n".join(
        f"- {p}: {desc}" for p, desc in (
            ("relevance", "what bears on the DIRECTION that the summary left implicit or omitted"),
            ("contradiction", "what in the evidence undercuts the summary's own conclusion"),
            ("surprise", "what one would expect to hold here but the evidence shows does NOT"),
            ("lineage", "where a load-bearing idea actually originates in the evidence"),
        )
    )
    return (
        "You are the excavation pass of a report pipeline. A producer explored a large body of "
        "evidence and wrote a THIN summary; the summary dropped the non-obvious long tail. Your "
        "job is to recover ONLY what the summary dropped that BEARS ON THE DIRECTION — never to "
        "restate the summary, never to pad.\n\n"
        f"DIRECTION (the lens — every finding must bear on this):\n{direction}\n\n"
        f"THE PRODUCER'S THIN SUMMARY (the map of what already surfaced — do NOT repeat it):\n{summary}\n\n"
        f"THE EVIDENCE (the territory — cite back into it, quote/locate, do not paraphrase):\n{evidence}\n\n"
        "Work these four probes as a checklist:\n"
        f"{probe_lines}\n\n"
        "Return STRICT JSON only, no prose:\n"
        '{"findings": [{"claim": "...", "citation": "where in the evidence", '
        '"bears_on": "how it touches the direction", "probe": "one of '
        f'{list(PROBES)}"}}], "residuals": ["open tensions you could not resolve"]}}'
    )


def _coerce_finding(item) -> dict | None:
    """Admit a finding only if it is a dict carrying all four required keys, non-empty."""
    if not isinstance(item, dict):
        return None
    if any(not str(item.get(k, "")).strip() for k in _REQUIRED):
        return None
    return {k: str(item[k]).strip() for k in _REQUIRED}


def _parse_seed(raw: str) -> dict:
    """Tolerant parse of the model's JSON seed. Strips code fences, drops malformed findings,
    never crashes on garbage — a refusal yields an empty seed, not an exception."""
    empty = {"findings": [], "residuals": []}
    if not raw or not raw.strip():
        return empty
    text = raw.strip()
    # strip a ```json ... ``` (or bare ```) fence if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    else:
        # else grab the outermost JSON object if there is leading/trailing prose
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            text = brace.group(0)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    findings = [f for f in (_coerce_finding(x) for x in data.get("findings", []) or []) if f]
    residuals = [str(r).strip() for r in (data.get("residuals", []) or []) if str(r).strip()]
    return {"findings": findings, "residuals": residuals}


def excavate(evidence: str, summary: str, direction: str, complete_fn,
             *, is_enabled=None) -> dict:
    """Run the excavation stage. OFF (default) => passthrough, ZERO model spend. ON => one
    `complete_fn(prompt)` call -> the accountable seed. `is_enabled` overrides the env flag
    (for tests / explicit callers); otherwise EDGE_EXCAVATE decides.

    `complete_fn` is the injected model call (prompt -> text), exactly like close.py's
    reviewers. NOTE: provision it generously — on a reasoning model the JSON seed runs to
    several thousand chars, and a tight `max_completion_tokens` truncates it to an empty parse.

    Returns {"enabled", "passthrough", "findings", "residuals"}."""
    on = enabled() if is_enabled is None else bool(is_enabled)
    if not on:
        return {"enabled": False, "passthrough": True, "findings": [], "residuals": []}
    raw = complete_fn(_build_prompt(evidence, summary, direction))
    seed = _parse_seed(raw)
    seed["enabled"] = True
    seed["passthrough"] = False
    return seed
