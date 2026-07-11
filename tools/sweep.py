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
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cortex
import eventlog
import sessions
import _identity

CURSORS = REPO / "state" / "cursors.json"
CODEX_BASELINE_KEY = "_codex_baselined"
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
    """Claude keeps its historical cursor key; Codex is namespaced to avoid collisions."""
    return f"codex:{session.id}" if session.surface == "codex" else session.id


def _source_description(item):
    return ("Codex work session (mentee<->edge)"
            if item.get("surface") == "codex"
            else "Claude work session (mentee<->edge)")


def _episode_name(item, chunk_index=None):
    sid = item["id"].replace(":", "-")[:24]
    base = f"session-{sid}"
    return base if chunk_index is None else f"{base}-p{chunk_index + 1}"


def _codex_enabled(project_dir, codex_dir):
    """Default real sweeps include Codex. Hermetic tests that pass project_dir stay Claude-only
    unless they explicitly pass codex_dir."""
    return codex_dir is not False and (codex_dir is not None or project_dir is None)


def _codex_baseline(cursors, codex_dir=None):
    """First Codex-aware run starts from now: existing Codex logs are marked seen but not ingested.
    New sessions/deltas after this baseline flow through normally."""
    if cursors.get(CODEX_BASELINE_KEY):
        return cursors
    for s in sessions.list_codex_sessions(codex_dir):
        if not sessions.is_user_session(s):
            continue
        _turns, watermark = sessions.delta(s.path, 0, surface=s.surface)
        cursors[_cursor_id(s)] = watermark
    cursors[CODEX_BASELINE_KEY] = True
    return cursors


def _load_install_env():
    """Load this install's secrets for real runtime sweeps. Hermetic tests pass project_dir."""
    try:
        import _secrets
        _secrets.load_env(_identity._env_dir(_identity.AGENT_YAML))
    except Exception:
        pass


# --- pure plan: the digestible deltas (reads files, no graph/LLM) ---
def plan_sweep(project_dir=None, cursors=None, recent=None, codex_dir=None):
    """For each session, the turns after its cursor + the new watermark, in **chronological order**
    (oldest first — bi-temporal ingest wants it). `skip` marks a delta too thin to ingest (left
    un-advanced to grow). Idempotent: a session at its watermark yields nothing new. `recent=N`
    bounds a run to the N most-recently-modified sessions (the rest backfill on later sweeps —
    the cursor makes the full sweep resumable)."""
    include_codex = _codex_enabled(project_dir, codex_dir)
    if project_dir is None:
        project_dir = _identity.project_dir()   # fail-loud seam (ADR-0015), never a baked-in path
    cursors = cursors or {}
    found = []
    for s in sessions.list_sessions(project_dir):
        if not sessions.is_user_session(s):
            continue
        sid = _cursor_id(s)
        seen = cursors.get(sid, 0)
        turns, watermark = sessions.delta(s.path, seen, surface=s.surface)
        if watermark <= seen or not turns:
            continue  # no new raw lines / no new dialogue
        found.append((Path(s.path).stat().st_mtime, s, turns, watermark, sid))
    if include_codex:
        for s in sessions.list_codex_sessions(codex_dir):
            if not sessions.is_user_session(s):
                continue
            sid = _cursor_id(s)
            seen = cursors.get(sid, 0)
            turns, watermark = sessions.delta(s.path, seen, surface=s.surface)
            if watermark <= seen or not turns:
                continue  # no new raw lines / no new dialogue
            found.append((Path(s.path).stat().st_mtime, s, turns, watermark, sid))
    found.sort(key=lambda x: x[0])           # chronological
    if recent:
        found = found[-recent:]              # the N newest, still chronological
    return [{"id": sid, "raw_id": s.id, "surface": s.surface, "path": str(s.path),
             "turns": turns, "watermark": watermark,
             "body": (body := clean_body(turns)), "skip": not _qualifies(turns, body)}
            for _, s, turns, watermark, sid in found]


# --- bounded a-posteriori rationalization (log-checkpointed; no cursor) ---
def _substantial_for_rationalization(turns):
    """The quente criterion, applied to the already-normalized persisted dialogue."""
    human = [turn for turn in turns if turn.role == "human"]
    return len(human) >= 5 and sum(len(turn.text) for turn in human) >= 1000


