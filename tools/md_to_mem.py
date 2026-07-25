"""md_to_mem — Voz direta em documento, injetada na memória do cortex (issue #130, spec
docs/specs/md-to-mem.md). Genotype tool.

O canal de escrita que faltava: a metade deliberada da memória. O operador injeta um .md curado
(handoff, plano, nota de direção) e ele entra na memória SEM rito/close/review — é Voz, não
produção (I1: injetar tem que ser mais barato que fingir um report). Três peças sobre trilhos
existentes, nenhuma maquinaria nova:

  1. inject barato (este módulo) — 1 comando, segundos, só validação mecânica.
  2. canonicidade = gesto da curadoria de thread (grill_writeback.elect_canon/retire_canon).
  3. relevância na pesquisa = top-K por embedding ao contexto vivo (relevant_docs), degradação
     DECLARADA quando o provider está dark (nunca silenciosa).

O log é a verdade (ADR-0006): o body vive NO evento `doc.injected`; state/docs/<slug>.md é
projeção. Nenhum TTL em lugar nenhum — duração = canônico até o grill des-eleger.
"""
import hashlib
import re
from pathlib import Path

import eventlog

REPO = Path(__file__).resolve().parent.parent
import _identity as _id_state
DOCS_DIR = _id_state.state_root() / "state" / "docs"
CAP_BYTES = 64 * 1024  # cap do body no evento (replay/prune-safe)
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _read_body(path_or_text):
    """Resolve o corpo do doc: um Path (ou str apontando um arquivo existente) é lido; qualquer
    outra str é o texto verbatim. Nunca inventa — texto é texto."""
    if isinstance(path_or_text, Path):
        return path_or_text.read_text()
    if isinstance(path_or_text, str):
        # trate como caminho só um candidato plausível (uma linha, sem cap estourado); um body longo
        # verbatim NUNCA vira um stat de arquivo (Path.exists levanta OSError num nome gigante).
        if "\n" not in path_or_text and len(path_or_text) < 4096:
            try:
                p = Path(path_or_text)
                if p.is_file():
                    return p.read_text()
            except OSError:
                pass
        return path_or_text
    raise ValueError(f"inject espera um Path ou str, recebeu {type(path_or_text).__name__}")


def _live_threads(log):
    """Os ids de thread VIVOS no log (log-nativo): direction items de kind='thread' (set ∪ proposed).
    Ligar só thread que EXISTE — mesma regra do distills, nunca fabricar link (I7/k)."""
    d = eventlog.direction_at(log=log) or {"set": [], "proposed": []}
    return {i["id"] for i in (d.get("set", []) + d.get("proposed", []))
            if i.get("kind") == "thread"}


def inject(path_or_text, slug, threads=None, log=eventlog.LOG, docs_dir=DOCS_DIR):
    """Injeta um .md na memória (issue #130). Valida mecanicamente (slug único entre docs vivos,
    tamanho ≤ 64KB, threads existentes), emite `doc.injected` (body verbatim NO evento), projeta
    state/docs/<slug>.md (projeção, nunca fonte) e projeta o episódio no grafo best-effort (falha
    reportada, NUNCA fatal — padrão do publisher). Retorna o payload do evento.

    Regras duras (spec): NUNCA passa por close/genus/review; thread-ref inexistente RECUSA loud
    (nunca cria); sem ref entra solto de primeira classe; slug já vivo RECUSA apontando doc.retired
    primeiro (simples e explícito, sem versionamento silencioso)."""
    if not (isinstance(slug, str) and SLUG_RE.fullmatch(slug)):
        raise ValueError(f"slug deve casar {SLUG_RE.pattern}, recebeu {slug!r}")
    body = _read_body(path_or_text)
    if not (isinstance(body, str) and body.strip()):
        raise ValueError(f"recusando doc {slug!r} com body vazio/whitespace — Voz oca não injeta")
    if len(body.encode("utf-8")) > CAP_BYTES:
        raise ValueError(f"body de {slug!r} excede o cap de {CAP_BYTES} bytes (64KB) — recusado loud")
    if slug in {d["slug"] for d in eventlog.docs_at(log=log)["live"]}:
        raise ValueError(f"slug {slug!r} já vivo — retire primeiro (doc.retired) e reinjete")
    threads = list(threads or [])
    if threads:
        live = _live_threads(log)
        missing = [t for t in threads if t not in live]
        if missing:
            raise ValueError(f"thread(s) inexistente(s) {missing} — recusa loud, nunca cria "
                             "(sem ref entra solto; a curadoria pendura depois)")
    payload = {"slug": slug, "body": body, "threads": threads,
               "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "author": "operador"}
    eventlog.append("doc.injected", f"doc:{slug}", payload, log=log)
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / f"{slug}.md").write_text(body)
    _project_graph(slug, body, threads, log=log)
    return payload


def docs_for_thread(thread, seq=None, ts=None, log=eventlog.LOG):
    """A via reversa (I7/j, padrão artefatos_for_thread): os slugs de doc vivos pendurados nesta
    thread, do fold. Vazio quando nenhum doc pendura (nunca um link fabricado)."""
    return [d["slug"] for d in eventlog.docs_at(seq=seq, ts=ts, log=log)["live"]
            if thread in (d.get("threads") or [])]


