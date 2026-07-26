"""emprego — porteiro de Mineração: accepted mentee employment → Cortex intake.

Contract (operator + turing 2026-07-26, PLAN-cortex-employment-gate):
  Nothing enters Cortex that mining did not accept as mentee employment material.
  The mining verdict is sessao.racionalizada.stitch.attribution.activity_relevant.

No session JSONL reopen. Module imports bare (no neo4j/graphiti at import time).
Graph writes project accepted digests only — never raw dialogue.
"""
from __future__ import annotations

from datetime import datetime, timezone

import eventlog

# Episode name prefix for employment projections (bypass residue is session-*).
EMPREGO_EPISODE_PREFIX = "emprego-"
BYPASS_EPISODE_PREFIX = "session-"

# Tier-1 ONLY: body chunking for the Graphiti extractor window (moved from sweep).
MAX_EPISODE_CHARS = 48_000
PREV_CONTEXT_MAX_CHARS = 120_000


def _attribution(payload):
    stitch = payload.get("stitch") if isinstance(payload.get("stitch"), dict) else {}
    attr = stitch.get("attribution") if isinstance(stitch.get("attribution"), dict) else {}
    return attr


def _activity_relevant(payload):
    return _attribution(payload).get("activity_relevant") is True


def _usable_accepted_payload(payload):
    """Fail-dark: skip corrupt rows rather than raising from the fold."""
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("rationalization_id"), str) or not payload["rationalization_id"]:
        return False
    if not isinstance(payload.get("sessao_id"), str) or not payload["sessao_id"]:
        return False
    attr = _attribution(payload)
    for key in ("human_purpose", "edge_execution", "shared_outcome"):
        val = attr.get(key)
        if not isinstance(val, str) or not val.strip():
            return False
    ops = payload.get("operacoes")
    if not isinstance(ops, list) or not ops or not all(
            isinstance(o, str) and o.strip() for o in ops):
        return False
    return _activity_relevant(payload)


def _atividades_for_rid(events, rid):
    """Join atividade.opened/touched by rationalization_id for digest lines."""
    opens = []
    touches_by_ref = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        p = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if p.get("rationalization_id") != rid:
            continue
        et = event.get("type")
        if et == "atividade.opened":
            opens.append(p)
        elif et == "atividade.touched":
            ref = p.get("ref")
            if isinstance(ref, str) and ref:
                touches_by_ref[ref] = p
    lines = []
    for op in opens:
        finalidade = op.get("finalidade")
        if not isinstance(finalidade, str) or not finalidade.strip():
            continue
        ulid = op.get("ulid")
        novo = None
        if isinstance(ulid, str) and ulid in touches_by_ref:
            n = touches_by_ref[ulid].get("novo")
            if isinstance(n, str) and n.strip():
                novo = n.strip()
        if novo is None:
            n = op.get("novo")
            if isinstance(n, str) and n.strip():
                novo = n.strip()
        if novo is None:
            novo = finalidade.strip()
        lines.append(f"- {finalidade.strip()} — {novo}")
    return lines


def _digest_body(payload, atividade_lines=None):
    """Deterministic employment digest — extractor input contract (omit empty sections)."""
    attr = _attribution(payload)
    ops = payload.get("operacoes") or []
    lines = [
        f"FINALIDADE: {attr['human_purpose'].strip()}",
        f"EXECUCAO: {attr['edge_execution'].strip()}",
        f"RESULTADO: {attr['shared_outcome'].strip()}",
        f"OPERACOES: {', '.join(o.strip() for o in ops)}",
    ]
    if atividade_lines:
        lines.append("ATIVIDADES:")
        lines.extend(atividade_lines)
    pres = []
    epi = payload.get("epistemico") if isinstance(payload.get("epistemico"), dict) else {}
    for item in epi.get("presuncoes") or []:
        if isinstance(item, dict):
            t = item.get("texto")
            if isinstance(t, str) and t.strip():
                pres.append(f"- {t.strip()}")
    if pres:
        lines.append("PRESSUPOSTOS:")
        lines.extend(pres)
    cenas = payload.get("cenas")
    cena_lines = []
    if isinstance(cenas, list):
        for c in cenas:
            if isinstance(c, dict):
                s = c.get("summary")
                if isinstance(s, str) and s.strip():
                    cena_lines.append(f"- {s.strip()}")
    if cena_lines:
        lines.append("CENAS:")
        lines.extend(cena_lines)
    return "\n".join(lines)


