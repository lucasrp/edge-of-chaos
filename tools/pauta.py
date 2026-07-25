"""pauta — o Módulo Pauta (Ato-1): a escolha de pauta ANTES da produção.

Contrato assinado: docs/agencia/pauta-tabela-normativa.md (2026-07-25) · ADR-0024 ·
spec do módulo: memory/spec-pauta-deep-module.md. Cisão do "mirar" do producer: a escolha
vira etapa do DISPATCH, gate de entrada simétrico ao Close. Estado = fold do eventlog
(`pauta.proposta` / `pauta.silencio` / `pauta.veto`), ADR-0006 — nenhum arquivo próprio.

O Seam senta na linha de capacidade (design round1, Variant 2): o TOOL sorteia e julga;
o AGENTE lê o wake e aterra. `sortear()` roda ANTES da leitura do wake (a leitura sai
mirada, §3.1); os passos 2–5 do funil (catálogo → ~12 sugestões → shortlist A → grounding)
são trabalho agêntico do chamador; `propose()` recebe os 2–3 sobreviventes ATERRADOS e
julga/pena — o juízo nunca sai do módulo, e o módulo nunca ingere veredito de agente,
só material (fontes/lastro).

R2 (o funil inteiro): todo juízo é SEMÂNTICO via `completer` (tools/llm_routes.
completer_for na vida real; fake roteirizado nos testes) e `voz_recall_fn` — NUNCA
classificador de keyword/substring. Um critério por chamada de juiz, AND mecânico em
python, trace por-critério com evidência citada (dig round1 #1/#2). Falha de protocolo
do juiz (JSON inválido, veredito sem citação) LEVANTA — infra fail-closed, nunca vira
silêncio de conteúdo. Δ mente NUNCA dentro do gate (§5) — é veredito do operador a
posteriori.

CLI (a porta do beat)::

    tools/edge-python tools/pauta.py sortear [--lock objeto=si ...]
    tools/edge-python tools/pauta.py catalogo --cell JSON
    tools/edge-python tools/pauta.py shortlist --cell JSON --sugestoes JSON [--direction F]
    tools/edge-python tools/pauta.py propose --cell JSON --candidates JSON --dispatch-id ID
    tools/edge-python tools/pauta.py proposta --dispatch-id ID      # a leitura do dente
    tools/edge-python tools/pauta.py veto --dispatch-id ID --reason TXT
    tools/edge-python tools/pauta.py status [--seq N]
"""
import argparse
import json
import random
import sys
from pathlib import Path

import eventlog

# A matriz assinada (§2). `ser` = coringa: desamarra o eixo onde aparece.
OBJETOS = ("mundo", "atividade", "si", "ser")
ABORDAGENS = ("fog", "operacional", "estrategico", "meta_dica",
              "tempo_gasto", "curiosidade", "ser")

PAUTA_TYPES = ["pauta.proposta", "pauta.silencio", "pauta.veto"]

_AXES = (("objeto", OBJETOS), ("abordagem", ABORDAGENS))


def sortear(constraints=None, rng=None):
    """O passo 1 do funil: {objeto, abordagem} independentes, pesos UNIFORMES, ANTES de
    ler o wake (§3.1 — a leitura já sai mirada). PURO: nenhum evento, nenhum estado.

    Voz trava campos: um eixo presente em `constraints` não é sorteado (célula travada
    ainda é célula — o nome carrega o setup). Valor fora da matriz → ValueError (fail
    loud; a ordem veio quebrada). Sem blocklist: célula inviável morre em silêncio no
    propose, nunca a priori — 3 silêncios consecutivos no fold = evidência de poda."""
    c = constraints or {}
    chooser = rng if rng is not None else random.Random()
    cell, locked, propensity = {}, [], 1.0
    for axis, values in _AXES:
        v = c.get(axis)
        if v is not None:
            if v not in values:
                raise ValueError(f"{axis} travado fora da matriz: {v!r} (matriz: {values})")
            cell[axis] = v
            locked.append(axis)
        else:
            cell[axis] = chooser.choice(values)
            propensity *= 1.0 / len(values)
    cell["locked"] = locked
    # p(célula) do sorteio, logada desde o dia 1 (dig round1 #4, racional IPS/Spotify):
    # de graça agora, destrava graduação futura a pesos aprendidos sem cold-start.
    cell["propensity"] = round(propensity, 6)
    return cell


def slug_prefix(cell):
    """`{abordagem}-{objeto}--` — o nome carrega o setup (§3). Install/data entram no
    publish (leitura de _identity lá, nunca literal aqui — genótipo sem identidade)."""
    return f"{cell['abordagem']}-{cell['objeto']}--"


def _cell_ok(cell):
    return (isinstance(cell, dict)
            and cell.get("objeto") in OBJETOS and cell.get("abordagem") in ABORDAGENS)


# ---------------------------------------------------------------------------
# O funil do meio (§3 passos 2–5) + os juízos semânticos (§4/§5)
# ---------------------------------------------------------------------------

# Números do funil — iniciais, calibrar por custo observado (§7).
N_SUGESTOES = 12
N_SHORTLIST = 6
N_ATERRAR = 3

# Catálogo por objeto (§3.2): ONDE o wake mira — nunca um pool de temas (§3.3).
_CATALOGO = {
    "mundo": "sources do agent.yaml e o mundo externo (source keys; X-first para "
             "perguntas de comunidade/prática)",
    "atividade": "conversas do mentee + a obra (sessões, artefatos, runtime dele)",
    "si": "leveling / fog / persona — o estado de fronteira do mentee",
    # §2: objeto=ser → catálogo SEM limite; a exigência fonte-fora-do-circuito é do
    # GATE (§5-ser a), nunca daqui (adv r1 cosmético #2).
    "ser": "livre — o coringa desamarra o catálogo (sem limite de fonte)",
}


def catalogo(cell):
    """O passo 2 do funil: a mira da leitura do wake para a célula sorteada. Devolve
    ONDE olhar (por objeto) e os números do funil — NUNCA temas (pool fixo no repo é
    violação assinada §3.3; as ~12 sugestões são função do wake, trabalho do agente)."""
    if not _cell_ok(cell):
        raise ValueError(f"célula fora da matriz: {cell!r}")
    return {"objeto": cell["objeto"], "abordagem": cell["abordagem"],
            "catalogo": _CATALOGO[cell["objeto"]],
            "n_sugestoes": N_SUGESTOES, "n_shortlist": N_SHORTLIST,
            "n_aterrar": N_ATERRAR}


