#!/usr/bin/env python3
"""edge-feedback-digest — LLM-compiled digest of user conversations.

Reads Claude conversation history, combines with previous digest,
and uses an external LLM (GPT 5.4 / Grok 4.20) to produce a rolling
"gold feedback" digest: the authoritative source of user intent,
corrections, priorities, and decisions.

Designed to be called as a step by heartbeat, ed-report, or any skill
that needs fresh user context. Not a standalone skill.

Usage:
  edge-feedback-digest              # default model (GPT 5.4)
  edge-feedback-digest --model grok-4.20-multi-agent-beta-0309
  edge-feedback-digest --dry-run    # show prompt, don't call LLM
  edge-feedback-digest --window 72  # hours of history to include (default: 48)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import (
    FEEDBACK_DIGEST_FILE,
    FEEDBACK_WATERMARK,
    STATE_DIR,
    LOGS_DIR,
)

sys.path.insert(0, str(SCRIPT_DIR))
from _shared.openai_client import make_openai_client, load_openai_env

HOME = Path.home()
HISTORY_FILE = HOME / ".claude" / "history.jsonl"
LOG_DIR = LOGS_DIR / "feedback-digest"

DEFAULT_MODEL = os.environ.get("EDGE_MODEL_FEEDBACK", "gpt-5.4")
DEFAULT_WINDOW_HOURS = 48
MAX_ENTRIES = 200  # cap to avoid token blowup
MAX_CHARS_PER_ENTRY = 500  # truncate long user inputs

# Provider configs (same as edge-consult)
PROVIDERS = {
    "gpt": {
        "env_var": "OPENAI_API_KEY",
        "base_url": None,
    },
    "grok": {
        "env_var": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
    },
}

RESPONSES_API_MODELS = {"grok-4.20-multi-agent-beta-0309", "gpt-5.4-pro"}

SYSTEM_PROMPT = """\
You are an analyst extracting actionable intelligence from a user's \
conversation history with their AI assistant. Your job is to compile a \
structured digest that captures what the user WANTS, THINKS, and DECIDED.

You receive:
1. A previous digest (rolling context from prior runs — may be empty)
2. New conversation entries (user inputs only, timestamped)

Produce an updated digest in markdown with these sections:

## Priorities
What the user is currently focused on. Ordered by recency and emphasis.

## Corrections & Feedback
Things the user corrected, rejected, or pushed back on. These are gold — \
they reveal preferences that aren't written anywhere.

## Decisions Made
Explicit choices the user made ("let's do X", "use Y instead", "drop Z").

## Open Questions
Things the user asked about but didn't resolve, or expressed uncertainty about.

## Mood & Satisfaction
Brief read on the user's tone — frustrated, exploring, in flow, blocked. \
One sentence.

## Meta
- Conversations processed: N sessions, N entries
- Time window: [start] to [end]
- Model used: [model]

