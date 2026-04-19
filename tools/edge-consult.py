#!/usr/bin/env python3
"""
edge-consult — Cross-model deliberation tool.

Adversarial (default): finds flaws, steelmans the opposite, catches biases.
Collaborative: expands, connects, suggests unseen angles.

Supports multiple model providers: OpenAI (gpt-*), xAI (grok-*).

Usage:
    edge-consult "minha análise: X implica Y"
    edge-consult "tem furo?" --context spec.yaml notes.md
    edge-consult --model grok-4 "onde está mais fraco?"
    cat analysis.md | edge-consult "onde está mais fraco?"
    edge-consult --mode collab "que ângulos não estou vendo?"

Exit codes: 0 = success, 1 = error
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
sys.path.insert(0, str(SCRIPT_DIR))
from paths import SECRETS_DIR, LOGS_DIR  # noqa: E402  (kept for downstream consumers)
from _shared.router_client import make_client  # noqa: E402
from _shared.telemetry import log_run_step  # noqa: E402

LOG_DIR = LOGS_DIR / "consult"

# Hard timeouts to avoid silent hangs (#92). These are client-side limits on
# the HTTP call — the server may still be processing when we time out, but
# the user gets a clear exit instead of an indefinite wait.
PER_MODEL_TIMEOUT = 300  # seconds, per model call
TOTAL_TIMEOUT = 600      # seconds, total for consult() (enforced in consult())


def _progress(msg: str) -> None:
    """Emit a timestamped progress line to stderr with explicit flush.

    Writes to stderr (not stdout) so callers using `| tail` still see progress
    in real time — tail buffers stdout until EOF, stderr is unbuffered through
    pipes. Explicit flush ensures no libc line buffering under any condition.
    """
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[edge-consult] {ts} {msg}", file=sys.stderr, flush=True)


_EDGE_CONSULT_TOKEN_RE = None  # Lazy-compiled below


def _check_contention() -> list[tuple[int, str]]:
    """Return list of (pid, cmdline) for other edge-consult processes running.

    Detects the case where the fleet has multiple heartbeats calling
    edge-consult in parallel, which historically correlated with silent hangs
    (possibly rate limits or internal contention). Warns the user, does not
    block.

    Only matches processes where `edge-consult` appears as an executable token
    (argv[0] or a filesystem path ending in edge-consult/edge-consult.py) —
    not when the string merely appears inside a script passed via `python -c`.
    """
    global _EDGE_CONSULT_TOKEN_RE
    if _EDGE_CONSULT_TOKEN_RE is None:
        import re
        _EDGE_CONSULT_TOKEN_RE = re.compile(
            r'(^|\s)(?:\S*/)?edge-consult(\.py)?(\s|$)'
        )

    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ["pgrep", "-af", "edge-consult"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        others = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split(None, 1)
            if not parts or not parts[0].isdigit():
                continue
            pid = int(parts[0])
            if pid == my_pid:
                continue
            cmd = parts[1] if len(parts) > 1 else ""
            # Filter pgrep itself and shell wrappers
            if "pgrep" in cmd or cmd.strip().startswith("sh -c"):
                continue
            # Only count if edge-consult is a real executable token in the
            # command line, not a substring inside a -c "..." payload
            if not _EDGE_CONSULT_TOKEN_RE.search(cmd):
                continue
            others.append((pid, cmd))
        return others
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []

# Provider resolution delegated to _shared/router_client.py (#222). Any new
# model/endpoint is declared in agent.yaml routers: — no changes here.

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

ADVERSARIAL_SYSTEM = """\
You are a rigorous, intellectually honest critic. Your job is to find the \
flaws in the reasoning presented. Do NOT agree. Do NOT soften your critique.

## Process:

1. **Weakest premise** — Which assumption is most likely wrong? Why?
2. **Missing evidence** — What data would change the conclusion? What's absent?
3. **Steelman the opposite** — The STRONGEST argument AGAINST the conclusion.
4. **Cognitive biases** — confirmation bias, availability heuristic, anchoring, \
sunk cost, survivorship bias, false consensus. Name it, show where it operates.
5. **Breaking scenario** — Under what conditions does this fail completely?
6. **Verdict** — 1-2 sentences: the single most important thing being ignored.