# Os 7 gates (§5) como DADO-prompt (padrão Weval/Harbor, dig round1 #1): critérios
# FIXOS e nomeados — o juiz nunca inventa subperguntas por rodada. Um critério por
# chamada, AND mecânico. Δ mente NUNCA aqui — é veredito do operador a posteriori.
GATES = {
    "fog": [
        {"id": "a", "exigencia": "lacuna NOMEADA. Âncora em uma das 3 fontes "
         "(declarada / nunca-abordada / vibe-coded) FORTALECE e vai citada no "
         "veredito quando existir — mas ausência de âncora JAMAIS reprova (operador "
         "2026-07-25: wake é insumo, não coleira; a guarda contra lacuna falsa é o "
         "delta_voz reverso — domínio na Voz mata a claim)"},
        {"id": "b", "exigencia": "caminho concreto de vir a saber: primeiro passo "
         "executável + material verificado; entrega em modo afirmação-com-evidência"},
    ],
    "operacional": [  # assinado provisório — revisar (§7)
        {"id": "a", "exigencia": "situação RECORRENTE do dia do mentee, evidenciada no "
         "runtime (>=2 ocorrências na janela ou rotina observada, citada); chore de uma "
         "vez só reprova"},
        {"id": "b", "exigencia": "dica usável na PRÓXIMA ocorrência, zero pré-requisito, "
         "trade-off nomeado"},
        {"id": "c", "exigencia": "mecanismo em 3-5 linhas (por que funciona) — diagnóstico "
         "profundo rebaixado a serviço do porquê, nunca entregável"},
    ],
    "estrategico": [
        {"id": "a", "exigencia": "nomeia a decisão não-tomada (o fork) — SUBSTÂNCIA, "
         "nunca fórmula: lacuna nomeada cujo custo compõe VALE mesmo com o custo "
         "implícito; NUNCA reprove por redação. Âncora na Direction é ADVISORY: se "
         "tocar um fio, cite o id no veredito; um fork genuinamente não-visto pode "
         "ainda NÃO existir na Direction — ausência de âncora JAMAIS reprova "
         "(operador 2026-07-25: o wake é insumo, não coleira)"},
        {"id": "b", "exigencia": "o custo de seguir sem decidir é real e discernível "
         "no material (explícito ou implícito-mas-derivável) — reprove só quando não "
         "há custo algum, nunca porque a frase não tem forma de aposta"},
        {"id": "c", "exigencia": "abre obra ou muda rumo (espelho do zero-pré-requisito "
         "do operacional)"},
    ],
    "meta_dica": [
        {"id": "a", "exigencia": "jeito-de-trabalhar recorrente do mentee, observado e "
         "citado"},
        {"id": "b", "exigencia": "custo do hábito atual evidenciado no runtime — hábito "
         "neutro NÃO é alvo; sem custo citado é opinião de estilo"},
        {"id": "c", "exigencia": "método substituto testável na próxima semana, com "
         "mecanismo + trade-off"},
    ],
    "tempo_gasto": [
        {"id": "a", "exigencia": "mede o sumidouro com dado citado (proxy do session "
         "store vale, afirmado)"},
        {"id": "b", "exigencia": "confronta com prioridade declarada (Direction/objetivo "
         "citado): você diz que A é prioridade; as horas foram pra B"},
        {"id": "c", "exigencia": "realocação explícita: de onde, pra onde, o que ganha, "
         "com trade-off"},
    ],
    "curiosidade": [
        {"id": "a", "exigencia": "pergunta genuína do edge: nomeia o que muda no MODELO "
         "dele (cortex/persona/modelo-de-domínio) com a resposta"},
        {"id": "b", "exigencia": "ponte de volta em UMA linha (declarada, nunca utilidade "
         "provada — exigir prova colapsaria o pólo)"},
    ],
    "ser": [
        {"id": "a", "exigencia": "o desamarrado é real: objeto=ser exige fonte fora do "
         "circuito habitual (checável nas source keys do lastro); abordagem=ser sobre "
         "objeto fixo exige LEITURA de fora; nunca os dois comuns"},
        {"id": "b", "exigencia": "ponte nomeada ao trabalho vivo em uma linha"},
        {"id": "c", "exigencia": "pisos valem inteiros — liberdade de onde/como olhar, "
         "nunca de olhar pra nada nem de recontar"},
    ],
}

_MATERIAL_FIELDS = ("tema", "forma", "faceta", "lastro", "fontes", "substrato_ref",
                    "semente", "evidencia")

# Piso substrato (§4.3) com a nuance fog(a)/vibe-coded (adv r1 #14): log delegado como
# evidência SOBRE o mentee reprova; log delegado como prova de que uma obra vibe-coded
# EXISTE (e o mentee esteve ausente) é exatamente o lastro que a fonte 3 do fog exige.
_SUBSTRATO_INSTRUCAO = (
    "Check de SUBSTRATO (piso universal §4.3): evidência SOBRE o mentee (o que ele "
    "sabe, faz, decide) tem de vir das conversas DELE — reprove candidatos cuja "
    "evidência sobre o mentee é rastro de agente delegado codando. EXCEÇÃO "
    "(§5-fog(a), fonte vibe-coded): logs delegados usados como prova de que uma obra "
    "EXISTE e foi feita sem participação direta do mentee são lastro legítimo — "
    "admita-os; existência-e-ausência é exatamente o que eles provam.")


def _material(cand):
    """Só o MATERIAL bruto do candidato cruza para o juiz — nunca veredito de agente
    (graft V1: o juízo não sai do módulo e o módulo não ingere julgamento alheio)."""
    return {k: cand[k] for k in _MATERIAL_FIELDS if k in cand}


def _lastro_ok(lastro):
    """Piso do lastro (§4.1) por FORMA, nunca truthiness (adv r1 #6): fonte LIDA
    (string não-vazia), seca DECLARADA ({"seca_declarada": razão}) ou
    {"fontes": lista não-vazia}. `lastro=True` morre aqui."""
    if isinstance(lastro, str):
        return bool(lastro.strip())
    if isinstance(lastro, dict):
        if _nonblank(lastro.get("seca_declarada")):
            return True
        fontes = lastro.get("fontes")
        return (isinstance(fontes, list) and bool(fontes)
                and all(isinstance(f, str) and f.strip() for f in fontes))
    return False


def _formas_roster():
    """O roster de producers (§2 Forma) = publisher.PRODUCER_ROSTER ∩ skills instalados
    NESTA árvore (adv r2 #3: o roster autoritativo JÁ existia em publisher.py — re-derivar
    de skills/* inteiro deixava forma="dig" passar o piso e morrer só no Ato-2, a exata
    falha que o piso existe pra matar). Import tardio de dado module-level (tupla, sem
    efeito colateral — verificado no build r3); zero literais de identidade."""
    from publisher import PRODUCER_ROSTER
    skills = Path(__file__).resolve().parent.parent / "skills"
    return {p.parent.name for p in skills.glob("*/SKILL.md")} & set(PRODUCER_ROSTER)


