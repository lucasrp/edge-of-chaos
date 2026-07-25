"""topic_threads - infer recent Voz topic threads into Direction proposals.

This is the automatic, non-curated leg: recent operator-authored turns are
grouped into coarse topic threads, then only decision-bearing threads become
`direction.proposed`. Grill/Voz still owns promotion to `set`.
"""
from __future__ import annotations

import dataclasses
import os
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import eventlog
import sessions


WINDOW_DAYS = 7
MAX_RELATES_TO = 8
MIN_FRAGMENTS = 2
MIN_SCORE = 2
SESSION_VOICE_TOPIC_ID = "session-voice"
SESSION_VOICE_TOPIC_TITLE = "Voz da sessao"

STOPWORDS = {
    "a", "ai", "ainda", "algo", "ao", "aos", "as", "ate", "bem", "cada", "com", "como",
    "da", "das", "de", "dele", "depois", "do", "dos", "e", "ela", "ele", "em", "entao",
    "era", "essa", "esse", "esta", "eu", "fazer", "foi", "isso", "ja", "la", "mais",
    "mas", "me", "mesmo", "na", "nao", "nas", "no", "nos", "o", "os", "ou", "para",
    "pela", "pelo", "por", "porque", "pra", "que", "se", "sem", "ser", "so", "sobre",
    "tambem", "tem", "ter", "todo", "um", "uma", "vc", "voce",
    "the", "and", "or", "of", "to", "in", "for", "with", "as", "is", "are", "was",
    "were", "be", "by", "from", "this", "that", "it", "we", "you",
    "command-message", "command-name", "command-args", "local-command-stdout",
    "local-command-caveat", "request-interrupted", "interrupted-user",
    "request", "interrupted", "user", "model", "local", "command",
}


TOPIC_SPECS: dict[str, dict[str, Any]] = {
    "edge-episteme-install": {
        "title": "Edge + Episteme",
        "terms": ["episteme", "merge", "genotipo", "fenotipo", "agent.yaml", "roberto",
                  "instalacao", "incorporou", "uma coisa so"],
        "steer": (
            "Manter Edge e Episteme como uma instalacao unica desde cedo: genotipo limpo, "
            "agent.yaml como fenotipo, e Roberto funcionando como fusao nativa."
        ),
    },
    "mentor-experiment": {
        "title": "Mentor + experiment",
        "terms": ["mentor", "grill", "mentorado", "experimento", "experiment", "arms",
                  "runs", "eval", "schema", "glossario"],
        "steer": (
            "Tratar experimentos como protocolo tecnico que nasce da interacao natural do mentor, "
            "com report obrigatorio no fechamento e artefatos navegaveis como evidencia."
        ),
    },
    "report-rite": {
        "title": "Reports, gates e storytelling",
        "terms": ["report", "relatorio", "gate", "gates", "grounding", "feynman",
                  "storytelling", "fan out", "juiz", "estrutura", "estrutural", "slots"],
        "steer": (
            "Reconstruir reports como artefatos ricos e escalaveis: plano estrutural antes do draft, "
            "grounding suficiente, gates em camadas, fan-out quando o tamanho exigir e storytelling "
            "avaliado como parte da qualidade."
        ),
    },
    "artifact-html-js": {
        "title": "Artefatos HTML/JS navegaveis",
        "terms": ["html", "javascript", "artefato", "artefatos", "netlify", "publish",
                  "publicar", "navegavel", "navegáveis", "editorial compass"],
        "steer": (
            "Fazer skills produtoras fecharem com artefatos humanos navegaveis, incluindo HTML e "
            "metadados suficientes para exploracao posterior."
        ),
    },
    "source-sufficiency": {
        "title": "Suficiencia de fontes",
        "terms": ["fontes", "sources", "internet", "internas", "externas", "exa", "hn",
                  "arxiv", "suficiencia", "justificar", "uso de fontes"],
        "steer": (
            "Avaliar fontes por suficiencia, nao checklist: separar fontes principais, justificar "
            "ausencias relevantes e transformar o julgamento em metadado de qualidade."
        ),
    },
    "session-memory-navigation": {
        "title": "Memoria de sessoes navegavel",
        "terms": ["recall", "sessao", "sessoes", "fragmentos", "fragments", "chunks",
                  "communities", "comunities", "busca semantica", "span", "500 semanas"],
        "steer": (
            "Construir memoria navegavel por Voz -> TopicChunk -> Topic -> Thread, preservando "
            "links para sessoes e permitindo busca semantica que entra em qualquer ponto."
        ),
    },
    "voice-indexing": {
        "title": "Voz e fragments",
        "terms": ["voz", "writing fragments", "pocock", "fragmentos meus", "claude chama",
                  "codex e vice versa", "meus textos", "curadoria", "indexar a voz"],
        "steer": (
            "Indexar Voz como texto autoral do mentorado, sem curadoria previa: fragments e topicos "
            "servem para busca e navegacao, nao para substituir a fala original."
        ),
    },
    "topic-thread-direction": {
        "title": "Topics -> Threads -> Direction",
        "terms": ["direction", "proposed", "estrategia", "strategy", "wake", "assemble",
                  "topic", "topics", "thread", "threads", "fio", "costura", "consolidando"],
        "steer": (
            "No wake, costurar topicos recentes em threads candidatas e emitir Direction.proposed "
            "como orientacao normal; o grill fica como curadoria para promover, dividir ou descartar."
        ),
    },
}