def _validate_lentes_limit(value, name, *, allow_zero=False):
    floor = 0 if allow_zero else 1
    if (not isinstance(value, int) or isinstance(value, bool) or value < floor):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"lentes.{name} must be a {qualifier} integer")
    return value


def _lentes_config(path=None):
    """Read only the phenotype knobs owned by the lenses coordinator."""
    path = REPO / "agent.yaml" if path is None else Path(path)
    try:
        import yaml
        raw = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raw = {}
    lenses = raw.get("lentes") if isinstance(raw, dict) else None
    lenses = lenses if isinstance(lenses, dict) else {}
    config = {
        "backfill_days": lenses.get("backfill_days"),
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
                             racionalizador_version="racionalizador-v1"):
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


def plan_rationalizations(project_dir=None, *, log=eventlog.LOG, codex_dir=None,
                          backfill_days=None, now=None,
                          racionalizador_version="racionalizador-v1"):
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

    discovered = list(sessions.list_sessions(project_dir))
    if include_codex:
        discovered.extend(sessions.list_codex_sessions(codex_dir))
    pending = []
    for session in discovered:
        if not sessions.is_user_session(session):
            continue
        path = Path(session.path)
        mtime = path.stat().st_mtime
        if floor is not None and mtime < floor:
            continue
        turns, watermark = sessions.delta(path, 0, surface=session.surface)
        if not turns or not _substantial_for_rationalization(turns):
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
    pending.sort(key=lambda item: (item["mtime"], item["surface"], item["id"]))
    return pending


def _add_usage(total, addition):
    addition = addition if isinstance(addition, dict) else {}
    for field in ("calls", "input_tokens", "output_tokens", "estimated_tokens"):
        value = addition.get(field, 0)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            total[field] += value


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
    racionalizador_version="racionalizador-v1",
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
    stopped_reason = None
    bounded_complete_fn = _bounded_sweep_completer(
        complete_fn, completer_factory, sweep_token_budget)
    with coordinator_lock.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            pending = plan_rationalizations(
                project_dir,
                log=log,
                codex_dir=codex_dir,
                backfill_days=backfill_days,
                racionalizador_version=racionalizador_version,
            )
            for item in pending:
                if len(rationalized) >= max_sessions_per_sweep:
                    stopped_reason = "max_sessions_per_sweep"
                    break
                remaining = (None if sweep_token_budget is None else
                             max(0, sweep_token_budget - usage["estimated_tokens"]))
                if remaining == 0:
                    stopped_reason = "budget_exhausted"
                    break
                attempted.append(item["id"])
                result = rationalize_fn(
                    item["id"],
                    item["turns"],
                    bounded_complete_fn,
                    log,
                    surface=item["surface"],
                    watermark=item["watermark"],
                    racionalizador_version=racionalizador_version,
                    sweep_token_budget=remaining,
                    scene_turn_limit=scene_turn_limit,
                )
                if not isinstance(result, dict):
                    raise TypeError("rationalize_fn must return a dict")
                _add_usage(usage, result.get("usage"))
                reason = result.get("skipped_reason")
                if reason == "already_rationalized":
                    continue
                if reason:
                    stopped_reason = reason
                    break
                rationalized.append(item["id"])
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
        if it.get("surface") == "codex":
            payload["surface"] = "codex"
        eventlog.append("episode", f"session:{it['id']}", payload, log=log)
        cursors[it["id"]] = it["watermark"]
    if qualifying and ingest_fn is not None:           # Tier-1: graph projection, best-effort
        # BOUNDED + degrade-dark (#62): Tier-0 (episode + cursor) is ALREADY durable above, so the
        # graph ingest must never gate the wake. It runs on a daemon thread with a hard deadline —
        # a HANG (add_episode on a network call with no client timeout) degrades dark LOUD exactly
        # like a raise; the graph re-projects from the log. Fail loud on a bad budget, never un-cap.
        budget_raw = os.environ.get("EDGE_SWEEP_INGEST_BUDGET_S", "30")
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

    async def go():
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
                    await g.add_episode(name=name, episode_body=chunk,
                                        source=EpisodeType.message,
                                        source_description=_source_description(it),
                                        reference_time=ref, group_id=group,
                                        previous_episode_uuids=prev)
                    print(f"  + ingested {name} ({len(chunk)} chars)")
                except Exception as e:
                    failed = True
                    print(f"  ! FAILED {name}: {type(e).__name__}: {e}")
            if not failed:           # a session counts as ingested only if every sub-episode landed
                ok.add(it["id"])
        await g.close()

    asyncio.run(go())
    return ok