def _nonblank(v):
    return bool(str(v or "").strip())


def _ask(completer, prompt, *, fields, context):
    """O KERNEL do protocolo do juiz (round2 design: um ponto estrito, nunca quatro
    validadores à mão): chama o completer, exige JSON ESTRITO (prosa em volta = juiz
    fora do protocolo — a extração de bloco {...} morreu, dig r2 #5) e valida cada
    campo exigido (`fields`: nome → predicado). Qualquer desvio LEVANTA — é INFRA
    quebrada (fail-closed), nunca vira silêncio de conteúdo."""
    text = (completer(prompt) or "").strip()
    try:
        out = json.loads(text)
    except ValueError:
        out = None
    if not isinstance(out, dict):
        raise ValueError(f"juiz fora do protocolo em {context}: {text[:200]!r}")
    for name, ok in fields.items():
        if name not in out or not ok(out[name]):
            raise ValueError(f"juiz fora do protocolo em {context}: campo {name!r} "
                             f"inválido: {out.get(name)!r}")
    return out


def default_completer():
    """O completer vivo da rota `chat` (tools/llm_routes) — resolvido tarde para os
    testes ficarem offline com fake injetado no seam."""
    import llm_routes
    return llm_routes.completer_for("chat")


def default_voz_recall():
    """O órgão VIVO do recall da Voz (adv r2 #8: um piso que nunca roda é piso só no
    nome). Espelha default_completer: resolvido tarde, injetável nos testes. Embrulha
    recall.semantic_search(tema) (contrato C1: NUNCA levanta; None no escuro) e rende
    os kernels top-K como o texto de recall; rail escuro (sem neo4j/embedder/corpus)
    → None → o ramo declarado `recall_status: "unavailable"` + o alarme do fold —
    infra ausente é modo degradado DECLARADO, nunca juízo fingido."""
    def organ(tema):
        import recall
        hits = recall.semantic_search(tema)
        if hits is None:
            return None
        return "\n".join(
            f"- {h.get('slug')}: {str(h.get('kernel') or '').strip()}" for h in hits)
    return organ


def delta_voz_check(tema, *, voz_recall_fn, completer):
    """O órgão delta_voz (§4.2): a Voz é BASELINE, não blocklist. Recall da Voz no tema
    → UM juízo semântico citando o recall (cite-or-abort: veredito sem citação é
    inválido). Saídas: noop (pousar onde a cabeça já está SEM delta novo) · review
    (incerto) · delta (delta genuíno — redigest com delta novo é o caso BOM).
    `dominio`: guarda reversa — a Voz mostra domínio (uso/decisão assinada, não mera
    menção) e o claim de lacuna morre. Todo veredito carrega `recall_status: "full"`
    (o órgão RODOU — o "unavailable" nasce quando NÃO há órgão ou o órgão devolve
    None, o rail escuro do contrato C1: declarado, nunca fingido; adv r2 #8)."""
    raw = voz_recall_fn(tema)
    if raw is None:
        return {"recall_status": "unavailable",
                "nota": "órgão de recall no escuro (rail/embedder/corpus) — piso "
                        "declarado, não fingido"}
    recall = str(raw).strip()
    if not recall:
        return {"outcome": "delta", "dominio": False, "recall_status": "full",
                "cita": "recall da Voz vazio no tema — baseline sem cobertura"}
    prompt = (
        "Você é o órgão delta_voz da Pauta (Ato-1). A Voz do mentee é a BASELINE, não "
        "blocklist: o candidato compete contra onde a cabeça do mentee JÁ está. Tema "
        "repetido com delta novo é o caso bom (Redigest = pousar onde a cabeça já está "
        "sem delta).\n"
        f"Tema candidato: {tema}\n"
        f"Recall da Voz no tema:\n{recall}\n\n"
        'Responda SÓ JSON: {"outcome": "noop"|"review"|"delta", '
        '"cita": "<trecho literal do recall que fundamenta>", "dominio": true|false}\n'
        "- noop: o candidato pousa onde a cabeça já está SEM delta novo.\n"
        "- review: incerto — deixe passar com flag.\n"
        "- delta: delta genuíno sobre a baseline.\n"
        "- dominio: true SÓ se o recall mostra DOMÍNIO (uso real/decisão assinada), "
        "não mera menção lexical.")
    out = _ask(completer, prompt, context=f"delta_voz({tema!r})",
               fields={"outcome": lambda v: v in ("noop", "review", "delta"),
                       "cita": _nonblank,  # cite-or-abort (dig r1 #6)
                       # adv r2 #5: "dominio": "false" (string) coagia True e a guarda
                       # reversa matava candidato legítimo — bool ESTRITO, como o resto
                       # do protocolo do juiz.
                       "dominio": lambda v: isinstance(v, bool)})
    return {"outcome": out["outcome"], "cita": out["cita"],
            "dominio": out["dominio"], "recall_status": "full"}


def run_gate(cell, cand, *, completer):
    """O gate da abordagem sorteada (§5): UM critério por chamada de juiz sobre o
    material BRUTO do candidato, AND mecânico aqui — nunca rebaixa critério. Devolve
    {passa, abordagem, criterios: [{id, veredito, evidencia}...]} (trace por-critério,
    dig round1 #2)."""
    ab = cell["abordagem"]
    material = json.dumps(_material(cand), ensure_ascii=False)
    criterios = []
    passa = True
    for crit in GATES[ab]:
        prompt = (
            "Você é o gate da Pauta (Ato-1). Julgue UM critério, binário, sobre o "
            "material bruto do candidato — nenhum critério é adjetivo: exige que o "
            "material nomeie/cite/evidencie/proponha.\n"
            f"Célula: abordagem={ab}, objeto={cell['objeto']}.\n"
            f"Critério ({crit['id']}): {crit['exigencia']}\n"
            f"Material do candidato:\n{material}\n\n"
            'Responda SÓ JSON: {"veredito": "passa"|"reprova", '
            '"evidencia": "<citação do material que sustenta o veredito>"}\n'
            "Sem evidência citável no material, reprova — e a evidência do reprovar "
            "nomeia o que faltou (nenhum veredito sem evidência, adv r1 #3).")
        out = _ask(completer, prompt, context=f"gate {ab}/{crit['id']}",
                   fields={"veredito": lambda v: v in ("passa", "reprova"),
                           "evidencia": _nonblank})  # cite-or-abort universal
        criterios.append({"id": crit["id"], "veredito": out["veredito"],
                          "evidencia": str(out["evidencia"]).strip()})
        if out["veredito"] != "passa":
            passa = False
    return {"passa": passa, "abordagem": ab, "criterios": criterios}