def accepted_employment(log=eventlog.LOG):
    """Pure fold: latest accepted sessao.racionalizada per session → employment digests.

    activity_relevant is True only. No graph, no LLM, no session JSONL.
    [] on empty/unusable log. Fail-dark skip on corrupt rows.
    """
    events = eventlog.read(
        types=["sessao.racionalizada", "atividade.opened", "atividade.touched"],
        log=log,
    )
    rationalized = [e for e in events if e.get("type") == "sessao.racionalizada"]
    superseded = {
        p["supersedes"]
        for e in rationalized
        for p in [e.get("payload") if isinstance(e.get("payload"), dict) else {}]
        if isinstance(p.get("supersedes"), str) and p["supersedes"]
    }
    out = []
    for event in rationalized:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        rid = payload.get("rationalization_id")
        if not isinstance(rid, str) or rid in superseded:
            continue
        if not _usable_accepted_payload(payload):
            continue
        atv_lines = _atividades_for_rid(events, rid)
        out.append({
            "session_id": payload["sessao_id"],
            "rationalization_id": rid,
            "surface": payload.get("surface") if isinstance(payload.get("surface"), str) else "",
            "ref_time": event.get("ts") if isinstance(event.get("ts"), str) else "",
            "body": _digest_body(payload, atv_lines),
        })
    return out


def episode_name(rationalization_id):
    """Deterministic Episodic name for an accepted rationalization.

    ponytail: rid truncated to 16 hex (~64 bits). Collision → second item
    skipped as already-projected until --migrate wipe-rebuild. Fine at O(100).
    """
    return f"{EMPREGO_EPISODE_PREFIX}{rationalization_id[:16]}"


def parse_ts(ts):
    if not ts:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def chunk_episode_body(body, max_chars=MAX_EPISODE_CHARS):
    """Split a body into <= max_chars chunks at newline boundaries (lossless)."""
    if len(body) <= max_chars:
        return [body]
    chunks, cur = [], ""
    for line in body.splitlines(keepends=True):
        while len(line) > max_chars:
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


def project(log=eventlog.LOG, group=None, *, existing_names=None, add_fn=None, group_fn=None):
    """Idempotent graph write of accepted employment digests.

    Production: Graphiti add_episode on digests only. Dark → None.
    Tests inject existing_names + add_fn(name, body, ref_time).
    Returns {"added": n, "total": m} or None when graph dark.
    """
    items = accepted_employment(log=log)
    if existing_names is None and add_fn is None:
        try:
            if group_fn is not None:
                group = group_fn()
            elif group is None:
                import _identity
                group = _identity.require_group()
        except Exception:
            return None
        try:
            return _project_graphiti(items, group)
        except Exception as e:
            print(f"emprego: project dark ({type(e).__name__}: {e})")
            return None
    if existing_names is None or add_fn is None:
        return None
    existing_names = set(existing_names)
    added = 0
    for item in items:
        name = episode_name(item["rationalization_id"])
        if name in existing_names:
            continue
        try:
            add_fn(name, item["body"], item["ref_time"])
            existing_names.add(name)
            added += 1
        except Exception:
            continue
    return {"added": added, "total": len(items)}


def _load_openai_key():
    import os
    from pathlib import Path
    if os.environ.get("OPENAI_API_KEY"):
        return

    def _from_file(f):
        if not f.exists():
            return False
        for line in f.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if "OPENAI_API_KEY" in line and "=" in line:
                os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
                return True
        return False

    home = Path.home()
    for root in filter(None, [
        os.environ.get("EDGE_HOME"),
        str(Path(__file__).resolve().parent.parent),
        str(home / "edge"),
    ]):
        if _from_file(Path(root) / "secrets" / "openai.env"):
            return
    _from_file(home / ".edge-sandbox-kit" / "openai.env")


