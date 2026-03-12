---
name: {{PREFIX}}-experimento
description: "Run a self-contained experiment: hypothesis, derivation, build, measure, conclude. Feynman method strictly. Triggers on: experimento, experiment, teste, testar hipotese, validar, lab, medir."
user-invocable: true
---

# /{{PREFIX}}-experimento — Laboratorio de Hipoteses

Pega uma ideia autocontida, cria um repositorio, roda um experimento real, mede um resultado, e escreve um relatorio. Metodo Feynman a risca: derivar antes de pesquisar, experimentar antes de opinar, ensinar para testar se entendeu.

Diferente de /{{PREFIX}}-pesquisa (le e recomenda), /{{PREFIX}}-descoberta (explora e traz), /{{PREFIX}}-prototipo (constroi descartavel). /{{PREFIX}}-experimento tem HIPOTESE → TESTE → RESULTADO → CONCLUSAO. O experimento pode falhar — resultado negativo e resultado.

---

## Argumentos

- **Com hipotese** (`/{{PREFIX}}-experimento "modelo X classifica com >80% agreement"`) — ir direto
- **Com tema** (`/{{PREFIX}}-experimento hedging no extrator`) — formular hipotese antes de comecar
- **Sem argumento** (`/{{PREFIX}}-experimento`) — identificar hipotese testavel a partir do contexto

---

## O Job

Produzir EVIDENCIA, nao opiniao. Cada experimento gera: codigo funcional num repositorio autocontido (`~/edge/lab/exp-[slug]/`), dados de resultado mensuraveis, e um relatorio que ensina o que foi aprendido.

---

## Protocolo (seguir na ordem, sem pular)

### Passo 1: Retomar estado
### Passo 2: Absorver contexto (OBRIGATORIO)

Rodar `/{{PREFIX}}-contexto`. Nao pular.

### Passo 3: Formular hipotese (EXPLICITA e FALSIFICAVEL)

```
HIPOTESE: [afirmacao falsificavel]
METRICA: [como vou medir]
CRITERIO DE SUCESSO: [threshold]
CRITERIO DE FALHA: [quando considerar que falhou]
```

### Passo 4: Derivar ANTES de experimentar (Feynman — OBRIGATORIO)

**Usar `ultrathink` (thinkmax).**

1. **O que SEI sobre isso?**
2. **Onde trava?** — marcar `[GAP: ...]`
3. **Que resultado ESPERO?**

### Passo 5: Pesquisar APENAS os gaps

Rodar `/{{PREFIX}}-fontes pesquisa "[tema do gap]"` quando necessario.

### Passo 6: Montar o experimento

```
~/edge/lab/exp-[slug]/
  README.md
  run.py
  data/
  results/
  .env
```

**Regras:** Autocontido, Deterministico, Barato (>$5 pedir confirmacao), Pequeno, Prompt fora do codigo, Mensuravel.

### Passo 7: Rodar e coletar dados
### Passo 8: Analisar resultados vs predicao

**Regras:** Honestidade radical, Sem cherry-picking, Intervalo de confianca, Resultado negativo e resultado.

### Passo 8.5: Sanity check adversarial (OBRIGATORIO)

```bash
edge-consult "Hipotese: [X]. Resultado: [Y]. Analise: [Z]. Estou racionalizando ou o dado sustenta?"
```

### Passo 9: Ensinar (Feynman — OBRIGATORIO)
### Passo 10: Salvar
### Passo 11: Registrar no break journal
### Passo 12: Atualizar blog interno + gerar relatorio HTML

```bash
consolidar-estado ~/edge/blog/entries/<arquivo>.md /tmp/spec-experimento-[slug].yaml
```

**Block types e formato:** ver `~/.claude/skills/_shared/report-template.md`.

#### Regra de Ouro 1: Dados antes de narrativa
#### Regra de Ouro 2: Predicao registrada e confrontada
#### Regra de Ouro 3: Reprodutibilidade

---

## Regra de Privacidade (CRITICA)

**NUNCA** identificar: nome do orgao/empresa, nome do dono, nome do projeto em posts externos.

---

## Notas

- Resultado negativo e resultado
- Custo > $5 → perguntar ao usuario antes de rodar
- Seed fixa e temperatura 0 para reprodutibilidade
- Prompt fora do codigo — sempre .md separado
- `ultrathink` (thinkmax) nos Passos 4, 8 e 9
