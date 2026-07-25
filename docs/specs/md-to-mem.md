# Spec — md-to-mem: Voz em documento + rail de canonicidade do grill

**Fonte normativa:** issue lucasrp/edge-next#130 (17 pontos + aceitações a–m; em conflito, a issue
manda). Este md fixa as decisões de INTERFACE que a issue deixa abertas.

## Propósito

Canal de injeção deliberada de conteúdo curado pelo operador na memória do cortex — a metade de
escrita que faltava. Substitui a gambiarra fundadora (encomendar um report só para persistir um
assunto). Três peças pequenas sobre trilhos existentes; nenhuma maquinaria nova:

1. **Inject barato** (`tools/md_to_mem.py`) — 1 comando, segundos, sem rito/close/review.
2. **Canonicidade como gesto da curadoria de thread** — eventos `canon.elected/retired` emitidos
   pelos atos que o grill já faz; rail geral (md | artefato | experimento).
3. **Relevância na pesquisa** — eleição dá standing, não carregamento; o que sobe é top-K por
   relevância ao contexto vivo (fiação da busca por embedding já existente, não construção).

## Vocabulário e eventos (log-nativo, ADR-0006)

- `doc.injected` — {slug, body (md verbatim, cap 64KB), threads: [cluster:<label>]|[], sha256,
  author: 'operador'}. O body vive NO evento (replay/prune-safe); arquivo em `state/docs/<slug>.md`
  é projeção, nunca fonte. Thread ref é opcional (SE cabível — solto é primeira classe); ref
  explícita a thread inexistente → recusa loud (nunca criar silenciosamente).
- `doc.retired` — {slug, reason} (o operador pode retirar; log preserva).
- `canon.elected` / `canon.retired` — {kind: 'md'|'artefato'|'experimento', ref, thread?, reason?}.
  Emitidos pelo grill (registro de Direction ou manutenção de thread); NUNCA pelo inject.
- **Sem TTL em lugar nenhum.** Duração = canônico até `canon.retired`; resto ordinal-por-escassez.

## Interfaces (módulos)

- `md_to_mem.inject(path_or_text, slug, threads=None, log=eventlog.LOG) -> dict` — valida
  (tamanho, slug único entre docs vivos, threads existentes via os clusters correntes), emite
  `doc.injected`, projeta `state/docs/`, projeta episódio no grafo best-effort (falha reportada,
  nunca fatal — padrão do publisher) com `provenance_class='asserted'` + `author='operador'`
  (classe EXISTENTE do axis; não estender o enum). CLI: `tools/edge-python tools/md_to_mem.py
  <arquivo.md> [--slug s] [--thread "cluster:X"]...`.
- `eventlog.docs_at(seq=None) -> {'live': [...], 'canon': [...]}` — fold dos eventos acima
  (padrão dos folds existentes: objective_at/direction_at).
- `grill_writeback.elect_canon(kind, ref, thread=None)` / `retire_canon(kind, ref, reason=None)` —
  açúcar sobre append_event; a superfície do grill continua sendo a curadoria de thread.
- `recall/briefing` (fiação): o briefing do predispatch ganha a seção **Documentos canônicos** —
  (i) índices das threads VIVAS na Direction sobem sempre; (ii) o resto do canon + docs vivos
  entra por relevância top-K (default K=5) ao contexto vivo (Direction + threads ativas), via a
  infra de embedding de conteúdo já viva nos artefatos. Provider de embedding dark → degradação
  DECLARADA no briefing (match por thread + recência), nunca silenciosa.

## Invariantes (mapeiam as aceitações da issue)

- I1 (a,i): inject é 1 comando, sem gate além da validação mecânica; segundos.
- I2 (b): grill rebaixa/retira → item sai das janelas SEM apagar (log preserva).
- I3 (c): janela por TIPO — enxurrada de sessões cruas nunca desloca doc curado.
- I4 (d): doc injetado nunca vence fato curado-do-grill em conflito (curado > desejado).
- I5 (e,f): Direction elenca índices → wake seguinte os carrega; thread fora da Direction →
  índice desce sem apagar; re-eleição o traz.
- I6 (g,h): artefato eleito não é prunado nem esfria enquanto eleito; nenhuma duração é
  declarada em inject/publish.
- I7 (j,k): thread-ref válida pendura (duas vias, padrão artefatos_for_thread); inexistente
  recusa; sem ref entra solto de primeira classe.
- I8 (l,m): canon 10× maior não engorda o briefing (top-K por relevância); doc da thread A não
  aparece em wake só-thread-B; consulta tocando A o traz.

## Não-objetivos

- NÃO passar pelo close/genus/reviewers (é Voz, não produção).
- NÃO nova classe no enum provenance_class (usar 'asserted' + author).
- NÃO comando "canon" novo para o operador — a superfície é o grill.
- NÃO reconstruir busca: fiar a dormente; degradação declarada quando dark.
- NÃO tocar o prune de artefatos além do respeito a canon.elected.