@dataclasses.dataclass(frozen=True)
class VoiceFragment:
    session_id: str
    surface: str
    path: str
    turn_index: int
    text: str


@dataclasses.dataclass(frozen=True)
class TopicDirection:
    id: str
    title: str
    body: str
    score: int
    fragment_count: int
    session_count: int
    relates_to: list[dict[str, Any]]


@dataclasses.dataclass(frozen=True)
class SessionTopic:
    session_id: str
    surface: str
    path: str
    topic_id: str
    title: str
    score: int
    keywords: list[str]
    fragments: list[dict[str, Any]]


def norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _session_id(surface: str, path: Path) -> str:
    if surface == "codex":
        return sessions.codex_session_anchor(sessions._codex_session_id(path))  # noqa: SLF001
    if surface == "grok":
        return sessions.grok_session_anchor(sessions._grok_session_id(path))  # noqa: SLF001
    return path.stem


def _exclude_anchor_set() -> set[str]:
    vals: set[str] = set()
    for key in ("CLAUDE_CODE_SESSION_ID", "CODEX_SESSION_ID", "CODEX_THREAD_ID"):
        val = os.environ.get(key)
        if isinstance(val, str) and val.strip():
            vals.add(val.strip())
            vals.add(sessions.codex_session_anchor(val.strip()))
    grok_sid = os.environ.get("GROK_SESSION_ID")
    if isinstance(grok_sid, str) and grok_sid.strip():
        vals.add(grok_sid.strip())
        vals.add(sessions.grok_session_anchor(grok_sid.strip()))
    extra = os.environ.get("EDGE_EXCLUDE_SESSION_IDS")
    if extra:
        vals.update(x.strip() for x in extra.split(",") if x.strip())
    return vals


def _iter_session_files(
    *,
    project_dir: str | Path | None = None,
    codex_dir: str | Path | bool | None = None,
    grok_dir: str | Path | bool | None = None,
    claude_root: str | Path | None = None,
    all_stores: bool | None = None,
) -> list[tuple[str, Path]]:
    if all_stores is None:
        all_stores = project_dir is None and os.environ.get("EDGE_TOPIC_DIRECTION_ALL_STORES", "1") != "0"
    found: list[tuple[str, Path]] = []
    if all_stores:
        root = Path(claude_root) if claude_root is not None else Path.home() / ".claude" / "projects"
        if root.is_dir():
            found.extend(("claude", p) for p in root.rglob("*.jsonl"))
    else:
        if project_dir is None:
            import _identity
            project_dir = _identity.project_dir()
        pdir = Path(project_dir)
        if pdir.is_dir():
            found.extend(("claude", p) for p in pdir.glob("*.jsonl"))
    import surfaces_cfg
    # all_stores=True ≡ real-host posture (honor agent.yaml); else hermetic unless explicit dir.
    gate = None if all_stores else project_dir
    if surfaces_cfg.include_optional_surface("codex", gate, codex_dir):
        found.extend(("codex", Path(s.path)) for s in sessions.list_codex_sessions(codex_dir))
    if surfaces_cfg.include_optional_surface("grok", gate, grok_dir):
        found.extend(("grok", Path(s.path)) for s in sessions.list_grok_sessions(grok_dir))
    return found


