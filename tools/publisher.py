"""The publisher — the close pipeline's atomic publish seam (ADR-0012/0013).

`consolidate-state` minus session-digestion (0008 moved digestion to the pull-at-open
sweep), de-YAML'd. One act: render the Artefato body (render.spec_to_html), wrap it in a
self-contained neutral HTML page that INLINES the neutralized tools/assets/base.css, record
state ATOMICALLY via the eventlog — the `artefato.published` event (carrying the proof-bound
SPEC, so the page is fully regenerable from the log) AND its `intent.kernel` together in one
indivisible write (eventlog.publish_artefato_atomic) — THEN write the page to
blog/entries/<slug>.html via temp+rename, THEN emit a `source.signal` per cited snippet.

ADR-0006: the log is truth, the page a re-derivable PROJECTION. The atomic event is the COMMIT
POINT; everything after it is a recoverable projection. So a page-write/replace/signal failure
after the commit no longer strands an UNRECOVERABLE state (Codex round-10 [high]): the logged
spec re-renders the exact page and the logged cites re-emit the missing signals via
`reproject_missing_pages`. Source-signal emission is non-fatal to the page (#4).

Three gates at this seam: #2/#3 — the publisher REFUSES unless handed the UNFORGEABLE, BOUND
proof `close.run_close` mints: `close.verify_proof` requires the run_close-only token, a sha256
digest that BINDS to this exact publish payload (slug + spec + intent + cites + proposes +
distills + skill + lineage — EVERY persisted publish arg, so distills/skill/lineage cannot be
altered post-mint to poison provenance), both blind reviewers passed, AND the verdicts carry both CANONICAL reviewer
identities — so a forged dict, a stale/cross-artefato proof (digest mismatch), a single-reviewer
proof, or a proof built from fake/injected reviewers cannot back-door the gate. C3 — there is no path that publishes
without the *why* (raises with no intent; the kernel rides the same atomic call so
`artefatos_without_kernel(log) == []` right after). #4 — the slug is validated against a strict
regex and contained under blog_dir (a `../` slug cannot escape).

Pure import-clean spine: imports only eventlog + render + close (the close-role functions) at
module scope; the impure embedder (embed_fn) and the graph projection (project_fn, the
project-after-publish side-effect — #30) are injectable so a test runs offline. The default
projection (`project_artefato`) imports neo4j/_identity/openai LAZILY and is fully degrade-safe:
a missing group/driver/key prints and returns, never raising into the publish (ADR-0011/0006).
"""
import hashlib
import html
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from datetime import date as _date
from datetime import datetime as _dt
from datetime import timezone as _tz
from pathlib import Path

import cortex
import eventlog
import render
import close
import producer_descriptor
from close import check_genus, verify_proof
# canonical authored declarations through persist + projection (each matches its proof bind)
from lineage import (normalize_bears_on, normalize_experiment_curation, normalize_lineage,
                     normalize_para, normalize_reports_on)

# R6 (S10) — adoption telemetry. Visual/labeled block types that, when a producer's DESCRIPTOR requires
# them, mean the FORM owes a visual (the form half of the `owed` signal; the content half is
# close.content_owes_visual). Mirrors the producer-descriptor visual recipes.
_VISUAL_REQUIRE_TYPES = frozenset({
    "diagram", "chart", "ascii-diagram", "comparison", "comparison-table",
    "metrics-grid", "next-steps-grid", "flow-example",
})


def _form_owes_visual(skill) -> bool:
    """True iff the producer's DESCRIPTOR declares a visual-form floor that is OWED at this publish. The
    floor is CAPABILITY-CONDITIONAL (S6/R1): its types are renderable (diagram/chart), so when `vl-convert`
    is ABSENT the floor degrades to not-owed (ENV_UNSAT) — telemetry must not count it as owed then, or the
    adoption denominator is corrupted (Codex S7 #2)."""
    def _types(rule):
        ts = set(rule.get("types", []) or [])
        for opt in rule.get("options", []) or []:
            ts |= _types(opt)
        return ts
    declared = set()
    for rule in producer_descriptor.DESCRIPTORS.get(skill, {}).get("require", []) or []:
        declared |= _types(rule)
    if not (declared & _VISUAL_REQUIRE_TYPES):
        return False
    # the declared visual types are all renderable (vl-convert) — owed only when the backend is present.
    return bool(render.diagram_available())


def _normalize_visual_flags(visual_flags):
    """Derive (degraded, shortfall) from the producer's flags — accepts a structured dict
    `{degraded, shortfall}` OR the `list[str]` that `visuals.add_visuals` actually returns (entries like
    `'shortfall: N spot(s) selected, M grounded'` / `'dropped spot i (kind): reason'` / a degradation
    marker). So a real publish that forwards add_visuals' list is not silently reported as healthy."""
    if visual_flags is None:
        return False, False     # no flags supplied → not degraded, no shortfall
    if isinstance(visual_flags, dict):
        degraded, shortfall = visual_flags.get("degraded", False), visual_flags.get("shortfall", False)
        if not isinstance(degraded, bool) or not isinstance(shortfall, bool):
            # a non-bool flag value (e.g. the string "false") must NOT be coerced into countable telemetry
            # (bool("false") is True); raise so `_adoption_event` records an all-null error instead.
            raise ValueError(f"visual_flags degraded/shortfall must be bools, got {visual_flags!r}")
        return degraded, shortfall
    if isinstance(visual_flags, list):     # only a real list (add_visuals' shape); not tuple/other
        joined = " ".join(str(f) for f in visual_flags).lower()
        return ("degrad" in joined), ("shortfall" in joined or "dropped spot" in joined)
    raise ValueError(f"visual_flags must be a dict, list, or None, got {type(visual_flags).__name__}")


def _adoption_event(slug, skill, spec, visual_flags):
    """The durable adoption-telemetry payload emitted AT publish (R6): per artefato + producer, whether the
    form/content OWED a visual, whether one was SATISFIED, and the producer-supplied degraded/shortfall
    flags + the publish-time render capability. The report/dashboard reads this stream — it never
    reconstructs `owed`/capability from a retrospective corpus scan.

    SELF-DEFENSIVE (Codex S10): this NEVER raises — a telemetry/capability-probe failure must not drop the
    adoption record (which would silently under-count adoption). On any compute error it returns the
    payload with null fields and an `error` marker, so EVERY publish still commits an adoption event."""
    payload = {"slug": slug, "producer": skill, "owed": None, "satisfied": None,
               "degraded": None, "shortfall": None, "capability_state": None, "error": None}
    # compute into LOCALS and commit to the payload only after EVERY probe succeeds (Codex S10): a late
    # failure (e.g. the capability probe) must not leave partially-computed or default-False booleans that
    # a dashboard would count — an errored record exposes ALL countable fields NULL + the error marker.
    try:
        owed = bool(_form_owes_visual(skill) or close.content_owes_visual(spec))
        satisfied = bool(close.has_substantive_visual(spec))
        degraded, shortfall = _normalize_visual_flags(visual_flags)
        capability_state = bool(render.diagram_available())
    except Exception as e:  # noqa: BLE001 — telemetry ALWAYS emits a record, never silently drops it
        payload["error"] = f"{type(e).__name__}: {e}"
        return payload
    payload.update(owed=owed, satisfied=satisfied, degraded=degraded,
                   shortfall=shortfall, capability_state=capability_state)
    return payload

REPO = Path(__file__).resolve().parent.parent
import _identity as _id_state
BLOG_DIR = _id_state.state_root() / "blog" / "entries"   # fenotipo: home do install, nunca o genotipo
BASE_CSS = Path(__file__).resolve().parent / "assets" / "base.css"
BASE_JS = Path(__file__).resolve().parent / "assets" / "page.js"

# Entries are written for the mentee in PT-BR and the wrapper must say so (screen
# readers, hyphenation and translators key on the lang attribute). One seam to
# change if that ever stops being true — never sniffed per-entry from content.
PAGE_LANG = "pt-BR"

# A slug names a single file under blog_dir — lowercase alphanumerics + hyphens, no leading
# or trailing hyphen, no dots/slashes/spaces. Anything else is rejected (#4: path traversal).
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# The allowed producer roster — the only skills that may close an Artefato (the beat's
# producer-skills). `skill` is proof-bound but the proof binds whatever the producer supplies,
# so an out-of-roster value (e.g. `report</p><script>…`) would verify cleanly; this roster is
# the gate that rejects it BEFORE anything is written, and _page escapes it as defense in depth.
PRODUCER_ROSTER = ("report", "research", "map", "plan", "discovery", "mentor", "grill",
                   "prototype", "lazer", "critique")

# Cortex-v1 (brick-1, L4): the AUTHORED typed lineage relations and their graph-edge labels — a
# FIXED Python allowlist. The producer-supplied `item["type"]` is mapped through THIS dict; an
# out-of-allowlist type is dropped (never linked), and the label NEVER comes from caller data — so
# no caller string is ever interpolated into Cypher. The edge is directed this -> prior.
LINEAGE_LABELS = {"builds_on": "BUILDS_ON", "supersedes": "SUPERSEDES",
                  "contradicts": "CONTRADICTS"}


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


def _page(slug, body_html, *, skill, date, css, js=""):
    """Wrap the rendered body in a self-contained neutral HTML page (no tricolor stripe —
    the neutralized base.css has no .header-stripe). Matches the existing entry shape:
    `<article class="report">` with `<p class="meta">{date} · {skill}</p>`.

    Codex round-4 [high]: reviewers only see slug/content/cites, so the wrapper's own
    caller/spec values (date, skill, the slug-derived title) reach the public page as raw
    HTML if not escaped. `html.escape(quote=True)` ALL wrapper text — no wrapper value may
    inject markup. `body_html` is render.spec_to_html's already-sanitized output, untouched.

    `js` is the repo-controlled assets/page.js (progressive display-only enhancements:
    sumário, diff tint, lightbox), inlined like the css so the page stays self-contained.
    It is NOT caller data and is inlined raw — the only sequence that could break out of
    the <script> element is a closing script tag, which is escaped here as defense in
    depth. Empty js (the default) emits no script element at all, so the page degrades
    to the previous shape."""
    title = html.escape(slug.replace("-", " "), quote=True)
    script = ""
    if js:
        safe_js = js.replace("</script>", "<\\/script>")
        script = f"<script>\n{safe_js}\n</script>"
    return (
        f'<!DOCTYPE html><html lang="{PAGE_LANG}"><head><meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{css}\n</style></head>\n"
        '<body><article class="report">\n'
        f"<h1>{title}</h1>\n"
        f'<p class="meta">{html.escape(date, quote=True)} · '
        f'{html.escape(skill, quote=True)}</p>\n\n'
        f"{body_html}\n"
        f"</article>{script}</body></html>\n"
    )


# --- The STANDALONE single-file publish path (ticket C, generalized by ticket 05) ------------
# The close path sanitizes raw-html (render.sanitize_raw_html strips <script>) — right for a
# block riding inside a rendered page, fatal for an authored interactive page. This separate
# seam publishes the single-file HTML page INTACT (script, inline image and all) at a
# CONTENT-ADDRESSED name — `<slug>.proto.<sha256[:12]>.html` — inside the SAME blog dir, so the
# existing /e/ route serves it with zero server change. The ".proto." infix keeps the namespace
# disjoint from close-published entries (SLUG_RE forbids dots, so `<slug>.html` can never collide).
# Content addressing makes the page immutable: identical bytes are idempotent, changed bytes are a
# NEW address — nothing is ever overwritten in place, and the companion entry's link stays true to
# what its reviewers saw.
# Ticket 05 (operador): JS/imagem LIBERADOS em qualquer artefato — o 04-C vira a regra geral,
# não a exceção. The seam is ROSTER-WIDE now; the ONE hard rule that stays is SINGLE FILE:
# a full document that opens whole by itself (links point outward, the artefato carries
# everything it loads). Out-of-roster skills are still refused.
#
# Single-file/zero-dep is the genus bar (the relicário régua): a network resource load (script src,
# stylesheet link, img/iframe/media src to http(s) or protocol-relative //) is refused — a plain
# <a href> outbound LINK is legal, a link is not a dependency. The semantic gate ("a interatividade
# ensina?") lives in the skill's converge.
# ponytail: this regex is a best-effort AUTHORING LINT, not a security boundary and not a complete
# zero-dep proof — arbitrary inline JS is the whole point of the genus, so it can fetch()/@import an
# external resource anyway (adversarial finding 3, SINAL). It catches the OBVIOUS mistake (a pasted
# CDN <script src>), nothing more. The real boundary is the ORIGIN the page is served on — see the
# SKILL's security model; the upgrade path is a restrictive per-file CSP / off-origin serve.
_PROTO_EXTERNAL_DEP_RE = re.compile(
    r"<(?:script|link|img|iframe|source|video|audio|embed|object|track)\b[^>]*?"
    r"(?:src|href|data)\s*=\s*[\"']?(?:https?:)?//", re.I)

# 04-C follow-up (rubrica: single-file lint MECÂNICO) — the attribute regex misses the RUNTIME
# and CSS loaders: fetch(), JS module import from a CDN (the modern vector: esm.run/jsdelivr),
# dynamic import(), side-effect import / re-export, CSS @import and url(). Same authoring-lint
# caveat as above (best-effort, not a proof: an URL built at runtime, or one quoted inside a
# <pre> code sample, is beyond a grep — adversarial lint #6/#7, accepted ceiling); external-only
# — a data: URI, an inline blob and a same-page relative fetch stay legal. A relative <script src>
# is NOT the lint's job: on the headless file:// run it 404s into a console error, so the
# roda-sem-erro gate vetoes it mechanically (adversarial lint #1).
_PROTO_EXTERNAL_LOADER_RE = re.compile(
    # quoted-URL loaders (quote REQUIRED so `fetch(\n  // comment` can't false-positive)
    r"(?:(?:\bfetch\s*\(\s*|\bimport\s*\(\s*|\bimport\s+|\bimport\b[^;()]{0,120}?\bfrom\s+|"
    r"\bexport\b[^;{}]{0,120}?\bfrom\s+)[\"']"
    # CSS loaders, where an unquoted url is legal syntax
    r"|(?:@import\s+|\burl\(\s*)[\"']?"
    r")(?:https?:)?//", re.I)

# An inline import map whose mappings point at the network is the CDN dependency in its newest
# clothes (adversarial lint #2, SINAL) — the JSON body carries no src= and no import statement,
# so neither regex above sees it. Mappings to data: URIs stay legal.
_PROTO_IMPORTMAP_EXTERNAL_RE = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']importmap[\"'][^>]*>[^<]*?(?:https?:)?//", re.I)


_ASSET_LOG_DEFAULT = object()
_ASSET_PROJECT_DEFAULT = object()


# --- roda-sem-erro (04-C rubrica: MECÂNICO, veto) ---------------------------------------------
# The live adapter runs the page in headless chromium via the playwright venv (the same harness
# the render→ver rite uses, ~/cortex-3d-ref/pw-venv) in a SUBPROCESS, so publisher's own
# environment never needs playwright. Contract: list = the page RAN (entries are console.error /
# pageerror strings; empty = clean), None = harness unavailable — the caller OBSERVES, never
# vetoes, on None (degrade honesto: a missing venv/browser must not block a publish on a box
# that cannot run pages, only a page that PROVABLY errors is vetoed).
_PW_PYTHON = Path.home() / "cortex-3d-ref" / "pw-venv" / "bin" / "python"

# The runner exits 0 whenever the page was EXERCISED (errors, load failure included — those are
# page verdicts, veto material) and non-zero only when the harness itself is broken (playwright
# import/launch failure) — the exit code IS the ran-vs-unavailable distinction.
_PW_RUNNER = r"""
import json, pathlib, sys
errors = []
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append("console.error: " + m.text))
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    try:
        # as_uri(), never string concat — a TMPDIR with space/# must not truncate the URL
        # into a false load failure (adversarial slice-3 #6, SINAL).
        page.goto(pathlib.Path(sys.argv[1]).resolve().as_uri(), timeout=15000)
        # ponytail: a fixed settle window is a CEILING — an error later than ~1s still passes
        # (adversarial slice-3 #1); catches the honest setTimeout/rAF-init bug, not the long tail.
        # Upgrade path: interact/scroll the page or wait for quiescence if the tail ever bites.
        page.wait_for_timeout(1000)
    except Exception as e:  # a page that cannot even load is a page verdict, not a harness one
        errors.append("load failed: " + str(e))
    browser.close()
print(json.dumps(errors))
"""