## Rules:
- Be SPECIFIC. Not "this might be wrong" — exactly WHERE and WHY.
- If the reasoning is solid, say so — but still identify the weakest link.
- No flattery. No "great analysis, but...". Straight to the critique.
- PT-BR.
- 200-400 words. Dense signal, no filler."""

COLLABORATIVE_SYSTEM = """\
You are a thought partner helping explore an idea. You are NOT critiquing — \
you are EXPANDING. Add value the author couldn't generate alone.

## Process:

1. **Unseen angles** — What perspectives haven't been considered?
2. **Cross-domain connections** — Concepts from physics, biology, economics, \
game theory, design, psychology that apply here?
3. **Strengthen** — What would make this MORE compelling? What evidence?
4. **Surprising implications** — If correct, what non-obvious consequences?
5. **Adjacent questions** — What questions might be MORE important?

## Rules:
- Generative, not evaluative. Add, don't subtract.
- Bring concepts the author probably doesn't know about.
- Concrete > abstract. "Like X in Y because Z" > "consider perspectives".
- PT-BR.
- 200-400 words. Dense signal, no filler."""


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

# Provider/key resolution now lives in _shared/router_client.py (#222). See
# make_client() — it handles OpenAI-compatible endpoints, Azure, xAI, and
# anything else that speaks the OpenAI contract.


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> str:
    rates = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-5.4": (2.50, 15.00),
        "gpt-5.4-pro": (30.00, 180.00),
        "grok-4.20-multi-agent-beta-0309": (2.00, 6.00),
        "grok-4-0709": (3.00, 15.00),
        "grok-4": (3.00, 15.00),
        "grok-3": (3.00, 15.00),
    }
    input_rate, output_rate = rates.get(model, (1.0, 3.0))
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return f"${cost:.4f}"


def log_start(mode: str, question: str, context_files: list, model: str) -> Path:
    """Write a preliminary log entry with status:in_progress BEFORE the API call.

    This makes post-incident debugging possible even if the process is killed,
    the network hangs, or the LLM never responds (#92 — the original failure
    mode was invocations that left no trace at all)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_model = model.replace("/", "-").replace(".", "-")
    log_file = LOG_DIR / f"{timestamp}_{safe_model}.json"
    entry = {
        "status": "in_progress",
        "started_at": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat(),  # back-compat with old readers
        "mode": mode,
        "model": model,
        "question": question[:500],
        "context_files": context_files,
    }
    log_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))
    return log_file


def log_finish(log_file: Path, response: str, cost: str, tokens: dict) -> None:
    """Update the in-progress log with final response, cost, tokens."""
    try:
        entry = json.loads(log_file.read_text())
    except (OSError, json.JSONDecodeError):
        entry = {}
    entry.update({
        "status": "done",
        "finished_at": datetime.now().isoformat(),
        "response": response[:2000],
        "cost": cost,
        "tokens": tokens,
    })
    log_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))


def log_error(log_file: Path, error_msg: str) -> None:
    """Mark an in-progress log as failed with the error message."""
    try:
        entry = json.loads(log_file.read_text())
    except (OSError, json.JSONDecodeError):
        entry = {}
    entry.update({
        "status": "failed",
        "finished_at": datetime.now().isoformat(),
        "error": error_msg[:1000],
    })
    log_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))


# Back-compat alias — any external caller of the old name keeps working.
def log_consultation(mode: str, question: str, context_files: list,
                     response: str, model: str, cost: str, tokens: dict):
    """Deprecated: use log_start + log_finish for write-early semantics."""
    log_file = log_start(mode, question, context_files, model)
    log_finish(log_file, response, cost, tokens)


# ---------------------------------------------------------------------------
# Dual-model consultation (always both GPT + Grok)
# ---------------------------------------------------------------------------

DUAL_MODELS = ["gpt-5.4", "grok-4.20-multi-agent-beta-0309"]


def _build_user_msg(question: str, context_files: list = None,
                    stdin_content: str = None) -> str:
    """Build user message from question, context files, and stdin."""
    parts = []

    if context_files:
        for f in context_files:
            p = Path(f)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                if len(content) > 8000:
                    content = content[:8000] + f"\n\n[... truncated, {len(content)} chars total]"
                parts.append(f"--- Context: {p.name} ---\n{content}")
            else:
                parts.append(f"--- Context: {f} (file not found) ---")

    if stdin_content:
        if len(stdin_content) > 8000:
            stdin_content = stdin_content[:8000] + "\n\n[... truncated]"
        parts.append(f"--- Piped input ---\n{stdin_content}")

    parts.append(f"--- Question ---\n{question}")
    return "\n\n".join(parts)