def _batch_cut(completer, items, instrucao, context):
    """Um CHECK (um critério) sobre o lote da shortlist: devolve {idx: evidencia} dos
    reprovados. Vetorizado por custo (§7) — segue sendo um critério por chamada.
    FAIL-CLOSED (adv r1 #4): chave `reprova` ausente, entrada não-dict, idx fora do
    range ou evidência vazia = juiz fora do protocolo → levanta, nunca "ninguém
    reprovou" por malformação."""
    material = json.dumps([dict(_material(c), idx=i) for i, c in enumerate(items)],
                          ensure_ascii=False)
    prompt = (f"{instrucao}\n"
              f"Candidatos (material bruto, com idx):\n{material}\n\n"
              'Responda SÓ JSON: {"reprova": [{"idx": <int>, "evidencia": "<citação>"}]} '
              "— liste SÓ os que reprovam neste check; evidência obrigatória.")
    out = _ask(completer, prompt, context=context,
               fields={"reprova": lambda v: isinstance(v, list)})
    cuts = {}
    for r in out["reprova"]:
        if (not isinstance(r, dict)
                or not isinstance(r.get("idx"), int) or isinstance(r.get("idx"), bool)
                or not 0 <= r["idx"] < len(items) or not _nonblank(r.get("evidencia"))):
            raise ValueError(f"juiz fora do protocolo em {context}: corte inválido {r!r}")
        cuts[r["idx"]] = str(r["evidencia"]).strip()
    return cuts


def shortlist(cell, sugestoes, *, completer, voz_recall_fn=None, direction_text="",
              n=N_SHORTLIST):
    """O passo 4 do funil: das ~12 sugestões (função do wake — entram como argumento,
    NUNCA pool do repo) para a shortlist A (~6 = mérito dentro do pólo + 1 slot
    estrutural de serendipidade), com os checks assinados (§3.4): substrato ·
    filtro direction/wayfind-aberto · delta_voz (roda SÓ aqui, §7). Devolve também o
    hook de grounding: 2–3 pontos de dispatch de explorer mirados no pólo (§3.5) —
    o agente aterra; seca declarada é lastro."""
    if not _cell_ok(cell):
        raise ValueError(f"célula fora da matriz: {cell!r}")
    sugs = [dict(s) for s in (sugestoes or []) if isinstance(s, dict)
            and str(s.get("tema") or "").strip()]
    trace = {"n_entrada": len(sugs)}
    if not sugs:
        trace["merito"] = "sem sugestões — nada a julgar (silêncio provável no propose)"
        return {"A": [], "cortados": [], "aterrar": [], "trace": trace}

    cat = catalogo(cell)

    # Mérito dentro do pólo (+ o pick de serendipidade) — um ranking, uma chamada.
    material = json.dumps([dict(_material(s), idx=i) for i, s in enumerate(sugs)],
                          ensure_ascii=False)
    prompt = (
        "Você é a shortlist da Pauta (Ato-1). Ranqueie os candidatos por MÉRITO DENTRO "
        f"DO PÓLO da célula (abordagem={cell['abordagem']}, objeto={cell['objeto']}; "
        f"catálogo do pólo: {cat['catalogo']}). Aponte também o candidato mais "
        "SERENDÍPICO (fora do circuito habitual) para o slot estrutural de "
        "serendipidade.\n"
        f"Candidatos (com idx):\n{material}\n\n"
        'Responda SÓ JSON: {"rank": [<TODOS os idx em ordem de mérito, sem repetição '
        'nem omissão>], "ser": <idx>|null}')
    _idx_ok = lambda i: isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(sugs)  # noqa: E731
    # adv r3 #2 (reproduzido): rank=[] / duplicado / parcial colapsava o pool em
    # SILÊNCIO — todo outro desvio de protocolo levanta. O protocolo é PERMUTAÇÃO
    # plena de range(len(sugs)): o ranking de mérito pedido não tem leitura parcial.
    out = _ask(completer, prompt, context="shortlist/merito",
               fields={"rank": lambda v: (isinstance(v, list)
                                          and all(_idx_ok(i) for i in v)
                                          and sorted(v) == list(range(len(sugs))))})
    rank = out["rank"]
    ser_pick = out.get("ser")
    # adv r2 #6: o slot estrutural é OBRIGATÓRIO com pool não-vazio (§3.4 "+ 1 slot",
    # §7bis-2 audita "sempre presente no A") — ser=null aqui é juiz fora do protocolo
    # (o pool vazio, a única ausência legítima, já retornou declarado lá em cima).
    if not _idx_ok(ser_pick):
        raise ValueError(f"juiz fora do protocolo em shortlist/merito: slot estrutural "
                         f"de serendipidade ausente/inválido com pool não-vazio: "
                         f"ser={ser_pick!r} (§3.4 sempre presente, adv r2 #6)")

    picked = []
    for i in rank:
        if i != ser_pick and i not in picked:
            picked.append(i)
        if len(picked) >= n - 1:
            break
    sugs[ser_pick]["slot"] = "ser"  # o slot estrutural (§3.4)
    picked.append(ser_pick)
    A = [sugs[i] for i in picked]
    trace["merito"] = f"rank sobre {len(sugs)}; A={len(A)} (slot ser: {ser_pick})"

    cortados = []

    def _apply_cut(cuts_by_pos, check_name):
        nonlocal A
        kept = []
        for pos, cand in enumerate(A):
            if pos in cuts_by_pos:
                cand.setdefault("checks", {})[check_name] = {
                    "veredito": "reprova", "evidencia": cuts_by_pos[pos]}
                cortados.append(cand)
                if cand.get("slot") == "ser":
                    # adv r3 #3: §5-ser(c) "pisos valem inteiros" legitima o corte —
                    # mas o A sem slot exige corte DECLARADO, nunca silêncio (§7bis-2
                    # audita presença OU corte declarado). ponytail: declara-e-mede;
                    # re-pick do restante + re-run dos pisos se o dry-run §7bis-2
                    # (~30 sorteios) medir corte frequente.
                    trace["slot_ser"] = (f"cortado por {check_name} "
                                         "(evidência no cortados; tag slot preservada)")
            else:
                cand.setdefault("checks", {})[check_name] = {"veredito": "passa"}
                kept.append(cand)
        A = kept

    # Poda forma-fit (§2 Forma, adv r3 #6): a forma nasce na sugestão; o critério
    # assinado roda AQUI como poda semântica do absurdo — o pen segue julgando só
    # roster-membership (o piso-universal assinado é de três, §4).
    _apply_cut(_batch_cut(
        completer, A,
        "Check de forma_fit (§2 Forma): reprove candidatos cuja forma não serve o "
        "desenvolvimento que o candidato precisa NEM o momento de leitura que a forma "
        "cria — a poda do absurdo (ex.: prototype interativo para um espelho de horas), "
        "nunca preferência de estilo.",
        "shortlist/forma_fit"), "forma_fit")
    trace["forma_fit"] = "rodado"

    # Substrato: ADVISORY (operador 2026-07-25: "o wake é insumo, não coleira" —
    # nenhuma âncora é eliminatória; a agência leu o wake; afastar-se dele é
    # julgamento, não defeito). Roda e REGISTRA no trace; nunca corta.
    _sub_adv = _batch_cut(completer, A, _SUBSTRATO_INSTRUCAO, "shortlist/substrato")
    trace["substrato"] = ("advisory: " + "; ".join(str(v) for v in _sub_adv.values())
                          if _sub_adv else "advisory: sem ressalvas")

    # Filtro direction/wayfind-aberto: Direction/Wayfind não CRIAM pauta — sustentam.
    if str(direction_text or "").strip():
        _apply_cut(_batch_cut(
            completer, A,
            "Check direction/wayfind-aberto: estar aberto/proposto/no frontier organiza "
            "continuidade, não prova valor editorial. Reprove candidatos que SÓ "
            "re-declaram um fio aberto abaixo (sem pauta própria que a Voz sustente).\n"
            f"Fios abertos (Direction/Wayfind):\n{direction_text}",
            "shortlist/wayfind"), "wayfind")
        trace["wayfind"] = "rodado"
    else:
        trace["wayfind"] = "nao-rodado (sem direction_text — declarado, nunca fingido)"

    # delta_voz roda SÓ na shortlist A (§7 custo); noop corta (pousar sem delta novo).
    if voz_recall_fn is not None:
        kept = []
        for cand in A:
            dv = delta_voz_check(cand["tema"], voz_recall_fn=voz_recall_fn,
                                 completer=completer)
            cand["delta_voz"] = dv
            if dv.get("recall_status") == "unavailable":
                kept.append(cand)  # rail escuro: declarado, nunca corta nem finge
            elif dv["outcome"] == "noop":
                cand.setdefault("checks", {})["delta_voz"] = {
                    "veredito": "reprova", "evidencia": dv["cita"]}
                cortados.append(cand)
                if cand.get("slot") == "ser":
                    trace["slot_ser"] = ("cortado por delta_voz (evidência no "
                                         "cortados; tag slot preservada)")
            else:
                kept.append(cand)
        A = kept
        trace["delta_voz"] = "rodado na A"
    else:
        trace["delta_voz"] = "nao-rodado (sem voz_recall_fn — declarado no propose)"

    # O hook de grounding (§3.5): 2–3 pontos de dispatch de explorer, mirados no pólo.
    aterrar = [{"tema": c["tema"], "forma": c.get("forma"),
                "explorer": (f"aterra '{c['tema']}' mirado no pólo "
                             f"{cell['objeto']}: {cat['catalogo']} — seca declarada "
                             "é lastro (§3.5)")}
               for c in A[:N_ATERRAR]]
    return {"A": A, "cortados": cortados, "aterrar": aterrar, "trace": trace}


