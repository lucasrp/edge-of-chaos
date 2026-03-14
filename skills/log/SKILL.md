---
name: log
description: "View unified chronological log of the autonomy system. Aggregates heartbeats, breaks, discoveries, proposals, reflections, notes, and reports. Triggers on: log, log do sistema, activity log, what happened, o que aconteceu."
user-invocable: true
---

# Log — Log Unificado do Sistema de Autonomia

Leitura pura (read-only). Agrega dados de todas as fontes do sistema de autonomia e apresenta um log cronologico estruturado. Sem modificar nenhum arquivo.

---

## O Job

Ler multiplas fontes de atividade do sistema de autonomia e produzir um log cronologico com:
- **Timeline** — eventos ordenados por data/hora
- **Metricas** — contagens por tipo de atividade
- **Estado Atual** — heartbeat state

---

## Argumentos

O usuario pode passar argumentos apos `/log`:

- **Sem argumento** (`/log`): ultimas 24h de atividade
- **Com periodo** (`/log 3d`, `/log 7d`, `/log hoje`): filtrar por periodo
  - `hoje` = desde 00:00 de hoje
  - `Nd` = ultimos N dias (ex: `3d` = ultimos 3 dias)
  - `Nw` = ultimas N semanas
- **Com tipo** (`/log heartbeat`, `/log breaks`, `/log propostas`, `/log notes`, `/log reports`): filtrar por tipo

---

## Protocolo (seguir na ordem)

### Passo 1: Determinar filtros

Parsear o argumento do usuario:

- **Periodo:** Se nenhum argumento ou tipo, default = 24h. Se `hoje`, usar data de hoje. Se `Nd`, calcular data de corte. Se `Nw`, calcular.
- **Tipo:** Se o argumento e um tipo conhecido (heartbeat, breaks, propostas, descobertas, reflexoes, notes, reports), filtrar apenas esse tipo.

Guardar a data de corte como variavel para filtrar eventos.

### Passo 2: Coletar eventos de TODAS as fontes

Executar os comandos abaixo e parsear os resultados. Cada evento deve ter: `[data/hora] tipo — resumo`.

#### 2a. Heartbeat log

```bash
# Extrair execucoes, skips e erros com timestamps
cat ~/.claude/heartbeat-output.log 2>/dev/null
```

Parsear linhas com padroes:
- `--- heartbeat YYYY-MM-DDTHH:MM:SS` → evento de execucao
- `--- done YYYY-MM-DDTHH:MM:SS` → fim de execucao
- `--- skipped YYYY-MM-DDTHH:MM:SS (motivo)` → skip
- `Error:` → erro
- `Heartbeat #N complete` → heartbeat concluido

Para cada heartbeat completo (entre `--- heartbeat` e `--- done`), extrair:
- Numero do beat (se mencionado)
- Dispatch (qual skill foi chamada)
- Resumo (primeira frase significativa)

#### 2b. Breaks (archive)

```bash
# Extrair entradas com data do breaks-archive.md
grep '^\## \[' ~/.claude/projects/-home-vboxuser/memory/breaks-archive.md 2>/dev/null
```

Cada linha `## [YYYY-MM-DD]` e um break. Parsear tipo e titulo.

#### 2c. Descobertas

```bash
# Extrair entradas com data e status
grep '^\## \[' ~/.claude/projects/-home-vboxuser/memory/descobertas.md 2>/dev/null
```

#### 2d. Reflexoes

```bash
# Extrair entradas do reflexao-log
grep '^\## \[' ~/.claude/projects/-home-vboxuser/memory/reflexao-log.md 2>/dev/null
```

#### 2e. Propostas

```bash
# Extrair propostas com data e status
grep '^\## \[' ~/.claude/projects/-home-vboxuser/memory/propostas.md 2>/dev/null
```

#### 2f. Notes

```bash
# Listar notes com data de modificacao
ls -lt --time-style=full-iso ~/edge/notes/*.md 2>/dev/null | grep -v INDEX.md
```

