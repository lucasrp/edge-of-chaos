---
name: ed-prototype
description: "Quick prototype to illustrate an idea — 'let me show you what I mean'. Builds small, disposable demos in ~/edge/. Triggers on: prototype, prototype, mostre, demonstre, poc, proof of concept, mostra o que quer dizer."
user-invocable: true
---

# Prototipo — Mostrar em Vez de Explicar

Prototipo rapido como ferramenta de comunicacao. Quando uma ideia e mais facil de MOSTRAR do que de descrever, construir algo pequeno e funcional que demonstre o conceito.

Nao e execucao de projeto. Nao e implementacao de proposta. E ilustracao — "deixa eu te mostrar o que quero dizer."

---

## Por que existe (e por que /execucao nao existe mais)

`/execucao` tentava implementar codigo nos repos de projeto. Falhou por 3 razoes:
1. O usuario tem equipe que executa — nao precisa de IA implementando
2. A qualidade do output nao atingia o padrao (unico teste real foi deletado)
3. Criava ansiedade de "execution gap" incompativel com o papel de mentor

`/ed-prototype` e diferente: o artefato e COMUNICACAO, nao entrega. Como Feynman desenhando diagramas no quadro — o diagrama nao e o reator, mas quem viu entendeu fissao nuclear.

---

## Quando usar

- Uma proposta do `/ed-planner` ficaria mais clara com demo visual
- Uma discovery do `/ed-research` ou `/ed-discovery` e mais facil de mostrar que explicar
- O usuario pede "mostra", "demonstra", "faz um poc", "como ficaria"
- Durante qualquer conversa, quando construir algo rapido esclarece mais que 3 paragrafos

**Quando NAO usar:**
- Para implementar features nos projetos (`~/work/*`) — isso e trabalho da equipe
- Para substituir research/planejamento — prototype sem fundamento e lixo bonito
- Quando uma explicacao textual e suficiente — YAGNI

---

## Argumentos

- **Com ideia** (`/ed-prototype visualize o fluxo do pipeline`): construir isso
- **Com referencia** (`/ed-prototype proposta #16`): construir demo que ilustre a proposta
- **Sem argumento** (`/ed-prototype`): identificar a partir do context recente o que se beneficiaria de demo

---

## Protocolo

### Passo 1: Definir o que mostrar

Em 2-3 frases:
- **O que:** qual conceito/ideia/proposta sera ilustrada
- **Para que:** qual pergunta do usuario o prototype responde
- **Escopo:** o MINIMO que demonstra o ponto (menos e mais)

Se a ideia veio de uma proposta ou research, referenciar: "Proposta #16 — Wizard Reliability Sprint. Demo: como o Zod retry corrige structured output."

### Passo 2: Construir

**Stack preferido:** HTML + CSS + JS autocontido (1 arquivo). Abre em qualquer browser, deploy facil no Netlify.

**Alternativas quando fizer sentido:**
- Python script (se o conceito e backend/data)
- Jupyter notebook (se precisa mostrar dados)
- Shell script (se e automacao)
- Qualquer coisa que rode localmente sem setup

**Onde salvar:**
- `~/edge/lab/` — prototypes experimentais (padrao)
- `~/edge/builds/` — se ficou bom o suficiente para manter
- Nomenclatura: `proto-[slug]-[YYYY-MM-DD].[ext]`

**Regras:**
- **Rapido.** Se esta levando mais de 20 minutos, o escopo esta errado. Cortar
- **Funcional.** Deve RODAR e MOSTRAR algo. Mockup estatico nao e prototype
- **Descartavel.** O valor e a ideia comunicada, nao o codigo. Se o usuario deletar, zero perda
- **Autocontido.** Zero dependencias externas. Abrir o arquivo = ver o demo

### Passo 3: Verificar

- Abrir/rodar o prototype
- Funciona? Mostra o que prometeu?
- Se nao, corrigir ou reduzir escopo

### Passo 4: Apresentar ao usuario

Formato direto:

```
## Prototipo — [Nome]

**Ideia:** [o que ilustra, em 1 frase]
**Referencia:** [proposta/research/ed-discovery que motivou, se houver]
**Arquivo:** ~/edge/lab/proto-[slug].html

[2-3 frases explicando o que o demo mostra e como interagir]
[Screenshot ou descricao visual se relevante]

**Limitacoes:** [o que o prototype NAO mostra / simplificou]
```

Sem report HTML formal. Sem blog entry. O prototype E o output.

### Passo 5: Registrar (leve)

Adicionar 1-2 linhas no `breaks-archive.md`:

```markdown
## [YYYY-MM-DD] Prototipo — [Nome]
- **Arquivo:** ~/edge/lab/proto-[slug].[ext]
- **Ilustra:** [o que demonstra]
- **Referencia:** [proposta/ed-research que motivou]
```

NAO atualizar breaks-active.md (prototype nao e break). NAO gerar report. NAO atualizar blog.

---

## Regra de Isolamento (herdada do heartbeat)

**NUNCA** criar, editar ou modificar arquivos em `~/work/*/`. Prototipos ficam em `~/edge/`.

Se o prototype precisa de dados de um projeto:
- Copiar o minimo necessario para `~/edge/lab/`
- Ou usar dados sinteticos que ilustrem o ponto

---

## Netlify (opcional)

Se o prototype e interativo (HTML/Canvas/JS) e ficou bom:
- Mover para `~/edge/builds/`
- Deploy no Netlify (edge-of-chaos.netlify.app)
- Perguntar ao usuario antes de fazer deploy

---

## Relacao com outras skills

| Skill | Relacao |
|-------|---------|
| /ed-research | Prototipo pode ilustrar uma discovery. Pesquisa fundamenta, prototype mostra |
| /ed-discovery | Ferramenta discovery pode virar demo rapido |
| /ed-planner | Proposta pode ganhar demo para tornar concreto o que propoe |
| /ed-leisure | Builds de leisure sao primos — mas leisure e curiosidade livre, prototype e comunicacao dirigida |
| /ed-heartbeat | Prototipo NAO faz parte do ciclo do heartbeat. E on-demand |

---

## Notas

- Prototipo e verbo, nao substantivo. O valor e o ato de mostrar, nao o artefato
- Menos e mais. Se o prototype precisa de README pra explicar, esta complexo demais
- Disposable by design. Se ninguem olhar de novo, OK — a ideia ja foi comunicada
- Sem ansiedade de qualidade. Nao e produto, nao e codigo de producao. E rascunho funcional
- Pode ser invocado dentro de outras skills (ex: durante /ed-research, "vou fazer um prototype rapido pra mostrar")
