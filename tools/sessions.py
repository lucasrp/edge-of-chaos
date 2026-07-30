"""Session reader + delta — the raw layer of the measure-learn spike (ADR-0004 decision A).

A transcript is the non-lossy raw: one `.jsonl` = one session. **Three operator surfaces** —
Claude Code, Codex, and Grok — normalize into the same ``Turn(role, text)`` shape.

**Dialogue filter (rationalizer / quente / employment film):** the operator-visible corpus is
exactly the Claude Code UI filter “conversation without terminals” — **user + assistant prose
only**. Tool calls, tool results, queue/attachment noise, synthetic Grok lines, and delegated
sessions identified by surface provenance are dropped *before* any a-posteriori cognition. That is the
pre-processing step: dialogue first, then mentee-employment policy (not agent meta).

Locator/offset-based; carries no domain semantics beyond surface normalization (ADR-0001).
"""
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# Legacy file-backed surfaces; Hermes is virtual and accepted separately by the normalizer.
SURFACES = ("claude", "codex", "grok")

ROLES = {"user": "human", "assistant": "edge"}
CODEX_ROLES = {"user": "human", "assistant": "edge"}
GROK_ROLES = {"user": "human", "assistant": "edge"}
_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
SCAFFOLDING_PREFIXES = (
    "[IMPORTANT: Background process ",
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
    "AUTHORITATIVE DISPATCH PLAN (mechanical; do not override):",
)
AUTOMATED_SESSION_PREFIXES = (
    "AUTHORITATIVE DISPATCH PLAN (mechanical; do not override):",
)


@dataclass(frozen=True)
class Session:
    """One transcript: an id, its path, and the surface that wrote it."""
    id: str
    path: Path
    surface: str = "claude"
    updated_at: str | None = None
    profile_name: str | None = None


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

    Real shape: [{"session_id", "pid", "cwd", "opened_at"}, ...]. Return only an
    entry whose pid is this process or an ancestor. Never invent identity from a
    sole unmatched entry (stale PID would stamp false session_id on dispatch.open).
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


def _strip_user_query(text: str) -> str:
    """Grok wraps operator text in <user_query>; return the inner body when present."""
    if not isinstance(text, str) or not text:
        return ""
    m = _USER_QUERY_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _first_human_text(path, surface="claude") -> str:
    """First human/user message after exact surface scaffolding envelopes."""
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
                text = _text_of(payload.get("content")).strip()
                if any(text.startswith(prefix) for prefix in AUTOMATED_SESSION_PREFIXES):
                    return text
                if not any(text.startswith(prefix) for prefix in SCAFFOLDING_PREFIXES):
                    return text
        elif surface == "grok":
            if obj.get("type") != "user" or obj.get("synthetic_reason"):
                continue
            text = _strip_user_query(_text_of(obj.get("content")))
            if any(text.startswith(prefix) for prefix in AUTOMATED_SESSION_PREFIXES):
                return text
            if not any(text.startswith(prefix) for prefix in SCAFFOLDING_PREFIXES):
                return text
        elif obj.get("type") == "user":
            origin = obj.get("origin")
            if obj.get("isMeta") is True or obj.get("promptSource") == "system":
                continue
            if (isinstance(origin, dict) and origin.get("kind") is not None
                    and origin.get("kind") != "human"):
                continue
            text = _text_of(obj.get("message", {}).get("content")).strip()
            if any(text.startswith(prefix) for prefix in AUTOMATED_SESSION_PREFIXES):
                return text
            if not any(text.startswith(prefix) for prefix in SCAFFOLDING_PREFIXES):
                return text
    return ""


# Veredito por (path, mtime, size) — um wake classifica a MESMA sessão até 3x
# (baseline, registro de exclusão, plano); o conteúdo só muda se mtime/size mudarem.
_EXCLUSION_CACHE: dict = {}
_DIALOGUE_CACHE: dict = {}