def _project_graphiti(items, group):
    """Real Graphiti write path — employment digests only. Early-exit without Graphiti import."""
    existing = _existing_emprego_names(group)
    if existing is None:
        return None
    to_add = [it for it in items
              if episode_name(it["rationalization_id"]) not in existing]
    if not to_add:
        return {"added": 0, "total": len(items)}
    return _project_graphiti_add(to_add, items, group)


def _project_graphiti_add(to_add, items, group):
    import asyncio
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client import LLMConfig, OpenAIClient
    import _identity

    _load_openai_key()
    neo = _identity.neo4j_conn()

    async def bounded_previous_uuids(g, ref):
        eps = await g.retrieve_episodes(
            ref, last_n=10, group_ids=[group], source=EpisodeType.message)
        chosen, total = [], 0
        for ep in reversed(eps):
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
        added = 0
        try:
            for it in to_add:
                name = episode_name(it["rationalization_id"])
                ref = parse_ts(it.get("ref_time"))
                chunks = chunk_episode_body(it["body"])
                failed = False
                for k, chunk in enumerate(chunks):
                    ep_name = name if len(chunks) == 1 else f"{name}-{k}"
                    try:
                        prev = await bounded_previous_uuids(g, ref)
                        await g.add_episode(
                            name=ep_name,
                            episode_body=chunk,
                            source=EpisodeType.message,
                            source_description="emprego digest (mentee employment)",
                            reference_time=ref,
                            group_id=group,
                            previous_episode_uuids=prev,
                        )
                        print(f"  + emprego {ep_name} ({len(chunk)} chars)")
                    except Exception as e:
                        failed = True
                        print(f"  ! emprego FAILED {ep_name}: {type(e).__name__}: {e}")
                if not failed:
                    added += 1
        finally:
            await g.close()
        return added

    added = asyncio.run(go())
    return {"added": added, "total": len(items)}


def bypass_episodes(group=None, *, query_fn=None):
    """Read-only: legacy session-* Episodic names in the group. None = dark."""
    if query_fn is not None:
        try:
            return list(query_fn(group))
        except Exception:
            return None
    try:
        if group is None:
            import _identity
            group = _identity.require_group()
        names = _query_bypass_names(group)
        return names
    except Exception:
        return None


def _existing_emprego_names(group):
    """MATCH Episodic names with emprego- prefix. None = dark."""
    try:
        import communities
        drv = communities._driver()
        if drv is None:
            return None
        with drv.session() as s:
            rows = s.run(
                "MATCH (ep:Episodic {group_id:$g}) "
                "WHERE ep.name STARTS WITH $p "
                "RETURN ep.name AS name",
                g=group, p=EMPREGO_EPISODE_PREFIX,
            ).data()
        return {r["name"] for r in rows if r.get("name")}
    except Exception:
        return None


def _query_bypass_names(group):
    import communities
    drv = communities._driver()
    if drv is None:
        return None
    with drv.session() as s:
        rows = s.run(
            "MATCH (ep:Episodic {group_id:$g}) "
            "WHERE ep.name STARTS WITH $p "
            "RETURN ep.name AS name ORDER BY name",
            g=group, p=BYPASS_EPISODE_PREFIX,
        ).data()
    return [r["name"] for r in rows if r.get("name")]


