"""sweep — the pull-at-open digestion sweep (ADR-0008, issue #15). Genotype tool.

ONE idempotent, cursor-guarded pass over the transcript store. Every operator session's delta
since its cursor becomes (a) an `episode` event in the Tier-0 log (raw, ADR-0006) and (b) a
Graphiti episode — the extracted, non-curated tier. **CONTRACT C2**: extraction runs on the
delta only, never the whole store. **Keyed on the store, not on any skill** — a session that ran
no ed skill is still digested at the next sweep. Re-running is a no-op (the cursor guards it).
After ingest, the wiki and Direction **re-project** (sweep → extract → re-project → digest).

The pure planning (`plan_sweep`, cursors) carries no graph/LLM; `execute` takes an injected
`ingest_fn`, so the cursor/idempotency logic is testable without Neo4j or OpenAI.

Run:  tools/edge-python tools/sweep.py          (sweep + re-project)
      python3 tools/sweep.py --plan             (re-execs into .venv when present)
      tools/edge-python tools/sweep.py --rationalize-only  (explicit sleep-time backlog)
"""
import json
import math
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cortex
import eventlog
import sessions
import _identity

CURSORS = _identity.state_root() / "state" / "cursors.json"
CODEX_BASELINE_KEY = "_codex_baselined"
GROK_BASELINE_KEY = "_grok_baselined"
# Identity (group + store) resolves LAZILY through _identity at call time (ADR-0015): no
# import-time cache (stale-copy risk), no baked-in host path (the dev's -home-<user> store
# default sent roberto scanning a nonexistent dir — "nothing new" over a 294-session backlog).
DISPATCH_MARKER = "Dispatch runtime context"   # strip the edge's own framing (exp-001)
MIN_CHARS = 200                                 # a substantive delta, not a stray turn
# Tier-1 ONLY: the body fed to ONE Graphiti episode. The extractor (gpt-4o-mini, 128k-token
# context) also carries its system prompt + retrieved prior episodes + reserved output, so a whole
# oversized session shipped as one episode overflowed and was dropped (#53). ~48k chars (~12k
# tokens) leaves deep headroom and keeps the common case (deltas under budget) a single episode —
# Tier-0 keeps the FULL body uncapped; only the add_episode boundary chunks.
MAX_EPISODE_CHARS = 48_000
# Tier-1 ONLY: the OTHER side of the same window. add_episode internally retrieves the last 10
# previous episodes (RELEVANT_SCHEMA_LIMIT) as prompt context — 10 x 48k already flirts with the
# 128k window, and legacy pre-#53 episodes (up to ~200k chars) made EVERY new ingest overflow
# regardless of the new delta's size, wedging the group (nothing lands, so the window never rolls
# past the giants). We pass previous_episode_uuids explicitly, greedy most-recent-first under this
# deterministic char budget (~30k tokens), skipping any single episode over MAX_EPISODE_CHARS.
PREV_CONTEXT_MAX_CHARS = 120_000
DEFAULT_MAX_SESSIONS_PER_SWEEP = 5
DEFAULT_SWEEP_TOKEN_BUDGET = 20_000
DEFAULT_SCENE_TURN_LIMIT = 40
# Soft-fail park (G2): after this many soft skips (invalid_output, …) on the same session
# watermark, the coordinator parks the session so it cannot burn the aggregate budget every
# sweep and starve later work. Cleared on successful rationalize, watermark growth, or manual
# delete of the side-file entry. budget_exhausted is a hard stop and does NOT count.
SOFT_FAIL_PARK_THRESHOLD = 3
# UX.W-sweep-lock-dark: exclusive cursors flock is non-blocking + retry up to this budget.
# Past the wait the sweep goes honest DARK (return 0) so predispatch can still stamp —
# identity precedes grounding; prefer swept=0 over a silent concurrent hang.
CURSORS_LOCK_WAIT_S = 45.0
CURSORS_LOCK_POLL_S = 0.1


def _reexec_repo_venv():
    """When called as `python3 tools/sweep.py`, switch to the install venv before real work.

    The graph tier is mandatory and the system Python often lacks `neo4j`/`graphiti_core`. Imports
    stay testable; the script entrypoint alone corrects the interpreter.
    """
    if os.environ.get("EDGE_SWEEP_NO_VENV_REEXEC"):
        return
    venv_py = REPO / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return
    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return
    except OSError:
        pass
    os.execv(str(venv_py), [str(venv_py), str(Path(__file__).resolve()), *sys.argv[1:]])


# --- cursors (per-session raw-line watermark already digested) ---
def load_cursors(path=CURSORS):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else {}


def save_cursors(cursors, path=CURSORS):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cursors, indent=2, sort_keys=True))


def clean_body(turns):
    """The mentee<->edge dialogue with the edge's own dispatch/heartbeat framing stripped (exp-001)."""
    kept = [t for t in turns if DISPATCH_MARKER not in t.text]
    return "\n".join(f"{t.role}: {t.text}" for t in kept)


def _qualifies(turns, body):
    return bool(body.strip()) and any(t.role == "human" for t in turns) and len(body) >= MIN_CHARS


def _cursor_id(session):
    """Claude keeps its historical cursor key; Codex/Grok are namespaced to avoid collisions."""
    if session.surface == "codex":
        return f"codex:{session.id}"
    if session.surface == "grok":
        return f"grok:{session.id}"
    return session.id


def _source_description(item):
    surface = item.get("surface")
    if surface == "codex":
        return "Codex work session (mentee<->edge)"
    if surface == "grok":
        return "Grok work session (mentee<->edge)"
    return "Claude work session (mentee<->edge)"


def _episode_name(item, chunk_index=None):
    sid = item["id"].replace(":", "-")[:24]
    base = f"session-{sid}"
    return base if chunk_index is None else f"{base}-p{chunk_index + 1}"


def _codex_enabled(project_dir, codex_dir):
    """Optional Codex surface: explicit dir / False override, else agent.yaml surfaces.codex."""
    import surfaces_cfg
    return surfaces_cfg.include_optional_surface("codex", project_dir, codex_dir)


def _grok_enabled(project_dir, grok_dir):
    """Optional Grok surface: explicit dir / False override, else agent.yaml surfaces.grok."""
    import surfaces_cfg
    return surfaces_cfg.include_optional_surface("grok", project_dir, grok_dir)


def _hermes_enabled(project_dir, hermes_dir):
    """Optional Hermes surface: explicit dir / False override, else configured surface."""
    import surfaces_cfg
    return surfaces_cfg.include_optional_surface("hermes", project_dir, hermes_dir)


def _session_in_window(session, window_start):
    return window_start is None or (
        sessions.updated_epoch(session) >= window_start if session.updated_at
        else _in_window(session.path, window_start))


def _film_window_start(log=None):
    """Início da janela do filme (epoch) a partir do backfill_days declarado — agent.yaml
    lentes.backfill_days, senão state/bootstrap.json. None = sem limite (legado).

    A janela é o APETITE DECLARADO do operador: classificar/filmar fora dela é trabalho
    morto — com backfill=0 o wake não toca arquivo nenhum (operador 2026-07-25: '0 dias
    e mesmo assim tá foda')."""
    days = None
    try:
        import surfaces_cfg
        cfg = surfaces_cfg.load_agent_cfg()
        days = (cfg.get("lentes") or {}).get("backfill_days")
    except Exception:
        pass
    if days is None:
        try:
            import json as _json
            boot = _json.loads((_identity.state_root() / "state" / "bootstrap.json").read_text())
            days = boot.get("backfill_days")
        except Exception:
            pass
    if days is None:
        return None
    try:
        return time.time() - float(days) * 86400
    except (TypeError, ValueError):
        return None


def _in_window(path, window_start):
    if window_start is None:
        return True
    try:
        return Path(path).stat().st_mtime >= window_start
    except OSError:
        return False


