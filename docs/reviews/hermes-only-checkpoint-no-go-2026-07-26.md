# Checkpoint Hermes-only — relatório de Gate NO-GO

**Data:** 2026-07-26
**Destinatário:** Lucas
**Status:** WIP / revisão técnica reprovada / não autorizado para merge ou operação

## Identidade do checkpoint

- Branch local: `feat/hermes-only`
- Base da derivação: `88828cbfb6a8eae81e6d2d0fbb70b0c528d3a87c`
- Commit WIP do código: `e535023fc2edb3df9b8802f4732cb47b0080c338`
- Manifesto portátil do snapshot de implementação antes deste relatório:
  `daddbb06c647b232e1b99c8be932d1c623214f1bf638ac08d04b2b9a7fb5ef22`
- `origin/main` observado durante o fechamento: `991fc7455492564243ce8186359ba4d01591a937`

O checkpoint preserva o hardening parcial sem rebasear ou incorporar silenciosamente o delta posterior do upstream. A análise de `991fc745` deve ocorrer separadamente.

## Objetivo do trabalho

Derivar uma variante estritamente Hermes-only do Edge of Chaos:

- Hermes como único harness público;
- completion pública exclusivamente via Hermes;
- seleção de provider/modelo de completion mantida dentro do Hermes;
- `HERMES_HOME` dedicado, sem uso do profile global;
- embedding em rota separada, explicitamente configurada;
- readers sem implementação Hermes-native mantidos dark;
- heartbeat, dogfood e runtime autônomo mantidos dark;
- adapters legados somente privados;
- bloqueio antes de secrets, filesystem, locks, subprocessos ou provisionamento.

## Avanço preservado

O checkpoint adiciona uma política central Hermes-only e endurece caminhos nominais de:

- seleção de harness e surfaces;
- completion e embedding;
- provisionamento de profile Hermes;
- onboarding e apply;
- readers públicos principais;
- heartbeat e dogfood;
- documentação e skills selecionadas;
- testes de política e de ordem fail-closed.

Também corrige a aceitação de seções malformadas como `surfaces: []`, `routers: []` e `heartbeat: []`.

## Evidências positivas

### Regressão focada Linux

```text
Bateria principal: 110/110
Bateria effectful/identidade: 61/61
Total focado: 171/171
```

### Smoke e verificações complementares

- Smoke canônico: `65/65`.
- Probes nominais fail-closed: `5/5`.
- Efeitos temporários observados nos probes: `[]`.
- Fuzz de seções malformadas: `17/17` bloqueadas.
- `git diff --check`: verde antes do commit.
- Bandit baseline-aware: zero achados novos médios ou altos.
- Ruff: zero erros fatais e zero regras de segurança novas.
- Literais de credenciais encontrados no delta: zero.

Esses resultados demonstram que os caminhos cobertos estão protegidos, mas não demonstram conformidade Hermes-only de ponta a ponta.

## Suíte integral

A suíte integral não está verde:

```text
Base 88828cb: 3368 testes, 254 issues
Derivado:      3401 testes, 403 issues
Novos:          152
Resolvidos:        3
```

Os novos resultados concentram-se em sessões, sweep, harvest, wake, predispatch e contratos legados multi-harness. Parte representa incompatibilidade intencional com capabilities tornadas dark; parte revelou cobertura incoerente ou caminhos públicos ainda alcançáveis. Portanto, o checkpoint não deve ser apresentado como regressão integral aprovada.

## Revisão independente paralela

Três revisores independentes foram executados em paralelo, com lentes diferentes:

1. superfícies, LLM, profiles e provisionamento;
2. ordem fail-closed e efeitos colaterais;
3. sessões, adapters, skills, documentação e coerência dos testes.

Resultado:

```text
Revisor A: REPROVADO
Revisor B: REPROVADO
Revisor C: REPROVADO
```

A correção de validação de seções malformadas ocorreu durante a janela da rodada. Por isso, a rodada não deve ser usada como aprovação criptográfica uniforme do snapshot final. Contudo, os principais blockers foram reproduzidos novamente no manifesto `daddbb...`, o que é suficiente para o NO-GO.

## Blockers reproduzidos no snapshot atual

Probes finais foram executados apenas com stubs e arquivos sintéticos em diretório temporário, sem rede, Docker, subprocesso real de harness, store real ou credencial real.

Foram confirmados:

1. selector externo arbitrário, como `primary: gemini`, aceito pela policy;
2. `heartbeat: {enabled: true}` aceito;
3. configuração Hermes aceita sem `HERMES_HOME` dedicado;
4. modelo externo propagado até `hermes -m <modelo>`;
5. subprocesso Hermes sem ambiente explícito fixando o profile dedicado;
6. traversal sintético de `secret_ref` para fora de `secrets/`;
7. reader público Codex lendo transcript sintético sem gate dark;
8. `edge-bootstrap runtime` alcançando o provisionador Neo4j.

Esses achados bastam para reprovar o Gate.

## Achados adicionais da revisão

Também foram apontados, devendo virar testes RED antes de correção:

- completion OpenAI direta em caminhos paralelos;
- fallbacks e descoberta implícita de embedding;
- efeitos de sweep/predispatch antes do guard dark;
- bootstrap com estado parcial antes de todas as validações;
- `edge-apply --provision-runtime` bloqueando após imports/leitura de YAML;
- helpers públicos adicionais de sessão/store;
- skills que ainda acionam capacidades dark;
- README e specs ainda descrevendo operação multi-harness;
- problema de coleta em `tests/test_onboarding.py`, com classe declarada após `unittest.main()`.

Alguns detalhes tiveram divergência entre revisores, mas não alteram o veredito porque os blockers reproduzidos acima já são suficientes.

## Veredito

> **NO-GO técnico e operacional.**

Este checkpoint:

- não está autorizado para merge;
- não está autorizado para instalação;
- não está autorizado para onboarding;
- não está autorizado para heartbeat, dogfood ou runtime autônomo;
- não deve ser rotulado como release ou implementação Hermes-only concluída.

O commit existe para preservar e compartilhar o avanço, permitir revisão e transformar os blockers em trabalho dirigido.

## Sequência recomendada

1. Transformar cada blocker reproduzido em teste RED canônico.
2. Corrigir primeiro traversal de secrets, runtime effectful, readers públicos e seleção externa de modelo.
3. Tornar selectors uma allowlist positiva e bloquear heartbeat enquanto dark.
4. Exigir e propagar `HERMES_HOME` dedicado em todo subprocesso Hermes.
5. Remover completion/embedding paralelos ou colocá-los atrás das factories autorizadas.
6. Mover guards antes de imports, arquivos, secrets, locks e mutações.
7. Corrigir skills, README, specs e coleta dos testes de onboarding.
8. Reexecutar regressão focada e suíte integral Linux.
9. Lançar nova revisão paralela contra um único commit congelado.
10. Avaliar separadamente o delta `88828cb..991fc745`.

Somente uma nova rodada sem blockers pode promover o trabalho de WIP para GO.
