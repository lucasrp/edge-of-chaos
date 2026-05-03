from __future__ import annotations

import html
import shutil
from pathlib import Path

from .config import RuntimeConfig
from .context import ContextPacket
from .reviewers import ReviewResult, summarize_reviews
from .search import SearchResult
from .util import date_slug, slugify, truncate


def draft_report(packet: ContextPacket, searches: list[SearchResult], thread_id: str) -> str:
    observations = "\n".join(f"- **{obs.source}:** {obs.title} — {truncate(obs.detail, 300)}" for obs in packet.observations[:12])
    reports = "\n".join(f"- {item.get('title')} ({item.get('path')})" for item in packet.report_candidates[:6]) or "- Nenhum report anterior encontrado."
    search_lines = "\n".join(f"- **{result.source}:** {result.title} {result.url} — {truncate(result.summary, 250)}" for result in searches)
    interests = "\n".join(f"- {item.get('area')}: {item.get('connection')}" for item in packet.interests[:5])
    return f"""# {packet.kind.title()}: {packet.request}

## Thread

This beat continues or creates thread `{thread_id}`.

## Contexto Observado

{observations}

## Continuidade

Reports candidatos:

{reports}

## Modelo Simples

O mentor deve partir do trabalho real observado, identificar o delta e transformar isso em uma orientacao que ajude o mentorado a pensar e agir melhor. Se o contexto ainda estiver fino, o report deve dizer isso em vez de fabricar certeza.

## Busca Ampla

{search_lines}

## Interesses Fenotipicos Relevantes

{interests or "- Nenhum interesse configurado."}

## Derivacao

1. O pedido/beat atual aponta para: {packet.request}
2. O contexto recente mostra evidencias do workspace, historico de reports, threads e sessoes.
3. A recomendacao precisa continuar uma thread real ou abrir uma nova com justificativa.
4. O report deve preservar o rito: busca ampla, adversarial, review, Feynman review e fechamento com proximos passos.

## Gaps

- Confirmar se a thread escolhida representa a linha viva correta.
- Confirmar se as fontes externas configuradas foram suficientes ou se houve fallback local.
- Confirmar se ha report anterior que deveria ter sido recuperado e nao foi.

## Recomendacao

Continuar com uma consulta privada rica, ancorada no delta e sem mutar o workspace do mentorado. O proximo passo e usar este report como base para atualizar a thread e melhorar a proxima consulta.

## Proximos Passos

- Revisar a aderencia do report ao trabalho real observado.
- Atualizar a thread compacta com o entendimento novo.
- Se a busca ficou degradada por falta de credenciais, configurar as fontes do fenotipo.
"""


def finalize_report(config: RuntimeConfig, *, packet: ContextPacket, draft: str, reviews: list[ReviewResult], thread_id: str) -> Path:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(f"{packet.kind}-{packet.request}")[:90]
    path = config.reports_dir / f"{date_slug()}-{slug}.md"
    final = draft.rstrip() + "\n\n## Reviews\n\n" + summarize_reviews(reviews) + "\n"
    path.write_text(final, encoding="utf-8")
    config.blog_entries_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, config.blog_entries_dir / path.name)
    return path


def build_blog(config: RuntimeConfig) -> Path:
    entries = sorted(config.blog_entries_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for path in entries:
        title = path.stem
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        rows.append(f'<li><a href="entries/{html.escape(path.name)}">{html.escape(title)}</a></li>')
    index = config.root / "blog" / "index.html"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(
        "<!doctype html><meta charset='utf-8'><title>edge reports</title>"
        "<style>body{font-family:system-ui;margin:3rem;max-width:820px}li{margin:.6rem 0}</style>"
        "<h1>edge-of-chaos reports</h1><ul>" + "\n".join(rows) + "</ul>",
        encoding="utf-8",
    )
    return index
