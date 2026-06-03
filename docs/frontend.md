# Frontend Direction — blog do edge

> Copiamos do agentops (`acessoverde-agentops`, host petertosh) a **organização**:
> convenções, stack, scaffolding, disciplina. A identidade visual é própria. Modelo
> mental: a equipe deles iniciando um projeto novo.

O blog é **server-rendered** (Flask + Jinja).

## Stack
- **Flask + Jinja** para páginas.
- **htmx** para updates parciais e ações inline (retorna HTML partial).
- **Tabler/Bootstrap 5** como base de UI.
- **Alpine.js** para estado local de UI (dropdowns, tabs, copy-button).
- Vanilla JS mínimo quando htmx não cobre.

## UX Catalog (style guide vivo)
- `/ux-catalog` mostra todo componente padronizado: tokens, tipografia, cores,
  botões, badges, tags, cards, modais, navegação, layout, e os macros Jinja.
- Antes de criar um componente, cheque o `/ux-catalog` — pode já existir.
- Ao adicionar componente/variante, registre no catálogo para ele ficar vivo.

## Sistema visual — identidade própria, organização copiada
- Do agentops copiamos a **organização**: o sistema de **tokens em `:root`**
  (`--bg/--surface/--border/--text/--accent/--ok/--warn/--err`) e a disciplina do `/ux-catalog`.
- A identidade (cores/fontes) é do blog, a definir — `static/style.css` começa neutro.

## Work in place
- Um servidor (`blog/server.py`), um `static/style.css`. Refatorar no lugar.

## Componentes / macros Jinja (reutilizáveis)
- `templates/base.html`, `templates/components/`, `templates/partials/`, `templates/pages/`.
- Páginas usam componentes compartilhados para botão/badge/input/card/modal.
- HTML repetido em dois lugares → extrair macro antes de continuar.

## Regras de template
- Páginas completas em `pages/` estendem `base.html`.
- Fragmentos htmx em `partials/` (só o fragmento).
- HTML repetido vira macro em `components/`.

## Regras de CSS
- CSS custom pequeno e específico; utilitários Tabler/Bootstrap primeiro.
- Denso, operacional, mobile-friendly.

## Domínio do blog (o que o blog mostra)
- **Lista de entries** (artefatos de pesquisa) — cards.
- **Render do artefato HTML** (o relatório: lineage/gaps/glossário/exec-summary/
  métricas/bibliografia/SVG) — tipografia + code + cards.
- **Badges de estado** (`state:ok` / `degraded`).