def user_session_exclusion_reason(session: Session, install_birth=None) -> str | None:
    """Return why this transcript is not a direct operator session, else None.

    The edge's memory should index operator-facing conversations. Agent-to-agent worker sessions
    remain useful execution trace, but they are not the default recall corpus.

    ``install_birth`` (epoch): sessão que PRE-DATA o nascimento do install não pode ser
    trabalho delegado do edge — o edge nem existia (caso edgesandbox 2026-07-25: as únicas
    sessões codex do mentee, sem session_meta do CLI antigo, caíam em unknown-provenance e
    o backfill filmava zero). Só suaviza os vereditos *unknown-provenance* (ausência de
    marcador); marcador POSITIVO de delegação (source:exec, subagent, thread-source) segue
    excluindo em qualquer época."""
    try:
        st = Path(session.path).stat()
        key = (str(session.path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None and key in _EXCLUSION_CACHE:
        reason = _EXCLUSION_CACHE[key]
    else:
        reason = _user_session_exclusion_reason(session)
        if key is not None:
            _EXCLUSION_CACHE[key] = reason
    if reason is not None and install_birth:
        if reason in ("codex-unknown-provenance", "grok-unknown-provenance"):
            try:
                if Path(session.path).stat().st_mtime < float(install_birth):
                    reason = None
            except OSError:
                pass
    if reason is not None:
        return reason
    # Piso de DIÁLOGO (#153) — última porta de TODA inclusão: voz é conversa, e conversa
    # tem ≥2 turnos humanos substantivos. One-shot de driver (`claude -p`, prompt-file)
    # tem exatamente 1 turno "humano" (o prompt do agente) e passava como voz — num host
    # de agente isso virou 812 falsas-vozes num estimate. Early-exit em 2; cache por
    # (path, mtime, size) como o veredito.
    if key is not None and key in _DIALOGUE_CACHE:
        ok = _DIALOGUE_CACHE[key]
    else:
        human_turns = 0
        try:
            for turn in read_turns(session.path, surface=session.surface):
                if turn.role == "human" and turn.text.strip():
                    human_turns += 1
                    if human_turns >= 2:
                        break
        except Exception:
            human_turns = 0
        ok = human_turns >= 2
        if key is not None:
            _DIALOGUE_CACHE[key] = ok
    return None if ok else f"{session.surface}-sem-dialogo"


def _user_session_exclusion_reason(session: Session) -> str | None:
    grok_unmarked = False
    if session.surface == "codex":
        meta = codex_session_meta(session.path)
        # Finding A / gate P1: fail closed without authoritative operator provenance.
        # Missing session_meta or non-user thread_source is not "probably the operator".
        if not meta:
            return "codex-unknown-provenance"
        # Marcador POSITIVO de delegação: outro harness dirigindo o codex (ex.
        # originator="Claude Code" via plugin). Não é ausência de prova — é prova
        # de agente-a-agente; a suavização pré-nascimento NUNCA se aplica aqui
        # (caso edgesandbox 2026-07-25: os turnos "user" eram o claude falando).
        originator = str(meta.get("originator") or "").strip()
        if originator and originator.lower().replace(" ", "_") not in (
                "codex", "codex_cli", "codex_exec"):
            return f"codex-originator:{originator.lower().replace(' ', '-')}"
        thread_source = meta.get("thread_source")
        if thread_source != "user":
            if isinstance(thread_source, str) and thread_source.strip():
                return f"codex-thread-source:{thread_source}"
            return "codex-unknown-provenance"
        if meta.get("parent_thread_id"):
            return "codex-parent-thread"
        source = meta.get("source")
        # Codex one-shot/delegated work can report thread_source=user. ``source=exec`` is the
        # authoritative transport provenance; the wording of its generated prompt is irrelevant.
        if source == "exec":
            return "codex-source:exec"
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
            grok_unmarked = True
    else:
        if claude_is_sidechain(session.path):
            return "claude-sidechain"

    first = _first_human_text(session.path, surface=session.surface)
    if any(first.startswith(prefix) for prefix in AUTOMATED_SESSION_PREFIXES):
        return "automated-session-envelope"
    # (piso de diálogo aplicado no invólucro — vale para TODO caminho de inclusão,
    # inclusive unknown-provenance suavizado pelo pré-nascimento)
    del grok_unmarked
    return None


def is_user_session(session: Session, install_birth=None) -> bool:
    return user_session_exclusion_reason(session, install_birth=install_birth) is None


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
    if role == "human":
        origin = obj.get("origin")
        if obj.get("isMeta") is True or obj.get("promptSource") == "system":
            return None
        if (isinstance(origin, dict) and origin.get("kind") is not None
                and origin.get("kind") != "human"):
            return None
    text = _text_of(obj.get("message", {}).get("content")).strip()
    if _is_scaffolding_turn(role, text):
        return None
    return Turn(role=role, text=text) if text else None


def _is_scaffolding_turn(role, text):
    """Drop exact UI/skill protocol envelopes; never classify by conversation vocabulary."""
    return any(text.startswith(p) for p in SCAFFOLDING_PREFIXES)


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


def _normalize_surface(surface) -> str:
    s = (surface or "claude").strip().lower()
    if s not in (*SURFACES, "hermes"):
        raise ValueError(f"surface must be one of {(*SURFACES, 'hermes')}, got {surface!r}")
    return s


def _turns_from_lines(lines, surface="claude") -> list:
    """Parse raw transcript lines into ordered human/edge dialogue turns, dropping noise.

    Drops (all surfaces): tool_use / tool_result / function_call / queue / attachment /
    synthetic Grok / non-message Codex items / scaffolding prefixes / agent-launch human prompts.
    A corrupt/truncated line is dropped — one bad line must never kill the whole sweep.
    """
    surface = _normalize_surface(surface)
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


def dialogue_turns(path, surface="claude") -> list:
    """Operator-visible dialogue for Claude Code / Codex / Grok (no terminals, no tools).

    This is the pre-processing the racionalizador (and quente) consume: same intent as the
    Claude Code UI filter that shows only user↔assistant chat. Returns ``Turn`` list with
    roles ``human`` | ``edge`` only.
    """
    surface = _normalize_surface(surface)
    return _turns_from_lines(
        Path(path).read_text(errors="replace").splitlines(), surface=surface
    )


def hermes_state_db(cfg=None, agent_yaml=None, env=None) -> Path:
    import surfaces_cfg
    return surfaces_cfg.surface_home("hermes", cfg=cfg, agent_yaml=agent_yaml, env=env) / "state.db"


def _hermes_target(path):
    db, session_id = str(path).rsplit("#", 1)
    return Path(db), session_id


def _hermes_connect(path):
    return sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)


def list_hermes_sessions(root=None, cfg=None, agent_yaml=None, env=None) -> list:
    db = hermes_state_db(cfg, agent_yaml, env) if root is None else Path(root)
    if db.is_dir():
        db /= "state.db"
    if not db.is_file():
        return []
    with _hermes_connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
        profile = "s.profile_name" if "profile_name" in columns else "NULL"
        rows = conn.execute(f"""SELECT s.id, MAX(m.timestamp), {profile} FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.id AND m.active = 1
                AND m.role IN ('user', 'assistant')
            GROUP BY s.id, {profile} ORDER BY MAX(m.timestamp), s.id""")
        return [Session(id, Path(f"{db}#{id}"), "hermes", updated_at,
                        profile_name or "default")
                for id, updated_at, profile_name in rows]


def updated_epoch(session) -> float:
    """Normalize Hermes REAL timestamps and older ISO-text stores."""
    try:
        return float(session.updated_at)
    except (TypeError, ValueError):
        from datetime import datetime
        return datetime.fromisoformat(str(session.updated_at).replace("Z", "+00:00")).timestamp()


def read_turns(path, surface="claude") -> list:
    """Parse a transcript into ordered human/edge dialogue turns (alias of dialogue_turns)."""
    if surface == "hermes":
        db, session_id = _hermes_target(path)
        with _hermes_connect(db) as conn:
            rows = conn.execute("""SELECT role, content FROM messages
                WHERE session_id = ? AND active = 1 AND role IN ('user', 'assistant')
                ORDER BY timestamp, id""", (session_id,))
            return [Turn("human" if role == "user" else "edge", content)
                    for role, content in rows
                    if content and not _is_scaffolding_turn(
                        "human" if role == "user" else "edge", content)]
    return dialogue_turns(path, surface=surface)


def filter_dialogue_for_rationalizer(turns) -> list:
    """Second pass over already-parsed turns: drop residual agent-launch human lines mid-session."""
    out = []
    for turn in turns or []:
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else None)
        text = getattr(turn, "text", None) or (turn.get("text") if isinstance(turn, dict) else None)
        if not isinstance(role, str) or not isinstance(text, str) or not text.strip():
            continue
        role = role.lower()
        if role not in ("human", "edge"):
            continue
        if _is_scaffolding_turn(role, text.strip()):
            continue
        if isinstance(turn, Turn):
            out.append(turn)
        else:
            out.append(Turn(role=role, text=text.strip()))
    return out