def collect_voice_fragments(
    *,
    window_days: int = WINDOW_DAYS,
    project_dir: str | Path | None = None,
    codex_dir: str | Path | bool | None = None,
    grok_dir: str | Path | bool | None = None,
    claude_root: str | Path | None = None,
    all_stores: bool | None = None,
    now: datetime | None = None,
) -> list[VoiceFragment]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    floor = cutoff.timestamp()
    exclude = _exclude_anchor_set()
    out: list[VoiceFragment] = []
    seen_paths: set[Path] = set()
    for surface, path in _iter_session_files(project_dir=project_dir, codex_dir=codex_dir,
                                             grok_dir=grok_dir, claude_root=claude_root,
                                             all_stores=all_stores):
        path = Path(path)
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            if path.stat().st_mtime < floor:
                continue
        except OSError:
            continue
        sid = _session_id(surface, path)
        raw_sid = sid.removeprefix("codex:").removeprefix("grok:")
        if sid in exclude or raw_sid in exclude:
            continue
        session = sessions.Session(id=raw_sid, path=path, surface=surface)
        if sessions.user_session_exclusion_reason(session):
            continue
        try:
            turns = sessions.read_turns(path, surface=surface)
        except Exception:
            continue
        for idx, turn in enumerate(turns, 1):
            if turn.role != "human":
                continue
            text = turn.text.strip()
            if text:
                out.append(VoiceFragment(sid, surface, str(path), idx, text))
    return out


def _topic_scores(text: str) -> Counter[str]:
    low = norm(text)
    scores: Counter[str] = Counter()
    for topic_id, spec in TOPIC_SPECS.items():
        for term in spec["terms"]:
            if norm(term) in low:
                scores[topic_id] += 1
    return scores


def _keywords(text: str, limit: int = 6) -> list[str]:
    tokens = []
    for token in re.findall(r"[A-Za-z0-9_.-]{3,}", norm(text)):
        if token not in STOPWORDS and not token.isdigit():
            tokens.append(token)
    counts = Counter(tokens)
    for a, b in zip(tokens, tokens[1:]):
        if a not in STOPWORDS and b not in STOPWORDS:
            counts[f"{a} {b}"] += 2
    return [k for k, _ in counts.most_common(limit)]


def _fragment_ref(fragment: VoiceFragment) -> dict[str, Any]:
    return {
        "kind": "voz.fragment",
        "session": fragment.session_id,
        "surface": fragment.surface,
        "path": fragment.path,
        "turn": fragment.turn_index,
        "snippet": re.sub(r"\s+", " ", fragment.text)[:240],
    }