def headless_page_errors(page_html, pw_python=_PW_PYTHON):
    """Open `page_html` in headless chromium and return its console.error/pageerror list
    ([] = ran clean), or None when the harness is unavailable (no pw-venv, browser missing,
    hung run) — the honest-degrade signal: observe, don't veto."""
    if not Path(pw_python).exists():
        return None
    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8")
    try:
        tmp.write(page_html)
        tmp.close()
        proc = subprocess.run([str(pw_python), "-c", _PW_RUNNER, tmp.name],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        os.unlink(tmp.name)
    if proc.returncode != 0:  # harness failure (import/launch), not a page verdict
        return None
    try:
        errors = json.loads(proc.stdout.strip() or "[]")
    except ValueError:
        return None
    return errors if isinstance(errors, list) else None


def _repo_relative(path):
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except ValueError:
        return str(Path(path).resolve())


def _asset_log_for(blog_dir, log):
    if log is not _ASSET_LOG_DEFAULT:
        return log
    try:
        return eventlog.LOG if Path(blog_dir).resolve() == BLOG_DIR.resolve() else None
    except Exception:  # noqa: BLE001 — a funny blog_dir means "do not touch canonical state"
        return None


def _asset_project_for(asset_log, project_fn):
    if project_fn is not _ASSET_PROJECT_DEFAULT:
        return project_fn
    return project_artefato_asset if asset_log is not None and _is_canonical_log(asset_log) else None


def _record_artefato_asset(asset_slug, out, *, kind, sha256, skill, parent_slug=None,
                           media_type=None, role=None, log=_ASSET_LOG_DEFAULT,
                           project_fn=_ASSET_PROJECT_DEFAULT):
    asset_log = _asset_log_for(Path(out).parent, log)
    if asset_log is None:
        return None
    ev = eventlog.publish_artefato_asset(
        asset_slug,
        path=_repo_relative(out),
        kind=kind,
        sha256=sha256,
        skill=skill,
        parent_slug=parent_slug,
        media_type=media_type,
        role=role,
        log=asset_log,
    )
    projector = _asset_project_for(asset_log, project_fn)
    if projector is not None:
        try:
            projector(asset_slug, path=_repo_relative(out), kind=kind, sha256=sha256,
                      skill=skill, parent_slug=parent_slug, media_type=media_type,
                      role=role, log=asset_log)
        except Exception as ex:  # noqa: BLE001 — asset projection is recoverable from the log
            print(f"asset project skipped for {asset_slug!r} (best-effort):", ex)
    return ev


def publish_artifact_asset(slug, content, *, kind, skill, ext=None, parent_slug=None,
                           blog_dir=BLOG_DIR, log=_ASSET_LOG_DEFAULT,
                           project_fn=_ASSET_PROJECT_DEFAULT) -> Path:
    """Write a content-addressed standalone Artefato asset, usually JS.

    The normal close path publishes the human-readable entry; this seam records companion files
    (for example an interactive report's JavaScript/data) as `artefato.asset`, so the Cortex can
    navigate them instead of treating them as stray files.
    """
    if skill not in PRODUCER_ROSTER:
        raise ValueError(f"skill {skill!r} is not in the producer roster {PRODUCER_ROSTER}")
    if kind not in eventlog.ASSET_KINDS:
        raise ValueError(f"asset kind must be one of {eventlog.ASSET_KINDS}, got {kind!r}")
    if not (isinstance(slug, str) and SLUG_RE.fullmatch(slug)):
        raise ValueError(f"invalid slug {slug!r}: must match {SLUG_RE.pattern} (#4)")
    if parent_slug is not None and not (isinstance(parent_slug, str) and SLUG_RE.fullmatch(parent_slug)):
        raise ValueError(f"invalid parent_slug {parent_slug!r}: must match {SLUG_RE.pattern} (#4)")
    if isinstance(content, bytes):
        data = content
    elif isinstance(content, str):
        data = content.encode("utf-8")
    else:
        raise ValueError("asset content must be str or bytes")
    ext = ext or {"js": "js", "html": "html", "css": "css", "data": "json",
                  "image": "bin"}.get(kind, kind)
    if not re.fullmatch(r"[a-z0-9]+", ext):
        raise ValueError(f"invalid asset extension {ext!r}")
    digest = hashlib.sha256(data).hexdigest()
    blog_dir = Path(blog_dir).resolve()
    out = (blog_dir / f"{slug}.{kind}.{digest[:12]}.{ext}").resolve()
    if out.parent != blog_dir:
        raise ValueError(f"slug {slug!r} escapes the blog dir (#4)")
    if out.exists():
        if out.read_bytes() != data:
            raise ValueError(
                f"content-address collision at {out.name!r}: existing bytes differ")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, out)
    media_type = {"js": "text/javascript", "html": "text/html", "css": "text/css",
                  "data": "application/json"}.get(kind)
    _record_artefato_asset(
        f"{slug}-{kind}-{digest[:12]}", out, kind=kind, sha256=digest, skill=skill,
        parent_slug=parent_slug, media_type=media_type, role=kind,
        log=log, project_fn=project_fn)
    return out


_ENTRY_ASSET_SUFFIXES = {
    ".html": ("html", "text/html"),
    ".js": ("js", "text/javascript"),
    ".css": ("css", "text/css"),
    ".json": ("data", "application/json"),
    ".bin": ("image", None),
}
_ENTRY_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(?:html|js|css|json|bin)$")


def _legacy_entry_asset_slug(path, digest):
    stem = re.sub(r"[^a-z0-9]+", "-", Path(path).stem.lower()).strip("-") or "entry"
    name_hash = hashlib.sha256(Path(path).name.encode("utf-8")).hexdigest()[:8]
    return f"entry-{stem}-{name_hash}-{digest[:12]}"


def _entry_parent_slug(name, published_slugs):
    for slug in sorted(published_slugs, key=len, reverse=True):
        if name.startswith(f"{slug}."):
            return slug
    return None


def backfill_entry_assets(*, blog_dir=BLOG_DIR, log=_ASSET_LOG_DEFAULT,
                          project_fn=_ASSET_PROJECT_DEFAULT):
    """Record pre-existing files under blog/entries as first-class Artefato assets.

    The old Cortex UX worked because generated HTML files were discoverable as artifacts even when
    their producer did not log a companion `artefato.asset`. New producers now log assets at publish
    time; this backfill closes the historical gap without duplicating normal close-published
    `<slug>.html` pages.
    """
    asset_log = _asset_log_for(blog_dir, log)
    if asset_log is None:
        return []
    root = Path(blog_dir).resolve()
    if not root.is_dir():
        return []
    corpus = cortex.corpus_at(log=asset_log)
    published_slugs = {item.get("slug") for item in corpus
                       if isinstance(item.get("slug"), str) and SLUG_RE.fullmatch(item["slug"])}
    assets = cortex.artefato_assets_at(log=asset_log)
    logged_paths = {asset.get("path") for asset in assets.values() if asset.get("path")}
    emitted = []
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if not path.is_file() or not _ENTRY_FILE_RE.fullmatch(path.name):
            continue
        suffix = path.suffix.lower()
        if suffix not in _ENTRY_ASSET_SUFFIXES:
            continue
        if suffix == ".html" and path.stem in published_slugs:
            continue
        rel = _repo_relative(path)
        if rel in logged_paths or str(path.resolve()) in logged_paths:
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        kind, media_type = _ENTRY_ASSET_SUFFIXES[suffix]
        asset_slug = _legacy_entry_asset_slug(path, digest)
        parent_slug = _entry_parent_slug(path.name, published_slugs)
        ev = _record_artefato_asset(
            asset_slug,
            path,
            kind=kind,
            sha256=digest,
            skill=None,
            parent_slug=parent_slug,
            media_type=media_type,
            role="entry-backfill",
            log=asset_log,
            project_fn=project_fn,
        )
        if ev is not None:
            emitted.append(ev)
            logged_paths.add(rel)
    return emitted


def publish_prototype_page(slug, page_html, *, skill, blog_dir=BLOG_DIR,
                           run_errors_fn=headless_page_errors, log=_ASSET_LOG_DEFAULT,
                           project_fn=_ASSET_PROJECT_DEFAULT) -> Path:
    """Write an intact, content-addressed single-file page for ANY roster genus (ticket 05
    generalizes the prototype-only seam: JS/imagem liberados; single file é a única regra dura).
    Returns the written Path (served at /e/<name>). Raises ValueError on an out-of-roster skill,
    a bad slug, a non-document fragment, an external resource dependency, or a page that errors
    in a headless run (roda-sem-erro, 04-C rubrica: veto) — before anything lands. When the
    headless harness is unavailable (`run_errors_fn` → None) the run is OBSERVED, never vetoed.
    # ponytail: the page is NOT eventlogged — the companion entry (published through the close)
    # is the committed record and carries the link; log the page bytes if replay ever needs them."""
    if skill not in PRODUCER_ROSTER:
        raise ValueError(
            f"publish_prototype_page is the roster's single-file seam — skill {skill!r} refused "
            f"(not in {PRODUCER_ROSTER}; an out-of-roster genus never rides raw script)")
    if not (isinstance(slug, str) and SLUG_RE.match(slug)):
        raise ValueError(f"invalid slug {slug!r}: must match {SLUG_RE.pattern} (#4)")
    if not (isinstance(page_html, str) and "<html" in page_html.lower()):
        raise ValueError(
            f"prototype page for {slug!r} is not a full HTML document (single-file bar: "
            "one self-contained page, not a fragment)")
    dep = (_PROTO_EXTERNAL_DEP_RE.search(page_html)
           or _PROTO_EXTERNAL_LOADER_RE.search(page_html)
           or _PROTO_IMPORTMAP_EXTERNAL_RE.search(page_html))
    if dep:
        raise ValueError(
            f"prototype page for {slug!r} is not self-contained: external resource load "
            f"{dep.group(0)!r} (zero-dep bar — inline everything; an <a href> link is fine)")
    # roda-sem-erro LAST of the refusals (the one expensive check runs only on a page that
    # already passed every cheap mechanical bar).
    try:  # a BROKEN harness must behave like a MISSING one (adversarial slice-3 #3, SINAL):
        # observe and publish — only a page that PROVABLY errors is vetoed.
        run_errors = run_errors_fn(page_html) if run_errors_fn is not None else None
    except Exception:
        run_errors = None
    if run_errors:
        raise ValueError(
            f"prototype page for {slug!r} does not run clean (roda-sem-erro veto): "
            + "; ".join(run_errors[:5]))
    if run_errors is None:
        print(f"[publisher] headless harness unavailable — roda-sem-erro for {slug!r} "
              "OBSERVED, not vetoed (degrade honesto)", file=sys.stderr)
    blog_dir = Path(blog_dir).resolve()
    full_digest = hashlib.sha256(page_html.encode("utf-8")).hexdigest()
    digest = full_digest[:12]
    out = (blog_dir / f"{slug}.proto.{digest}.html").resolve()
    if out.parent != blog_dir:  # unreachable given SLUG_RE — defense in depth like _safe_target
        raise ValueError(f"slug {slug!r} escapes the blog dir (#4)")
    if out.exists():  # content-addressed: identical bytes should already live at this address
        # verify, never trust: a differing file at the same 48-bit address is a sha12 collision or a
        # tampered page — refuse rather than silently serve wrong bytes (adversarial finding 4, SINAL:
        # keeps the "link points to the reviewed bytes" claim honest).
        if out.read_text() != page_html:
            raise ValueError(
                f"content-address collision at {out.name!r}: existing bytes differ from {slug!r}'s "
                "page — refusing to serve unreviewed content")
    else:
        _write_page(out, page_html)
    _record_artefato_asset(
        f"{slug}-proto-{digest}", out, kind="html", sha256=full_digest, skill=skill,
        parent_slug=slug, media_type="text/html", role="prototype",
        log=log, project_fn=project_fn)
    return out


# --- The APOSTILA sibling (PAR B+C, doc 05 §REVISÃO DO PAR) -----------------------------------
# The winning pair is single-file interactive + printable APOSTILA as a build SUBPRODUCT of the
# SAME data (the operator loves paper — grill-design.md persona-fact). The apostila is print
# matter: A4 @page CSS, break-inside:avoid, the page's interaction PRECOMPUTED into static
# tables by the producer's build script (régua: drafts/grounding-exp/formC-apostila.html —
# "subproduto por script, não 3ª autoria"). It lands content-addressed as the sibling
# `<slug>.apostila.<sha256[:12]>.html` in the same blog dir (the /e/ route serves it, zero
# server change; SLUG_RE forbids dots so it can never collide with a close entry) and the
# artefato links it ("versão pra imprimir"). Optional for any roster genus, default ON for
# prototype (apostila_wanted); the flow wiring is the lead's — these are the seam primitives.
# ponytail: an authoring LINT like _PROTO_EXTERNAL_DEP_RE, not a security boundary — but print
# matter is STATIC, so anything live (script, on* handlers, javascript: URLs) or CSS-networked
# (@import, url(http…)) is refused outright (codex adversarial #1/#2; the .proto. CSP does not
# cover .apostila., so the lint carries more weight here — upgrade path: per-file CSP at serve).
_APOSTILA_LIVE_RE = re.compile(
    r"<script\b|\bon[a-z]+\s*=|javascript\s*:|@import\b|url\(\s*['\"]?(?:https?:)?//", re.I)

# The sibling's canonical name — what publish_apostila_page mints and what the link block
# accepts: <slug>.apostila.<sha256[:12]>.html, nothing else (codex adversarial #5).
_APOSTILA_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.apostila\.[0-9a-f]{12}\.html$")


def apostila_wanted(skill, param=None):
    """The apostila policy in one place: generated when the producer asks (`param`),
    default ON for the prototype genus, OFF elsewhere."""
    return skill == "prototype" if param is None else bool(param)


def apostila_link_block(page_name):
    """The canonical 'versão pra imprimir' block for the companion entry's spec — a palette
    callout whose text is a markdown link (codex adversarial: render_text only linkifies
    [text](url); a bare /e/... string would render as dead text, not an anchor). Accepts the
    Path publish_apostila_page returns or a bare name; anything not shaped
    <slug>.apostila.<sha12>.html is refused (no markdown/structure injection, no pointing at
    .proto./close entries)."""
    name = Path(page_name).name if page_name else ""
    if not _APOSTILA_NAME_RE.match(name):
        raise ValueError(
            f"apostila link for {page_name!r}: not a <slug>.apostila.<sha12>.html sibling "
            "(pass publish_apostila_page's return)")
    return {"type": "callout", "variant": "info",
            "text": f"[Versão pra imprimir (apostila A4)](/e/{name})"}


def publish_apostila_page(slug, page_html, *, skill, blog_dir=BLOG_DIR,
                          log=_ASSET_LOG_DEFAULT,
                          project_fn=_ASSET_PROJECT_DEFAULT) -> Path:
    """Write the intact, content-addressed printable APOSTILA sibling for a roster genus.
    Returns the written Path (served at /e/<name>). Shares the proto seam's bars (roster,
    slug, full document, zero external deps) plus two print-matter bars: NO <script> — the
    interaction must already be precomputed static tables from the same DATA — and an @page
    print-CSS rule present (the A4 marker the régua carries). Raises ValueError before
    anything lands.
    # ponytail: validation intentionally mirrors publish_prototype_page instead of sharing a
    # helper — that function is being touched by parallel branches (curadoria-autoral,
    # js-gates) and this ticket forbids editing it; fold the common bars into one _seam_check
    # after the branches merge."""
    if skill not in PRODUCER_ROSTER:
        raise ValueError(
            f"publish_apostila_page is a roster seam — skill {skill!r} refused "
            f"(not in {PRODUCER_ROSTER})")
    # fullmatch, not match (codex adversarial #7): SLUG_RE ends in $, and re.match+$ accepts
    # a trailing newline — strict means strict before the slug lands in a served filename.
    if not (isinstance(slug, str) and SLUG_RE.fullmatch(slug)):
        raise ValueError(f"invalid slug {slug!r}: must match {SLUG_RE.pattern} (#4)")
    if not (isinstance(page_html, str) and "<html" in page_html.lower()):
        raise ValueError(
            f"apostila for {slug!r} is not a full HTML document (one self-contained "
            "printable page, not a fragment)")
    dep = _PROTO_EXTERNAL_DEP_RE.search(page_html)
    if dep:
        raise ValueError(
            f"apostila for {slug!r} is not self-contained: external resource load "
            f"{dep.group(0)!r} (print matter must open whole by itself)")
    live = _APOSTILA_LIVE_RE.search(page_html)
    if live:
        raise ValueError(
            f"apostila for {slug!r} carries live/networked markup {live.group(0)!r} — print "
            "matter is STATIC: precompute the interaction into tables from the same DATA "
            "(régua: formC-apostila.html)")
    if "@page" not in page_html.lower():
        raise ValueError(
            f"apostila for {slug!r} has no @page print CSS — the A4 rule "
            "(e.g. @page{size:A4;margin:18mm 16mm}) is the print-matter bar")
    blog_dir = Path(blog_dir).resolve()
    full_digest = hashlib.sha256(page_html.encode("utf-8")).hexdigest()
    digest = full_digest[:12]
    out = (blog_dir / f"{slug}.apostila.{digest}.html").resolve()
    if out.parent != blog_dir:  # unreachable given SLUG_RE — defense in depth
        raise ValueError(f"slug {slug!r} escapes the blog dir (#4)")
    if out.exists():
        # content-addressed: verify, never trust — differing bytes at the address are refused
        if out.read_text() != page_html:
            raise ValueError(
                f"content-address collision at {out.name!r}: existing bytes differ from "
                f"{slug!r}'s apostila — refusing to serve unreviewed content")
    else:
        _write_page(out, page_html)
    _record_artefato_asset(
        f"{slug}-apostila-{digest}", out, kind="html", sha256=full_digest, skill=skill,
        parent_slug=slug, media_type="text/html", role="apostila",
        log=log, project_fn=project_fn)
    return out