def propose(cell, candidates, *, dispatch_id, constraints=None,
            completer=None, voz_recall_fn=None, log=eventlog.LOG):
    """O passo 6 do funil: julga os sobreviventes aterrados e pena a verdade no log —
    `pauta.proposta` (1) ou `pauta.silencio` (0, com a célula no payload — §6 precisa).
    Retorna o evento estampado.

    A FRONTEIRA DE CONFIANÇA senta AQUI (round2 design, dig r2 #1: "the evidence gets
    the only vote"): qualquer campo-veredito que venha montado no candidato (checks,
    delta_voz, qualquer coisa fora de `_MATERIAL_FIELDS`) é DESCARTADO no ingresso —
    as anotações da shortlist são trace consultivo, nunca fluxo de controle. propose
    SEMPRE re-julga os pisos sobre o material bruto dos 2–3 sobreviventes (custo:
    ~meia dúzia de chamadas; a otimização "honra a anotação" ERA a brecha, adv r1 #1).

    `candidates`: lista de {tema, forma, faceta?, lastro, fontes?, ...} — os aterrados
    que o AGENTE colheu pelo funil. `lastro` valida por FORMA (`_lastro_ok`): fonte
    lida | {"seca_declarada": razão} | {"fontes": [...]}. `forma` tem de estar no
    roster do install (skills/*/SKILL.md) — o piso aqui é SÓ membership; o juízo
    forma-fit (§2: desenvolvimento + momento de leitura) roda na shortlist como
    poda semântica, nunca no pen (adv r3 #6; o piso-universal assinado é de três, §4).

    Caminho autônomo (R2): por candidato, na ordem — pisos mecânicos (lastro, forma
    no roster) → piso substrato (RE-julgado aqui, nuance vibe-coded §4.3) → piso
    delta_voz (computado via `voz_recall_fn`, ou DECLARADO indisponível com
    `recall_status: "unavailable"` — o fold alarma a taxa; noop corta; guarda reversa
    §4.2: domínio na Voz mata claim de lacuna do fog) → gate da abordagem (`run_gate`:
    um critério por juiz, AND mecânico, Δ mente NUNCA dentro). Primeiro que passa TUDO
    vence. Nenhum → silêncio LOGADO com `reason_kind` ("processo" = funil seco |
    "editorial" = juízo reprovou), nunca raise-and-wait (lei do risco). Falha do juiz
    LEVANTA (infra fail-closed via `_ask`), nunca silêncio de conteúdo.

    Caminho Voz (constraints origem="voz"): a AUTORIDADE DERIVA DO LOG, nunca do JSON
    (adv r2 #1: autoridade que pode ser alegada será forjada — reproduzido; mesmo
    precedente do publisher, que deriva origin do fold e recusa a palavra do caller).
    Exige um `dispatch.open` com origin=user_requested para ESTE dispatch_id
    (eventlog.dispatch_origin — a trilha comandada da predispatch pena esse evento);
    origem="voz" num dispatch de heartbeat/desconhecido → ValueError (ordem FORJADA,
    classe fail-loud, nunca silêncio editorial). Com a autoridade provada: a palavra
    do operador é PROPOSTA-ok — NENHUM juízo LLM roda; o recibo break-glass (dig r2
    #3) vai no `gate_trace.waived`. Campos travados (tema/forma) vencem o candidato;
    com tema travado só candidato do MESMO tema empresta lastro/faceta (adv r2 #4:
    evidência de X nunca cavalga proposta Y) — sem irmão do tema, seca declarada.
    Lastro inválido/seco NORMALIZA para seca declarada (autoridade nunca bloqueia);
    contra ordem NUNCA há silêncio. Ordem sem tema nem candidato viável, célula
    corrupta ou forma fora do roster → ValueError (ordem quebrada)."""
    if not isinstance(dispatch_id, str) or not dispatch_id.strip():
        raise ValueError("dispatch_id deve ser string não-vazia")
    dispatch_id = dispatch_id.strip()
    c = constraints or {}
    voz = c.get("origem") == "voz"
    if voz and eventlog.dispatch_origin(dispatch_id, log=log) != "user_requested":
        raise ValueError(
            f"origem='voz' sem dispatch comandado no log para {dispatch_id!r}: a "
            "autoridade deriva do dispatch.open origin=user_requested (o log é a "
            "verdade, ADR-0006) — prosa/JSON nunca confere autoridade (adv r2 #1)")

    if not _cell_ok(cell):
        if voz:
            raise ValueError(f"célula fora da matriz num caminho comandado: {cell!r}")
        return eventlog.append("pauta.silencio", "pauta", {
            "objeto": (cell or {}).get("objeto") if isinstance(cell, dict) else None,
            "abordagem": (cell or {}).get("abordagem") if isinstance(cell, dict) else None,
            "dispatch_id": dispatch_id, "origem": "autonomo", "reason_kind": "processo",
            "reason": f"célula fora da matriz: {cell!r}"}, log=log)

    # O INGRESSO da fronteira de confiança: só material bruto entra — carimbos de
    # veredito (checks/delta_voz/...) que viajaram pelo agente morrem aqui (adv r1 #1).
    cands = [_material(x) for x in (candidates or []) if isinstance(x, dict)]

    def _pen_proposta(tema, forma, lastro, winner, gate_trace, dv):
        seca = isinstance(lastro, dict) and "seca_declarada" in lastro
        gate_trace["floors"]["lastro"] = "seca_declarada" if seca else "ok"
        if cell["objeto"] == "ser" and cell["abordagem"] != "ser":
            # Tag curta + ponteiro (r3 cosmético): a leitura vinculante mora na spec.
            gate_trace["ser_desamarrado"] = (
                "liberdade de catálogo, sem critério extra — spec §2×§5-ser(a), "
                "leitura vinculante 2026-07-25")
        payload = {
            "abordagem": cell["abordagem"], "objeto": cell["objeto"],
            "forma": forma, "tema": tema,
            "faceta": (winner or {}).get("faceta") or c.get("faceta"),
            "lastro": lastro,
            "gate_trace": gate_trace,
            "delta_voz": dv,
            "origem": "voz" if voz else "autonomo",
            "depth": c.get("depth") or "brief",
            "dispatch_id": dispatch_id,
            "slug_prefix": slug_prefix(cell),
        }
        if "propensity" in (cell or {}):
            payload["propensity"] = cell["propensity"]  # dig round1 #4
        return eventlog.append("pauta.proposta", "pauta", payload, log=log)

    if voz:
        # Autoridade: nenhum juízo LLM — a palavra é PROPOSTA-ok. Winner: com tema
        # TRAVADO só irmão do MESMO tema entra no pool (adv r2 #4: lastro de X nunca
        # pena sob proposta Y — igualdade mecânica de campo; o juízo semântico já
        # rodou rio acima sob o tema travado); o irmão COM lastro válido vence o
        # seco (adv r1 cosmético #1); campos travados vencem tudo.
        tema_lock = str(c.get("tema") or "").strip()
        pool = ([x for x in cands if str(x.get("tema") or "").strip() == tema_lock]
                if tema_lock else [x for x in cands if _nonblank(x.get("tema"))])
        winner = next((x for x in pool if _lastro_ok(x.get("lastro"))),
                      pool[0] if pool else None)
        tema = tema_lock or str((winner or {}).get("tema") or "").strip()
        forma = str(c.get("forma") or (winner or {}).get("forma") or "").strip()
        if not tema or not forma:
            raise ValueError("caminho comandado sem tema/forma resolvíveis "
                             "(nem constraints nem candidato) — ordem quebrada")
        if forma not in _formas_roster():
            raise ValueError(f"caminho comandado nomeia producer fora do roster: "
                             f"{forma!r} — ordem quebrada (adv r1 #7)")
        lastro = (winner or {}).get("lastro")
        if not _lastro_ok(lastro):
            lastro = {"seca_declarada": "grounding seco/lastro inválido no caminho "
                      "comandado — a palavra do operador é PROPOSTA-ok por "
                      "autoridade (§1); autoridade nunca bloqueia"}
        gate_trace = {
            "floors": {
                "delta_voz": "modo-declara (autoridade — citado, nunca veta)",
                "substrato": "modo-declara (autoridade — citado, nunca veta)",
            },
            "gate_abordagem": "autoridade-voz (PROPOSTA-ok pela palavra do operador; "
                              "pisos em modo-declara)",
            # O recibo break-glass (dig r2 #3): a PROPOSTA-por-autoridade lista
            # EXATAMENTE o que não rodou e por quê — waive por ordem, nunca flag.
            "waived": [
                {"check": "substrato",
                 "reason": "autoridade da ordem — piso não rodou (§1)"},
                {"check": "delta_voz",
                 "reason": "autoridade da ordem — piso não rodou (§1)"},
                {"check": f"gate {cell['abordagem']}",
                 "reason": "autoridade da ordem — a palavra do operador é "
                           "PROPOSTA-ok (§1)"},
            ],
        }
        # adv r3 #4 (resíduo bounded): os campos travados são a palavra do agente-
        # relay. Eco MECÂNICO (zero LLM, zero bloqueio) do que o dispatch.open
        # cunhado carrega (pedido/intent/theme) — a palavra verbatim do operador
        # cavalga a PROPOSTA, auditável. A estampa do pedido na predispatch é
        # fiação de outro rail (ticket nomeado no build r4), não desta região.
        stamped = next((e["payload"] for e in
                        eventlog.read(types=["dispatch.open"], log=log)
                        if isinstance(e.get("payload"), dict)
                        and e["payload"].get("dispatch_id") == dispatch_id), {})
        gate_trace["pedido_stamped"] = next(
            (str(stamped[k]).strip() for k in ("pedido", "intent", "theme")
             if _nonblank(stamped.get(k))),
            "não-estampado (fiação predispatch pendente)")
        return _pen_proposta(tema, forma, lastro, winner, gate_trace, None)

    # ---- caminho autônomo (R2): pisos + gate, primeiro que passa TUDO vence ----
    roster = _formas_roster()
    viaveis = [x for x in cands
               if _nonblank(x.get("tema")) and _nonblank(x.get("forma"))
               and x["forma"] in roster and _lastro_ok(x.get("lastro"))]
    if not viaveis:
        reason = ("sem candidatos" if not cands else
                  f"nenhum dos {len(cands)} candidatos passou o piso mecânico "
                  "(tema + forma no roster + lastro por forma; seca declarada é lastro)")
        return eventlog.append("pauta.silencio", "pauta", {
            "objeto": cell["objeto"], "abordagem": cell["abordagem"],
            "dispatch_id": dispatch_id, "origem": "autonomo",
            "reason_kind": "processo", "reason": reason}, log=log)

    judge = completer if completer is not None else default_completer()
    por_candidato = []
    for cand in viaveis:
        floors = {}
        # Piso substrato: SEMPRE re-julgado aqui do material bruto (adv r1 #1 — a
        # anotação da shortlist viajou pelo agente; a evidência tem o único voto).
        cuts = _batch_cut(judge, [cand], _SUBSTRATO_INSTRUCAO, "propose/substrato")
        # ADVISORY (operador 2026-07-25: nenhuma âncora elimina — wake é insumo,
        # não coleira). A ressalva vai no trace; o candidato segue.
        floors["substrato"] = ({"veredito": "ressalva", "evidencia": cuts[0]}
                               if 0 in cuts else {"veredito": "passa"})
        # Piso delta_voz: computado via voz_recall_fn (organ ausente OU rail escuro
        # devolvendo None → DECLARADO indisponível) — nunca fingido, nunca anotação
        # de agente. recall_status alimenta o alarme do fold (dig r2 #7: "downtime
        # always looks novel" se não for contado).
        dv = None
        if voz_recall_fn is not None:
            dv = delta_voz_check(cand["tema"], voz_recall_fn=voz_recall_fn,
                                 completer=judge)
        if dv is None:
            dv = {"recall_status": "unavailable",
                  "nota": "recall da Voz indisponível — piso declarado, não fingido"}
        floors["delta_voz"] = dv
        if dv.get("recall_status") != "unavailable":
            if dv.get("outcome") == "noop":
                por_candidato.append({"tema": cand.get("tema"),
                                      "morreu": "delta_voz noop (redigest sem delta novo)",
                                      "evidencia": dv.get("cita")})
                continue
            # Guarda reversa (§4.2): a Voz mostra DOMÍNIO → claim de lacuna morre.
            if dv.get("dominio") and cell["abordagem"] == "fog":
                por_candidato.append({"tema": cand.get("tema"),
                                      "morreu": "guarda reversa (domínio na Voz mata "
                                                "claim de lacuna)",
                                      "evidencia": dv.get("cita")})
                continue
        # O gate da abordagem (§5) — AND mecânico, nunca rebaixa critério.
        gate = run_gate(cell, cand, completer=judge)
        if gate["passa"]:
            gate_trace = {"floors": floors, "gate_abordagem": gate}
            return _pen_proposta(cand["tema"], cand["forma"], cand["lastro"],
                                 cand, gate_trace, dv)
        por_candidato.append({"tema": cand.get("tema"), "morreu": "gate da abordagem",
                              "criterios": gate["criterios"]})

    return eventlog.append("pauta.silencio", "pauta", {
        "objeto": cell["objeto"], "abordagem": cell["abordagem"],
        "dispatch_id": dispatch_id, "origem": "autonomo",
        "reason_kind": "editorial",
        "reason": (f"nenhum dos {len(viaveis)} candidatos aterrados passou "
                   "pisos+gate (AND — nunca rebaixa critério)"),
        "por_candidato": por_candidato}, log=log)


