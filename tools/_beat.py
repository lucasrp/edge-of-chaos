"""Beat launcher — run the beat as an agent inside Claude Code (ADR-0003).

The launcher does no cognition: it loads the /ed-beat skill body and pipes it into a single
`claude -p -` invocation. Cognition lives in the skill. Interactive dispatch does not use this
at all — the live session runs the skill in-place (never spawns claude -p).
"""
import fcntl
import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import eventlog

REPO = Path(__file__).resolve().parent.parent


@contextmanager
def heartbeat_lock(home):
    """Serialize the WHOLE heartbeat critical section {capture before_count -> run claude -p ->
    assert_beat_produced} across concurrent heartbeats (Codex gate round-4 [medium]).

    The post-dispatch gate captures a corpus count BEFORE dispatch and accepts ANY increase after
    `claude -p` returns. Under overlap that breaks: two heartbeats (or a heartbeat + another
    producer) let one invocation produce NOTHING yet pass, because another appended a kerneled
    Artefato inside its before/after window — so a corpus increase is no longer attributable to the
    invocation that produced it. Holding an exclusive `fcntl.flock` on a per-install lockfile for the
    full window (the same flock pattern as `next_producer`/`append_batch`) means the second heartbeat
    cannot begin its own before/after window until the first's gate completes: no overlap, so any
    increase is attributable to the invocation that produced it. Blocking flock is simplest + correct.
    """
    lock_path = Path(home) / "state" / "beat" / "heartbeat.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def assert_beat_produced(log, before_count) -> list:
    """The deterministic POST-DISPATCH gate (Codex gate finding [high]): a `claude -p` exit of 0
    only proves the subprocess ran — NOT that stage-(iii) corpus work happened. Folding the log is
    the only proof. Given the corpus count captured BEFORE the beat, return the list of GAPS — empty
    means the beat produced; non-empty means a beat that 'succeeded' did no real work and must fail:

      * the corpus did NOT grow by >=1 (no new Artefato was published), and/or
      * `artefatos_without_kernel(log)` is non-empty (a published Artefato with no intent kernel — C3
        debt), which is a gap even when the corpus grew.

    A pure reader over the log (no append, no claude): edge-heartbeat captures before_count, runs the
    beat, then calls this; non-empty gaps → NONZERO exit."""
    gaps = []
    after_count = len(eventlog.corpus_at(log=log))
    if after_count - before_count < 1:
        gaps.append(f"no new Artefato: corpus stayed at {after_count} (was {before_count})")
    debt = eventlog.artefatos_without_kernel(log=log)
    if debt:
        gaps.append(f"C3 debt — Artefato(s) published without an intent kernel: {debt}")
    return gaps


def next_producer(roster, state_path) -> str:
    """Advance the round-robin cursor strictly and return whose turn it is (ADR-0012).

    The beat carries ONLY rotation state — no judgment, no queue-jump. Given roster
    ["report","map","plan"] and a fresh cursor, successive calls return report, map, plan,
    report, ... The cursor (the next index to serve) is persisted to `state_path` as JSON;
    the path is injectable so tests use a temp file.

    The read-modify-write is guarded by an exclusive flock on a sibling lockfile (#6): two
    concurrent beats (the systemd timer overlapping a manual run) serialize and never read
    the same index — no lost turn.
    """
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(state_path.name + ".lock")
    with open(lock_path, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            idx = json.loads(state_path.read_text())["next"]
        except (FileNotFoundError, ValueError, KeyError):
            idx = 0
        idx %= len(roster)
        producer = roster[idx]
        state_path.write_text(json.dumps({"next": (idx + 1) % len(roster)}))
    return producer


def resolve_claude_bin() -> str:
    """Find the claude CLI: env override, then PATH, then common install locations."""
    candidates = []
    env_override = os.environ.get("EDGE_CLAUDE_BIN") or os.environ.get("CLAUDE_BIN")
    if env_override:
        candidates.append(env_override)
    path_hit = shutil.which("claude")
    if path_hit:
        candidates.append(path_hit)
    home = Path.home()
    candidates += [str(home / ".local" / "bin" / "claude"), str(home / "bin" / "claude")]
    for hit in sorted((home / ".nvm" / "versions" / "node").glob("*/bin/claude"), reverse=True):
        candidates.append(str(hit))
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    raise FileNotFoundError("claude CLI not found on PATH or common install locations")


def build_beat_command(claude_bin: str, mcp_config_path=None) -> list:
    """One beat = one single-shot `claude -p -`, permissions bypassed. No retry, no envelope.

    When `mcp_config_path` is given (Slice 6, F1), the lead beat is launched with `--mcp-config <path>`
    so the standing `cortex` read door is registered on the parent claude -p — pullable mid-turn by the
    lead AND the self-reading subagents it fans. The world-reading delta subagent is denied via its own
    skill `disallowed-tools: mcp__cortex__*` (Slice 4), so inheriting the parent server is safe. Without
    a path the command is the unchanged base single-shot invocation (backward-compatible)."""
    cmd = [claude_bin, "-p", "-", "--dangerously-skip-permissions"]
    if mcp_config_path:
        cmd += ["--mcp-config", str(mcp_config_path)]
    return cmd


def ensure_cortex_config(home, group=None):
    """Generate (idempotently) the LEAD's cortex --mcp-config for THIS install and return its path
    (Slice 6, F1/N2). A genotype path: the group resolves from identity at runtime (subject=lead, the
    granted self-cognition), so the door deploys to the fleet without an identity literal. The config
    is a RUNTIME artifact under state/cortex/ (gitignored, never committed) — it derives per install."""
    import cortex_config
    path = Path(os.path.expanduser(str(home))) / "state" / "cortex" / "lead.mcp.json"
    cortex_config.write_config(path, subject="lead", group=group, home=str(home))
    return path


def build_beat_env(home) -> dict:
    """The dispatch env = the launcher env + the install's secrets, so the beat's **agentic** source
    calls (the `via` specs in agent.yaml: exa/x/hn/arxiv/github) AND the graph leg have credentials.
    Without this the `claude -p` child inherits a key-less env and the world-leg darkens — only the
    python tools that touch `_identity` self-load secrets; the agent's own `via`-spec calls do not.
    ADR-0011: never block — a missing secrets dir just returns the base env (the leg darkens, the
    beat still runs)."""
    import _secrets
    try:
        _secrets.load_env(Path(home) / "secrets")
    except Exception:
        pass
    return dict(os.environ)


def load_beat_prompt(home) -> str:
    """The /ed-beat skill body (frontmatter stripped), piped as the prompt. home wins over repo."""
    for base in (Path(home) / "skills", REPO / "skills"):
        p = base / "beat" / "SKILL.md"
        if p.exists():
            text = p.read_text()
            if text.startswith("---"):
                parts = text.split("---", 2)
                text = parts[2] if len(parts) >= 3 else text
            return text.strip()
    raise FileNotFoundError("beat skill not found (skills/beat/SKILL.md)")
