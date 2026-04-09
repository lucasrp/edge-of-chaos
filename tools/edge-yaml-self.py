#!/usr/bin/env python3
"""edge-yaml-self — auto-generate agent.yaml from user data.

Reads Claude Code conversation history, feedback digest, and existing
agent.yaml, then uses an external LLM to produce a complete phenotype
YAML. The agent writes its own identity from what the operator actually
said — natural language throughout, no genotype references.

Usage:
  edge-yaml-self                    # merge with existing agent.yaml
  edge-yaml-self --fresh            # ignore existing, generate from scratch
  edge-yaml-self --dry-run          # show what would be generated
  edge-yaml-self --model grok-4.20-multi-agent-beta-0309
  edge-yaml-self --window 96        # hours of history (default: 72)
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import (
    EDGE_DIR,
    FEEDBACK_DIGEST_FILE,
    STATE_DIR,
    LOGS_DIR,
)

sys.path.insert(0, str(SCRIPT_DIR))
from _shared.openai_client import make_openai_client, load_openai_env

HOME = Path.home()
HISTORY_FILE = HOME / ".claude" / "history.jsonl"
AGENT_YAML = EDGE_DIR / "agent.yaml"
WATERMARK_FILE = STATE_DIR / "yaml-self-watermark"
LOG_DIR = LOGS_DIR / "yaml-self"

DEFAULT_MODEL = os.environ.get("EDGE_MODEL_YAML", "gpt-5.4")
DEFAULT_WINDOW_HOURS = 72
MAX_ENTRIES = 300
MAX_CHARS_PER_ENTRY = 600

# Provider configs (same pattern as edge-consult / edge-feedback-digest)
PROVIDERS = {
    "gpt": {"env_var": "OPENAI_API_KEY", "base_url": None},
    "grok": {"env_var": "XAI_API_KEY", "base_url": "https://api.x.ai/v1"},
}

RESPONSES_API_MODELS = {"grok-4.20-multi-agent-beta-0309", "gpt-5.4-pro"}

SYSTEM_PROMPT = """\
You are an expert at writing agent.yaml files for the edge-of-chaos \
autonomous agent framework. Your job is to produce a COMPLETE phenotype \
YAML from the operator's conversation history and (optionally) an existing YAML.

## What agent.yaml IS

A phenotype document — the agent's identity, behavior, and preferences \
expressed in natural language. It tells the agent WHO it is, WHAT it \
cares about, and HOW it operates. Every field uses prose, not code.

## What agent.yaml is NOT

- NOT a config file with paths, scripts, or commands
- NOT genotype (tools, skills, blog code, search code, templates)
- NOT a place for API key values or secrets
- NOT a technical specification — it's a personality document

## YAML structure (produce ALL these sections)

```yaml
# --- Identity (REQUIRED) ---
name: <full agent name>
codename: <short name>
mission: |
  <2-4 sentences: what this agent does, how it thinks, its role>
voice: "<how it communicates — tone, style, constraints>"
domain: "<primary domain of expertise>"

# --- Short-term goal ---
short_term_goal: |
  <what to focus on RIGHT NOW — extract from recent conversations>

# --- Interests ---
interests:
  - area: "<topic>"
    connection: "<why this matters to this agent — 1-2 sentences>"

# --- Routines (prose only — describe HOW the agent works) ---
routines:
  - |
    <paragraph describing a recurring workflow in natural language>

# --- Sources (what external data the agent uses) ---
sources:
  - name: <source_name>
    description: "<what it's for and why this agent uses it>"

# --- First steps (bootstrap on first heartbeat) ---
first_steps:
  - "<natural language instruction>"

# --- Defaults ---
language: <en|pt-br|etc>
skill_prefix: "<codename>"
tool_prefix: edge
edge_home: "~/edge/"
heartbeat_interval: <Nh>
blog_port: <port>
blog_host: "0.0.0.0"
blog_auth_enabled: true
blog_auth_user: "<user>"
blog_auth_pass: "<pass>"

# --- Pre-skill context (guardrails and identity) ---
pre_skill_context:
  - |
    <natural language guardrail or identity statement>

# --- Pre-skill procedure (boot ritual) ---
pre_skill_procedure:
  - |
    <natural language description of what to do before every beat>

# --- Post-skill ---
post_skill:
  - |
    <natural language description of what to do after every beat>

# --- Onboarding ---
onboarding_mode: <true|false>

# --- Fleet peers ---
fleet_peers:
  <codename>:
    role: "<what they do>"
    access: "<how to reach them>"
    usage: "<relationship to this agent>"

# --- Optional ---
bio: "<one-line bio>"
public_url: "<if any>"
repo_owner: "<github owner>"
repo_name: "<github repo>"

# --- LLM Models ---
openai_model: "<model>"
openai_model_mini: "<model>"
grok_model: "<model>"
image_model: "<model>"
```

