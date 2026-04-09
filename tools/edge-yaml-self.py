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
    SECRETS_DIR,
    THREADS_DIR,
    ENTRIES_DIR,
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
YAML from the operator's conversation history, existing config, secrets \
(capabilities), active threads, and recent work.

## What agent.yaml IS

A phenotype document — the agent's identity, behavior, and preferences \
expressed in natural language. It tells the agent WHO it is, WHAT it \
cares about, and HOW it operates. Every field uses prose, not code.

## What agent.yaml is NOT

- NOT a config file with paths, scripts, or commands
- NOT genotype (tools, skills, blog code, search code, templates)
- NOT a place for API key values or secrets
- NOT a technical specification — it's a personality document

## CRITICAL RULES (these produce good YAMLs — domain-agnostic)

1. **Adapt to THIS operator, not a template**. The output YAML must \
reflect what this specific operator actually does, says, and uses. \
Do not invent a domain, do not assume a platform, do not project \
another agent's shape onto this one. If a section has no basis in the \
evidence you received, leave it minimal or omit it.

2. **Sources are executable primitives**. Each source maps to a CLI \
script that the agent calls to reach an external API. Name sources \
after the SERVICE they talk to, not after abstractions. A source must \
correspond to a real API the operator has credentials for — not to a \
concept, a document type, or an internal artifact.

3. **Every credential = a source**. If the evidence shows the operator \
has a credential for a service, that service MUST appear as a source. \
No capability should be left undeclared. If the evidence shows no \
credentials for a platform, do NOT invent one.

4. **Include non-secret identifiers in source descriptions**. If the \
evidence exposes IDs — account IDs, page IDs, project IDs, container \
IDs, display names, phone numbers, workspace IDs — embed them in the \
source description so the agent knows what to call. Never embed \
secrets themselves (tokens, keys, passwords).

5. **Routines reflect what the operator actually does**. Read the \
conversation history and existing YAML to understand real workflows. \
Write each routine as the operator would narrate it in first person: \
when it triggers, what the primary source is, what the fallback is, \
what to avoid. Do NOT invent workflows the evidence doesn't support.

6. **Framework infrastructure is NOT a source**. Do not list the \
framework's own tools (edge-consult, edge-signal, edge-search, \
review-gate, consolidate-state, edge-feedback-digest) or LLM providers \
(OpenAI, Grok, Anthropic) as sources. These are plumbing the agent \
uses through skills, not external APIs it declares.

7. **Preserve REAL current config values**. If an existing agent.yaml \
exists, keep its blog_port, blog_host, heartbeat_interval, \
blog_auth_user, language, and other configured values — do NOT copy \
from the example or invent new ones. Only change config values when \
the operator explicitly said to.

8. **pre_skill_context is DOMAIN knowledge**, not framework plumbing. \
Guardrails, audience, compliance rules, stakeholders, platform risks \
specific to THIS agent's domain. Never mention edge-digest, boot \
ritual, consolidate-state, or any framework tool.

9. **pre_skill_procedure is what to CHECK** before each beat in \
natural language ("verify operator messages", "confirm campaigns are \
running", "check if regulatory change happened"). NOT framework calls.

10. **No guessing beyond evidence**. If you don't have evidence for \
something, either leave it out or mark it clearly as a placeholder the \
operator needs to fill. Better to produce a shorter accurate YAML than \
a longer fabricated one.

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
branding_dir: "<path to branding assets dir, optional — omit if no custom branding>"

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


ID_SUFFIXES = (
    "_ID", "_CUSTOMER_ID", "_ACCOUNT_ID", "_PAGE_ID", "_PAGE_NAME",
    "_WABA_ID", "_PHONE_NUMBER_ID", "_DISPLAY_NUMBER", "_VERIFIED_NAME",
    "_WORKSPACE_ID", "_CONTAINER_ID", "_MCC_ID", "_DATASET_ID",
    "_USERNAME", "_PROFILE", "_BUCKET", "_REGION", "_PROJECT_ID",
)

