"""The publisher — the close pipeline's atomic publish seam (ADR-0012/0013).

`consolidate-state` minus session-digestion (0008 moved digestion to the pull-at-open
sweep), de-YAML'd. One act: render the Artefato body (render.spec_to_html), wrap it in a
self-contained neutral HTML page that INLINES the neutralized tools/assets/base.css, record
state ATOMICALLY via the eventlog — the `artefato.published` event AND its `intent.kernel`
together in one indivisible write (eventlog.publish_artefato_atomic) — then write the page to
blog/entries/<slug>.html via temp+rename, plus a `source.signal` per cited snippet. The log is
truth, the page a re-derivable projection, so state lands before the file (#3) and a failed
write never orphans a page.

Three gates at this seam: #2/#3 — the publisher REFUSES unless handed the UNFORGEABLE, BOUND
proof `close.run_close` mints: `close.verify_proof` requires the run_close-only token, a sha256
digest that BINDS to this exact publish payload (slug + spec + intent + cites + proposes +
distills + skill — EVERY persisted publish arg, so distills/skill cannot be altered post-mint to
poison provenance), both blind reviewers passed, AND the verdicts carry both CANONICAL reviewer
identities — so a forged dict, a stale/cross-artefato proof (digest mismatch), a single-reviewer
proof, or a proof built from fake/injected reviewers cannot back-door the gate. C3 — there is no path that publishes
without the *why* (raises with no intent; the kernel rides the same atomic call so
`artefatos_without_kernel(log) == []` right after). #4 — the slug is validated against a strict
regex and contained under blog_dir (a `../` slug cannot escape).

Pure import-clean spine: imports only eventlog + render + close (the close-role functions);
the impure embedder is injectable (embed_fn) so a test runs offline.
"""
import os
import re
from datetime import date as _date
from pathlib import Path

import eventlog
import render
from close import check_genus, verify_proof

REPO = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO / "blog" / "entries"
BASE_CSS = Path(__file__).resolve().parent / "assets" / "base.css"

# A slug names a single file under blog_dir — lowercase alphanumerics + hyphens, no leading
# or trailing hyphen, no dots/slashes/spaces. Anything else is rejected (#4: path traversal).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _safe_target(slug, blog_dir):
    """Resolve the page path for `slug` and ASSERT it stays under blog_dir (#4). A slug that
    fails the strict regex or whose resolved path escapes blog_dir raises ValueError before
    anything is written — `../` cannot climb out, an empty/funny slug cannot land elsewhere."""
    if not (isinstance(slug, str) and SLUG_RE.match(slug)):
        raise ValueError(f"invalid slug {slug!r}: must match {SLUG_RE.pattern} (#4)")
    blog_dir = Path(blog_dir).resolve()
    target = (blog_dir / f"{slug}.html").resolve()
    if target.parent != blog_dir:
        raise ValueError(f"slug {slug!r} escapes the blog dir (#4)")
    return target


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


def publish(slug, spec, intent, *, skill, verdict=None, proposes=None, distills=None,
            cites=None, date=None, log=eventlog.LOG, blog_dir=BLOG_DIR, embed_fn=None) -> Path:
    """Publish an Artefato: render → self-contained neutral HTML → atomic state record.

    #2/#3 at the seam: RAISES ValueError unless `verdict` is the UNFORGEABLE, BOUND proof
    `close.run_close` mints — `close.verify_proof` requires the run_close-only token, a digest
    that BINDS to THIS exact payload (slug + spec + intent + cites + proposes + distills +
    skill), both blind reviewers passed, and both CANONICAL reviewer identities are present. A
    hand-built dict, a proof minted for a different artefato (digest mismatch), an altered
    distills/skill, a single-reviewer proof, or a proof from fake reviewers raises here, before
    any HTML or state lands — the publisher is never a back door around the gate. C3 at the seam: RAISES when `intent` is
    missing/empty — you cannot publish without the kernel (and defensively when the genus
    contract is violated). #4 at the seam: the slug is validated + contained under blog_dir,
    the page written via temp+rename.

    Order (#3): render the page in memory, record state, THEN write the HTML — the log is truth,
    the page a re-derivable projection, so a failed write never leaves an orphan page. Returns
    the written page Path. `date` is a param (defaults to today) so tests pin it; `embed_fn`
    is injectable so the source-signal step runs offline.
    """
    verify_proof(verdict, slug=slug, spec=spec, intent=intent,
                 cites=cites or [], proposes=proposes or [],
                 distills=distills, skill=skill)
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")

    out = _safe_target(slug, blog_dir)

    cites = cites or []
    artefato = {"intent": intent, "proposes": proposes or [], "cites": cites,
                "content": spec}
    violations = check_genus(artefato)
    if violations:
        raise ValueError(f"artefato {slug!r} violates the genus contract: {violations}")

    body_html = render.spec_to_html(spec)
    css = BASE_CSS.read_text()
    page = _page(slug, body_html, skill=skill, date=date or _date.today().isoformat(), css=css)

    eventlog.publish_artefato_atomic(slug, intent, proposes=proposes, distills=distills,
                                     cites=cites, log=log)
    _signal_cites(slug, body_html, cites, embed_fn, log)

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".html.tmp")
    tmp.write_text(page)
    os.replace(tmp, out)
    return out