def _install_birth(log=None):
    """Epoch do 1º evento do log — o nascimento do install (None se log vazio/ilegível).

    Fronteira da proveniência: sessão codex/grok anterior ao nascimento não pode ser
    trabalho delegado do edge (caso edgesandbox 2026-07-25 — backfill filmava zero)."""
    try:
        for e in eventlog.read(log=log if log is not None else eventlog.LOG):
            ts = e.get("ts")
            if ts:
                from datetime import datetime
                return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
            break
    except Exception:
        return None
    return None


def _codex_baseline(cursors, codex_dir=None, install_birth=None):
    """First Codex-aware run starts from now: existing Codex logs are marked seen but not ingested.
    New sessions/deltas after this baseline flow through normally."""
    if cursors.get(CODEX_BASELINE_KEY):
        return cursors
    window = _film_window_start()
    for s in sessions.list_codex_sessions(codex_dir):
        if not _in_window(s.path, window):
            continue
        if not sessions.is_user_session(s, install_birth=install_birth):
            continue
        if install_birth:
            try:
                if Path(s.path).stat().st_mtime < float(install_birth):
                    continue   # vida pré-edge do mentee = backfill, nunca baseline
            except OSError:
                pass
        _turns, watermark = sessions.delta(s.path, 0, surface=s.surface)
        cursors[_cursor_id(s)] = watermark
    cursors[CODEX_BASELINE_KEY] = True
    return cursors


def _grok_baseline(cursors, grok_dir=None, install_birth=None):
    """First Grok-aware run starts from now: existing Grok logs are marked seen but not ingested.
    New sessions/deltas after this baseline flow through normally."""
    if cursors.get(GROK_BASELINE_KEY):
        return cursors
    window = _film_window_start()
    for s in sessions.list_grok_sessions(grok_dir):
        if not _in_window(s.path, window):
            continue
        if not sessions.is_user_session(s, install_birth=install_birth):
            continue
        if install_birth:
            try:
                if Path(s.path).stat().st_mtime < float(install_birth):
                    continue   # vida pré-edge do mentee = backfill, nunca baseline
            except OSError:
                pass
        _turns, watermark = sessions.delta(s.path, 0, surface=s.surface)
        cursors[_cursor_id(s)] = watermark
    cursors[GROK_BASELINE_KEY] = True
    return cursors


def record_session_exclusions(project_dir=None, *, log=eventlog.LOG, codex_dir=None,
                              grok_dir=None):
    """Append provenance corrections for non-operator sessions, once per session.

    This is deliberately mechanical and model-free. The raw transcript remains intact; report
    folds use the correction to stop projecting prior delegated activity as operator activity.
    """
    include_codex = _codex_enabled(project_dir, codex_dir)
    include_grok = _grok_enabled(project_dir, grok_dir)
    if project_dir is None:
        project_dir = _identity.project_dir()
    discovered = list(sessions.list_sessions(project_dir))
    if include_codex:
        discovered.extend(sessions.list_codex_sessions(codex_dir))
    if include_grok:
        discovered.extend(sessions.list_grok_sessions(grok_dir))
    already = {
        payload["sessao_id"]
        for event in eventlog.read(types=["sessao.excluded"], log=log)
        for payload in [event.get("payload")]
        if isinstance(payload, dict)
        and isinstance(payload.get("sessao_id"), str)
        and payload["sessao_id"]
    }
    additions = []
    window = _film_window_start()
    birth = _install_birth(log)
    for session in discovered:
        if not _in_window(session.path, window):
            continue           # fora do apetite declarado: nem classifica, nem registra
        session_id = _cursor_id(session)
        if session_id in already:
            continue
        reason = sessions.user_session_exclusion_reason(session, install_birth=birth)
        if reason is None:
            continue
        additions.append((
            "sessao.excluded",
            f"sessao:{session_id}",
            {"sessao_id": session_id, "surface": session.surface, "reason": reason},
        ))
        already.add(session_id)
    return eventlog.append_batch(additions, log=log) if additions else []


def _load_install_env():
    """Load this install's secrets for real runtime sweeps. Hermetic tests pass project_dir."""
    try:
        import _secrets
        _secrets.load_env(_identity._env_dir(_identity.AGENT_YAML))
    except Exception:
        pass


# --- pure plan: the digestible deltas (reads files, no graph/LLM) ---
def plan_sweep(project_dir=None, cursors=None, recent=None, codex_dir=None, grok_dir=None,
               install_birth=None, hermes_dir=None, *, hermes_backfill=False, exclude=None):
    """For each session, the turns after its cursor + the new watermark, in **chronological order**
    (oldest first — bi-temporal ingest wants it). `skip` marks a delta too thin to ingest (left
    un-advanced to grow). Idempotent: a session at its watermark yields nothing new. `recent=N`
    bounds a run to the N most-recently-modified sessions (the rest backfill on later sweeps —
    the cursor makes the full sweep resumable)."""
    include_codex = _codex_enabled(project_dir, codex_dir)
    include_grok = _grok_enabled(project_dir, grok_dir)
    include_hermes = _hermes_enabled(project_dir, hermes_dir)
    if project_dir is None:
        project_dir = _identity.project_dir()   # fail-loud seam (ADR-0015), never a baked-in path
    cursors = cursors or {}
    excluded = set(sessions.current_session_anchors() if exclude is None else exclude)
    window = _film_window_start()
    found = []
    for s in sessions.list_sessions(project_dir):
        if not _in_window(s.path, window):
            continue
        if not sessions.is_user_session(s, install_birth=install_birth):
            continue
        sid = _cursor_id(s)
        seen = cursors.get(sid, 0)
        turns, watermark = sessions.delta(s.path, seen, surface=s.surface)
        if watermark <= seen or not turns:
            continue  # no new raw lines / no new dialogue
        found.append((Path(s.path).stat().st_mtime, s, turns, watermark, sid, None))
    if include_codex:
        for s in sessions.list_codex_sessions(codex_dir):
            if not _in_window(s.path, window):
                continue
            if not sessions.is_user_session(s, install_birth=install_birth):
                continue
            sid = _cursor_id(s)
            seen = cursors.get(sid, 0)
            turns, watermark = sessions.delta(s.path, seen, surface=s.surface)
            if watermark <= seen or not turns:
                continue  # no new raw lines / no new dialogue
            found.append((Path(s.path).stat().st_mtime, s, turns, watermark, sid, None))
    if include_grok:
        for s in sessions.list_grok_sessions(grok_dir):
            if not _in_window(s.path, window):
                continue
            if not sessions.is_user_session(s, install_birth=install_birth):
                continue
            sid = _cursor_id(s)
            seen = cursors.get(sid, 0)
            turns, watermark = sessions.delta(s.path, seen, surface=s.surface)
            if watermark <= seen or not turns:
                continue  # no new raw lines / no new dialogue
            found.append((Path(s.path).stat().st_mtime, s, turns, watermark, sid, None))
    if include_hermes:
        import hermes_profiles
        hermes_path = sessions.hermes_state_db() if hermes_dir is None else Path(hermes_dir)
        hermes_home = hermes_path.parent if hermes_path.is_file() else hermes_path
        for s in sessions.list_hermes_sessions(hermes_dir):
            if not hermes_backfill and not _session_in_window(s, window):
                continue
            sid = _cursor_id(s)
            seen = cursors.get(sid, 0)
            turns, watermark = sessions.delta(s.path, seen, surface="hermes")
            if watermark <= seen or not turns:
                continue
            member = hermes_profiles.membership(hermes_home, s.profile_name)
            if member.enabled:
                found.append((sessions.updated_epoch(s), s, turns, watermark, sid, member.edge_group))
    found = [item for item in found
             if item[4] not in excluded
             and item[1].id not in excluded
             and f"{item[1].surface}:{item[1].id}" not in excluded]
    found.sort(key=lambda x: x[0])           # chronological
    if recent:
        found = found[-recent:]              # the N newest, still chronological
    return [{"id": sid, "raw_id": s.id, "surface": s.surface, "path": str(s.path),
             **({"profile_name": s.profile_name} if s.profile_name else {}),
             **({"edge_group": group} if group else {}),
             "turns": turns, "watermark": watermark,
             "body": (body := clean_body(turns)), "skip": not _qualifies(turns, body)}
            for _, s, turns, watermark, sid, group in found]