# Patterns that look like API key names (for discovery on foreign machines)
KEY_NAME_PATTERNS = (
    "_API_KEY", "_ACCESS_TOKEN", "_BOT_TOKEN", "_APP_TOKEN", "_SECRET",
    "_API_SECRET", "_CLIENT_SECRET", "_CLIENT_ID", "_TOKEN",
    "_BEARER_TOKEN", "_APP_ID", "_APP_SECRET", "_DEVELOPER_TOKEN",
    "_REFRESH_TOKEN",
)


def _parse_env_file(path: Path) -> tuple[list[str], list[str]]:
    """Parse an env file, return (key_names, id_lines)."""
    key_names = []
    ids = []
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key or not key[0].isalpha():
                continue
            # Heuristic: looks like a credential variable name
            if key.isupper() and (
                any(p in key for p in KEY_NAME_PATTERNS)
                or any(key.endswith(s) for s in ID_SUFFIXES)
            ):
                key_names.append(key)
                # Only expose values for identifiers, never for secrets
                if any(key.endswith(s) for s in ID_SUFFIXES) and len(val) < 200:
                    ids.append(f"  {key}={val}")
    except Exception:
        pass
    return key_names, ids


def read_capabilities(context_dir: Path | None = None) -> str:
    """Discover API keys and IDs from multiple locations.

    Search order:
      1. SECRETS_DIR/keys.env (and other .env files there) — inside a
         running edge-of-chaos install
      2. context_dir/*.env if the operator passed --context-dir
      3. ~/.env and ~/secrets/*.env — common places on foreign machines
      4. Environment variables in os.environ — currently exported keys
      5. Shell rc files (~/.bashrc, ~/.zshrc, ~/.profile) for exported
         credentials — best effort, may miss

    Returns a formatted block listing capabilities. Key names become
    sources (one per service the agent has credentials for). ID-style
    values (account IDs, usernames, project IDs) are included so the
    LLM can embed them in source descriptions; secrets themselves are
    NEVER exposed to the LLM.
    """
    all_keys = []
    all_ids = []
    sources_found = []

    candidates: list[Path] = []

    # 1. edge-of-chaos install (preferred)
    if SECRETS_DIR.exists():
        candidates.extend(SECRETS_DIR.glob("*.env"))

    # 2. operator-provided context directory
    if context_dir and context_dir.exists():
        candidates.extend(context_dir.glob("*.env"))
        candidates.extend(context_dir.rglob("keys.env"))

    # 3. common fresh-install locations
    home = Path.home()
    fresh_paths = [
        home / ".env",
        home / ".envrc",
        home / "secrets" / "keys.env",
    ]
    for p in fresh_paths:
        if p.exists() and p not in candidates:
            candidates.append(p)
    # Also scan ~/secrets/*.env if the dir exists
    secrets_home = home / "secrets"
    if secrets_home.exists() and secrets_home.is_dir():
        for p in secrets_home.glob("*.env"):
            if p not in candidates:
                candidates.append(p)

    for path in candidates:
        keys, ids = _parse_env_file(path)
        if keys:
            sources_found.append(str(path))
            all_keys.extend(keys)
            all_ids.extend(ids)

    # 4. live environment variables — currently exported credentials
    env_keys = []
    env_ids = []
    for key, val in os.environ.items():
        if not key.isupper() or not key[0].isalpha():
            continue
        if any(p in key for p in KEY_NAME_PATTERNS) or any(
            key.endswith(s) for s in ID_SUFFIXES
        ):
            env_keys.append(key)
            if any(key.endswith(s) for s in ID_SUFFIXES) and len(val) < 200:
                env_ids.append(f"  {key}={val}")
    if env_keys:
        sources_found.append("os.environ")
        all_keys.extend(env_keys)
        all_ids.extend(env_ids)

    # 5. shell rc files (best effort, dedup against env)
    rc_files = [home / ".bashrc", home / ".zshrc", home / ".profile",
                home / ".bash_profile"]
    for rc in rc_files:
        if not rc.exists():
            continue
        try:
            for line in rc.read_text().splitlines():
                line = line.strip()
                if not line.startswith("export "):
                    continue
                pair = line[len("export "):].strip()
                if "=" not in pair:
                    continue
                key = pair.split("=", 1)[0].strip()
                if key.isupper() and (
                    any(p in key for p in KEY_NAME_PATTERNS)
                    or any(key.endswith(s) for s in ID_SUFFIXES)
                ):
                    all_keys.append(key)
            sources_found.append(str(rc))
        except Exception:
            continue

    if not all_keys:
        return ""

    lines = [
        f"Discovered from: {', '.join(sorted(set(sources_found)))}",
        "",
        "Available API keys (each = a capability the agent has):",
    ]
    lines.extend(f"  {k}" for k in sorted(set(all_keys)))
    if all_ids:
        lines.append("")
        lines.append("Non-secret identifiers to embed in source descriptions:")
        lines.extend(sorted(set(all_ids)))
    return "\n".join(lines)


