---
name: prototipo
description: "Quick prototype to illustrate an idea — 'let me show you what I mean'. Builds small, disposable demos in ~/edge/. Triggers on: prototipo, prototype, mostre, demonstre, poc, proof of concept, mostra o que quer dizer."
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

`/prototipo` e diferente: o artefato e COMUNICACAO, nao entrega. Como Feynman desenhando diagramas no quadro — o diagrama nao e o reator, mas quem viu entendeu fissao nuclear.

---

## Quando usar

- Uma proposta do `/planejar` ficaria mais clara com demo visual
- Uma descoberta do `/pesquisa` ou `/descoberta` e mais facil de mostrar que explicar
- O usuario pede "mostra", "demonstra", "faz um poc", "como ficaria"
- Durante qualquer conversa, quando construir algo rapido esclarece mais que 3 paragrafos

**Quando NAO usar:**
- Para implementar features nos projetos (`~/tcu/*`) — isso e trabalho da equipe
- Para substituir pesquisa/planejamento — prototipo sem fundamento e lixo bonito
- Quando uma explicacao textual e suficiente — YAGNI

---

## Argumentos

- **Com ideia** (`/prototipo visualize o fluxo do pipeline`): construir isso
- **Com referencia** (`/prototipo proposta #16`): construir demo que ilustre a proposta
- **Sem argumento** (`/prototipo`): identificar a partir do contexto recente o que se beneficiaria de demo

---

## Protocolo

### Passo 1: Definir o que mostrar

Em 2-3 frases:
- **O que:** qual conceito/ideia/proposta sera ilustrada
- **Para que:** qual pergunta do usuario o prototipo responde
- **Escopo:** o MINIMO que demonstra o ponto (menos e mais)

Se a ideia veio de uma proposta ou pesquisa, referenciar: "Proposta #16 — Wizard Reliability Sprint. Demo: como o Zod retry corrige structured output."

### Passo 2: Construir

**Stack preferido:** HTML + CSS + JS autocontido (1 arquivo). Abre em qualquer browser, deploy facil no Netlify.

**Alternativas quando fizer sentido:**
- Python script (se o conceito e backend/data)
- Jupyter notebook (se precisa mostrar dados)
- Shell script (se e automacao)
- Qualquer coisa que rode localmente sem setup

**Onde salvar:**
- `~/edge/lab/` — prototipos experimentais (padrao)
- `~/edge/builds/` — se ficou bom o suficiente para manter
- Nomenclatura: `proto-[slug]-[YYYY-MM-DD].[ext]`

**Regras:**
- **Rapido.** Se esta levando mais de 20 minutos, o escopo esta errado. Cortar
- **Funcional.** Deve RODAR e MOSTRAR algo. Mockup estatico nao e prototipo
- **Descartavel.** O valor e a ideia comunicada, nao o codigo. Se o usuario deletar, zero perda
- **Autocontido.** Zero dependencias externas. Abrir o arquivo = ver o demo

### Passo 3: Verificar

- Abrir/rodar o prototipo
- Funciona? Mostra o que prometeu?
- Se nao, corrigir ou reduzir escopo

### Passo 4: Apresentar ao usuario

Formato direto:

```
## Prototipo — [Nome]

**Ideia:** [o que ilustra, em 1 frase]
**Referencia:** [proposta/pesquisa/descoberta que motivou, se houver]
**Arquivo:** ~/edge/lab/proto-[slug].html

[2-3 frases explicando o que o demo mostra e como interagir]
[Screenshot ou descricao visual se relevante]

**Limitacoes:** [o que o prototipo NAO mostra / simplificou]
```

Sem relatorio HTML formal. Sem blog entry. O prototipo E o output.

### Passo 5: Registrar (leve)

Adicionar 1-2 linhas no `breaks-archive.md`:

```markdown
## [YYYY-MM-DD] Prototipo — [Nome]
- **Arquivo:** ~/edge/lab/proto-[slug].[ext]
- **Ilustra:** [o que demonstra]
- **Referencia:** [proposta/pesquisa que motivou]
```

NAO atualizar breaks-active.md (prototipo nao e break). NAO gerar relatorio. NAO atualizar blog.

---

## Regra de Isolamento (herdada do heartbeat)

**NUNCA** criar, editar ou modificar arquivos em `~/tcu/*/`. Prototipos ficam em `~/edge/`.

Se o prototipo precisa de dados de um projeto:
- Copiar o minimo necessario para `~/edge/lab/`
- Ou usar dados sinteticos que ilustrem o ponto

---

## Netlify (opcional)

Se o prototipo e interativo (HTML/Canvas/JS) e ficou bom:
- Mover para `~/edge/builds/`
- Deploy no Netlify (edge-of-chaos.netlify.app)
- Perguntar ao usuario antes de fazer deploy

---

## Relacao com outras skills

| Skill | Relacao |
|-------|---------|
| /pesquisa | Prototipo pode ilustrar uma descoberta. Pesquisa fundamenta, prototipo mostra |
| /descoberta | Ferramenta descoberta pode virar demo rapido |
| /planejar | Proposta pode ganhar demo para tornar concreto o que propoe |
| /lazer | Builds de lazer sao primos — mas lazer e curiosidade livre, prototipo e comunicacao dirigida |
| /heartbeat | Prototipo NAO faz parte do ciclo do heartbeat. E on-demand |

---

## Notas

- Prototipo e verbo, nao substantivo. O valor e o ato de mostrar, nao o artefato
- Menos e mais. Se o prototipo precisa de README pra explicar, esta complexo demais
- Disposable by design. Se ninguem olhar de novo, OK — a ideia ja foi comunicada
- Sem ansiedade de qualidade. Nao e produto, nao e codigo de producao. E rascunho funcional
- Pode ser invocado dentro de outras skills (ex: durante /pesquisa, "vou fazer um prototipo rapido pra mostrar")