def _signal_cites(slug, body, cites, embed_fn, log):
    """Emit one `source.signal` per cited snippet (ADR-0009). With an injected embed_fn the
    signal is the cosine(embed(snippet), embed(body)) score (offline-testable); without one
    the cite still records, scored 0.0 — the publish never depends on a network call."""
    for c in cites:
        if not (isinstance(c, dict) and c.get("snippet")):
            continue
        if embed_fn is not None:
            sim = cortex.cosine(embed_fn(c["snippet"]), embed_fn(body))
        else:
            sim = 0.0
        eventlog.source_signal(slug, c.get("ref"), c.get("kind"), sim, log=log)


def _render_page(slug, spec, *, skill, date):
    """Render the self-contained neutral HTML page for `slug` from its spec — the SINGLE
    place the page bytes are produced, so a normal publish and a reprojection (recovery from
    the logged spec) emit byte-identical pages. Returns (body_html, page_text).

    `edge-markdown/v1` (the rito's publish spec, docs/rito-runtime.md): the page IS the
    pinned renderer's output — no legacy `_page` shell, no base.css — so a reprojection from
    the logged spec re-derives the EXACT bytes `publish_rito` wrote and sealed."""
    if isinstance(spec, dict) and spec.get("format") == "edge-markdown/v1":
        page = render.markdown_spec_to_page(spec)
        return page, page
    body_html = render.spec_to_html(spec)
    css = BASE_CSS.read_text()
    js = BASE_JS.read_text()
    page = _page(slug, body_html, skill=skill, date=date or _date.today().isoformat(),
                 css=css, js=js)
    return body_html, page


def _write_page(out, page):
    """Write the page to `out` via temp+rename (atomic, no half-written page). A failure here
    is recoverable AFTER the commit: the logged spec re-renders the page (reproject_missing_pages)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".html.tmp")
    tmp.write_text(page)
    os.replace(tmp, out)


def _is_canonical_log(log):
    """True iff `log` is the install's CANONICAL event log — compared by NORMALIZED PATH, not object
    identity (Codex P3): a caller writing the real log via an equivalent `Path(eventlog.LOG)`, a
    resolved path, or a string path is still canonical and must project/sync. A temp/dry-run log is
    not. Path-resolution failures fall back to object identity (never raises)."""
    if log is eventlog.LOG:
        return True
    try:
        return Path(log).resolve() == Path(eventlog.LOG).resolve()
    except Exception:  # noqa: BLE001 — a non-path log → not canonical
        return False


def _cluster_slug(label):
    """wiki_render's canonical cluster-slug rule (letters only — drops spaces, &, digits,
    punctuation). The ONE rule the projection resolves a `distills` ref against (memory.md:
    the slug↔display trap) — APOC is not installed, so normalize in Python, never cypher."""
    return re.sub(r"[^a-z]", "", (label or "").lower())



def _distill_catalog(s, g):
    """Slug → (kind, label) for DISTILLS resolution.

    Two independent catalogs (genotype, not host-specific):
      - entity: Entity.curated_cluster (grill attach)
      - community: Community.name (automatic communities.consolidate)

    communities.consolidate never stamps curated_cluster; without the Community path,
    every distill ref stays unresolved forever and strands projection_complete=false,
    hiding Artefatos from recall (which filters on projection_complete=true).
    """
    catalog = {}
    for r in s.run(
        "MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
        "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
        "RETURN DISTINCT e.curated_cluster AS l", g=g):
        label = r["l"]
        if label:
            catalog[_cluster_slug(label)] = ("entity", label)
    for r in s.run(
        "MATCH (c:Community {group_id:$g}) WHERE c.name IS NOT NULL "
        "RETURN c.name AS n", g=g):
        name = r["n"]
        if name:
            catalog.setdefault(_cluster_slug(name), ("community", name))
    return catalog


def _link_distill(s, g, slug, kind, label):
    """MERGE DISTILLS from Artefato to Entity (curated) or Community (automatic)."""
    if kind == "entity":
        s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$slug}),"
            "(e:Entity {group_id:$g, curated_cluster:$label}) "
            "WHERE coalesce(e.archived,false)=false AND e.merged_into IS NULL "
            "MERGE (a)-[:DISTILLS]->(e)",
            g=g, slug=slug, label=label)
    elif kind == "community":
        s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$slug}),"
            "(c:Community {group_id:$g, name:$label}) "
            "MERGE (a)-[:DISTILLS]->(c)",
            g=g, slug=slug, label=label)



def _load_openai_key():
    """Load OPENAI_API_KEY into the env if absent (Codex P1): the embedding key lives in the install
    secrets (or the ~/.edge-sandbox-kit dev fallback) and is NOT necessarily exported when a producer
    invokes the projection. Without this, the embed fails, the projection never completes, and recall
    filters the Artefato out forever. Mirrors sweep._load_openai_key (the runtime's loader)."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    for f in (REPO / "secrets" / "openai.env", Path.home() / ".edge-sandbox-kit" / "openai.env"):
        try:
            if f.exists():
                for line in f.read_text().splitlines():
                    if "OPENAI_API_KEY" in line:
                        os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
                        return
        except Exception:  # noqa: BLE001 — best-effort; embed degrades if the key cannot be loaded
            pass


def _spec_text(spec):
    """Flatten the published spec to plain text for the content embedding (Codex P2: embed the
    CONTENT, not just the kernel). Walks the string leaves render reads — executive_summary +
    every block's string/list-of-string/list-of-dict values — best-effort, bounded for the embed
    request. Returns '' for a None/empty spec (the embed then falls back to slug+kernel)."""
    if not isinstance(spec, dict):
        return ""
    # `edge-markdown/v1` (the rito's publish spec) carries the whole body as one markdown string,
    # not the legacy sections/executive_summary tree — flatten THAT, or the content embedding and
    # MENTIONS see an empty node and the artefato is unrecallable (a first-class-citizen gap).
    if spec.get("format") == "edge-markdown/v1":
        return (spec.get("markdown") or "")[:8000]
    parts = []
    # top-level rendered fields render.spec_to_html emits as content: executive_summary, the
    # metrics grid, and the bibliography (Codex P2) — plus every section/additional_section block.
    _walk_strings(spec.get("executive_summary") or [], parts)
    _walk_strings(spec.get("metrics") or [], parts)
    _walk_strings(spec.get("bibliography") or [], parts)
    for block in _iter_spec_blocks(spec):
        _walk_strings(block, parts)
    return " ".join(parts)[:8000]   # bound the embed input


def _walk_strings(node, out):
    """Collect every string leaf under `node` (dict/list nested to any depth — e.g. a table's
    rows are list-of-lists), so table cells and nested bullets reach the content embedding."""
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            _walk_strings(v, out)
    elif isinstance(node, list):
        for it in node:
            _walk_strings(it, out)


def _iter_spec_blocks(spec):
    for key in ("sections", "additional_sections"):
        for section in spec.get(key, []):
            for block in section.get("blocks", []):
                if isinstance(block, dict):
                    yield block


# Ticket A (ontologia §2b) — the FIXED valence→label allowlist: the edge label is a literal from
# this dict, never interpolated caller data (same discipline as LINEAGE_LABELS). Aliases to
# episteme's canonical bearing valences live in cortex/schema/ontologia.yaml.
_VALENCE_LABELS = {"supports": "SUPPORTS", "refutes": "REFUTES",
                   "qualifies": "QUALIFIES", "inconclusive": "INCONCLUSIVE"}


def _project_bears_on(s, g, slug, bears_on):
    """Project the artefato's valenced declarations as (a)-[:SUPPORTS|REFUTES|QUALIFIES|
    INCONCLUSIVE]->(h:Hypothesis) edges (ontologia §2b). Every edge carries the plane it lives
    on: provenance_class='asserted' (author-declared — NEVER computed; CX-1 keeps it out of any
    verdict rollup), rigor='lead' (the HARD ceiling — cravado is structurally unreachable here),
    validity='inferred_default' (O-12: flips only via a review.approved event), scope='cortex'.
    The hypothesis is matched by ulid OR display slug; an UNRESOLVED target (not declared/
    projected yet) returns True so the caller leaves projection_complete=false and the next
    sweep self-heals (the unresolved_lineage pattern). Verdict is NEVER stored anywhere."""
    unresolved = False
    for b in normalize_bears_on(bears_on):
        label = _VALENCE_LABELS[b["valence"]]
        row = s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$slug}) "
            "MATCH (h:Hypothesis {group_id:$g}) WHERE h.ulid=$ref OR h.slug=$ref "
            "MERGE (a)-[r:%s]->(h) "
            "SET r.provenance_class='asserted', r.rigor='lead', "
            "r.validity='inferred_default', r.scope='cortex', r.rationale=$rat "
            "RETURN count(h) AS n" % label,
            g=g, slug=slug, ref=b["hypothesis"], rat=b.get("rationale")).single()
        if not row or row["n"] == 0:
            unresolved = True   # hypothesis not in the graph yet — revisit next sweep
    return unresolved


def _project_para(s, g, slug, para):
    """Project artefato-[:PARA]->parceiro (§6: the document MADE for the person). The endpoint
    is the PROMOTED Entity only (e.parceiro=true) — promotion, never minting: a name that no
    parceiro.promoted marked yet resolves nothing and returns True (projection_complete=false,
    self-heals once the promotion lands). The edge is author-asserted."""
    unresolved = False
    for name in normalize_para(para):
        row = s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$slug}) "
            "MATCH (e:Entity {group_id:$g, parceiro:true}) WHERE e.name=$name "
            "MERGE (a)-[r:PARA]->(e) SET r.provenance_class='asserted' "
            "RETURN count(e) AS n", g=g, slug=slug, name=name).single()
        if not row or row["n"] == 0:
            unresolved = True   # parceiro not promoted/extracted yet — revisit next sweep
    return unresolved


def _experiment_report_slug(exp):
    """The canonical finalization report slug carried by native Experiment audit artifacts."""
    artifacts = exp.get("canonical_artifacts") if isinstance(exp, dict) else None
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        ref = artifact.get("ref")
        if not (isinstance(ref, str) and ref.startswith("artefato:")):
            continue
        slug = ref.split(":", 1)[1].strip()
        if SLUG_RE.fullmatch(slug):
            return slug
    return None


def _experiment_graph_props_from(exp, experiment_id, *, report_slug=None):
    canonical = exp.get("canonical") if isinstance(exp.get("canonical"), dict) else {}
    typed = canonical.get("typed") if isinstance(canonical.get("typed"), dict) else {}
    prose = canonical.get("prose") if isinstance(canonical.get("prose"), str) else None
    claim = typed.get("claim") if isinstance(typed.get("claim"), str) else None
    title = exp.get("title") if isinstance(exp.get("title"), str) else None
    scope = typed.get("scope") if isinstance(typed.get("scope"), str) else exp.get("scope")
    status = typed.get("status") if isinstance(typed.get("status"), str) else exp.get("status")
    caveat = typed.get("caveat") if isinstance(typed.get("caveat"), str) else None
    supports = typed.get("supports") if isinstance(typed.get("supports"), list) else []
    excludes = typed.get("excludes") if isinstance(typed.get("excludes"), list) else []
    next_step = typed.get("next") if isinstance(typed.get("next"), str) else None
    return {
        "title": title or claim or experiment_id,
        "claim": claim or prose,
        "scope": scope if isinstance(scope, str) else None,
        "status": status if isinstance(status, str) else "reported",
        "caveat": caveat,
        "supports": [str(v) for v in supports if isinstance(v, str) and v.strip()],
        "excludes": [str(v) for v in excludes if isinstance(v, str) and v.strip()],
        "next": next_step,
        "report_slug": report_slug,
        "declared_at": exp.get("declared_ts") if isinstance(exp.get("declared_ts"), str) else None,
        "curated_at": exp.get("ts") if isinstance(exp.get("ts"), str) else None,
    }


def _experiment_graph_props(experiment_id, *, report_slug, log):
    """Flat props for a navigable Experiment node.

    The event log is the source of truth for native Experiments. Projection keeps only the fields the
    Cortex UI needs to title, filter and drill down: id/title/current claim/status/scope and the
    finalization report slug. If an old report only carries `reports_on`, the Experiment still gets a
    useful asserted stub instead of an anonymous node.
    """
    exp = cortex.experiment_at(experiment_id, log=log) or {}
    return _experiment_graph_props_from(exp, experiment_id, report_slug=report_slug)


def _project_experiment_node(s, g, experiment_id, props):
    s.run(
        "MERGE (x:Experiment {group_id:$g, id:$experiment_id}) "
        "SET x.kind='experiment', x.provenance_class='asserted', "
        "x.experiment_id=$experiment_id, x.uuid=$uuid, "
        "x.title=$title, x.claim=$claim, x.scope=$scope, x.status=$status, "
        "x.caveat=$caveat, x.supports=$supports, x.excludes=$excludes, x.next=$next, "
        "x.report_slug=coalesce($report_slug, x.report_slug), "
        "x.canonical_report=coalesce($report_slug, x.canonical_report), "
        "x.declared_at=$declared_at, x.curated_at=$curated_at, "
        "x.projected_at=$pat, x.projection_complete=true",
        g=g, experiment_id=experiment_id, uuid=f"experiment:{experiment_id}",
        pat=_dt.now(_tz.utc).isoformat(), **props)
    report_slug = props.get("report_slug")
    if report_slug:
        s.run(
            "MATCH (a:Artefato {group_id:$g, slug:$report_slug}) "
            "MATCH (x:Experiment {group_id:$g, id:$experiment_id}) "
            "MERGE (a)-[r:REPORTS_ON]->(x) "
            "SET r.provenance_class='asserted'",
            g=g, report_slug=report_slug, experiment_id=experiment_id)


def _project_reports_on(s, g, slug, reports_on, *, log=eventlog.LOG):
    """Project report Artefato → Experiment.

    The report is the human-readable Artefato that links into clusters/entities/sources through the
    normal Edge graph. The Experiment is the scientific object. Unlike PARA/bears_on, the Experiment
    endpoint is allowed to be minted by this authored report edge: the report is the curation act that
    makes the experimental object navigable.
    """
    for experiment_id in normalize_reports_on(reports_on):
        props = _experiment_graph_props(experiment_id, report_slug=slug, log=log)
        _project_experiment_node(s, g, experiment_id, props)
    return False


def _project_native_experiments(s, g, log):
    """Project every native Experiment fold, including legacy ids that predate expNNN numbering."""
    for experiment_id, exp in cortex.experiments_at(log=log).items():
        if not (isinstance(experiment_id, str) and experiment_id.strip()):
            continue
        report_slug = _experiment_report_slug(exp)
        props = _experiment_graph_props_from(exp, experiment_id, report_slug=report_slug)
        _project_experiment_node(s, g, experiment_id.strip(), props)


