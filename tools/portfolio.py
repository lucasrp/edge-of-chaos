"""Pure selectors over eventlog projections."""

import hashlib
import re
from pathlib import Path

import eventlog
import md_to_mem


DEFAULT_VIEW = Path(__file__).resolve().parent.parent / "state" / "wayfinds" / "portfolio.md"
_DIRECTION_GESTURES = (
    "abertos", "fechados", "reabertos", "ativados", "pausados", "arquivados",
    "moves_ratificados",
)


class AmbiguousFocus(ValueError):
    """A touch without an explicit activity has zero or multiple valid targets."""


class _Turn:
    def __init__(self, dispatch_id, operacao, log):
        if not isinstance(dispatch_id, str) or not dispatch_id.strip():
            raise ValueError("`dispatch_id` must be a non-blank string")
        if not isinstance(operacao, str) or not operacao.strip():
            raise ValueError("`operacao` must be a non-blank string")
        self.dispatch_id = dispatch_id.strip()
        self.operacao = operacao.strip()
        self.log = log
        self._focus = None

    def _activities(self):
        return eventlog.atividades_at(log=self.log)

    def _resolve_activity(self, ref):
        activities = self._activities()
        if ref in activities:
            return ref, activities[ref]
        bound = f"{self.operacao}/{ref}" if isinstance(ref, str) and "/" not in ref else None
        if bound in activities:
            return bound, activities[bound]
        matches = [(full_ref, item) for full_ref, item in activities.items()
                   if item.get("ulid") == ref and item.get("operacao") == self.operacao]
        if len(matches) != 1:
            raise ValueError(f"activity {ref!r} does not resolve in {self.operacao!r}")
        return matches[0]

    def _touch_target(self, activity):
        if activity is not None:
            full_ref, before = self._resolve_activity(activity)
            return full_ref, before, before["estado"]
        if self._focus is not None:
            full_ref, expected_state = self._focus
            resolved_ref, before = self._resolve_activity(full_ref)
            return resolved_ref, before, expected_state
        candidates = [(full_ref, item) for full_ref, item in self._activities().items()
                      if item.get("operacao") == self.operacao
                      and item.get("estado") in ("aberta", "reaberta")]
        if len(candidates) != 1:
            raise AmbiguousFocus(
                f"touch needs exactly one open activity in {self.operacao!r}; "
                f"found {len(candidates)}"
            )
        full_ref, before = candidates[0]
        return full_ref, before, before["estado"]

    def open(self, *, finalidade, eval=None, arco=None, tipo_ref=None,
             tier="asserted", author="grill", origem_sessao=None,
             derivation_key=None):
        landed = eventlog.open_atividade(
            operacao=self.operacao, finalidade=finalidade, eval=eval, arco=arco,
            tipo_ref=tipo_ref, tier=tier, author=author,
            origem_sessao=origem_sessao, derivation_key=derivation_key,
            dispatch_id=self.dispatch_id, log=self.log,
        )
        full_ref = f"{self.operacao}/{landed['payload']['num']}"
        after = self._activities()[full_ref]
        self._focus = (full_ref, after["estado"])
        return {"target": full_ref, "before": None, "event": landed, "after": after}

    def map(self, *, titulo, rationale, thread=None, tier="asserted", author="grill",
            resolve_thread_fn=None):
        """Open one map through the dispatch/operation-bound curatorial surface."""
        if thread is not None and resolve_thread_fn is None:
            import thread_resolver
            resolve_thread_fn = thread_resolver.resolve_for_install
        landed = eventlog.open_map(
            operacao=self.operacao, titulo=titulo, rationale=rationale,
            dispatch_id=self.dispatch_id, author=author, thread=thread,
            resolve_thread_fn=resolve_thread_fn, tier=tier, log=self.log,
        )
        full_ref = f"{self.operacao}/{landed['payload']['num']}"
        after = eventlog.wayfinds_at(log=self.log)["maps"][full_ref]
        return {"target": full_ref, "before": None, "event": landed, "after": after}

    def touch(self, *, sessao, activity=None, novo=None, files=None, spans=None,
              tier="asserted"):
        full_ref, before, expected_state = self._touch_target(activity)
        landed = eventlog.touch_atividade(
            ref=full_ref, sessao=sessao, novo=novo, files=files, spans=spans,
            tier=tier, operacao=self.operacao, dispatch_id=self.dispatch_id,
            expects={"estado": expected_state}, log=self.log,
        )
        after = self._activities()[full_ref]
        self._focus = ((full_ref, after["estado"])
                       if after["estado"] in ("aberta", "reaberta") else None)
        return {"target": full_ref, "before": before, "event": landed, "after": after}

    def close(self, *, activity=None, estado, julgamento, rationale,
              superada_por=None, tier="asserted", author="grill"):
        if activity is None:
            raise ValueError("close requires an explicit activity target")
        full_ref, before = self._resolve_activity(activity)
        landed = eventlog.close_atividade(
            ref=full_ref, estado=estado, julgamento=julgamento,
            superada_por=superada_por, tier=tier, author=author,
            rationale=rationale, dispatch_id=self.dispatch_id,
            operacao=self.operacao, expects={"estado": ["aberta", "reaberta"]},
            log=self.log,
        )
        after = self._activities()[full_ref]
        if self._focus is not None and self._focus[0] == full_ref:
            self._focus = None
        return {"target": full_ref, "before": before, "event": landed, "after": after}

    def reopen(self, *, activity=None, motivo, rationale, evidencia=None,
               tier="asserted", author="grill"):
        if activity is None:
            raise ValueError("reopen requires an explicit activity target")
        full_ref, before = self._resolve_activity(activity)
        landed = eventlog.reopen_atividade(
            ref=full_ref, motivo=motivo, evidencia=evidencia,
            tier=tier, author=author, rationale=rationale,
            dispatch_id=self.dispatch_id, operacao=self.operacao,
            expects={"estado": before["estado"]}, log=self.log,
        )
        after = self._activities()[full_ref]
        self._focus = (full_ref, after["estado"])
        return {"target": full_ref, "before": before, "event": landed, "after": after}

    def _resolve_move(self, ref):
        moves = eventlog.wayfinds_at(log=self.log)["moves"]
        matches = [move for state in ("propostos", "ratificados", "declinados")
                   for move in moves[state] if move.get("ulid") == ref]
        if len(matches) != 1:
            raise ValueError(f"move {ref!r} does not resolve")
        return matches[0]

    def ratify(self, *, move=None, rationale, author="grill"):
        if move is None:
            raise ValueError("ratify requires an explicit move target")
        before = self._resolve_move(move)
        landed = eventlog.ratify_move(
            ref=move, rationale=rationale, dispatch_id=self.dispatch_id,
            author=author, operacao=self.operacao, log=self.log,
        )
        after = self._resolve_move(move)
        return {"target": move, "before": before, "event": landed, "after": after}

    def decline(self, *, move=None, reason, rationale=None, pin=False, author="grill"):
        if move is None:
            raise ValueError("decline requires an explicit move target")
        before = self._resolve_move(move)
        landed = eventlog.decline_move(
            ref=move, reason=reason, rationale=rationale,
            dispatch_id=self.dispatch_id, author=author, pin=pin,
            operacao=self.operacao, log=self.log,
        )
        after = self._resolve_move(move)
        return {"target": move, "before": before, "event": landed, "after": after}

    def refute(self, *, activity=None, alvo=None, evidencia=None, tier="asserted"):
        if activity is None or alvo is None:
            raise ValueError("refute requires explicit activity and alvo targets")
        full_ref, before = self._resolve_activity(activity)
        landed = eventlog.bears_on(
            ref=full_ref, alvo=alvo, valencia="refutes", evidencia=evidencia,
            tier=tier, operacao=self.operacao, dispatch_id=self.dispatch_id,
            expects={"estado": before["estado"]}, log=self.log,
        )
        after = self._activities()[full_ref]
        return {"target": full_ref, "before": before, "event": landed, "after": after}


