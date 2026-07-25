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
**O benchmark é o RELICÁRIO, não o vencedor local (operador, 2026-07-05):** "os do edge no netlify dão de 10 nesse que ganhou aí." A formB venceu o páreo das 3 formas mas está 10× abaixo do teto. Critério final do teste de arms: o output para em pé AO LADO de um artefato do netlify (Lorenz-3D, kuramoto, editorial-compass) — não basta vencer os irmãos. A escolha cega do operador julga contra ESSA régua.
**O DELTA 10× nomeado (comparação minha, compass vs formB, 2026-07-05):** o compass é INSTRUMENTO, a formB é documento. A riqueza = (1) carrega um MODELO DE JUÍZO reusável (serve pra qualquer achado, pra sempre), não um dataset; (2) ARQUÉTIPOS clicáveis ensinam a taxonomia (a forma de cada tipo no radar); (3) DECIDE — a saída é recomendação acionável (seção+score), não fato; (4) a REGRA GERAL escrita ao lado da interação (o mecanismo nomeado); (5) estética com voz própria (signature element). Regra pra skill: quando o material permitir, aspire ao INSTRUMENTO (o leitor volta a usar), não ao relato animado (lê uma vez). E: constraints duras são de caso específico — a skill dá LIBERDADE com invariantes (single-file, dado real, ensina), goal-level, nunca checklist prescritivo.
**Veredito do teste de arms (operador, 2026-07-05): DEFERIDO para conteúdo rico.** "Vou esperar ela com conteúdo rico — com grounding genérico é tirar leite de pedra. Mas os resultados ficaram legais." Os 3 outputs (blind, x/y/z no blog local; mapa selado em drafts/skill-proto-arms/BLIND-MAP.txt) ficam congelados; o julgamento cego acontece quando o FLUXO REAL (proposta→rounds→consolidação) alimentar a skill com grounding de verdade — o experimento real é com tudo implementado. As 3 skill-variants preservadas em drafts/skill-proto-arms/SKILL-arm-{1,2,3}.md.
