"""emprego — porteiro de Mineração: accepted mentee employment → Cortex intake.

Contract (operator + turing 2026-07-26, PLAN-cortex-employment-gate):
  Nothing enters Cortex that mining did not accept as mentee employment material.
  The mining verdict is sessao.racionalizada.stitch.attribution.activity_relevant.

Slice 1 ships the pure fold + injectable project/bypass (callers arrive in later slices).
No session JSONL reopen. Module imports bare (no neo4j/graphiti at import time).
"""
from __future__ import annotations

import eventlog

# Episode name prefix for employment projections (bypass residue is session-*).
EMPREGO_EPISODE_PREFIX = "emprego-"
BYPASS_EPISODE_PREFIX = "session-"


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


def project(log=eventlog.LOG, group=None, *, existing_names=None, add_fn=None, group_fn=None):
    """Idempotent graph write of accepted employment digests.

    Production: lazy Graphiti adapters (slice 2 wires real add). Dark → None.
    Tests inject existing_names (set of episode names) + add_fn(name, body, ref_time).
    Returns {"added": n, "total": m} or None when graph dark.
    """
    items = accepted_employment(log=log)
    if existing_names is None and add_fn is None:
        # Production path: not fully wired until slice 2; degrade dark.
        try:
            if group_fn is not None:
                group = group_fn()
            elif group is None:
                import _identity
                group = _identity.require_group()
        except Exception:
            return None
        try:
            existing = _existing_emprego_names(group)
            if existing is None:
                return None
            add = _make_graphiti_add(group)
            if add is None:
                return None
        except Exception:
            return None
        existing_names = existing
        add_fn = add
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
            # best-effort per item; continue others
            continue
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


def _make_graphiti_add(group):
    """Real Graphiti add lands in slice 2; until then production project stays dark."""
    return None