def turn(dispatch_id, operacao, log):
    """Bind one grill turn explicitly to its dispatch, operation, and ledger."""
    return _Turn(dispatch_id, operacao, log)


def reconcile(log):
    """Mechanically propose cross-lens moves from explicit ledger relationships."""
    events = eventlog.read(log=log)
    basis_seq = max(
        (event.get("seq") for event in events
         if isinstance(event.get("seq"), int) and not isinstance(event.get("seq"), bool)),
        default=0,
    )
    emitted = []
    activities = eventlog.atividades_at(log=log)
    wayfinds = eventlog.wayfinds_at(log=log)
    for activity_ref, activity in activities.items():
        closure = activity.get("fecho")
        if closure is None or activity.get("estado") in ("aberta", "reaberta"):
            continue
        if not any(touch.get("seq", -1) > closure.get("seq", -1)
                   for touch in activity.get("toques", [])):
            continue
        event = eventlog.propose_move(
            kind="contest", alvo=activity_ref,
            effect={
                "event_type": "contest.raised",
                "subject": f"atividade:{activity['ulid']}",
                "payload": {
                    "alvo": activity["ulid"], "evidencia": activity_ref,
                    "detalhe": "atividade fechada recebeu evidência posterior",
                    "author": "edge",
                },
            },
            expects={"estado": activity["estado"]}, evidencia=[activity_ref],
            rationale="Touch posterior contesta o fecho da atividade",
            basis_seq=basis_seq, operacao=activity["operacao"], log=log,
        )
        if event is not None:
            emitted.append(event)
    tickets_by_ulid = {ticket["ulid"]: (ticket_ref, ticket)
                       for ticket_ref, ticket in wayfinds["tickets"].items()}
    mapped_activity_refs = {
        activity_ref for activity_ref, activity in activities.items()
        if any(bearing.get("alvo") in tickets_by_ulid
               for bearing in activity.get("bears_on", []))
    }
    ticket_contest_targets = set()
    for activity_ref, activity in activities.items():
        target_ulids = {bearing.get("alvo") for bearing in activity.get("bears_on", [])
                        if isinstance(bearing.get("alvo"), str)}
        for target_ulid in sorted(target_ulids):
            target = tickets_by_ulid.get(target_ulid)
            if target is None:
                continue
            ticket_ref, ticket = target
            closure = ticket.get("fecho")
            if closure is None or ticket.get("estado") != "closed":
                continue
            if not any(touch.get("seq", -1) > closure.get("seq", -1)
                       for touch in activity.get("toques", [])):
                continue
            if ticket["ulid"] in ticket_contest_targets:
                continue
            event = eventlog.propose_move(
                kind="contest", alvo=ticket_ref,
                effect={
                    "event_type": "contest.raised",
                    "subject": f"ticket:{ticket['ulid']}",
                    "payload": {
                        "alvo": ticket["ulid"], "evidencia": activity_ref,
                        "detalhe": "atividade ligada retomou trabalho após o fecho do ticket",
                        "author": "edge",
                    },
                },
                expects={"estado": "closed"}, evidencia=[activity_ref],
                rationale="Retrabalho contesta o fecho do ticket",
                basis_seq=basis_seq, operacao=ticket["operacao"], log=log,
            )
            if event is not None:
                emitted.append(event)
            ticket_contest_targets.add(ticket["ulid"])
    for rationalization in eventlog.read(types=["sessao.racionalizada"], log=log):
        payload = (rationalization.get("payload")
                   if isinstance(rationalization.get("payload"), dict) else {})
        session = payload.get("sessao_id")
        stitch = payload.get("stitch")
        entities = stitch.get("entidades") if isinstance(stitch, dict) else None
        if not isinstance(session, str) or not isinstance(entities, list):
            continue
        evidence = sorted(
            activity_ref for activity_ref, activity in activities.items()
            if any(touch.get("sessao") == session for touch in activity.get("toques", []))
        )
        for entity in entities:
            if isinstance(entity, dict):
                operation, number = entity.get("operacao"), entity.get("num")
                full_ref = (f"{operation}/{number}"
                            if isinstance(operation, str) and isinstance(number, str) else None)
            else:
                full_ref = entity if isinstance(entity, str) and entity.count("/") == 1 else None
            ticket = wayfinds["tickets"].get(full_ref)
            if ticket is None:
                continue
            session_evidence = [ref for ref in evidence
                                if activities[ref]["operacao"] == ticket["operacao"]]
            mapped_activity_refs.update(session_evidence)
            if ticket.get("estado") != "closed":
                continue
            closure = ticket.get("fecho") or {}
            matching_evidence = [
                ref for ref in session_evidence
                if any(touch.get("sessao") == session
                       and touch.get("seq", -1) > closure.get("seq", -1)
                       for touch in activities[ref].get("toques", []))
            ]
            if not matching_evidence:
                continue
            if ticket["ulid"] in ticket_contest_targets:
                continue
            evidence_ref = matching_evidence[0]
            event = eventlog.propose_move(
                kind="contest", alvo=full_ref,
                effect={
                    "event_type": "contest.raised",
                    "subject": f"ticket:{ticket['ulid']}",
                    "payload": {
                        "alvo": ticket["ulid"], "evidencia": evidence_ref,
                        "detalhe": "STITCH pleno retomou um ticket fechado",
                        "author": "edge",
                    },
                },
                expects={"estado": "closed"}, evidencia=matching_evidence,
                rationale="STITCH pleno contesta o fecho do ticket",
                basis_seq=basis_seq, operacao=ticket["operacao"], log=log,
            )
            if event is not None:
                emitted.append(event)
            ticket_contest_targets.add(ticket["ulid"])
    tickets_by_hypothesis = {}
    for ticket_ref, ticket in wayfinds["tickets"].items():
        if isinstance(ticket.get("inscricao"), str):
            tickets_by_hypothesis.setdefault(ticket["inscricao"], []).append(
                (ticket_ref, ticket)
            )
    for run_ref, run in eventlog.runs_at(log=log).items():
        closure = run.get("fecho") or {}
        for bearing in closure.get("bears_on", []):
            hypothesis = bearing.get("alvo")
            if bearing.get("valencia") != "refutes":
                continue
            for ticket_ref, ticket in tickets_by_hypothesis.get(hypothesis, []):
                event = eventlog.propose_move(
                    kind="falsificador_aconteceu", alvo=ticket_ref,
                    effect={
                        "event_type": "contest.raised",
                        "subject": f"ticket:{ticket['ulid']}",
                        "payload": {
                            "alvo": ticket["ulid"], "evidencia": run_ref,
                            "detalhe": f"hypothesis {hypothesis} refutada por {run_ref}",
                            "author": "edge",
                        },
                    },
                    expects={"estado": ticket["estado"]}, evidencia=[run_ref],
                    rationale="Falsificador inscrito aconteceu",
                    basis_seq=basis_seq, operacao=ticket["operacao"], log=log,
                )
                if event is not None:
                    emitted.append(event)
    all_moves = [move for state in ("propostos", "ratificados", "declinados")
                 for move in wayfinds["moves"][state]]
    ticket_open_sources = {
        annotations.get("source_activity")
        for move in all_moves if move.get("kind") == "ticket.open"
        for effect in [move.get("effect") if isinstance(move.get("effect"), dict) else {}]
        for effect_payload in [effect.get("payload")
                               if isinstance(effect.get("payload"), dict) else {}]
        for annotations in [effect_payload.get("annotations")
                            if isinstance(effect_payload.get("annotations"), dict) else {}]
        if isinstance(annotations.get("source_activity"), str)
    }
    active_maps_by_operation = {}
    for map_ref, item in wayfinds["maps"].items():
        if item.get("estado") == "ativado":
            active_maps_by_operation.setdefault(item["operacao"], []).append((map_ref, item))
    ticket_open_covered = set(ticket_open_sources)
    for activity_ref, activity in sorted(activities.items()):
        touched_sessions = {touch.get("sessao") for touch in activity.get("toques", [])
                            if isinstance(touch.get("sessao"), str)}
        candidate_maps = active_maps_by_operation.get(activity["operacao"], [])
        if (activity.get("estado") not in ("aberta", "reaberta")
                or activity_ref in mapped_activity_refs
                or activity.get("eval") is None or len(touched_sessions) < 2
                or len(candidate_maps) != 1):
            continue
        if activity_ref in ticket_open_sources:
            ticket_open_covered.add(activity_ref)
            continue
        map_ref, target_map = candidate_maps[0]
        evaluation = activity["eval"]
        question = (evaluation.get("regua") if isinstance(evaluation, dict) else None)
        question = (question if isinstance(question, str) and question.strip()
                    else activity["finalidade"])
        event = eventlog.propose_move(
            kind="ticket.open", alvo=map_ref,
            effect={
                "event_type": "ticket.opened", "subject": None,
                "payload": {
                    "map": target_map["ulid"], "titulo": activity["finalidade"],
                    "question": question,
                    "rationale": "Atividade cobrável persistiu sem ticket por duas sessões",
                    "blocked_by": [], "inscricao": None, "tier": "llm_judged",
                    "author": "edge", "dispatch_id": f"reconcile:{activity['ulid']}",
                    "legacy_ref": None, "annotations": {"source_activity": activity_ref},
                },
            },
            expects={"estado": "ativado"}, evidencia=[activity_ref],
            rationale="Trabalho sem mapa cruzou o critério falsificável",
            basis_seq=basis_seq, operacao=activity["operacao"], log=log,
        )
        if event is not None:
            emitted.append(event)
        # None means the pen found the same logical intent under its flock; either way the
        # activity is represented by the proposal and must not also consume the signal lane.
        ticket_open_covered.add(activity_ref)
    sem_mapa = []
    for activity_ref, activity in sorted(activities.items()):
        if activity.get("estado") not in ("aberta", "reaberta"):
            continue
        if activity_ref in mapped_activity_refs:
            continue
        if activity_ref in ticket_open_covered:
            continue
        motivo = ("loop" if activity.get("toques") and not activity.get("novo")
                  else "largada")
        sem_mapa.append({"ref": activity_ref, "operacao": activity["operacao"],
                         "motivo": motivo})
    return {"emitted": emitted, "sem_mapa": sem_mapa}


