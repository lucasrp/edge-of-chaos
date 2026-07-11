"""Session reader + delta — the raw layer of the measure-first spike (ADR-0004 decision A).

A transcript is the non-lossy raw: one `.jsonl` = one session. Claude Code remains the original
store/format; Codex and Grok are additional surfaces normalized into the same Turn(role, text)
shape. This module discovers sessions and parses ordered dialogue deltas since a watermark. It is
locator/offset-based, carrying no semantics (ADR-0001).
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROLES = {"user": "human", "assistant": "edge"}
CODEX_ROLES = {"user": "human", "assistant": "edge"}
GROK_ROLES = {"user": "human", "assistant": "edge"}
_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
SCAFFOLDING_PREFIXES = (
    "<environment_context>",
    "<skill>",
    "<subagent_notification>",
    "<task-notification>",
    "<command-message>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<request-interrupted>",
    "<interrupted-user>",
    "<turn_aborted>",
    "<task>",
    "Base directory for this skill:",
    "This session is being continued from a previous conversation",
    "<system-reminder>",
    "<user_info>",
)


@dataclass(frozen=True)
class Session:
    """One transcript: an id, its path, and the surface that wrote it."""
    id: str
    path: Path
    surface: str = "claude"


@dataclass(frozen=True)
class Turn:
    """One dialogue turn: who spoke (`human`/`edge`) and what they said (text only)."""
    role: str
    text: str


def list_sessions(project_dir) -> list:
    """Discover sessions: every `.jsonl` in the project dir is one session."""
    return [Session(id=p.stem, path=p) for p in Path(project_dir).glob("*.jsonl")]


def codex_sessions_dir():
    """The Codex transcript root. Env → agent.yaml surfaces.codex → ~/.codex/sessions."""
    import surfaces_cfg
    return surfaces_cfg.surface_sessions_dir("codex") or (Path.home() / ".codex" / "sessions")


def codex_session_anchor(session_id: str) -> str:
    return session_id if session_id.startswith("codex:") else f"codex:{session_id}"


def grok_session_anchor(session_id: str) -> str:
    return session_id if session_id.startswith("grok:") else f"grok:{session_id}"


def split_session_anchor(session_id):
    if isinstance(session_id, str) and session_id.startswith("codex:"):
        raw = session_id[len("codex:"):]
        return ("codex", raw) if raw else (None, None)
    if isinstance(session_id, str) and session_id.startswith("grok:"):
        raw = session_id[len("grok:"):]
        return ("grok", raw) if raw else (None, None)
    return ("claude", session_id) if isinstance(session_id, str) and session_id else (None, None)


def current_session_anchor(env=None):
    """Live session anchor: Claude first, then Codex, then Grok, else None.

    Grok CLI does not export GROK_SESSION_ID; when unset, resolve from
    active_sessions.json (pid match / parent chain, else sole entry).
    """
    env = os.environ if env is None else env
    sid = env.get("CLAUDE_CODE_SESSION_ID")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    for key in ("CODEX_THREAD_ID", "CODEX_SESSION_ID"):
        sid = env.get(key)
        if isinstance(sid, str) and sid.strip():
            return codex_session_anchor(sid.strip())
    sid = env.get("GROK_SESSION_ID")
    if isinstance(sid, str) and sid.strip():
        return grok_session_anchor(sid.strip())
    live = resolve_grok_live_session_id(env=env)
    if live:
        return grok_session_anchor(live)
    return None


def grok_active_sessions_path(env=None) -> Path:
    """Path to Grok's live active_sessions.json (env → agent.yaml → ~/.grok/...)."""
    import surfaces_cfg
    env = os.environ if env is None else env
    return (surfaces_cfg.surface_active_sessions_path("grok", env=env)
            or (Path.home() / ".grok" / "active_sessions.json"))


def _ancestor_pids(start_pid=None):
    """Yield this process id and its parent chain (Linux /proc)."""
    pid = os.getpid() if start_pid is None else int(start_pid)
    seen = set()
    # Never yield pid 1 (init) — every process ancestry ends there and would false-match.
    while pid and pid > 1 and pid not in seen:
        seen.add(pid)
        yield pid
        try:
            with open(f"/proc/{pid}/status") as fh:
                ppid = None
                for line in fh:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        break
            if ppid is None or ppid == pid:
                break
            pid = ppid
        except (OSError, ValueError):
            break


