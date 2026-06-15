# Frontend Direction — blog do edge

> **Canonical front-end doc.** Reconciles the former root `FRONTEND.md` (the
> server-rendered/htmx/islands rationale + the cheap-on-resources constraint) with the
> petertosh-aligned organization (Jinja scaffold, Tabler, the `/ux-catalog`). Root
> `FRONTEND.md` is now a pointer here. Companion to `SURFACE.md` (what to expose) and
> `CONTEXT.md` (what words mean). UX decisions are challenged against these constraints.
>
> Modelo mental (organização, do agentops / host petertosh): convenções, stack,
> scaffolding, disciplina — copiadas. A identidade visual é própria (a dark theme do edge).

O dashboard é **server-rendered** (Flask + Jinja). Cada página é uma **projeção do event log**
(ADR-0005/0006): o servidor dobra o log (e o grafo) em HTML a cada request — sem store paralelo
no cliente, sem build step.

## Stack
- **Flask + Jinja** para páginas. O scaffold: `templates/base.html` (chrome) + `partials/`
  (head, nav) + `components/` (macros) + `pages/` (cada superfície estende o base).
- **htmx** para updates parciais e ações inline (retorna HTML partial) — progressive enhancement
  sobre o HTML server-rendered, **não um SPA**. Postar comentário/voto, ver estado
  respondido/votado, renderizar replies = fragment swaps. O servidor permanece autoritativo.
- **Tabler/Bootstrap 5** como vocabulário de componentes (grid, cards, badges, forms).
- **JS islands só onde a view é inerentemente interativa.** O navegador do grafo (`/cortex`:
  pan / zoom / click) é uma lib de grafo (Cytoscape) embutida numa página server-rendered — uma
  *island*, nunca o app shell. A lib pesada nunca toca as páginas read-mostly.
- Vanilla JS mínimo quando htmx não cobre.

## Hard constraint — cheap on resources
Sem framework client pesado. **Um bundle React/SPA — o `node_modules` de 1–3 GB, o ship de
múltiplos MB — está fora**; um install OSS não deve pagar isso para ler o próprio edge. O
footprint fica: Python + Flask + Jinja + um stylesheet + Tabler (CSS) + htmx (~48 KB,
self-hosted) + uma lib de grafo carregada *só* na view do grafo. Interface rica, sapatos leves.

### Por quê (o trade-off)
Um SPA compra interatividade client mais rica ao custo de um build pipeline, um modelo de estado
client paralelo (a falha #1 de dashboard que a física log-native existe pra deletar), e um install
pesado. Para um dashboard operacional single-user, read-mostly, cujas páginas são projeções do
log, htmx + islands dão a riqueza — incluindo navegação de grafo — sem nenhum desse custo. O teto:
se uma view algum dia precisar de live-collab ou estado local pesado, *aquela view* vira uma
island; o app shell nunca.

## Supply chain — self-hosted, no CDN (Slice 7 #37)
Todo JS/CSS de terceiros é **vendored** em `blog/static/vendor/` e servido localmente — **nenhum
`<script src="https://…">` de CDN** em nenhuma página. Fecha o achado de supply-chain (um CDN é
uma dependência de execução remota numa superfície authed). Versões pinadas:
- `vendor/htmx.min.js` — htmx 1.9.12
- `vendor/cytoscape.min.js` — Cytoscape 3.30.2 (só carregada em `/cortex`)
- `vendor/tabler.min.css` — Tabler 1.0.0-beta20

## UX Catalog (style guide vivo)
- `/ux-catalog` mostra todo componente padronizado: tokens, cores, botões, badges, chips, cards,
  threads, steer cards, health metrics, navegação, e os macros Jinja. Os **tokens são parseados
  ao vivo** do `style.css` `:root`, então o catálogo nunca diverge do stylesheet.
- Antes de criar um componente, cheque o `/ux-catalog` — pode já existir.
- Ao adicionar componente/variante, registre-o (o macro em `components/ui.html`, o exemplo na
  página do catálogo) para ele ficar vivo.

## Sistema visual — identidade própria sobre organização copiada
- Do agentops copiamos a **organização**: o sistema de **tokens em `:root`**
  (`--bg/--surface/--border/--text/--accent/--ok/--warn/--err`) e a disciplina do `/ux-catalog`.
- A **identidade é a dark theme do edge** (aprovada pelo operador): o `static/style.css` é a fonte
  da verdade da paleta. O Tabler dá o vocabulário de componentes mas é **light por default** —
  então `style.css` carrega **depois** do Tabler e mapeia os tokens do edge nas variáveis
  `--tblr-*` (o "Tabler bridge" no fim do stylesheet), pra que os componentes Tabler herdem a dark
  theme em vez de regredir pro branco. Componentes vêm do Tabler; a paleta/identidade fica a do edge.

## Work in place
- Um servidor (`blog/server.py`), um `static/style.css`, o scaffold `templates/`. Refatorar no lugar.

## Componentes / macros Jinja (reutilizáveis)
- `templates/base.html`, `templates/partials/` (head, nav), `templates/components/` (macros),
  `templates/pages/` (uma por superfície).
- Páginas usam componentes compartilhados para botão/badge/input/card/composer.
- HTML repetido em dois lugares → extrair macro em `components/ui.html` antes de continuar.

## Regras de template
- Páginas completas em `pages/` estendem `base.html`.
- Fragmentos htmx (os swaps de thread/voto/chat) são montados pelos render-helpers em
  `blog/server.py` (cada um devolve só o fragmento), threaded na página como Markup já-escapado.
- HTML repetido vira macro em `components/ui.html`.

## Regras de CSS
- CSS custom pequeno e específico; utilitários Tabler/Bootstrap primeiro.
- Denso, operacional, desktop-first (read-and-direct no teclado; mobile é um Medium diferente).

## Segurança das superfícies (boundaries)
- **Voz writes**: todo route log-mutante passa pelo gate auth + CSRF/origin + `target_ref`
  validation + body-size limit (Slice 1), via o append canônico do `eventlog`.
- **Docs** (`/docs`): markdown → HTML **inerte** pelo sanitizer allowlist compartilhado (`docmd`).
- **Wiki** (`/wiki`): HTML edge-gerado isolado num `<iframe sandbox>` + CSP `default-src 'none'`
  na sub-rota `/raw` — scripts nunca rodam, nunca alcançam o parent origin same-origin.

## Domínio do dashboard (o que cada superfície mostra)
- **Blog** (`/`): lista de entries (Artefatos) — cards — + o render do artefato HTML + o Voz rail.
- **Chat** (`/chat`): o timeline unificado de `voz.*`.
- **Cortex** (`/cortex`): a island do grafo (read-only surf da brain).
- **Briefing** (`/briefing`): a self-state landing + o health strip do read-model.
- **Direction** (`/direction`): os dois tiers de steers (set curado / proposed candidato).
- **Docs** (`/docs`) e **Wiki** (`/wiki`): a documentação navegável e os Knowledge clusters.
- **Badges de estado** (`state:ok` / `degraded`).