def direction_gate(dispatch_id, log):
    """Require a curatorial portfolio gesture from one exact mentor dispatch."""
    diff = eventlog.portfolio_diff(dispatch_id, log=log)
    if diff["confirmed"] or any(diff[field] for field in _DIRECTION_GESTURES):
        return True
    raise ValueError(
        f"dispatch {dispatch_id!r} has no portfolio diff or matching confirmed event"
    )


def _markdown_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def render(log, out=DEFAULT_VIEW):
    """Write a deterministic Markdown view of the current wayfinder fold."""
    folded = eventlog.wayfinds_at(log=log)
    maps = sorted(folded["maps"].values(), key=lambda item: item["ref"])
    tickets = folded["tickets"]
    ticket_ref_by_ulid = {item["ulid"]: item["ref"] for item in tickets.values()}
    lines = ["<!-- GERADO — edite via eventos. -->", "", "# Portfólio", ""]
    for item in maps:
        lines.extend([
            f"## {_markdown_cell(item['ref'])} — {_markdown_cell(item['titulo'])} "
            f"({_markdown_cell(item['estado'])})",
            "",
            _markdown_cell(item["rationale"]),
            "",
            "| ref | ticket | estado | depende de | rationale |",
            "|---|---|---|---|---|",
        ])
        for ticket_ref in sorted(item["tickets"]):
            ticket = tickets[ticket_ref]
            blockers = [ticket_ref_by_ulid.get(ref, ref)
                        for ref in ticket.get("blocked_by", [])]
            lines.append(
                f"| {_markdown_cell(ticket_ref)} | {_markdown_cell(ticket['titulo'])} | "
                f"{_markdown_cell(ticket['estado'])} | "
                f"{_markdown_cell(', '.join(blockers) or '—')} | "
                f"{_markdown_cell(ticket['rationale'])} |"
            )
        lines.append("")
    rendered = "\n".join(lines).rstrip() + "\n"
    destination = Path(out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(rendered.encode("utf-8"))
    return destination


_LEGACY_MAP_RE = re.compile(
    r"^##\s+(M\d+)\s+[—-]\s+(.+?)(?:\s+\(([^)]*)\))?$"
)
_LEGACY_TICKET_RE = re.compile(r"^M\d+\.\w+$")


def _legacy_portfolio(source):
    maps = []
    paused = []
    current = None
    in_paused = False
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            in_paused = line == "## PAUSADOS / FORA DO PORTFÓLIO"
        heading = _LEGACY_MAP_RE.match(line)
        if heading:
            current = {
                "legacy_ref": heading.group(1),
                "titulo": heading.group(2).strip(),
                "raw_state": (heading.group(3) or "").strip(),
                "rationale": None,
                "tickets": [],
            }
            maps.append(current)
            continue
        if in_paused and line.startswith("- "):
            paused.extend(item.strip() for item in line[2:].split(" · ") if item.strip())
            continue
        if current is not None and line.startswith("*Visão:") and line.endswith("*"):
            current["rationale"] = line[len("*Visão:"):-1].strip()
            continue
        if current is None or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 5 or not _LEGACY_TICKET_RE.fullmatch(cells[0]):
            continue
        current["tickets"].append({
            "legacy_ref": cells[0],
            "titulo": cells[1],
            "raw_state": cells[2].replace("**", "").strip(),
            "depends_on": cells[3],
            "rationale": cells[4],
        })
    return {"maps": maps, "paused": paused}


def migrate(path, log):
    """Migrate a hand-authored portfolio snapshot through the public eventlog pens."""
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    slug = f"portfolio-migration-{hashlib.sha256(source.encode('utf-8')).hexdigest()[:16]}"
    if slug in {doc["slug"] for doc in eventlog.docs_at(log=log)["live"]}:
        raise ValueError(f"portfolio snapshot {slug!r} already migrated")
    dispatch_id = f"migration:{slug}"
    migrated = {"maps": [], "tickets": [], "doc": slug}
    parsed = _legacy_portfolio(source)
    tickets_by_legacy = {}
    ticket_maps = {}
    for legacy_map in parsed["maps"]:
        opened_map = eventlog.open_map(
            operacao="edge",
            titulo=f"{legacy_map['legacy_ref']} — {legacy_map['titulo']}",
            rationale=legacy_map["rationale"] or legacy_map["titulo"],
            dispatch_id=dispatch_id, author="operador", log=log,
        )
        map_ref = f"edge/{opened_map['payload']['num']}"
        migrated["maps"].append(map_ref)
        for legacy_ticket in legacy_map["tickets"]:
            raw_state = legacy_ticket["raw_state"]
            dependency_refs = [
                ref.strip() for ref in legacy_ticket["depends_on"].split(",")
                if ref.strip() and ref.strip() != "—"
            ]
            blockers = [tickets_by_legacy[ref] for ref in dependency_refs
                        if ref in tickets_by_legacy and ticket_maps[ref] == map_ref]
            missing = [ref for ref in dependency_refs
                       if ref not in tickets_by_legacy or ticket_maps.get(ref) != map_ref]
            needs_raw_state = not (
                raw_state.upper() == "ABERTO"
                or raw_state.upper().startswith("FECHADO")
                or (raw_state.upper() == "BLOQUEADO" and not missing)
            )
            preserved_state = raw_state
            if missing:
                preserved_state += f" | depende de: {', '.join(missing)}"
                needs_raw_state = True
            annotations = ({"raw_state": preserved_state} if needs_raw_state else None)
            proposed = raw_state.upper().startswith("PROPOSTO")
            opened_ticket = eventlog.open_ticket(
                map=map_ref,
                titulo=legacy_ticket["titulo"],
                question=legacy_ticket["titulo"],
                rationale=legacy_ticket["rationale"],
                dispatch_id=dispatch_id, author="edge" if proposed else "operador",
                tier="llm_judged" if proposed else "asserted",
                blocked_by=blockers,
                legacy_ref=legacy_ticket["legacy_ref"],
                annotations=annotations, log=log,
            )
            ticket_ref = f"edge/{opened_ticket['payload']['num']}"
            migrated["tickets"].append(ticket_ref)
            tickets_by_legacy[legacy_ticket["legacy_ref"]] = ticket_ref
            ticket_maps[legacy_ticket["legacy_ref"]] = map_ref
            if raw_state.upper().startswith("FECHADO"):
                eventlog.close_ticket(
                    ref=ticket_ref, resolucao=raw_state, valencia="inconclusive",
                    bears_on=[{"alvo": ticket_ref, "valencia": "no_bearing"}],
                    rationale=legacy_ticket["rationale"], dispatch_id=dispatch_id,
                    author="operador", tier="asserted", log=log,
                )
    for paused_title in parsed["paused"]:
        rationale = f"Migrado de PAUSADOS / FORA DO PORTFÓLIO: {paused_title}"
        opened_map = eventlog.open_map(
            operacao="edge", titulo=paused_title, rationale=rationale,
            dispatch_id=dispatch_id, author="operador", log=log,
        )
        map_ref = f"edge/{opened_map['payload']['num']}"
        eventlog.set_map_state(
            ref=map_ref, estado="pausado", rationale=rationale,
            dispatch_id=dispatch_id, author="operador", log=log,
        )
        migrated["maps"].append(map_ref)
    docs_dir = (md_to_mem.DOCS_DIR
                if Path(log).resolve() == Path(eventlog.LOG).resolve()
                else Path(log).parent / "docs")
    md_to_mem.inject(source, slug, log=log, docs_dir=docs_dir)
    return migrated


def _rank_presumptions(nodes, operation=None):
    scoped = {
        node_id
        for node_id, node in nodes.items()
        if operation is None or operation in node.get("operacoes", [])
    }

    def subtree_size(root):
        visited = set()
        pending = [root]
        while pending:
            node_id = pending.pop()
            if node_id in visited or node_id not in scoped:
                continue
            visited.add(node_id)
            pending.extend(nodes[node_id].get("depends_on", []))
        return len(visited)

    ranked = [
        (node_id, node)
        for node_id, node in nodes.items()
        if node_id in scoped and node.get("eval") is not None
    ]
    ranked.sort(key=lambda pair: (
        -subtree_size(pair[0]),
        str(pair[1].get("kind", "")),
        str(pair[1].get("ref", "")),
        pair[0],
    ))
    return [dict(node) for _, node in ranked]


def bisect(operacao, log):
    """Return operation-scoped questions ordered by structural pruning power."""
    if not isinstance(operacao, str) or not operacao.strip():
        raise ValueError("`operacao` must be a non-blank string")
    operation = operacao.strip()
    return _rank_presumptions(eventlog.presumptions_at(log=log)["nodes"], operation)


def portfolio_at(seq=None, ts=None, log=eventlog.LOG, top_k=10, agenda_k=5):
    """Fold one bounded wake brief from exactly one eventlog snapshot."""
    events = eventlog.read(until_seq=seq, until_ts=ts, log=log)
    wayfinds = eventlog.fold_wayfinds(events)
    activities = eventlog.fold_atividades(events)
    runs = eventlog.fold_runs(events)
    facts = eventlog.fold_fatos(events)
    presumptions = eventlog.fold_presumptions(events)
    canon = eventlog.fold_docs(events)["canon"]
    latest_by_subject = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_seq = event.get("seq")
        if not isinstance(event_seq, int) or isinstance(event_seq, bool):
            continue
        subjects = [event.get("subject")]
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        effect = payload.get("effect") if isinstance(payload.get("effect"), dict) else {}
        subjects.append(effect.get("subject"))
        for subject in subjects:
            if isinstance(subject, str):
                latest_by_subject[subject] = max(
                    event_seq, latest_by_subject.get(subject, -1),
                )
    active_maps = [
        {
            "ref": map_ref,
            "titulo": item["titulo"],
            "frontier": eventlog.frontier_from_wayfinds(map_ref, wayfinds),
        }
        for map_ref, item in sorted(wayfinds["maps"].items())
        if item.get("estado") == "ativado"
    ]
    lane = []
    for activity_ref, item in activities.items():
        if item.get("estado") not in ("aberta", "reaberta"):
            continue
        lane.append((
            latest_by_subject.get(f"atividade:{item['ulid']}", -1),
            "atividade", activity_ref,
            {
                "ref": activity_ref,
                "finalidade": item["finalidade"],
                "estado": item["estado"],
                "sessoes_sem_toque": item["sessoes_sem_toque"],
            },
        ))
    for ticket_ref, item in wayfinds["tickets"].items():
        lane.append((
            latest_by_subject.get(f"ticket:{item['ulid']}", -1),
            "ticket", ticket_ref,
            {"ref": ticket_ref, "titulo": item["titulo"], "estado": item["estado"]},
        ))
    for run_ref, item in runs.items():
        lane.append((
            latest_by_subject.get(f"run:{item['ulid']}", -1),
            "run", run_ref,
            {
                "ref": run_ref, "leva": item.get("leva"), "eval": item.get("eval"),
                "resultado": item.get("resultado"),
                "admissibilidade": item.get("admissibilidade"),
            },
        ))
    for fact_ref, item in facts.items():
        lane.append((
            latest_by_subject.get(f"fato:{item['ulid']}", -1),
            "fato", fact_ref,
            {
                "ref": fact_ref, "leva": item.get("leva"), "body": item.get("body"),
                "medida": item.get("medida"),
                "admissibilidade": item.get("admissibilidade"),
            },
        ))
    presumption_seq = {}
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "sessao.racionalizada":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        identity = (payload.get("rationalization_id") or payload.get("sessao_id")
                    or event.get("seq"))
        epistemic = payload.get("epistemico")
        raw = epistemic.get("presuncoes") if isinstance(epistemic, dict) else None
        if not isinstance(raw, list):
            continue
        for index in range(len(raw)):
            presumption_seq[f"sessao:{identity}:presuncao:{index}"] = event.get("seq", -1)
    for node_id, item in presumptions["nodes"].items():
        if item.get("kind") not in ("claim", "presuncao"):
            continue
        ref = item.get("ref") or node_id
        item_seq = presumption_seq.get(node_id, max(
            latest_by_subject.get(f"claim:{ref}", -1),
            latest_by_subject.get(f"hypothesis:{ref}", -1),
        ))
        lane.append((item_seq, "presuncao", str(ref), dict(item)))
    lane.sort(key=lambda row: (-row[0], row[1], row[2]))
    visible = lane[:top_k]
    lost_activities = [
        {
            "ref": activity_ref,
            "finalidade": item["finalidade"],
            "sessoes_sem_toque": item["sessoes_sem_toque"],
        }
        for activity_ref, item in activities.items()
        if item.get("estado") in ("aberta", "reaberta")
        and item.get("sessoes_sem_toque", 0) > 0
    ]
    lost_activities.sort(key=lambda item: (-item["sessoes_sem_toque"], item["ref"]))
    ticket_ulids = {item["ulid"] for item in wayfinds["tickets"].values()}
    mapped_activities = {
        activity_ref
        for activity_ref, item in activities.items()
        if any(bearing.get("alvo") in ticket_ulids for bearing in item.get("bears_on", []))
    }
    proposed_sources = {
        annotations.get("source_activity")
        for state in ("propostos", "ratificados", "declinados")
        for move in wayfinds["moves"][state]
        for effect in [move.get("effect") if isinstance(move.get("effect"), dict) else {}]
        for payload in [effect.get("payload")
                        if isinstance(effect.get("payload"), dict) else {}]
        for annotations in [payload.get("annotations")
                            if isinstance(payload.get("annotations"), dict) else {}]
        if isinstance(annotations.get("source_activity"), str)
    }
    sem_mapa = []
    for activity_ref, item in sorted(activities.items()):
        if (item.get("estado") not in ("aberta", "reaberta")
                or activity_ref in mapped_activities
                or activity_ref in proposed_sources):
            continue
        sem_mapa.append({
            "ref": activity_ref,
            "operacao": item["operacao"],
            "motivo": ("loop" if item.get("toques") and not item.get("novo") else "largada"),
        })
    admissibility = sorted(
        [
            {"tipo": kind, "ref": ref, "leva": item.get("leva"),
             "admissibilidade": "suspeita"}
            for kind, folded in (("run", runs), ("fato", facts))
            for ref, item in folded.items()
            if item.get("admissibilidade") == "suspeita"
        ],
        key=lambda item: (item["tipo"], item["ref"]),
    )
    agenda = [
        {
            "tipo": "move", "ref": move["ulid"], "kind": move.get("kind"),
            "alvo": move.get("alvo"), "rationale": move.get("rationale"),
        }
        for move in sorted(
            wayfinds["moves"]["propostos"],
            key=lambda item: (-(item.get("seq") if isinstance(item.get("seq"), int) else -1),
                              item.get("ulid", "")),
        )
    ]
    agenda.extend(
        {
            "tipo": "pergunta", "ref": question.get("ref"),
            "kind": question.get("kind"), "eval": question.get("eval"),
            "texto": question.get("texto"),
        }
        for question in _rank_presumptions(presumptions["nodes"])
    )
    agenda = agenda[:agenda_k]
    open_contests = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event_type == "move.ratified":
            effect = payload.get("effect") if isinstance(payload.get("effect"), dict) else {}
            if effect.get("event_type") == "contest.raised":
                event_type = "contest.raised"
                payload = (effect.get("payload")
                           if isinstance(effect.get("payload"), dict) else {})
        target = payload.get("alvo")
        if event_type == "contest.raised" and isinstance(target, str):
            open_contests[target] = {
                "alvo": target,
                "evidencia": payload.get("evidencia"),
                "detalhe": payload.get("detalhe"),
                "author": payload.get("author"),
                "seq": event.get("seq"),
            }
        elif (event_type == "contest.adjudicated" and isinstance(target, str)
              and payload.get("veredito") in ("mantido", "corrigido")):
            open_contests.pop(target, None)
    contested = sorted(
        open_contests.values(),
        key=lambda item: (-(item["seq"] if isinstance(item.get("seq"), int) else -1),
                          item["alvo"]),
    )
    return {
        "mapas_ativos": active_maps,
        "atividades": [item for _, kind, _, item in visible if kind == "atividade"],
        "atividades_perdidas": lost_activities,
        "tickets": [item for _, kind, _, item in visible if kind == "ticket"],
        "runs": [item for _, kind, _, item in visible if kind == "run"],
        "fatos": [item for _, kind, _, item in visible if kind == "fato"],
        "presuncoes": [item for _, kind, _, item in visible if kind == "presuncao"],
        "sem_mapa": sem_mapa,
        "canon": canon,
        "agenda": agenda,
        "contested": contested,
        "admissibilidade": admissibility,
    }