def resolve_grok_live_session_id(env=None, path=None, pid=None):
    """Resolve the live Grok session_id from active_sessions.json.

    Real shape: [{"session_id", "pid", "cwd", "opened_at"}, ...]. Prefer an entry
    whose pid is this process or an ancestor; if exactly one entry exists, use it
    carefully as a sole-entry fallback. Multiple unmatched entries → None.
    """
    path = Path(path) if path is not None else grok_active_sessions_path(env)
    try:
        data = json.loads(Path(path).read_text(errors="replace"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, list):
        return None
    entries = []
    for e in data:
        if not isinstance(e, dict):
            continue
        sid = e.get("session_id")
        if isinstance(sid, str) and sid.strip():
            entries.append(e)
    if not entries:
        return None
    ancestors = set(_ancestor_pids(pid))
    for e in entries:
        try:
            ep = int(e.get("pid"))
        except (TypeError, ValueError):
            continue
        if ep in ancestors:
            return e["session_id"].strip()
    if len(entries) == 1:
        return entries[0]["session_id"].strip()
    return None


def grok_sessions_dir():
    """The Grok transcript root. Env → agent.yaml surfaces.grok → ~/.grok/sessions."""
    import surfaces_cfg
    return surfaces_cfg.surface_sessions_dir("grok") or (Path.home() / ".grok" / "sessions")


def _grok_summary(path) -> dict:
    """Sibling summary.json next to chat_history.jsonl (best-effort)."""
    summary = Path(path).parent / "summary.json"
    try:
        if summary.is_file():
            data = json.loads(summary.read_text(errors="replace"))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _grok_session_id(path) -> str:
    """Grok stores chat_history.jsonl under <cwd-encoded>/<session-id>/; id is the dir name,
    optionally confirmed by summary.json."""
    data = _grok_summary(path)
    info = data.get("info") if isinstance(data, dict) else None
    if isinstance(info, dict) and isinstance(info.get("id"), str) and info["id"].strip():
        return info["id"].strip()
    return Path(path).parent.name


def list_grok_sessions(root=None) -> list:
    """Discover Grok sessions via chat_history.jsonl. [] means the optional store is dark."""
    root = grok_sessions_dir() if root is None else Path(root)
    if not root.is_dir():
        return []
    return [Session(id=_grok_session_id(p), path=p, surface="grok")
            for p in sorted(root.rglob("chat_history.jsonl"))]


def find_grok_session(session_id, root=None):
    """Locate one Grok session by raw id or grok:<id> anchor."""
    _surface, raw = split_session_anchor(session_id)
    if not raw:
        return None
    for session in list_grok_sessions(root):
        if session.id == raw:
            return session
    return None


def _codex_session_id(path) -> str:
    """Codex filenames include timestamps; the stable session id lives in session_meta when present."""
    p = Path(path)
    try:
        for line in p.read_text(errors="replace").splitlines()[:20]:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") == "session_meta":
                payload = obj.get("payload") or {}
                if isinstance(payload.get("id"), str) and payload["id"].strip():
                    return payload["id"].strip()
    except OSError:
        pass
    return p.stem


def list_codex_sessions(root=None) -> list:
    """Discover Codex sessions recursively. [] means the optional Codex store is absent/dark."""
    root = codex_sessions_dir() if root is None else Path(root)
    if not root.is_dir():
        return []
    return [Session(id=_codex_session_id(p), path=p, surface="codex")
            for p in sorted(root.rglob("*.jsonl"))]


def find_codex_session(session_id, root=None):
    """Locate one Codex session by raw id or codex:<id> anchor."""
    _surface, raw = split_session_anchor(session_id)
    if not raw:
        return None
    for session in list_codex_sessions(root):
        if session.id == raw:
            return session
    return None


def codex_session_meta(path) -> dict:
    """Best-effort session_meta for a Codex transcript."""
    try:
        for line in Path(path).read_text(errors="replace").splitlines()[:40]:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") == "session_meta":
                payload = obj.get("payload") or {}
                return payload if isinstance(payload, dict) else {}
    except OSError:
        pass
    return {}


def claude_is_sidechain(path) -> bool:
    """True for Claude subagent/sidechain transcripts."""
    p = Path(path)
    if "subagents" in p.parts:
        return True
    try:
        for line in p.read_text(errors="replace").splitlines()[:40]:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("isSidechain") is True:
                return True
    except OSError:
        pass
    return False


_AGENT_LAUNCH_PATTERNS = tuple(re.compile(p, re.IGNORECASE | re.DOTALL) for p in (
    r"^you are the prototype producer for this run\.",
    r"^you are (?:an|a|the) .{0,80}?(?:subagent|explorer|producer|worker|"
    r"triage verification agent|world-reading explorer|ed-explorer)\b",
    r"^you are drafting the new report skill\b",
    r"^you are operating on `?ssh roberto\b",
    r"^read-only exploration of\b",
    r"^experiment arm \d+\b",
    r"^produce a research artifact on\b",
    r"^adversarial (?:design )?review\b",
    r"^correctness review of\b",
    r"^meta-gate\b",
    r"^you are the meta-gate\b",
    r"^you are (?:the|a|an) (?:adversarial|gate|reviewer|judge)\b",
    r"^você é o meta-gate\b",
    r"^você é o ed (?:construindo|executando|rodando|fechando|operando)\b",
    r"^você é (?:o|a) (?:adversarial|gate|revisor|juiz)\b",
    r"^você é um(?:a)? (?:produtor|subagente|agente)\b",
    r"^gate final do motor integrado\b",
))


def looks_agent_launched_prompt(text) -> bool:
    """Conservative prompt-shape detector for one agent spawning another as a worker.

    This is not a classifier for content about agents. It only catches strong launch prompts that
    assign a worker role/ticket. Casual operator prompts like "vc é o fable..." are intentionally
    left alone.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    head = re.sub(r"\s+", " ", text).strip()[:1200]
    return any(p.search(head) for p in _AGENT_LAUNCH_PATTERNS)


def _strip_user_query(text: str) -> str:
    """Grok wraps operator text in <user_query>; return the inner body when present."""
    if not isinstance(text, str) or not text:
        return ""
    m = _USER_QUERY_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _first_human_text(path, surface="claude") -> str:
    """First raw human/user message, before scaffolding filters."""
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if surface == "codex":
            if obj.get("type") != "response_item":
                continue
            payload = obj.get("payload") or {}
            if payload.get("type") == "message" and payload.get("role") == "user":
                return _text_of(payload.get("content")).strip()
        elif surface == "grok":
            if obj.get("type") != "user" or obj.get("synthetic_reason"):
                continue
            return _strip_user_query(_text_of(obj.get("content")))
        elif obj.get("type") == "user":
            return _text_of(obj.get("message", {}).get("content")).strip()
    return ""


def user_session_exclusion_reason(session: Session) -> str | None:
    """Return why this transcript is not a direct operator session, else None.

    The edge's memory should index operator-facing conversations. Agent-to-agent worker sessions
    remain useful execution trace, but they are not the default recall corpus.
    """
    if session.surface == "codex":
        meta = codex_session_meta(session.path)
        if meta.get("thread_source") and meta.get("thread_source") != "user":
            return f"codex-thread-source:{meta.get('thread_source')}"
        if meta.get("parent_thread_id"):
            return "codex-parent-thread"
        source = meta.get("source")
        if isinstance(source, dict) and source.get("subagent"):
            return "codex-subagent"
    elif session.surface == "grok":
        if "subagents" in Path(session.path).parts:
            return "grok-subagent"
        # Real Grok stores workers as session_kind in sibling summary.json (not a path part).
        kind = _grok_summary(session.path).get("session_kind")
        if isinstance(kind, str) and kind.strip():
            k = kind.strip()
            if k.lower() not in {"user", "operator"}:
                return f"grok-session-kind:{k}"
    else:
        if claude_is_sidechain(session.path):
            return "claude-sidechain"

    first = _first_human_text(session.path, surface=session.surface)
    if looks_agent_launched_prompt(first):
        return "agent-launch-prompt"
    return None


def is_user_session(session: Session) -> bool:
    return user_session_exclusion_reason(session) is None


def _text_of(content) -> str:
    """The human-readable text of a message: the joined text blocks (or a bare string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict)
                       and b.get("type") in ("text", "input_text", "output_text"))
    return ""