## Rules

1. EVERYTHING is natural language. No file paths, no script names, no \
   shell commands, no code snippets anywhere in the YAML.
2. Routines describe BEHAVIOR ("When researching, I start by..."), not \
   instructions ("Run edge-search, then call arXiv API").
3. Pre-skill context contains PRINCIPLES and GUARDRAILS in prose.
4. Pre-skill procedure describes the RITUAL in prose ("Before every \
   beat, I refresh my briefing, scan external sources, update threads").
5. Sources list WHAT and WHY, not HOW (no API endpoints, no auth details).
6. If merging with an existing YAML, preserve valid entries and update \
   based on what the operator said. Recent operator statements override \
   older YAML content.
7. Interests should have a `connection` field explaining WHY the agent \
   cares — not just "it's interesting."
8. Be SPECIFIC. Use the operator's own words and priorities, not generic \
   descriptions.
9. Produce the COMPLETE YAML — all sections, no placeholders, no TODOs.
10. Fleet peers: include only agents actually mentioned in conversations.
11. The comment header at the top should identify the agent and the \
    schema version. Keep it brief.
12. Do NOT include API key sections or comments about secrets."""


def _progress(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[edge-yaml-self] {ts} {msg}", file=sys.stderr, flush=True)


def load_api_key(model: str) -> tuple[str, str | None]:
    load_openai_env()
    for prefix, config in PROVIDERS.items():
        if model.startswith(prefix):
            key = os.environ.get(config["env_var"])
            if key:
                return key, config["base_url"]
            raise RuntimeError(f"{config['env_var']} not found for {model}")
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key, None
    raise RuntimeError(f"No API key found for model {model}")


def read_watermark() -> float:
    if WATERMARK_FILE.exists():
        try:
            return float(WATERMARK_FILE.read_text().strip())
        except (ValueError, OSError):
            pass
    return 0


def write_watermark(ts: float) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    WATERMARK_FILE.write_text(str(ts))


def read_history(since_ts: float, window_hours: int) -> list[dict]:
    """Read conversation entries from Claude Code history.jsonl."""
    if not HISTORY_FILE.exists():
        _progress(f"No history file at {HISTORY_FILE}")
        return []

    cutoff_ms = since_ts * 1000
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
                    if text and len(text) > 3:
                        entries.append({
                            "text": text[:MAX_CHARS_PER_ENTRY],
                            "timestamp": ts,
                            "session": entry.get("sessionId", "?"),
                            "project": entry.get("project", "?"),
                        })
            except json.JSONDecodeError:
                continue

    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]
    return entries


def read_feedback_digest() -> str:
    if FEEDBACK_DIGEST_FILE.exists():
        return FEEDBACK_DIGEST_FILE.read_text()
    return ""


def read_existing_yaml() -> str:
    if AGENT_YAML.exists():
        return AGENT_YAML.read_text()
    return ""


def format_entries(entries: list[dict]) -> str:
    if not entries:
        return "(no conversation entries)"

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


def read_chat_messages() -> str:
    """Read async chat messages from blog DB if available."""
    import sqlite3
    db_path = EDGE_DIR / "search" / "edge-memory.db"
    if not db_path.exists():
        return ""
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT author, text, ts FROM chat WHERE author='user' "
            "ORDER BY ts DESC LIMIT 50"
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        lines = [f"[{r[2]}] {r[1][:400]}" for r in reversed(rows)]
        return "\n".join(lines)
    except Exception:
        return ""


def call_llm(model: str, user_msg: str) -> tuple[str, dict]:
    api_key, base_url = load_api_key(model)
    client = make_openai_client(api_key=api_key, timeout=180, base_url=base_url)

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


def extract_yaml(text: str) -> str:
    """Extract YAML from LLM response, stripping markdown fences."""
    lines = text.strip().splitlines()
    # Remove leading/trailing ```yaml fences
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def log_run(entries_count: int, model: str, meta: dict, success: bool,
            error: str = "") -> None:
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
        description="Auto-generate agent.yaml from user data"
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW_HOURS,
                        help=f"Hours of history (default: {DEFAULT_WINDOW_HOURS})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling LLM")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore existing agent.yaml, generate from scratch")
    parser.add_argument("--force", action="store_true",
                        help="Ignore watermark, reprocess full window")
    parser.add_argument("--output", type=str, default=None,
                        help="Write to a different file instead of agent.yaml")
    args = parser.parse_args()

    # Step 1: Gather data
    watermark = 0 if args.force else read_watermark()
    entries = read_history(watermark, args.window)
    feedback = read_feedback_digest()
    chat = read_chat_messages()
    existing_yaml = "" if args.fresh else read_existing_yaml()

    if not entries and not feedback and not chat:
        _progress("No user data found. Cannot generate YAML.")
        print("ERROR: no user data (history.jsonl, feedback-digest, chat)")
        sys.exit(1)

    source_count = sum([
        1 if entries else 0,
        1 if feedback else 0,
        1 if chat else 0,
    ])
    _progress(f"Data sources: {source_count} "
              f"(history={len(entries)} entries, "
              f"digest={'yes' if feedback else 'no'}, "
              f"chat={'yes' if chat else 'no'})")

    # Step 2: Build prompt
    parts = []

    if existing_yaml:
        parts.append(
            "## Existing agent.yaml (merge with this — keep valid, update stale)\n\n"
            f"```yaml\n{existing_yaml}\n```"
        )
    else:
        parts.append(
            "## Existing agent.yaml\n\n"
            "(none — generating from scratch)"
        )

    if feedback:
        parts.append(
            "## Feedback digest (compiled priorities, corrections, decisions)\n\n"
            f"{feedback}"
        )

    if entries:
        formatted = format_entries(entries)
        parts.append(
            f"## Conversation history ({len(entries)} entries)\n\n"
            f"{formatted}"
        )

    if chat:
        parts.append(
            f"## Async chat messages\n\n{chat}"
        )

    parts.append(
        "## Task\n\n"
        "Produce a COMPLETE agent.yaml. All sections, natural language "
        "throughout. No code, no paths, no scripts. Output ONLY the YAML "
        "(no markdown fences, no explanation before or after)."
    )

    user_msg = "\n\n---\n\n".join(parts)

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(SYSTEM_PROMPT)
        print(f"\n=== USER MESSAGE ({len(user_msg)} chars) ===")
        print(user_msg[:3000])
        if len(user_msg) > 3000:
            print(f"\n... ({len(user_msg) - 3000} more chars)")
        print(f"\n=== Would call: {args.model} ===")
        return

    # Step 3: Call LLM
    try:
        result, meta = call_llm(args.model, user_msg)
    except Exception as e:
        _progress(f"LLM call failed: {e}")
        log_run(len(entries), args.model, {}, False, str(e))
        sys.exit(1)

    yaml_content = extract_yaml(result)

    # Step 4: Write output
    output_path = Path(args.output) if args.output else AGENT_YAML
    output_path.write_text(yaml_content + "\n")

    # Update watermark
    if entries:
        last_ts = max(e["timestamp"] for e in entries) / 1000
        write_watermark(last_ts)

    log_run(len(entries), args.model, meta, True)

    _progress(f"YAML written to {output_path}")
    print(f"OK: {len(entries)} entries + "
          f"{'digest' if feedback else 'no digest'} + "
          f"{'chat' if chat else 'no chat'} → {output_path.name} "
          f"({meta.get('duration_s', '?')}s, {args.model})")


if __name__ == "__main__":
    main()
