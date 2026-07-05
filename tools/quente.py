"""quente — Modulo 1/2 seam: o construtor do insumo do 4º brief do wake (o SENTIR passivo).

Prepara o pacote de DOIS TRILHOS que o leitor-subagente (skills/quente) transforma no brief:
trilho VOZ = prompts do operador verbatim (cap 500c/turno, scaffolding filtrado — E3: vence o
transcript por token) + trilho EXECUTADO = âncoras mecânicas (git log, eventlog — E2: o
executado não passa pelos dedos do operador e nunca vem de prosa de assistente). Janela
ORDINAL-K (E1: últimas K sessões substanciais; wall-clock só como TETO — cadência varia por
install). Pure core aqui; a leitura de disco/git fica em adapters finos no chamador.
Proposta: docs/agencia/proposta-novo-wake.md · grounding: memory/wake-quente-grounding.md.
"""
from datetime import datetime, timedelta, timezone

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


def select_window(store_dir=None, k=3, max_age_days=7, exclude=None):
    """O scan barato de metadata: seleciona as K substanciais do store (ordinal, teto wall-clock)
    e devolve (metas selecionadas, window_start_ts). COMPARTILHADO por build_bundle e pelo
    hot_cutoff do predispatch — uma seleção só, ou o §5 defere pra um quente que não cobre o
    cluster. `store_dir=None` → `_identity.project_dir()` (host-agnóstico, ADR-0015: EDGE_PROJECT_DIR
    → convenção `~/.claude/projects/<$HOME>`). `exclude=None` → CLAUDE_CODE_SESSION_ID (a sessão
    em curso nunca entra na própria janela); passe `()` pra desligar."""
    import os
    from pathlib import Path
    from datetime import datetime, timezone
    if store_dir is None:
        import _identity
        store_dir = _identity.project_dir()
    if exclude is None:
        cur = os.environ.get("CLAUDE_CODE_SESSION_ID")
        exclude = (cur,) if cur else ()
    now_dt = datetime.now(timezone.utc)
    floor_mtime = (now_dt - timedelta(days=max_age_days)).timestamp() if max_age_days else None
    metas = []
    for p in Path(store_dir).glob("*.jsonl"):
        if p.stem in exclude:
            continue
        # mtime >= ts do último evento, então mtime além do teto ⇒ fora da janela de qualquer
        # jeito — o pre-filtro poupa o parse dos arquivos velhos (store real: centenas de MB).
        if floor_mtime is not None and p.stat().st_mtime < floor_mtime:
            continue
        meta, _ = _session_meta_and_turns(p)
        meta["id"] = p.stem
        meta["path"] = p
        metas.append(meta)
    sel = select_sessions(metas, k=k, max_age_days=max_age_days, now=now_dt.isoformat())
    return sel, min((m.get("last", "") for m in sel), default="")


def _eventlog_tail(path=None, n=20):
    """Tail do eventlog (ts · type) — a âncora executada que não passa pelo git. Degrade-honesto:
    indisponível/vazio é DECLARADO, nunca silenciado (o leitor jura 'fato executado vem SÓ das
    âncoras' — codex 7, gate=SINAL)."""
    import json
    from pathlib import Path
    if path is None:
        from eventlog import LOG as path
    try:
        lines = Path(path).read_text().splitlines()[-n:]
    except OSError:
        return "(eventlog indisponível)"
    out = []
    for ln in lines:
        try:
            d = json.loads(ln)
            out.append(f"{d.get('ts', '?')} {d.get('type', '?')}")
        except Exception:
            continue
    return "\n".join(out) or "(eventlog vazio)"