# Models that require Responses API instead of Chat Completions
RESPONSES_API_MODELS = {"grok-4.20-multi-agent-beta-0309", "gpt-5.4-pro"}


CLAUDE_FALLBACK_MODEL = "claude-cli"


def _call_claude_cli(system: str, user_msg: str,
                     timeout: int = PER_MODEL_TIMEOUT) -> tuple[str, dict, str]:
    """Invoke the local `claude` CLI as a final adversarial reviewer (#235).

    Uses whatever auth the `claude` binary has configured — API key if the
    host is signed into Anthropic via ANTHROPIC_API_KEY, subscription (Max /
    Pro) otherwise. The caller never sees the distinction; cost accounting
    is handled by Claude itself (subscription: zero marginal cost; API:
    billed upstream on the Anthropic account).

    No new SDK dependency — this is a subprocess invocation of the same
    `claude` binary that runs the agent, so if the heartbeat works, this
    path works.
    """
    prompt = f"## System prompt\n\n{system}\n\n## User\n\n{user_msg}"
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"claude CLI not on PATH: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"claude CLI timed out after {timeout}s") from e
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        raise RuntimeError(
            f"claude CLI exited {result.returncode}: {stderr_tail or '(no stderr)'}"
        )
    text = (result.stdout or "").strip()
    if not text:
        raise RuntimeError("claude CLI produced empty output")
    # Subscription mode: no per-call token accounting surfaced to the caller.
    # API mode: tokens billed on the Anthropic account, not attributed here.
    # Keep the shape identical to other providers so callers don't branch.
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    cost = "$0.0000"
    return text, tokens, cost


def _call_model(model: str, system: str, user_msg: str,
                timeout: int = PER_MODEL_TIMEOUT) -> tuple[str, dict, str]:
    """Call a single model. Returns (response_text, tokens_dict, cost_str).

    The timeout parameter is passed to the OpenAI client constructor — any
    single HTTP call exceeding it raises APITimeoutError, which the caller
    converts to a logged failure (#92 fix 2: hard timeout default)."""
    client, _resolved_model = make_client(model=model, timeout=timeout)

    if model in RESPONSES_API_MODELS:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        result = response.output_text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        result = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    tokens = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens,
    }
    return result, tokens, cost