def project_native_experiments(log=eventlog.LOG):
    """Best-effort projection of native Experiment memory independent of report replay.

    `reports_on` remains strict for new authored report edges, but old Roberto experiments already
    exist in the native event fold with legacy ids. This replay makes those scientific objects
    navigable in Cortex instead of leaving anonymous Experiment stubs behind.
    """
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; the log already holds the truth
        print("experiment project skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            _project_native_experiments(s, g, log)
    except Exception as ex:  # noqa: BLE001 — recoverable on next reproject
        print("experiment project failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


def _project_artefato_asset(s, g, asset):
    """Project one `artefato.asset` event as a navigable :Artefato node (#108).

    Assets are not close-published entries and do not carry an intent kernel, but they are still
    first-class generated Artefatos: HTML/JS files the reader can open, inspect, and traverse from
    the parent report/prototype.
    """
    if not isinstance(asset, dict):
        return
    asset_slug = asset.get("asset_slug")
    path = asset.get("path")
    kind = asset.get("kind")
    sha256 = asset.get("sha256")
    if not (asset_slug and path and kind and sha256):
        return
    s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) "
          "SET a.kind='asset', a.asset_kind=$kind, a.asset_role=$role, "
          "a.page=$page, a.sha256=$sha, a.skill=coalesce($skill, a.skill), "
          "a.media_type=$media_type, a.projected_at=$pat, a.projection_complete=true",
          g=g, slug=asset_slug, kind=kind, role=asset.get("role"), page=path,
          sha=sha256, skill=asset.get("skill"), media_type=asset.get("media_type"),
          pat=_dt.now(_tz.utc).isoformat())
    parent = asset.get("parent_slug")
    if parent:
        s.run("MERGE (p:Artefato {group_id:$g, slug:$parent}) "
              "MERGE (a:Artefato {group_id:$g, slug:$slug}) "
              "MERGE (p)-[r:HAS_ASSET]->(a) "
              "SET r.provenance_class='asserted', r.role=$role",
              g=g, parent=parent, slug=asset_slug, role=asset.get("role"))
    s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}),(o:Objective {group_id:$g}) "
          "MERGE (a)-[:SERVES]->(o)", g=g, slug=asset_slug)