def _user_requested_anchor(path=None, n=5, since=None):
    """Âncora dos artefatos `origin: user_requested` (follow-up 05: consumidores da origem) —
    o pedido do usuário é exatamente onde está a cognição dele AGORA, sinal de pauta de
    primeira ordem; artefatos de beat são exploração e NÃO entram (pesar ≫ = só o gradiente
    ancora). Cada linha carrega o intent.kernel do slug (a pauta legível — slug sozinho não
    diz o pedido; codex #3). `since` = teto wall-clock ISO (o quente envelhece em horas — um
    pedido velho não é AGORA; codex #2). Mais recente primeiro, cap n. Degrade-honesto."""
    import json
    from pathlib import Path
    if path is None:
        from eventlog import LOG as path
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return "(eventlog indisponível)"
    pubs, intents = [], {}
    for ln in lines:
        try:
            d = json.loads(ln)
        except Exception:
            continue
        p = d.get("payload")
        if not isinstance(p, dict):
            continue
        if d.get("type") == "intent.kernel" and p.get("slug"):
            intents[p["slug"]] = p.get("intent", "")
        if d.get("type") == "artefato.published" and p.get("origin") == "user_requested":
            if since is not None and d.get("ts", "") < since:
                continue
            pubs.append((d.get("ts", "?"), p.get("slug", "?")))
    out = [f"{ts} {slug}" + (f" — {intents[slug]}" if intents.get(slug) else "")
           for ts, slug in pubs]
    return "\n".join(reversed(out[-n:])) or "(nenhum artefato user_requested na janela)"


def build_bundle(store_dir=None, repos=(), k=3, max_age_days=7, exclude=None, eventlog_path=None):
    """O insumo completo do quente, do disco: seleciona via select_window (a MESMA seleção do
    hot_cutoff), extrai o trilho-voz, monta as âncoras (git log dos repos + eventlog-tail) e
    devolve (bundle_text, window_start_ts). Defaults host-agnósticos herdados de select_window;
    `eventlog_path=None` → eventlog.LOG. Âncora que falha é marcada dark, nunca afirmada
    ('git indisponível' ≠ '(sem commits)' — codex 8, gate=SINAL)."""
    import subprocess
    sel, window_start = select_window(store_dir=store_dir, k=k, max_age_days=max_age_days,
                                      exclude=exclude)
    sessions = []
    for m in sel:
        _, turns = _session_meta_and_turns(m["path"])
        sessions.append({"id": m["id"][:8], "prompts": operator_prompts(turns)})
    anchors = ""
    for repo in repos:
        try:
            r = subprocess.run(["git", "-C", str(repo), "log", "--oneline",
                                "--since=72 hours ago"], capture_output=True, text=True)
            body = (r.stdout or "(sem commits)") if r.returncode == 0 else \
                f"(git indisponível — rc {r.returncode}; âncora dark, não afirme execução)"
        except OSError:
            body = "(git indisponível — sem binário; âncora dark, não afirme execução)"
        anchors += f"## git log {repo} (72h)\n{body}\n"
    anchors += f"## eventlog (tail)\n{_eventlog_tail(eventlog_path)}\n"
    # o MESMO teto wall-clock da janela (codex #2: pedido velho não é "cognição AGORA")
    since = ((datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
             if max_age_days else None)
    anchors += ("## artefatos user_requested (o pedido do usuário = onde está a cognição dele)\n"
                f"{_user_requested_anchor(eventlog_path, since=since)}\n")
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


def main(argv=None):
    """CLI fino pro wake: imprime o insumo no stdout (`tools/edge-python tools/quente.py >
    insumo.md`). Defaults host-agnósticos: store = _identity.project_dir(), repos = edge_home
    do agent.yaml, exclude = a sessão em curso (CLAUDE_CODE_SESSION_ID)."""
    import argparse
    parser = argparse.ArgumentParser(
        description="quente — monta o insumo de dois trilhos do 4º brief do wake")
    parser.add_argument("--store-dir", default=None,
                        help="store de sessões (default: _identity.project_dir(), host-agnóstico)")
    parser.add_argument("--repos", nargs="*", default=None,
                        help="repos vivos pras âncoras git (default: edge_home do agent.yaml)")
    parser.add_argument("--k", type=int, default=3, help="janela ordinal-K (fenótipo; default 3)")
    parser.add_argument("--max-age-days", type=int, default=7, help="teto wall-clock (default 7)")
    parser.add_argument("--exclude", nargs="*", default=None,
                        help="sessões a pular (default: CLAUDE_CODE_SESSION_ID)")
    args = parser.parse_args(argv)
    repos = args.repos
    if repos is None:
        import _identity
        repos = [_identity.edge_home()]
    bundle, _window_start = build_bundle(
        store_dir=args.store_dir, repos=repos, k=args.k, max_age_days=args.max_age_days,
        exclude=tuple(args.exclude) if args.exclude is not None else None)
    print(bundle)


if __name__ == "__main__":
    main()