def mentee_dialogue_for_rationalize(session: Session):
    """Dialogue corpus for a-posteriori film, or None if this session must not feed employment.

    Pipeline (all surfaces claude|codex|grok):
      1. is_user_session — drop sidechains/subagents/worker launches
      2. dialogue_turns / _turns_from_lines — user+assistant prose only (tools + scaffolding gone)
      3. require ≥1 human turn

    Scaffolding is filtered once inside surface adapters (gate P2: no second pass).
    Returns ``(turns, watermark)`` where watermark is the raw line count (CAS identity), or None.
    """
    if not isinstance(session, Session):
        return None
    surface = _normalize_surface(session.surface)
    if not is_user_session(session):
        return None
    if surface == "hermes":
        turns, watermark = delta(session.path, 0, surface=surface)
        turns = filter_dialogue_for_rationalizer(turns)
        return (turns, watermark) if turns and any(t.role == "human" for t in turns) else None
    try:
        raw_lines = Path(session.path).read_text(errors="replace").splitlines()

    except OSError:
        return None
    watermark = len(raw_lines)
    turns = _turns_from_lines(raw_lines, surface=surface)
    if not turns or not any(t.role == "human" for t in turns):
        return None
    return turns, watermark


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
    if surface == "hermes":
        db, session_id = _hermes_target(path)
        with _hermes_connect(db) as conn:
            rows = list(conn.execute("""SELECT id, role, content FROM messages
                WHERE session_id = ? AND active = 1 AND role IN ('user', 'assistant') AND id > ?
                ORDER BY timestamp, id""", (session_id, since_line)))
        return ([Turn("human" if role == "user" else "edge", content)
                 for _, role, content in rows], max((id for id, _, _ in rows), default=since_line))
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
