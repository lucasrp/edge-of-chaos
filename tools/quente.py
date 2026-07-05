"""quente — Modulo 1/2 seam: o construtor do insumo do 4º brief do wake (o SENTIR passivo).

Prepara o pacote de DOIS TRILHOS que o leitor-subagente (skills/quente) transforma no brief:
trilho VOZ = prompts do operador verbatim (cap 500c/turno, scaffolding filtrado — E3: vence o
transcript por token) + trilho EXECUTADO = âncoras mecânicas (git log, eventlog — E2: o
executado não passa pelos dedos do operador e nunca vem de prosa de assistente). Janela
ORDINAL-K (E1: últimas K sessões substanciais; wall-clock só como TETO — cadência varia por
install). Pure core aqui; a leitura de disco/git fica em adapters finos no chamador.
Proposta: docs/agencia/proposta-novo-wake.md · grounding: memory/wake-quente-grounding.md.
"""
from datetime import datetime, timedelta

SCAFFOLDING = ("<system-reminder>", "<task-notification>", "<command-name>",
               "heartbeat keep-warm", "<local-command")


def is_substantial(meta):
    """E1 (validada ~95% vs rótulo manual): sessão de discussão real do operador."""
    return meta.get("op_turns", 0) >= 5 and meta.get("op_chars", 0) >= 1000


def select_sessions(metas, k=3, max_age_days=None, now=None):
    """Ordinal-K: as K sessões SUBSTANCIAIS mais recentes; wall-clock é teto, não régua
    (max_age_days corta o que passou do teto mesmo com K sobrando)."""
    subs = [m for m in metas if is_substantial(m)]
    if max_age_days is not None and now is not None:
        cutoff = (datetime.fromisoformat(now.replace("Z", "+00:00"))
                  - timedelta(days=max_age_days)).isoformat()
        subs = [m for m in subs if m.get("last", "").replace("Z", "+00:00") >= cutoff]
    return sorted(subs, key=lambda m: m.get("last", ""), reverse=True)[:k]


def operator_prompts(turns, cap=500):
    """Trilho VOZ: os turnos digitados do operador, verbatim com cap — scaffolding injetado
    pelo harness fora (o desenho do edge-feedback-digest, agora COM leitor no wake)."""
    out = []
    for role, text in turns:
        if role != "user":
            continue
        t = (text or "").strip()
        if not t or any(m in t[:200] for m in SCAFFOLDING):
            continue
        out.append(t[:cap])
    return out


def build_input(sessions, anchors):
    """Monta o pacote de dois trilhos que o leitor recebe. `sessions` = [{id, prompts}] já
    selecionadas/extraídas (mais recente primeiro); `anchors` = o texto das âncoras mecânicas
    (git log + eventlog), montado pelo chamador. Nenhuma prosa nossa entra — só fonte."""
    parts = ["# INSUMO DO QUENTE — dois trilhos (voz + executado)",
             "\n## TRILHO VOZ — prompts do operador, verbatim, mais recente primeiro"]
    for s in sessions:
        parts.append(f"\n### Sessão {s['id']} ({len(s.get('prompts', []))} turnos)")
        parts.extend(f"- {p}" for p in s.get("prompts", []))
    parts.append("\n## TRILHO EXECUTADO — ÂNCORAS MECÂNICAS (git/eventlog; fatos, não conversa)")
    parts.append(anchors or "_(âncoras indisponíveis — declare no brief)_")
    return "\n".join(parts)
