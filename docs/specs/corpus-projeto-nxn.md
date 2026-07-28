# Corpus de projeto — N pessoas × N agentes numa mesma KB

**Fórmula:** o corpus é do PROJETO; o agente é da PESSOA×projeto. O bobmarley (marketing) e o
petertosh (atendimento) trabalham NO MESMO produto: cada um tem seu agente (persona, missão,
direction, leveling próprios), e os dois agentes habitam o mesmo corpus — o cérebro coletivo do
projeto. Uma pessoa pode ter vários agentes (um por projeto) e compartilhar só um deles.

**O modo simples é o caso degenerado.** 1 pessoa × 1 agente × corpus privado × filme da vida
inteira = exatamente o comportamento de hoje. Nenhum campo declarado → nenhum install existente
muda. "Modo avançado" é linguagem de onboarding, não um fork de código.

## Declaração (agent.yaml)

```yaml
corpus:
  group: edge-of-chaos          # a chave de tenancy do corpus (default: name do install)
  uri: bolt://10.0.0.5:7687     # onde o Neo4j do corpus vive (default: localhost)
  role: member                  # host | member (default: host)
  film:
    stores:                     # o filtro de projeto sobre o filme (default: store da vida toda)
      - /mnt/c/Users/bob/.claude/projects/-home-bob-proj-x
```

Lido por `_identity.corpus()` / `group()` / `agent_id()` / `neo4j_conn()` / `film_stores()`.

## As quatro regras

1. **Regime chaveado por agente.** `Genesis/Objective/Direction` são `{group_id, agent}` —
   N espinhas num só group. Escritas em `publisher.BACKBONE_*` (constantes pinadas); leitura no
   `recall.SPINE_QUERY` com `coalesce(n.agent,$agent)=$agent` (nó legado sem `agent` continua
   respondendo ao seu único install; o `BACKBONE_CLAIM` migra-o no primeiro sweep canônico).
2. **Proveniência em tudo que entra no corpus.** `Artefato.agent` carimbado na projeção
   (coalesced — replay nunca re-clama artefato alheio); `SERVES` liga o artefato ao objetivo DO
   AUTOR, nunca a todos os objetivos.
3. **`corpus_role: host|member`.** Só o host consolida communities (guarda em
   `communities.consolidate`, declarada em voz alta) — regra sem lock para N agentes numa KB.
   Cada agente filma o PRÓPRIO mentee (o `project_dir`/`film.stores` de cada install já faz o
   roteamento); ninguém filma a mesma pessoa duas vezes.
4. **Filme filtrado por projeto.** O Claude Code já particiona sessões por diretório de
   trabalho; `film.stores` declara quais diretórios pertencem ao projeto. Compartilhar o corpus
   expõe só a fatia-projeto do filme, não a vida da pessoa.

## Consentimento e acesso

Entrar num corpus = publicar tua fatia-projeto pro time (sessões legíveis pelos agentes dos
colegas). Dito em voz alta na entrevista, nunca implícito. Controle de acesso = posse da
credencial bolt; não há ACL por membro nesta versão.

## Tetos declarados (validação com usuários antes de resolver)

- **Proveniência do filme (`:Episodic`/Graphiti)** ainda não carimba autor — só artefatos e
  regime. Numa KB compartilhada, "quem disse isto" no filme vem do store de origem, não do nó.
- **Sessão mista** (dois projetos na mesma pasta) vaza pro corpus do projeto da pasta — filtro é
  por diretório; re-escopo semântico só se doer na prática.
- **`Hypothesis` continua chaveada só por group** — aposta do agente ou conhecimento do corpus?
  Questão aberta pra validação.
- **Infra fora do código:** bolt alcançável entre as caixas do time (bind + rede + secret
  distribuído) é deploy, não edge.
- **Consumidores do filme** ainda leem `project_dir()` (um store); `film_stores()` é o seam
  novo — o rewire de quente/harvest para N stores vem com a validação.