def project_artefato_asset(asset_slug, *, path, kind, sha256, skill=None, parent_slug=None,
                           media_type=None, role=None, log=eventlog.LOG):
    """Best-effort projection for a generated Artefato asset."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; the log already holds the truth
        print("asset project skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            if _is_canonical_log(log):
                _project_backbone(s, g, log)
            _project_artefato_asset(s, g, {
                "asset_slug": asset_slug,
                "path": path,
                "kind": kind,
                "sha256": sha256,
                "skill": skill,
                "parent_slug": parent_slug,
                "media_type": media_type,
                "role": role,
            })
    except Exception as ex:  # noqa: BLE001 — recoverable on next reproject
        print("asset project failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


def _project_session_topic_index(s, g, index, log=eventlog.LOG):
    """Project the automatic Voz/session topic index.

    The log is the source of truth; these nodes are navigational hypotheses. Rebuild the owned
    Session->Topic/Fragment edges for sessions present in the fold so a changed topic extraction does
    not strand stale fragments.
    """
    if not isinstance(index, dict):
        return
    topics = index.get("topics") or {}
    fragments = index.get("fragments") or {}
    for session in (index.get("sessions") or {}).values():
        sid = session.get("session_id")
        if not sid:
            continue
        s.run(
            "MERGE (se:Episodic {group_id:$g, session_id:$sid}) "
            "SET se.name=$sid, se.key=$sid, se.uuid=$uuid, se.surface=$surface, se.path=$path, "
            "se.summary=$summary, se.medium_tier='low', se.projected_at=$pat",
            g=g, sid=sid, uuid=f"session:{sid}", surface=session.get("surface"),
            path=session.get("path"),
            summary=f"session topic index: {len(session.get('topics') or [])} topic(s)",
            pat=session.get("latest_ts") or _dt.now(_tz.utc).isoformat())
        s.run(
            "MATCH (se:Episodic {group_id:$g, session_id:$sid})-[r:HAS_TOPIC]->(:Topic) DELETE r",
            g=g, sid=sid)
        s.run(
            "MATCH (se:Episodic {group_id:$g, session_id:$sid})-[:HAS_FRAGMENT]->"
            "(vf:VozFragment {group_id:$g}) DETACH DELETE vf",
            g=g, sid=sid)
        for topic_id in session.get("topics") or []:
            topic = topics.get(topic_id) or {}
            s.run(
                "MERGE (t:Topic {group_id:$g, topic_id:$tid}) "
                "SET t.key=$tid, t.uuid=$uuid, t.title=$title, t.name=$title, "
                "t.score=$score, t.keywords=$keywords, t.projected_at=$pat",
                g=g, tid=topic_id, uuid=f"topic:{topic_id}",
                title=topic.get("title") or topic_id,
                score=topic.get("score") or 0,
                keywords=topic.get("keywords") or [],
                pat=topic.get("latest_ts") or _dt.now(_tz.utc).isoformat())
            s.run(
                "MATCH (se:Episodic {group_id:$g, session_id:$sid}),"
                "(t:Topic {group_id:$g, topic_id:$tid}) "
                "MERGE (se)-[r:HAS_TOPIC]->(t) SET r.provenance_class='extracted'",
                g=g, sid=sid, tid=topic_id)
        for fid in session.get("fragments") or []:
            frag = fragments.get(fid) or {}
            topic_id = frag.get("topic_id")
            s.run(
                "MERGE (vf:VozFragment {group_id:$g, fragment_id:$fid}) "
                "SET vf.key=$fid, vf.uuid=$uuid, vf.session_id=$sid, vf.surface=$surface, "
                "vf.path=$path, vf.turn=$turn, vf.snippet=$snippet, vf.text=$snippet, "
                "vf.title=$title, vf.medium_tier='low', vf.projected_at=$pat",
                g=g, fid=fid, uuid=f"voz:{fid}", sid=sid, surface=frag.get("surface"),
                path=frag.get("path"), turn=frag.get("turn"), snippet=frag.get("snippet"),
                title=frag.get("snippet"), pat=frag.get("ts") or _dt.now(_tz.utc).isoformat())
            s.run(
                "MATCH (se:Episodic {group_id:$g, session_id:$sid}),"
                "(vf:VozFragment {group_id:$g, fragment_id:$fid}) "
                "MERGE (se)-[r:HAS_FRAGMENT]->(vf) SET r.provenance_class='extracted'",
                g=g, sid=sid, fid=fid)
            if topic_id:
                s.run(
                    "MATCH (vf:VozFragment {group_id:$g, fragment_id:$fid}),"
                    "(t:Topic {group_id:$g, topic_id:$tid}) "
                    "MERGE (vf)-[r:ABOUT]->(t) SET r.provenance_class='extracted'",
                    g=g, fid=fid, tid=topic_id)

    s.run("MATCH (t:Topic {group_id:$g})-[r:PROPOSES]->(:Direction) DELETE r", g=g)
    dirs = cortex.direction_at(log=log) or {}
    for item in dirs.get("set", []) + dirs.get("proposed", []):
        iid = item.get("id")
        body = item.get("body")
        if not (isinstance(iid, str) and iid.startswith("topic-7d:")
                and isinstance(body, str) and body.strip()):
            continue
        topic_id = iid.split(":", 1)[1]
        if topic_id not in topics:
            continue
        s.run(
            "MATCH (t:Topic {group_id:$g, topic_id:$tid}) "
            "MERGE (d:Direction {group_id:$g, body:$body}) "
            "SET d.id=$id, d.kind=$kind "
            "MERGE (t)-[r:PROPOSES]->(d) SET r.provenance_class='extracted'",
            g=g, tid=topic_id, body=body, id=iid, kind=item.get("kind") or "thread")
    s.run(
        "MATCH (t:Topic {group_id:$g}) "
        "WHERE NOT (()-[:HAS_TOPIC]->(t)) AND NOT (()-[:ABOUT]->(t)) "
        "DETACH DELETE t", g=g)


def project_session_topics(log=eventlog.LOG):
    """Best-effort projection for session.topic events."""
    if not _is_canonical_log(log):
        return
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; the log already holds the truth
        print("session-topic project skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            _project_session_topic_index(s, g, cortex.session_topics_at(log=log), log=log)
    except Exception as ex:  # noqa: BLE001 — recoverable on next reproject
        print("session-topic project failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


def project_doc(payload, log=eventlog.LOG, *, driver_factory=None, identity=None,
                embed_fn=None):
    """Best-effort projection for an injected md doc (issue #130, S6). MERGE a :Doc node carrying
    the provenance markers the spec fixes — `provenance_class='asserted'` + `author='operador'`
    (a classe EXISTENTE do axis, não um enum novo) — plus a content embedding (best-effort) and
    DISTILLS edges to EXISTING clusters only (never fabricated, mirror project_artefato). The doc
    is Voz curada-desejada: acima da sessão crua, abaixo do curado-do-grill.

    Degrade-safe (ADR-0011/0006): the LOG is truth; ANY failure PRINTS and returns, NEVER raises
    into the inject. `payload` = md_to_mem.graph_episode_payload(...)."""
    if not _is_canonical_log(log):
        return
    try:
        if not isinstance(payload, dict):
            raise ValueError("doc projection payload must be a dict")
        slug = payload.get("slug")
        body = payload.get("body")
        threads = payload.get("threads", [])
        if not (isinstance(slug, str) and SLUG_RE.fullmatch(slug)):
            raise ValueError("doc projection needs a valid slug")
        if not (isinstance(body, str) and body.strip()):
            raise ValueError("doc projection needs a non-blank body")
        if (not isinstance(threads, list)
                or not all(isinstance(ref, str) and ref.strip() for ref in threads)):
            raise ValueError("doc projection threads must be a list of non-blank refs")
        if payload.get("author") != "operador":
            raise ValueError("doc projection author must be operador")
        if payload.get("provenance_class") != "asserted":
            raise ValueError("doc projection provenance_class must be asserted")
        content_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()
        supplied_sha256 = payload.get("sha256")
        if supplied_sha256 is not None and supplied_sha256 != content_sha256:
            raise ValueError("doc projection sha256 does not match body")
        threads = [ref.strip() for ref in threads]
    except Exception as ex:  # noqa: BLE001 — malformed projection input is degrade-safe
        print("doc project skipped (best-effort, malformed payload):", ex)
        return
    try:
        if identity is None:
            import _identity as identity
        g = identity.require_group()
        uri, user, pw = identity.neo4j_conn()
        if driver_factory is None:
            from neo4j import GraphDatabase
            driver_factory = GraphDatabase.driver
        drv = driver_factory(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; the log already holds the truth
        print("doc project skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            s.run("MERGE (d:Doc {group_id:$g, slug:$slug}) "
                  "SET d.body=$body, d.sha256=$sha256, d.threads=$threads, "
                  "d.provenance_class=$pc, d.author=$author, "
                  "d.projected_at=$pat, d.projection_complete=false",
                  g=g, slug=slug, body=body, sha256=content_sha256, threads=threads,
                  pc="asserted", author="operador",
                  pat=_dt.now(_tz.utc).isoformat())
            # embed the CONTENT (mesma infra dos artefatos, best-effort — sem key → pula).
            emb_hash = hashlib.sha256(f"{slug}\n{body}".encode("utf-8")).hexdigest()
            row = s.run("MATCH (d:Doc {group_id:$g, slug:$slug}) "
                        "RETURN d.embedding IS NOT NULL AS e, d.embedding_input_hash AS h",
                        g=g, slug=slug).single()
            embed_current = bool(row["e"]) and row["h"] == emb_hash
            if not embed_current:
                try:
                    embedding_input = f"{slug}\n{body}"
                    if embed_fn is None:
                        from openai import OpenAI
                        _load_openai_key()
                        emb = OpenAI().embeddings.create(
                            model="text-embedding-3-small", input=embedding_input,
                        ).data[0].embedding
                    else:
                        emb = embed_fn(embedding_input)
                    s.run("MATCH (d:Doc {group_id:$g, slug:$slug}) "
                          "SET d.embedding=$e, d.embedding_input_hash=$h",
                          g=g, slug=slug, e=emb, h=emb_hash)
                    embed_current = True
                except Exception as ex:  # noqa: BLE001 — embed is best-effort (no key → skip)
                    print("doc embed skipped (best-effort, will retry on recovery):", ex)
            # DISTILLS to curated Entity clusters and/or automatic Communities (never fabricate).
            s.run("MATCH (d:Doc {group_id:$g, slug:$slug})-[r:DISTILLS]->() DELETE r", g=g, slug=slug)
            catalog = _distill_catalog(s, g)
            pending = []
            for ref in threads:
                hit = catalog.get(_cluster_slug(str(ref).replace("cluster:", "")))
                if not hit:
                    pending.append(str(ref))
                    continue
                kind, label = hit
                if kind == "entity":
                    s.run(
                        "MATCH (d:Doc {group_id:$g, slug:$slug}),"
                        "(e:Entity {group_id:$g, curated_cluster:$label}) "
                        "WHERE coalesce(e.archived,false)=false AND e.merged_into IS NULL "
                        "MERGE (d)-[:DISTILLS]->(e)",
                        g=g, slug=slug, label=label)
                else:
                    s.run(
                        "MATCH (d:Doc {group_id:$g, slug:$slug}),"
                        "(c:Community {group_id:$g, name:$label}) "
                        "MERGE (d)-[:DISTILLS]->(c)",
                        g=g, slug=slug, label=label)
            if pending:
                s.run("MATCH (d:Doc {group_id:$g, slug:$slug}) SET d.pending_distills=$p",
                      g=g, slug=slug, p=pending)
            else:
                s.run("MATCH (d:Doc {group_id:$g, slug:$slug}) REMOVE d.pending_distills",
                      g=g, slug=slug)
            # Soft distills: completion tracks embed only (pending_distills retried on reproject).
            if embed_current:
                s.run("MATCH (d:Doc {group_id:$g, slug:$slug}) SET d.projection_complete=true",
                      g=g, slug=slug)
    except Exception as ex:  # noqa: BLE001 — recoverable on next reproject
        print("doc project failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


def _project_para_default(s, g, slug, name):
    """Curadoria autoral (§6, regra do operador): with NO authored `para`, the artefato is still
    FOR someone — the operador/mentee. The mark is a PROP on the :Artefato (`a.para_default`,
    the para-o-mentee mark) plus a PARA edge ONLY when the mentee's Entity is ALREADY promoted
    (`parceiro:true` — §6: the PARA endpoint is the promoted Entity only; the default never mints
    nor promotes, promotion stays HITL). FAIL-SAFE, unlike _project_para: an unpromoted/absent
    mentee Entity NEVER flags unresolved — the default must not strand projection_complete=false
    on every artefato of an install whose mentee was not promoted yet. A falsy `name` (an authored
    `para` now rides, or the mentee is unresolvable) CLEARS a stale mark — the same corrected-
    republish discipline as the destructive edge rebuild."""
    if not name:
        s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) REMOVE a.para_default",
              g=g, slug=slug)
        return
    s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) SET a.para_default=$name",
          g=g, slug=slug, name=name)
    # best-effort edge: only onto the PROMOTED mentee Entity; r.default distinguishes the
    # mechanical default from an authored PARA (both asserted — the rule is author-level).
    s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
          "MATCH (e:Entity {group_id:$g, parceiro:true}) WHERE e.name=$name "
          "MERGE (a)-[r:PARA]->(e) SET r.provenance_class='asserted', r.default=true",
          g=g, slug=slug, name=name)


def _project_hypotheses(s, g, log):
    """Project the :Hypothesis spine from the fold (ontologia §1: hipotese, verbatim — the node
    is a projection of hypothesis.declared, exactly as :Artefato is of artefato.published).
    Idempotent MERGE keyed by ulid (O-2); the display slug is a prop, never a key. A superseded
    pair projects (new)-[:SUPERSEDES]->(old) — the existing lineage label, a new endpoint pair,
    no new edge type (O-4). NO stored verdict/status — standing is derived at read."""
    for h in cortex.hypotheses_at(log=log).values():
        f = h.get("falsifier") or {}
        s.run("MERGE (h:Hypothesis {group_id:$g, ulid:$ulid}) "
              "SET h.statement=$statement, h.slug=$slug, h.content_hash=$ch, h.author=$author, "
              "h.created_at=$created, h.falsifier_metric=$fm, h.falsifier_threshold=$ft, "
              "h.falsifier_direction=$fd",
              g=g, ulid=h["ulid"], statement=h.get("statement"), slug=h.get("slug"),
              ch=h.get("content_hash"), author=h.get("author"), created=h.get("created_at"),
              fm=f.get("metric"), ft=f.get("threshold"), fd=f.get("direction"))
        if h.get("superseded_by"):
            # destructive rebuild per TARGET (the ANCHORS pattern; codex adversarial #4): the
            # fold is last-wins (a re-supersede corrects the successor), so drop every
            # SUPERSEDES pointing at this old FIRST — replay stays byte-faithful to the fold.
            s.run("MATCH (:Hypothesis)-[r:SUPERSEDES]->(old:Hypothesis {group_id:$g, ulid:$old}) "
                  "DELETE r", g=g, old=h["ulid"])
            s.run("MATCH (new:Hypothesis {group_id:$g, ulid:$new}),"
                  "(old:Hypothesis {group_id:$g, ulid:$old}) "
                  "MERGE (new)-[:SUPERSEDES]->(old)",
                  g=g, new=h["superseded_by"], old=h["ulid"])


def _project_parceiros(s, g, log):
    """Project the §6 parceiro PROMOTION onto the graph: MATCH the existing extracted :Entity
    by name and SET the mark (parceiro=true + kind/domain/by) — promotion, NOT minting (the
    node graphiti extracted keeps its edges/communities; an Entity that was never extracted
    stays unmarked until it is). provenance of the mark = asserted (declared HITL)."""
    for p in cortex.parceiros_at(log=log).values():
        s.run("MATCH (e:Entity {group_id:$g}) WHERE e.name=$name "
              "SET e.parceiro=true, e.parceiro_kind=$kind, e.parceiro_domain=$domain, "
              "e.parceiro_by=$by, e.parceiro_provenance='asserted'",
              g=g, name=p["name"], kind=p.get("kind"), domain=p.get("domain"),
              by=p.get("by"))
        # curadoria autoral (codex adversarial #1): publish-before-promotion SELF-HEALS here —
        # the para-o-mentee default is fail-safe (never blocks completion, so the per-slug
        # recovery won't revisit it); the backbone, run every canonical publish + sweep,
        # backfills the pending a.para_default -> PARA edges once the promotion lands. The
        # same pattern as the SERVES backfill for artefatos published before the Objective.
        s.run("MATCH (a:Artefato {group_id:$g}) WHERE a.para_default=$name "
              "MATCH (e:Entity {group_id:$g, parceiro:true}) WHERE e.name=$name "
              "MERGE (a)-[r:PARA]->(e) SET r.provenance_class='asserted', r.default=true",
              g=g, name=p["name"])


def _project_backbone(s, g, log):
    """Project the canonical SPINE BACKBONE on an open session `s`: :Genesis (space-0) -GROUNDS->
    :Objective + the ANCHORS rebuild (the active steers, DESTRUCTIVE DELETE-then-readd from the
    canonical fold). Shared by project_artefato (per publish) and reproject_graph (per sweep) so the
    ANCHORS stay current with the log every canonical sync, regardless of which artefatos exist."""
    import yaml
    try:
        cfg = yaml.safe_load(_identity.identity_path("agent.yaml").read_text()) or {}
    except Exception:  # noqa: BLE001 — agent.yaml read is best-effort
        cfg = {}
    s.run("MERGE (gen:Genesis {group_id:$g}) SET gen.space=0, gen.codename=$c, gen.voice=$v, "
          "gen.method='memory/method.md', gen.personality='memory/personality.md'",
          g=g, c=cfg.get("codename") or cfg.get("name"), v=cfg.get("voice"))
    obj = cortex.objective_at(log=log) or {}
    if obj.get("body"):
        s.run("MERGE (o:Objective {group_id:$g}) SET o.body=$b", g=g, b=obj["body"])
        s.run("MATCH (gen:Genesis {group_id:$g}),(o:Objective {group_id:$g}) "
              "MERGE (gen)-[:GROUNDS]->(o)", g=g)
        # ENSURE every Artefato SERVES the objective (Codex P2): an Artefato published BEFORE the
        # Objective existed had its SERVES no-op at projection time; the backbone (run every canonical
        # sweep, once an Objective exists) guarantees the hub link so it is reachable from space-0 —
        # cheap idempotent MERGEs, no embeddings, independent of the per-slug skip-present recovery.
        s.run("MATCH (a:Artefato {group_id:$g}),(o:Objective {group_id:$g}) "
              "MERGE (a)-[:SERVES]->(o)", g=g)
    # ANCHORS = the CURRENTLY active steers — REBUILD each sync (DESTRUCTIVE) so a dropped/superseded
    # Direction stops being anchored (recall from space-0 must match the log).
    dirs = cortex.direction_at(log=log) or {}
    s.run("MATCH (o:Objective {group_id:$g})-[r:ANCHORS]->(:Direction) DELETE r", g=g)
    for it in dirs.get("set", []) + dirs.get("proposed", []):
        s.run("MERGE (d:Direction {group_id:$g, body:$b})", g=g, b=it["body"])
        s.run("MATCH (o:Objective {group_id:$g}),(d:Direction {group_id:$g, body:$b}) "
              "MERGE (o)-[:ANCHORS]->(d)", g=g, b=it["body"])
    # Ticket A — the episteme spine rides the same canonical sync: :Hypothesis nodes fold from
    # hypothesis.declared/superseded; the §6 parceiro mark folds from parceiro.promoted.
    _project_hypotheses(s, g, log)
    _project_parceiros(s, g, log)


def project_backbone(log=eventlog.LOG):
    """Open a session and project the canonical spine backbone (Codex P2): the ANCHORS rebuild must
    run EVERY canonical sweep so newly-folded Directions get anchored even when no artefato changed.
    CANONICAL-LOG ONLY + degrade-safe — a non-canonical log or an unreachable graph is a no-op."""
    if not _is_canonical_log(log):
        return
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort
        print("backbone sync skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            _project_backbone(s, g, log)
    except Exception as ex:  # noqa: BLE001 — best-effort, never fatal
        print("backbone sync failed (best-effort):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


# B.1 (ticket B) — o mapa reviewer-canônico → chave curta do payload/props. Os DOIS gates do fim
# (substância = feynman, passabilidade = regular) — o AND é do close; aqui só se persiste.
_GATE_REVIEWER_KEYS = {close.FEYNMAN_REVIEWER_ID: "feynman", close.REGULAR_REVIEWER_ID: "regular"}


def _gate_payload(proof):
    """B.1 — projeta o proof que `run_close` mintou num payload PERSISTÍVEL do gate: rubrica
    versionada (pinada por sha, GLO-13), pass derivado de strikes (#65), scores/rationales por
    reviewer (só numéricos/strings — vai virar prop flat no nó). Degrada a None (um verdict
    ausente/malformado nunca quebra o publish — o evento registra a ausência honestamente).

    provenance (CX-1): um verdict de gate é `llm_judged`, rigor teto `lead`, validity
    `inferred_default` — NUNCA agrega num rollup `computed` (cortex_provenance.assert_rollup_computed
    grita se tentar)."""
    if not isinstance(proof, dict):
        return None
    verdicts = proof.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return None
    # A rubrica vem do MÓDULO, nunca do proof (Codex adversarial #2): `gate_rubric` não é
    # digest-bound, então um proof mutado pós-mint carimbaria rubrica falsa no evento. Mint e
    # publish rodam no mesmo load do módulo — a régua de publish É a de mint; o campo no proof
    # fica como auditoria, não como fonte.
    gate = {"rubric": close.GATE_RUBRIC_VERSION,
            "rubric_sha": close.GATE_RUBRIC_SHA,
            "provenance_class": "llm_judged", "rigor": "lead",
            "validity": "inferred_default"}
    strikes_n = 0
    for v in verdicts:
        if not isinstance(v, dict):
            strikes_n += 1   # um verdict não-dict conta como defeito, nunca como limpo
            continue
        s = v.get("strikes")
        strikes_n += len(s) if isinstance(s, list) else 1
        key = _GATE_REVIEWER_KEYS.get(v.get("reviewer"))
        if key:
            scores = v.get("scores") if isinstance(v.get("scores"), dict) else {}
            rationales = v.get("rationales") if isinstance(v.get("rationales"), dict) else {}
            gate[key] = {
                # só dims da RUBRICA (Codex adversarial: um dim desconhecido do reviewer viraria
                # prop arbitrária no nó) e só numérico FINITO (json.loads aceita NaN/Infinity).
                "scores": {d: s for d, s in scores.items()
                           if d in close.DIMENSIONS
                           and not isinstance(s, bool) and isinstance(s, (int, float))
                           and math.isfinite(s)},
                "rationales": {d: r for d, r in rationales.items() if isinstance(r, str)},
            }
    gate["pass"] = strikes_n == 0
    gate["strikes_n"] = strikes_n
    return gate


def _gate_props(gate):
    """As FLAT props do gate no :Artefato (episteme: badge de verdict no NÓ — não um nó, não uma
    aresta; MIR-2/3, Cypher-navegável): gate_rubric, gate_pass, gate_strikes_n,
    gate_feynman_<dim>/gate_regular_<dim> (só numéricos), gate_rationales (json) + a proveniência
    (llm_judged/lead/inferred_default). {} quando não há gate — nada a projetar."""
    if not isinstance(gate, dict):
        return {}
    props = {"gate_rubric": gate.get("rubric"), "gate_rubric_sha": gate.get("rubric_sha"),
             "gate_pass": gate.get("pass"), "gate_strikes_n": gate.get("strikes_n"),
             "gate_provenance_class": gate.get("provenance_class", "llm_judged"),
             "gate_rigor": gate.get("rigor", "lead"),
             "gate_validity": gate.get("validity", "inferred_default")}
    rationales = {}
    for rev in ("feynman", "regular"):
        block = gate.get(rev)
        if not isinstance(block, dict):
            continue
        scores = block.get("scores") if isinstance(block.get("scores"), dict) else {}
        for dim, sc in scores.items():
            # re-filtra (um gate REPLAYED de evento antigo pode carregar dim/valor que o filtro
            # de _gate_payload ainda não barrava): rubrica + numérico finito, nunca prop arbitrária.
            if (dim in close.DIMENSIONS and not isinstance(sc, bool)
                    and isinstance(sc, (int, float)) and math.isfinite(sc)):
                props[f"gate_{rev}_{dim}"] = sc
        rat = block.get("rationales")
        if isinstance(rat, dict) and rat:
            rationales[rev] = {d: r for d, r in rat.items() if isinstance(r, str)}
    props["gate_rationales"] = json.dumps(rationales, ensure_ascii=False, sort_keys=True)
    return {k: v for k, v in props.items() if v is not None}


def project_artefato(slug, intent, *, skill, distills=None, proposes=None, cites=None,
                     spec=None, lineage=None, log=eventlog.LOG, gate=None, origin=None,
                     bears_on=None, para=None, para_default=None, reports_on=None):
    """Project a just-published Artefato into the edge's graph — the deterministic spine write
    that was prose in `skills/_shared/memory.md` (the "Project — AFTER you publish" block) and so
    got SKIPPED by the producer. Ported here as a GUARANTEED side-effect of every publish so the
    graph grows model-independently (#30).

    Best-effort / degrade-safe (ADR-0011/0006): the LOG is canonical; this projection is a
    re-derivable view. ANY failure (no group, no neo4j driver, graph unreachable, no OpenAI key
    for the embed) PRINTS and returns — it NEVER raises into the publish (`publish` also wraps the
    call). The next beat reprojects from the log.

    What it writes (idempotent MERGEs), exactly as memory.md specifies:
      (0) backbone — :Genesis (space-0, codename+voice) -GROUNDS-> :Objective; ANCHORS REBUILT
          from the canonical fold each sync (drop retired steers; the Artefato->PROPOSES->Direction
          provenance is left intact);
      (1) :Artefato MERGE + SERVES the Objective (the hub that keeps it reachable from space-0) +
          a content `embedding` (text-embedding-3-small, best-effort — skipped if no key);
      (2) edges — DISTILLS (slug-resolved to existing clusters only, never fabricated), PROPOSES,
          CITES.
    `skill` is passed through so the projection records WHICH producer minted the Artefato."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        distills, proposes, cites = distills or [], proposes or [], cites or []
        lineage = lineage or []
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; the log already holds the truth
        print("project skipped (best-effort, graph unreachable):", ex)
        return
    # The WHOLE spine backbone (Genesis/Objective/Direction) is CANONICAL-LOG ONLY (Codex P2): it
    # writes the install group's identity + objective + the destructive ANCHORS rebuild, all of which
    # read the log. A custom/offline log (a test, a dry-run) must NEVER overwrite the install's live
    # Objective or delete its Directions — it projects ONLY the ADD-only Artefato + its edges below.
    canonical = _is_canonical_log(log)
    try:
        with drv.session() as s:
            if canonical:
                # (0) keep the SPINE BACKBONE current and ROOTED at space-0 (idempotent, cheap).
                # Shared with reproject_graph so the ANCHORS rebuild runs EVERY canonical sweep even
                # when no artefato is missing (Codex P2 — newly folded Directions must get anchored).
                _project_backbone(s, g, log)
            # (1) the Artefato + its content embedding (semantic search; best-effort). `projected_at`
            # is the recency signal recall-push orders by (#30, Codex P2) — set on every (re)project.
            # CLEAR `projection_complete` FIRST (Codex P2): a republish with a corrected payload is
            # NOT complete until THIS run finishes — if it fails partway, the marker stays false so
            # the next sweep re-projects and the graph cannot keep a stale kernel/edges forever.
            # `skill` is COALESCED (Codex P2): the published event now carries skill, so a replay
            # restores the REAL producer identity; a legacy event with no skill folds to None, which
            # coalesce PRESERVES (never clobbers an already-projected skill to NULL).
            # ticket 05: `origin` (user_requested|beat) coalesced like skill — the graph read
            # models weigh user_requested ≫ beat; a legacy call with no origin never clobbers.
            s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) "
                  "SET a.kernel=$k, a.skill=coalesce($skill, a.skill), a.page=$page, "
                  "a.origin=coalesce($origin, a.origin), "
                  "a.projected_at=$pat, a.projection_complete=false",
                  g=g, slug=slug, k=intent, skill=skill, page=f"blog/entries/{slug}.html",
                  origin=origin,
                  pat=_dt.now(_tz.utc).isoformat())
            # B.1 — o verdict do gate como FLAT props no nó (badge, MIR-2/3). `SET a +=` com o
            # dict sanitizado (_gate_props: só primitivos), nunca interpolação de chave no Cypher.
            # Sem gate (legado/replay antigo) → nada a escrever; as props velhas ficam (o replay
            # com gate corrige — forward-only, sem backfill).
            gate_props = _gate_props(gate)
            if gate_props:
                s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) SET a += $props",
                      g=g, slug=slug, props=gate_props)
            # every Artefato SERVES the objective — the hub keeping it reachable from space-0.
            s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}),(o:Objective {group_id:$g}) "
                  "MERGE (a)-[:SERVES]->(o)", g=g, slug=slug)
            # embed the CONTENT (Codex P2): a concept in the body but not the kernel must still be
            # semantically recallable over a.embedding. Re-embed only when the EMBED INPUT CHANGED
            # (Codex P2): store a hash of (slug+intent+spec_text); a republish with changed
            # intent/spec refreshes the stale embedding, but a pure edge-link revisit (same content,
            # e.g. an unresolved distill that resolved) skips the costly re-embed (hash unchanged).
            emb_input = f"{slug}\n{intent}\n{_spec_text(spec)}".strip()
            emb_hash = hashlib.sha256(emb_input.encode("utf-8")).hexdigest()
            row = s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                        "RETURN a.embedding IS NOT NULL AS e, a.embedding_input_hash AS h",
                        g=g, slug=slug).single()
            embed_current = bool(row["e"]) and row["h"] == emb_hash
            if not embed_current:
                try:
                    from openai import OpenAI
                    _load_openai_key()   # source the install/dev OpenAI key if not exported (Codex P1)
                    emb = OpenAI().embeddings.create(model="text-embedding-3-small",
                                                     input=emb_input).data[0].embedding
                    s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                          "SET a.embedding=$e, a.embedding_input_hash=$h",
                          g=g, slug=slug, e=emb, h=emb_hash)
                    embed_current = True
                except Exception as ex:  # noqa: BLE001 — embed is best-effort (no key → skip)
                    # a FAILED embed (key/service down) must NOT mark the projection complete (Codex
                    # P2): leave embed_current False so recovery RETRIES the embed once creds recover,
                    # instead of skipping the slug forever with no/stale embedding.
                    print("embed skipped (best-effort, will retry on recovery):", ex)
            # (2) edges — distills (slug-resolved), proposes, cites. REBUILD this slug's edge set
            # each (re)project (Codex P2): clear the slug's OLD DISTILLS/PROPOSES/CITES first, so a
            # republish/replay with corrected provenance does not leave stale clusters/directions/
            # sources behind — recall stays a faithful projection of the log's latest payload. SERVES
            # is to the single hub (idempotent) and is left intact.
            # C2 CARVE-OUT: DISTILLS/PROPOSES/CITES are AUTHORED edges — the producer declared the
            # distill/proposal/citation and they are proof-bound into the close digest. They are NOT
            # the cosine-nominated RELATES_TO path, which is the ONLY edge C2 (mutual-kNN candidate →
            # NLI/entailment → grounded typer) governs. RELATES_TO is OUT of v1's publisher entirely
            # (research spec: cosine-nominates-the-author-disposes); these MERGEs emit directly by
            # design and require no NLI gating.
            # L4: the three AUTHORED lineage labels JOIN this destructive rebuild set so a corrected
            # republish (lineage now points elsewhere, or is removed) strands no stale lineage edge.
            # Ticket A: the valenced bears_on labels + PARA + REPORTS_ON join the destructive
            # rebuild — a republish with corrected declarations strands no stale edge.
            s.run("MATCH (a:Artefato {group_id:$g, slug:$slug})"
                  "-[r:DISTILLS|PROPOSES|CITES|BUILDS_ON|SUPERSEDES|CONTRADICTS"
                  "|SUPPORTS|REFUTES|QUALIFIES|INCONCLUSIVE|PARA|REPORTS_ON]->() "
                  "DELETE r", g=g, slug=slug)
            # resolve distills against grill-curated Entity clusters AND automatic Communities.
            # (communities.consolidate never stamps Entity.curated_cluster — Community is the
            # navigation organ.) Soft-pending: a still-missing ref is recorded on the node but
            # does NOT strand projection_complete=false forever (that hid Artefatos from recall).
            catalog = _distill_catalog(s, g)
            pending_distills = []
            for ref in distills:                  # link ONLY existing targets (never fabricate)
                key = _cluster_slug(str(ref).replace("cluster:", ""))
                hit = catalog.get(key)
                if not hit:
                    pending_distills.append(str(ref))
                    continue
                kind, label = hit
                _link_distill(s, g, slug, kind, label)
            if pending_distills:
                s.run(
                    "MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                    "SET a.pending_distills=$pending",
                    g=g, slug=slug, pending=pending_distills)
            else:
                s.run(
                    "MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                    "REMOVE a.pending_distills",
                    g=g, slug=slug)
            for p in proposes:
                body = p.get("body") if isinstance(p, dict) else None
                if not body:
                    continue
                s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                      "MERGE (d:Direction {group_id:$g, body:$b}) MERGE (a)-[:PROPOSES]->(d)",
                      g=g, slug=slug, b=body)
            for c in cites:
                ref = c.get("ref") if isinstance(c, dict) else None
                if not ref:
                    continue
                s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) "
                      "MERGE (src:Source {group_id:$g, key:$key}) MERGE (a)-[:CITES]->(src)",
                      g=g, slug=slug, key=ref)
            # (2b) L4 — AUTHORED typed lineage as DIRECTED edges this -> prior. The producer's
            # `item["type"]` is mapped through the FIXED LINEAGE_LABELS allowlist (an out-of-allowlist
            # type is dropped); the label is a literal from that dict, never interpolated caller data,
            # so the Cypher is fixed per label. The prior is named by `target` (the prior Artefato
            # slug). If the prior :Artefato is not in the graph yet (out-of-order publish), the MERGE
            # matches nothing — treat as UNRESOLVED (mirror unresolved_distills): leave the projection
            # incomplete so the next sweep re-projects once the prior lands.
            unresolved_lineage = False
            for item in lineage:
                if not isinstance(item, dict):
                    continue
                label = LINEAGE_LABELS.get(item.get("type"))
                prior = item.get("target") or item.get("slug")
                if not (label and prior):
                    continue
                row = s.run(
                    "MATCH (a:Artefato {group_id:$g, slug:$slug}),"
                    "(p:Artefato {group_id:$g, slug:$prior}) "
                    "MERGE (a)-[:%s]->(p) RETURN count(p) AS n" % label,
                    g=g, slug=slug, prior=prior).single()
                if not row or row["n"] == 0:
                    unresolved_lineage = True   # prior not in the graph yet — revisit next sweep
            # (2b2) Ticket A — the valenced bears_on edges (→:Hypothesis) + PARA (→promoted
            # parceiro Entity). Both use the unresolved pattern: a target not in the graph yet
            # leaves the projection incomplete, so the next sweep re-links once it lands.
            unresolved_bears = _project_bears_on(s, g, slug, bears_on)
            unresolved_para = _project_para(s, g, slug, para)
            _project_reports_on(s, g, slug, reports_on, log=log)
            # (2b3) curadoria autoral — the para-o-mentee DEFAULT mark (prop + promoted-only
            # edge). Fail-safe by design: NEVER joins the unresolved set / completion marker.
            _project_para_default(s, g, slug, para_default)
            # (2c) MENTIONS — ticket D: the entities the published CONTENT (intent+spec) DE FATO
            # names (curadoria inline no publish — the offline curator was cut). NOT emb_input: the
            # slug is metadata, and its hyphens count as word boundaries — a compound slug would
            # fabricate an asserted mention the body never makes (codex #4). project_mentions rides
            # THIS session and never raises; None (a swallowed mid-rebuild failure — the wipe may
            # have landed) leaves the projection INCOMPLETE so the next sweep replays it (codex #3).
            import relate
            mentions_ok = relate.project_mentions(
                s, g, slug, f"{intent}\n{_spec_text(spec)}") is not None
            # (3) COMPLETION MARKER — set LAST. Hard gates: current embedding, mentions rebuild ok,
            # lineage/bears/para resolved (out-of-order targets). Distills are soft: linked when a
            # Community or curated Entity exists; otherwise stored as pending_distills and retried
            # on reproject WITHOUT hiding the Artefato from recall (projection_complete=true is the
            # recall filter). A failed embed still leaves complete=false so recovery retries.
            s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) SET a.projection_complete=$done",
                  g=g, slug=slug,
                  done=(embed_current and not unresolved_lineage
                        and mentions_ok and not unresolved_bears and not unresolved_para))
    except Exception as ex:  # noqa: BLE001 — a failed projection is reported, never fatal
        print("project failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


_DEFAULT_PROJECT = object()  # sentinel: "use module project_artefato" (resolved at CALL time so a
                             # test can patch publisher.project_artefato to stay offline) vs an
                             # explicit None ("skip the projection") vs an injected fake.


def publish(slug, spec, intent, *, skill, verdict=None, proposes=None, distills=None,
            cites=None, lineage=None, dispatch_id=None, date=None, log=eventlog.LOG,
            blog_dir=BLOG_DIR, embed_fn=None, project_fn=_DEFAULT_PROJECT,
            visual_flags=None, bears_on=None, para=None, reports_on=None,
            experiment_curation=None) -> Path:
    """Publish an Artefato: render → self-contained neutral HTML → atomic state record.

    #2/#3 at the seam: RAISES ValueError unless `verdict` is the UNFORGEABLE, BOUND proof
    (binding covers slug+spec+intent+cites+proposes+distills+skill+lineage+dispatch_id — E1b)
    `close.run_close` mints — `close.verify_proof` requires the run_close-only token, a digest
    that BINDS to THIS exact payload (slug + spec + intent + cites + proposes + distills +
    skill + lineage), both blind reviewers passed, and both CANONICAL reviewer identities are
    present. A hand-built dict, a proof minted for a different artefato (digest mismatch), an
    altered distills/skill/lineage, a single-reviewer proof, or a proof from fake reviewers raises here, before
    any HTML or state lands — the publisher is never a back door around the gate. C3 at the seam: RAISES when `intent` is
    missing/empty — you cannot publish without the kernel (and defensively when the genus
    contract is violated). #4 at the seam: the slug is validated + contained under blog_dir,
    the page written via temp+rename.

    Order (#2/#3, ADR-0006): render the page in memory → append the atomic event WITH the spec
    (the COMMIT POINT; the log is truth) → THEN write the HTML (a projection) → THEN emit source
    signals. Everything after the commit is a recoverable projection: a page-write or signal
    failure is no longer unrecoverable — the logged spec re-renders the exact page and the logged
    cites re-emit the signals via `reproject_missing_pages`. Signal emission is non-fatal to the
    page (#4). Returns the written page Path. `date` is a param (defaults to today) so tests pin
    it; `embed_fn` is injectable so the source-signal step runs offline.

    S2 (E1/E1b/E1c): `dispatch_id` is the dispatch's IDENTITY — the producer's publish_fn reads
    it off the proof-bound artefato (`dispatch_id=art['dispatch_id']`), verify_proof binds it
    into the digest (a publish under another dispatch identity is a digest mismatch, E1b), and
    `publish_artefato_atomic` persists it on the event — REQUIRED there for the canonical log
    (E1c), so a canonical publish without it fails loud before anything lands.
    """
    # ADR-0016 FIRST — no wake, no publish: the refusal names the real gap (`no-wake`), not a
    # proof error. The stamp is checked on the SAME log this publish would commit to. S2 gate
    # D1: an id-carrying publish fast-fails on the IDENTITY-HELD check (E1 — this dispatch's
    # OWN stamp, unconsumed; the global newest-stamp check would let concurrent dispatches
    # spend each other's wakes and let an unminted id ride a valid proof). The authoritative
    # form of the same check runs under the eventlog lock at the commit below; id-less callers
    # keep the legacy global check.
    if isinstance(dispatch_id, str) and dispatch_id.strip():
        if not eventlog.wake_fresh_for(dispatch_id, log=log):
            raise RuntimeError(
                f"no-wake: cannot publish {slug!r} under dispatch_id {dispatch_id!r} — no "
                "unconsumed dispatch.open minted that id on this log (E1 identity-held gate; "
                "ADR-0016: run tools/predispatch.py at dispatch entry and carry ITS id; one "
                "wake per publish)")
    elif not eventlog.wake_fresh(log=log):
        raise RuntimeError(
            f"no-wake: cannot publish {slug!r} — no dispatch.open newer than the last "
            "artefato.published on this log (ADR-0016: run tools/predispatch.py at dispatch "
            "entry; one wake per publish)")
    verify_proof(verdict, slug=slug, spec=spec, intent=intent,
                 cites=cites or [], proposes=proposes or [],
                 distills=distills, skill=skill, lineage=lineage, dispatch_id=dispatch_id,
                 bears_on=bears_on, para=para, reports_on=reports_on,
                 experiment_curation=experiment_curation)
    # Canonical lineage from here on (Codex): the proof binds the NORMALIZED lineage and the event persists
    # it, so the live projection must see the SAME — else proof/event-invisible junk (e.g. a blank-slug item
    # stripped by the digest) could still drive project_artefato and strand projection_complete=false.
    lineage = normalize_lineage(lineage)
    # Ticket A: same rule for the valenced/PARA declarations — the digest bound the NORMALIZED
    # form; the event and the live projection must see the SAME.
    bears_on = normalize_bears_on(bears_on)
    para = normalize_para(para)
    reports_on = normalize_reports_on(reports_on)
    # Validate early, before render/page work. The event seam repeats the same normalization and writes
    # the resulting experiment.curated payloads in the atomic publish batch.
    normalize_experiment_curation(reports_on, experiment_curation, report_slug=slug, by=skill)
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")
    if skill not in PRODUCER_ROSTER:
        raise ValueError(
            f"skill {skill!r} is not in the producer roster {PRODUCER_ROSTER} — "
            "an out-of-roster skill is refused before anything is written (Codex round-4)")
    # The legacy publish road is CLOSED for the rito-migrated producers (docs/rito-runtime.md):
    # their ONLY road is the rite (rito.run_rito → publish_rito, which does NOT route through
    # here). This refusal makes the legacy close (close.run_close → publish) impossible for them,
    # so the rite is forced rather than opt-in-by-cognition. prototype/lazer stay legacy (excepted).
    if skill in producer_descriptor.RITO_PRODUCERS:
        raise ValueError(
            f"{skill}: legacy publish is closed for rito producers — produce through "
            "rito.run_rito (docs/rito-runtime.md). prototype/lazer excepted.")

    out = _safe_target(slug, blog_dir)

    cites = cites or []
    # The publisher-side genus check must see EVERY field check_genus reads, or it disagrees with
    # run_close's check (Codex P2): the rich-rite floor reads `distills` (lineage) and content, so
    # a report whose lineage rides on its published `distills` would pass run_close but raise here.
    artefato = {"intent": intent, "proposes": proposes or [], "cites": cites,
                "content": spec, "distills": distills or [], "skill": skill, "lineage": lineage}
    violations = check_genus(artefato)
    if violations:
        raise ValueError(f"artefato {slug!r} violates the genus contract: {violations}")

    body_html, page = _render_page(slug, spec, skill=skill, date=date)

    # COMMIT POINT (#2, ADR-0006: the log is truth). The atomic event carries the proof-bound
    # spec, so the page is fully regenerable from the log alone. EVERYTHING after this is a
    # recoverable projection (reproject_missing_pages re-derives it from the logged spec/cites).
    # require_wake=True: the AUTHORITATIVE wake check runs under the eventlog lock at this
    # commit (codex gate) — the early check at entry is only a fast-fail; one stamp admits
    # exactly one publish even under concurrent publishers.
    # R6 (S10) — compute the adoption telemetry BEFORE the commit so it rides in the SAME atomic batch as
    # the published event (durable, no crash window where the artefato published but its adoption was lost).
    # `_adoption_event` is self-defensive and NEVER raises (a compute failure yields a payload with an
    # `error` marker, not a dropped record — Codex S10), so EVERY publish commits an adoption event. The
    # outer guard is a last-resort backstop that still emits a minimal error record rather than None.
    try:
        adoption = _adoption_event(slug, skill, spec, visual_flags)
    except Exception as e:  # noqa: BLE001 — must STILL emit a record, never drop it (never block the page)
        adoption = {"slug": slug, "producer": skill, "owed": None, "satisfied": None,
                    "degraded": None, "shortfall": None, "capability_state": None,
                    "error": f"{type(e).__name__}: {e}"}

    # S6 (design-close §5): the unaddressed criticism rides as a first-class event field, read OFF
    # the proof (`proof['unaddressed']`) — NEVER a caller arg (a caller cannot inject residuals the
    # gate did not mint; verify_proof already bound the appended spec). None on a normal publish.
    residuals = verdict.get("unaddressed") if isinstance(verdict, dict) else None
    # B.1 (ticket B) — pare de descartar o verdict: o gate persiste como campo do MESMO batch
    # atômico (verify_proof já validou o proof acima; a projeção é lida DELE, nunca de um arg
    # do caller). None quando o proof não projeta (nunca bloqueia o publish).
    gate = _gate_payload(verdict)
    # ticket 05 (hierarquia de ORIGEM): the artefato carries its origin — resolved from the
    # dispatch.open that MINTED this dispatch_id (user_requested ≫ beat), never a caller arg
    # (a producer cannot claim user_requested the wake did not declare; the atomic seam derives
    # its own copy for the event — codex meta-gate #5). Id-less/legacy → beat. Resolved here
    # only for the graph projection below.
    origin = eventlog.dispatch_origin(dispatch_id, log=log)
    published_ev, _ = eventlog.publish_artefato_atomic(
        slug, intent, proposes=proposes, distills=distills,
        cites=cites, spec=spec, skill=skill, log=log,
        lineage=lineage, require_wake=True, adoption=adoption,
        dispatch_id=dispatch_id, residuals=residuals, gate=gate,
        bears_on=bears_on, para=para, reports_on=reports_on,
        experiment_curation=experiment_curation)
    # curadoria autoral: the para-o-mentee default is derived ONCE, at the event seam (origin
    # pattern — never a caller arg, never in the digest); the projection reads it OFF the
    # committed event so event and graph can never disagree.
    para_default = published_ev["payload"].get("para_default")

    # the page is a PROJECTION written after the commit — a failure here is recoverable.
    _write_page(out, page)

    _post_publish_sideeffects(
        slug, intent, spec=spec, skill=skill, body=body_html, cites=cites, embed_fn=embed_fn,
        log=log, project_fn=project_fn, distills=distills, proposes=proposes, lineage=lineage,
        gate=gate, origin=origin, bears_on=bears_on, para=para, para_default=para_default,
        reports_on=reports_on)
    return out


def _post_publish_sideeffects(slug, intent, *, spec, skill, body, cites, embed_fn, log,
                              project_fn=_DEFAULT_PROJECT, distills=None, proposes=None,
                              lineage=None, gate=None, origin=None, bears_on=None, para=None,
                              para_default=None, reports_on=None):
    """The post-commit side-effect sequence SHARED by both publish paths (`publish` and
    `publish_rito`), so a rito-published artefato is a first-class citizen of the graph/corpus
    (docs/rito-runtime.md §Post-publish side-effects). Runs AFTER the commit + page write;
    every step is BEST-EFFORT — a failure is reported/swallowed, NEVER aborts the publish (the
    log is canonical; the next beat reprojects/re-emits). `body` is the text the cite snippets
    are scored against (legacy: body_html; rito: the markdown body via _spec_text).

    source-signal emission is NON-FATAL to the page (#4): a signal-store failure must not
    corrupt the published page; the cites are durably logged, so the signals are recoverable
    (reproject_missing_pages re-emits any missing ones)."""
    try:
        _signal_cites(slug, body, cites or [], embed_fn, log)
    except Exception:
        pass

    # project-after-publish (#30): a GUARANTEED, best-effort side-effect after the commit — the
    # spine projection that was prose in memory.md and got skipped, now runs every publish so the
    # graph grows model-independently. NON-FATAL (ADR-0011/0006): a failed projection is reported,
    # never breaks the publish — the log is canonical, the next beat reprojects. Injectable so the
    # seam runs offline. The double-wrap (here + inside project_artefato) is belt-and-suspenders:
    # even an injected project_fn that raises can never strand the already-committed Artefato.
    # resolve the default at CALL time (name lookup) so a test can patch project_artefato to stay
    # offline; an explicit None skips projection entirely. DEFAULT-SKIP for a non-canonical log
    # (Codex P2): a dry-run/test/recovery publish to a temp log must NOT write into the install
    # graph — those nodes could not be replayed or cleaned from the canonical log. Only the
    # canonical-log publish projects by default; a caller wanting to project a custom log must pass
    # an explicit project_fn.
    if project_fn is _DEFAULT_PROJECT:
        project_fn = project_artefato if _is_canonical_log(log) else None
    if project_fn is not None:
        try:
            project_fn(slug, intent, skill=skill, distills=distills, proposes=proposes,
                       cites=cites, spec=spec, lineage=lineage, log=log, gate=gate,
                       origin=origin, bears_on=bears_on, para=para,
                       para_default=para_default, reports_on=reports_on)
        except Exception as ex:  # noqa: BLE001 — projection is best-effort, never fatal
            print(f"project skipped for {slug!r} (best-effort, reproject next beat):", ex)


def publish_rito(slug, run_dir, *, intent, skill="report", dispatch_id=None,
                 log=eventlog.LOG, blog_dir=BLOG_DIR, proposes=None, distills=None,
                 cites=None, lineage=None, bears_on=None, para=None, reports_on=None,
                 experiment_curation=None, embed_fn=None, project_fn=_DEFAULT_PROJECT):
    """The rito's publication seam (docs/rito-runtime.md) — the terminal stage of the rite.

    Proves EXECUTION, never scores the artifact: refuses unless the run dir's sealed manifest
    shows every cognitive stage COMPLETED and the fail-closed final review allowed the
    package. THE FORM IS PINNED AS A PIPELINE STAGE: recomputes the approved renderer's
    output (render.markdown_page_bytes) from the sealed markdown and REFUSES a hash mismatch
    against the sealed final_html receipt — so the exact reviewed bytes, and only they, ship.

    Order (ADR-0006, same as `publish`): atomic `artefato.published` event first (spec format
    `edge-markdown/v1` carrying the markdown + renderer id + manifest binding, so the page is
    fully re-derivable from the log via `_render_page`'s markdown branch) → THEN the exact
    page bytes via temp+rename. C3 (intent kernel) and the ADR-0016 wake gate ride the same
    atomic call. Returns the publication receipt the rite seals as its terminal stage."""
    if blog_dir is None:
        blog_dir = BLOG_DIR    # None de caller (rito blog_dir default) nunca vira crash no estagio 11

    import rito  # lazy: rito ↔ publisher may not import each other at module scope
    run_dir = Path(run_dir)
    manifest_path = run_dir / rito.MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"no rite manifest at {manifest_path} — the rite did not run")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("slug") != slug:
        raise ValueError(f"manifest slug {manifest.get('slug')!r} != publish slug {slug!r}")
    stages = {s.get("name"): s for s in manifest.get("stages") or []}
    incomplete = [name for name in rito.COGNITIVE_STAGES
                  if (stages.get(name) or {}).get("status") != "completed"]
    if incomplete:
        raise ValueError(f"rite incomplete — stages not completed: {incomplete} (a run that "
                         "didn't traverse the whole rite does not publish)")
    acceptance = (stages.get("final_review") or {}).get("acceptance") or {}
    if not acceptance.get("package_allowed"):
        raise ValueError(f"final review did not allow publication: {acceptance}")

    md_path = run_dir / stages["treatment_cleanup"]["output_file"]
    data = md_path.read_bytes() if md_path.is_file() else b""
    if hashlib.sha256(data).hexdigest() != stages["treatment_cleanup"]["output"]["sha256"]:
        raise ValueError(f"sealed markdown drifted on disk: {md_path} — refusing to publish")
    markdown = data.decode("utf-8")

    # THE PIN: recompute the approved renderer's bytes; refuse any mismatch with the sealed
    # final_html receipt (pinning the pipeline, not scoring the artifact).
    page_bytes = render.markdown_page_bytes(markdown)
    page_sha = hashlib.sha256(page_bytes).hexdigest()
    sealed_html_sha = (stages.get("final_html") or {}).get("output", {}).get("sha256")
    if page_sha != sealed_html_sha:
        raise ValueError(
            f"pinned renderer mismatch: recomputed page sha {page_sha} != sealed final_html "
            f"receipt {sealed_html_sha} ({render.RENDERER_ID}) — refusing to publish")

    out = _safe_target(slug, blog_dir)
    core = rito.manifest_core_hash(manifest)
    spec = {"format": "edge-markdown/v1", "markdown": markdown,
            "renderer_id": render.RENDERER_ID, "rito_manifest_sha256": core,
            "page_sha256": page_sha}

    # IDEMPOTENT RESUME (codex [high]): the event is the commit point (ADR-0006), the page a
    # projection — a crash between them must not double-publish. If THIS run's bound event
    # already landed (same slug + manifest core + page hash), skip the commit and just
    # re-derive the projection; the receipt names the original event.
    # the reuse predicate is the FULL spec the verifier binds to (codex gate 2): a prior
    # event that verify_rito would reject must never be reused.
    published_ev = next(
        (ev for ev in eventlog.read(types=["artefato.published"], log=log)
         if (ev.get("payload") or {}).get("slug") == slug
         and (ev.get("payload") or {}).get("spec") == spec),
        None)
    fresh_commit = published_ev is None
    if fresh_commit:
        published_ev, _ = eventlog.publish_artefato_atomic(
            slug, intent, spec=spec, skill=skill, log=log,
            dispatch_id=dispatch_id, require_wake=True,
            proposes=proposes, distills=distills, cites=cites, lineage=lineage,
            bears_on=bears_on, para=para, reports_on=reports_on,
            experiment_curation=experiment_curation, _rite_authorized=True)

    # the EXACT reviewed bytes, temp+rename (a failure here is recoverable from the log)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".html.tmp")
    tmp.write_bytes(page_bytes)
    os.replace(tmp, out)

    # SAME post-publish side-effects as the legacy path (docs/rito-runtime.md §Post-publish
    # side-effects) — source-signal + graph projection — so a rito-published artefato is a
    # first-class citizen of the graph/corpus. Best-effort, after the commit. `origin` is derived
    # from the dispatch that minted this id (legacy pattern); `para_default` is read OFF the
    # committed event (never a caller arg). No verdict here → no gate to project.
    # ONLY on a FRESH commit (codex adversarial): the resume branch reuses an already-committed
    # event whose side-effects the original publish ALREADY emitted — re-emitting here would
    # double-count source signals (source_signal is a bare append, no dedup) and re-derive
    # origin/para from the RETRY's args instead of the committed event, diverging graph from log.
    # A resume that crashed BEFORE its side-effects landed is healed by reproject_missing_pages /
    # the next beat sweep (re-emits only MISSING signals, reprojects) — the same recovery the
    # legacy path relies on. So the resume path stays a pure page re-derivation, like the commit.
    if fresh_commit:
        origin = eventlog.dispatch_origin(dispatch_id, log=log)
        para_default = (published_ev.get("payload") or {}).get("para_default")
        _post_publish_sideeffects(
            slug, intent, spec=spec, skill=skill, body=markdown, cites=cites, embed_fn=embed_fn,
            log=log, project_fn=project_fn, distills=distills, proposes=proposes, lineage=lineage,
            origin=origin, bears_on=bears_on, para=para, para_default=para_default,
            reports_on=reports_on)
    return {"event_seq": published_ev["seq"], "event_ts": published_ev["ts"],
            "page_path": str(out), "page_sha256": page_sha,
            "rito_manifest_sha256": core, "renderer_id": render.RENDERER_ID}