def consult(question: str, mode: str = "adversarial", context_files: list = None,
            stdin_content: str = None, gate_spec: str = None) -> str:
    """Send consultation to BOTH GPT-5.4 and Grok-4.20 and return combined response.

    If gate_spec is provided, saves review as {spec}.review.json for
    consolidate-state to enforce resolution before publishing.

    Progress is emitted to stderr throughout (not stdout) so callers using
    `| tail` still see live updates. Each model call has a hard timeout and
    a write-early log entry for post-incident debugging (#92).
    """
    import time
    started = time.time()
    run_id = f"consult:{uuid.uuid4().hex[:8]}"

    system = ADVERSARIAL_SYSTEM if mode == "adversarial" else COLLABORATIVE_SYSTEM
    log_run_step(
        "edge-consult",
        "consult",
        "started",
        run_id=run_id,
        mode=mode,
        context_files=len(context_files or []),
        stdin=bool(stdin_content),
        gate_spec=bool(gate_spec),
    )

    _progress(f"Building prompt (question={len(question)} chars, "
              f"context_files={len(context_files or [])}, "
              f"stdin={'yes' if stdin_content else 'no'})")
    if context_files:
        for f in context_files:
            p = Path(f)
            if p.exists():
                size = p.stat().st_size
                _progress(f"  loading context: {p.name} ({size} bytes)")
    user_msg = _build_user_msg(question, context_files, stdin_content)
    _progress(f"Prompt ready ({len(user_msg)} chars)")

    models = list(DUAL_MODELS)
    _progress(f"Calling {len(models)} models in sequence: {', '.join(models)}")

    results = []
    all_tokens = []
    all_costs = []
    # Track attempt outcomes for provenance in .review.json (#235).
    attempts = []  # list of {"model": str, "status": "ok"|"error", "error": str|None}

    context_file_strs = [str(f) for f in (context_files or [])]

    for m in models:
        # Enforce total-timeout budget across the whole consult
        elapsed = time.time() - started
        if elapsed > TOTAL_TIMEOUT:
            _progress(f"TOTAL_TIMEOUT ({TOTAL_TIMEOUT}s) reached, skipping remaining models")
            results.append((m, f"[{m} skipped: total timeout of {TOTAL_TIMEOUT}s reached]"))
            continue

        # Write-early log BEFORE the API call — if the process hangs or is
        # killed, the log still exists with status:in_progress for post-mortem.
        log_file = log_start(mode, question, context_file_strs, m)

        _progress(f"Calling {m}... (timeout {PER_MODEL_TIMEOUT}s, log: {log_file.name})")
        model_started = time.time()
        try:
            result, tokens, cost = _call_model(m, system, user_msg,
                                               timeout=PER_MODEL_TIMEOUT)
            dur = time.time() - model_started
            log_finish(log_file, result, cost, tokens)
            _progress(f"{m} ✓ {dur:.1f}s  tokens={tokens['total']}  cost={cost}")

            results.append((m, result))
            all_tokens.append(tokens)
            all_costs.append(cost)
            attempts.append({"model": m, "status": "ok", "error": None})

            # Metadata block to stderr (preserved for compatibility with
            # existing callers that scrape this format)
            mode_label = "\033[31mADVERSARIAL\033[0m" if mode == "adversarial" else "\033[36mCOLLABORATIVE\033[0m"
            print(f"\n{'='*55}", file=sys.stderr, flush=True)
            print(f"  edge-consult [{mode_label}]  ({m})", file=sys.stderr, flush=True)
            print(f"  Tokens: {tokens['total']} | Cost: {cost}", file=sys.stderr, flush=True)
            print(f"{'='*55}", file=sys.stderr, flush=True)

        except Exception as e:
            dur = time.time() - model_started
            err_msg = f"{type(e).__name__}: {e}"
            log_error(log_file, err_msg)
            _progress(f"{m} ✗ {dur:.1f}s  {err_msg}")
            results.append((m, f"[{m} error: {err_msg}]"))
            attempts.append({"model": m, "status": "error", "error": err_msg[:500]})

    # If every external model failed, fall back to the local `claude` CLI so
    # the adversarial gate still produces a real review instead of silently
    # relying on the .resolved bypass marker (#235).
    fallback_used = None
    any_ok = any(a["status"] == "ok" for a in attempts)
    if not any_ok:
        elapsed = time.time() - started
        remaining = max(30, TOTAL_TIMEOUT - int(elapsed))
        _progress(
            f"All {len(attempts)} external models failed — invoking claude CLI "
            f"fallback (#235) with {remaining}s budget"
        )
        log_file = log_start(mode, question, context_file_strs, CLAUDE_FALLBACK_MODEL)
        model_started = time.time()
        try:
            result, tokens, cost = _call_claude_cli(
                system, user_msg, timeout=min(PER_MODEL_TIMEOUT, remaining)
            )
            dur = time.time() - model_started
            log_finish(log_file, result, cost, tokens)
            _progress(f"{CLAUDE_FALLBACK_MODEL} ✓ {dur:.1f}s (fallback)")
            results.append((CLAUDE_FALLBACK_MODEL, result))
            all_tokens.append(tokens)
            all_costs.append(cost)
            attempts.append({"model": CLAUDE_FALLBACK_MODEL, "status": "ok", "error": None})
            fallback_used = CLAUDE_FALLBACK_MODEL
            mode_label = "\033[31mADVERSARIAL\033[0m" if mode == "adversarial" else "\033[36mCOLLABORATIVE\033[0m"
            print(f"\n{'='*55}", file=sys.stderr, flush=True)
            print(f"  edge-consult [{mode_label}]  ({CLAUDE_FALLBACK_MODEL}, fallback)",
                  file=sys.stderr, flush=True)
            print(f"  Cost: {cost} (subscription) | Upstream models failed",
                  file=sys.stderr, flush=True)
            print(f"{'='*55}", file=sys.stderr, flush=True)
        except Exception as e:
            dur = time.time() - model_started
            err_msg = f"{type(e).__name__}: {e}"
            log_error(log_file, err_msg)
            _progress(f"{CLAUDE_FALLBACK_MODEL} ✗ {dur:.1f}s  {err_msg}")
            results.append((CLAUDE_FALLBACK_MODEL, f"[{CLAUDE_FALLBACK_MODEL} fallback error: {err_msg}]"))
            attempts.append({"model": CLAUDE_FALLBACK_MODEL, "status": "error", "error": err_msg[:500]})

    # Combine outputs from both models
    combined = "\n\n".join(
        f"── {m} ──\n{text}" for m, text in results
    )
    ok_attempts = sum(1 for a in attempts if a["status"] == "ok")
    failed_attempts = sum(1 for a in attempts if a["status"] == "error")
    final_status = "completed" if ok_attempts else "failed"
    log_run_step(
        "edge-consult",
        "consult",
        final_status,
        run_id=run_id,
        mode=mode,
        ok_attempts=ok_attempts,
        failed_attempts=failed_attempts,
        fallback_used=bool(fallback_used),
    )

    # Gate: save combined review alongside YAML spec
    if gate_spec:
        spec_path = Path(gate_spec)
        review_path = spec_path.with_suffix(".review.json")
        resolved_path = spec_path.with_suffix(".resolved")
        if resolved_path.exists():
            resolved_path.unlink()
        total_cost = sum(
            float(c.replace("$", "")) for c in all_costs
        )
        review_data = {
            "timestamp": datetime.now().isoformat(),
            "spec": str(spec_path),
            "mode": mode,
            "models": [m for m, _ in results],
            "models_attempted": attempts,
            "fallback_used": fallback_used,
            "question": question[:500],
            "response": combined[:4000],
            "cost": f"${total_cost:.4f}",
            "resolved": False,
        }
        review_path.write_text(json.dumps(review_data, indent=2, ensure_ascii=False))
        print(f"\n  Gate review saved: {review_path}", file=sys.stderr)
        print(f"  To resolve: address feedback, then touch {resolved_path}", file=sys.stderr)

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cross-model deliberation: adversarial (default) or collaborative",
        epilog=(
            "Timing expectations: short prompts complete in ~15-45s; large --context "
            f"(>10k tokens) can take up to {PER_MODEL_TIMEOUT}s per model. Total hard "
            f"timeout is {TOTAL_TIMEOUT}s.\n\n"
            "Troubleshooting: if a call seems stuck, progress is always emitted to "
            "stderr — check the [edge-consult] HH:MM:SS lines. For piped usage, "
            "stdout is buffered until completion, but stderr is not. Use "
            "`edge-consult \"...\" 2>&1 | tee /tmp/consult.log` to see progress AND "
            "capture the full output.\n\n"
            "Post-incident debug: each model call writes an in_progress log to "
            "~/edge/logs/consult/ BEFORE the API call. If killed or hung, the log "
            "tells you what was being attempted."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("question", nargs="?", default=None,
                        help="Question or reasoning to challenge/explore")
    parser.add_argument("--mode", "-m", choices=["adversarial", "collab"],
                        default="adversarial",
                        help="Mode: adversarial (default) or collab")
    parser.add_argument("--context", "-c", nargs="+", default=None,
                        help="Context files to include")
    parser.add_argument("--gate", default=None, metavar="SPEC_PATH",
                        help="Save review as .review.json alongside SPEC_PATH for consolidate-state enforcement")
    args = parser.parse_args()

    # Read from stdin if piped
    stdin_content = None
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()

    if not args.question and not stdin_content:
        parser.error("Provide a question as argument or pipe content via stdin")

    # Pipe-to-tail warning (#92 fix 5): if stdout is a pipe, the user won't see
    # progress on stdout until the process completes. Progress goes to stderr
    # regardless, but flag this to avoid the "why is it hanging?" confusion.
    if not sys.stdout.isatty():
        print(
            "[edge-consult] NOTE: stdout is piped. Progress messages go to stderr. "
            "Use `edge-consult \"...\" 2>&1 | tee /tmp/consult.log` to see progress "
            "in real time.",
            file=sys.stderr, flush=True,
        )

    # Contention detection (#92 fix 4): warn if other edge-consult instances are
    # running. Historically correlates with silent hangs via rate limits.
    others = _check_contention()
    if others:
        _progress(
            f"WARNING: {len(others)} other edge-consult instance(s) running concurrently. "
            f"Rate limits may cause delays."
        )
        for pid, cmd in others[:3]:
            _progress(f"  pid={pid}: {cmd[:100]}")

    question = args.question or "Analyze this:"

    result = consult(
        question=question,
        mode=args.mode,
        context_files=args.context,
        stdin_content=stdin_content,
        gate_spec=args.gate,
    )

    print(result)


if __name__ == "__main__":
    main()