def reset_bypass(group=None, keep_curated=True, *, run_tx=None):
    """Migration: wipe rebuildable bypass projections (Community, non-curated Entity,
    session-* Episodic). Curated parceiro/curated_cluster entities preserved when
    keep_curated=True. Returns counts or None if dark.

    Tests inject run_tx(fn) that receives a recording session-like object.
    """
    try:
        if group is None:
            import _identity
            group = _identity.require_group()
    except Exception:
        return None

    counts = {"communities": 0, "entities": 0, "episodics": 0}

    def _tx(tx):
        n_c = tx.run(
            "MATCH (c:Community {group_id:$g}) RETURN count(c) AS n", g=group
        ).single()["n"]
        tx.run("MATCH (c:Community {group_id:$g}) DETACH DELETE c", g=group)
        if keep_curated:
            n_e = tx.run(
                "MATCH (e:Entity {group_id:$g}) "
                "WHERE e.parceiro IS NULL AND e.curated_cluster IS NULL "
                "RETURN count(e) AS n", g=group
            ).single()["n"]
            tx.run(
                "MATCH (e:Entity {group_id:$g}) "
                "WHERE e.parceiro IS NULL AND e.curated_cluster IS NULL "
                "DETACH DELETE e", g=group)
        else:
            n_e = tx.run(
                "MATCH (e:Entity {group_id:$g}) RETURN count(e) AS n", g=group
            ).single()["n"]
            tx.run("MATCH (e:Entity {group_id:$g}) DETACH DELETE e", g=group)
        n_ep = tx.run(
            "MATCH (ep:Episodic {group_id:$g}) "
            "WHERE ep.name STARTS WITH $p RETURN count(ep) AS n",
            g=group, p=BYPASS_EPISODE_PREFIX,
        ).single()["n"]
        tx.run(
            "MATCH (ep:Episodic {group_id:$g}) "
            "WHERE ep.name STARTS WITH $p DETACH DELETE ep",
            g=group, p=BYPASS_EPISODE_PREFIX,
        )
        counts["communities"] = int(n_c or 0)
        counts["entities"] = int(n_e or 0)
        counts["episodics"] = int(n_ep or 0)

    if run_tx is not None:
        try:
            run_tx(_tx)
            return counts
        except Exception:
            return None
    try:
        import communities
        drv = communities._driver()
        if drv is None:
            return None
        with drv.session() as s:
            s.execute_write(_tx)
        return counts
    except Exception as e:
        print(f"emprego: reset_bypass dark ({type(e).__name__}: {e})")
        return None


def main(argv=None):
    """CLI: --check (read-only) | --migrate (reset_bypass + project)."""
    import argparse
    import sys
    p = argparse.ArgumentParser(description="emprego porteiro — check/migrate Cortex intake")
    p.add_argument("--check", action="store_true", help="list bypass episodes + unprojected count")
    p.add_argument("--migrate", action="store_true", help="wipe bypass projections + project digests")
    p.add_argument("--group", default=None, help="graph group_id (default: install identity)")
    args = p.parse_args(argv)
    if not args.check and not args.migrate:
        p.print_help()
        return 2
    log = eventlog.LOG
    items = accepted_employment(log=log)
    bypass = bypass_episodes(group=args.group)
    if args.check:
        print(f"accepted_employment: {len(items)}")
        if bypass is None:
            print("bypass_episodes: DARK (graph unreachable)")
        else:
            print(f"bypass_episodes: {len(bypass)}")
            for name in bypass[:50]:
                print(f"  - {name}")
            if len(bypass) > 50:
                print(f"  … +{len(bypass) - 50} more")
        # unprojected: need graph existing names
        try:
            import _identity
            g = args.group or _identity.require_group()
            existing = _existing_emprego_names(g) or set()
        except Exception:
            existing = set()
            print("existing emprego episodes: DARK")
        missing = [it for it in items
                   if episode_name(it["rationalization_id"]) not in existing]
        print(f"unprojected accepted: {len(missing)}")
        return 0
    if args.migrate:
        wiped = reset_bypass(group=args.group)
        print(f"reset_bypass: {wiped}")
        out = project(log=log, group=args.group)
        print(f"project: {out}")
        try:
            import communities
            if __import__("os").environ.get("EDGE_COMMUNITIES") == "1":
                written = communities.consolidate(group=args.group)
                print(f"communities: {len(written or [])} clusters")
        except Exception as e:
            print(f"communities skipped ({type(e).__name__}: {e})")
        return 0 if wiped is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())