def infer_session_topics(
    fragments: list[VoiceFragment],
    *,
    min_score: int = 1,
) -> list[SessionTopic]:
    """Group recent Voz fragments into per-session Topic records.

    This is indexing, not curation: one matched fragment may create a topic record so navigation can
    land on the exact session/turn. Direction promotion keeps its stricter aggregate thresholds.
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "score": 0,
        "fragments": [],
        "keywords": Counter(),
        "surface": None,
        "path": None,
    })
    for fragment in fragments:
        generic = grouped[(fragment.session_id, SESSION_VOICE_TOPIC_ID)]
        generic["score"] += 1
        generic["fragments"].append(fragment)
        generic["keywords"].update(_keywords(fragment.text))
        generic["surface"] = fragment.surface
        generic["path"] = fragment.path
        scores = _topic_scores(fragment.text)
        for topic_id, score in scores.items():
            row = grouped[(fragment.session_id, topic_id)]
            row["score"] += score
            row["fragments"].append(fragment)
            row["keywords"].update(_keywords(fragment.text))
            row["surface"] = fragment.surface
            row["path"] = fragment.path

    out: list[SessionTopic] = []
    for (session_id, topic_id), row in grouped.items():
        score = int(row["score"])
        if score < min_score:
            continue
        spec = TOPIC_SPECS.get(topic_id, {"title": SESSION_VOICE_TOPIC_TITLE})
        out.append(SessionTopic(
            session_id=session_id,
            surface=row["surface"] or "claude",
            path=row["path"] or "",
            topic_id=topic_id,
            title=spec["title"],
            score=score,
            keywords=[k for k, _ in row["keywords"].most_common(12)],
            fragments=[_fragment_ref(f) for f in row["fragments"][-MAX_RELATES_TO:]],
        ))
    out.sort(key=lambda t: (t.session_id, t.topic_id))
    return out


def index_session_topics(
    fragments: list[VoiceFragment],
    *,
    window_days: int = WINDOW_DAYS,
    min_score: int = 1,
    authoritative: bool = False,
    log=eventlog.LOG,
) -> int:
    existing = {}
    for e in eventlog.read(types=eventlog.SESSION_TOPIC_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        sid, tid, ch = p.get("session_id"), p.get("topic_id"), p.get("content_hash")
        if isinstance(sid, str) and isinstance(tid, str) and isinstance(ch, str):
            existing[(sid, tid)] = ch
    written = 0
    inferred = infer_session_topics(fragments, min_score=min_score)
    topics_by_session: dict[str, list[str]] = defaultdict(list)
    for topic in inferred:
        topics_by_session[topic.session_id].append(topic.topic_id)
        ev = eventlog.record_session_topic(
            topic.session_id,
            topic.topic_id,
            title=topic.title,
            surface=topic.surface,
            path=topic.path,
            score=topic.score,
            keywords=topic.keywords,
            fragments=topic.fragments,
            window_days=window_days,
            log=log,
        )
        p = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        key, ch = (topic.session_id, topic.topic_id), p.get("content_hash")
        if isinstance(ch, str) and existing.get(key) != ch:
            written += 1
            existing[key] = ch
    for session_id in sorted({fragment.session_id for fragment in fragments}):
        eventlog.record_session_topics_snapshot(
            session_id, topics_by_session.get(session_id, []),
            window_days=window_days, log=log)
    if authoritative:
        eventlog.record_session_topics_generation(
            sorted({fragment.session_id for fragment in fragments}),
            window_days=window_days, log=log)
    return written


def infer_topic_directions(
    fragments: list[VoiceFragment],
    *,
    window_days: int = WINDOW_DAYS,
    min_fragments: int = MIN_FRAGMENTS,
    min_score: int = MIN_SCORE,
    limit: int = 12,
) -> list[TopicDirection]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "score": 0,
        "fragments": [],
        "sessions": set(),
        "keywords": Counter(),
    })
    for fragment in fragments:
        scores = _topic_scores(fragment.text)
        if not scores:
            continue
        for topic_id, score in scores.items():
            row = grouped[topic_id]
            row["score"] += score
            row["fragments"].append(fragment)
            row["sessions"].add(fragment.session_id)
            row["keywords"].update(_keywords(fragment.text))
    directions: list[TopicDirection] = []
    for topic_id, row in grouped.items():
        fragments_for_topic: list[VoiceFragment] = row["fragments"]
        score = int(row["score"])
        if len(fragments_for_topic) < min_fragments or score < min_score:
            continue
        spec = TOPIC_SPECS[topic_id]
        evidence = fragments_for_topic[-MAX_RELATES_TO:]
        relates_to = [_fragment_ref(f) for f in evidence]
        session_count = len(row["sessions"])
        fragment_count = len(fragments_for_topic)
        body = (
            f"{spec['steer']} Evidencia: {fragment_count} fragmentos de Voz em "
            f"{session_count} sessao(oes) nos ultimos {window_days} dias; grill deve ratificar, "
            "dividir, promover para set ou descartar."
        )
        directions.append(TopicDirection(
            id=f"topic-7d:{topic_id}",
            title=spec["title"],
            body=body,
            score=score,
            fragment_count=fragment_count,
            session_count=session_count,
            relates_to=relates_to,
        ))
    directions.sort(key=lambda d: (d.session_count, d.fragment_count, d.score), reverse=True)
    return directions[:limit]


def index_recent_session_topics(
    *,
    window_days: int = WINDOW_DAYS,
    project_dir: str | Path | None = None,
    codex_dir: str | Path | bool | None = None,
    grok_dir: str | Path | bool | None = None,
    claude_root: str | Path | None = None,
    all_stores: bool | None = None,
    log=eventlog.LOG,
    now: datetime | None = None,
    min_score: int = 1,
) -> int:
    fragments = collect_voice_fragments(window_days=window_days, project_dir=project_dir,
                                        codex_dir=codex_dir, grok_dir=grok_dir,
                                        claude_root=claude_root,
                                        all_stores=all_stores, now=now)
    return index_session_topics(fragments, window_days=window_days, min_score=min_score, log=log)


def _direction_status(log=eventlog.LOG) -> dict[str, tuple[str, str]]:
    status: dict[str, tuple[str, str]] = {}
    for e in eventlog.read(types=eventlog.DIRECTION_TYPES, log=log):
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        iid = payload.get("id")
        if not isinstance(iid, str):
            continue
        typ = e.get("type")
        if typ == "direction.proposed":
            if status.get(iid, ("", ""))[0] != "set":
                status[iid] = ("proposed", payload.get("body", ""))
        elif typ == "direction.set":
            sup = payload.get("supersedes")
            if isinstance(sup, str) and sup != iid:
                status[sup] = ("set", "")
            status[iid] = ("set", payload.get("body", payload.get("plan", "")))
        elif typ == "direction.dropped":
            status[iid] = ("dropped", payload.get("reason", ""))
    return status


def propose_recent_topic_directions(
    *,
    window_days: int = WINDOW_DAYS,
    project_dir: str | Path | None = None,
    codex_dir: str | Path | bool | None = None,
    grok_dir: str | Path | bool | None = None,
    claude_root: str | Path | None = None,
    all_stores: bool | None = None,
    log=eventlog.LOG,
    now: datetime | None = None,
    min_fragments: int = MIN_FRAGMENTS,
    min_score: int = MIN_SCORE,
) -> int:
    fragments = collect_voice_fragments(window_days=window_days, project_dir=project_dir,
                                        codex_dir=codex_dir, grok_dir=grok_dir,
                                        claude_root=claude_root,
                                        all_stores=all_stores, now=now)
    directions = infer_topic_directions(fragments, window_days=window_days,
                                        min_fragments=min_fragments, min_score=min_score)
    status = _direction_status(log)
    written = 0
    for direction in directions:
        state, body = status.get(direction.id, ("", ""))
        if state in {"set", "dropped"}:
            continue
        if state == "proposed" and body == direction.body:
            continue
        eventlog.propose(direction.id, direction.body, kind="thread",
                         relates_to=direction.relates_to, log=log)
        status[direction.id] = ("proposed", direction.body)
        written += 1
    return written


def sync_recent_topic_memory(
    *,
    window_days: int = WINDOW_DAYS,
    project_dir: str | Path | None = None,
    codex_dir: str | Path | bool | None = None,
    grok_dir: str | Path | bool | None = None,
    claude_root: str | Path | None = None,
    all_stores: bool | None = None,
    log=eventlog.LOG,
    now: datetime | None = None,
    min_fragments: int = MIN_FRAGMENTS,
    min_score: int = MIN_SCORE,
    index_min_score: int = 1,
) -> dict[str, int]:
    """One wake-time pass for the automatic Voz memory layer.

    The same recent fragments feed two read models:
    - session.topic events, broad and navigable, preserving session/turn anchors;
    - direction.proposed events, narrower and decision-bearing, for the mentor to curate.
    """
    fragments = collect_voice_fragments(window_days=window_days, project_dir=project_dir,
                                        codex_dir=codex_dir, grok_dir=grok_dir,
                                        claude_root=claude_root,
                                        all_stores=all_stores, now=now)
    topics_written = index_session_topics(fragments, window_days=window_days,
                                          min_score=index_min_score,
                                          authoritative=(all_stores is True), log=log)
    directions = infer_topic_directions(fragments, window_days=window_days,
                                        min_fragments=min_fragments, min_score=min_score)
    status = _direction_status(log)
    directions_written = 0
    for direction in directions:
        state, body = status.get(direction.id, ("", ""))
        if state in {"set", "dropped"}:
            continue
        if state == "proposed" and body == direction.body:
            continue
        eventlog.propose(direction.id, direction.body, kind="thread",
                         relates_to=direction.relates_to, log=log)
        status[direction.id] = ("proposed", direction.body)
        directions_written += 1
    return {"topics": topics_written, "directions": directions_written,
            "total": topics_written + directions_written}
