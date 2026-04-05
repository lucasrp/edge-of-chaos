"""Routine rendering — convert operator free-form prose to workflow entries.

Used by edge-apply's routine-rendering phase to materialize `routines:` from
agent.yaml as operator-authored blog entries (tag: workflow, status: approved).

Provider priority (closes #91):
    1. claude -p (Claude Code CLI)   ← preferred when binary on PATH
    2. OPENAI_API_KEY → gpt-4o-mini  ← fallback for non-Claude installs
    3. None                          ← defer to first heartbeat via pending-routines.yaml

The two providers receive the same prompt and produce the same structured
output format, so parsing is provider-agnostic. See #90 for the feature spec
and #91 for the claude-first rationale.
"""

import hashlib
import os
import re
import shutil
import subprocess


# ─── Prompt ────────────────────────────────────────────────────────────────

ROUTINE_CONVERSION_PROMPT = """You are converting an operator's free-form description of a research or work routine into a structured workflow entry. The operator's prose is verbatim text — preserve its meaning faithfully. Do not invent details the prose does not support.

Extract these fields:

1. TITLE — short (5-8 words), describes WHAT the routine is about. No leading "Workflow:".
2. TRIGGER — one declarative sentence describing WHEN to use the routine.
3. STEPS — numbered, imperative, concrete. Name specific sources/tools the prose mentions. Usually 3-6 steps.
4. WHEN_IT_WORKS — short paragraph describing the success case, ONLY if the prose states or strongly implies one. Omit if not derivable.
5. WHEN_IT_FAILS — short paragraph extracting avoidances, limitations, or fallback behaviors mentioned by the prose. This is the highest-signal piece. Omit if the prose says nothing about limits.
6. COST — extract if mentioned ("free", "paid", "API credits", specific pricing). Otherwise write "not specified".

Output EXACTLY in this format. No preamble. No commentary. No trailing text.

TITLE: <short title>
TRIGGER: <one sentence>
STEPS:
1. <step>
2. <step>
WHEN_IT_WORKS: <paragraph, or the literal string OMIT if not derivable>
WHEN_IT_FAILS: <paragraph, or the literal string OMIT if not mentioned>
COST: <cost or "not specified">

OPERATOR'S PROSE:
{prose}
"""


# ─── Public helpers ────────────────────────────────────────────────────────

def source_hash(prose: str) -> str:
    """Stable 8-char hash of the prose. Used for idempotency and edit detection."""
    return hashlib.sha256(prose.strip().encode("utf-8")).hexdigest()[:8]


def slugify_title(title: str, max_len: int = 40) -> str:
    """Filename-safe slug from the LLM-generated title."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-") or "routine"


# ─── LLM providers ─────────────────────────────────────────────────────────

def _call_claude_cli(prompt: str, timeout: int = 60) -> str | None:
    """Tier 1: Claude Code CLI in headless mode. Zero API key required.

    Spawns a NEW child session (not the parent, if edge-apply runs inside one).
    Stateless call, no context pollution."""
    if not shutil.which("claude"):
        return None
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _call_openai(prompt: str, model: str = "gpt-4o-mini", timeout: int = 60) -> str | None:
    """Tier 2: OpenAI API via openai SDK. Requires OPENAI_API_KEY."""
    if not os.environ.get("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    try:
        client = OpenAI(timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if content and content.strip():
            return content.strip()
    except Exception:
        pass
    return None


def _call_llm(prompt: str) -> tuple[str | None, str | None]:
    """Try providers in priority order. Returns (output, provider_name)."""
    out = _call_claude_cli(prompt)
    if out is not None:
        return out, "claude-cli"
    out = _call_openai(prompt)
    if out is not None:
        return out, "openai-gpt-4o-mini"
    return None, None


# ─── Output parsing ────────────────────────────────────────────────────────

_SECTION_RE = re.compile(
    r"^(TITLE|TRIGGER|STEPS|WHEN_IT_WORKS|WHEN_IT_FAILS|COST)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def _parse_llm_output(text: str) -> dict:
    """Parse the LLM's structured response into a dict.

    Expected input is the TITLE/TRIGGER/STEPS/... format produced by the
    prompt above. Robust to minor formatting variations (blank lines,
    trailing whitespace, optional colons)."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            current = m.group(1).upper()
            first = m.group(2).strip()
            sections[current] = [first] if first else []
        elif current is not None:
            sections.setdefault(current, []).append(line)

    def _joined(key: str) -> str:
        lines = sections.get(key, [])
        return "\n".join(lines).strip()

    parsed = {
        "title": _joined("TITLE").strip('"').strip() or "unnamed routine",
        "trigger": _joined("TRIGGER"),
        "steps": _joined("STEPS"),
        "when_it_works": _joined("WHEN_IT_WORKS"),
        "when_it_fails": _joined("WHEN_IT_FAILS"),
        "cost": _joined("COST") or "not specified",
    }
    # Normalize the literal "OMIT" sentinel to empty
    for opt in ("when_it_works", "when_it_fails"):
        if parsed[opt].strip().upper() == "OMIT":
            parsed[opt] = ""
    return parsed


# ─── Entry markdown builder ────────────────────────────────────────────────

def build_entry_markdown(
    prose: str,
    parsed: dict,
    source_hash_value: str,
    index: int,
    date_str: str,
    provider: str,
) -> str:
    """Assemble the blog entry markdown with frontmatter + sections.

    The original prose is preserved verbatim under `## Original (operator's words)`
    so the operator can audit the LLM's interpretation."""
    title = parsed["title"]
    trigger = parsed["trigger"] or "(not specified)"
    steps = parsed["steps"] or "(no steps extracted)"
    when_it_works = parsed["when_it_works"]
    when_it_fails = parsed["when_it_fails"]
    cost = parsed["cost"] or "not specified"

    lines = [
        "---",
        f'title: "workflow: {title}"',
        f"date: {date_str}",
        "tags: [workflow, operator-authored]",
        "status: approved",
        "authored_by: operator",
        f'source: "agent.yaml:routines[{index}]"',
        f'source_hash: "{source_hash_value}"',
        f'rendered_by: "{provider}"',
        f'trigger: "{trigger}"',
        "---",
        "",
        "## Original (operator's words)",
        "",
        prose.strip(),
        "",
        "## Steps",
        "",
        steps,
        "",
    ]

    if when_it_works:
        lines.extend(["## When it works", "", when_it_works, ""])
    if when_it_fails:
        lines.extend(["## When it fails", "", when_it_fails, ""])

    lines.extend(["## Cost", "", cost, ""])
    return "\n".join(lines)


# ─── Top-level entrypoint ──────────────────────────────────────────────────

def render_routine(prose: str) -> tuple[dict | None, str | None]:
    """Convert prose to structured fields via LLM. Returns (parsed, provider).

    Returns (None, None) if all LLM providers are unavailable or fail. In that
    case, the caller should defer to pending-routines.yaml and retry on the
    next heartbeat."""
    if not prose or not prose.strip():
        return None, None
    prompt = ROUTINE_CONVERSION_PROMPT.format(prose=prose.strip())
    output, provider = _call_llm(prompt)
    if output is None:
        return None, None
    parsed = _parse_llm_output(output)
    if not parsed.get("title") or not parsed.get("steps"):
        # Malformed output — treat as failure
        return None, None
    return parsed, provider