# --- bounded a-posteriori rationalization (log-checkpointed; no cursor) ---
def _substantial_for_rationalization(turns):
    """Substantial mentee dialogue for film (all surfaces).

    Multi-turn conversations: ≥5 human turns and ≥1000 human chars (quente heritage).
    Single long operator briefs (common on Grok): ≥1 human turn and ≥1000 human chars —
    otherwise Grok never enters the rationalize plan despite long employment prompts.
    """
    human = [turn for turn in turns if turn.role == "human"]
    n = len(human)
    chars = sum(len(turn.text) for turn in human)
    if n >= 5 and chars >= 1000:
        return True
    if n >= 1 and chars >= 1000:
        return True
    return False


def _validate_lentes_limit(value, name, *, allow_zero=False):
    floor = 0 if allow_zero else 1
    if (not isinstance(value, int) or isinstance(value, bool) or value < floor):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"lentes.{name} must be a {qualifier} integer")
    return value


def _lentes_config(path=None):
    """Read only the phenotype knobs owned by the lenses coordinator.

    When agent.yaml is absent (first-run), fall back to state/bootstrap.json
    ``backfill_days`` so the initial assemble uses the install lookback.
    """
    path = _identity.identity_path("agent.yaml") if path is None else Path(path)
    try:
        import yaml
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raw = {}
    lenses = raw.get("lentes") if isinstance(raw, dict) else None
    lenses = lenses if isinstance(lenses, dict) else {}
    backfill = lenses.get("backfill_days")
    if backfill is None:
        # bootstrap pre-phenotype (EDGE_HOME or REPO)
        for root in filter(None, [
            os.environ.get("EDGE_HOME"),
            str(REPO),
        ]):
            boot = Path(os.path.expanduser(root)) / "state" / "bootstrap.json"
            if boot.is_file():
                try:
                    import json
                    backfill = (json.loads(boot.read_text()) or {}).get("backfill_days")
                    break
                except (json.JSONDecodeError, OSError):
                    pass
    config = {
        "backfill_days": backfill,
        "max_sessions_per_sweep": lenses.get(
            "max_sessions_per_sweep", DEFAULT_MAX_SESSIONS_PER_SWEEP),
        "sweep_token_budget": lenses.get(
            "sweep_token_budget", DEFAULT_SWEEP_TOKEN_BUDGET),
        "scene_turn_limit": lenses.get(
            "scene_turn_limit", DEFAULT_SCENE_TURN_LIMIT),
    }
    if config["backfill_days"] is not None:
        _validate_lentes_limit(config["backfill_days"], "backfill_days", allow_zero=True)
    _validate_lentes_limit(config["max_sessions_per_sweep"], "max_sessions_per_sweep")
    _validate_lentes_limit(config["sweep_token_budget"], "sweep_token_budget")
    _validate_lentes_limit(config["scene_turn_limit"], "scene_turn_limit")
    return config


def rationalization_identity(session_id, turns, *, surface="claude", watermark=None,
                             racionalizador_version="racionalizador-v3-session-provenance"):
    """Compute the exact public checkpoint identity using the rationalizer's normalization."""
    import racionalizador
    normalized_turns = racionalizador._normalized_turns(turns)
    if watermark is None:
        watermark = len(normalized_turns)
    source_hash = racionalizador._digest({
        "session_id": session_id,
        "surface": surface,
        "watermark": watermark,
        "turns": normalized_turns,
    })
    return {
        "source_hash": source_hash,
        "rationalization_id": racionalizador._digest({
            "source_hash": source_hash,
            "racionalizador_version": racionalizador_version,
        }),
    }


def plan_rationalizations(project_dir=None, *, log=eventlog.LOG, codex_dir=None, grok_dir=None,
                          backfill_days=None, now=None,
                          racionalizador_version="racionalizador-v3-session-provenance"):
    """Return current substantial inputs lacking a log checkpoint, oldest first.

    The raw transcript is append-only, so ``session + surface + watermark + version`` identifies
    the current input cheaply.  ``rationalization_id`` being present on that checkpoint is the
    authority; there is deliberately no second cursor.  A grown session gets a new watermark and
    becomes pending again.  ``backfill_days`` is only a scan/cost horizon and never mutates files.
    """
    if backfill_days is not None:
        _validate_lentes_limit(backfill_days, "backfill_days", allow_zero=True)
    if not isinstance(racionalizador_version, str) or not racionalizador_version.strip():
        raise ValueError("racionalizador_version must be a non-blank string")
    include_codex = _codex_enabled(project_dir, codex_dir)
    include_grok = _grok_enabled(project_dir, grok_dir)
    if project_dir is None:
        project_dir = _identity.project_dir()
    now = datetime.now(timezone.utc) if now is None else now
    if isinstance(now, str):
        now = datetime.fromisoformat(now.replace("Z", "+00:00"))
    if not isinstance(now, datetime):
        raise ValueError("now must be a datetime or ISO timestamp")
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    floor = ((now - timedelta(days=backfill_days)).timestamp()
             if backfill_days is not None else None)

    checkpoints = set()
    for event in eventlog.read(types=["sessao.racionalizada"], log=log):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        rationalization_id = payload.get("rationalization_id")
        if not isinstance(rationalization_id, str) or not rationalization_id.strip():
            continue
        checkpoints.add(rationalization_id)

    # Three surfaces → same dialogue filter (user↔assistant only), then mentee session gate.
    discovered = list(sessions.list_sessions(project_dir))
    if include_codex:
        discovered.extend(sessions.list_codex_sessions(codex_dir))
    if include_grok:
        discovered.extend(sessions.list_grok_sessions(grok_dir))
    pending = []
    for session in discovered:
        path = Path(session.path)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if floor is not None and mtime < floor:
            continue
        # Pre-process: operator dialogue only (no terminals/tools) + not worker/sidechain.
        packed = sessions.mentee_dialogue_for_rationalize(session)
        if packed is None:
            continue
        turns, watermark = packed
        if not _substantial_for_rationalization(turns):
            continue
        session_id = _cursor_id(session)
        identity = rationalization_identity(
            session_id, turns, surface=session.surface, watermark=watermark,
            racionalizador_version=racionalizador_version,
        )
        if identity["rationalization_id"] in checkpoints:
            continue
        pending.append({
            "id": session_id,
            "raw_id": session.id,
            "surface": session.surface,
            "path": str(path),
            "mtime": mtime,
            "turns": turns,
            "watermark": watermark,
            **identity,
        })
    # Smallest dialogue first so sleep-time budget is not eaten by 1000-turn sessions
    # before any film lands (7d drain dogfood 2026-07-13: 0 rationalized on default oldest-first).
    pending.sort(key=lambda item: (
        len(item["turns"]), item["mtime"], item["surface"], item["id"]))
    return pending


def _add_usage(total, addition):
    addition = addition if isinstance(addition, dict) else {}
    for field in ("calls", "input_tokens", "output_tokens", "estimated_tokens"):
        value = addition.get(field, 0)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            total[field] += value


def _softfail_path(log):
    """Durable soft-fail map beside the coordinator lock: ``<log>.rationalize-softfail.json``."""
    return Path(log).with_name(Path(log).name + ".rationalize-softfail.json")


def load_softfail_state(log):
    """Load ``{session_id: {count, last_error, last_ts, watermark}}``; missing/corrupt → {}."""
    path = _softfail_path(log)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_softfail_state(state, log):
    path = _softfail_path(log)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def _softfail_entry(state, session_id):
    entry = state.get(session_id) if isinstance(state, dict) else None
    return entry if isinstance(entry, dict) else None


def _softfail_is_parked(entry, watermark, threshold=SOFT_FAIL_PARK_THRESHOLD):
    if not entry:
        return False
    count = entry.get("count", 0)
    if not isinstance(count, int) or isinstance(count, bool) or count < threshold:
        return False
    return entry.get("watermark") == watermark