#### 2g. Reports

```bash
# Listar reports com data de modificacao
ls -lt --time-style=full-iso ~/edge/reports/*.html 2>/dev/null
```

#### 2h. Blog

```bash
# Extrair datas de entradas do blog
grep -E '<h2>|<time|class="entry-date"' ~/edge/blog/index.html 2>/dev/null
```

### Passo 3: Filtrar por periodo

Aplicar a data de corte determinada no Passo 1. Descartar eventos fora do periodo.

### Passo 4: Filtrar por tipo (se aplicavel)

Se o usuario pediu um tipo especifico, manter apenas eventos daquele tipo.

### Passo 5: Ordenar cronologicamente

Ordenar todos os eventos coletados por data/hora, do mais antigo ao mais recente.

### Passo 6: Extrair estado atual do heartbeat

```bash
grep -A 10 "Estado do Heartbeat" ~/.claude/projects/-home-vboxuser/memory/breaks-active.md 2>/dev/null
```

### Passo 7: Calcular metricas

Contar por tipo:
- Heartbeats: executados, skipped, com erro
- Breaks: total e por tipo (lazer, pesquisa, descoberta, estrategia, reflexao, planejamento, execucao)
- Propostas: criadas no periodo, por status
- Descobertas: criadas no periodo, por status
- Reflexoes: total no periodo
- Notes: novas no periodo
- Reports: gerados no periodo

---

## Output

Produzir markdown estruturado direto no terminal:

```markdown
## Log do Sistema — [periodo descritivo]

### Timeline
[YYYY-MM-DD HH:MM] HEARTBEAT — resumo 1 linha
[YYYY-MM-DD HH:MM] BREAK — tipo: titulo
[YYYY-MM-DD HH:MM] PROPOSTA — #N titulo [STATUS]
[YYYY-MM-DD HH:MM] DESCOBERTA — titulo [STATUS]
[YYYY-MM-DD HH:MM] REFLEXAO — #N resumo
[YYYY-MM-DD HH:MM] NOTE — titulo do arquivo
[YYYY-MM-DD HH:MM] REPORT — titulo do arquivo
...

### Metricas
- Heartbeats: N executados, N skipped, N erros
- Breaks: N total (N lazer, N pesquisa, N descoberta...)
- Propostas: N no periodo (N PROPOSTA, N APROVADA, N CONCLUIDA...)
- Descobertas: N no periodo (N PENDENTE, N ADOTADA...)
- Reflexoes: N
- Notes: N novas
- Reports: N gerados

### Estado Atual
- Ultimo beat: #N
- Dispatch: [tipo]
- Beats desde estrategia: N
- Beats desde planejar: N
- Proximo heartbeat: [se detectavel do log]
```

**Se nao houver atividade no periodo:** Informar claramente "Nenhuma atividade registrada no periodo [X]."

**Se filtrado por tipo:** Omitir secoes de metricas para tipos nao solicitados. Manter timeline e metricas apenas do tipo pedido.

---

## Regra de Isolamento (OBRIGATORIA)

**Leitura pura.** Esta skill NAO modifica NENHUM arquivo — nem state files, nem projetos, nem nada.
Todos os comandos sao de leitura (cat, grep, ls, wc, stat).

---

## Notas

- Output conciso e factual. Sem interpretacao, sem recomendacoes
- Se uma fonte nao existe, omitir silenciosamente (nao reportar erro)
- Timestamps: usar o formato mais preciso disponivel na fonte
- Para heartbeats: agrupar `--- heartbeat` + conteudo + `--- done` como um unico evento
- Heartbeats vazios (sem output entre heartbeat e done/proximo) representam execucoes que nao geraram acao — listar como "HEARTBEAT — sem dispatch"
- Heartbeats com "skipped" nao sao execucoes — listar separadamente nas metricas
- Para notas e reports: usar data de modificacao do filesystem
- Nao duplicar eventos que aparecem em multiplas fontes (ex: um break aparece no archive E no heartbeat log)
