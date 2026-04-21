"""Claim/thread continuity facts, projections, and shadow validation."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .telemetry import current_actor, current_cycle_id, emit_shadow_event
from .router_client import make_client

SCRIPT_DIR = Path(__file__).resolve().parent
_CONFIG_DIR = SCRIPT_DIR.parent.parent / "config"
if str(_CONFIG_DIR) not in sys.path:
    sys.path.insert(0, str(_CONFIG_DIR))

try:
    from paths import (  # type: ignore
        CLAIMS_DIGEST_FILE,
        CLAIMS_VALIDATION_FILE,
        CONTINUITY_DELTAS_DIR,
        ENTRIES_DIR,
        EVENTS_FILE,
        ORPHAN_CLAIMS_FILE,
        STATE_EVENTS_FILE,
        THREADS_DIR,
    )
except ImportError:  # pragma: no cover
    from pathlib import Path as _Path

    _ROOT = _Path.home() / "edge"
    ENTRIES_DIR = _ROOT / "blog" / "entries"
    EVENTS_FILE = _ROOT / "logs" / "events.jsonl"
    STATE_EVENTS_FILE = _ROOT / "state" / "events" / "log.jsonl"
    THREADS_DIR = _ROOT / "threads"
    CLAIMS_DIGEST_FILE = _ROOT / "state" / "projections" / "claims-digest.json"
    ORPHAN_CLAIMS_FILE = _ROOT / "state" / "projections" / "orphan-claims.json"
    CLAIMS_VALIDATION_FILE = _ROOT / "state" / "projections" / "claims-validation.json"
    CONTINUITY_DELTAS_DIR = _ROOT / "state" / "projections" / "continuity-deltas"


CLAIM_STALE_DAYS = 14
ORPHAN_CLUSTER_MIN_SCORE = 4
_STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "das", "dos", "para", "por", "em", "no",
    "na", "nos", "nas", "um", "uma", "as", "os", "que", "se", "com", "sem",
    "and", "or", "the", "to", "of", "in", "for", "is", "are", "be", "this",
    "that", "it", "on", "we", "não", "nao", "ser", "tem", "mais", "menos",
    "sobre", "still", "open", "gap", "claim", "thread", "new",
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _read_frontmatter(entry_path: Path) -> tuple[dict[str, Any], str]:
    raw = entry_path.read_text(encoding="utf-8", errors="replace")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    fm = yaml.safe_load(parts[1]) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, parts[2]


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    else:
        return []
    return [str(item).strip() for item in items if str(item).strip()]


def _claim_text(claim: Any) -> str:
    if isinstance(claim, dict):
        return str(claim.get("claim") or claim.get("text") or "").strip()
    return str(claim).lstrip("! ").strip()


def _claim_status(claim: Any) -> str:
    if isinstance(claim, dict):
        status = str(claim.get("status", "")).strip().lower()
        if status in {"unverified", "open", "disputed"}:
            return "gap"
        return "verified"
    return "gap" if isinstance(claim, str) and claim.startswith("!") else "verified"


def _claim_id(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return "claim-" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _entry_slug(entry_path: Path) -> str:
    return entry_path.stem


def _entry_href(entry_path: Path) -> str:
    return f"/entry/{entry_path.stem}"


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        try:
            return datetime.fromisoformat(raw + "T00:00:00+00:00")
        except ValueError:
            return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _claim_occurrences(entries_dir: Path = ENTRIES_DIR) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not entries_dir.exists():
        return rows
    for entry_path in sorted(entries_dir.glob("*.md")):
        try:
            fm, _body = _read_frontmatter(entry_path)
        except Exception:
            continue
        raw_claims = fm.get("claims") or []
        if not isinstance(raw_claims, list) or not raw_claims:
            continue
        threads = _normalize_string_list(fm.get("threads") or [])
        report = str(fm.get("report") or "").strip() or None
        title = str(fm.get("title") or entry_path.stem).strip()
        date_value = str(fm.get("date") or "").strip()
        date_dt = _parse_ts(date_value) or datetime.fromtimestamp(entry_path.stat().st_mtime, timezone.utc)
        for position, claim in enumerate(raw_claims):
            text = _claim_text(claim)
            if not text:
                continue
            rows.append(
                {
                    "claim_id": _claim_id(text),
                    "text": text,
                    "kind": _claim_status(claim),
                    "threads": list(threads),
                    "artifact_filename": entry_path.name,
                    "artifact_slug": _entry_slug(entry_path),
                    "artifact_href": _entry_href(entry_path),
                    "artifact_title": title,
                    "report": report,
                    "date": date_dt.isoformat(),
                    "position": position,
                }
            )
    return rows


def _aggregate_claims(entries_dir: Path = ENTRIES_DIR) -> list[dict[str, Any]]:
    today = _now().date()
    buckets: dict[str, dict[str, Any]] = {}
    for item in _claim_occurrences(entries_dir):
        bucket = buckets.setdefault(
            item["claim_id"],
            {
                "claim_id": item["claim_id"],
                "text": item["text"],
                "kind": item["kind"],
                "threads": set(),
                "artifact_filenames": set(),
                "reports": set(),
                "occurrences": [],
                "latest_date": None,
                "latest_artifact_title": None,
                "latest_artifact_href": None,
                "latest_artifact_filename": None,
                "latest_report": None,
            },
        )
        if item["kind"] == "gap":
            bucket["kind"] = "gap"
        bucket["threads"].update(item.get("threads") or [])
        bucket["artifact_filenames"].add(item["artifact_filename"])
        if item.get("report"):
            bucket["reports"].add(item["report"])
        bucket["occurrences"].append(item)
        dt = _parse_ts(item.get("date"))
        if dt and (bucket["latest_date"] is None or dt > _parse_ts(bucket["latest_date"])):
            bucket["latest_date"] = dt.isoformat()
            bucket["latest_artifact_title"] = item["artifact_title"]
            bucket["latest_artifact_href"] = item["artifact_href"]
            bucket["latest_artifact_filename"] = item["artifact_filename"]
            bucket["latest_report"] = item["report"]

    records: list[dict[str, Any]] = []
    for bucket in buckets.values():
        latest_dt = _parse_ts(bucket["latest_date"])
        stale_days = (today - latest_dt.date()).days if latest_dt else None
        stale = stale_days is not None and stale_days >= CLAIM_STALE_DAYS
        no_thread = len(bucket["threads"]) == 0
        support_count = len(bucket["artifact_filenames"])
        reports_count = len(bucket["reports"])
        records.append(
            {
                "claim_id": bucket["claim_id"],
                "text": bucket["text"],
                "kind": bucket["kind"],
                "threads": sorted(bucket["threads"]),
                "support_count": support_count,
                "reports_count": reports_count,
                "latest_date": bucket["latest_date"],
                "latest_artifact_title": bucket["latest_artifact_title"],
                "latest_artifact_href": bucket["latest_artifact_href"],
                "latest_artifact_filename": bucket["latest_artifact_filename"],
                "latest_report": bucket["latest_report"],
                "stale": stale,
                "stale_days": stale_days,
                "no_thread": no_thread,
                "occurrences": bucket["occurrences"],
            }
        )
    records.sort(key=lambda item: (item["latest_date"] or "", item["text"]), reverse=True)
    return records


def _event_resolution_counts() -> dict[str, int]:
    counts = {"resolved_7d": 0, "resolved_30d": 0}
    now = _now()
    resolution_types = {"ClaimAnswered", "ClaimSuperseded", "ClaimPromotedToThread"}
    for row in _read_jsonl(STATE_EVENTS_FILE):
        if row.get("type") not in resolution_types:
            continue
        dt = _parse_ts(row.get("ts"))
        if not dt:
            continue
        age = now - dt
        if age <= timedelta(days=30):
            counts["resolved_30d"] += 1
        if age <= timedelta(days=7):
            counts["resolved_7d"] += 1
    return counts


def build_claims_digest(entries_dir: Path = ENTRIES_DIR) -> dict[str, Any]:
    claims = _aggregate_claims(entries_dir)
    now = _now()
    resolution_counts = _event_resolution_counts()
    open_claims = [item for item in claims if item["kind"] == "gap"]
    verified_claims = [item for item in claims if item["kind"] != "gap"]
    attention = [item for item in claims if item["kind"] == "gap" or item["no_thread"] or item["stale"]]
    opened_7d = 0
    opened_30d = 0
    thread_counter: Counter[str] = Counter()
    oldest_open: list[dict[str, Any]] = []
    for item in open_claims:
        latest_dt = _parse_ts(item.get("latest_date"))
        if latest_dt:
            age = now - latest_dt
            if age <= timedelta(days=30):
                opened_30d += 1
            if age <= timedelta(days=7):
                opened_7d += 1
        for thread_id in item.get("threads") or []:
            thread_counter[thread_id] += 1
        oldest_open.append(
            {
                "claim_id": item["claim_id"],
                "text": item["text"],
                "date": item["latest_date"],
                "threads": item["threads"],
                "artifact": item["latest_artifact_filename"],
                "stale_days": item["stale_days"],
            }
        )
    oldest_open.sort(key=lambda item: item.get("date") or "")
    fanout_ratio = round(opened_30d / max(resolution_counts["resolved_30d"], 1), 2)
    return {
        "built_at": now.isoformat(),
        "version": 1,
        "open_total": len(open_claims),
        "verified_total": len(verified_claims),
        "attention_count": len(attention),
        "unthreaded_count": len([item for item in claims if item["no_thread"]]),
        "stale_count": len([item for item in claims if item["stale"]]),
        "opened_7d": opened_7d,
        "opened_30d": opened_30d,
        **resolution_counts,
        "fanout_ratio": fanout_ratio,
        "hot_threads_by_open_claims": [
            {"thread_id": thread_id, "open_claims": count}
            for thread_id, count in thread_counter.most_common(8)
        ],
        "oldest_open_claims": oldest_open[:10],
        "claims": claims,
    }


def _cluster_key(text: str) -> str:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9à-ÿ]+", text.lower())
        if len(token) > 2 and token not in _STOPWORDS
    ]
    if not tokens:
        return "misc"
    head = tokens[:3]
    return " ".join(head)


def build_orphan_claims(digest: dict[str, Any]) -> dict[str, Any]:
    claims = digest.get("claims") or []
    orphans = [item for item in claims if item.get("no_thread")]
    open_orphans = [item for item in orphans if item.get("kind") == "gap"]
    stale_orphans = [item for item in orphans if item.get("stale")]
    multi_support = [item for item in orphans if int(item.get("support_count", 0)) > 1]
    clusters: dict[str, dict[str, Any]] = {}
    for item in orphans:
        key = _cluster_key(str(item.get("text") or ""))
        bucket = clusters.setdefault(
            key,
            {"cluster_key": key, "items": [], "support_total": 0, "open_total": 0, "stale_total": 0},
        )
        bucket["items"].append(
            {
                "claim_id": item["claim_id"],
                "text": item["text"],
                "kind": item["kind"],
                "support_count": item["support_count"],
                "stale": item["stale"],
                "stale_days": item["stale_days"],
                "artifact": item["latest_artifact_filename"],
            }
        )
        bucket["support_total"] += int(item.get("support_count", 0))
        bucket["open_total"] += 1 if item.get("kind") == "gap" else 0
        bucket["stale_total"] += 1 if item.get("stale") else 0

    candidates = []
    for bucket in clusters.values():
        score = bucket["support_total"] + bucket["open_total"] * 2 + bucket["stale_total"]
        if len(bucket["items"]) > 1:
            score += 2
        if score < ORPHAN_CLUSTER_MIN_SCORE:
            continue
        candidates.append(
            {
                "cluster_key": bucket["cluster_key"],
                "score": score,
                "claim_count": len(bucket["items"]),
                "support_total": bucket["support_total"],
                "open_total": bucket["open_total"],
                "stale_total": bucket["stale_total"],
                "items": bucket["items"][:8],
                "rationale": (
                    "multi-artifact orphan cluster"
                    if bucket["support_total"] > len(bucket["items"])
                    else "single-surface orphan cluster"
                ),
            }
        )
    candidates.sort(key=lambda item: (item["score"], item["claim_count"]), reverse=True)
    return {
        "built_at": _now().isoformat(),
        "version": 1,
        "orphan_total": len(orphans),
        "open_orphan_total": len(open_orphans),
        "stale_orphan_total": len(stale_orphans),
        "multi_artifact_orphan_total": len(multi_support),
        "orphans": orphans,
        "candidate_clusters": candidates[:10],
    }


def _emit_claim_fact(
    event_type: str,
    *,
    claim_id: str,
    text: str,
    thread_id: str | None = None,
    artifact: str | None = None,
    payload: dict[str, Any] | None = None,
    cycle_id: str | None = None,
) -> None:
    body = {"claim_id": claim_id, "text": text}
    if thread_id:
        body["thread_id"] = thread_id
    if payload:
        body.update(payload)
    emit_shadow_event(
        event_type,
        actor=current_actor(),
        artifact=artifact,
        cycle_id=cycle_id or current_cycle_id(),
        payload=body,
    )


def emit_continuity_facts_for_entry(
    entry_path: Path,
    *,
    primary_thread_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    fm, body = _read_frontmatter(entry_path)
    threads = _normalize_string_list(fm.get("threads") or [])
    raw_claims = fm.get("claims") or []
    title = str(fm.get("title") or entry_path.stem)
    artifact = f"blog/entries/{entry_path.name}"
    claim_ids: list[str] = []

    emit_shadow_event(
        "ArtifactPublished",
        actor="continuity",
        artifact=artifact,
        cycle_id=cycle_id or current_cycle_id(),
        payload={
            "title": title,
            "thread_id": primary_thread_id or (threads[0] if threads else None),
            "threads": threads,
            "claims_count": len(raw_claims) if isinstance(raw_claims, list) else 0,
        },
    )

    touched = []
    for thread_id in dict.fromkeys(([primary_thread_id] if primary_thread_id else []) + threads):
        if not thread_id:
            continue
        touched.append(thread_id)
        emit_shadow_event(
            "ThreadTouched",
            actor="continuity",
            artifact=artifact,
            cycle_id=cycle_id or current_cycle_id(),
            payload={
                "thread_id": thread_id,
                "reason": "artifact_published",
                "title": title,
            },
        )

    if isinstance(raw_claims, list):
        for position, claim in enumerate(raw_claims):
            text = _claim_text(claim)
            if not text:
                continue
            claim_id = _claim_id(text)
            claim_ids.append(claim_id)
            kind = _claim_status(claim)
            _emit_claim_fact(
                "ClaimObserved",
                claim_id=claim_id,
                text=text,
                artifact=artifact,
                cycle_id=cycle_id,
                payload={
                    "kind": kind,
                    "threads": threads,
                    "position": position,
                    "title": title,
                    "body_preview": body.strip()[:280],
                },
            )
            for thread_id in threads:
                _emit_claim_fact(
                    "ClaimLinkedToThread",
                    claim_id=claim_id,
                    text=text,
                    thread_id=thread_id,
                    artifact=artifact,
                    cycle_id=cycle_id,
                    payload={"kind": kind, "title": title},
                )

    return {
        "threads": touched,
        "claim_ids": claim_ids,
        "claims_count": len(claim_ids),
    }


def _heuristic_validation_items(entry_path: Path, fm: dict[str, Any]) -> list[dict[str, Any]]:
    seen: Counter[str] = Counter()
    items: list[dict[str, Any]] = []
    for claim in fm.get("claims") or []:
        text = _claim_text(claim)
        if not text:
            continue
        cid = _claim_id(text)
        seen[cid] += 1
        status = "accepted"
        reason = "default heuristic acceptance"
        lowered = text.lower()
        if len(text) < 18:
            status = "uncertain"
            reason = "claim too short to be safely canonicalized"
        if any(token in lowered for token in ("todo", "fixme", "continue", "continuar", "resolver depois")):
            status = "rejected"
            reason = "looks like a task note rather than a claim"
        if seen[cid] > 1:
            status = "uncertain"
            reason = "duplicate claim inside same artifact"
        items.append({"claim_id": cid, "text": text, "status": status, "reason": reason})
    return items


def _llm_validate_claims(entry_path: Path, fm: dict[str, Any]) -> dict[str, Any] | None:
    claims = [_claim_text(item) for item in (fm.get("claims") or []) if _claim_text(item)]
    if not claims:
        return {
            "status": "accepted",
            "provider": "none",
            "model": "none",
            "items": [],
            "summary": "no claims declared",
        }

    title = str(fm.get("title") or entry_path.stem)
    threads = _normalize_string_list(fm.get("threads") or [])
    _fm, body = _read_frontmatter(entry_path)
    body_preview = body.strip()[:1800]
    prompt = {
        "title": title,
        "threads": threads,
        "claims": claims,
        "body_preview": body_preview,
        "task": (
            "Classify each claim as accepted, uncertain, or rejected for whether it is a "
            "good continuity fact extracted from this artifact. Reject TODOs, workflow notes, "
            "or vague non-claims. Return JSON with keys overall_status, summary, items. "
            "Each item must have claim, status, reason."
        ),
    }
    try:
        client, model = make_client("review", timeout=45, max_retries=0)
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You validate claim extraction quality for a continuity graph. "
                        "Return strict JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
        )
        text = resp.choices[0].message.content or ""
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        items = data.get("items")
        if not isinstance(items, list):
            return None
        normalized_items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            claim_text = str(item.get("claim") or "").strip()
            if not claim_text:
                continue
            normalized_items.append(
                {
                    "claim_id": _claim_id(claim_text),
                    "text": claim_text,
                    "status": str(item.get("status") or "uncertain").strip().lower(),
                    "reason": str(item.get("reason") or "").strip()[:280],
                }
            )
        if not normalized_items:
            return None
        return {
            "status": str(data.get("overall_status") or "uncertain").strip().lower(),
            "provider": "review",
            "model": model,
            "summary": str(data.get("summary") or "").strip(),
            "items": normalized_items,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "provider": "review",
            "model": "unavailable",
            "summary": str(exc)[:280],
            "items": [],
        }


def validate_claims_shadow(entry_path: Path) -> dict[str, Any]:
    fm, _body = _read_frontmatter(entry_path)
    heuristic_items = _heuristic_validation_items(entry_path, fm)
    llm_result = _llm_validate_claims(entry_path, fm)
    result = {
        "validated_at": _now().isoformat(),
        "artifact": f"blog/entries/{entry_path.name}",
        "slug": entry_path.stem,
        "title": str(fm.get("title") or entry_path.stem),
        "heuristic": {
            "status": "accepted" if all(item["status"] == "accepted" for item in heuristic_items) else "uncertain",
            "items": heuristic_items,
        },
        "judge": llm_result or {
            "status": "unavailable",
            "provider": "review",
            "model": "unknown",
            "summary": "llm result not parseable",
            "items": [],
        },
    }
    rows = []
    if CLAIMS_VALIDATION_FILE.exists():
        try:
            existing = json.loads(CLAIMS_VALIDATION_FILE.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                rows = existing.get("entries") or []
        except Exception:
            rows = []
    rows = [row for row in rows if row.get("slug") != entry_path.stem]
    rows.insert(0, result)
    payload = {
        "built_at": _now().isoformat(),
        "version": 1,
        "entries": rows[:50],
    }
    _write_json(CLAIMS_VALIDATION_FILE, payload)
    emit_shadow_event(
        "ClaimsValidationObserved",
        actor="continuity",
        artifact=f"blog/entries/{entry_path.name}",
        cycle_id=current_cycle_id(),
        payload={
            "slug": entry_path.stem,
            "judge_status": result["judge"]["status"],
            "heuristic_status": result["heuristic"]["status"],
        },
    )
    return result


def build_continuity_delta(entry_path: Path, digest: dict[str, Any], orphans: dict[str, Any]) -> dict[str, Any]:
    fm, _body = _read_frontmatter(entry_path)
    claims = fm.get("claims") or []
    threads = _normalize_string_list(fm.get("threads") or [])
    primary_thread = threads[0] if threads else None
    verified = [_claim_text(c) for c in claims if _claim_status(c) == "verified" and _claim_text(c)]
    gaps = [_claim_text(c) for c in claims if _claim_status(c) == "gap" and _claim_text(c)]
    orphan_claims = verified + gaps if not threads else []
    hot_threads = digest.get("hot_threads_by_open_claims") or []
    hot_thread = next((item for item in hot_threads if item.get("thread_id") == primary_thread), None)
    orphan_candidates = orphans.get("candidate_clusters") or []
    matching_cluster = None
    for cluster in orphan_candidates:
        cluster_ids = {item.get("claim_id") for item in cluster.get("items") or []}
        if cluster_ids.intersection({_claim_id(text) for text in orphan_claims}):
            matching_cluster = cluster
            break

    if primary_thread and gaps:
        paragraph = (
            f"Este artifact avança a thread `{primary_thread}` com {len(verified)} claim(s) verificadas "
            f"e {len(gaps)} gap(s) ainda em aberto. O efeito líquido é reforçar a continuidade sem fechar "
            "toda a frente pendente."
        )
    elif primary_thread:
        paragraph = (
            f"Este artifact avança a thread `{primary_thread}` e consolida {len(verified)} claim(s) "
            "sem abrir novos gaps explícitos."
        )
    elif matching_cluster:
        paragraph = (
            f"Este artifact ainda não está ligado a nenhuma thread existente. As claims órfãs aqui "
            f"formam um candidato de continuidade (`{matching_cluster.get('cluster_key')}`) com score "
            f"{matching_cluster.get('score')}."
        )
    else:
        paragraph = (
            "Este artifact ainda não está ligado a nenhuma thread existente. Ele aumenta o pool de claims "
            "órfãs e precisa de decisão de continuidade."
        )

    next_step = (
        f"Atacar os gaps remanescentes em `{primary_thread}`."
        if primary_thread and gaps
        else (
            f"Decidir se as claims órfãs devem promover uma nova thread ({matching_cluster.get('cluster_key')})."
            if matching_cluster
            else (
                f"Continuar aprofundando `{primary_thread}`."
                if primary_thread
                else "Associar o artifact a uma thread existente ou promover uma nova thread."
            )
        )
    )
    return {
        "built_at": _now().isoformat(),
        "slug": entry_path.stem,
        "primary_thread": primary_thread,
        "linked_threads": threads,
        "claims_total": len(claims),
        "claims_verified": len(verified),
        "claims_open": len(gaps),
        "orphan_claims": len(orphan_claims),
        "hot_thread_snapshot": hot_thread,
        "candidate_cluster": matching_cluster,
        "summary": paragraph,
        "next_step": next_step,
    }


def refresh_continuity_projections(entries_dir: Path = ENTRIES_DIR) -> dict[str, Any]:
    digest = build_claims_digest(entries_dir)
    orphans = build_orphan_claims(digest)
    _write_json(CLAIMS_DIGEST_FILE, digest)
    _write_json(ORPHAN_CLAIMS_FILE, orphans)
    return {"digest": digest, "orphans": orphans}


def process_publication_continuity(
    entry_path: Path,
    *,
    primary_thread_id: str | None = None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    facts = emit_continuity_facts_for_entry(entry_path, primary_thread_id=primary_thread_id, cycle_id=cycle_id)
    projections = refresh_continuity_projections()
    validation = validate_claims_shadow(entry_path)
    delta = build_continuity_delta(entry_path, projections["digest"], projections["orphans"])
    CONTINUITY_DELTAS_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(CONTINUITY_DELTAS_DIR / f"{entry_path.stem}.json", delta)
    return {
        "facts": facts,
        "digest": projections["digest"],
        "orphans": projections["orphans"],
        "validation": validation,
        "delta": delta,
    }