def veto(dispatch_id, reason, log=eventlog.LOG):
    """A caneta do veto do operador: mata a PROPOSTA viva deste dispatch (o dente passa
    a ler None). Razão obrigatória — veto sem palavra não realimenta a baseline."""
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("veto exige razão não-vazia (a palavra realimenta a baseline)")
    return eventlog.append("pauta.veto", "pauta", {
        "dispatch_id": str(dispatch_id).strip(), "reason": reason.strip()}, log=log)


def proposta_for(dispatch_id, log=eventlog.LOG):
    """A leitura do DENTE (ADR-0024): a pauta.proposta VIVA (não vetada) deste dispatch,
    ou None. Ato-2 toma producer = proposta['forma'] — fiado em `_beat.dispatch_plan`
    (a estrada velha pool-fixo/cursor morreu naquele commit; commit-to-remove).
    Um pauta.silencio POSTERIOR não mata a proposta — o veto é a única caneta de morte
    (§1; by-design, adv r1 cosmético #8).

    Round 4 (adv r3 #1, Variant A): o log é append-only, não append-autenticado — a
    verificação READ-side mora AQUI, uma vez, e todo leitor herda (require_proposta,
    dispatch_plan, dente, CLI, publish futuro). A proposta VIVA levanta ValueError
    (evento forjado/legado — classe protocolo-quebrado) quando:
      * alega `origem: "voz"` sem `dispatch.open` origin=user_requested no log
        (autoridade deriva do log, nunca do payload — adv r2 #1/r3 #1);
      * carrega `forma` fora do roster do install (o plano nunca nomeia producer
        que o install não roda — adv r2 #3).
    Recuperação documentada: `pauta.veto` mata a forjada e o fold volta a None —
    nunca brick. A verificação roda SÓ na proposta viva (forjada+vetada = None
    quieto); o evento cru segue VISÍVEL nos folds de auditoria (§6/voz_authority)."""
    live = None
    for e in eventlog.read(types=PAUTA_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if p.get("dispatch_id") != dispatch_id:
            continue
        if e["type"] == "pauta.proposta":
            live = dict(p, seq=e["seq"])
        elif e["type"] == "pauta.veto":
            live = None
    if live is not None:
        if (live.get("origem") == "voz"
                and eventlog.dispatch_origin(dispatch_id, log=log) != "user_requested"):
            raise ValueError(
                f"pauta.proposta forjada no log: origem='voz' sem dispatch.open "
                f"origin=user_requested para {dispatch_id!r} — a autoridade deriva do "
                "log, nunca do payload (adv r3 #1; recuperação: pauta.py veto)")
        if live.get("forma") not in _formas_roster():
            raise ValueError(
                f"pauta.proposta forjada/legada no log: forma {live.get('forma')!r} "
                f"fora do roster de producers para {dispatch_id!r} — o plano nunca "
                "nomeia producer que o install não roda (adv r2 #3; recuperação: "
                "pauta.py veto)")
    return live


def latest_pauta_state(dispatch_id, log=eventlog.LOG):
    """O ÚLTIMO evento pauta.* deste dispatch — replay até a cabeça, a MESMA disciplina
    de fold do proposta_for (dig r2 #2: nunca "algum silêncio histórico"; adv r1 #9).
    Devolve "proposta" | "silencio" | "veto" | None. O consumidor canônico é o
    post-gate do _beat: silêncio só exime se for o estado MAIS RECENTE."""
    state = None
    for e in eventlog.read(types=PAUTA_TYPES, log=log):
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        if p.get("dispatch_id") == dispatch_id:
            state = e["type"].split(".", 1)[1]
    return state


def require_proposta(dispatch_id, log=eventlog.LOG):
    """O DENTE: sem pauta.proposta viva, Ato-2 não abre — uniforme autônomo/comandado."""
    p = proposta_for(dispatch_id, log=log)
    if p is None:
        raise RuntimeError(
            f"o dente: sem pauta.proposta viva para dispatch {dispatch_id!r} — "
            "Ato-2 não abre (ADR-0024; rode tools/pauta.py sortear → propose antes)")
    return p


def fold_pauta(events):
    """Fold puro de pauta.* (§6): distribuição realizada por célula vs uniforme
    (falsificador de ato1-multi-setup-vs-centro), silêncios CONSECUTIVOS por célula
    (3+ = candidata a poda, por evidência), vetos, e os dois contadores de honestidade
    do round2: `recall_unavailable` (propostas cujo piso delta_voz rodou SEM órgão de
    recall — o alarme do dig r2 #7) e `voz_authority` (propostas por autoridade da
    Voz, o recibo agregado do break-glass, dig r2 #3)."""
    cells, streaks, vetoes = {}, {}, 0
    recall_unavailable = voz_authority = 0
    for e in events:
        p = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        t = e.get("type")
        if t == "pauta.veto":
            vetoes += 1
            continue
        key = f"{p.get('abordagem')}-{p.get('objeto')}"
        cell = cells.setdefault(key, {"proposta": 0, "silencio": 0})
        if t == "pauta.proposta":
            cell["proposta"] += 1
            streaks.pop(key, None)
            if p.get("origem") == "voz":
                voz_authority += 1
            dv = ((p.get("gate_trace") or {}).get("floors") or {}).get("delta_voz")
            if isinstance(dv, dict) and dv.get("recall_status") == "unavailable":
                recall_unavailable += 1
        elif t == "pauta.silencio":
            cell["silencio"] += 1
            streaks[key] = streaks.get(key, 0) + 1
    return {"cells": cells,
            "silence_streaks": streaks,
            "poda_candidates": [k for k, v in streaks.items() if v >= 3],
            "vetoes": vetoes,
            "recall_unavailable": recall_unavailable,
            "voz_authority": voz_authority}


def pauta_at(seq=None, ts=None, log=eventlog.LOG):
    """O estado da Pauta num cursor — replay puro do log (ADR-0006)."""
    return fold_pauta(eventlog.read(types=PAUTA_TYPES, until_seq=seq, until_ts=ts, log=log))


def _cli_direction_text(arg, base=None):
    """--direction do CLI: caminho explícito lê o arquivo; '' opta fora ALTO (o trace
    da shortlist declara nao-rodado); None (omitido) → default assinado §3.4:
    state/direction.md DESTE install quando existe (adv r2 #11: a estrada default
    rodava um check assinado NUNCA)."""
    if arg == "":
        return ""
    if arg:
        return Path(arg).read_text()
    default = Path(base or Path(__file__).resolve().parent.parent) / "state" / "direction.md"
    return default.read_text() if default.exists() else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pauta (Ato-1) — sorteio, proposta, dente, fold")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sortear")
    s.add_argument("--lock", action="append", default=[], metavar="EIXO=VALOR")
    cat = sub.add_parser("catalogo")
    cat.add_argument("--cell", required=True, help="JSON {objeto, abordagem}")
    sl = sub.add_parser("shortlist")
    sl.add_argument("--cell", required=True, help="JSON {objeto, abordagem}")
    sl.add_argument("--sugestoes", required=True,
                    help="JSON [~12 {tema, forma, semente}] — função do wake, nunca pool")
    sl.add_argument("--direction", default=None,
                    help="arquivo com os fios abertos p/ o filtro wayfind; default: "
                         "state/direction.md do install quando existe; '' opta fora")
    p = sub.add_parser("propose")
    p.add_argument("--cell", required=True, help="JSON {objeto, abordagem}")
    p.add_argument("--candidates", default="[]", help="JSON [{tema, forma, faceta, lastro, ...}]")
    p.add_argument("--constraints", default="{}", help="JSON (Voz: origem/tema/forma/depth)")
    p.add_argument("--dispatch-id", required=True)
    d = sub.add_parser("proposta")
    d.add_argument("--dispatch-id", required=True)
    v = sub.add_parser("veto")
    v.add_argument("--dispatch-id", required=True)
    v.add_argument("--reason", required=True)
    st = sub.add_parser("status")
    st.add_argument("--seq", type=int, default=None)
    args = ap.parse_args(argv)

    if args.cmd == "sortear":
        locks = dict(kv.split("=", 1) for kv in args.lock)
        out = sortear(locks or None)
    elif args.cmd == "catalogo":
        out = catalogo(json.loads(args.cell))
    elif args.cmd == "shortlist":
        out = shortlist(json.loads(args.cell), json.loads(args.sugestoes),
                        completer=default_completer(),
                        voz_recall_fn=default_voz_recall(),
                        direction_text=_cli_direction_text(args.direction))
    elif args.cmd == "propose":
        out = propose(json.loads(args.cell), json.loads(args.candidates),
                      dispatch_id=args.dispatch_id,
                      constraints=json.loads(args.constraints),
                      voz_recall_fn=default_voz_recall())
    elif args.cmd == "proposta":
        out = proposta_for(args.dispatch_id)
    elif args.cmd == "veto":
        out = veto(args.dispatch_id, args.reason)
    else:
        out = pauta_at(seq=args.seq)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return out


if __name__ == "__main__":
    main()
