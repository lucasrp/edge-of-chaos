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


# --- adapters (IO fino; o pure core acima é o testado) ---

def _session_meta_and_turns(path):
    """Um passe no jsonl: meta (op_turns/op_chars/last) + turnos (role, texto) já sem tool-noise."""
    import json
    turns, op_turns, op_chars, last = [], 0, 0, ""
    for line in open(path):
        try:
            d = json.loads(line)
        except Exception:
            continue
        t = d.get("type")
        if t not in ("user", "assistant"):
            continue
        ts = d.get("timestamp") or ""
        last = max(last, ts)
        c = d.get("message", {}).get("content")
        txt = c if isinstance(c, str) else "".join(
            b.get("text", "") for b in (c or []) if isinstance(b, dict) and b.get("type") == "text")
        txt = (txt or "").strip()
        if not txt:
            continue
        turns.append((("user" if t == "user" else "assistant"), txt))
        if t == "user" and not any(m in txt[:200] for m in SCAFFOLDING):
            op_turns += 1
            op_chars += len(txt)
    return {"op_turns": op_turns, "op_chars": op_chars, "last": last}, turns


def build_bundle(store_dir, repos=(), k=3, max_age_days=7, exclude=()):
    """O insumo completo do quente, do disco: seleciona as K substanciais do store (ordinal,
    teto wall-clock), extrai o trilho-voz, monta as âncoras (git log dos repos + tail de tipos
    do eventlog se disponível) e devolve (bundle_text, window_start_ts). `exclude` = sessões a
    pular (ex.: a própria sessão em curso)."""
    import subprocess
    from pathlib import Path
    from datetime import datetime, timezone
    store = Path(store_dir)
    metas = []
    for p in store.glob("*.jsonl"):
        if p.stem in exclude:
            continue
        meta, _ = _session_meta_and_turns(p)
        meta["id"] = p.stem
        meta["path"] = p
        metas.append(meta)
    now = datetime.now(timezone.utc).isoformat()
    sel = select_sessions(metas, k=k, max_age_days=max_age_days, now=now)
    sessions = []
    for m in sel:
        _, turns = _session_meta_and_turns(m["path"])
        sessions.append({"id": m["id"][:8], "prompts": operator_prompts(turns)})
    anchors = ""
    for repo in repos:
        out = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "--since=72 hours ago"],
                             capture_output=True, text=True).stdout
        anchors += f"## git log {repo} (72h)\n{out or '(sem commits)'}\n"
    window_start = min((m.get("last", "") for m in sel), default="")
    return build_input(sessions, anchors), window_start


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
