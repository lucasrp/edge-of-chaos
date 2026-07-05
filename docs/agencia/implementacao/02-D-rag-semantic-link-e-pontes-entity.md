# D — Acordar o semântico + as pontes Entity/Community (o grafo que se mistura)

O gap-map achou D como fiação (relate.py built-sem-caller; embeddings 16/16 dormentes). O operador (2026-07-05, pós-communities-no-roberto) elevou o alvo: **com os nós `:Community` vivos, os artefatos geram relacionamentos MUITO mais ricos via as `:Entity` dos knowledge clusters — "pra tudo se misturar" — e é essa mistura que gera a riqueza de navegabilidade.**

## As 4 vias de navegação (a mistura)
1. **Semântica (o D original):** wire `relate.py` (nominate por cosine → author dispose) + o `MERGE RELATES_TO` faltante → arestas artefato↔artefato. Embeddings já existem (16/16, dim 1536).
2. **Temática via Entity (o NOVO):** artefato-`MENTIONS`->Entity (as entidades que o artefato de fato nomeia — extraível no publish/harvest do próprio texto, casando com as Entity existentes do grafo por nome/uuid) → Entity-`HAS_MEMBER`<-Community → artefatos-irmãos do mesmo cluster. **A ponte artefato↔artefato de 2 hops que já tem substrato vivo** (roberto: 280 Entity, 19 Community).
3. **Estrutural:** mentions/distills/cites (ontologia-cortex-v2 §3).
4. **Julgamento:** gate-metadado navegável (ticket B).

**Navegar = cruzar as vias:** deste artefato → entidades → cluster → irmãos; ou → RELATES_TO direto; ou → o gate-score dos irmãos (qual vale ler). O recall/surf ganha as 4 (RELATES_TO já está no allowlist do SURF_QUERY).

## Guard-rails
- `provenance_class`: RELATES_TO/in_community = `extracted` (hipótese navegável, NUNCA agrega — CX-1); MENTIONS = `asserted` quando extraído do texto publicado (o artefato DE FATO menciona).
- Match artefato-texto→Entity: conservador (nome exato/uuid; sem fuzzy-inventivo — não fabricar menção).
- As 3 camadas do domínio (pesquisa/material/meta — [[communities-loop-roberto-2026-07-05]]): a ponte herda a mistura de níveis; distinguir é trabalho da persona/provenance (#75), não deste ticket.
- Forward-only; sem backfill em massa (o backfill honesto = re-publicações futuras vão ligando).

## Arquivos
`relate.py` (ganha caller no sweep/publish), `publisher.py`/`harvest.py` (extração MENTIONS no publish), `recall.py` (surf pelas novas arestas), `communities.py` (intacto — já provê Entity/Community/HAS_MEMBER).

## O leitor-curador (operador, 2026-07-05): a passada geral cru→contexto→identidade
O padrão do parceiro (nó nasce cru → community dá contexto → promoção dá identidade) vale pra TUDO: **alguém tem que LER os nós — começando pelos MAIORES (grau/tamanho desc, maior retorno primeiro) — e ir atribuindo tipo e relacionamento.** Uma cognição de curadoria periódica (offline, nunca no wake): anda o grafo por importância, lê a Entity crua + vizinhança + episódios, e dispõe — tipo (parceiro/tema/material), arestas que a extração perdeu, promoção extracted→asserted. É o "cosine nominates, author disposes" generalizado; o irmão de leitura da reflexão (a reflexão tuna instrumentos; o curador tuna o GRAFO). provenance: o que o curador atribui = asserted-by-agent, HITL onde a marca carrega autoridade.
**E no SALVAR (operador):** o artefato também cura — no publish, o produtor está com o contexto QUENTE do tema (acabou de derivar/pesquisar): ao gravar MENTIONS, já dispõe tipo/aresta/promoção das entidades que tocou. Curadoria inline no write (barata, contexto pago) + a passada offline pro resto — dois braços do mesmo curador.