def _record_soft_fail(state, session_id, *, watermark, error=None):
    """Increment soft-fail count for this session@watermark (park when threshold reached).

    Policy: count soft skips (``invalid_output`` and other per-session soft reasons, never
    ``already_rationalized`` / ``budget_exhausted``). Same watermark accumulates; a new
    watermark starts fresh (caller resets before record when watermark changed).
    """
    prev = _softfail_entry(state, session_id)
    count = 0
    if prev and prev.get("watermark") == watermark:
        raw = prev.get("count", 0)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
            count = raw
    entry = {
        "count": count + 1,
        "last_error": error,
        "last_ts": datetime.now(timezone.utc).isoformat(),
        "watermark": watermark,
    }
    state[session_id] = entry
    return entry


def _clear_soft_fail(state, session_id):
    if isinstance(state, dict):
        state.pop(session_id, None)


def _estimated_tokens(value):
    rendered = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True)
    return max(1, math.ceil(len(rendered.encode("utf-8")) / 4))


def _bounded_sweep_completer(complete_fn, completer_factory, token_budget):
    """Cap every model output by the aggregate budget; instantiate providers only on demand."""
    spent = 0

    def complete(prompt):
        nonlocal spent
        input_cost = _estimated_tokens(prompt)
        available = None if token_budget is None else token_budget - spent - input_cost
        if available is not None and available < 1:
            # Same sentinel rationalize catches for its own pre-call budget check. No provider is
            # constructed and its usage remains at/below the hard aggregate ceiling.
            import racionalizador
            raise racionalizador._BudgetExhausted
        if completer_factory is not None:
            call = completer_factory(max_tokens=available)
            raw = call(prompt)
        else:
            raw = complete_fn(prompt)
        rendered = raw if isinstance(raw, str) else json.dumps(
            raw, ensure_ascii=False, sort_keys=True)
        if available is not None and _estimated_tokens(rendered) > available:
            # The production provider already received max_tokens=available. Truncation is a
            # fail-safe for injected/non-conforming transports: invalid JSON keeps the session
            # pending, while rationalizer's accounted consumption can never cross the ceiling.
            rendered = rendered.encode("utf-8")[:available * 4].decode("utf-8", errors="ignore")
            while rendered and _estimated_tokens(rendered) > available:
                rendered = rendered[:-1]
            raw = rendered
        spent += input_cost + _estimated_tokens(raw)
        return raw

    return complete


def _open_threads(log):
    """Currently-open Atividades as {operacao, finalidade} — the connection context (#584).

    Folded from the eventlog (graph-independent, works corpus-dark). Feeds the rationalizer so
    its ``activity_relevant`` gate discriminates on connection to a live thread, not frequency:
    a one-off front connected to an open thread survives the sweep.
    """
    return [
        {"operacao": a["operacao"], "finalidade": a["finalidade"]}
        for a in eventlog.atividades_at(log=log).values()
        if a.get("estado") in ("aberta", "reaberta")
        and a.get("operacao") and a.get("finalidade")
    ]


def rationalize_pending_sessions(
    project_dir,
    complete_fn,
    *,
    completer_factory=None,
    log=eventlog.LOG,
    codex_dir=None,
    rationalize_fn=None,
    backfill_days=None,
    max_sessions_per_sweep=DEFAULT_MAX_SESSIONS_PER_SWEEP,
    sweep_token_budget=DEFAULT_SWEEP_TOKEN_BUDGET,
    scene_turn_limit=DEFAULT_SCENE_TURN_LIMIT,
    racionalizador_version="racionalizador-v3-session-provenance",
):
    """Rationalize an oldest-first prefix under one aggregate sweep budget.

    Planning and execution share a coordinator lock.  The per-session writer still performs its
    authoritative ``rationalization_id`` CAS under the event-log lock; this outer lock prevents two
    sweeps from spending model budget on the same oldest backlog item before either CAS lands.
    """
    _validate_lentes_limit(max_sessions_per_sweep, "max_sessions_per_sweep")
    if sweep_token_budget is not None:
        _validate_lentes_limit(sweep_token_budget, "sweep_token_budget")
    _validate_lentes_limit(scene_turn_limit, "scene_turn_limit")
    if (complete_fn is None) == (completer_factory is None):
        raise ValueError("provide exactly one of complete_fn or completer_factory")
    if complete_fn is not None and not callable(complete_fn):
        raise ValueError("complete_fn must be callable")
    if completer_factory is not None and not callable(completer_factory):
        raise ValueError("completer_factory must be callable")
    if rationalize_fn is None:
        import racionalizador
        rationalize_fn = racionalizador.rationalize

    import fcntl
    coordinator_lock = Path(log).with_name(Path(log).name + ".rationalize.lock")
    coordinator_lock.parent.mkdir(parents=True, exist_ok=True)
    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_tokens": 0}
    rationalized = []
    attempted = []
    skipped = []
    stopped_reason = None
    softfail_dirty = False
    bounded_complete_fn = _bounded_sweep_completer(
        complete_fn, completer_factory, sweep_token_budget)
    # Finding F: bound rationalize coordinator lock (same pattern as cursors lock-dark).
    lock_wait_s = float(os.environ.get("EDGE_RATIONALIZE_LOCK_WAIT_S", "45"))
    lock_poll_s = float(os.environ.get("EDGE_RATIONALIZE_LOCK_POLL_S", "0.2"))
    with coordinator_lock.open("w") as lock:
        if not _acquire_cursors_lock(lock, wait_s=lock_wait_s, poll_s=lock_poll_s):
            print(
                f"sweep: rationalize lock DARK (held >{lock_wait_s}s on {coordinator_lock}) "
                "— backlog retained; next trigger retries",
                flush=True,
            )
            return {
                "attempted": [],
                "rationalized": [],
                "pending": [],
                "usage": usage,
                "stopped_reason": "lock_dark",
                "skipped": [],
            }
        try:
            # Soft-fail park state is durable across sweeps (side file next to this lock).
            # Policy: on soft skip (invalid_output, …) increment count@watermark; at
            # SOFT_FAIL_PARK_THRESHOLD park (skip attempt) until watermark grows or manual
            # clear; success clears; budget_exhausted hard-stops without counting.
            softfail = load_softfail_state(log)
            pending = plan_rationalizations(
                project_dir,
                log=log,
                codex_dir=codex_dir,
                backfill_days=backfill_days,
                racionalizador_version=racionalizador_version,
            )
            # Prefer non-parked so a parked oldest session cannot sit first forever.
            def _park_key(item):
                entry = _softfail_entry(softfail, item["id"])
                if entry and entry.get("watermark") != item["watermark"]:
                    return 0  # watermark grew → will unpark below
                return 1 if _softfail_is_parked(entry, item["watermark"]) else 0

            pending = sorted(
                pending,
                key=lambda item: (_park_key(item), item["mtime"], item["surface"], item["id"]),
            )
            for item in pending:
                # Finding G: limit attempts (not only successes) so invalid_output cannot burn
                # unbounded sessions past max_sessions_per_sweep.
                if len(attempted) >= max_sessions_per_sweep:
                    stopped_reason = "max_sessions_per_sweep"
                    break
                remaining = (None if sweep_token_budget is None else
                             max(0, sweep_token_budget - usage["estimated_tokens"]))
                if remaining == 0:
                    stopped_reason = "budget_exhausted"
                    break
                sid = item["id"]
                entry = _softfail_entry(softfail, sid)
                # Watermark growth resets soft-fail count (unpark / fresh attempts).
                if entry is not None and entry.get("watermark") != item["watermark"]:
                    _clear_soft_fail(softfail, sid)
                    softfail_dirty = True
                    entry = None
                if _softfail_is_parked(entry, item["watermark"]):
                    skipped.append({"id": sid, "reason": "soft_fail_parked"})
                    continue
                attempted.append(sid)
                result = rationalize_fn(
                    sid,
                    item["turns"],
                    bounded_complete_fn,
                    log,
                    surface=item["surface"],
                    watermark=item["watermark"],
                    racionalizador_version=racionalizador_version,
                    sweep_token_budget=remaining,
                    scene_turn_limit=scene_turn_limit,
                    # Recomputed per session so a front connects to threads opened earlier in
                    # THIS oldest-first sweep, not only threads open before it started (#584).
                    open_threads=_open_threads(log),
                )
                if not isinstance(result, dict):
                    raise TypeError("rationalize_fn must return a dict")
                _add_usage(usage, result.get("usage"))
                reason = result.get("skipped_reason")
                if reason == "already_rationalized":
                    # Checkpoint already exists; drop any stale soft-fail row.
                    if _softfail_entry(softfail, sid) is not None:
                        _clear_soft_fail(softfail, sid)
                        softfail_dirty = True
                    continue
                if reason == "budget_exhausted":
                    stopped_reason = reason
                    break
                if reason:
                    # Soft per-session failure (invalid_output, …): count + keep sweeping.
                    _record_soft_fail(
                        softfail, sid,
                        watermark=item["watermark"],
                        error=result.get("error"),
                    )
                    softfail_dirty = True
                    skip_entry = {"id": sid, "reason": reason}
                    if result.get("error") is not None:
                        skip_entry["error"] = result["error"]
                    skipped.append(skip_entry)
                    continue
                # Success: clear soft-fail tracking for this session.
                if _softfail_entry(softfail, sid) is not None:
                    _clear_soft_fail(softfail, sid)
                    softfail_dirty = True
                rationalized.append(sid)
            if softfail_dirty:
                save_softfail_state(softfail, log)
            current_pending = plan_rationalizations(
                project_dir,
                log=log,
                codex_dir=codex_dir,
                backfill_days=backfill_days,
                racionalizador_version=racionalizador_version,
            )
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return {
        "attempted": attempted,
        "rationalized": rationalized,
        "pending": [item["id"] for item in current_pending],
        "usage": usage,
        "stopped_reason": stopped_reason,
        "skipped": skipped,
    }