def _openai_embed(text):
    """The real embedder: one OpenAI embedding call (lazy-imported so importing sweep on bare
    python3 still works). Used when `embed_and_signal` is called without an injected `embed_fn`."""
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
    como o graph-ingest — NUNCA derruba um sweep (grafo/LLM fora → skip logado)."""
    if os.environ.get("EDGE_COMMUNITIES") != "1":
        return
    try:
        import communities
        written = communities.consolidate()
        print(f"sweep: communities consolidadas — {len(written or [])} clusters")
    except Exception as e:
        print(f"sweep: communities skipped ({type(e).__name__}: {e}) — graph/LLM leg dark")


def _topic_direction_window_days():
    raw = os.environ.get("EDGE_TOPIC_DIRECTION_WINDOW_DAYS", "7")
    try:
        val = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"EDGE_TOPIC_DIRECTION_WINDOW_DAYS={raw!r} is not an integer")
    if val <= 0:
        raise ValueError(f"EDGE_TOPIC_DIRECTION_WINDOW_DAYS={raw!r} must be positive")
    return val


def _maybe_propose_topic_directions(project_dir=None, codex_dir=None, log=eventlog.LOG):
    """Recent Voz -> topic threads -> Direction.proposed.

    This is the automatic non-curated tier the wake can safely run before assemble reads Direction.
    It never promotes to `set`, and it never reopens a dropped/set steer.
    """
    if os.environ.get("EDGE_TOPIC_DIRECTION", "1").lower() in {"0", "false", "no", "off"}:
        return 0
    try:
        import topic_threads
        out = topic_threads.sync_recent_topic_memory(
            window_days=_topic_direction_window_days(),
            project_dir=project_dir,
            codex_dir=codex_dir,
            all_stores=(project_dir is None),
            log=log,
        )
        if out.get("total"):
            print(f"sweep: session topics indexed {out.get('topics', 0)}; "
                  f"topic threads proposed {out.get('directions', 0)} Direction item(s)")
        return out.get("total", 0)
    except Exception as e:  # noqa: BLE001 — automatic inference must not gate the wake
        print(f"sweep: topic-thread Direction skipped ({type(e).__name__}: {e}) — "
              "wake continues; grill can still curate existing Direction")
        return 0


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
        wiki_render.main(group, str(REPO / "state" / "wiki"), "threads")
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


def run(project_dir=None, ingest_fn=None, cursors_path=CURSORS, reproject_fn=None,
        log=eventlog.LOG, recent=None, graph_recover_fn=None, group=None, codex_dir=None):
    """Full sweep: plan the deltas → ingest + log + advance cursors → re-project (if anything new) →
    graph-recover (ALWAYS). `recent=N` bounds this run to the N newest sessions (the rest backfill on
    later sweeps). Graph recovery runs EVERY sweep, independent of `n` (Codex P2), so a no-delta sweep
    after Neo4j comes back still heals a publish-time-missed projection."""
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
    import fcntl
    lock_path = Path(cursors_path).with_name(Path(cursors_path).name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            cursors = load_cursors(cursors_path)
            if _codex_enabled(project_dir, codex_dir):
                cursors = _codex_baseline(cursors, codex_dir)
            plan = plan_sweep(project_dir, cursors, recent=recent, codex_dir=codex_dir)
            cursors, n = execute(plan, ingest_fn or graphiti_ingest, cursors, log=log)
            save_cursors(cursors, cursors_path)
            proposed = _maybe_propose_topic_directions(project_dir=project_dir, codex_dir=codex_dir,
                                                       log=log)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)

    if (n or proposed) and reproject_fn is not False:
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
    version = config.get("racionalizador_version", "racionalizador-v1")
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
        plan = plan_sweep(None, cursors, recent=recent)
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
