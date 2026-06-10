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
distills + skill — EVERY persisted publish arg, so distills/skill cannot be altered post-mint to
poison provenance), both blind reviewers passed, AND the verdicts carry both CANONICAL reviewer
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
import os
import re
from datetime import date as _date
from datetime import datetime as _dt
from datetime import timezone as _tz
from pathlib import Path

import eventlog
import render
from close import check_genus, verify_proof

REPO = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO / "blog" / "entries"
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
PRODUCER_ROSTER = ("report", "research", "map", "plan", "discovery", "grill")


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


def _render_page(slug, spec, *, skill, date):
    """Render the self-contained neutral HTML page for `slug` from its spec — the SINGLE
    place the page bytes are produced, so a normal publish and a reprojection (recovery from
    the logged spec) emit byte-identical pages. Returns (body_html, page_text)."""
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


def _project_backbone(s, g, log):
    """Project the canonical SPINE BACKBONE on an open session `s`: :Genesis (space-0) -GROUNDS->
    :Objective + the ANCHORS rebuild (the active steers, DESTRUCTIVE DELETE-then-readd from the
    canonical fold). Shared by project_artefato (per publish) and reproject_graph (per sweep) so the
    ANCHORS stay current with the log every canonical sync, regardless of which artefatos exist."""
    import yaml
    try:
        cfg = yaml.safe_load((REPO / "agent.yaml").read_text()) or {}
    except Exception:  # noqa: BLE001 — agent.yaml read is best-effort
        cfg = {}
    s.run("MERGE (gen:Genesis {group_id:$g}) SET gen.space=0, gen.codename=$c, gen.voice=$v, "
          "gen.method='memory/method.md', gen.personality='memory/personality.md'",
          g=g, c=cfg.get("codename") or cfg.get("name"), v=cfg.get("voice"))
    obj = eventlog.objective_at(log=log) or {}
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
    dirs = eventlog.direction_at(log=log) or {}
    s.run("MATCH (o:Objective {group_id:$g})-[r:ANCHORS]->(:Direction) DELETE r", g=g)
    for it in dirs.get("set", []) + dirs.get("proposed", []):
        s.run("MERGE (d:Direction {group_id:$g, body:$b})", g=g, b=it["body"])
        s.run("MATCH (o:Objective {group_id:$g}),(d:Direction {group_id:$g, body:$b}) "
              "MERGE (o)-[:ANCHORS]->(d)", g=g, b=it["body"])


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


