# C — Artefato JS interativo (conceito e qualidade = o blog do Netlify)

Ticket C do wayfinder (paralelo a A). **A régua é o relicário** (operador, 2026-07-05): `edge-of-chaos.netlify.app` — 19 artefatos single-file interativos (Lorenz-3D sem three.js, editorial-compass, kuramoto).

## O conceito (a barra do `prototype` do relicário — `drafts/relicario/ed-20260417/skills/prototype/`)
- **Single-file, self-contained, zero-dep** (HTML+JS+CSS num arquivo; sem CDN, sem build).
- **RODA** — o rito render→ver→revisar (o produtor abre e vê antes de shipar).
- **Interativo que ENSINA** — a interação carrega o insight (gate: "a interatividade ensina?"); NUNCA forçada — se o conteúdo não pede, não põe.
- **Ancorado em dado REAL** (o experimento literal embutido quando houver — "se fiz um experimento, por que não mostrar ele literalmente"; interatividade ≠ riqueza visual, é OUTRA dimensão).

## O que destrava no runtime
- O publisher vivo **sanitiza `<script>`** (blocks.py→sanitize_raw_html) — o genus interativo precisa de um caminho de publicação PRÓPRIO (página standalone content-addressed, não bloco sanitizado no template). A capacidade regrediu desde abril; C a restaura como genus de 1ª classe no roster.
- JS-artefato = ferramenta NATIVA (duas faces: UI-humana + lógica-headless) → é a rampa do /artefato (#69) e do /app (#70).
- Netlify key: `drafts/relicario/ed-20260417/secrets/netlify.env`.