# --- effectful execute: log + ingest + advance cursor ---
def execute(plan, ingest_fn, cursors, log=eventlog.LOG):
    """**Tier-0 is truth** (ADR-0006): write each qualifying delta as an `episode` event and advance
    its cursor — **always, even with no graph**. The graph ingest (`ingest_fn`) is **best-effort**:
    a missing runtime or a down Neo4j (e.g. a graph-less fleet host) is logged and skipped, never
    fatal — the graph is a projection rebuildable from the log. Returns (cursors, n_logged)."""
    qualifying = [it for it in plan if not it.get("skip") and it.get("body", "").strip()]
    for it in qualifying:                              # Tier-0: the log + cursor, unconditionally
        # R8c part 1 (F9-dep, C5): STAMP the source Medium's tier on the episode at ingest. The native
        # Claude work session is a LOW-TIER Medium (context, never an order — C5), so the truth-path
        # record carries medium_tier=low_tier. This is the provenance the read door's context_only axis
        # reads; propagating it onto MERGED Graphiti nodes (the conservative lattice) is the v1.1 build,
        # until which the read-door fail-safe (unknown ⇒ context_only) holds the C5 invariant.
        payload = {"session": it["id"], "watermark": it["watermark"], "chars": len(it["body"]),
                   "medium_tier": "low_tier"}
        if it.get("surface") in ("codex", "grok"):
            payload["surface"] = it["surface"]
        eventlog.append("episode", f"session:{it['id']}", payload, log=log)
        cursors[it["id"]] = it["watermark"]
    if qualifying and ingest_fn is not None:           # Tier-1: graph projection, best-effort
        # BOUNDED + degrade-dark (#62): Tier-0 (episode + cursor) is ALREADY durable above, so the
        # graph ingest must never gate the wake. It runs on a daemon thread with a hard deadline —
        # a HANG (add_episode on a network call with no client timeout) degrades dark LOUD exactly
        # like a raise; the graph re-projects from the log. Fail loud on a bad budget, never un-cap.
        # Default 600s (qualidade>latência, operador 2026-07-25): extração LLM honesta
        # passa fácil de 30s e o grafo vivia truncando em silêncio; o cap segue existindo
        # só para HANG de rede — nunca para apressar trabalho real.
        budget_raw = os.environ.get("EDGE_SWEEP_INGEST_BUDGET_S", "600")
        try:
            budget = float(budget_raw)
        except (TypeError, ValueError):
            raise ValueError(f"EDGE_SWEEP_INGEST_BUDGET_S={budget_raw!r} is not a number — fail loud (#62)")
        if not math.isfinite(budget) or budget < 0:
            raise ValueError(f"EDGE_SWEEP_INGEST_BUDGET_S={budget_raw!r} is not a finite non-negative "
                             "number — nan/inf/negative would un-bound the graph ingest (#62); fail loud")
        err = []
        done = threading.Event()

        def _ingest():
            try:
                ingest_fn(qualifying)
            except Exception as e:  # noqa: BLE001 — captured, surfaced on the caller thread
                err.append(e)
            finally:
                done.set()

        threading.Thread(target=_ingest, daemon=True).start()
        if not done.wait(timeout=budget):
            print(f"sweep: graph ingest EXCEEDED {budget:g}s budget — degraded DARK (Tier-0 log is "
                  f"current; the graph is rebuildable from the log)")
        elif err:
            print(f"sweep: graph ingest skipped ({type(err[0]).__name__}: {err[0]}) — "
                  f"Tier-0 log is current; the graph is rebuildable from the log")
    return cursors, len(qualifying)


# --- real ingest (Graphiti) + re-projection ---
def _load_openai_key():
    if os.environ.get("OPENAI_API_KEY"):
        return
    # The install's OWN secrets first (OSS: BYO key); ~/.edge-sandbox-kit is only a dev fallback.
    for f in (REPO / "secrets" / "openai.env", Path.home() / ".edge-sandbox-kit" / "openai.env"):
        if f.exists():
            for line in f.read_text().splitlines():
                if "OPENAI_API_KEY" in line:
                    os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
                    return


def _first_ts(path):
    for line in open(path):
        try:
            ts = json.loads(line).get("timestamp")
            if ts:
                return ts
        except Exception:
            pass
    return None


def _parse_ts(ts):
    if not ts:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def chunk_episode_body(body, max_chars=MAX_EPISODE_CHARS):
    """Split an episode body into <= max_chars chunks at TURN ('\\n') boundaries, so a large
    session-delta lands as several sub-episodes that each fit the extractor's context window
    instead of overflowing as one episode and being dropped whole (#53, ex edge-of-chaos #573).
    Lossless: ''.join(chunks) == body. A body already under budget is returned as one chunk
    (the common case — name/behaviour unchanged). A single turn longer than max_chars is
    hard-split, so a giant paste still lands rather than blocking its session."""
    if len(body) <= max_chars:
        return [body]
    chunks, cur = [], ""
    for line in body.splitlines(keepends=True):          # keepends → ''.join reconstructs body
        while len(line) > max_chars:                     # one turn bigger than a whole chunk
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:max_chars])
            line = line[max_chars:]
        if cur and len(cur) + len(line) > max_chars:
            chunks.append(cur)
            cur = line
        else:
            cur += line
    if cur:
        chunks.append(cur)
    return chunks


def _ingest_summary(ingested, failures):
    """A linha ALTA do ingest, ou None quando tudo entrou.

    As falhas por episódio já são impressas uma a uma — e é exatamente por isso que elas somem:
    ficam soterradas num traço longo, e TODAS as linhas de resumo seguintes ('communities
    consolidadas — 0 clusters', etc.) continuam parecendo normais. Um wake que não filmou NADA
    reportava sucesso em todas as outras pernas. O operador não via uma falha; via calmaria.

    Ingest que falha é a memória parando de avançar — o órgão do qual todo o resto depende — e
    isso não pode custar um grep para ser notado."""
    if not failures:
        return None
    first = failures[0]
    total = ingested + len(failures)
    return (f"sweep: graph ingest — {len(failures)} de {total} episódio(s) FALHARAM; "
            f"a memória NÃO avançou neles. Primeiro: {first}")