def read_threads_summary(context_dir: Path | None = None) -> str:
    """Read thread frontmatter from edge install or context_dir."""
    candidates: list[Path] = []
    if THREADS_DIR.exists():
        candidates.extend(THREADS_DIR.glob("*.md"))
    if context_dir and context_dir.exists():
        threads_sub = context_dir / "threads"
        if threads_sub.exists():
            candidates.extend(threads_sub.glob("*.md"))
    if not candidates:
        return ""

    lines = []
    for f in sorted(set(candidates)):
        try:
            raw = f.read_text()
            parts = raw.split("---", 2)
            if len(parts) < 3:
                continue
            fm_text = parts[1]
            title = status = ""
            for fm_line in fm_text.splitlines():
                if fm_line.startswith("title:"):
                    title = fm_line.split(":", 1)[1].strip().strip('"')
                elif fm_line.startswith("status:"):
                    status = fm_line.split(":", 1)[1].strip()
            if title and status in ("active", "waiting"):
                lines.append(f"  - [{status}] {title}")
        except Exception:
            continue
    if not lines:
        return ""
    return "Active investigation threads:\n" + "\n".join(lines)


def read_recent_blog_titles(limit: int = 20,
                             context_dir: Path | None = None) -> str:
    """Read recent blog entry titles from edge install or context_dir."""
    candidates: list[Path] = []
    if ENTRIES_DIR.exists():
        candidates.extend(ENTRIES_DIR.glob("*.md"))
    if context_dir and context_dir.exists():
        for sub in ("blog/entries", "entries", "blog"):
            d = context_dir / sub
            if d.exists():
                candidates.extend(d.glob("*.md"))
                break
    if not candidates:
        return ""

    entries = sorted(
        set(candidates),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    titles = []
    for f in entries:
        try:
            for line in f.read_text().splitlines()[:15]:
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if title:
                        titles.append(f"  - {title}")
                    break
        except Exception:
            continue
    if not titles:
        return ""
    return (
        f"Recent blog entries (what the agent actually works on, "
        f"last {len(titles)}):\n" + "\n".join(titles)
    )


def discover_project_docs(context_dir: Path | None = None) -> str:
    """Find CLAUDE.md, README.md, and similar context docs anywhere useful.

    For fresh installs on foreign machines, these often hold the clearest
    picture of what the user works on. Search:
      - ~/CLAUDE.md, ~/work/CLAUDE.md, ~/projects/CLAUDE.md
      - ~/.claude/CLAUDE.md
      - context_dir/CLAUDE.md, context_dir/README.md
      - Top-level README.md in home directory project folders

    Returns concatenated excerpts (truncated per file).
    """
    home = Path.home()
    candidates: list[Path] = []

    doc_names = ["CLAUDE.md", "README.md", "readme.md", "AGENT.md", "agent.md"]

    # 1. Claude Code globals
    claude_dir = home / ".claude"
    if claude_dir.exists():
        for name in ("CLAUDE.md",):
            p = claude_dir / name
            if p.exists():
                candidates.append(p)

    # 2. Home and common project dirs
    for base in (home, home / "work", home / "projects", home / "dev",
                 home / "repos", home / "code"):
        if not base.exists():
            continue
        for name in doc_names:
            p = base / name
            if p.exists():
                candidates.append(p)
        # Also peek into immediate subdirectories for per-project docs
        if base.is_dir():
            try:
                for child in sorted(base.iterdir())[:20]:
                    if child.is_dir() and not child.name.startswith("."):
                        for name in doc_names:
                            p = child / name
                            if p.exists():
                                candidates.append(p)
                                break
            except (PermissionError, OSError):
                continue

    # 3. operator-provided context
    if context_dir and context_dir.exists():
        for name in doc_names:
            p = context_dir / name
            if p.exists():
                candidates.append(p)
        # also recurse one level
        try:
            for child in context_dir.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    for name in doc_names:
                        p = child / name
                        if p.exists():
                            candidates.append(p)
                            break
        except (PermissionError, OSError):
            pass

    if not candidates:
        return ""

    lines = ["Project docs found on this machine:"]
    MAX_PER_FILE = 800
    MAX_TOTAL = 6000
    total = 0
    seen = set()
    for p in candidates:
        if p in seen:
            continue
        seen.add(p)
        if total >= MAX_TOTAL:
            break
        try:
            content = p.read_text(errors="ignore")[:MAX_PER_FILE]
        except Exception:
            continue
        rel = str(p).replace(str(home), "~")
        lines.append(f"\n--- {rel} ---")
        lines.append(content)
        total += len(content)
    return "\n".join(lines)



def discover_git_repos(limit: int = 10) -> str:
    """List top-level git repos in common project dirs.

    Repos often reveal what the user works on, even when there's no
    agent.yaml or CLAUDE.md. Just the names and branches is enough signal.
    """
    home = Path.home()
    found = []
    for base in (home / "work", home / "projects", home / "dev",
                 home / "repos", home / "code"):
        if not base.exists() or not base.is_dir():
            continue
        try:
            for child in sorted(base.iterdir())[:30]:
                if not child.is_dir() or child.name.startswith("."):
                    continue
                if (child / ".git").exists():
                    found.append(str(child).replace(str(home), "~"))
                if len(found) >= limit:
                    break
        except (PermissionError, OSError):
            continue
        if len(found) >= limit:
            break
    if not found:
        return ""
    return "Git repositories found:\n" + "\n".join(f"  - {f}" for f in found)


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
        description="Generate a DRAFT agent.yaml from user data. Always "
                    "writes to agent.yaml.draft — never touches agent.yaml "
                    "directly. Operator must review and copy explicitly."
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
    parser.add_argument("--context-dir", type=str, default=None,
                        help="Additional directory to scan for env files, "
                             "threads, and blog entries (for installs "
                             "outside of ~/edge/)")
    parser.add_argument("--output", type=str, default=None,
                        help="Override output path (default: agent.yaml.draft)")
    args = parser.parse_args()

    context_dir = Path(os.path.expanduser(args.context_dir)) if args.context_dir else None

    # Step 1: Gather data
    watermark = 0 if args.force else read_watermark()
    entries = read_history(watermark, args.window)
    feedback = read_feedback_digest()
    chat = read_chat_messages()
    existing_yaml = "" if args.fresh else read_existing_yaml()
    capabilities = read_capabilities(context_dir)
    threads_summary = read_threads_summary(context_dir)
    blog_titles = read_recent_blog_titles(context_dir=context_dir)
    project_docs = discover_project_docs(context_dir)

    if not entries and not feedback and not chat and not existing_yaml:
        _progress("No user data found. Cannot generate YAML.")
        print("ERROR: no user data (history.jsonl, feedback-digest, chat, agent.yaml)")
        sys.exit(1)

    _progress(f"Data sources: "
              f"history={len(entries)} entries, "
              f"digest={'yes' if feedback else 'no'}, "
              f"chat={'yes' if chat else 'no'}, "
              f"existing={'yes' if existing_yaml else 'no'}, "
              f"capabilities={'yes' if capabilities else 'no'}, "
              f"threads={'yes' if threads_summary else 'no'}, "
              f"blog={'yes' if blog_titles else 'no'}, "
              f"docs={'yes' if project_docs else 'no'}")

    # Step 2: Build prompt
    parts = []

    if existing_yaml:
        parts.append(
            "## Existing agent.yaml (merge with this — keep valid, update stale)\n\n"
            "IMPORTANT: preserve blog_port, blog_host, heartbeat_interval, "
            "blog_auth_user, language, and other config values from this "
            "file unless the operator explicitly said to change them. Do "
            "NOT copy values from any example.\n\n"
            f"```yaml\n{existing_yaml}\n```"
        )
    else:
        parts.append(
            "## Existing agent.yaml\n\n"
            "(none — generating from scratch)"
        )

    if capabilities:
        parts.append(
            "## Capabilities discovered\n\n"
            "These are credentials the operator has configured on this "
            "machine. Each unique service represented here MUST become a "
            "source in the output YAML — no capability should be left "
            "undeclared. Embed the non-secret identifiers below inside "
            "source descriptions so the agent knows what to call.\n\n"
            f"{capabilities}"
        )

    if threads_summary:
        parts.append(
            "## Current investigations\n\n"
            "These are what the agent is actively working on. Use them to "
            "shape interests, routines, and short_term_goal.\n\n"
            f"{threads_summary}"
        )

    if blog_titles:
        parts.append(
            "## Recent work\n\n"
            "What the agent has been producing — use to calibrate voice, "
            "interests, and operational focus.\n\n"
            f"{blog_titles}"
        )

    if feedback:
        parts.append(
            "## Feedback digest (compiled priorities, corrections, decisions)\n\n"
            f"{feedback}"
        )

    if entries:
        formatted = format_entries(entries)
        parts.append(
            f"## Conversation history (PRIMARY SOURCE — {len(entries)} entries)\n\n"
            "This is the most important evidence you have. The operator's "
            "actual words, in their own voice, describing what they want, "
            "what they correct, and how they work. Anchor the YAML in what "
            "they have actually SAID. Scanning files and credentials is a "
            "secondary signal — conversation history is primary.\n\n"
            f"{formatted}"
        )

    if chat:
        parts.append(
            f"## Async chat messages\n\n{chat}"
        )

    if project_docs:
        parts.append(
            "## Project docs found on this machine\n\n"
            "These files exist in the home directory or project folders. "
            "Use them as CONTEXT to corroborate what the conversation says, "
            "not as the authoritative source. If a doc conflicts with the "
            "conversation history, the conversation wins.\n\n"
            f"{project_docs}"
        )

    parts.append(
        "## Task\n\n"
        "Produce a COMPLETE agent.yaml DRAFT. All sections, natural "
        "language throughout. No code, no paths, no scripts. Output ONLY "
        "the YAML (no markdown fences, no explanation before or after). "
        "The operator will review this draft before applying — do not try "
        "to be diplomatic or hedge. Be specific and grounded in evidence. "
        "Anything you cannot ground in the evidence, leave out."
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

    # Step 4: Write output — ALWAYS draft unless operator overrides
    # NEVER touch agent.yaml directly. The operator must review and
    # apply explicitly.
    if args.output:
        output_path = Path(os.path.expanduser(args.output))
    else:
        output_path = AGENT_YAML.with_suffix(".yaml.draft")

    # Refuse to overwrite agent.yaml unless operator explicitly pointed --output there
    if output_path == AGENT_YAML:
        _progress(
            "REFUSING to write directly to agent.yaml. This tool only "
            "produces drafts. Use --output agent.yaml.draft (default) "
            "and review before applying manually."
        )
        print("ERROR: refusing to overwrite agent.yaml. Generate a draft, "
              "review it, then apply manually.")
        sys.exit(2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml_content + "\n")

    # Update watermark
    if entries:
        last_ts = max(e["timestamp"] for e in entries) / 1000
        write_watermark(last_ts)

    log_run(len(entries), args.model, meta, True)

    _progress(f"DRAFT written to {output_path}")
    print(f"OK: {len(entries)} entries + "
          f"{'digest' if feedback else 'no digest'} + "
          f"{'chat' if chat else 'no chat'} → {output_path.name} "
          f"({meta.get('duration_s', '?')}s, {args.model})")
    print()
    print("NEXT STEP: Review the draft. When satisfied, apply manually:")
    print(f"  diff agent.yaml {output_path.name}")
    print(f"  cp {output_path.name} agent.yaml")
    print("Never auto-apply. The draft is a proposal, not a decision.")


if __name__ == "__main__":
    main()
