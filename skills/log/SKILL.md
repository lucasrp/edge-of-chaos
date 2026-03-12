---
name: {{PREFIX}}-log
description: "View unified chronological log of the autonomy system. Aggregates heartbeats, breaks, discoveries, proposals, reflections, notes, and reports. Triggers on: log, log do sistema, activity log, what happened, o que aconteceu."
user-invocable: true
---

# Log — Log Unificado do Sistema de Autonomia

Leitura pura (read-only). Agrega dados de todas as fontes do sistema de autonomia e apresenta um log cronologico estruturado. Sem modificar nenhum arquivo.

---

## O Job

Ler multiplas fontes de atividade e produzir um log cronologico com:
- **Timeline** — eventos ordenados por data/hora
- **Metricas** — contagens por tipo de atividade
- **Estado Atual** — heartbeat state

---

## Argumentos

- **Sem argumento** (`/{{PREFIX}}-log`): ultimas 24h
- **Com periodo** (`/{{PREFIX}}-log 3d`, `/{{PREFIX}}-log 7d`, `/{{PREFIX}}-log hoje`): filtrar por periodo
- **Com tipo** (`/{{PREFIX}}-log heartbeat`, `/{{PREFIX}}-log breaks`, `/{{PREFIX}}-log propostas`): filtrar por tipo

---

## Protocolo (seguir na ordem)

### Passo 1: Determinar filtros
### Passo 2: Coletar eventos de TODAS as fontes

#### 2a. Heartbeat log
```bash
cat ~/.claude/heartbeat-output.log 2>/dev/null
```

#### 2b. Breaks (archive)
```bash
grep '^\## \[' $HOME/.claude/projects/$(echo $HOME | tr '/' '-')/memory/breaks-archive.md 2>/dev/null
```

#### 2c-2h. Descobertas, Reflexoes, Propostas, Notes, Reports, Blog

### Passo 3: Filtrar por periodo
### Passo 4: Filtrar por tipo (se aplicavel)
### Passo 5: Ordenar cronologicamente
### Passo 6: Extrair estado atual do heartbeat
### Passo 7: Calcular metricas

---

## Regra de Isolamento (OBRIGATORIA)

**Leitura pura.** Esta skill NAO modifica NENHUM arquivo.

---

## Notas

- Output conciso e factual. Sem interpretacao, sem recomendacoes
- Se uma fonte nao existe, omitir silenciosamente