def live_thread_indices(seq=None, ts=None, log=eventlog.LOG):
    """Os docs canônicos das threads VIVAS na Direction (I5): índices que o wake carrega enquanto a
    thread vive. Um doc entra aqui quando (i) está eleito canônico (kind='md'), (ii) pendurado numa
    thread, e (iii) essa thread está viva na Direction. Thread fora da Direction → índice desce sem
    apagar (não aparece aqui; re-eleição/re-abertura o traz)."""
    state = eventlog.docs_at(seq=seq, ts=ts, log=log)
    live_docs = {d["slug"]: d for d in state["live"]}
    canon_md = {c["ref"] for c in state["canon"] if c["kind"] == "md"}
    threads = _live_threads(log)
    out = []
    for slug, d in live_docs.items():
        if slug in canon_md and any(t in threads for t in (d.get("threads") or [])):
            out.append(d)
    return out


def relevant_docs(context, log=eventlog.LOG, embed_fn=None, k=5, seq=None, ts=None):
    """I8 (l,m): STANDING ≠ carregamento. O que sobe é top-K por relevância (cosine do body ao
    contexto vivo), não a lista inteira de canon. Um canon 10× maior não engorda a saída (cap K);
    um doc irrelevante ao contexto não carrega, mas continua elegível.

    `embed_fn(text)->vec` é injetado (mock nos testes; em runtime o embedder OpenAI da sweep). Dark
    (levanta) → RelevanceDegraded: o caller declara a degradação e cai pra thread+recência. Somente
    docs vivos e canônicos (kind='md') entram no pool."""
    state = eventlog.docs_at(seq=seq, ts=ts, log=log)
    canon_md = {c["ref"] for c in state["canon"] if c["kind"] == "md"}
    pool = [d for d in state["live"] if d["slug"] in canon_md]
    if not pool:
        return []
    embed = embed_fn or _openai_embed
    try:
        ctx_vec = embed(context)
        scored = [(eventlog.cosine(embed(d["body"]), ctx_vec), d) for d in pool]
    except Exception as e:  # noqa: BLE001 — provider dark: declarar, nunca silenciar
        raise RelevanceDegraded(str(e))
    # floor de relevância (I8/m): um doc SEM relação semântica ao contexto vivo (cosine ≤ 0) não
    # carrega — um doc da thread A não aparece num wake cujo contexto é só thread B. Standing ≠
    # carregamento: ele continua elegível, só não sobe aqui.
    scored = [sd for sd in scored if sd[0] > 0.0]
    scored.sort(key=lambda sd: sd[0], reverse=True)
    return [d for _s, d in scored[:k]]


class RelevanceDegraded(Exception):
    """O provider de embedding está dark. Levantada por relevant_docs para o caller DECLARAR a
    degradação (fallback thread+recência) — nunca uma degradação silenciosa (spec)."""


def _openai_embed(text):
    """O embedder real: reusa o da sweep (mesma infra dos artefatos, text-embedding-3-small).
    Lazy pra manter o módulo importável em bare python3."""
    import sweep
    return sweep._openai_embed(text)


def graph_episode_payload(slug, body, threads):
    """O payload do episódio que a projeção grafo escreve (S6): provenance_class='asserted' +
    author='operador' — a classe EXISTENTE do axis (cortex_provenance), NÃO um enum novo (spec:
    não-objetivo). Ligeiramente superior à sessão crua (curado-desejado), abaixo do curado-do-grill."""
    return {"slug": slug, "body": body, "threads": list(threads or []),
            "provenance_class": "asserted", "author": "operador"}


def _project_graph(slug, body, threads, log=eventlog.LOG):
    """Projeta o doc como episódio no grafo — best-effort (ADR-0011/0006): o LOG já é a verdade,
    isto é view re-derivável. QUALQUER falha (sem neo4j, grafo down, sem key) IMPRIME e retorna,
    NUNCA levanta no inject (padrão publisher.project_artefato). O próximo beat reprojeta do log."""
    payload = graph_episode_payload(slug, body, threads)
    try:
        import publisher
        publisher.project_doc(payload, log=log)
    except Exception as ex:  # noqa: BLE001 — best-effort; o log já segura a verdade
        print(f"md_to_mem: projeção grafo pulada (best-effort): {type(ex).__name__}: {ex}")


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Injeta um .md na memória do cortex (Voz direta, sem rito/close/review).")
    parser.add_argument("arquivo", help="caminho do .md a injetar (ou texto verbatim)")
    parser.add_argument("--slug", required=True, help="slug único do doc (a-z0-9-)")
    parser.add_argument("--thread", action="append", default=None, dest="threads",
                        help="thread existente a pendurar (cluster:X); repetível; opcional")
    args = parser.parse_args(argv)
    payload = inject(args.arquivo, slug=args.slug, threads=args.threads)
    print(f"injetado: doc:{payload['slug']} (sha256={payload['sha256'][:12]}, "
          f"threads={payload['threads'] or 'solto'})")


if __name__ == "__main__":
    main()
