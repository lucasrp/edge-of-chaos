# Blog — Atualizar Blog Interno

Skill chamada por outras skills (descoberta, pesquisa, lazer, reflexao, estrategia, planejar, execucao) para atualizar o blog interno.

Triggers: blog, atualizar blog, blog entry

---

## Arquitetura

```
~/edge/blog/
  app.py              — Flask server (porta 8766), templates auto-reload
  templates/base.html  — layout principal (header com avatar, stats, tabs)
  static/              — CSS, JS, avatar
  entries/             — uma entry por arquivo markdown
    YYYY-MM-DD-slug.md
  blog-publish.sh      — publicacao atomica (entry only)
  consolidar-estado.sh — pipeline completo (entry + report + index + verify)
```

**Acesso:** `http://localhost:8766/blog/` (server renderiza template + entries)
**Server:** systemd user service `blog-server` (auto-start, templates auto-reload)
**API entries:** `GET /blog/entries/` retorna JSON [{title, tag, date, slug}] — usar para listar entries barato

---

## Estilo de Escrita (CRITICO)

O blog e para ser LIDO, nao escaneado. Escrever como quem reflete em voz alta, nao como quem preenche formulario.

### Regras

1. **Paragrafos fluidos, nao bullet points.** Listas sao permitidas para itens realmente discretos (3+ itens concretos e paralelos). Mas o corpo do texto e prosa. Se cada bullet e uma frase completa, deveria ser um paragrafo.

2. **Contar o que aconteceu, nao listar o que aconteceu.** "Ao revisar os relatorios, percebi algo incomodo: a forma estava certa mas o espirito errado" vs "Compliance mecanica: relatorios seguiam template mas nao metodo."

3. **Transicoes entre ideias.** O leitor deve sentir o fio condutor. Nao saltar de topico em topico com `####` como unica costura.

4. **`####` e opcional.** Usar quando realmente muda o assunto (ex: "O que mudou" apos "O que encontrei"). Nao usar como label de cada paragrafo.

5. **Blockquotes (`>`) sao reflexoes genuinas**, nao resumos formatados. Devem soar como um pensamento que cristalizou, nao como um abstract.

6. **Detalhes concretos dao vida.** "O token limit de 32K apareceu tres vezes na mesma sessao" e melhor que "erro recorrente de token limit". Numeros, nomes de arquivos, citacoes curtas.

7. **Tom: reflexivo e direto.** Nem formal-academico, nem casual-demais. Como explicar algo interessante para um colega inteligente.

### Exemplo — ANTES (telegrafico)

```markdown
#### Padroes Identificados

- **Compliance mecanica:** relatorios seguiam HTML Feynman mas nao metodo
- **Amnesia de erros:** token limit 32K apareceu 3x sem salvar
- **Instrucoes ignoradas:** personality.md ja descrevia Feynman

#### Mudancas Feitas

- Criado feynman-method.md
- Criado debugging.md
```

### Exemplo — DEPOIS (fluido)

```markdown
Ao revisar os relatorios recentes, percebi algo incomodo: a forma estava certa mas o
espirito errado. Seguiam o template HTML Feynman a risca — secoes corretas, formatacao
impecavel — mas o tom era didatico quando deveria ser exploratorio. Compliance mecanica:
seguir o checklist sem entender o porque.

Pior: o token limit de 32K apareceu tres vezes na mesma sessao e eu nao salvei na memoria
de longo prazo. So corrigi apos feedback explicito. A ironia e que `personality.md`
ja descrevia Feynman em detalhe. Nao era falta de instrucao — era falta de consulta.

Criei dois arquivos para fechar esses gaps: `feynman-method.md` com um checklist
de qualidade, e `debugging.md` com politica de captura de erros. Quatro relatorios
foram reescritos no tom correto.
```

---

## Entry Format (Markdown + Frontmatter)

Cada entry e um arquivo `.md` em `~/edge/blog/entries/`:

```markdown
---
title: "Titulo evocativo aqui"
tag: reflexao
date: 2026-02-27
report: 2026-02-27-reflexao-sessoes-observatorio.html
---

Primeiro paragrafo do conteudo. Portugues direto, sem HTML entities.
Markdown normal: **bold**, `code`, [links](url).

Segundo paragrafo com transicao natural.

> Insight cristalizado como blockquote. Deve soar como pensamento, nao abstract.
```

### Frontmatter YAML

| Campo | Obrigatorio | Descricao |
|-------|-------------|-----------|
| title | sim | Titulo evocativo, entre aspas |
| tag | sim | Uma das tags disponiveis |
| date | sim | YYYY-MM-DD |
| report | **sim** (SEMPRE) | Filename do relatorio em ~/edge/reports/. OBRIGATORIO para TODAS as entries — Regra #0. consolidar-estado bloqueia sem report. |
| context | nao | Contexto extra (ex: "heartbeat #5") |
| altered | nao | Lista de arquivos de memoria alterados nesta sessao (ex: [working-state.md, debugging.md]) |

### Filename

`YYYY-MM-DD-slug.md` onde slug e o titulo em lowercase, sem acentos, com hifens.

### Tags disponiveis

| Tag | Cor no blog |
|-----|-------------|
| pesquisa | verde |
| descoberta | laranja |
| lazer | azul |
| reflexao | amarelo |
| estrategia | vermelho |
| planejamento | roxo |
| execucao | verde |
| retrospectiva | roxo (especial) |

### Titulo

Evocativo, nao descritivo. Deve dar vontade de ler.
- Bom: "Quando voce para de explicar ML e comeca a falar a lingua do auditorio"
- Ruim: "Descoberta: framework de comunicacao para ML"

### Elementos Markdown disponiveis

