"""The publisher — the close pipeline's atomic publish seam (ADR-0012/0013).

`consolidate-state` minus session-digestion (0008 moved digestion to the pull-at-open
sweep), de-YAML'd. One act: render the Artefato body (render.spec_to_html), wrap it in a
self-contained neutral HTML page that INLINES the neutralized tools/assets/base.css, write
it to blog/entries/<slug>.html, then ATOMICALLY record state via the eventlog — the
`artefato.published` event AND its `intent.kernel` together (eventlog.publish_artefato_atomic),
plus a `source.signal` per cited snippet. Because the kernel rides in the same call,
`artefatos_without_kernel(log) == []` right after, and there is no path that publishes
without the *why*: C3 is enforced at this seam (the publisher raises with no intent).

Pure import-clean spine: imports only eventlog + render + close (the close-role functions);
the impure embedder is injectable (embed_fn) so a test runs offline.
"""
from datetime import date as _date
from pathlib import Path

import eventlog
import render
from close import check_genus

REPO = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO / "blog" / "entries"
BASE_CSS = Path(__file__).resolve().parent / "assets" / "base.css"


def _page(slug, body_html, *, skill, date, css):
    """Wrap the rendered body in a self-contained neutral HTML page (no tricolor stripe —
    the neutralized base.css has no .header-stripe). Matches the existing entry shape:
    `<article class="report">` with `<p class="meta">{date} · {skill}</p>`."""
    title = slug.replace("-", " ")
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{css}\n</style></head>\n"
        '<body><article class="report">\n'
        f"<h1>{title}</h1>\n"
        f'<p class="meta">{date} · {skill}</p>\n\n'
        f"{body_html}\n"
        "</article></body></html>\n"
    )


def _signal_cites(slug, body, cites, embed_fn, log):
    """Emit one `source.signal` per cited snippet (ADR-0009). With an injected embed_fn the
    signal is the cosine(embed(snippet), embed(body)) score (offline-testable); without one
    the cite still records, scored 0.0 — the publish never depends on a network call."""
    for c in cites:
        if not (isinstance(c, dict) and c.get("snippet")):
            continue
        if embed_fn is not None:
            sim = eventlog.cosine(embed_fn(c["snippet"]), embed_fn(body))
        else:
            sim = 0.0
        eventlog.source_signal(slug, c.get("ref"), c.get("kind"), sim, log=log)


def publish(slug, spec, intent, *, skill, proposes=None, distills=None, cites=None,
            date=None, log=eventlog.LOG, blog_dir=BLOG_DIR, embed_fn=None) -> Path:
    """Publish an Artefato: render → self-contained neutral HTML → atomic state record.

    C3 at the seam: RAISES ValueError when `intent` is missing/empty — you cannot publish
    without the kernel (and defensively when the genus contract is violated). Returns the
    written page Path. `date` is a param (defaults to today) so tests pin it; `embed_fn` is
    injectable so the source-signal step runs offline.
    """
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")

    cites = cites or []
    artefato = {"intent": intent, "proposes": proposes or [], "cites": cites,
                "content": spec}
    violations = check_genus(artefato)
    if violations:
        raise ValueError(f"artefato {slug!r} violates the genus contract: {violations}")

    body_html = render.spec_to_html(spec)
    css = BASE_CSS.read_text()
    page = _page(slug, body_html, skill=skill, date=date or _date.today().isoformat(), css=css)

    blog_dir = Path(blog_dir)
    blog_dir.mkdir(parents=True, exist_ok=True)
    out = blog_dir / f"{slug}.html"
    out.write_text(page)

    eventlog.publish_artefato_atomic(slug, intent, proposes=proposes, distills=distills,
                                     cites=cites, log=log)
    _signal_cites(slug, body_html, cites, embed_fn, log)
    return out
