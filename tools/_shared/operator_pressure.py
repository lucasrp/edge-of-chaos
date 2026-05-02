"""Operator pressure atom store + hot digest for recent Claude sessions.

This module maintains three layers:

1. Canonical atom snapshot in state/operator-pressure/ledger.json
2. Append-only atom ledger in state/operator-pressure/pressure-ledger.jsonl
3. Hot digest + periodic redigests derived from those atoms

The hot digest is optimized for current skill execution and is not meant for
retrieval indexing. The periodic redigest is the colder, segmentable layer.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent / "config"))
from paths import (  # noqa: E402
    OPERATOR_PRESSURE_ATOMS_FILE,
    OPERATOR_PRESSURE_HOT_DIGEST_FILE,
    OPERATOR_PRESSURE_LEDGER_FILE,
    OPERATOR_PRESSURE_PROJECTION_FILE,
    OPERATOR_PRESSURE_REDIGEST_DIR,
    PROJECTS_BASE,
    PROJECT_DIR,
)
from .router_client import make_client  # noqa: E402
from .telemetry import emit_shadow_event, log_event  # noqa: E402

SCHEMA_VERSION = 3
LEDGER_WINDOW_DAYS = int(os.environ.get("EDGE_OPERATOR_PRESSURE_WINDOW_DAYS", "7") or "7")
MAX_SESSIONS = int(os.environ.get("EDGE_OPERATOR_PRESSURE_MAX_SESSIONS", "8") or "8")
MAX_MESSAGES = int(os.environ.get("EDGE_OPERATOR_PRESSURE_MAX_MESSAGES", "48") or "48")
SECTION_LIMIT = int(os.environ.get("EDGE_OPERATOR_PRESSURE_SECTION_LIMIT", "4") or "4")
REDIGEST_INTERVAL_HOURS = int(os.environ.get("EDGE_OPERATOR_PRESSURE_REDIGEST_INTERVAL_HOURS", "24") or "24")
PROJECTION_MAX_AGE_MINUTES = int(os.environ.get("EDGE_OPERATOR_PRESSURE_PROJECTION_MAX_AGE_MINUTES", "30") or "30")
LLM_DISABLED = os.environ.get("EDGE_OPERATOR_PRESSURE_DISABLE_LLM", "").strip() in {"1", "true", "yes"}
LLM_MODEL = os.environ.get("EDGE_OPERATOR_PRESSURE_MODEL", "gpt-5.4").strip() or "gpt-5.4"

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_QUESTION_RE = re.compile(r"\?$|^(como|qual|quais|porque|por que|sera|será)\b", re.I)
_FAILURE_RE = re.compile(r"\b(falhou|falha|erro|timeout|degraded|quebrou|bug|problema)\b", re.I)
_CONTRADICTION_RE = re.compile(r"\b(na verdade|ali[aá]s|espera|opa|mas|s[oó] que)\b", re.I)
_DIRECTIVE_RE = re.compile(
    r"\b(tem que|deve|deveria|quero que|fa[cç]a|adicione|coloque|tire|remova|deixe|sempre|nunca|padroniza|padronizar|implemente|corrija|ajuste|abra uma issue|de merge)\b",
    re.I,
)
_CORRECTION_RE = re.compile(
    r"\b(n[aã]o [ée]|n[aã]o foi|n[aã]o era|de novo|errado|erro operacional|voc[eê] tem que|era para|n[aã]o devia)\b",
    re.I,
)
_TENTATIVE_RE = re.compile(r"\b(talvez|acho que|ser[aá] que|poderia|quem sabe)\b", re.I)
_RESOLUTION_RE = re.compile(r"\b(fechado|resolvido|pode seguir|segue isso|pode tocar)\b", re.I)
_OUTBURST_RE = re.compile(r"\b(merda|shit|porra|caralho|droga)\b", re.I)
_FRUSTRATED_RE = re.compile(r"\b(merda|shit|porra|caralho|de novo|sempre|deveria funcionar|nao aguento)\b", re.I)
_SARCASTIC_RE = re.compile(r"(^aham\b|/s\b|\".*\"\s*$)", re.I)
_GLOBAL_SCOPE_RE = re.compile(
    r"\b(sempre|nunca|todo beat|every beat|todas as skills|all skills|install|instal[a-z]*|runtime|sistema|system|workflow|policy|capability|primitive|primitiva|preflight|postflight|heartbeat)\b",
    re.I,
)
_STRONG_IMPERATIVE_RE = re.compile(r"\b(tem que|quero que|sempre|nunca|fa[cç]a|adicione|tire|remova|coloque|implemente|corrija|ajuste)\b", re.I)
_SUBSTRATE_GAP_RULES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(use|usa|usar)\b.{0,40}\b(key|chave|token|credential|credencial|api|integra[cç][aã]o|integration)\b",
            re.I,
        ),
        "ad_hoc_surface_use",
    ),
    (
        re.compile(
            r"\b(should already be available|devia j[aá] existir|isso deveria existir|isso deveria estar pronto|should come ready in the install|vir no install|existir no install)\b",
            re.I,
        ),
        "native_support_expectation",
    ),
    (
        re.compile(
            r"\b(i keep having to ask|keep having to ask|tenho que repetir|n[aã]o deveria ter que repetir|shouldn'?t need to repeat|toda vez eu tenho que|sempre preciso que)\b",
            re.I,
        ),
        "repeated_manual_request",
    ),
    (
        re.compile(
            r"\b(why can'?t you already see this|por que voc[eê] n[aã]o consegue ver|you should be able to inspect this directly|devia conseguir consultar isso direto)\b",
            re.I,
        ),
        "missing_native_observability",
    ),
]

_TARGET_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(workflow|routines?|preflight|postflight|protocolo)\b", re.I), "workflow"),
    (re.compile(r"\b(procedure|procedural|procedimento)\b", re.I), "procedure"),
    (re.compile(r"\b(capability|primitive|primitiva|repo\.sync|exa|grafana|github|meta|whatsapp)\b", re.I), "capability"),
    (re.compile(r"\b(policy|politica|policy|regra|guardrail)\b", re.I), "policy"),
    (re.compile(r"\b(skill|heartbeat|autonomy|reflection|report|research|strategy|map|discovery)\b", re.I), "skill"),
    (re.compile(r"\b(thread|topic|topics|claim|claims)\b", re.I), "thread"),
    (re.compile(r"\b(research|pesquisa|investigar|investiga[cç][aã]o|search)\b", re.I), "research"),
]

_ENTITY_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bmeta\b", re.I), "meta"),
    (re.compile(r"\bwhatsapp\b", re.I), "whatsapp"),
    (re.compile(r"\bgrafana\b", re.I), "grafana"),
    (re.compile(r"\bexa\b", re.I), "exa"),
    (re.compile(r"\bgithub\b", re.I), "github"),
    (re.compile(r"\bworkflow\b", re.I), "workflow"),
    (re.compile(r"\btopic[s]?\b", re.I), "topic"),
    (re.compile(r"\bmemory\b", re.I), "memory"),
    (re.compile(r"\bpreflight\b", re.I), "preflight"),
    (re.compile(r"\bpostflight\b", re.I), "postflight"),
    (re.compile(r"\bheartbeat\b", re.I), "heartbeat"),
    (re.compile(r"\breflection\b", re.I), "reflection"),
    (re.compile(r"\bautonomy\b", re.I), "autonomy"),
    (re.compile(r"\breport\b", re.I), "report"),
    (re.compile(r"\bresearch\b", re.I), "research"),
    (re.compile(r"\bstrategy\b", re.I), "strategy"),
    (re.compile(r"\bmap\b", re.I), "map"),
    (re.compile(r"\bclaude\b", re.I), "claude"),
    (re.compile(r"\bopenai\b", re.I), "openai"),
]

_ENTITY_TYPE_MAP = {
    "meta": "surface",
    "whatsapp": "surface",
    "grafana": "surface",
    "exa": "surface",
    "github": "surface",
    "claude": "system",
    "openai": "surface",
    "workflow": "workflow",
    "topic": "memory",
    "memory": "memory",
    "preflight": "protocol",
    "postflight": "protocol",
    "heartbeat": "skill",
    "reflection": "skill",
    "autonomy": "skill",
    "report": "skill",
    "research": "skill",
    "strategy": "skill",
    "map": "skill",
}

_HOT_DIGEST_KEYS = {
    "summary",
    "signal_from_operator_now",
    "operator_pains_resolvable_now",
    "operator_toil_optimizable_now",
    "mistakes_to_avoid_now",
    "implicit_needs_hypotheses",
    "workflow_candidates",
    "capability_candidates",
    "substrate_gap_requests",
    "active_entities",
    "item_ids",
}

_DIGEST_SECTION_KEYS = (
    "signal_from_operator_now",
    "operator_pains_resolvable_now",
    "operator_toil_optimizable_now",
    "mistakes_to_avoid_now",
    "implicit_needs_hypotheses",
    "workflow_candidates",
    "capability_candidates",
    "substrate_gap_requests",
)

_RUNTIME_PRESSURE_NOISE_RE = (
    re.compile(
        r"^\s*(?:-\s*\n\s*)?/[a-z0-9_.-]+\s*\n\s*\n"
        r"Dispatch runtime context below is authoritative for\b",
        re.I,
    ),
    re.compile(r"^\s*Base directory for this skill:\s+\S*\.claude/skills/", re.I),
    re.compile(r"^\s*## System\s*\n\s*You are a quality reviewer for report artifacts\b", re.I),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _jsonl_count(path: Path) -> int:
    try:
        return sum(1 for item in path.glob("*.jsonl") if item.is_file())
    except Exception:
        return 0


def _resolve_project_dir(project_dir: Path | None = None) -> Path:
    if project_dir is not None:
        return project_dir

    candidates = [PROJECT_DIR]
    name = PROJECT_DIR.name
    if name:
        alternate = PROJECTS_BASE / (name[1:] if name.startswith("-") else f"-{name}")
        if alternate not in candidates:
            candidates.append(alternate)

    existing = [candidate for candidate in candidates if candidate.exists()]
    with_sessions = [candidate for candidate in existing if _jsonl_count(candidate)]
    if with_sessions:
        return sorted(with_sessions, key=lambda item: _jsonl_count(item), reverse=True)[0]
    if existing:
        return existing[0]
    return PROJECT_DIR


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        value = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _extract_user_text(message: dict[str, Any]) -> str:
    content = message.get("message") or {}
    if isinstance(content, dict):
        raw = content.get("content")
        if isinstance(raw, list):
            parts: list[str] = []
            for item in raw:
                if isinstance(item, dict):
                    text = str(item.get("text") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(parts).strip()
        return str(raw or "").strip()
    return str(content or "").strip()


def _is_runtime_pressure_noise(text: str) -> bool:
    return any(pattern.search(text) for pattern in _RUNTIME_PRESSURE_NOISE_RE)


def _iter_recent_user_messages(
    *,
    project_dir: Path,
    window_days: int = LEDGER_WINDOW_DAYS,
    max_sessions: int = MAX_SESSIONS,
    max_messages: int = MAX_MESSAGES,
) -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(days=window_days)
    if not project_dir.exists():
        return []
    session_files = sorted(
        [path for path in project_dir.glob("*.jsonl") if path.is_file()],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )[:max_sessions]
    rows: list[dict[str, Any]] = []
    for path in session_files:
        try:
            handle = path.open(encoding="utf-8")
        except Exception:
            continue
        with handle:
            for idx, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if payload.get("type") != "user":
                    continue
                text = _extract_user_text(payload)
                if not text or len(text) < 8:
                    continue
                if _is_runtime_pressure_noise(text):
                    continue
                ts = _parse_ts(str(payload.get("timestamp") or ""))
                if ts and ts < cutoff:
                    continue
                rows.append(
                    {
                        "session_id": str(payload.get("sessionId") or path.stem),
                        "message_idx": idx,
                        "timestamp": (ts or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)).isoformat(),
                        "text": text,
                        "source_file": path.name,
                        "cwd": str(payload.get("cwd") or ""),
                    }
                )
    rows.sort(key=lambda item: (item["timestamp"], item["session_id"], item["message_idx"]))
    return rows[-max_messages:]


def _normalize_text(text: str) -> str:
    value = _WHITESPACE_RE.sub(" ", text.strip().lower())
    return value


def _fingerprint_text(text: str) -> str:
    value = _normalize_text(text)
    value = _PUNCT_RE.sub(" ", value)
    value = _WHITESPACE_RE.sub(" ", value).strip()
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _classify_kind(text: str) -> str:
    if _RESOLUTION_RE.search(text):
        return "resolution"
    if _OUTBURST_RE.search(text) and not (_DIRECTIVE_RE.search(text) or _CORRECTION_RE.search(text) or _QUESTION_RE.search(text)):
        return "outburst"
    if _FAILURE_RE.search(text):
        return "failure"
    if _CONTRADICTION_RE.search(text):
        return "contradiction"
    if _CORRECTION_RE.search(text):
        return "correction"
    if _QUESTION_RE.search(text):
        return "question"
    if _TENTATIVE_RE.search(text):
        return "tentative"
    if _DIRECTIVE_RE.search(text):
        return "directive"
    return "directive"


def _substrate_gap_reasons(text: str) -> list[str]:
    reasons: list[str] = []
    for pattern, reason in _SUBSTRATE_GAP_RULES:
        if pattern.search(text):
            reasons.append(reason)
    return sorted(set(reasons))


def _infer_target(text: str) -> str:
    for pattern, target in _TARGET_RULES:
        if pattern.search(text):
            return target
    if _substrate_gap_reasons(text):
        return "capability"
    return "policy"


def _extract_entity_names(text: str) -> list[str]:
    entities: list[str] = []
    for pattern, label in _ENTITY_RULES:
        if pattern.search(text):
            entities.append(label)
    return sorted(set(entities))


def _extract_entity_objects(text: str) -> list[dict[str, str]]:
    return [
        {
            "name": name,
            "type": _ENTITY_TYPE_MAP.get(name, "concept"),
        }
        for name in _extract_entity_names(text)
    ]


def _entity_names(raw_entities: Any) -> list[str]:
    names: list[str] = []
    if not isinstance(raw_entities, list):
        return names
    for item in raw_entities:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return sorted(set(names))


def _infer_emotion(text: str, kind: str) -> str:
    if _SARCASTIC_RE.search(text):
        return "sarcastic"
    if _TENTATIVE_RE.search(text) or kind in {"question", "tentative"}:
        return "uncertain"
    if _FRUSTRATED_RE.search(text):
        return "frustrated"
    if kind in {"directive", "correction", "contradiction"}:
        return "instructive"
    return "neutral"


def _infer_scope(text: str) -> str:
    return "global" if _GLOBAL_SCOPE_RE.search(text) else "local"


def _imperative_strength(text: str, kind: str, *, explicit_operator_direction: bool, repeat_count: int) -> str:
    if kind in {"directive", "correction", "contradiction"} and (_STRONG_IMPERATIVE_RE.search(text) or repeat_count >= 2):
        return "high"
    if explicit_operator_direction or kind in {"directive", "correction", "contradiction"}:
        return "medium"
    return "low"


def _salience_for_item(item: dict[str, Any]) -> float:
    score = 0.15
    score += min(int(item.get("repeat_count") or 0) * 0.12, 0.36)
    if item.get("explicit_operator_direction"):
        score += 0.20
    if str(item.get("kind") or "") in {"correction", "contradiction", "failure"}:
        score += 0.16
    if item.get("substrate_gap_signal"):
        score += 0.10
    if str(item.get("scope") or "") == "global":
        score += 0.08
    return round(min(score, 1.0), 3)


def _atom_hash(item: dict[str, Any]) -> str:
    payload = {
        "id": item.get("id"),
        "kind": item.get("kind"),
        "content": item.get("content"),
        "target": item.get("target"),
        "status": item.get("status"),
        "repeat_count": item.get("repeat_count"),
        "created_at": item.get("created_at"),
        "last_seen_at": item.get("last_seen_at"),
        "valid_from": item.get("valid_from"),
        "valid_until": item.get("valid_until"),
        "entities": item.get("entities"),
        "salience": item.get("salience"),
        "explicit_operator_direction": item.get("explicit_operator_direction"),
        "emotion": item.get("emotion"),
        "imperative_strength": item.get("imperative_strength"),
        "scope": item.get("scope"),
        "substrate_gap_signal": item.get("substrate_gap_signal"),
        "substrate_gap_reasons": item.get("substrate_gap_reasons"),
        "supersedes": item.get("supersedes"),
        "promoted_to": item.get("promoted_to"),
    }
    return _hash_payload(payload)


def _explicit_operator_direction(kind: str, text: str) -> bool:
    if kind not in {"directive", "correction", "contradiction"}:
        return False
    return bool(_DIRECTIVE_RE.search(text) or _CORRECTION_RE.search(text))


def _items_from_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for message in messages:
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        kind = _classify_kind(text)
        target = _infer_target(text)
        fingerprint = _fingerprint_text(text)
        item_id = f"pressure:{fingerprint}"
        item = grouped.get(item_id)
        if item is None:
            substrate_gap_reasons = _substrate_gap_reasons(text)
            explicit_direction = _explicit_operator_direction(kind, text)
            item = {
                "id": item_id,
                "kind": kind,
                "content": text[:600],
                "target": target,
                "status": "active",
                "repeat_count": 0,
                "created_at": message["timestamp"],
                "last_seen_at": message["timestamp"],
                "valid_from": message["timestamp"],
                "valid_until": "",
                "entities": _extract_entity_objects(text),
                "salience": 0.0,
                "explicit_operator_direction": explicit_direction,
                "emotion": _infer_emotion(text, kind),
                "imperative_strength": "low",
                "scope": _infer_scope(text),
                "substrate_gap_signal": bool(substrate_gap_reasons),
                "substrate_gap_reasons": substrate_gap_reasons,
                "provenance": [],
                "supersedes": [],
                "promoted_to": [],
            }
            grouped[item_id] = item
        item["repeat_count"] += 1
        item["last_seen_at"] = message["timestamp"]
        item["kind"] = kind if item["repeat_count"] == 1 else item["kind"]
        item["target"] = target if item["repeat_count"] == 1 else item["target"]
        provenance = item.setdefault("provenance", [])
        provenance.append(
            {
                "source_kind": "session",
                "source_id": message["session_id"],
                "message_range": [int(message["message_idx"]), int(message["message_idx"])],
                "timestamp": message["timestamp"],
                "source_file": message["source_file"],
                "cwd": message.get("cwd") or "",
            }
        )
        item["provenance"] = provenance[-5:]
        merged_entities = {entity["name"]: entity for entity in item.get("entities") or [] if isinstance(entity, dict)}
        for entity in _extract_entity_objects(text):
            merged_entities[entity["name"]] = entity
        item["entities"] = [merged_entities[name] for name in sorted(merged_entities)]
        merged_gap_reasons = set(item.get("substrate_gap_reasons") or [])
        merged_gap_reasons.update(_substrate_gap_reasons(text))
        item["substrate_gap_reasons"] = sorted(merged_gap_reasons)
        item["substrate_gap_signal"] = bool(item["substrate_gap_reasons"])
        item["imperative_strength"] = _imperative_strength(
            text,
            kind,
            explicit_operator_direction=bool(item.get("explicit_operator_direction")),
            repeat_count=int(item.get("repeat_count") or 0),
        )
    for item in grouped.values():
        item["salience"] = _salience_for_item(item)
        item["atom_hash"] = _atom_hash(item)
    items = list(grouped.values())
    items.sort(
        key=lambda item: (
            float(item.get("salience") or 0.0),
            -int(item.get("repeat_count") or 0),
            str(item.get("last_seen_at") or ""),
            str(item.get("id") or ""),
        ),
        reverse=True,
    )
    return items


def _ledger_from_messages(messages: list[dict[str, Any]], *, project_dir: Path) -> dict[str, Any]:
    items = _items_from_messages(messages)
    item_payload = [
        {
            "id": item["id"],
            "atom_id": item["id"],
            "atom_hash": item["atom_hash"],
            "kind": item["kind"],
            "content": item["content"],
            "target": item["target"],
            "status": item["status"],
            "repeat_count": item["repeat_count"],
            "created_at": item["created_at"],
            "last_seen_at": item["last_seen_at"],
            "valid_from": item["valid_from"],
            "valid_until": item["valid_until"],
            "entities": item["entities"],
            "salience": item["salience"],
            "explicit_operator_direction": item["explicit_operator_direction"],
            "emotion": item["emotion"],
            "imperative_strength": item["imperative_strength"],
            "scope": item["scope"],
            "substrate_gap_signal": item["substrate_gap_signal"],
            "substrate_gap_reasons": item["substrate_gap_reasons"],
            "provenance": item["provenance"],
            "supersedes": item["supersedes"],
            "promoted_to": item["promoted_to"],
        }
        for item in items
    ]
    source_hash = _hash_payload(item_payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "store_kind": "operator_pressure_atom_store",
        "generated_at": _now_iso(),
        "project_dir": str(project_dir),
        "window_days": LEDGER_WINDOW_DAYS,
        "message_total": len(messages),
        "session_total": len({row["session_id"] for row in messages}),
        "item_total": len(item_payload),
        "atom_total": len(item_payload),
        "source_hash": source_hash,
        "atoms": item_payload,
        "items": item_payload,
    }


def _rank_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[float, int, str, int]:
        return (
            float(item.get("salience") or 0.0),
            int(item.get("repeat_count") or 0),
            str(item.get("last_seen_at") or ""),
            1 if item.get("explicit_operator_direction") else 0,
        )
    return sorted(items, key=key, reverse=True)


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_id": item.get("id"),
        "text": str(item.get("content") or "")[:220],
        "target": item.get("target"),
        "kind": item.get("kind"),
        "repeat_count": int(item.get("repeat_count") or 0),
        "status": item.get("status"),
        "entities": _entity_names(item.get("entities") or []),
        "last_seen_at": item.get("last_seen_at"),
    }


def _hot_digest_matches_schema(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
        return False
    return all(key in payload for key in _HOT_DIGEST_KEYS)


def _deterministic_hot_digest(ledger: dict[str, Any], previous_digest: dict[str, Any] | None = None) -> dict[str, Any]:
    items = list(ledger.get("items") or [])
    ranked = _rank_items(items)
    directives = [item for item in ranked if item.get("explicit_operator_direction")]
    pains = [
        item
        for item in ranked
        if item.get("explicit_operator_direction") or str(item.get("kind") or "") in {"failure", "question", "tentative"}
    ]
    toil = [
        item
        for item in ranked
        if int(item.get("repeat_count") or 0) >= 2 and (item.get("explicit_operator_direction") or str(item.get("kind") or "") in {"correction", "contradiction"})
    ]
    mistakes = [
        item
        for item in ranked
        if str(item.get("kind") or "") in {"correction", "contradiction", "failure"}
    ]
    hypotheses = [
        item
        for item in ranked
        if str(item.get("kind") or "") in {"tentative", "question"}
    ]
    workflow_candidates = [
        item for item in directives if str(item.get("target") or "") in {"workflow", "procedure", "policy"}
    ]
    capability_candidates = [
        item for item in directives if str(item.get("target") or "") == "capability"
    ]
    substrate_gap_requests = [item for item in ranked if item.get("substrate_gap_signal")]
    entity_counts = Counter(entity for item in ranked for entity in _entity_names(item.get("entities") or []))
    top_entities = [name for name, _count in entity_counts.most_common(8)]
    summary_parts = []
    if directives:
        summary_parts.append(f"{len(directives)} active operator signals")
    if toil:
        summary_parts.append(f"{len(toil)} recurring operator toil patterns")
    if mistakes:
        summary_parts.append(f"{len(mistakes)} recent mistakes to avoid")
    if substrate_gap_requests:
        summary_parts.append(f"{len(substrate_gap_requests)} substrate gaps still requested by the operator")
    if not summary_parts:
        summary_parts.append("no strong recent operator pressure detected")
    digest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "source_hash": ledger.get("source_hash"),
        "render_mode": "deterministic",
        "model": "",
        "previous_digest_hash": str(previous_digest.get("digest_hash") or "") if isinstance(previous_digest, dict) else "",
        "summary": "; ".join(summary_parts),
        "signal_from_operator_now": [_compact_item(item) for item in directives[:SECTION_LIMIT]],
        "operator_pains_resolvable_now": [_compact_item(item) for item in pains[:SECTION_LIMIT]],
        "operator_toil_optimizable_now": [_compact_item(item) for item in toil[:SECTION_LIMIT]],
        "mistakes_to_avoid_now": [_compact_item(item) for item in mistakes[:SECTION_LIMIT]],
        "implicit_needs_hypotheses": [_compact_item(item) for item in hypotheses[:SECTION_LIMIT]],
        "workflow_candidates": [_compact_item(item) for item in workflow_candidates[:SECTION_LIMIT]],
        "capability_candidates": [_compact_item(item) for item in capability_candidates[:SECTION_LIMIT]],
        "substrate_gap_requests": [_compact_item(item) for item in substrate_gap_requests[:SECTION_LIMIT]],
        "active_entities": top_entities,
        "item_ids": [str(item.get("id") or "") for item in ranked[: max(SECTION_LIMIT * 4, 1)]],
    }
    digest["digest_hash"] = _hash_payload(
        {
            key: value
            for key, value in digest.items()
            if key not in {"generated_at", "digest_hash"}
        }
    )
    return digest


def _llm_prompt(
    render_input: dict[str, Any],
    *,
    previous_digest: dict[str, Any] | None,
    delta_items: list[dict[str, Any]],
) -> str:
    return (
        "You are rendering an operator-pressure digest for runtime preflight.\n"
        "Return JSON only. Do not add commentary.\n\n"
        "Goal:\n"
        "- compress recent operator pressure into a bounded operational digest\n"
        "- preserve explicit operator direction\n"
        "- surface repeated guidance and unresolved feedback\n"
        "- keep entries short and directly actionable\n\n"
        "Required JSON schema:\n"
        "{\n"
        '  "summary": "short paragraph",\n'
        '  "signal_from_operator_now": [{"item_id":"...","text":"...","target":"...","kind":"...","repeat_count":1,"status":"active","entities":["..."],"last_seen_at":"..."}],\n'
        '  "operator_pains_resolvable_now": [same shape],\n'
        '  "operator_toil_optimizable_now": [same shape],\n'
        '  "mistakes_to_avoid_now": [same shape],\n'
        '  "implicit_needs_hypotheses": [same shape],\n'
        '  "workflow_candidates": [same shape],\n'
        '  "capability_candidates": [same shape],\n'
        '  "substrate_gap_requests": [same shape],\n'
        '  "active_entities": ["..."]\n'
        "}\n\n"
        "Rules:\n"
        "- Keep lists bounded to the most important items already provided.\n"
        "- Do not invent workflow candidates unless they come from explicit operator direction.\n"
        "- Keep `text` concise but faithful.\n"
        "- Preserve item_id/target/kind/repeat_count/status/entities/last_seen_at from the inputs.\n"
        "- If a section has nothing useful, return an empty list.\n\n"
        f"Previous digest (if any):\n{json.dumps(previous_digest or {}, ensure_ascii=False, indent=2)}\n\n"
        f"Delta items since previous digest:\n{json.dumps(delta_items, ensure_ascii=False, indent=2)}\n\n"
        f"Render input:\n{json.dumps(render_input, ensure_ascii=False, indent=2)}\n"
    )


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        payload = json.loads(raw[start : end + 1])
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _coerce_digest_shape(candidate: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    digest = dict(fallback)
    digest["summary"] = str(candidate.get("summary") or fallback.get("summary") or "").strip()
    for key in _DIGEST_SECTION_KEYS:
        items = candidate.get(key)
        if isinstance(items, list):
            normalized: list[dict[str, Any]] = []
            for item in items[:SECTION_LIMIT]:
                if not isinstance(item, dict):
                    continue
                normalized.append(
                    {
                        "item_id": str(item.get("item_id") or ""),
                        "text": str(item.get("text") or "")[:220],
                        "target": str(item.get("target") or ""),
                        "kind": str(item.get("kind") or ""),
                        "repeat_count": int(item.get("repeat_count") or 0),
                        "status": str(item.get("status") or "active"),
                        "entities": [str(entity) for entity in (item.get("entities") or []) if str(entity).strip()],
                        "last_seen_at": str(item.get("last_seen_at") or ""),
                    }
                )
            digest[key] = normalized
    entities = candidate.get("active_entities")
    if isinstance(entities, list):
        digest["active_entities"] = [str(entity) for entity in entities[:8] if str(entity).strip()]
    return digest


def _render_input_has_pressure(render_input: dict[str, Any]) -> bool:
    for key in _DIGEST_SECTION_KEYS:
        if render_input.get(key):
            return True
    return bool(render_input.get("active_entities"))


def _render_hot_digest_with_llm(
    ledger: dict[str, Any],
    *,
    previous_digest: dict[str, Any] | None,
    delta_items: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback = _deterministic_hot_digest(ledger, previous_digest=previous_digest)
    if LLM_DISABLED:
        return fallback
    render_input = {
        "source_hash": ledger.get("source_hash"),
        "item_total": ledger.get("item_total", 0),
        "session_total": ledger.get("session_total", 0),
        "signal_from_operator_now": fallback.get("signal_from_operator_now", []),
        "operator_pains_resolvable_now": fallback.get("operator_pains_resolvable_now", []),
        "operator_toil_optimizable_now": fallback.get("operator_toil_optimizable_now", []),
        "mistakes_to_avoid_now": fallback.get("mistakes_to_avoid_now", []),
        "implicit_needs_hypotheses": fallback.get("implicit_needs_hypotheses", []),
        "workflow_candidates": fallback.get("workflow_candidates", []),
        "capability_candidates": fallback.get("capability_candidates", []),
        "substrate_gap_requests": fallback.get("substrate_gap_requests", []),
        "active_entities": fallback.get("active_entities", []),
    }
    if int(ledger.get("item_total") or 0) == 0 and not _render_input_has_pressure(render_input):
        return fallback
    prompt = _llm_prompt(render_input, previous_digest=previous_digest, delta_items=delta_items[:SECTION_LIMIT])
    try:
        client, model = make_client("chat", model=LLM_MODEL, timeout=90)
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You compress operator pressure into compact structured JSON for runtime use."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        payload = _extract_json_object(str(content or ""))
        if not payload:
            raise RuntimeError("digest renderer did not return JSON")
        digest = _coerce_digest_shape(payload, fallback)
        digest["render_mode"] = "gpt-5"
        digest["model"] = model
        digest["generated_at"] = _now_iso()
        digest["source_hash"] = ledger.get("source_hash")
        digest["previous_digest_hash"] = str(previous_digest.get("digest_hash") or "") if isinstance(previous_digest, dict) else ""
        digest["item_ids"] = fallback.get("item_ids", [])
        digest["digest_hash"] = _hash_payload(
            {
                key: value
                for key, value in digest.items()
                if key not in {"generated_at", "digest_hash"}
            }
        )
        return digest
    except Exception as exc:
        fallback["render_mode"] = "deterministic"
        fallback["render_warning"] = str(exc)
        return fallback


def _existing_atom_index(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    index: dict[str, dict[str, Any]] = {}
    try:
        handle = path.open(encoding="utf-8")
    except Exception:
        return {}
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            atom_id = str(payload.get("atom_id") or "").strip()
            if not atom_id:
                continue
            index[atom_id] = {
                "atom_hash": str(payload.get("atom_hash") or ""),
                "revision": int(payload.get("revision") or 0),
            }
    return index


def _append_atom_store(ledger: dict[str, Any], *, atoms_path: Path) -> dict[str, Any]:
    atoms_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_atom_index(atoms_path)
    appended = 0
    with atoms_path.open("a", encoding="utf-8") as handle:
        for item in ledger.get("items") or []:
            if not isinstance(item, dict):
                continue
            atom_id = str(item.get("id") or "").strip()
            if not atom_id:
                continue
            atom_hash = str(item.get("atom_hash") or _atom_hash(item))
            previous = existing.get(atom_id) or {}
            if previous.get("atom_hash") == atom_hash:
                continue
            entry = {
                "schema_version": SCHEMA_VERSION,
                "entry_type": "atom",
                "recorded_at": _now_iso(),
                "atom_id": atom_id,
                "atom_hash": atom_hash,
                "revision": int(previous.get("revision") or 0) + 1,
                "kind": item.get("kind"),
                "content": item.get("content"),
                "target": item.get("target"),
                "status": item.get("status"),
                "repeat_count": int(item.get("repeat_count") or 0),
                "created_at": item.get("created_at"),
                "last_seen_at": item.get("last_seen_at"),
                "valid_from": item.get("valid_from") or item.get("created_at"),
                "valid_until": item.get("valid_until") or "",
                "entities": item.get("entities") or [],
                "salience": float(item.get("salience") or 0.0),
                "explicit_operator_direction": bool(item.get("explicit_operator_direction")),
                "emotion": item.get("emotion"),
                "imperative_strength": item.get("imperative_strength"),
                "scope": item.get("scope"),
                "substrate_gap_signal": bool(item.get("substrate_gap_signal")),
                "substrate_gap_reasons": list(item.get("substrate_gap_reasons") or []),
                "provenance": item.get("provenance") or [],
                "supersedes": item.get("supersedes") or [],
                "promoted_to": item.get("promoted_to") or [],
            }
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            appended += 1
    return {
        "path": str(atoms_path),
        "appended": appended,
        "atom_total": int(ledger.get("atom_total") or ledger.get("item_total") or 0),
    }


def _build_redigest(ledger: dict[str, Any], hot_digest: dict[str, Any], previous_latest: dict[str, Any] | None = None) -> dict[str, Any]:
    items = list(ledger.get("items") or [])
    by_target = Counter(str(item.get("target") or "policy") for item in items)
    by_kind = Counter(str(item.get("kind") or "directive") for item in items)
    by_status = Counter(str(item.get("status") or "active") for item in items)
    derived_sections: dict[str, list[str]] = {}
    for section in (
        "signal_from_operator_now",
        "operator_pains_resolvable_now",
        "operator_toil_optimizable_now",
        "mistakes_to_avoid_now",
        "implicit_needs_hypotheses",
        "workflow_candidates",
        "capability_candidates",
        "substrate_gap_requests",
    ):
        for item in hot_digest.get(section) or []:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("item_id") or "").strip()
            if not item_id:
                continue
            derived_sections.setdefault(item_id, []).append(section)
    segments: list[dict[str, Any]] = []
    for item in _rank_items(items):
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        segments.append(
            {
                "segment_id": f"pressure-segment:{item_id}",
                "segment_type": "operator_pressure_atom",
                "derived_from_atom_ids": [item_id],
                "derived_sections": derived_sections.get(item_id, []),
                "text": str(item.get("content") or "")[:220],
                "target": str(item.get("target") or ""),
                "kind": str(item.get("kind") or ""),
                "status": str(item.get("status") or "active"),
                "repeat_count": int(item.get("repeat_count") or 0),
                "salience": float(item.get("salience") or 0.0),
                "explicit_operator_direction": bool(item.get("explicit_operator_direction")),
                "emotion": str(item.get("emotion") or ""),
                "imperative_strength": str(item.get("imperative_strength") or ""),
                "scope": str(item.get("scope") or ""),
                "entities": _entity_names(item.get("entities") or []),
                "entity_refs": list(item.get("entities") or []),
                "valid_from": str(item.get("valid_from") or item.get("created_at") or ""),
                "valid_until": str(item.get("valid_until") or ""),
                "last_seen_at": str(item.get("last_seen_at") or ""),
                "substrate_gap_signal": bool(item.get("substrate_gap_signal")),
                "substrate_gap_reasons": list(item.get("substrate_gap_reasons") or []),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "source_hash": ledger.get("source_hash"),
        "item_total": ledger.get("item_total", 0),
        "atom_total": ledger.get("atom_total", 0),
        "summary": hot_digest.get("summary", ""),
        "segments": segments,
        "counts": {
            "by_target": dict(sorted(by_target.items())),
            "by_kind": dict(sorted(by_kind.items())),
            "by_status": dict(sorted(by_status.items())),
        },
        "active_entities": hot_digest.get("active_entities", []),
        "previous_snapshot_hash": str(previous_latest.get("snapshot_hash") or "") if isinstance(previous_latest, dict) else "",
    }
    payload["snapshot_hash"] = _hash_payload(
        {
            key: value
            for key, value in payload.items()
            if key not in {"generated_at", "snapshot_hash"}
        }
    )
    return payload


def _maybe_write_redigest(ledger: dict[str, Any], hot_digest: dict[str, Any], *, redigest_dir: Path) -> dict[str, Any]:
    latest_path = redigest_dir / "latest.json"
    latest = _read_json(latest_path)
    if latest:
        previous_ts = _parse_ts(str(latest.get("generated_at") or ""))
        if previous_ts and (_now() - previous_ts) < timedelta(hours=REDIGEST_INTERVAL_HOURS):
            return latest
    snapshot = _build_redigest(ledger, hot_digest, previous_latest=latest)
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = redigest_dir / f"{stamp}.json"
    _write_json(snapshot_path, snapshot)
    _write_json(latest_path, snapshot)
    emit_shadow_event(
        "OperatorPressureRedigestUpdated",
        actor="operator-pressure",
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        payload={
            "snapshot_path": str(snapshot_path),
            "item_total": snapshot.get("item_total", 0),
            "segment_total": len(snapshot.get("segments") or []),
            "source_hash": snapshot.get("source_hash"),
        },
    )
    log_event(
        "operator_pressure_redigest",
        actor="operator-pressure",
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        snapshot_path=str(snapshot_path),
        item_total=snapshot.get("item_total", 0),
        segment_total=len(snapshot.get("segments") or []),
        source_hash=snapshot.get("source_hash"),
        status="updated",
    )
    return snapshot


def _projection_summary(
    ledger: dict[str, Any],
    hot_digest: dict[str, Any],
    redigest: dict[str, Any],
    *,
    project_dir: Path,
    ledger_path: Path,
    atoms_path: Path,
    hot_digest_path: Path,
    redigest_dir: Path,
    atom_store: dict[str, Any],
    latest_before: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "project_dir": str(project_dir),
        "message_total": ledger.get("message_total", 0),
        "session_total": ledger.get("session_total", 0),
        "item_total": ledger.get("item_total", 0),
        "active_entities": hot_digest.get("active_entities", []),
        "signal_from_operator_now": len(hot_digest.get("signal_from_operator_now") or []),
        "operator_pains_resolvable_now": len(hot_digest.get("operator_pains_resolvable_now") or []),
        "operator_toil_optimizable_now": len(hot_digest.get("operator_toil_optimizable_now") or []),
        "mistakes_to_avoid_now": len(hot_digest.get("mistakes_to_avoid_now") or []),
        "implicit_needs_hypotheses": len(hot_digest.get("implicit_needs_hypotheses") or []),
        "workflow_candidates": len(hot_digest.get("workflow_candidates") or []),
        "capability_candidates": len(hot_digest.get("capability_candidates") or []),
        "substrate_gap_requests": len(hot_digest.get("substrate_gap_requests") or []),
        "render_mode": hot_digest.get("render_mode", "deterministic"),
        "source_hash": ledger.get("source_hash"),
        "ledger_path": str(ledger_path),
        "atoms_path": atom_store["path"],
        "atom_entries_appended": atom_store["appended"],
        "hot_digest_path": str(hot_digest_path),
        "redigest_path": str(redigest_dir / "latest.json"),
        "redigest_updated": (not latest_before) or latest_before.get("snapshot_hash") != redigest.get("snapshot_hash"),
    }


def build_operator_pressure_layers(
    *,
    project_dir: Path | None = None,
    ledger_path: Path | None = None,
    hot_digest_path: Path | None = None,
    redigest_dir: Path | None = None,
    atoms_path: Path | None = None,
    write: bool = True,
    emit_events: bool = True,
    allow_llm: bool = True,
) -> dict[str, Any]:
    project_dir = _resolve_project_dir(project_dir)
    explicit_ledger_path = ledger_path
    ledger_path = ledger_path or OPERATOR_PRESSURE_LEDGER_FILE
    hot_digest_path = hot_digest_path or OPERATOR_PRESSURE_HOT_DIGEST_FILE
    redigest_dir = redigest_dir or OPERATOR_PRESSURE_REDIGEST_DIR
    atoms_path = atoms_path or ((explicit_ledger_path.parent / "pressure-ledger.jsonl") if explicit_ledger_path else OPERATOR_PRESSURE_ATOMS_FILE)

    messages = _iter_recent_user_messages(project_dir=project_dir)
    ledger = _ledger_from_messages(messages, project_dir=project_dir)
    previous_digest = _read_json(hot_digest_path)
    if _hot_digest_matches_schema(previous_digest) and previous_digest.get("source_hash") == ledger.get("source_hash"):
        hot_digest = previous_digest
    else:
        previous_item_ids = set(previous_digest.get("item_ids") or []) if isinstance(previous_digest, dict) else set()
        delta_items = [
            _compact_item(item)
            for item in (ledger.get("items") or [])
            if str(item.get("id") or "") not in previous_item_ids
        ]
        hot_digest = (
            _render_hot_digest_with_llm(ledger, previous_digest=previous_digest, delta_items=delta_items)
            if allow_llm
            else _deterministic_hot_digest(ledger, previous_digest=previous_digest)
        )

    latest_before = _read_json((redigest_dir / "latest.json"))
    if write:
        _write_json(ledger_path, ledger)
        _write_json(hot_digest_path, hot_digest)
        atom_store = _append_atom_store(ledger, atoms_path=atoms_path)
        redigest = _maybe_write_redigest(ledger, hot_digest, redigest_dir=redigest_dir)
    else:
        atom_store = {
            "path": str(atoms_path),
            "appended": 0,
            "atom_total": int(ledger.get("atom_total") or ledger.get("item_total") or 0),
        }
        if latest_before and latest_before.get("source_hash") == ledger.get("source_hash"):
            redigest = latest_before
        else:
            redigest = _build_redigest(ledger, hot_digest, previous_latest=latest_before)

    summary = _projection_summary(
        ledger,
        hot_digest,
        redigest,
        project_dir=project_dir,
        ledger_path=ledger_path,
        atoms_path=atoms_path,
        hot_digest_path=hot_digest_path,
        redigest_dir=redigest_dir,
        atom_store=atom_store,
        latest_before=latest_before,
    )
    if emit_events:
        emit_shadow_event(
            "ClaudeSessionDigestComputed",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            payload=summary,
        )
        log_event(
            "operator_pressure_digest",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            status="computed",
            item_total=summary["item_total"],
            session_total=summary["session_total"],
            render_mode=summary["render_mode"],
            signal_from_operator_now=summary["signal_from_operator_now"],
            operator_toil_optimizable_now=summary["operator_toil_optimizable_now"],
            workflow_candidates=summary["workflow_candidates"],
            capability_candidates=summary["capability_candidates"],
            substrate_gap_requests=summary["substrate_gap_requests"],
            mistakes_to_avoid_now=summary["mistakes_to_avoid_now"],
            atom_entries_appended=summary["atom_entries_appended"],
        )
    return {
        "ledger": ledger,
        "hot_digest": hot_digest,
        "redigest": redigest,
        "summary": summary,
    }


def _projection_age_minutes(payload: dict[str, Any] | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    generated = _parse_ts(str(payload.get("generated_at") or ""))
    if generated is None:
        return None
    return (_now() - generated).total_seconds() / 60


def operator_pressure_projection_is_stale(
    payload: dict[str, Any] | None,
    *,
    max_age_minutes: int = PROJECTION_MAX_AGE_MINUTES,
) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("projection_kind") != "operator_pressure":
        return True
    if payload.get("status") != "ok":
        return True
    age = _projection_age_minutes(payload)
    return age is None or age > max_age_minutes


def _raw_chat_from_ledger(ledger: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": bool(ledger.get("items") or ledger.get("atoms")),
        "message_total": int(ledger.get("message_total") or summary.get("message_total") or 0),
        "session_total": int(ledger.get("session_total") or summary.get("session_total") or 0),
        "item_total": int(ledger.get("item_total") or summary.get("item_total") or 0),
        "window_days": ledger.get("window_days"),
        "project_dir": ledger.get("project_dir") or summary.get("project_dir"),
    }


def build_operator_pressure_projection(
    *,
    project_dir: Path | None = None,
    projection_path: Path | None = None,
    write_layers: bool = True,
    emit_events: bool = False,
    allow_llm: bool = True,
) -> dict[str, Any]:
    projection_path = projection_path or OPERATOR_PRESSURE_PROJECTION_FILE
    layers = build_operator_pressure_layers(
        project_dir=project_dir,
        write=write_layers,
        emit_events=False,
        allow_llm=allow_llm,
    )
    ledger = layers["ledger"]
    summary = dict(layers["summary"])
    hot_digest = layers["hot_digest"]
    redigest = layers["redigest"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "projection_kind": "operator_pressure",
        "status": "ok",
        "generated_at": summary.get("generated_at") or _now_iso(),
        "output_path": str(projection_path),
        "source": {
            "project_dir": summary.get("project_dir"),
            "source_hash": summary.get("source_hash"),
            "window_days": ledger.get("window_days"),
        },
        "summary": summary,
        "ledger": ledger,
        "hot_digest": hot_digest,
        "redigest": redigest,
        "raw_chat": _raw_chat_from_ledger(ledger, summary),
        "source_paths": {
            "ledger": summary.get("ledger_path"),
            "atoms": summary.get("atoms_path"),
            "hot_digest": summary.get("hot_digest_path"),
            "redigest": summary.get("redigest_path"),
            "projection": str(projection_path),
        },
    }
    if emit_events:
        emit_shadow_event(
            "OperatorPressureProjectionBuilt",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            payload={
                "projection_path": str(projection_path),
                "item_total": summary.get("item_total", 0),
                "source_hash": summary.get("source_hash"),
                "write_layers": write_layers,
            },
        )
    return payload


def write_operator_pressure_projection(
    *,
    project_dir: Path | None = None,
    projection_path: Path | None = None,
    allow_llm: bool = True,
) -> dict[str, Any]:
    projection_path = projection_path or OPERATOR_PRESSURE_PROJECTION_FILE
    try:
        payload = build_operator_pressure_projection(
            project_dir=project_dir,
            projection_path=projection_path,
            write_layers=True,
            emit_events=False,
            allow_llm=allow_llm,
        )
        _write_json(projection_path, payload)
        summary = payload.get("summary") or {}
        emit_shadow_event(
            "ClaudeSessionDigestComputed",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            payload={
                **summary,
                "projection_path": str(projection_path),
                "projection_kind": "operator_pressure",
            },
        )
        log_event(
            "operator_pressure_projection",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            status="computed",
            projection_path=str(projection_path),
            item_total=summary.get("item_total", 0),
            session_total=summary.get("session_total", 0),
            render_mode=summary.get("render_mode"),
            source_hash=summary.get("source_hash"),
        )
        return payload
    except Exception as exc:
        failed = {
            "schema_version": SCHEMA_VERSION,
            "projection_kind": "operator_pressure",
            "status": "failed",
            "generated_at": _now_iso(),
            "output_path": str(projection_path),
            "error": str(exc),
            "summary": {
                "schema_version": SCHEMA_VERSION,
                "generated_at": _now_iso(),
                "message_total": 0,
                "session_total": 0,
                "item_total": 0,
                "render_mode": "failed",
            },
            "ledger": {"items": [], "atoms": []},
            "hot_digest": _deterministic_hot_digest({"items": [], "source_hash": ""}),
            "redigest": {},
            "raw_chat": {"available": False, "message_total": 0, "session_total": 0, "item_total": 0},
            "source_paths": {"projection": str(projection_path)},
        }
        _write_json(projection_path, failed)
        emit_shadow_event(
            "ClaudeSessionDigestFailed",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            payload={"projection_path": str(projection_path), "error": str(exc)},
        )
        log_event(
            "operator_pressure_projection",
            actor="operator-pressure",
            cycle_id=os.environ.get("EDGE_CYCLE_ID"),
            status="failed",
            projection_path=str(projection_path),
            error=str(exc),
        )
        return failed


def read_operator_pressure_projection(projection_path: Path | None = None) -> dict[str, Any] | None:
    return _read_json(projection_path or OPERATOR_PRESSURE_PROJECTION_FILE)


def read_or_refresh_operator_pressure_projection(
    *,
    projection_path: Path | None = None,
    max_age_minutes: int = PROJECTION_MAX_AGE_MINUTES,
) -> dict[str, Any]:
    projection_path = projection_path or OPERATOR_PRESSURE_PROJECTION_FILE
    current = read_operator_pressure_projection(projection_path)
    if not operator_pressure_projection_is_stale(current, max_age_minutes=max_age_minutes):
        current = dict(current or {})
        current["projection_status"] = "fresh"
        return current

    age = _projection_age_minutes(current)
    emit_shadow_event(
        "ClaudeSessionDigestStale",
        actor="operator-pressure",
        cycle_id=os.environ.get("EDGE_CYCLE_ID"),
        payload={
            "projection_path": str(projection_path),
            "age_minutes": age,
            "max_age_minutes": max_age_minutes,
            "reason": "missing" if current is None else "stale_or_invalid",
        },
    )
    refreshed = write_operator_pressure_projection(projection_path=projection_path)
    refreshed["projection_status"] = "refreshed"
    return refreshed


__all__ = [
    "build_operator_pressure_layers",
    "build_operator_pressure_projection",
    "operator_pressure_projection_is_stale",
    "read_operator_pressure_projection",
    "read_or_refresh_operator_pressure_projection",
    "write_operator_pressure_projection",
]
