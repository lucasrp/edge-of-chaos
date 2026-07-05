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

## A rubrica de gates do JS (fechada 2026-07-05; parte shipped no C, parte follow-up do PAR)
| gate | tipo | estado |
|---|---|---|
| **ensina?** (a interação carrega o insight) | semântico, converge | ✅ shipped (C) |
| **never-forced** (conteúdo não pede → não põe) | semântico | ✅ shipped (C) |
| **render→ver→revisar** (o produtor VÊ antes de shipar) | rito | ✅ shipped (C, degrada honesto) |
| substância + passabilidade AND | close (B.4) | ✅ herda do close |
| **roda-sem-erro** (headless abre, console limpo) | MECÂNICO, veto | ⬜ follow-up (hoje é rito, não veto) |
| **single-file/zero-dep lint** (sem CDN, sem fetch externo de lib) | mecânico | ⬜ follow-up |
| **dado REAL** (ancorado no dado do artefato-par, não inventado) | semântico | ⬜ follow-up (nasce com o PAR) |

## Plano de TESTE da skill (operador: "teste algumas versões")
Quando o dig do craft voltar (memory/js-artefato-craft.md): montar 2-3 VERSÕES da skill prototype (ex.: a atual do C · a atual+regras-de-craft · craft+alma-do-relicário "show instead of explain") → cada uma gera o MESMO artefato JS (mesma pauta, dado real) → render→ver + gates (roda/ensina/passabilidade) → escolher a vencedora às cegas (arms, como manda a casa). A vencedora vira a skills/prototype/SKILL.md canônica.