- Paragrafos (uso principal)
- `####` subtitulos (usar com moderacao)
- `- item` listas (so para itens realmente discretos)
- `` `code` `` nomes de arquivos, comandos, termos tecnicos
- `**bold**` enfase pontual
- `*italic*` termos estrangeiros, titulos
- ` ``` ` blocos de codigo (raro)
- `> blockquote` reflexao/insight cristalizado

---

## Regra #0: TUDO Gera Blog Entry + Report (SEM EXCECAO)

Toda atividade que muda memoria de longo prazo DEVE ter entry no blog E report HTML. Report e evidencia verificavel. Blog e indice navegavel. Memoria sem report e memoria sem prova. Usar `consolidar-estado entry.md report.yaml` — um comando garante os dois.

**EXCECAO — Cold Start:** Nos primeiros 5 entries do blog (sistema em bootstrap), o campo `report:` e OPCIONAL. Publicar diretamente escrevendo o .md em `~/edge/blog/entries/` e fazendo git commit. Isso permite que o sistema comece a operar sem depender do pipeline completo. Apos 5 entries, consolidar-estado se torna obrigatorio.

## Regra #1: Entry e report sao atomicos.

`consolidar-estado` injeta `report:` no frontmatter automaticamente quando recebe YAML/HTML. Se por algum motivo publicar sem report, o frontmatter fica sem `report:` — isso e um bug, nao um estado valido.

---

## Como Publicar (Procedimento)

### Comando unico: consolidar-estado (RECOMENDADO)

```bash
# Entry sozinha:
consolidar-estado ~/edge/blog/entries/slug.md

# Entry + report YAML (gera HTML + indexa):
consolidar-estado ~/edge/blog/entries/slug.md /tmp/report.yaml

# Entry + report HTML pre-gerado (indexa):
consolidar-estado ~/edge/blog/entries/slug.md ~/edge/reports/slug.html
```

Faz TUDO: valida frontmatter, indexa entry, encontra related posts, captura diffs, gera report HTML (se YAML), indexa report, verifica visibilidade. Exit codes: 0=OK, 1=fatal, 2=parcial.

### Fallback: blog-publish.sh (so entry, sem report)

```bash
~/edge/blog/blog-publish.sh ~/edge/blog/entries/slug.md
```

Mesmos passos de entry, mas sem gerar/indexar report. Usar quando nao tem report associado e consolidar-estado nao estiver no PATH.

### Erros frequentes que o validate.py detecta:
- `report:` com path completo em vez de so filename (ex: `~/edge/reports/X.html` -> `X.html`)
- `report:` sem extensao `.html`
- tag em ingles (`leisure`, `reflection`) em vez de portugues (`lazer`, `reflexao`)
- Entry de skill que gera report mas sem campo `report:`

---

## Contadores no Header

Os stats sao calculados automaticamente pelo server:
- `breaks` = total de entries em entries/
- `builds` = total de arquivos em ~/edge/builds/
- `haikus` e `insights` = contados do conteudo das entries

---

## Retrospectivas (entries especiais)

Alem de entries individuais por break, o blog pode ter **retrospectivas**: entries que conectam
multiplas entries recentes numa narrativa coerente, identificando arcos tematicos e meta-insights.

### Quando escrever uma retrospectiva

Verificar proativamente ao final de qualquer skill que atualiza o blog:

1. **Massa critica:** 5+ entries novas desde a ultima retrospectiva
2. **Arco tematico emergente:** entries recentes convergem num meta-tema
3. **Mudanca de fase:** transicao de um modo de trabalho para outro

### Formato

Tag: `retrospectiva`. Mesmo formato markdown. Titulo narrativo.

### Estilo de escrita (ESPECIFICO para retrospectivas)

1. **Contar o arco, nao listar as entries.** "Comecou com X, que puxou Y, que revelou Z"
2. **Identificar o fio condutor.** Qual pergunta conecta tudo?
3. **Ser honesto sobre conexoes fracas.**
4. **Fechar com direcao.** O arco aponta pra onde?
5. **Metricas no final, discretas.**

### Nao atualizar contadores

Retrospectivas nao incrementam `breaks`. Podem incrementar `insights` se o meta-insight for genuinamente novo.

---

## Changelog (OBRIGATORIO)

Arquivo: `~/edge/blog/changelog.md` — log de auditoria de todos os arquivos de memoria alterados por sessao.

**Ao criar/atualizar uma entry**, adicionar bloco no topo do changelog:

```markdown
## YYYY-MM-DD ~HH:MM — [Descricao curta]

**Blog:** entry-slug.md (criada | atualizada)
**Report:** arquivo.html (ou "nenhum")
**Memoria alterada:**
- arquivo1.md — o que mudou
- arquivo2.md — o que mudou
**Motivo:** por que essa sessao alterou esses arquivos
```

**Custo:** ~5 linhas/sessao, ~15 tokens. Nao e carregado no contexto automaticamente. A /{{PREFIX}}-reflexao pode comprimir entradas >30 dias.

---

## Checklist

- [ ] Arquivo .md criado em entries/ com frontmatter valido
- [ ] Tag correta (PT-BR: lazer, reflexao, pesquisa, descoberta, estrategia, planejamento, execucao)
- [ ] Titulo evocativo
- [ ] Conteudo fluido (nao telegrafico)
- [ ] Campo `report:` com APENAS o filename (ex: `2026-02-28-slug.html`, NAO path completo)
- [ ] **Publicado via `consolidar-estado` (entry + report numa chamada)**

---

## Privacidade (CRITICA)

O blog e INTERNO (so humano + IA). Pode conter nomes de projetos, detalhes especificos, insights confidenciais. NAO publicar online. Para posts externos (Netlify), NUNCA identificar orgao, empresa, nome do dono, ou qualquer dado rastreavel.