def _claude_turn_from_obj(obj):
    role = ROLES.get(obj.get("type"))
    if not role:
        return None
    text = _text_of(obj.get("message", {}).get("content")).strip()
    if _is_scaffolding_turn(role, text):
        return None
    return Turn(role=role, text=text) if text else None


def _is_scaffolding_turn(role, text):
    if role != "human":
        return False
    return any(text.startswith(p) for p in SCAFFOLDING_PREFIXES) or looks_agent_launched_prompt(text)


def _codex_turn_from_obj(obj):
    if obj.get("type") != "response_item":
        return None
    payload = obj.get("payload") or {}
    if payload.get("type") != "message":
        return None
    role = CODEX_ROLES.get(payload.get("role"))
    if not role:
        return None
    text = _text_of(payload.get("content")).strip()
    if not text or _is_scaffolding_turn(role, text):
        return None
    return Turn(role=role, text=text)


def _grok_turn_from_obj(obj):
    """One Grok chat_history line → Turn, or None for synthetic/tool/system noise."""
    if not isinstance(obj, dict):
        return None
    if obj.get("synthetic_reason"):
        return None
    role = GROK_ROLES.get(obj.get("type"))
    if not role:
        return None
    text = _text_of(obj.get("content")).strip()
    if role == "human":
        text = _strip_user_query(text)
    if not text or _is_scaffolding_turn(role, text):
        return None
    return Turn(role=role, text=text)


