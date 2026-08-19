"""Bounded a-posteriori rationalization of persisted work sessions.

The sole public interface keeps cognition, input identity, validation and the atomic
event-log checkpoint local.  The injected completer is the only model seam; this module
imports neither a provider client nor Graphiti.
"""

import hashlib
import json
import math
import re
import unicodedata

import eventlog


DEFAULT_VERSION = "racionalizador-v3-session-provenance"
_OPERATION_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NUMBERED_REF_RE = re.compile(r"^(?:atv|run|arc|map|tkt|fat)-\d+$")
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$", re.IGNORECASE)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)


class _AlreadyRationalized(Exception):
    pass


class _BudgetExhausted(Exception):
    pass


_DERIVED_TYPES = {
    "atividade.opened", "atividade.touched", "claim.hypothesized", "move.proposed"
}

# Completer is a free-form text endpoint (claude -p / codex). Without an explicit shape it
# answers the question in prose; rationalize needs JSON. Hints ride in the request payload
# as a short instruction (keep small — session prompts already carry the turns).
_SCENE_JSON_INSTRUCTION = (
    'Return ONLY JSON: {"summary":"<one short paragraph>"}. Preserve who did what: '
    "the human's purpose/decision and the edge's execution are distinct. The input turn_index "
    "is evidence identity; do not renumber turns. No markdown/prose."
)
_SESSION_JSON_INSTRUCTION = (
    "Return ONLY a JSON object (no markdown fences). Schema:\n"
    '{"operacoes":["edge"],'
    '"stitch":{"attribution":{"human_purpose":"why the human is doing this",'
    '"human_turn_indexes":[0],"edge_execution":"what the AI/edge did",'
    '"shared_outcome":"what changed for the human purpose",'
    '"activity_relevant":true},"entidades":[]},'
    '"epistemico":{"presuncoes":[]},'
    '"organizacional":{"enderecos":[]},'
    '"derived_events":[{"type":"atividade.opened","subject":"atividade:auto",'
    '"payload":{"operacao":"edge","finalidade":"the work purpose","novo":"what changed"}}]}\n'
    "Rules: operacoes = short lowercase slugs ^[a-z0-9][a-z0-9-]*$ (e.g. edge), never "
    "descriptions. Attribution is semantic, never keyword-based: human_purpose states WHY the "
    "human initiated or continued the work, at the granularity their own turns support; "
    "human_turn_indexes cites those original human turns; edge_execution records what the AI "
    "implemented/reviewed/explained and NEVER replaces human_purpose; shared_outcome says what "
    "that execution changed for the human purpose. Set activity_relevant=false ONLY when the "
    "scene neither advances a durable human purpose NOR opens/continues a new front connected "
    "to one of the request's `open_threads` (the currently-open Atividades). Frequency is NOT "
    "the discriminator: a one-off front (a new dataset, download, pipeline, sub-goal) that "
    "connects to an open thread is activity_relevant=true and inherits that thread's salience "
    "even at its first appearance — reuse that thread's operacao. Discard only the one-off that "
    "is ALSO disconnected from every open thread. "
    "A technical purpose is valid when the human "
    "actually reasons about that technical trade-off; delegation alone does not transfer the "
    "edge's implementation vocabulary to the human. Epistemic presumptions and derived claims "
    "must likewise bear on human_purpose; edge-only implementation details may support them but "
    "must not become standalone concerns."
)

def _has_activity_derived(derived_events):
    return any(
        item.get("type") in ("atividade.opened", "atividade.touched")
        for item in derived_events
    )