def promote_artefato_to_source(slug, reviewer, note="", log=eventlog.LOG):
    """B.3 — a promoção artefato→source. O LOG é a verdade (ADR-0006): o evento de integração
    HITL landa PRIMEIRO (eventlog.integrate_artefato_source valida autoridade + slug publicado);
    a marca no nó do grafo é uma PROJEÇÃO best-effort depois — e SÓ no log canônico (um log de
    teste/dry-run nunca escreve no grafo do install, mesmo padrão de project_artefato). Retorna
    o evento escrito."""
    ev = eventlog.integrate_artefato_source(slug, reviewer, note=note, log=log)
    if _is_canonical_log(log):
        # o ts da marca é o do EVENTO (Codex adversarial: `now()` local quebraria "o log é a
        # verdade" num replay — a projeção deve ser determinística do evento).
        _mark_integrated_source(slug, reviewer, ts=ev.get("ts"))
    return ev


# ---------------------------------------------------------------------------
# Structured Activity/Direction lenses — deterministic GraphStore projection.
# ---------------------------------------------------------------------------

def project_lentes(log, store):
    """Replay the structured lenses into ``store`` best-effort, keyed by stable refs.

    The log/folds remain truth; this projection performs no extraction or model call.  A graph
    outage stops the pass and names every ref in the untouched suffix so the next sweep can
    deterministically finish it.
    """
    from graph_store import EdgeSpec, GraphUnavailable, ProjectionResult

    events = eventlog.read(log=log)
    activities = eventlog.atividades_at(log=log)
    claims = eventlog.claims_at(log=log)
    graph_refs = {}
    operations = []

    def _seq_for(event_types, ulid):
        return next((event.get("seq") for event in events
                     if event.get("type") in event_types
                     and isinstance(event.get("payload"), dict)
                     and event["payload"].get("ulid") == ulid), None)

    for _full_ref, activity in sorted(activities.items()):
        ulid = activity["ulid"]
        ref = f"atividade:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid,
            "num": activity.get("num"),
            "operacao": activity.get("operacao"),
            "finalidade": activity.get("finalidade"),
            "estado": activity.get("estado"),
            "tipo_ref": activity.get("tipo_ref"),
            "tier": activity.get("tier"),
            "contested": bool(activity.get("contested")),
            "src_seq": _seq_for({"atividade.opened"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Atividade", props)))

    runs = eventlog.runs_at(log=log)
    for _full_ref, run in sorted(runs.items()):
        ulid = run["ulid"]
        ref = f"run:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid, "num": run.get("num"), "operacao": run.get("operacao"),
            "resultado": run.get("resultado"), "tier": run.get("tier"),
            "leva": run.get("leva"), "prediction_hash": run.get("prediction_hash"),
            "src_seq": _seq_for({"run.opened"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Run", props)))

    facts = {}
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (event.get("type") == "fato.observed" and isinstance(payload.get("ulid"), str)
                and isinstance(event.get("seq"), int)):
            facts[payload["ulid"]] = (event, payload)
    for ulid, (event, fact) in sorted(facts.items()):
        ref = f"fato:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid, "num": fact.get("num"), "operacao": fact.get("operacao"),
            "body": fact.get("body"), "tier": fact.get("tier"), "leva": fact.get("leva"),
            "src_seq": event["seq"],
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Fato", props)))

    arcs = eventlog.arcos_at(log=log)
    for _full_ref, arc in sorted(arcs.items()):
        ulid = arc["ulid"]
        ref = f"arco:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid, "num": arc.get("num"), "operacao": arc.get("operacao"),
            "nome": arc.get("nome"), "tier": arc.get("tier"),
            "valencia": arc.get("valencia"), "julgamento": arc.get("julgamento"),
            "src_seq": _seq_for({"arco.opened"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Arco", props)))

    wayfinds = eventlog.wayfinds_at(log=log)
    for _full_ref, item in sorted(wayfinds["maps"].items()):
        ulid = item["ulid"]
        ref = f"map:{ulid}"
        graph_refs[ulid] = ref
        thread = item.get("thread") if isinstance(item.get("thread"), dict) else {}
        props = {
            "ulid": ulid, "num": item.get("num"), "operacao": item.get("operacao"),
            "titulo": item.get("titulo"), "estado": item.get("estado"),
            "tier": item.get("tier"), "thread_uuid": thread.get("uuid"),
            "thread_display": thread.get("display"), "src_seq": _seq_for({"map.opened"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Map", props)))
    for _full_ref, item in sorted(wayfinds["tickets"].items()):
        ulid = item["ulid"]
        ref = f"ticket:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid, "num": item.get("num"), "operacao": item.get("operacao"),
            "titulo": item.get("titulo"), "question": item.get("question"),
            "estado": item.get("estado"), "tier": item.get("tier"),
            "src_seq": _seq_for({"ticket.opened"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Ticket", props)))
    for state in ("propostos", "ratificados", "declinados"):
        for item in wayfinds["moves"].get(state, []):
            ulid = item.get("ulid")
            if not isinstance(ulid, str):
                continue
            ref = f"move:{ulid}"
            graph_refs[ulid] = ref
            props = {
                "ulid": ulid, "kind": item.get("kind"), "estado": item.get("estado"),
                "move_key": item.get("move_key"), "author": item.get("author"),
                "src_seq": item.get("seq"),
            }
            operations.append((ref, lambda ref=ref, props=props:
                               store.merge_node(ref, "Move", props)))

    claim_items = []
    claim_items.extend((ulid, item, "asserted")
                       for ulid, item in claims.get("declared", {}).items())
    claim_items.extend((ulid, item, "llm_judged")
                       for ulid, item in claims.get("hypothesized", {}).items())
    for ulid, claim, tier in sorted(claim_items):
        ref = f"claim:{ulid}"
        graph_refs[ulid] = ref
        props = {
            "ulid": ulid,
            "statement": claim.get("statement"),
            "tier": tier,
            "contested": bool(claim.get("contested")),
            "promoted_to": claim.get("promoted_to"),
            "src_seq": _seq_for({"hypothesis.declared", "claim.hypothesized"}, ulid),
        }
        operations.append((ref, lambda ref=ref, props=props:
                           store.merge_node(ref, "Claim", props)))

    session_ids = sorted({
        touch.get("sessao")
        for activity in activities.values()
        for touch in activity.get("toques", [])
        if isinstance(touch.get("sessao"), str)
    })
    for session_id in session_ids:
        ref = f"sessao:{session_id}"
        operations.append((ref, lambda ref=ref, session_id=session_id:
                           store.merge_node(ref, "Episodic", {"session_id": session_id})))

    operation_names = sorted({
        item.get("operacao")
        for collection in (activities.values(), runs.values(), arcs.values(),
                           wayfinds["maps"].values())
        for item in collection
        if isinstance(item.get("operacao"), str)
    })
    for operation_name in operation_names:
        ref = f"operacao:{operation_name}"
        operations.append((ref, lambda ref=ref, operation_name=operation_name:
                           store.merge_node(ref, "Objective", {"operacao": operation_name})))

    edge_sets = {}

    def _plane(tier):
        return "llm_judged" if tier == "llm_judged" else "asserted"

    def _put_edge(owner_ref, kind, target_ref, seq, tier="asserted", **props):
        if not (isinstance(seq, int) and seq > 0 and owner_ref and target_ref):
            return
        edge_props = {"src_seq": seq, "provenance_class": _plane(tier), **props}
        current = edge_sets.setdefault((owner_ref, kind), {}).get(target_ref)
        if current is None or current.props["src_seq"] <= seq:
            edge_sets[(owner_ref, kind)][target_ref] = EdgeSpec(target_ref, edge_props)

    def _latest_event(types, predicate):
        candidates = [event for event in events
                      if event.get("type") in types and isinstance(event.get("payload"), dict)
                      and isinstance(event.get("seq"), int) and predicate(event["payload"])]
        return max(candidates, key=lambda event: event["seq"]) if candidates else None

    # Atividade → Arco membership and Session → Atividade touches.
    for activity in activities.values():
        activity_ref = graph_refs[activity["ulid"]]
        arc_ulid = activity.get("arco")
        if arc_ulid in graph_refs:
            assertion = _latest_event(
                {"atividade.opened", "arco.moved"},
                lambda payload, activity=activity, arc_ulid=arc_ulid: (
                    (payload.get("ulid") == activity["ulid"] and payload.get("arco") == arc_ulid)
                    or (payload.get("ref") == activity["ulid"]
                        and payload.get("arco_novo") == arc_ulid)
                ),
            )
            if assertion:
                _put_edge(activity_ref, "PART_OF", graph_refs[arc_ulid], assertion["seq"],
                          assertion["payload"].get("tier"))
        for touch in activity.get("toques", []):
            session_id = touch.get("sessao")
            if isinstance(session_id, str):
                _put_edge(f"sessao:{session_id}", "TOUCHES", activity_ref,
                          touch.get("seq"), touch.get("tier"))

    # Current Activity bearings (same endpoint is amendable, latest assertion wins).
    for event in events:
        if event.get("type") != "atividade.bears_on" or not isinstance(event.get("payload"), dict):
            continue
        payload = event["payload"]
        source, target = payload.get("ref"), payload.get("alvo")
        if source in graph_refs and target in graph_refs:
            _put_edge(graph_refs[source], "BEARS_ON", graph_refs[target], event.get("seq"),
                      payload.get("tier"), valencia=payload.get("valencia"),
                      evidencia=payload.get("evidencia"))

    # Run/Ticket verdict bearings.
    for run in runs.values():
        closure = run.get("fecho") or {}
        for bearing in closure.get("bears_on", []):
            target = bearing.get("alvo") if isinstance(bearing, dict) else None
            if target in graph_refs:
                _put_edge(graph_refs[run["ulid"]], "BEARS_ON", graph_refs[target],
                          closure.get("seq"), closure.get("tier"),
                          valencia=bearing.get("valencia"))
    for ticket in wayfinds["tickets"].values():
        ticket_ref = graph_refs[ticket["ulid"]]
        opened = _latest_event({"ticket.opened"},
                               lambda payload, ticket=ticket: payload.get("ulid") == ticket["ulid"])
        if opened and ticket.get("map") in graph_refs:
            _put_edge(ticket_ref, "PART_OF", graph_refs[ticket["map"]], opened["seq"],
                      opened["payload"].get("tier"))
        deps_event = _latest_event(
            {"ticket.opened", "ticket.deps_changed"},
            lambda payload, ticket=ticket: (payload.get("ulid") == ticket["ulid"]
                                             or payload.get("ref") == ticket["ulid"]),
        )
        if deps_event:
            for blocker in ticket.get("blocked_by", []):
                if blocker in graph_refs:
                    _put_edge(ticket_ref, "BLOCKED_BY", graph_refs[blocker], deps_event["seq"],
                              deps_event["payload"].get("tier", "asserted"))
        if opened and ticket.get("inscricao") in graph_refs:
            _put_edge(ticket_ref, "INSCRIBES", graph_refs[ticket["inscricao"]], opened["seq"],
                      opened["payload"].get("tier"))
        closure = ticket.get("fecho") or {}
        for bearing in closure.get("bears_on", []):
            target = bearing.get("alvo") if isinstance(bearing, dict) else None
            if target in graph_refs:
                _put_edge(ticket_ref, "BEARS_ON", graph_refs[target], closure.get("seq"),
                          closure.get("tier"), valencia=bearing.get("valencia"))

    # Immutable claim lineage.
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if event.get("type") == "hypothesis.superseded":
            old, new = payload.get("old"), payload.get("new")
            if old in graph_refs and new in graph_refs:
                _put_edge(graph_refs[new], "SUPERSEDES", graph_refs[old], event.get("seq"))

    # Latest stable landmark per operation (target grain → operation hub).
    latest_marcos = {}
    for event in events:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if (event.get("type") == "marco.set" and isinstance(payload.get("operacao"), str)
                and payload.get("ref") in graph_refs):
            latest_marcos[payload["operacao"]] = (event, payload)
    for operation_name, (event, payload) in latest_marcos.items():
        _put_edge(graph_refs[payload["ref"]], "MARCO_OF", f"operacao:{operation_name}",
                  event.get("seq"), "asserted")

    # Every owned edge kind is replaced, including empty desired sets, so stale topology leaves.
    owners_by_kind = set(edge_sets)
    for item in activities.values():
        owners_by_kind.update({
            (graph_refs[item["ulid"]], "BEARS_ON"),
            (graph_refs[item["ulid"]], "PART_OF"),
            (graph_refs[item["ulid"]], "MARCO_OF"),
        })
    for item in runs.values():
        owners_by_kind.update({
            (graph_refs[item["ulid"]], "BEARS_ON"),
            (graph_refs[item["ulid"]], "MARCO_OF"),
        })
    for ulid in facts:
        owners_by_kind.add((graph_refs[ulid], "MARCO_OF"))
    for item in arcs.values():
        owners_by_kind.add((graph_refs[item["ulid"]], "MARCO_OF"))
    for item in wayfinds["tickets"].values():
        owners_by_kind.update({
            (graph_refs[item["ulid"]], "PART_OF"),
            (graph_refs[item["ulid"]], "BLOCKED_BY"),
            (graph_refs[item["ulid"]], "INSCRIBES"),
            (graph_refs[item["ulid"]], "BEARS_ON"),
        })
    owners_by_kind.update((f"sessao:{session_id}", "TOUCHES") for session_id in session_ids)
    owners_by_kind.update((f"claim:{ulid}", "SUPERSEDES")
                          for ulid, _item, _tier in claim_items)
    for owner_ref, kind in sorted(owners_by_kind):
        desired = sorted(edge_sets.get((owner_ref, kind), {}).values(),
                         key=lambda edge: (edge.dst_ref, edge.props["src_seq"]))
        operations.append((owner_ref, lambda owner_ref=owner_ref, kind=kind, desired=desired:
                           store.replace_edges(owner_ref, kind, desired)))

    # Map → Graphiti thread. On replay, navigation follows ``merged_into`` to the canonical
    # UUID. Replacing this map-owned edge removes the stale endpoint; the Graphiti Entity and
    # its semantic relations remain owned by Graphiti/grill writeback (F16).
    for item in sorted(wayfinds["maps"].values(), key=lambda value: value["ulid"]):
        map_ref = graph_refs[item["ulid"]]
        thread = item.get("thread") if isinstance(item.get("thread"), dict) else {}
        declared_uuid = thread.get("uuid")
        opened_seq = _seq_for({"map.opened"}, item["ulid"])

        def _project_thread(map_ref=map_ref, declared_uuid=declared_uuid,
                            opened_seq=opened_seq, tier=item.get("tier")):
            if not isinstance(declared_uuid, str):
                return store.replace_edges(map_ref, "PART_OF", [])
            existing = store.neighbors(map_ref, "PART_OF", direction="out")
            target = existing[0].ref if existing and existing[0].ref != declared_uuid else declared_uuid
            store.replace_edges(map_ref, "PART_OF", [EdgeSpec(
                target,
                {"src_seq": opened_seq, "provenance_class": _plane(tier),
                 "graphiti_uuid": declared_uuid},
            )])

        operations.append((map_ref, _project_thread))

    for index, (_ref, operation) in enumerate(operations):
        try:
            operation()
        except GraphUnavailable:
            return ProjectionResult.incomplete(ref for ref, _operation in operations[index:])
    return ProjectionResult.success()


def _mark_integrated_source(slug, reviewer, ts=None):
    """A projeção da integração no :Artefato — flat props (integrated_source/by/at), MERGE
    idempotente (um nó ainda não projetado ganha o stub; o próximo project preenche o resto).
    `ts` = o timestamp do EVENTO `artefato.integrated` (determinístico no replay; um ts ausente
    de evento legado degrada a now()). Best-effort/degrade-safe: qualquer falha PRINTA e retorna,
    nunca sobe (o log já é a verdade; o replay em `reproject_graph` restaura)."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception as ex:  # noqa: BLE001 — best-effort; o log já registrou o ato
        print("integrate projection skipped (best-effort, graph unreachable):", ex)
        return
    try:
        with drv.session() as s:
            s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) "
                  "SET a.integrated_source=true, a.integrated_by=$r, a.integrated_at=$ts",
                  g=g, slug=slug, r=reviewer,
                  ts=ts or _dt.now(_tz.utc).isoformat())
    except Exception as ex:  # noqa: BLE001 — a projeção falha reportada, nunca fatal
        print("integrate projection failed (best-effort, reproject next beat):", ex)
    finally:
        try:
            drv.close()
        except Exception:
            pass


def reproject_missing_pages(log=eventlog.LOG, blog_dir=BLOG_DIR, date=None, embed_fn=None):
    """Recovery/reprojection (Codex round-10 [high], ADR-0006: pages are PROJECTIONS of the log).
    For every committed `artefato.published` that carries a spec, re-render any MISSING
    blog/entries/<slug>.html from the logged spec (byte-identical to a normal publish) and
    re-emit any MISSING source signals from the logged cites. Idempotent: a present page is left
    untouched and an already-emitted signal (per ref) is not re-emitted. This is what makes a
    page-write or signal failure AFTER the publish commit recoverable rather than unrecoverable.

    The published event now carries `skill` (#30), so the reprojected page uses the REAL producer
    skill for the meta line (Codex P2) — a map/plan recovered page is byte-identical to the original,
    not mislabelled 'report'. A legacy event with no skill falls back to the producer-neutral default;
    the body (the load-bearing content) re-renders exactly either way."""
    blog_dir = Path(blog_dir)
    yields = cortex.source_yield_at(log=log)  # refs that already have a signal
    redone = []
    for item in cortex.corpus_at(log=log):
        spec = item.get("spec")
        if spec is None:
            continue  # legacy/migration published events with no spec are not regenerable
        slug = item["slug"]
        try:
            out = _safe_target(slug, blog_dir)
        except ValueError:
            continue
        body_html, page = _render_page(slug, spec, skill=item.get("skill") or "report", date=date)
        if not out.exists():
            _write_page(out, page)
            redone.append(out)
        # re-emit only cites whose source signal never landed (idempotent recovery)
        missing = [c for c in (item.get("cites") or [])
                   if isinstance(c, dict) and c.get("snippet") and c.get("ref") not in yields]
        _signal_cites(slug, body_html, missing, embed_fn, log)
    return redone


def _graph_present_slugs():
    """The slugs FULLY projected into the install graph, mapped to their `projected_at` — read once so
    recovery replays only the missing/incomplete/STALE ones (Codex P2): never re-embed the whole
    corpus each sweep, BUT re-project a node left INCOMPLETE (no `projection_complete` marker — set
    ONLY as project_artefato's last step) OR STALE (its `projected_at` is older than the log's latest
    published ts for that slug — a republish whose projection never reached the graph). Returns a dict
    `{slug: projected_at}`, or None on a degrade (no group / no driver / unreachable) — the caller then
    skips the replay entirely (there is nothing to recover into a graph it cannot read)."""
    try:
        import _identity
        from neo4j import GraphDatabase
        uri, user, pw = _identity.neo4j_conn()
        g = _identity.require_group()
        drv = GraphDatabase.driver(uri, auth=(user, pw))
    except Exception:  # noqa: BLE001 — degrade: caller skips the replay
        return None
    try:
        with drv.session() as s:
            return {r["slug"]: r["pat"] for r in s.run(
                "MATCH (a:Artefato {group_id:$g}) WHERE a.projection_complete = true "
                "RETURN a.slug AS slug, a.projected_at AS pat", g=g)}
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            drv.close()
        except Exception:
            pass


def reproject_graph(log=eventlog.LOG, project_fn=_DEFAULT_PROJECT, present_slugs=_graph_present_slugs,
                    backbone_fn=project_backbone, asset_project_fn=None,
                    session_topic_project_fn=None):
    """Graph recovery (Codex P2, #30, ADR-0006: the graph is a re-derivable PROJECTION of the log).
    A transient Neo4j outage at publish time leaves the committed Artefato out of the graph (so
    `recall_subgraph` misses it) — this is the "reproject next beat" path the publish-time catch
    promises. Replay `project_artefato` for the MISSING Artefatos only (idempotent MERGEs). The
    published event carries `skill`, so the replay restores the REAL producer identity; the Artefato
    + its SERVES/DISTILLS/PROPOSES/CITES + embedding are re-derived from the log.

    REPLAY ONLY THE MISSING/STALE (Codex P2): steady-state must NOT re-embed the whole corpus each
    sweep. `present_slugs()` reports `{slug: projected_at}` for complete nodes (one cheap read); a slug
    is skipped ONLY if it is complete AND its `projected_at` is at-or-after the log's latest published
    ts for that slug. A republished slug (newer log ts) — or one whose republish projection never
    reached the graph — is STALE and re-projected, so the graph cannot keep a stale kernel/edges
    forever. If `present_slugs()` degrades to None (graph unreachable), the replay is skipped entirely.

    Best-effort: a still-unreachable graph degrades inside project_artefato (prints, never raises).
    Call it from the sweep/assemble at beat-open so a missed projection self-heals next beat.

    DEFAULT-SKIP for a non-canonical log (Codex P2): like `publish`, replaying a temp/dry-run log
    must NOT write into the install graph — those nodes could not be replayed/cleaned from the
    canonical log. Only a canonical-log (`log is eventlog.LOG`) replay projects by default; a caller
    wanting to replay a custom log must pass an explicit project_fn."""
    if project_fn is _DEFAULT_PROJECT:
        project_fn = project_artefato if _is_canonical_log(log) else None
    if project_fn is None:
        return
    # rebuild the spine backbone FIRST, every canonical sweep (Codex P2): the ANCHORS rebuild reads
    # the log's active steers, so newly-folded Directions get anchored even when no artefato is
    # missing — independent of the skip-present optimization below. Cheap (no embeddings), idempotent.
    if backbone_fn is not None:
        backbone_fn(log)
    if _is_canonical_log(log):
        try:
            backfill_entry_assets(log=log, project_fn=None)
        except Exception as ex:  # noqa: BLE001 — page discovery must not block graph recovery
            print(f"entry asset backfill skipped (best-effort): {ex}")
    present = present_slugs() if present_slugs is not None else {}
    if present is None:
        return  # graph unreachable — nothing to recover into it; skip (no per-item embed storm)
    for item in cortex.corpus_at(log=log):
        pat = present.get(item["slug"])
        # skip ONLY if complete AND FRESH: the node's projected_at is at-or-after the log's LATEST
        # event ts for this slug. `latest_ts` advances to a kernel ADDED LATER (Codex P3), so a
        # legacy C3-debt repair (kernel appended after publish) makes the slug stale → replay. A
        # republish (newer ts) or a never-projected republish is likewise STALE → replay.
        latest = item.get("latest_ts") or item.get("ts")
        if pat is not None and latest is not None and str(pat) >= str(latest):
            continue  # already projected and current — skip (no re-embed in steady state)
        try:
            # the published event now carries `skill` (Codex P2), so a publish-time-outage replay
            # restores the REAL producer identity even when the node does not exist yet. A legacy
            # event with no skill folds to None, which coalesce preserves (never clobbers).
            project_fn(item["slug"], item.get("intent") or "", skill=item.get("skill"),
                       distills=item.get("distills"), proposes=item.get("proposes"),
                       cites=item.get("cites"), spec=item.get("spec"),
                       lineage=item.get("lineage"), log=log, gate=item.get("gate"),
                       origin=item.get("origin"),
                       bears_on=item.get("bears_on"), para=item.get("para"),
                       para_default=item.get("para_default"),
                       reports_on=item.get("reports_on"))
        except Exception as ex:  # noqa: BLE001 — replay is best-effort, never fatal
            print(f"graph reproject skipped for {item.get('slug')!r} (best-effort):", ex)
    if asset_project_fn is None:
        asset_project_fn = project_artefato_asset if _is_canonical_log(log) else None
    if asset_project_fn is not None:
        for asset in cortex.artefato_assets_at(log=log).values():
            pat = present.get(asset["asset_slug"])
            latest = asset.get("ts")
            if pat is not None and latest is not None and str(pat) >= str(latest):
                continue
            try:
                asset_project_fn(
                    asset["asset_slug"],
                    path=asset.get("path"),
                    kind=asset.get("kind"),
                    sha256=asset.get("sha256"),
                    skill=asset.get("skill"),
                    parent_slug=asset.get("parent_slug"),
                    media_type=asset.get("media_type"),
                    role=asset.get("role"),
                    log=log,
                )
            except Exception as ex:  # noqa: BLE001 — replay is best-effort, never fatal
                print(f"asset graph reproject skipped for {asset.get('asset_slug')!r}: {ex}")
    if _is_canonical_log(log):
        project_native_experiments(log=log)
    if session_topic_project_fn is None:
        session_topic_project_fn = project_session_topics if _is_canonical_log(log) else None
    if session_topic_project_fn is not None:
        try:
            session_topic_project_fn(log=log)
        except Exception as ex:  # noqa: BLE001 — replay is best-effort, never fatal
            print(f"session-topic graph reproject skipped (best-effort): {ex}")
    # B.3 (Codex adversarial) — replay das INTEGRAÇÕES também: uma promoção cuja marca best-effort
    # no grafo falhou se cura aqui (MERGE idempotente, ts do evento). Canônico-somente, como o
    # project acima: um log de teste/dry-run nunca escreve marcas no grafo do install.
    if _is_canonical_log(log):
        for slug, info in eventlog.integrated_sources_at(log=log).items():
            _mark_integrated_source(slug, info.get("reviewer"), ts=info.get("ts"))
