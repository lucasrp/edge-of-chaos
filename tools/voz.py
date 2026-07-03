"""Voz inbox — a Voz do mentorado como fold do eventlog (canal nativo).

Pendência é DERIVADA do log, nunca armazenada: uma Voz (voz.vote / voz.comment) está
pendente enquanto nenhum voz.disposition fechante a referencia. Voto fecha com recibo;
comentário exige resposta semântica — um recibo registrado não o fecha (invariante
estrutural: o ack barato é inócuo, não proibido).
"""
import eventlog

# O que cada ato exige para FECHAR: voto = recibo; comentário = resposta semântica.
_REQUIRED = {"voz.vote": "receipt", "voz.comment": "semantic"}

STATES = {"receipt_sent", "semantic_answer_required", "semantic_answered", "dead_lettered"}


class VozUnreceived(Exception):
    """Uma Voz pendente sem NENHUMA disposição — ignorada sem nem um recibo."""


def _signal(event):
    p = event.get("payload") or {}
    act = event["type"].split(".", 1)[1]
    return {
        "seq": event["seq"],
        "ts": event.get("ts", ""),
        "channel": "native",
        "act": act,
        "target": p.get("slug") or (event.get("subject", "").split(":", 1) + [""])[1],
        "value": p.get("value"),
        "text": p.get("text"),
        "comment_id": p.get("comment_id"),
        "required": _REQUIRED[event["type"]],
    }


# O que cada estado de disposição fecha: recibo só satisfaz "receipt";
# resposta semântica e dead-letter fecham qualquer exigência.
_CLOSES = {"receipt_sent": {"receipt"},
           "semantic_answered": {"receipt", "semantic"},
           "dead_lettered": {"receipt", "semantic"}}


def fold_voz(events):
    """Fold puro: eventos → {pending: [Signal], dispositions: {seq: [payloads]}}.

    Pendente = Voz cuja exigência (required) não foi fechada por nenhuma disposição.
    Um receipt_sent num comentário é registrado mas NÃO fecha — o invariante
    "semântica não fecha barato" vive aqui, na estrutura, não em validação.
    """
    signals, dispositions, resolved_cids = [], {}, set()
    for e in events:
        t, p = e.get("type"), e.get("payload") or {}
        if t in _REQUIRED:
            signals.append(_signal(e))
        elif t == "voz.disposition":
            dispositions.setdefault(p.get("of"), []).append(p)
        elif t == "voz.resolved":
            # ADR-0017: o terminal do grill (qualquer outcome) fecha o chat — o fold
            # honra os DOIS rails, senão um comentário grill-resolvido nagaria pra sempre.
            resolved_cids.add(p.get("comment_id"))
    pending = [
        s for s in signals
        if not (s.get("comment_id") and s["comment_id"] in resolved_cids)
        and not any(s["required"] in _CLOSES.get(d.get("state"), set())
                    for d in dispositions.get(s["seq"], []))
    ]
    return {"pending": pending, "dispositions": dispositions}


def voz_at(seq=None, ts=None, log=eventlog.LOG):
    """Leitor fino (padrão *_at da casa): o estado da Voz a partir do log em disco."""
    return fold_voz(eventlog.read(until_seq=seq, until_ts=ts, log=log))


def brief(log=eventlog.LOG, top=5):
    """Seção Voz do briefing (bounded): contagens + top-N one-liners. '' sem pendência."""
    pending = voz_at(log=log)["pending"]
    if not pending:
        return ""
    votes = sum(1 for s in pending if s["act"] == "vote")
    comments = len(pending) - votes
    lines = [f"## Voz pendente — {len(pending)} pendente(s): "
             f"{votes} voto(s), {comments} comentário(s)"]
    for s in pending[:top]:
        gist = (s["text"] or "")[:80] or f"value={s['value']}"
        lines.append(f"- seq {s['seq']} · {s['act']} · {s['target']} · {gist}")
    if len(pending) > top:
        lines.append(f"- … +{len(pending) - top} mais")
    return "\n".join(lines)


def close_cycle(answered=None, log=eventlog.LOG):
    """Dispõe toda a pendência atual no fechamento do beat (process-then-ack).

    Voto → receipt_sent (fecha). Comentário em `answered` ({seq: ref}) →
    semantic_answered(ref). Comentário não respondido → receipt_sent, só se ainda
    não tem recibo — segue pendente pros próximos beats (recibo agora, semântica
    eventualmente). Idempotente: re-run não grava nada novo.
    """
    answered = answered or {}
    state = voz_at(log=log)
    written = []
    for s in state["pending"]:
        seq, prior = s["seq"], state["dispositions"].get(s["seq"], [])
        if seq in answered:
            written.append(dispose(seq, "semantic_answered", ref=answered[seq], log=log))
        elif not any(d.get("state") == "receipt_sent" for d in prior):
            written.append(dispose(seq, "receipt_sent", log=log))
    return written


def assert_all_received(log=eventlog.LOG):
    """O gate mecânico do close: levanta VozUnreceived se alguma Voz pendente não tem
    nem recibo. (Ponto de enforcement em close.py pluga quando a obra do conductor
    assentar — o mecanismo já nasce testado.)"""
    state = voz_at(log=log)
    naked = [s for s in state["pending"] if not state["dispositions"].get(s["seq"])]
    if naked:
        listing = ", ".join(f"seq {s['seq']} ({s['act']} em {s['target']})" for s in naked)
        raise VozUnreceived(f"Voz sem disposição alguma: {listing}")


def dispose(of_seq, state, reason=None, ref=None, log=eventlog.LOG):
    """O ÚNICO escritor de disposição. Fail-loud: estado fora da máquina ou
    dead-letter sem motivo nunca chegam ao log."""
    if state not in STATES:
        raise ValueError(f"estado de disposição desconhecido: {state!r}")
    if state == "dead_lettered" and not (reason or "").strip():
        raise ValueError("dead_lettered exige um motivo")
    payload = {"of": of_seq, "state": state}
    if reason:
        payload["reason"] = reason
    if ref:
        payload["ref"] = ref
    return eventlog.append("voz.disposition", f"voz:{of_seq}", payload, log=log)
