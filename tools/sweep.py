"""sweep — the pull-at-open digestion sweep (ADR-0008, issue #15). Genotype tool.

ONE idempotent, cursor-guarded pass over the transcript store. Every operator session's delta
since its cursor becomes (a) an `episode` event in the Tier-0 log (raw, ADR-0006) and (b) a
Graphiti episode — the extracted, non-curated tier. **CONTRACT C2**: extraction runs on the
delta only, never the whole store. **Keyed on the store, not on any skill** — a session that ran
no ed skill is still digested at the next sweep. Re-running is a no-op (the cursor guards it).
After ingest, the wiki and Direction **re-project** (sweep → extract → re-project → digest).

The pure planning (`plan_sweep`, cursors) carries no graph/LLM; `execute` takes an injected
`ingest_fn`, so the cursor/idempotency logic is testable without Neo4j or OpenAI.

Run:  .venv/bin/python tools/sweep.py           (sweep + re-project)
      .venv/bin/python tools/sweep.py --plan    (dry run: what the delta would digest)
"""
import json
import math
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cortex
import eventlog
import sessions
import _identity

CURSORS = REPO / "state" / "cursors.json"
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


# --- pure plan: the digestible deltas (reads files, no graph/LLM) ---
def plan_sweep(project_dir=None, cursors=None, recent=None):
    """For each session, the turns after its cursor + the new watermark, in **chronological order**
    (oldest first — bi-temporal ingest wants it). `skip` marks a delta too thin to ingest (left
    un-advanced to grow). Idempotent: a session at its watermark yields nothing new. `recent=N`
    bounds a run to the N most-recently-modified sessions (the rest backfill on later sweeps —
    the cursor makes the full sweep resumable)."""
    if project_dir is None:
        project_dir = _identity.project_dir()   # fail-loud seam (ADR-0015), never a baked-in path
    cursors = cursors or {}
    found = []
    for s in sessions.list_sessions(project_dir):
        seen = cursors.get(s.id, 0)
        turns, watermark = sessions.delta(s.path, seen)
        if watermark <= seen or not turns:
            continue  # no new raw lines / no new dialogue
        found.append((Path(s.path).stat().st_mtime, s, turns, watermark))
    found.sort(key=lambda x: x[0])           # chronological
    if recent:
        found = found[-recent:]              # the N newest, still chronological
    return [{"id": s.id, "path": str(s.path), "turns": turns, "watermark": watermark,
             "body": (body := clean_body(turns)), "skip": not _qualifies(turns, body)}
            for _, s, turns, watermark in found]


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
        eventlog.append("episode", f"session:{it['id']}",
                        {"session": it["id"], "watermark": it["watermark"], "chars": len(it["body"]),
                         "medium_tier": "low_tier"},
                        log=log)
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
            sid = it["id"][:8]
            ref = _parse_ts(_first_ts(it["path"]))   # all sub-episodes share the session's ref-time
            chunks = chunk_episode_body(it["body"])   # one big session → several context-fit episodes (#53)
            failed = False
            for k, chunk in enumerate(chunks):
                name = f"session-{sid}" if len(chunks) == 1 else f"session-{sid}-p{k + 1}"
                try:
                    prev = await bounded_previous_uuids(g, ref)
                    await g.add_episode(name=name, episode_body=chunk,
                                        source=EpisodeType.message,
                                        source_description="Claude work session (mentee<->edge)",
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


def run(project_dir=None, ingest_fn=None, cursors_path=CURSORS, reproject_fn=None,
        log=eventlog.LOG, recent=None, graph_recover_fn=None, group=None):
    """Full sweep: plan the deltas → ingest + log + advance cursors → re-project (if anything new) →
    graph-recover (ALWAYS). `recent=N` bounds this run to the N newest sessions (the rest backfill on
    later sweeps). Graph recovery runs EVERY sweep, independent of `n` (Codex P2), so a no-delta sweep
    after Neo4j comes back still heals a publish-time-missed projection."""
    # ADR-0015 preflight (codex gate): an install that has not declared who it is must not
    # write as anyone — Tier-0 episode appends and cursor advances ARE writes. Identity fails
    # loud HERE, before the delta is consumed, never mid-sweep (where a rerun would see the
    # delta as already eaten by a groupless ghost). Tests pass `group` explicitly (hermetic).
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
            plan = plan_sweep(project_dir, cursors, recent=recent)
            cursors, n = execute(plan, ingest_fn or graphiti_ingest, cursors, log=log)
            save_cursors(cursors, cursors_path)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
    if n and reproject_fn is not False:
        (reproject_fn or reproject)()
    # graph recovery runs ALWAYS (not under `if n`) — a no-delta sweep still self-heals the graph.
    # The run's `log` is threaded through (Codex P2): a custom-log dry-run never projects the real
    # corpus (publisher.reproject_graph default-skips a non-canonical log).
    if graph_recover_fn is not False:
        (graph_recover_fn or reproject_graph)(log)
    return n


def _recent_arg(argv):
    if "--recent" in argv:
        i = argv.index("--recent")
        return int(argv[i + 1]) if i + 1 < len(argv) else None
    return None


def main(argv):
    recent = _recent_arg(argv)
    if "--plan" in argv:
        plan = plan_sweep(None, load_cursors(), recent=recent)
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
    main(sys.argv[1:])
