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


DEFAULT_VERSION = "racionalizador-v1"
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


def _nonblank(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-blank string")
    return value.strip()


def _normalized_turns(turns):
    normalized = []
    for index, turn in enumerate(turns):
        if isinstance(turn, dict):
            role, text = turn.get("role"), turn.get("text")
        else:
            role, text = getattr(turn, "role", None), getattr(turn, "text", None)
        role = _nonblank(role, f"turns[{index}].role").lower()
        if not isinstance(text, str):
            raise ValueError(f"turns[{index}].text must be a string")
        text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
        normalized.append({"role": role, "text": text.strip()})
    if not normalized:
        raise ValueError("turns must contain at least one dialogue turn")
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


def _validated_output(raw):
    try:
        output = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError) as exc:
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
    goal = _nonblank(stitch.get("goal"), "stitch.goal")
    action = _nonblank(stitch.get("acao"), "stitch.acao")
    entities = stitch.get("entidades")
    if not isinstance(entities, list):
        raise ValueError("stitch.entidades must be a list")
    normalized_entities = [
        _full_ref(entity, f"stitch.entidades[{index}]", normalized_operations)
        for index, entity in enumerate(entities)
    ]

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

    return {
        "operacoes": normalized_operations,
        "stitch": {"goal": goal, "acao": action, "entidades": normalized_entities},
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
        if item is not None and item["estado"] in ("aberta", "reaberta"):
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
):
    """Rationalize one persisted session and atomically checkpoint its validated batch.

    Identical input/version returns no events.  A later input for the same session names
    the previous rationalization in ``supersedes`` under the append lock.
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

    try:
        if scene_turn_limit is not None and len(normalized_turns) > scene_turn_limit:
            scenes = _uniform_scenes(normalized_turns, scene_turn_limit, max_scenes)
            summaries = []
            for index, scene in enumerate(scenes):
                raw_scene = _complete({
                    "stage": "scene",
                    "question": "Que atividade esta cena continua, abre ou muda?",
                    "session_id": session_id,
                    "scene_index": index,
                    "scene_count": len(scenes),
                    "turns": scene,
                })
                try:
                    scene_output = json.loads(raw_scene) if isinstance(raw_scene, str) else raw_scene
                except (TypeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"scene[{index}] output is not valid JSON: {exc}") from exc
                if not isinstance(scene_output, dict):
                    raise ValueError(f"scene[{index}] output must be an object")
                summaries.append(_nonblank(scene_output.get("summary"), f"scene[{index}].summary"))
            raw_output = _complete({
                "stage": "consolidate",
                "question": "Esta sessão muda algo no que fazemos?",
                "session_id": session_id,
                "surface": surface,
                "watermark": watermark,
                "scene_summaries": summaries,
            })
        else:
            raw_output = _complete({
                "stage": "session",
                "question": "Esta sessão muda algo no que fazemos?",
                "session_id": session_id,
                "surface": surface,
                "watermark": watermark,
                "turns": normalized_turns,
            })
        output = _validated_output(raw_output)
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
