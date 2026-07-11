# Plano — md-to-mem (slices TDD)

Spec: `docs/specs/md-to-mem.md` (interface) + issue #130 (normativa). TDD por slice: teste
vermelho → mínimo verde → refactor. Testes rodam DIRETO (`tools/edge-python tests/test_md_to_mem.py`;
`-m unittest` acha 0). Working-tree only; nenhum commit.

- **S1 — eventos + fold** (`eventlog`): `doc.injected/doc.retired/canon.elected/canon.retired` +
  `docs_at()`. Testes: fold com inject→retire; canon elect→retire; body verbatim preservado;
  cap 64KB recusa loud.
- **S2 — inject** (`tools/md_to_mem.py`): validação (slug único, thread existente, tamanho),
  emissão, projeção `state/docs/`, CLI. Testes: I1, I7 (ref inexistente recusa; sem ref entra
  solto), idempotência de slug (re-inject mesmo slug → recusa ou versiona — decidir: RECUSA com
  mensagem apontando `doc.retired` primeiro; simples e explícito).
- **S3 — canon rail no grill** (`grill_writeback.elect_canon/retire_canon`): açúcar + testes I2,
  I5, I6 (prune de artefato respeita canon — teste vermelho sobre o caminho de prune existente,
  se houver; se não houver prune implementado, teste trava só o fold).
- **S4 — briefing/wake** (`predispatch`/`briefing`): seção Documentos canônicos — índices das
  threads vivas da Direction sempre; demais por relevância top-K. Testes: I5, I8 com embedding
  mockado; degradação declarada com provider dark.
- **S5 — relevância** (fiação embedding): embed do body no inject (mesma infra dos artefatos);
  score = cosine ao contexto vivo (Direction + threads ativas). Testes: I8 (l,m) com vetores
  fixos; dark → fallback thread+recência DECLARADO.
- **S6 — projeção grafo** (best-effort): episódio com provenance_class='asserted' +
  author='operador'; falha reportada nunca fatal. Teste: payload correto; guard do
  cortex_provenance passa.

Ordem: S1→S2→S3→S4 entregam o valor inteiro sem embedding; S5/S6 fecham. Regressões: suíte
existente de eventlog/predispatch/close continua verde.