def graphiti_ingest(items):
    """Incremental Graphiti extraction (C2): one episode per session-delta, into THIS install's
    own group (agent.yaml identity, #21). Robust: a per-episode failure is logged and skipped (the
    others still land). Returns the set of session ids that ingested — INFORMATIONAL: `execute`
    advances cursors unconditionally (Tier-0 is truth; the episode event is already logged), so a
    failed graph ingest does NOT retry via the cursor — its episode lives in the log awaiting an
    episode-replay recovery (a known gap, mirror of publisher.reproject_graph for artefatos)."""
    import asyncio
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client import LLMConfig, OpenAIClient
    _load_openai_key()
    neo = _identity.neo4j_conn()
    group = _identity.require_group()   # resolved ONCE, before any episode (codex gate)
    ok = set()

    async def bounded_previous_uuids(g, ref):
        """The previous-episode context add_episode would retrieve, bounded: most-recent-first
        under PREV_CONTEXT_MAX_CHARS, never an episode over MAX_EPISODE_CHARS (a legacy pre-#53
        giant — one alone can blow the window). Deterministic seam: the tool disposes what the
        extractor may see, instead of trusting the internal unbounded last-10 retrieval."""
        eps = await g.retrieve_episodes(ref, last_n=10, group_ids=[group],
                                        source=EpisodeType.message)
        chosen, total = [], 0
        for ep in reversed(eps):                     # chronological → most-recent-first
            size = len(ep.content)
            if size > MAX_EPISODE_CHARS:
                continue
            if total + size > PREV_CONTEXT_MAX_CHARS:
                break
            chosen.append(ep.uuid)
            total += size
        return chosen

    _ingested, _failures = [], []

    async def go():
        # gpt-5.6-luna NÃO serve aqui: graphiti_core fixa reasoning.effort="minimal"
        # (openai_base_client.py:36) e o luna recusa esse valor — o extractor morre com 400 e
        # a sessão inteira deixa de ser filmada. 9d330ea já mantinha 4o-mini neste caminho por
        # custo (extractor = linha #1 da fatura); agora há também um motivo de compatibilidade.
        llm = OpenAIClient(config=LLMConfig(model="gpt-4o-mini", small_model="gpt-4o-mini"))
        g = Graphiti(*neo, llm_client=llm)
        await g.build_indices_and_constraints()
        for it in items:
            ref = _parse_ts(_first_ts(it["path"]))   # all sub-episodes share the session's ref-time
            chunks = chunk_episode_body(it["body"])   # one big session → several context-fit episodes (#53)
            failed = False
            for k, chunk in enumerate(chunks):
                name = _episode_name(it) if len(chunks) == 1 else _episode_name(it, k)
                try:
                    prev = await bounded_previous_uuids(g, ref)
                    await _add_episode_with_backoff(lambda: g.add_episode(
                        name=name, episode_body=chunk,
                        source=EpisodeType.message,
                        source_description=_source_description(it),
                        reference_time=ref, group_id=group,
                        previous_episode_uuids=prev))
                    print(f"  + ingested {name} ({len(chunk)} chars)")
                except Exception as e:
                    failed = True
                    _failures.append(f"{name}: {type(e).__name__}: {e}")
                    print(f"  ! FAILED {name}: {type(e).__name__}: {e}")
                    if os.environ.get("EDGE_GRAPHITI_DEBUG") == "1":
                        import traceback
                        traceback.print_exc()
                else:
                    _ingested.append(name)
            if not failed:           # a session counts as ingested only if every sub-episode landed
                ok.add(it["id"])
        await g.close()

    asyncio.run(go())
    summary = _ingest_summary(len(_ingested), _failures)
    if summary:
        print(summary)
    return ok


def _openai_embed(text):
    """The real embedder. The phenotype's embedding adapter (llm_routes.embed_fn: openai
    direto, openrouter, azure/base_url — routers.embedding) wins; the legacy hardcoded
    OpenAI call survives as fallback for installs whose phenotype predates the route."""
    try:
        import llm_routes
        fn = llm_routes.embed_fn()
        if fn is not None:
            return fn(text)
    except Exception:
        pass  # adapter dark/malformed → estrada legada abaixo (degrade, never crash)
    from openai import OpenAI
    _load_openai_key()
    return OpenAI().embeddings.create(model="text-embedding-3-small", input=text).data[0].embedding


def embed_and_signal(slug, body, cites, embed_fn=None, log=eventlog.LOG):
    """ADR-0009 source-feedback (hypothesis tier), the impure boundary: for each cite carrying a
    `snippet`, emit a `source.signal` scoring `cosine(embed(snippet), embed(body))` — the cheap
    embedding-attribution signal (one OpenAI call per snippet). Returns the count emitted.

    **Degrade-safe** (same spirit as graphiti_ingest): the embedder is best-effort. With no `embed_fn`
    the real OpenAI one is used (lazy-imported); if it is unavailable — no openai, no key — nothing is
    emitted, a Tier-0 skip line is logged, and it never raises (the log stays current without it)."""
    snippetted = [c for c in cites if isinstance(c, dict) and c.get("snippet")]
    if not snippetted:
        return 0
    embed = embed_fn or _openai_embed
    try:
        body_vec = embed(body)
    except Exception as e:
        print(f"sweep: source.signal skipped ({type(e).__name__}: {e}) — no embedder (openai/key "
              f"absent); the Tier-0 log is current without embedding attribution")
        return 0
    n = 0
    for c in snippetted:
        sim = cortex.cosine(embed(c["snippet"]), body_vec)
        eventlog.source_signal(slug, c.get("ref"), c.get("kind"), sim, log=log)
        n += 1
    return n


def _maybe_consolidate():
    """Communities consolidation behind EDGE_COMMUNITIES=1 (dark by default, padrão EDGE_CONDUCTOR).
    Vazão×confiança: a vazão é automática atrás do knob; a confiança fica no harm-bearing. Best-effort
    como o graph-ingest — NUNCA derruba um sweep (grafo/LLM fora → skip logado).

    Mas "não derruba" nunca quis dizer "não conta". `len(written or [])` colapsava as duas
    respostas possíveis num único "0 clusters": o grafo que rodou e não tinha o que agrupar, e o
    grafo que NÃO CONSEGUIU rodar. A frota inteira imprimia a linha calma da escassez enquanto o
    órgão estava parado (#635)."""
    if os.environ.get("EDGE_COMMUNITIES") != "1":
        return
    try:
        import communities
    except Exception as e:
        print(f"sweep: communities skipped ({type(e).__name__}: {e}) — módulo indisponível")
        return
    try:
        written = communities.consolidate()
    except communities.ConsolidationFailed as e:
        # severidade na língua de group_health.verdicts (#638): `dark` = não pude rodar,
        # `fail` = rodei e quebrei. As duas são altas; nenhuma é "0 clusters".
        print(f"sweep: communities [{e.severity}] FALHARAM ({e.reason}) — a consolidação NÃO "
              f"rodou; as Community deste grupo estão PARADAS (não vazias) e a navegação por "
              f"cluster segue no estado da última passagem que funcionou. {e.detail}")
        return
    except Exception as e:   # noqa: BLE001 — best-effort leg: loga alto, nunca derruba o sweep
        print(f"sweep: communities [fail] FALHARAM ({type(e).__name__}: {e}) — a consolidação "
              f"NÃO rodou; as Community deste grupo estão PARADAS, não vazias")
        return
    print(f"sweep: communities consolidadas — {len(written)} clusters")


def _topic_direction_window_days():
    raw = os.environ.get("EDGE_TOPIC_DIRECTION_WINDOW_DAYS", "7")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"EDGE_TOPIC_DIRECTION_WINDOW_DAYS={raw!r} is not an integer")
    if val <= 0:
        raise ValueError(f"EDGE_TOPIC_DIRECTION_WINDOW_DAYS={raw!r} must be positive")
    return val


