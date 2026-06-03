# Frontend Direction — blog do edge

> Boas práticas copiadas do agentops (`acessoverde-agentops`, host petertosh). Mesmo
> stack e disciplina; domínio adaptado (blog de artefatos de pesquisa, não CRM).

O blog é **server-rendered. Não é SPA.**

## Stack
- **Flask + Jinja** para páginas.
- **htmx** para updates parciais e ações inline (retorna **HTML partial**, não JSON).
- **Tabler/Bootstrap 5** como base de UI.
- **Alpine.js** só para estado local de UI (dropdowns, tabs, copy-button).
- Vanilla JS mínimo só quando htmx não cobre.
- **Proibido** sem pedido explícito: React, Vue, Next.js, Tailwind, build pipeline custom.

## UX Catalog (style guide vivo)
- `/ux-catalog` mostra todo componente padronizado: tokens, tipografia, cores,
  botões, badges, tags, cards, modais, navegação, layout, e os macros Jinja.
- **Antes de criar um componente visual, cheque o `/ux-catalog`** — pode já existir.
- Ao adicionar componente/variante, **adicione ao catálogo** para ele ficar vivo.

## Sistema visual (de `static/style.css`)
- Tema **escuro**; fontes **IBM Plex Sans / Mono**.
- Tokens (CSS custom properties): `--bg/--surface/--border/--text/--text-muted`,
  `--accent #6e7bf2`, `--green/--yellow/--red`.
- Faixa de topo **reggae** (`--reggae-flag` / `.rasta-stripe`) — a assinatura visual.
- `style.css` foi copiado do agentops; **podar** classes específicas de CRM
  (kanban, leads, chat, stage-viewer) conforme formos usando; manter tokens, base,
  tipografia, code, cards, botões, badges.

## Work in place
- Um servidor (`blog/server.py`), um `static/style.css`. **Nada** de `_v2/_new/_old`.
- Refatorar no lugar, salvo pedido explícito de protótipo lado-a-lado.

## Componentes / macros Jinja (reutilizáveis)
- `templates/base.html`, `templates/components/`, `templates/partials/`, `templates/pages/`.
- Páginas **não inventam** botão/badge/input/card/modal — usam componentes compartilhados.
- HTML repetido em dois lugares → **extrair macro** antes de continuar.

## Regras de template
- Páginas completas em `pages/` estendem `base.html`.
- Fragmentos htmx em `partials/` — sem o shell da página.
- HTML repetido vira macro em `components/`.

## Regras de CSS
- CSS custom pequeno e específico; utilitários Tabler/Bootstrap primeiro.
- Sem sistemas de classe one-off por página; sem redesign decorativo/marketing.
- Denso, operacional, mobile-friendly.

## Domínio do blog (o que o blog mostra)
- **Lista de entries** (artefatos de pesquisa) — cards.
- **Render do artefato HTML** (o relatório: lineage/gaps/glossário/exec-summary/
  métricas/bibliografia/SVG) — tipografia + code + cards.
- **Badges de estado** (`state:ok` / `degraded`).
- Sem kanban/leads/chat — isso é do CRM, não do blog.