def _turns_from_lines(lines, surface="claude") -> list:
    """Parse raw transcript lines into ordered human/edge dialogue turns, dropping noise.
    A corrupt/truncated line (a session written mid-sweep, a crashed writer) is dropped as
    noise — one bad line must never kill the whole sweep."""
    turns = []
    if surface == "codex":
        turn_from_obj = _codex_turn_from_obj
    elif surface == "grok":
        turn_from_obj = _grok_turn_from_obj
    else:
        turn_from_obj = _claude_turn_from_obj
    for line in lines:
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        turn = turn_from_obj(obj)
        if turn is not None:
            turns.append(turn)
    return turns


def read_turns(path, surface="claude") -> list:
    """Parse a transcript into ordered human/edge dialogue turns."""
    return _turns_from_lines(Path(path).read_text(errors="replace").splitlines(), surface=surface)


@dataclass(frozen=True)
class Claim:
    """A discrete assertion about the mentee or the work, mined from a session's dialogue."""
    text: str


_CLAIM_PROMPT = """\
Below is the text dialogue of one work session between a person (human) and their mentor (edge).
Extract the discrete claims it asserts about the person or their work — decisions, preferences,
facts, and stated hypotheses. One claim per item. Reply ONLY a JSON array of strings.

DIALOGUE:
{dialogue}"""


def extract_claims(turns, complete_fn) -> list:
    """Mine a session's discrete claims, agentically, via an injected LLM `complete_fn`."""
    dialogue = "\n".join(f"{t.role}: {t.text}" for t in turns)
    raw = complete_fn(_CLAIM_PROMPT.format(dialogue=dialogue))
    return [Claim(text=c) for c in json.loads(raw)]


KINDS = ("replacement", "duplicate", "divergence", "novel")


@dataclass(frozen=True)
class Classification:
    """A claim labelled against prior state — the G5 distinction (time vs meaning)."""
    text: str
    kind: str


_CLASSIFY_PROMPT = """\
A mentor holds this STATE of claims about a person and their work:
{state}

A new work session asserts these NEW claims:
{new}

Label each NEW claim against the STATE, exactly one of:
- "replacement": a clean factual update of a state claim (the old fact is now wrong)
- "duplicate": restates a state claim, no new information
- "divergence": shifts meaning/interpretation (hypothesis, irony, self-image) without cleanly
  replacing a fact — the two coexist in tension
- "novel": unrelated to anything in the state

Reply ONLY a JSON array of {{"text": <claim>, "kind": <label>}}, one per NEW claim, in order."""


def classify_session(state, new_claims, complete_fn) -> list:
    """Label each new claim against the accumulated state in one batched LLM call."""
    raw = complete_fn(_CLASSIFY_PROMPT.format(
        state="\n".join(f"- {s}" for s in state) or "(empty)",
        new="\n".join(f"- {c.text}" for c in new_claims)))
    return [Classification(text=o["text"], kind=o["kind"]) for o in json.loads(raw)]


def run_spike(sessions_turns, extract_fn, classify_fn) -> dict:
    """Walk sessions oldest->newest: classify each against the state grown so far, then fold
    its claims into the state. Returns the G5 measurement over all classifications."""
    state = []
    labelled = []
    for turns in sessions_turns:
        claims = extract_fn(turns)
        labelled.extend(classify_fn(state, claims))
        state.extend(c.text for c in claims)
    return measure(labelled)


def measure(classifications) -> dict:
    """Aggregate labels into the G5 verdict: `time` (replacement+duplicate, Zep solves) vs
    `meaning` (divergence, Zep does not solve — grill-me's domain). Novel is excluded."""
    counts = {k: 0 for k in KINDS}
    for c in classifications:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    time = counts["replacement"] + counts["duplicate"]
    meaning = counts["divergence"]
    return {"counts": counts, "verdict": "time" if time > meaning else "meaning"}


def delta(path, since_line: int, surface="claude"):
    """The turns after a raw-line watermark, with the new watermark (total line count).

    Transcripts are append-only, so the watermark is the count of raw lines already seen.
    A truncated FINAL line (a writer flushing mid-sweep) is NOT consumed by the watermark —
    when the writer completes it, the next sweep re-reads it (non-lossy raw). A corrupt
    interior line is a crashed writer: dropped and consumed (`_turns_from_lines`)."""
    lines = Path(path).read_text(errors="replace").splitlines()
    watermark = len(lines)
    new = lines[since_line:]
    if new:
        try:
            json.loads(new[-1])
        except ValueError:
            watermark -= 1          # leave the half-flushed tail for the next sweep
            new = new[:-1]
    return _turns_from_lines(new, surface=surface), watermark