def _atividades_state_dir(explicit=None):
    """Persisted 4-level register (N1–N4). Never invents a state path."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("EDGE_ATIVIDADES_STATE")
    if env:
        return Path(env)
    try:
        cand = _identity.state_root() / "state" / "atividades"
        if (cand / "atividades.json").is_file():
            return cand
    except Exception:
        return None
    return None


def _maybe_propose_topic_directions(project_dir=None, codex_dir=None, grok_dir=None,
                                    log=eventlog.LOG, atividades_state=None):
    """Wake-time Direction.proposed BEFORE assemble.

    Primary engine: live activity N3+N4 pair (one proposed per open activity).
    TOPIC_SPECS / topic-7d canned steers are NOT the proposed engine — session
    topics stay as navigation index only. Never promotes to `set`. Never reopens
    set/dropped. Without a persisted atividades state (or without an N3+N4 pair),
    degrades declared — no silent invented objectives.
    """
    written = 0
    if os.environ.get("EDGE_TOPIC_DIRECTION", "1").lower() not in {"0", "false", "no", "off"}:
        try:
            import topic_threads
            kwargs = dict(
                window_days=_topic_direction_window_days(),
                project_dir=project_dir,
                codex_dir=codex_dir,
                grok_dir=grok_dir,
                all_stores=(project_dir is None),
                log=log,
            )
            # index only — sync_recent_topic_memory no longer emits topic-7d proposed
            out = topic_threads.sync_recent_topic_memory(**kwargs)
            if out.get("topics"):
                print(f"sweep: session topics indexed {out.get('topics', 0)}")
            written += int(out.get("topics") or 0)
        except Exception as e:  # noqa: BLE001 — automatic inference must not gate the wake
            print(f"sweep: session-topic index skipped ({type(e).__name__}: {e}) — "
                  "wake continues")
    try:
        import atividades
        state = _atividades_state_dir(atividades_state)
        if state is None or not (Path(state) / "atividades.json").is_file():
            return written
        reg, proj = atividades.carregar_estado(state)
        n = atividades.propose_live_activity_directions(reg, proj, log)
        if n:
            print(f"sweep: live-activity Direction proposed {n} item(s) "
                  "(N3+N4 pair; not topic-7d)")
        written += n
        return written
    except Exception as e:  # noqa: BLE001 — automatic inference must not gate the wake
        print(f"sweep: activity Direction skipped ({type(e).__name__}: {e}) — "
              "wake continues; grill can still curate existing Direction")
        return written


def reproject():
    """Re-project the folds. The Direction page + artefato candidates fold from the **log** (pure,
    always). The **wiki** projects from the graph and is **best-effort** — skipped (logged) on a
    host without Neo4j, since the wiki is a graph projection and the agent's durable read is the log."""
    eventlog.consolidate_artefato_proposals()
    eventlog.project_direction()                       # pure fold — always
    eventlog.project_corpus()                          # pure fold — always (Tier-0, no graph)
    _maybe_consolidate()                               # communities: vazão automática, knob-gated
    missing = cortex.artefatos_without_kernel()        # the C3 gate finally gets a reader (ADR-0009)
    if missing:
        print(f"sweep: C3 — {len(missing)} published Artefato(s) without an intent.kernel: "
              f"{', '.join(missing)} — edge work without a recorded intent is incomplete (warning)")
    # identity resolves OUTSIDE the outage catch (ADR-0015): a missing group must fail loud,
    # never be swallowed and mislabeled as "the wiki needs Neo4j"
    group = _identity.require_group()
    try:
        import wiki_render
        wiki_render.main(group, str(_identity.state_root() / "state" / "wiki"), "threads")
    except Exception as e:
        print(f"sweep: wiki render skipped ({type(e).__name__}: {e}) — "
              f"Direction projected from the log; the wiki needs Neo4j")


def reproject_graph(log=eventlog.LOG):
    """Graph recovery (#30): replay any Artefato a transient outage left out of the graph + rebuild
    the spine backbone, so the "reproject next beat" path the publisher promises self-heals. Runs on
    EVERY sweep (Codex P2 — NOT gated by new ingest): if Neo4j was down at publish and the next sweep
    has no delta, this no-delta sweep still recovers. The run's `log` is THREADED through (Codex P2),
    so a custom-log dry-run does not read/project the real corpus — publisher.reproject_graph
    default-skips a non-canonical log. Best-effort (an unreachable graph degrades) — never blocks."""
    try:
        import publisher
        publisher.reproject_graph(log=log)
    except Exception as e:
        print(f"sweep: graph reproject skipped ({type(e).__name__}: {e}) — needs Neo4j")
    # ticket D: re-nominate the semantic layer over the refreshed corpus. GLOBAL by design (the
    # relative floor + mutual-kNN are corpus-relative — a per-publish incremental mint would
    # freeze yesterday's floor) and CANONICAL-LOG ONLY: a custom-log dry-run/test must never
    # wipe-rebuild the install's live RELATES_TO edges. Best-effort like the leg above.
    try:
        import publisher
        import relate
        if publisher._is_canonical_log(log):
            out = relate.sync()
            if out is not None:
                print(f"sweep: semantic link — {len(out['minted'])} RELATES_TO minted, "
                      f"{len(out['offers'])} contradiction offer(s) for the author")
    except Exception as e:
        print(f"sweep: relate sync skipped ({type(e).__name__}: {e}) — semantic leg dark")


def _acquire_cursors_lock(lk, wait_s=CURSORS_LOCK_WAIT_S, poll_s=CURSORS_LOCK_POLL_S):
    """Exclusive cursors flock: non-blocking + retry up to wait_s (UX.W-sweep-lock-dark).

    Returns True when acquired; False when the wait budget expires without the lock. Caller
    must treat False as honest DARK (skip this sweep, return 0) so predispatch can still stamp.
    """
    import fcntl
    deadline = time.monotonic() + max(0.0, float(wait_s))
    while True:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_s)