def project_artefato(slug, intent, *, skill, distills=None, proposes=None, cites=None,
                     spec=None, log=eventlog.LOG):
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
            s.run("MERGE (a:Artefato {group_id:$g, slug:$slug}) "
                  "SET a.kernel=$k, a.skill=coalesce($skill, a.skill), a.page=$page, "
                  "a.projected_at=$pat, a.projection_complete=false",
                  g=g, slug=slug, k=intent, skill=skill, page=f"blog/entries/{slug}.html",
                  pat=_dt.now(_tz.utc).isoformat())
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
            s.run("MATCH (a:Artefato {group_id:$g, slug:$slug})-[r:DISTILLS|PROPOSES|CITES]->() "
                  "DELETE r", g=g, slug=slug)
            # resolve distills against ACTIVE clusters only (Codex P2): mirror graph_clusters —
            # archived/merged entities are hidden, so a retired cluster is never linked or pushed.
            labels = [r["l"] for r in s.run(
                "MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
                "RETURN DISTINCT e.curated_cluster AS l", g=g)]
            by_slug = {_cluster_slug(l): l for l in labels}
            unresolved_distills = False
            for ref in distills:                  # link ONLY existing active clusters (never fabricate)
                label = by_slug.get(_cluster_slug(str(ref).replace("cluster:", "")))
                if not label:
                    # cluster not in the graph yet — the grill attaches it later. Mark the projection
                    # INCOMPLETE so recovery REVISITS this slug once the cluster exists (the embed is
                    # already set, so the revisit is a cheap edge-only re-link, not a re-embed).
                    unresolved_distills = True
                    continue
                s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}),"
                      "(e:Entity {group_id:$g, curated_cluster:$label}) "
                      "MERGE (a)-[:DISTILLS]->(e)", g=g, slug=slug, label=label)
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
            # (3) COMPLETION MARKER — set LAST, complete ONLY when (a) every edge write succeeded,
            # (b) the embedding is current (a FAILED embed leaves it false → retried on recovery,
            # Codex P2), AND (c) every distill ref RESOLVED. `_graph_present_slugs` reads THIS: a node
            # left half-projected (embed/edge outage) OR with an unresolved distill (cluster not in
            # the graph yet) is NOT present and is re-projected — so a transient embed outage and the
            # "grill attaches the cluster later" path both self-heal on the next sweep.
            s.run("MATCH (a:Artefato {group_id:$g, slug:$slug}) SET a.projection_complete=$done",
                  g=g, slug=slug, done=(embed_current and not unresolved_distills))
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
            cites=None, date=None, log=eventlog.LOG, blog_dir=BLOG_DIR, embed_fn=None,
            project_fn=_DEFAULT_PROJECT) -> Path:
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

    Order (#2/#3, ADR-0006): render the page in memory → append the atomic event WITH the spec
    (the COMMIT POINT; the log is truth) → THEN write the HTML (a projection) → THEN emit source
    signals. Everything after the commit is a recoverable projection: a page-write or signal
    failure is no longer unrecoverable — the logged spec re-renders the exact page and the logged
    cites re-emit the signals via `reproject_missing_pages`. Signal emission is non-fatal to the
    page (#4). Returns the written page Path. `date` is a param (defaults to today) so tests pin
    it; `embed_fn` is injectable so the source-signal step runs offline.
    """
    # ADR-0016 FIRST — no wake, no publish: the refusal names the real gap (`no-wake`), not a
    # proof error. The stamp is checked on the SAME log this publish would commit to.
    if not eventlog.wake_fresh(log=log):
        raise RuntimeError(
            f"no-wake: cannot publish {slug!r} — no dispatch.open newer than the last "
            "artefato.published on this log (ADR-0016: run tools/predispatch.py at dispatch "
            "entry; one wake per publish)")
    verify_proof(verdict, slug=slug, spec=spec, intent=intent,
                 cites=cites or [], proposes=proposes or [],
                 distills=distills, skill=skill)
    if not (intent and intent.strip()):
        raise ValueError(f"cannot publish artefato {slug!r} without an intent kernel (C3)")
    if skill not in PRODUCER_ROSTER:
        raise ValueError(
            f"skill {skill!r} is not in the producer roster {PRODUCER_ROSTER} — "
            "an out-of-roster skill is refused before anything is written (Codex round-4)")

    out = _safe_target(slug, blog_dir)

    cites = cites or []
    # The publisher-side genus check must see EVERY field check_genus reads, or it disagrees with
    # run_close's check (Codex P2): the rich-rite floor reads `distills` (lineage) and content, so
    # a report whose lineage rides on its published `distills` would pass run_close but raise here.
    artefato = {"intent": intent, "proposes": proposes or [], "cites": cites,
                "content": spec, "distills": distills or [], "skill": skill}
    violations = check_genus(artefato)
    if violations:
        raise ValueError(f"artefato {slug!r} violates the genus contract: {violations}")

    body_html, page = _render_page(slug, spec, skill=skill, date=date)

    # COMMIT POINT (#2, ADR-0006: the log is truth). The atomic event carries the proof-bound
    # spec, so the page is fully regenerable from the log alone. EVERYTHING after this is a
    # recoverable projection (reproject_missing_pages re-derives it from the logged spec/cites).
    eventlog.publish_artefato_atomic(slug, intent, proposes=proposes, distills=distills,
                                     cites=cites, spec=spec, skill=skill, log=log)

    # the page is a PROJECTION written after the commit — a failure here is recoverable.
    _write_page(out, page)

    # source-signal emission is NON-FATAL to the page (#4): a signal-store failure must not
    # corrupt the published page; the cites are durably logged, so the signals are recoverable
    # (reproject_missing_pages re-emits any missing ones).
    try:
        _signal_cites(slug, body_html, cites, embed_fn, log)
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
                       cites=cites, spec=spec, log=log)
        except Exception as ex:  # noqa: BLE001 — projection is best-effort, never fatal
            print(f"project skipped for {slug!r} (best-effort, reproject next beat):", ex)
    return out


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
    yields = eventlog.source_yield_at(log=log)  # refs that already have a signal
    redone = []
    for item in eventlog.corpus_at(log=log):
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
                    backbone_fn=project_backbone):
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
    present = present_slugs() if present_slugs is not None else {}
    if present is None:
        return  # graph unreachable — nothing to recover into it; skip (no per-item embed storm)
    for item in eventlog.corpus_at(log=log):
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
                       cites=item.get("cites"), spec=item.get("spec"), log=log)
        except Exception as ex:  # noqa: BLE001 — replay is best-effort, never fatal
            print(f"graph reproject skipped for {item.get('slug')!r} (best-effort):", ex)