Rules:
- MERGE with the previous digest, don't replace — keep valid older items, \
update or remove stale ones.
- Be SPECIFIC. Quote the user when relevant ("user said: '...'").
- Prioritize RECENT over old. If something from 3 days ago contradicts \
something from today, today wins.
- Keep each section to 3-7 items max. Compress older items.
- Language: match the user's language (likely pt-br or en). If mixed, use \
the language they used most recently.
- 400-800 words total. Dense signal, no filler."""


def _progress(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[edge-feedback-digest] {ts} {msg}", file=sys.stderr, flush=True)


def load_api_key(model: str) -> tuple[str, str | None]:
    """Load API key for model. Returns (api_key, base_url)."""
    load_openai_env()
    for prefix, config in PROVIDERS.items():
        if model.startswith(prefix):
            key = os.environ.get(config["env_var"])
            if key:
                return key, config["base_url"]
            raise RuntimeError(
                f"{config['env_var']} not found for {model}"
            )
    # Fallback to OpenAI
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key, None
    raise RuntimeError(f"No API key found for model {model}")


def read_watermark() -> float:
    """Read last processed timestamp. Returns 0 if no watermark."""
    if FEEDBACK_WATERMARK.exists():
        try:
            return float(FEEDBACK_WATERMARK.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def write_watermark(ts: float) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    FEEDBACK_WATERMARK.write_text(str(ts))


def read_previous_digest() -> str:
    """Read previous feedback digest if it exists."""
    if FEEDBACK_DIGEST_FILE.exists():
        return FEEDBACK_DIGEST_FILE.read_text()
    return ""


def read_history(since_ts: float, window_hours: int) -> list[dict]:
    """Read conversation entries from history.jsonl.

    Filters by watermark AND window_hours (whichever is more recent).
    Groups implicitly by sessionId for context.
    """
    if not HISTORY_FILE.exists():
        _progress(f"No history file at {HISTORY_FILE}")
        return []

    cutoff_ms = since_ts * 1000  # history uses ms timestamps
    window_cutoff_ms = (time.time() - window_hours * 3600) * 1000
    effective_cutoff = max(cutoff_ms, window_cutoff_ms)

    entries = []
    with open(HISTORY_FILE) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", 0)
                if ts > effective_cutoff:
                    text = entry.get("display", "").strip()
                    if text and len(text) > 3:  # skip trivial inputs
                        entries.append({
                            "text": text[:MAX_CHARS_PER_ENTRY],
                            "timestamp": ts,
                            "session": entry.get("sessionId", "?"),
                            "project": entry.get("project", "?"),
                        })
            except json.JSONDecodeError:
                continue

    # Cap to most recent MAX_ENTRIES
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    return entries


def format_entries_for_prompt(entries: list[dict]) -> str:
    """Format entries into a readable block for the LLM prompt."""
    if not entries:
        return "(no new conversation entries)"

    lines = []
    current_session = None
    for e in entries:
        ts = datetime.fromtimestamp(e["timestamp"] / 1000)
        ts_str = ts.strftime("%Y-%m-%d %H:%M")

        if e["session"] != current_session:
            current_session = e["session"]
            project = Path(e["project"]).name if e["project"] != "?" else "?"
            lines.append(f"\n--- Session ({project}) ---")

        lines.append(f"[{ts_str}] {e['text']}")

    return "\n".join(lines)


def call_llm(model: str, user_msg: str) -> tuple[str, dict]:
    """Call LLM and return (response_text, metadata)."""
    api_key, base_url = load_api_key(model)
    client = make_openai_client(api_key=api_key, timeout=120, base_url=base_url)

    _progress(f"Calling {model}...")
    started = time.time()

    if model in RESPONSES_API_MODELS:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
        result = response.output_text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
        result = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    duration = time.time() - started
    meta = {
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "duration_s": round(duration, 1),
    }
    _progress(f"{model} done in {duration:.1f}s "
              f"(tokens: {prompt_tokens}+{completion_tokens})")
    return result, meta


def log_run(entries_count: int, model: str, meta: dict, success: bool,
            error: str = "") -> None:
    """Log run metadata for observability."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "entries_processed": entries_count,
        "model": model,
        "success": success,
        "error": error,
        **meta,
    }
    log_file = LOG_DIR / f"{ts}.json"
    log_file.write_text(json.dumps(log_entry, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="LLM-compiled digest of user conversations"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_HOURS,
                        help=f"Hours of history to include (default: {DEFAULT_WINDOW_HOURS})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling LLM")
    parser.add_argument("--force", action="store_true",
                        help="Ignore watermark, reprocess full window")
    args = parser.parse_args()

    # Step 1: Determine what's new
    watermark = 0 if args.force else read_watermark()
    entries = read_history(watermark, args.window)

    if not entries:
        _progress("No new conversation entries since last run. Skipping.")
        print("OK: no new entries")
        return

    _progress(f"Found {len(entries)} new entries")

    # Step 2: Build prompt
    previous_digest = read_previous_digest()
    formatted_entries = format_entries_for_prompt(entries)

    user_msg_parts = []
    if previous_digest:
        user_msg_parts.append(
            f"## Previous digest\n\n{previous_digest}"
        )
    else:
        user_msg_parts.append(
            "## Previous digest\n\n(first run — no previous digest)"
        )

    user_msg_parts.append(
        f"## New conversation entries ({len(entries)} entries)\n\n"
        f"{formatted_entries}"
    )
    user_msg = "\n\n---\n\n".join(user_msg_parts)

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(SYSTEM_PROMPT)
        print("\n=== USER MESSAGE ===")
        print(user_msg)
        print(f"\n=== Would call: {args.model} ===")
        print(f"=== Entries: {len(entries)} ===")
        return

    # Step 3: Call LLM
    try:
        result, meta = call_llm(args.model, user_msg)
    except Exception as e:
        _progress(f"LLM call failed: {e}")
        log_run(len(entries), args.model, {}, False, str(e))
        sys.exit(1)

    # Step 4: Write outputs
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    FEEDBACK_DIGEST_FILE.write_text(result)

    # Watermark = timestamp of last processed entry
    last_ts = max(e["timestamp"] for e in entries) / 1000
    write_watermark(last_ts)

    log_run(len(entries), args.model, meta, True)

    _progress(f"Digest written to {FEEDBACK_DIGEST_FILE}")
    print(f"OK: {len(entries)} entries → {FEEDBACK_DIGEST_FILE.name} "
          f"({meta.get('duration_s', '?')}s, {args.model})")


if __name__ == "__main__":
    main()