def run(project_dir=None, ingest_fn=None, cursors_path=CURSORS, reproject_fn=None,
        log=eventlog.LOG, recent=None, graph_recover_fn=None, group=None, codex_dir=None,
        grok_dir=None, cursors_lock_wait_s=None, atividades_state=None):
    """Full sweep: plan the deltas → ingest + log + advance cursors → re-project (if anything new) →
    graph-recover (ALWAYS). `recent=N` bounds this run to the N newest sessions (the rest backfill on
    later sweeps). Graph recovery runs EVERY sweep, independent of `n` (Codex P2), so a no-delta sweep
    after Neo4j comes back still heals a publish-time-missed projection.

    `cursors_lock_wait_s` (default CURSORS_LOCK_WAIT_S=45) bounds how long run() retries the
    exclusive cursors flock. On timeout: loud DARK print and return 0 (skip sweep) so a concurrent
    holder never silently hangs the wake — identity precedes grounding (UX.W-sweep-lock-dark)."""
    # ADR-0015 preflight (codex gate): an install that has not declared who it is must not
    # write as anyone — Tier-0 episode appends and cursor advances ARE writes. Identity fails
    # loud HERE, before the delta is consumed, never mid-sweep (where a rerun would see the
    # delta as already eaten by a groupless ghost). Tests pass `group` explicitly (hermetic).
    if project_dir is None:
        _load_install_env()
    if group is None:
        group = _identity.require_group()
    # The whole load→plan→execute→save window is serialized by an exclusive flock on a sibling
    # lockfile (the append_batch/next_producer house pattern) — cursors.json is the one shared
    # mutable state on a multi-dispatch host (operator + heartbeat): two overlapping sweeps would
    # otherwise read the same base and append duplicate episode events / clobber each other's
    # cursor advances (review B1, ADR-0008's idempotency is only real under this lock).
    # UX.W-sweep-lock-dark: NON-BLOCKING + retry (not indefinite LOCK_EX). Past the wait budget
    # we skip this sweep (return 0) with a loud DARK print — prefer wake continues with swept=0
    # than a silent hang past 45s while another instance holds the cursor lock.
    import fcntl
    lock_wait = CURSORS_LOCK_WAIT_S if cursors_lock_wait_s is None else float(cursors_lock_wait_s)
    lock_path = Path(cursors_path).with_name(Path(cursors_path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    corrected = False
    with lock_path.open("w") as lk:
        if not _acquire_cursors_lock(lk, wait_s=lock_wait):
            print(f"sweep: cursors lock DARK (held >{lock_wait:g}s) — skipping sweep this wake "
                  "(swept=0); identity precedes grounding; next wake retries.")
            return 0
        try:
            cursors = load_cursors(cursors_path)
            excluded = record_session_exclusions(
                project_dir, log=log, codex_dir=codex_dir, grok_dir=grok_dir)
            corrected = bool(excluded)
            if excluded:
                print(f"sweep: excluded {len(excluded)} delegated/protocol session(s) "
                      "from operator projections")
            birth = _install_birth(log)
            if _codex_enabled(project_dir, codex_dir):
                cursors = _codex_baseline(cursors, codex_dir, install_birth=birth)
            if _grok_enabled(project_dir, grok_dir):
                cursors = _grok_baseline(cursors, grok_dir, install_birth=birth)
            plan = plan_sweep(project_dir, cursors, recent=recent, codex_dir=codex_dir,
                              grok_dir=grok_dir, install_birth=birth)
            cursors, n = execute(plan, ingest_fn or graphiti_ingest, cursors, log=log)
            save_cursors(cursors, cursors_path)
            proposed = _maybe_propose_topic_directions(project_dir=project_dir, codex_dir=codex_dir,
                                                       grok_dir=grok_dir, log=log,
                                                       atividades_state=atividades_state)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)

    if (n or proposed or corrected) and reproject_fn is not False:
        (reproject_fn or reproject)()
    elif reproject_fn is None:
        # Communities are the automatic consolidation leg of the wake. They must still refresh on a
        # no-delta dispatch so the briefing can read the current graph before any skill reasoning.
        _maybe_consolidate()
    # graph recovery runs ALWAYS (not under `if n`) — a no-delta sweep still self-heals the graph.
    # The run's `log` is threaded through (Codex P2): a custom-log dry-run never projects the real
    # corpus (publisher.reproject_graph default-skips a non-canonical log).
    if graph_recover_fn is not False:
        (graph_recover_fn or reproject_graph)(log)
    return n


def run_rationalization_backlog(project_dir=None, *, log=eventlog.LOG, codex_dir=None,
                                complete_fn=None, completer_factory=None,
                                rationalize_fn=None, lentes_config=None,
                                reconcile_fn=None, project_fn=None, render_fn=None,
                                graph_store=None, graph_store_factory=None):
    """Explicit sleep-time entrypoint; deliberately absent from mechanical ``run()``.

    The provider is lazy and only constructed after a substantial pending session is found. A
    service/timer may execute this entrypoint with its own runtime timeout; predispatch never waits
    for cognition and needs no thread/subprocess lifecycle inside this module.
    """
    config = _lentes_config() if lentes_config is None else dict(lentes_config)
    backfill_days = config.get("backfill_days")
    version = config.get(
        "racionalizador_version", "racionalizador-v3-session-provenance")
    pending = plan_rationalizations(
        project_dir, log=log, codex_dir=codex_dir, backfill_days=backfill_days,
        racionalizador_version=version,
    )
    if pending:
        if complete_fn is None and completer_factory is None:
            def completer_factory(*, max_tokens):
                import llm_routes
                return llm_routes.completer_for("chat", max_tokens=max_tokens)
        result = rationalize_pending_sessions(
            project_dir,
            complete_fn,
            completer_factory=completer_factory,
            log=log,
            codex_dir=codex_dir,
            rationalize_fn=rationalize_fn,
            backfill_days=backfill_days,
            max_sessions_per_sweep=config.get(
                "max_sessions_per_sweep", DEFAULT_MAX_SESSIONS_PER_SWEEP),
            sweep_token_budget=config.get(
                "sweep_token_budget", DEFAULT_SWEEP_TOKEN_BUDGET),
            scene_turn_limit=config.get("scene_turn_limit", DEFAULT_SCENE_TURN_LIMIT),
            racionalizador_version=version,
        )
    else:
        result = {"attempted": [], "rationalized": [], "pending": [],
                  "usage": {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                            "estimated_tokens": 0},
                  "stopped_reason": None}

    downstream = {}

    def _best_effort(name, call):
        try:
            value = call()
            complete = getattr(value, "complete", True)
            downstream[name] = {"ok": bool(complete), "result": value}
        except Exception as exc:  # noqa: BLE001 — log is truth; projections retry next worker
            downstream[name] = {"ok": False,
                                "error": f"{type(exc).__name__}: {exc}"}
            print(f"sweep: lenses {name} skipped ({type(exc).__name__}: {exc}) — "
                  "checkpoint retained")

    def _reconcile():
        nonlocal reconcile_fn
        if reconcile_fn is None:
            import portfolio
            reconcile_fn = portfolio.reconcile
        return reconcile_fn(log)

    def _project():
        nonlocal project_fn, graph_store
        if project_fn is None:
            import publisher
            project_fn = publisher.project_lentes
        close_fn = None
        if graph_store is None:
            factory = graph_store_factory or _live_lenses_graph_store
            built = factory()
            if isinstance(built, tuple) and len(built) == 2:
                graph_store, close_fn = built
            else:
                graph_store = built
        try:
            return project_fn(log, graph_store)
        finally:
            if close_fn is not None:
                close_fn()

    def _render():
        nonlocal render_fn
        if render_fn is None:
            import portfolio
            render_fn = portfolio.render
        return render_fn(log)

    _best_effort("reconcile", _reconcile)
    _best_effort("project", _project)
    _best_effort("render", _render)
    result["downstream"] = downstream
    return result


def _live_lenses_graph_store():
    """Construct the live adapter lazily; return ``(store, close)`` for worker cleanup."""
    import _identity
    from graph_store import Neo4jGraphStore
    from neo4j import GraphDatabase
    uri, user, password = _identity.neo4j_conn()
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        store = Neo4jGraphStore(driver, group_id=_identity.require_group())
    except Exception:
        driver.close()
        raise
    return store, driver.close


def enqueue_rationalization(run_fn=None, timeout=2):
    """Ask systemd to start the detached worker; never spawn cognition in predispatch."""
    if run_fn is None:
        import subprocess
        run_fn = subprocess.run
    result = run_fn(
        ["systemctl", "--user", "start", "--no-block", "edge-rationalize.service"],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
    )
    return result.returncode == 0


def _recent_arg(argv):
    if "--recent" in argv:
        i = argv.index("--recent")
        return int(argv[i + 1]) if i + 1 < len(argv) else None
    return None


def main(argv):
    recent = _recent_arg(argv)
    if "--rationalize-only" in argv:
        result = run_rationalization_backlog()
        print(f"sweep: rationalized {len(result['rationalized'])} session(s); "
              f"{len(result['pending'])} pending; "
              f"{result['usage']['estimated_tokens']} estimated tokens")
        return
    if "--plan" in argv:
        cursors = load_cursors()
        if _codex_enabled(None, None):
            cursors = _codex_baseline(dict(cursors), None)
        if _grok_enabled(None, None):
            cursors = _grok_baseline(dict(cursors), None)
        plan = plan_sweep(None, cursors, recent=recent, install_birth=_install_birth())
        ingest = [p for p in plan if not p["skip"]]
        print(f"plan: {len(plan)} sessions with new lines; {len(ingest)} qualify to ingest"
              + (f" (recent={recent})" if recent else ""))
        for p in ingest:
            print(f"  - {p['id'][:8]}  +{len(p['body'])} chars  (→ watermark {p['watermark']})")
        return
    n = run(recent=recent)
    print(f"sweep: ingested {n} session-delta(s); wiki + Direction re-projected" if n
          else "sweep: nothing new (cursor up to date)")


if __name__ == "__main__":
    _reexec_repo_venv()
    main(sys.argv[1:])