def _nonblank(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-blank string")
    return value.strip()


def _normalized_turns(turns):
    """Accept only human|edge dialogue prose (Claude / Codex / Grok pre-filter output).

    Callers must pass ``sessions.dialogue_turns`` / ``mentee_dialogue_for_rationalize`` —
    not raw JSONL. Roles other than human/edge are dropped (defense in depth).
    """
    normalized = []
    for index, turn in enumerate(turns):
        if isinstance(turn, dict):
            role, text = turn.get("role"), turn.get("text")
        else:
            role, text = getattr(turn, "role", None), getattr(turn, "text", None)
        if not isinstance(role, str) or not role.strip():
            continue
        role = role.strip().lower()
        if role in ("user", "assistant"):
            role = "human" if role == "user" else "edge"
        if role not in ("human", "edge"):
            continue
        if not isinstance(text, str):
            raise ValueError(f"turns[{index}].text must be a string")
        text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n")).strip()
        if not text:
            continue
        normalized.append({"turn_index": index, "role": role, "text": text})
    if not normalized:
        raise ValueError("turns must contain at least one dialogue turn")
    if not any(t["role"] == "human" for t in normalized):
        raise ValueError("turns must include at least one human (mentee/operator) turn")
    return normalized


def _digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _full_ref(value, field, operations, *, allow_ulid=False):
    if allow_ulid and isinstance(value, str) and _ULID_RE.fullmatch(value.strip()):
        return value.strip().upper()
    if isinstance(value, str):
        parts = value.strip().split("/")
        if len(parts) != 2 or not _OPERATION_RE.fullmatch(parts[0]) \
                or not _NUMBERED_REF_RE.fullmatch(parts[1]):
            raise ValueError(
                f"{field} must be a full <operacao>/<prefix-NNN> ref"
                + (" or ULID" if allow_ulid else "")
            )
        operation, number = parts
        normalized = value.strip()
    elif isinstance(value, dict):
        operation = value.get("operacao")
        number = value.get("num")
        if not isinstance(operation, str) or not _OPERATION_RE.fullmatch(operation):
            raise ValueError(f"{field}.operacao must match {_OPERATION_RE.pattern}")
        if not isinstance(number, str) or not _NUMBERED_REF_RE.fullmatch(number):
            raise ValueError(f"{field}.num must be a numbered grain ref")
        normalized = {"operacao": operation, "num": number}
    else:
        raise ValueError(
            f"{field} must be a full <operacao>/<prefix-NNN> ref"
            + (" or ULID" if allow_ulid else "")
        )
    if operation not in operations:
        raise ValueError(f"{field}.operacao {operation!r} is absent from operacoes")
    return normalized


def _loads_json_loose(raw):
    """Parse model JSON tolerating fences and leading/trailing prose.

    1. dict → return as-is
    2. str → strip, try json.loads
    3. else extract first ```json fence block, then first object via JSONDecoder.raw_decode
    4. else raise ValueError

    Gate P2: stdlib raw_decode replaces a hand-rolled brace scanner.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        raise ValueError(f"expected JSON object or string, got {type(raw).__name__}")
    text = raw.strip()
    if not text:
        raise ValueError("empty JSON input")
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip(), strict=False)
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start >= 0:
        try:
            obj, _end = json.JSONDecoder().raw_decode(text, start)
            return obj
        except json.JSONDecodeError:
            pass
    raise ValueError("could not parse JSON object from completer output")


def _validated_attribution(stitch, turns=None):
    attribution = stitch.get("attribution")
    if not isinstance(attribution, dict):
        raise ValueError("stitch.attribution must be an object")
    human_purpose = _nonblank(
        attribution.get("human_purpose"), "stitch.attribution.human_purpose")
    edge_execution = _nonblank(
        attribution.get("edge_execution"), "stitch.attribution.edge_execution")
    shared_outcome = _nonblank(
        attribution.get("shared_outcome"), "stitch.attribution.shared_outcome")
    indexes = attribution.get("human_turn_indexes")
    if (not isinstance(indexes, list) or not indexes
            or any(not isinstance(index, int) or isinstance(index, bool) or index < 0
                   for index in indexes)):
        raise ValueError(
            "stitch.attribution.human_turn_indexes must be non-empty non-negative integers")
    indexes = list(dict.fromkeys(indexes))
    if turns is not None:
        human_indexes = {
            turn["turn_index"] for turn in turns
            if isinstance(turn, dict) and turn.get("role") == "human"
        }
        missing = [index for index in indexes if index not in human_indexes]
        if missing:
            raise ValueError(
                "stitch.attribution.human_turn_indexes must cite human turns: "
                + ", ".join(map(str, missing)))
    activity_relevant = attribution.get("activity_relevant")
    if not isinstance(activity_relevant, bool):
        raise ValueError("stitch.attribution.activity_relevant must be boolean")
    return {
        "human_purpose": human_purpose,
        "human_turn_indexes": indexes,
        "edge_execution": edge_execution,
        "shared_outcome": shared_outcome,
        "activity_relevant": activity_relevant,
    }


def _validated_output(raw, turns=None):
    try:
        output = _loads_json_loose(raw)
    except ValueError as exc:
        raise ValueError(f"completer output is not valid JSON: {exc}") from exc
    if not isinstance(output, dict):
        raise ValueError("completer output must be a JSON object")

    operations = output.get("operacoes")
    if (not isinstance(operations, list) or not operations
            or not all(isinstance(item, str) and item.strip() for item in operations)):
        raise ValueError("operacoes must be a non-empty list of non-blank strings")
    normalized_operations = []
    for index, operation in enumerate(operations):
        operation = operation.strip()
        if not _OPERATION_RE.fullmatch(operation):
            raise ValueError(f"operacoes[{index}] must match {_OPERATION_RE.pattern}")
        if operation not in normalized_operations:
            normalized_operations.append(operation)
    stitch = output.get("stitch")
    if not isinstance(stitch, dict):
        raise ValueError("stitch must be an object")
    attribution = _validated_attribution(stitch, turns=turns)
    goal = attribution["human_purpose"]
    action = attribution["shared_outcome"]
    entities = stitch.get("entidades")
    # Completer sometimes omits entidades or returns a non-list — coerce to [] (same as empty).
    if entities is None:
        entities = []
    if not isinstance(entities, list):
        entities = []
    # Drop malformed refs instead of invalid_output on the whole film (drain 7d: completer
    # often invents free-text entities). Empty entidades remains valid.
    normalized_entities = []
    for index, entity in enumerate(entities):
        try:
            normalized_entities.append(
                _full_ref(entity, f"stitch.entidades[{index}]", normalized_operations)
            )
        except ValueError:
            continue

    epistemic = output.get("epistemico")
    if not isinstance(epistemic, dict) or not isinstance(epistemic.get("presuncoes"), list):
        raise ValueError("epistemico.presuncoes must be a list")
    presumptions = []
    for index, presumption in enumerate(epistemic["presuncoes"]):
        if not isinstance(presumption, dict):
            raise ValueError(f"epistemico.presuncoes[{index}] must be an object")
        normalized = {
            field: _nonblank(
                presumption.get(field), f"epistemico.presuncoes[{index}].{field}"
            )
            for field in ("texto", "confirmaria", "refutaria")
        }
        if "depende_de" in presumption:
            normalized["depende_de"] = _nonblank(
                presumption["depende_de"],
                f"epistemico.presuncoes[{index}].depende_de",
            )
        presumptions.append(normalized)
    organizational = output.get("organizacional")
    if not isinstance(organizational, dict) or not isinstance(
        organizational.get("enderecos"), list
    ):
        raise ValueError("organizacional.enderecos must be a list")
    addresses = []
    for index, address in enumerate(organizational["enderecos"]):
        if not isinstance(address, dict):
            raise ValueError(f"organizacional.enderecos[{index}] must be an object")
        prefix = f"organizacional.enderecos[{index}]"
        activity = _full_ref(
            address.get("atividade"), f"{prefix}.atividade", normalized_operations,
            allow_ulid=True,
        )
        normalized_address = {
            "atividade": activity,
            "path": _nonblank(address.get("path"), f"{prefix}.path"),
            "papel": _nonblank(address.get("papel"), f"{prefix}.papel"),
        }
        if "sha256" in address:
            sha = address.get("sha256")
            if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
                raise ValueError(f"{prefix}.sha256 must be 64 hexadecimal characters")
            normalized_address["sha256"] = sha.lower()
        if "stat" in address:
            stat = address.get("stat")
            if not isinstance(stat, dict) or not stat or not all(
                isinstance(key, str) and key.strip() for key in stat
            ):
                raise ValueError(f"{prefix}.stat must be a non-empty object with named fields")
            normalized_address["stat"] = stat
        addresses.append(normalized_address)
    derived = output.get("derived_events", [])
    if not isinstance(derived, list):
        raise ValueError("derived_events must be a list")
    normalized_derived = []
    for index, derived_event in enumerate(derived):
        if not isinstance(derived_event, dict):
            raise ValueError(f"derived_events[{index}] must be an object")
        event_type = _nonblank(derived_event.get("type"), f"derived_events[{index}].type")
        if event_type in {"atividade.closed", "atividade.reopened"}:
            raise ValueError(
                f"derived_events[{index}].type must use move.proposed for activity "
                "closure/reopening"
            )
        subject = _nonblank(derived_event.get("subject"), f"derived_events[{index}].subject")
        payload = derived_event.get("payload")
        if not isinstance(payload, dict):
            raise ValueError(f"derived_events[{index}].payload must be an object")
        normalized_derived.append({"type": event_type, "subject": subject, "payload": payload})

    # Role attribution owns the activity surface. The model may still emit a detailed
    # implementation payload, but that detail belongs to edge_execution, never to the
    # portfolio's purpose. No vocabulary/occupation filter participates in this decision.
    attributed_derived = []
    for item in normalized_derived:
        if item.get("type") in ("atividade.opened", "atividade.touched"):
            if not attribution["activity_relevant"]:
                continue
            payload = dict(item["payload"])
            if item["type"] == "atividade.opened":
                payload["finalidade"] = goal
            payload["novo"] = action
            item = {**item, "payload": payload}
        attributed_derived.append(item)
    normalized_derived = attributed_derived

    if attribution["activity_relevant"] and not _has_activity_derived(normalized_derived):
        normalized_derived.append({
            "type": "atividade.opened",
            "subject": "atividade:auto",
            "payload": {
                "operacao": normalized_operations[0],
                "finalidade": goal,
                "novo": action,
            },
        })

    return {
        "operacoes": normalized_operations,
        "stitch": {"goal": goal, "acao": action, "entidades": normalized_entities,
                   "attribution": attribution},
        "epistemico": {"presuncoes": presumptions},
        "organizacional": {"enderecos": addresses},
        "derived_events": normalized_derived,
    }


def _rationalizations(log, session_id=None):
    rows = []
    for event in eventlog.read(types=["sessao.racionalizada"], log=log):
        if not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        if session_id is None or payload.get("sessao_id") == session_id:
            rows.append(event)
    return rows


def _uniform_scenes(turns, scene_turn_limit, max_scenes):
    scenes = [turns[start:start + scene_turn_limit]
              for start in range(0, len(turns), scene_turn_limit)]
    if len(scenes) <= max_scenes:
        return scenes
    # Half-up (not Python's bankers-rounding) makes the unique sampled middle of an even
    # scene count the scene containing the session's central turn.
    indexes = [math.floor(index * (len(scenes) - 1) / (max_scenes - 1) + 0.5)
               for index in range(max_scenes)]
    return [scenes[index] for index in indexes]


def _estimated_tokens(prompt):
    return max(1, math.ceil(len(prompt.encode("utf-8")) / 4))


def _derivation_key(source_hash, kind, ordinal):
    return hashlib.sha256(f"{source_hash}{kind}{ordinal}".encode("utf-8")).hexdigest()


def _existing_session_activities(session_id, operation, log):
    folded = eventlog.atividades_at(log=log)
    candidates = []
    for event in eventlog.read(types=["atividade.opened"], log=log):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (payload.get("operacao") != operation
                or payload.get("origem_sessao") != session_id
                or not isinstance(payload.get("ulid"), str)):
            continue
        item = next((item for item in folded.values() if item["ulid"] == payload["ulid"]), None)
        pinned = item is not None and any(
            row.get("tier") == "asserted"
            for field in ("toques", "fechos", "bears_on")
            for row in item.get(field, [])
            if isinstance(row, dict)
        )
        if (item is not None and item["estado"] in ("aberta", "reaberta") and pinned):
            candidates.append((event.get("seq", 0), item, payload))
    return [candidate for _seq, candidate, _payload in sorted(candidates)]


def _normalized_files(files, field):
    if files is None:
        return []
    if not isinstance(files, list) or not all(isinstance(path, str) and path.strip()
                                               for path in files):
        raise ValueError(f"{field} must be a list of non-blank paths")
    return [path.strip() for path in files]


def _normalized_spans(spans, session_id, field):
    if spans is None:
        return []
    if not isinstance(spans, list):
        raise ValueError(f"{field} must be a list")
    normalized = []
    for index, span in enumerate(spans):
        if not isinstance(span, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        start, end = span.get("ini"), span.get("fim")
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, int) or not isinstance(end, int)
                or start < 0 or end < start):
            raise ValueError(f"{field}[{index}] needs integer 0 <= ini <= fim")
        normalized.append({"sessao": _nonblank(span.get("sessao", session_id),
                                                f"{field}[{index}].sessao"),
                           "ini": start, "fim": end})
    return normalized


def _move_payload(raw, events, ordinal):
    kind = _nonblank(raw.get("kind"), f"derived_events[{ordinal}].payload.kind")
    if kind not in eventlog._MOVE_EFFECT_TYPES:
        raise ValueError(f"derived_events[{ordinal}].payload.kind is unknown: {kind!r}")
    alvo = raw.get("alvo")
    if alvo is None and kind == "ticket.open" and isinstance(raw.get("effect"), dict):
        effect_payload = raw["effect"].get("payload")
        alvo = effect_payload.get("map") if isinstance(effect_payload, dict) else None
    target = eventlog._move_target(kind, alvo, events, None)
    effect = eventlog._validated_move_effect(kind, raw.get("effect"), target, events)
    expects = raw.get("expects")
    if not isinstance(expects, dict):
        raise ValueError(f"derived_events[{ordinal}].payload.expects must be an object")
    evidence = raw.get("evidencia")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError(f"derived_events[{ordinal}].payload.evidencia must be non-empty")
    evidence_ulids = sorted({
        eventlog._resolve_lens_ref(ref, events, operacao=target.get("operacao"),
                                   kinds={"atividade", "run", "fato"})["ulid"]
        for ref in evidence
    })
    basis_seq = raw.get("basis_seq")
    if not isinstance(basis_seq, int) or isinstance(basis_seq, bool) or basis_seq < 0:
        raise ValueError(f"derived_events[{ordinal}].payload.basis_seq must be >= 0")
    rationale = _nonblank(raw.get("rationale"),
                          f"derived_events[{ordinal}].payload.rationale")
    key_material = {"kind": kind, "alvo": target["ulid"], "effect": effect,
                    "evidencia": evidence_ulids}
    move_key = _digest(key_material)
    ulid = eventlog._ulid()
    return {"ulid": ulid, "kind": kind, "alvo": target["ulid"], "effect": effect,
            "expects": dict(expects), "evidencia": evidence_ulids,
            "rationale": rationale, "basis_seq": basis_seq,
            "move_key": move_key, "author": "edge"}


def _build_derived_batch(output, session_id, source_hash, rationalization_id, log):
    """Validate every derived intention in memory; returned tuples are safe for one append_batch."""
    events = eventlog.read(log=log)
    batch = []
    pending_activity_opens = []
    touched = set()
    existing_by_operation = {}
    open_ordinals = {}

    for index, derived in enumerate(output["derived_events"]):
        event_type = derived["type"]
        if event_type not in _DERIVED_TYPES:
            raise ValueError(
                f"derived_events[{index}].type {event_type!r} is not an allowed derived event")
        raw = derived["payload"]
        if event_type == "atividade.opened":
            operation = _nonblank(raw.get("operacao"),
                                  f"derived_events[{index}].payload.operacao")
            if operation not in output["operacoes"]:
                raise ValueError(
                    f"derived_events[{index}].payload.operacao is absent from operacoes")
            purpose = _nonblank(raw.get("finalidade"),
                                f"derived_events[{index}].payload.finalidade")
            evaluation = raw.get("eval")
            if evaluation is not None:
                if not isinstance(evaluation, dict):
                    raise ValueError(f"derived_events[{index}].payload.eval must be an object")
                evaluation = dict(evaluation)
                evaluation["regua"] = _nonblank(
                    evaluation.get("regua"), f"derived_events[{index}].payload.eval.regua")
            type_ref = raw.get("tipo_ref")
            if type_ref is not None:
                type_ref = _nonblank(type_ref, f"derived_events[{index}].payload.tipo_ref")
                if not eventlog._TIPO_REF_RE.fullmatch(type_ref):
                    raise ValueError(f"derived_events[{index}].payload.tipo_ref is invalid")
            arc = raw.get("arco")
            if arc is not None:
                arc = eventlog._resolve_lens_ref(
                    arc, events, operacao=operation, kinds={"arco"})["ulid"]
            ordinal = open_ordinals.get(operation, 0)
            open_ordinals[operation] = ordinal + 1
            existing = existing_by_operation.setdefault(
                operation, _existing_session_activities(session_id, operation, log))
            item = existing[ordinal] if ordinal < len(existing) else None
            key = _derivation_key(source_hash, "atividade", ordinal)
            if item is None:
                ulid = eventlog._ulid()
                payload = {"ulid": ulid, "num": None, "operacao": operation,
                           "finalidade": purpose, "eval": evaluation, "arco": arc,
                           "tipo_ref": type_ref, "tier": "llm_judged",
                           "author": "racionalizador", "origem_sessao": session_id,
                           "derivation_key": key, "rationalization_id": rationalization_id}
                pending_activity_opens.append(payload)
                batch.append(("atividade.opened", f"atividade:{ulid}", payload))
                activity_ulid = ulid
            else:
                activity_ulid = item["ulid"]
            touch_key = (session_id, activity_ulid)
            if touch_key not in touched:
                touch = {"ref": activity_ulid, "sessao": session_id,
                         "novo": (_nonblank(raw.get("novo"),
                                             f"derived_events[{index}].payload.novo")
                                  if raw.get("novo") is not None else purpose),
                         "files": _normalized_files(
                             raw.get("files"), f"derived_events[{index}].payload.files"),
                         "spans": _normalized_spans(
                             raw.get("spans"), session_id,
                             f"derived_events[{index}].payload.spans"),
                         "tier": "llm_judged", "rationalization_id": rationalization_id,
                         "derivation_key": key}
                batch.append(("atividade.touched", f"atividade:{activity_ulid}", touch))
                touched.add(touch_key)
        elif event_type == "atividade.touched":
            target = eventlog._resolve_lens_ref(
                raw.get("ref"), events, kinds={"atividade"})
            touch_key = (session_id, target["ulid"])
            if touch_key in touched:
                raise ValueError(f"derived_events[{index}] duplicates a session×activity touch")
            touch = {"ref": target["ulid"], "sessao": session_id,
                     "novo": (_nonblank(raw.get("novo"),
                                         f"derived_events[{index}].payload.novo")
                              if raw.get("novo") is not None else None),
                     "files": _normalized_files(
                         raw.get("files"), f"derived_events[{index}].payload.files"),
                     "spans": _normalized_spans(
                         raw.get("spans"), session_id,
                         f"derived_events[{index}].payload.spans"),
                     "tier": "llm_judged", "rationalization_id": rationalization_id,
                     "derivation_key": _derivation_key(source_hash, "touch", index)}
            batch.append((event_type, f"atividade:{target['ulid']}", touch))
            touched.add(touch_key)
        elif event_type == "claim.hypothesized":
            statement = _nonblank(raw.get("statement"),
                                  f"derived_events[{index}].payload.statement")
            falsifier = raw.get("falsifier")
            if falsifier is not None:
                falsifier = eventlog._validated_falsifier(falsifier)
            key = _derivation_key(source_hash, "claim", index)
            ulid = eventlog._ulid()
            payload = {"ulid": ulid, "statement": statement, "falsifier": falsifier,
                       "origem_sessao": session_id, "derivation_key": key,
                       "tier": "llm_judged", "rationalization_id": rationalization_id}
            if not eventlog._foldable_hypothesized_claim(payload):
                raise ValueError(f"derived_events[{index}] failed claim.hypothesized validation")
            batch.append((event_type, f"claim:{ulid}", payload))
        elif event_type == "move.proposed":
            payload = _move_payload(raw, events, index)
            payload["rationalization_id"] = rationalization_id
            batch.append((event_type, f"move:{payload['ulid']}", payload))
    return batch, pending_activity_opens


def backfill_atividades_from_rationalizations(log=eventlog.LOG):
    """Emit missing atividade.opened/touched for rationalized sessions (no re-LLM).

    For each ``sessao.racionalizada`` whose role attribution marks durable human activity:
    - if no ``atividade.opened`` carries ``origem_sessao == sessao_id``, open and
      touch one activity via public eventlog pens (tier llm_judged, author racionalizador);
    - if open exists but no ``atividade.touched`` for that session×activity, append
      the missing touch only (repairs incomplete prior backfill / crash window).

    Eligibility comes from the rationalizer's role attribution, never from vocabulary.
    """
    emitted = []
    for event in eventlog.read(types=["sessao.racionalizada"], log=log):
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        session_id = payload.get("sessao_id")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        stitch = payload.get("stitch") if isinstance(payload.get("stitch"), dict) else {}
        attribution = (stitch.get("attribution")
                       if isinstance(stitch.get("attribution"), dict) else {})
        if attribution.get("activity_relevant") is not True:
            continue
        goal = attribution.get("human_purpose")
        if not isinstance(goal, str) or not goal.strip():
            continue
        operations = payload.get("operacoes")
        if (not isinstance(operations, list) or not operations
                or not isinstance(operations[0], str) or not operations[0].strip()):
            continue
        rationalization_id = payload.get("rationalization_id")
        if not isinstance(rationalization_id, str) or not rationalization_id.strip():
            continue
        acao = attribution.get("shared_outcome")
        acao_s = acao.strip() if isinstance(acao, str) and acao.strip() else ""
        novo = acao_s or goal.strip()

        session_opens = []
        for open_event in eventlog.read(types=["atividade.opened"], log=log):
            open_payload = (open_event.get("payload")
                            if isinstance(open_event.get("payload"), dict) else {})
            if open_payload.get("origem_sessao") == session_id:
                session_opens.append(open_payload)

        if not session_opens:
            key = _derivation_key(rationalization_id, "backfill", 0)
            opened = eventlog.open_atividade(
                operacao=operations[0].strip(),
                finalidade=goal.strip(),
                tier="llm_judged",
                author="racionalizador",
                origem_sessao=session_id,
                derivation_key=key,
                log=log,
            )
            emitted.append(opened)
            touched = eventlog.touch_atividade(
                ref=opened["payload"]["ulid"],
                sessao=session_id,
                novo=novo,
                tier="llm_judged",
                log=log,
            )
            emitted.append(touched)
            continue

        # Repair open-without-touch (separate pens left a crash window).
        touched_refs = set()
        for touch_event in eventlog.read(types=["atividade.touched"], log=log):
            touch_payload = (touch_event.get("payload")
                             if isinstance(touch_event.get("payload"), dict) else {})
            if touch_payload.get("sessao") == session_id:
                ref = touch_payload.get("ref")
                if isinstance(ref, str) and ref.strip():
                    touched_refs.add(ref.strip())
        for open_payload in session_opens:
            ulid = open_payload.get("ulid")
            if not isinstance(ulid, str) or not ulid.strip():
                continue
            if ulid in touched_refs:
                continue
            touched = eventlog.touch_atividade(
                ref=ulid,
                sessao=session_id,
                novo=novo,
                tier="llm_judged",
                log=log,
            )
            emitted.append(touched)
            touched_refs.add(ulid)
    return emitted


def rationalize(
    session_id,
    turns,
    complete_fn,
    log=eventlog.LOG,
    *,
    surface="claude",
    watermark=None,
    racionalizador_version=DEFAULT_VERSION,
    scene_turn_limit=None,
    max_scenes=9,
    sweep_token_budget=None,
    open_threads=None,
):
    """Rationalize one persisted session and atomically checkpoint its validated batch.

    Identical input/version returns no events.  A later input for the same session names
    the previous rationalization in ``supersedes`` under the append lock.

    ``open_threads`` — the currently-open Atividades (``eventlog.atividades_at`` folded to
    ``estado in {aberta, reaberta}``, each ``{operacao, finalidade}``). Fed into the session
    prompt so the ``activity_relevant`` gate discriminates on CONNECTION to a live thread, not
    on frequency: a one-off front connected to an open thread survives the sweep (#584).
    """
    session_id = _nonblank(session_id, "session_id")
    surface = _nonblank(surface, "surface")
    version = _nonblank(racionalizador_version, "racionalizador_version")
    normalized_turns = _normalized_turns(turns)
    if scene_turn_limit is not None and (
        not isinstance(scene_turn_limit, int) or isinstance(scene_turn_limit, bool)
        or scene_turn_limit < 1
    ):
        raise ValueError("scene_turn_limit must be a positive integer or None")
    if (not isinstance(max_scenes, int) or isinstance(max_scenes, bool) or max_scenes < 3):
        raise ValueError("max_scenes must be an integer >= 3 (start/middle/end)")
    if sweep_token_budget is not None and (
        not isinstance(sweep_token_budget, int) or isinstance(sweep_token_budget, bool)
        or sweep_token_budget < 1
    ):
        raise ValueError("sweep_token_budget must be a positive integer or None")
    if watermark is None:
        watermark = len(normalized_turns)
    if isinstance(watermark, (dict, list)) or watermark is None:
        raise ValueError("watermark must be a scalar cursor")

    # Open threads the connection discriminator judges against — {operacao, finalidade} only,
    # blanks dropped. Empty/None omits the key (backward-compatible prompt).
    open_context = [
        {"operacao": t["operacao"].strip(), "finalidade": t["finalidade"].strip()}
        for t in (open_threads or [])
        if isinstance(t, dict)
        and isinstance(t.get("operacao"), str) and t["operacao"].strip()
        and isinstance(t.get("finalidade"), str) and t["finalidade"].strip()
    ]

    source_hash = _digest({
        "session_id": session_id,
        "surface": surface,
        "watermark": watermark,
        "turns": normalized_turns,
    })
    rationalization_id = _digest({
        "source_hash": source_hash,
        "racionalizador_version": version,
    })
    if any(
        event["payload"].get("rationalization_id") == rationalization_id
        for event in _rationalizations(log)
    ):
        return {"emitted": [], "skipped_reason": "already_rationalized"}

    usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_tokens": 0}

    def _complete(request):
        prompt = json.dumps(request, ensure_ascii=False, sort_keys=True)
        cost = _estimated_tokens(prompt)
        if (sweep_token_budget is not None
                and usage["estimated_tokens"] + cost > sweep_token_budget):
            raise _BudgetExhausted
        usage["input_tokens"] += cost
        usage["estimated_tokens"] += cost
        usage["calls"] += 1
        raw = complete_fn(prompt)
        rendered = raw if isinstance(raw, str) else json.dumps(
            raw, ensure_ascii=False, sort_keys=True
        )
        output_cost = _estimated_tokens(rendered)
        usage["output_tokens"] += output_cost
        usage["estimated_tokens"] += output_cost
        if (sweep_token_budget is not None
                and usage["estimated_tokens"] > sweep_token_budget):
            raise _BudgetExhausted
        return raw

    # Scene summaries for long sessions (free density for employment digests).
    # Single-shot path leaves []. Additive field — does not enter rationalization_id.
    summaries = []
    try:
        if scene_turn_limit is not None and len(normalized_turns) > scene_turn_limit:
            scenes = _uniform_scenes(normalized_turns, scene_turn_limit, max_scenes)
            for index, scene in enumerate(scenes):
                raw_scene = _complete({
                    "stage": "scene",
                    "question": (
                        "Que finalidade os turnos humanos sustentam, o que o edge executou "
                        "e o que isso mudou para aquela finalidade?"
                    ),
                    "instruction": _SCENE_JSON_INSTRUCTION,
                    "session_id": session_id,
                    "scene_index": index,
                    "scene_count": len(scenes),
                    "turns": scene,
                })
                try:
                    scene_output = _loads_json_loose(raw_scene)
                except ValueError as exc:
                    # Prose fallback: free-form completers sometimes ignore JSON shape.
                    if isinstance(raw_scene, str) and raw_scene.strip():
                        scene_output = {"summary": raw_scene.strip()}
                    else:
                        raise ValueError(
                            f"scene[{index}] output is not valid JSON: {exc}"
                        ) from exc
                if not isinstance(scene_output, dict):
                    raise ValueError(f"scene[{index}] output must be an object")
                summaries.append({
                    "summary": _nonblank(
                        scene_output.get("summary"), f"scene[{index}].summary"),
                    "human_turn_indexes": [
                        turn["turn_index"] for turn in scene if turn["role"] == "human"
                    ],
                })
            raw_output = _complete({
                "stage": "consolidate",
                "question": (
                    "Qual finalidade humana esta sessão avança, o que o edge executou e "
                    "qual resultado compartilhado houve?"
                ),
                "instruction": _SESSION_JSON_INSTRUCTION,
                "session_id": session_id,
                "surface": surface,
                "watermark": watermark,
                "scene_summaries": summaries,
                **({"open_threads": open_context} if open_context else {}),
            })
        else:
            raw_output = _complete({
                "stage": "session",
                "question": (
                    "Qual finalidade humana esta sessão avança, o que o edge executou e "
                    "qual resultado compartilhado houve?"
                ),
                "instruction": _SESSION_JSON_INSTRUCTION,
                "session_id": session_id,
                "surface": surface,
                "watermark": watermark,
                "turns": normalized_turns,
                **({"open_threads": open_context} if open_context else {}),
            })
        output = _validated_output(raw_output, turns=normalized_turns)
    except _BudgetExhausted:
        return {
            "emitted": [],
            "skipped_reason": "budget_exhausted",
            "usage": usage,
        }
    except ValueError as exc:
        return {
            "emitted": [],
            "skipped_reason": "invalid_output",
            "error": str(exc),
            "usage": usage,
        }

    payload = {
        "sessao_id": session_id,
        "surface": surface,
        "watermark": watermark,
        "operacoes": output["operacoes"],
        "source_hash": source_hash,
        "rationalization_id": rationalization_id,
        "racionalizador_version": version,
        "stitch": output["stitch"],
        "epistemico": output["epistemico"],
        "organizacional": output["organizacional"],
        "cenas": summaries,
    }
    try:
        derived_batch, pending_activity_opens = _build_derived_batch(
            output, session_id, source_hash, rationalization_id, log)
    except ValueError as exc:
        return {"emitted": [], "skipped_reason": "invalid_output",
                "error": str(exc), "usage": usage}
    batch = [("sessao.racionalizada", f"sessao:{session_id}", payload)] + derived_batch

    def _cas_and_overlay():
        existing = _rationalizations(log, session_id=session_id)
        if any(
            event["payload"].get("rationalization_id") == rationalization_id
            for event in existing
        ):
            raise _AlreadyRationalized
        previous = next((
            event["payload"].get("rationalization_id")
            for event in reversed(existing)
            if isinstance(event["payload"].get("rationalization_id"), str)
        ), None)
        if previous:
            payload["supersedes"] = previous
        next_numbers = {}
        existing_events = eventlog.read(log=log)
        for activity in pending_activity_opens:
            operation = activity["operacao"]
            if operation not in next_numbers:
                first = eventlog._next_lens_num(existing_events, operation, "atv")
                next_numbers[operation] = int(first.split("-", 1)[1])
            activity["num"] = f"atv-{next_numbers[operation]:03d}"
            next_numbers[operation] += 1
            if not eventlog._foldable_activity_open(activity):
                raise ValueError("derived atividade.opened failed canonical eventlog validation")

        existing_move_keys = {
            event["payload"].get("move_key")
            for event in existing_events if event.get("type") == "move.proposed"
            and isinstance(event.get("payload"), dict)
        }
        batch[:] = [batch[0]] + [event for event in batch[1:]
                                if not (event[0] == "move.proposed"
                                        and event[2].get("move_key") in existing_move_keys)]

    try:
        emitted = eventlog.append_batch(
            batch,
            log=log,
            precondition=_cas_and_overlay,
        )
    except _AlreadyRationalized:
        return {"emitted": [], "skipped_reason": "already_rationalized"}
    except ValueError as exc:
        return {"emitted": [], "skipped_reason": "invalid_output",
                "error": str(exc), "usage": usage}
    return {"emitted": emitted, "usage": usage}
