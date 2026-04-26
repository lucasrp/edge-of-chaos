#!/usr/bin/env python3
"""Dashboard server in the legacy ``blog`` package: Flask + Jinja2 + htmx."""

import html as html_mod
import json
import math
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, jsonify, redirect, render_template, request, send_from_directory, abort
)
from flask_compress import Compress
import markdown
import yaml

# ─── Paths ───
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
from paths import (  # noqa: E402
    AUTONOMY_CAPABILITIES_FILE,
    BLOG_COMMENTS_FILE,
    BLOG_DIFFS_DIR,
    BLOG_DIR,
    BLOG_FTS_DB_FILE,
    BUILDS_DIR,
    EDGE_REPO_DIR,
    ENTRIES_DIR,
    FRONTIER_FILE,
    META_REPORTS_DIR,
    NOTES_DIR,
    PROPOSALS_FILE,
    REPORTS_DIR,
    SEARCH_DIR,
    SIGNALS_DIR,
    STATE_DIR,
    THREADS_DIR,
)

ROOT = EDGE_REPO_DIR
COMMENTS_FILE = BLOG_COMMENTS_FILE
DIFFS_DIR = BLOG_DIFFS_DIR
DIFFS_DIR.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SEARCH_DIR))
sys.path.insert(0, str(ROOT))

import yaml as _yaml

from blog.api_dashboard import dashboard_bp, _build_status_strip_data, _build_alerts_data, _build_pipeline_data, _build_hotspots_data, _build_corpus_data, _build_briefing_data, _build_epistemic_data, _build_interventions_data, _build_runtime_data

# ─── Branding ───
_branding_path = ROOT / "config" / "branding.yaml"
BRANDING = {}
if _branding_path.exists():
    try:
        BRANDING = _yaml.safe_load(_branding_path.read_text()) or {}
    except Exception:
        pass
AGENT_NAME = BRANDING.get("agent_name", "agent")
AGENT_BIO = BRANDING.get("agent_bio", "")
from blog.api_actions import actions_bp
from blog.api_setup import setup_bp

# ─── Flask app ───
app = Flask(
    __name__,
    template_folder=str(BLOG_DIR / "templates"),
    static_folder=str(BLOG_DIR / "static"),
    static_url_path="/static",
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
Compress(app)
app.register_blueprint(dashboard_bp)
app.register_blueprint(actions_bp)
app.register_blueprint(setup_bp)

PAGE_SIZE = 20

# ─── Auth + Read-only mode ───
_blog_cfg = BRANDING.get("blog", {})
_auth_enabled = str(_blog_cfg.get("auth_enabled", False)).lower() in ("true", "1", "yes")
_auth_user = _blog_cfg.get("auth_user", "")
_auth_pass = _blog_cfg.get("auth_pass", "")
@app.before_request
def enforce_auth():
    if _auth_enabled and _auth_user:
        # Loopback bypass: local callers (agent, skills, same-machine browser)
        # are trusted by the kernel — packets claiming source 127.0.0.1/::1
        # cannot originate off-host. Keeps internal tooling free of credentials
        # while preserving Basic Auth for remote browsers.
        if request.remote_addr in ("127.0.0.1", "::1"):
            return None
        if request.path.startswith("/static"):
            return None
        auth = request.authorization
        if not auth or auth.username != _auth_user or auth.password != _auth_pass:
            return ("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Dashboard"'})

# ─── Tag normalization ───
TAG_MAP = {
    "leisure": "lazer", "reflection": "reflexao", "research": "pesquisa",
    "discovery": "descoberta", "strategy": "estrategia", "planning": "planejamento",
    "execution": "execucao", "calibration": "calibracao",
}

UNPUBLISHED_STATUSES = {"draft", "pending", "pendente", "unpublished", "private", "hidden"}
UNPUBLISHED_TAGS = {"draft", "workflow-draft", "unpublished"}


def _normalized_token(value):
    return str(value or "").strip().lower()


def is_entry_published(fm, tags):
    status = _normalized_token(fm.get("status"))
    if status in UNPUBLISHED_STATUSES:
        return False
    normalized_tags = {_normalized_token(tag) for tag in tags or []}
    return not bool(normalized_tags & UNPUBLISHED_TAGS)

SKILL_GROUPS = [
    {"name": "producao", "label": "producao", "tags": ["pesquisa", "descoberta", "lazer"]},
    {"name": "planejamento", "label": "planejamento", "tags": ["planejamento", "estrategia"]},
    {"name": "meta", "label": "meta", "tags": ["reflexao", "execucao"]},
]


# ─── FTS5 index ───
FTS_DB_PATH = BLOG_FTS_DB_FILE


def get_fts_conn():
    conn = sqlite3.connect(str(FTS_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
            slug, title, body, tags,
            tokenize='porter unicode61 remove_diacritics 2'
        )
    """)
    return conn


def rebuild_fts_index(entries):
    """Rebuild FTS5 index from scratch."""
    conn = get_fts_conn()
    conn.execute("DELETE FROM entries_fts")
    for e in entries:
        # Strip HTML for indexing
        body_text = e.get("body_md", "")
        conn.execute(
            "INSERT INTO entries_fts(slug, title, body, tags) VALUES(?, ?, ?, ?)",
            (e["slug"], e["title"], body_text, e["tag"]),
        )
    conn.commit()
    conn.close()


def fts_search(query, limit=20):
    """Search entries using FTS5 BM25 ranking."""
    conn = get_fts_conn()
    safe = query.replace('"', '""')
    terms = safe.split()
    fts_q = " OR ".join(f'"{t}"' for t in terms if t)
    if not fts_q:
        conn.close()
        return []
    try:
        rows = conn.execute(
            """SELECT slug, title,
                      snippet(entries_fts, 2, '>>>', '<<<', '...', 40) AS snippet,
                      rank AS score
               FROM entries_fts WHERE entries_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (fts_q, limit),
        ).fetchall()
        results = [dict(r) for r in rows]
    except Exception:
        results = []
    conn.close()
    return results


# ─── Data loading ───
def load_comments():
    if not COMMENTS_FILE.exists():
        return {"version": 1, "entries": {}}
    with open(COMMENTS_FILE, "r") as f:
        return json.load(f)


def save_comments(data):
    tmp = str(COMMENTS_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(COMMENTS_FILE))


def _parse_frontmatter(content: str) -> dict:
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        return yaml.safe_load(parts[1]) or {}
    except Exception:
        return {}


def load_entries():
    entries = []
    if not ENTRIES_DIR.exists():
        return entries
    for fp in sorted(ENTRIES_DIR.glob("*.md"), reverse=True):
        raw = fp.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1])
        except Exception:
            continue
        body_md = parts[2].strip()

        tag = fm.get("tag", "")
        if not tag:
            tags = fm.get("tags", [])
            if isinstance(tags, list) and tags:
                tag = tags[0]
            elif isinstance(tags, str) and tags:
                tag = tags.split(",")[0].strip()
            else:
                tag = "lazer"
        tag = TAG_MAP.get(tag, tag)

        altered = fm.get("altered", [])
        if isinstance(altered, str):
            altered = [altered]

        diffs_file = DIFFS_DIR / f"{fp.stem}.json"
        entry_diffs = []
        if diffs_file.exists():
            try:
                # Skip diffs > 1MB to avoid bloating HTML
                if diffs_file.stat().st_size < 1_000_000:
                    diffs_data = json.loads(diffs_file.read_text(encoding="utf-8"))
                    entry_diffs = diffs_data.get("files", [])
            except Exception:
                pass

        # Tags: always as list
        tags_list = fm.get("tags", [])
        if isinstance(tags_list, str):
            tags_list = [t.strip() for t in tags_list.split(",")]

        # Claims
        claims_list = fm.get("claims", [])
        if not isinstance(claims_list, list):
            claims_list = []

        # Threads
        threads_list = fm.get("threads", [])
        if not isinstance(threads_list, list):
            threads_list = []

        # Keywords
        keywords_list = fm.get("keywords", [])
        if not isinstance(keywords_list, list):
            keywords_list = []

        # Meta-report detection
        meta_report = ""
        meta_path = META_REPORTS_DIR / f"{fp.stem}-meta.md"
        if meta_path.exists():
            meta_report = meta_path.name

        # State audit detection
        state_proposal = ""
        state_audit = ""
        proposal_path = META_REPORTS_DIR / f"{fp.stem}.state-proposal.yaml"
        audit_path = META_REPORTS_DIR / f"{fp.stem}.state-audit.yaml"
        if proposal_path.exists():
            state_proposal = proposal_path.name
        if audit_path.exists():
            state_audit = audit_path.name

        pipeline_complete = bool(meta_report)
        published = is_entry_published(fm, tags_list)

        entries.append({
            "title": fm.get("title", fp.stem),
            "tag": tag,
            "tags": tags_list,
            "date": str(fm.get("date", "")),
            "context": fm.get("context", ""),
            "report": os.path.basename(fm.get("report", "")) if fm.get("report") else "",
            "meta_report": meta_report,
            "pipeline_complete": pipeline_complete,
            "pipeline_status": "complete" if pipeline_complete else "missing_meta_report",
            "published": published,
            "state_proposal": state_proposal,
            "state_audit": state_audit,
            "llm_cost": fm.get("llm_cost", ""),
            "claims": claims_list,
            "threads": threads_list,
            "keywords": keywords_list,
            "altered": altered,
            "diffs": entry_diffs,
            "slug": fp.stem,
            "filename": fp.name,
            "body_md": body_md,
            "body_html": "",
            "mtime": fp.stat().st_mtime,
            "path": str(fp),
        })

    entries.sort(key=lambda e: (e["date"], e["mtime"]), reverse=True)

    chronological = sorted(entries, key=lambda e: (e["date"], e["mtime"]))
    cat_counters = {}
    for i, entry in enumerate(chronological, 1):
        entry["break_number"] = i
        t = entry["tag"]
        cat_counters[t] = cat_counters.get(t, 0) + 1
        entry["category_number"] = cat_counters[t]

    return entries


# ─── Cache ───
_entries_cache = {"data": None, "ts": 0}
CACHE_TTL = 300  # seconds


def get_entries():
    now = time.time()
    if _entries_cache["data"] is None or (now - _entries_cache["ts"]) > CACHE_TTL:
        entries = load_entries()
        enrich_entries(entries)
        _entries_cache["data"] = entries
        _entries_cache["ts"] = now
        rebuild_fts_index(entries)
    return _entries_cache["data"]


def render_page_html(entries):
    """Render markdown->HTML only for entries that need it (lazy)."""
    for e in entries:
        if not e["body_html"] and e.get("body_md"):
            e["body_html"] = markdown.markdown(e["body_md"], extensions=["extra"])


def invalidate_cache():
    _entries_cache["data"] = None
    _entries_cache["ts"] = 0


# ─── Helpers ───
def format_date(date_str):
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str or ""):
        parts = date_str.split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return date_str or ""


def short_date(date_str):
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str or ""):
        parts = date_str.split("-")
        return f"{parts[2]}/{parts[1]}"
    return date_str or ""


def get_temp_map():
    """Get temperature signals for all entries."""
    try:
        from dashboard_db import get_signals
        return {s["doc_path"]: s["value"] for s in get_signals(signal="temperature")}
    except Exception:
        return {}


def get_entry_meta():
    """Get metadata from DuckDB for entries (status, effort, project, proposta_id, content_html)."""
    try:
        from db import ensure_db
        conn = ensure_db()
        rows = conn.execute(
            "SELECT path, title, metadata, content FROM documents WHERE type='blog'"
        ).fetchall()
        conn.close()
        meta = {}
        for r in rows:
            fm = json.loads(r["metadata"]) if r["metadata"] else _parse_frontmatter(r["content"] or "")
            body_md = r["content"] or ""
            try:
                content_html = markdown.markdown(body_md, extensions=["extra"])
            except Exception:
                content_html = ""
            meta[r["path"]] = {
                "status": fm.get("status"),
                "effort": fm.get("effort"),
                "project": fm.get("project"),
                "proposta_id": fm.get("proposta_id"),
                "content_html": content_html,
            }
        return meta
    except Exception:
        return {}


def enrich_entries(entries):
    """Merge temperature and metadata into entries."""
    temp_map = get_temp_map()
    meta_map = get_entry_meta()
    for e in entries:
        e["temperature"] = temp_map.get(e["path"])
        m = meta_map.get(e["path"], {})
        e["status"] = m.get("status")
        e["effort"] = m.get("effort")
        e["project"] = m.get("project")
        e["proposta_id"] = m.get("proposta_id")
        if m.get("content_html"):
            e["content_html"] = m["content_html"]
    return entries


def filter_entries(entries, comments_data, cat=None, temp=None, status=None,
                   report=False, q=None, show_pending=False):
    """Filter entries based on criteria."""
    filtered = []
    # If search query, try FTS first
    fts_slugs = None
    if q:
        fts_results = fts_search(q, limit=100)
        if fts_results:
            fts_slugs = {r["slug"] for r in fts_results}

    for e in entries:
        # Hide explicit drafts/unpublished entries unless explicitly requested.
        # Missing meta-report is tracked separately as pipeline_status.
        if not show_pending and not e.get("published"):
            continue

        # Category filter (OR logic on list)
        if cat:
            cats = [c for c in cat if c]
            if cats and e["tag"] not in cats:
                continue

        # Temperature filter
        if temp and e.get("temperature") != temp:
            continue

        # Status filter (saved/commented)
        if status in ("saved", "commented"):
            key = (e["title"] or "")[:80]
            ed = comments_data.get("entries", {}).get(key, {})
            if status == "saved" and not ed.get("saved"):
                continue
            if status == "commented" and not ed.get("comments"):
                continue

        # Report filter
        if report and not e.get("report"):
            continue

        # Search filter
        if q:
            if fts_slugs is not None:
                if e["slug"] not in fts_slugs:
                    continue
            else:
                # Fallback to title+tag match
                ql = q.lower()
                if ql not in (e["title"] or "").lower() and ql not in (e["tag"] or "").lower():
                    continue

        filtered.append(e)
    return filtered


# ─── Template context ───
@app.context_processor
def inject_globals():
    return {
        "format_date": format_date,
        "short_date": short_date,
        "skill_groups": SKILL_GROUPS,
        "agent_name": AGENT_NAME,
        "agent_bio": AGENT_BIO,
    }


# ─── Routes: Main pages ───
@app.route("/")
def root_redirect():
    return redirect("/dashboard")


@app.route("/blog/")
@app.route("/blog")
def blog_index():
    """Legacy compatibility surface for feed/chat/workflow views."""
    tab = request.args.get("tab", "feed")
    if tab not in ("feed", "chat", "workflows"):
        tab = "feed"

    entries = get_entries()
    comments_data = load_comments()

    # Parse filter params
    cat = request.args.getlist("cat")
    temp = request.args.get("temp")
    status_f = request.args.get("status")
    report_f = request.args.get("report") == "1"
    q = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", "1")))
    view = request.args.get("view", "expanded")
    show_pending = request.args.get("pending") == "1"

    # Count pending (unpublished) entries
    pending_count = sum(1 for e in entries if not e.get("published"))

    # Get stats
    stats = get_stats_data()

    if tab == "feed":
        filtered = filter_entries(entries, comments_data, cat=cat, temp=temp,
                                  status=status_f, report=report_f, q=q,
                                  show_pending=show_pending)
        total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
        if page > total_pages:
            page = total_pages
        start = (page - 1) * PAGE_SIZE
        page_entries = filtered[start:start + PAGE_SIZE]
        render_page_html(page_entries)

        # Count saved/commented for display
        saved_count = 0
        commented_count = 0
        for e in entries:
            key = (e["title"] or "")[:80]
            ed = comments_data.get("entries", {}).get(key, {})
            if ed.get("saved"):
                saved_count += 1
            if ed.get("comments"):
                commented_count += 1

        return render_template("feed.html",
                               tab=tab,
                               entries=page_entries,
                               all_entries=entries,
                               comments_data=comments_data,
                               stats=stats,
                               page=page,
                               total_pages=total_pages,
                               total_filtered=len(filtered),
                               total_entries=len(entries),
                               saved_count=saved_count,
                               commented_count=commented_count,
                               pending_count=pending_count,
                               show_pending=show_pending,
                               cat=cat,
                               temp=temp,
                               status_f=status_f,
                               report_f=report_f,
                               q=q,
                               view=view,
                               is_htmx=request.headers.get("HX-Request") == "true")

    elif tab == "workflows":
        all_wf = [e for e in entries if any(t in e.get("tags", []) for t in ("workflow", "anti-pattern", "workflow-draft"))]
        pending = [e for e in all_wf if "workflow-draft" in e.get("tags", [])]
        approved = [e for e in all_wf if "workflow-draft" not in e.get("tags", [])]
        sort_by = request.args.get("sort", "date")
        if sort_by == "views":
            approved.sort(key=lambda e: e.get("view_count", 0), reverse=True)
        # Load proposals
        proposals = _load_proposals()
        return render_template("workflows.html", tab=tab, pending=pending,
                               entries=approved, proposals=proposals,
                               sort_by=sort_by, stats=stats,
                               is_htmx=request.headers.get("HX-Request") == "true")

    elif tab == "chat":
        return render_template("chat.html", tab=tab, stats=stats,
                               is_htmx=request.headers.get("HX-Request") == "true")


@app.route("/htmx/workflow/<slug>")
def htmx_workflow_detail(slug):
    entries = get_entries()
    entry = next((e for e in entries if e.get("slug") == slug), None)
    if not entry:
        return "<p>Workflow not found.</p>", 404
    render_page_html([entry])
    return render_template("partials/workflow_detail.html", entry=entry)


@app.route("/workflows/<slug>/approve", methods=["POST"])
def workflow_approve(slug):
    """Approve a workflow draft: change tag from workflow-draft to workflow.

    Accepts optional JSON body with edited content:
      {"body_md": "new markdown content"}
    """
    entries_dir = ENTRIES_DIR
    path = next(entries_dir.glob(f"*{slug}*"), None)
    if not path:
        return jsonify({"error": "not found"}), 404
    text = path.read_text()
    parts = text.split("---", 2)
    if len(parts) >= 3:
        parts[1] = parts[1].replace("workflow-draft", "workflow")
        # Apply edited body if provided
        try:
            data = request.get_json(silent=True) or {}
            new_body = data.get("body_md")
            if new_body is not None:
                parts[2] = "\n\n" + new_body.strip() + "\n"
        except Exception:
            pass
        path.write_text("---".join(parts))
    invalidate_cache()
    return "", 204


@app.route("/workflows/<slug>/reject", methods=["POST"])
def workflow_reject(slug):
    """Reject a workflow draft: change tag to workflow-rejected."""
    entries_dir = ENTRIES_DIR
    path = next(entries_dir.glob(f"*{slug}*"), None)
    if not path:
        return jsonify({"error": "not found"}), 404
    text = path.read_text()
    parts = text.split("---", 2)
    if len(parts) >= 3:
        parts[1] = parts[1].replace("workflow-draft", "workflow-rejected")
        path.write_text("---".join(parts))
    invalidate_cache()
    return "", 204


@app.route("/proposals/<proposal_id>/approve", methods=["POST"])
def proposal_approve(proposal_id):
    """Approve a proposal: set status to approved."""
    import json as _j
    try:
        proposals = _j.loads(PROPOSALS_FILE.read_text())
    except Exception:
        return jsonify({"error": "no proposals file"}), 404
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = "approved"
            break
    else:
        return jsonify({"error": "not found"}), 404
    PROPOSALS_FILE.write_text(_j.dumps(proposals, indent=2, ensure_ascii=False))
    return "", 204


@app.route("/proposals/<proposal_id>/reject", methods=["POST"])
def proposal_reject(proposal_id):
    """Reject a proposal: set status to rejected, log in decision.md."""
    import json as _j
    try:
        proposals = _j.loads(PROPOSALS_FILE.read_text())
    except Exception:
        return jsonify({"error": "no proposals file"}), 404
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = "rejected"
            # Log rejection in decision signals
            signals_path = SIGNALS_DIR / "decision.md"
            try:
                signals_path.parent.mkdir(parents=True, exist_ok=True)
                existing = signals_path.read_text() if signals_path.exists() else ""
                signals_path.write_text(existing + f"\n- Rejected proposal: {p.get('title', proposal_id)}\n")
            except Exception:
                pass
            break
    else:
        return jsonify({"error": "not found"}), 404
    PROPOSALS_FILE.write_text(_j.dumps(proposals, indent=2, ensure_ascii=False))
    return "", 204


# ─── Routes: htmx partials ───
@app.route("/htmx/entries")
def htmx_entries():
    """Return filtered entry list as HTML partial (htmx target)."""
    entries = get_entries()
    comments_data = load_comments()

    cat = request.args.getlist("cat")
    temp = request.args.get("temp")
    status_f = request.args.get("status")
    report_f = request.args.get("report") == "1"
    q = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", "1")))
    view = request.args.get("view", "expanded")
    show_pending = request.args.get("pending") == "1"

    pending_count = sum(1 for e in entries if not e.get("published"))

    filtered = filter_entries(entries, comments_data, cat=cat, temp=temp,
                              status=status_f, report=report_f, q=q,
                              show_pending=show_pending)
    total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
    if page > total_pages:
        page = total_pages
    start = (page - 1) * PAGE_SIZE
    page_entries = filtered[start:start + PAGE_SIZE]
    render_page_html(page_entries)

    saved_count = sum(1 for e in entries
                      if comments_data.get("entries", {}).get((e["title"] or "")[:80], {}).get("saved"))
    commented_count = sum(1 for e in entries
                          if comments_data.get("entries", {}).get((e["title"] or "")[:80], {}).get("comments"))

    return render_template("partials/entry_list.html",
                           entries=page_entries,
                           comments_data=comments_data,
                           page=page,
                           total_pages=total_pages,
                           total_filtered=len(filtered),
                           total_entries=len(entries),
                           saved_count=saved_count,
                           commented_count=commented_count,
                           pending_count=pending_count,
                           show_pending=show_pending,
                           cat=cat,
                           temp=temp,
                           status_f=status_f,
                           report_f=report_f,
                           q=q,
                           view=view)


@app.route("/htmx/chat-messages")
def htmx_chat_messages():
    """Return chat messages as HTML partial."""
    try:
        from dashboard_db import get_chats
        limit = int(request.args.get("limit", "100"))
        messages = get_chats(limit=limit)
        return render_template("partials/chat_messages.html", messages=messages)
    except Exception as e:
        return f'<div class="empty-state">erro: {e}</div>'


@app.route("/htmx/entry/<slug>/comments")
def htmx_entry_comments(slug):
    """Return comments for a specific entry."""
    entries = get_entries()
    entry = next((e for e in entries if e["slug"] == slug), None)
    if not entry:
        abort(404)
    key = (entry["title"] or "")[:80]
    comments_data = load_comments()
    ed = comments_data.get("entries", {}).get(key, {})
    return render_template("partials/comments.html",
                           entry=entry,
                           entry_key=key,
                           saved=ed.get("saved", False),
                           comments=ed.get("comments", []))


# ─── Routes: JSON APIs (backward compatible) ───
@app.route("/blog/reindex", methods=["POST"])
def reindex():
    """Invalidate the entries cache so the next request re-reads from disk.
    Called by blog-publish.sh after writing a new entry (issue #236)."""
    invalidate_cache()
    return {"ok": True}, 200


@app.route("/blog/entries/")
@app.route("/blog/entries")
def entries_json():
    entries = get_entries()
    result = [
        {
            "title": e["title"],
            "tag": e["tag"],
            "tags": e.get("tags", []),
            "date": e["date"],
            "slug": e["slug"],
            "break_number": e["break_number"],
            "category_number": e["category_number"],
            "report": e.get("report", ""),
            "meta_report": e.get("meta_report", ""),
            "pipeline_complete": e.get("pipeline_complete", False),
            "pipeline_status": e.get("pipeline_status", ""),
            "published": e.get("published", False),
            "state_proposal": e.get("state_proposal", ""),
            "state_audit": e.get("state_audit", ""),
            "llm_cost": e.get("llm_cost", ""),
            "context": e.get("context", ""),
            "claims": e.get("claims", []),
            "threads": e.get("threads", []),
            "keywords": e.get("keywords", []),
            "diffs": e.get("diffs", []),
        }
        for e in entries
    ]
    return jsonify(result)


def get_autonomy_data():
    """Read ~/edge/autonomy/capabilities.md and compute Sheridan stats."""
    import re
    try:
        cap_path = AUTONOMY_CAPABILITIES_FILE
        frontier_path = FRONTIER_FILE
        content = cap_path.read_text()
        # Parse table rows: | # | Name | Sheridan | ...
        rows = re.findall(r'^\|\s*\d+\s*\|([^|]+)\|\s*(\d+)\s*\|', content, re.MULTILINE)
        if not rows:
            return None
        caps = [{"name": r[0].strip(), "level": int(r[1])} for r in rows]
        levels = [c["level"] for c in caps]
        avg = sum(levels) / len(levels)
        by_level = {}
        for c in caps:
            by_level.setdefault(c["level"], []).append(c["name"])
        # Top 3 gaps (lowest non-zero + zeros)
        gaps = sorted(caps, key=lambda c: c["level"])[:3]
        # Next steps from frontier.md (skip resolved)
        next_steps = []
        if frontier_path.exists():
            fc = frontier_path.read_text()
            for m in re.finditer(r'### (?!~~)(GAP-\d+): (.+)', fc):
                next_steps.append({"id": m.group(1), "title": m.group(2)})
        return {
            "avg": round(avg, 1),
            "total": len(caps),
            "caps": caps,
            "by_level": by_level,
            "gaps": gaps,
            "next_steps": next_steps[:4],
        }
    except Exception:
        return None


def get_stats_data():
    try:
        from dashboard_db import get_signals
        from db import ensure_db
        conn = ensure_db()
        total = conn.execute("SELECT COUNT(*) FROM documents WHERE type='blog'").fetchone()[0]
        propostas = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE type='blog' AND json_extract(metadata, '$.proposta_id') IS NOT NULL"
        ).fetchone()[0]
        descobertas = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE type='blog' AND path LIKE '%descoberta%'"
        ).fetchone()[0]
        reports = conn.execute("SELECT COUNT(*) FROM documents WHERE type='report'").fetchone()[0]
        quentes = len(get_signals(signal="temperature", value="quente", conn=conn))
        conn.close()
        autonomy = get_autonomy_data()
        return {"entries": total, "propostas": propostas, "descobertas": descobertas,
                "reports": reports, "quentes": quentes, "autonomy": autonomy}
    except Exception:
        entries = get_entries()
        return {"entries": len(entries), "propostas": 0, "descobertas": 0,
                "reports": 0, "quentes": 0, "autonomy": get_autonomy_data()}


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats_data())


@app.route("/api/entries")
def api_entries():
    try:
        from dashboard_db import get_signals
        from db import ensure_db
        params = request.args
        page = int(params.get("page", "1"))
        per_page = int(params.get("per_page", "50"))
        tag = params.get("tag")
        status_filter = params.get("status")
        temp = params.get("temp")
        q = params.get("q")

        conn = ensure_db()
        sql = "SELECT d.path, d.title, d.type, d.metadata, d.content FROM documents d WHERE d.type='blog'"
        count_sql = "SELECT COUNT(*) FROM documents d WHERE d.type='blog'"
        params_list = []

        if q:
            sql += " AND (d.title LIKE ? OR d.content LIKE ?)"
            count_sql += " AND (d.title LIKE ? OR d.content LIKE ?)"
            params_list.extend([f"%{q}%", f"%{q}%"])
        if status_filter:
            sql += " AND json_extract(d.metadata, '$.status') = ?"
            count_sql += " AND json_extract(d.metadata, '$.status') = ?"
            params_list.append(status_filter)
        if tag:
            sql += " AND d.metadata LIKE ?"
            count_sql += " AND d.metadata LIKE ?"
            params_list.append(f"%{tag}%")

        total = conn.execute(count_sql, params_list).fetchone()[0]
        sql += " ORDER BY d.path DESC LIMIT ? OFFSET ?"
        params_list.extend([per_page, (page - 1) * per_page])
        rows = conn.execute(sql, params_list).fetchall()

        temp_map = {}
        for s in get_signals(signal="temperature", conn=conn):
            temp_map[s["doc_path"]] = s["value"]

        items = []
        for r in rows:
            path = r["path"]
            entry_temp = temp_map.get(path)
            if temp and entry_temp != temp:
                continue
            fm = json.loads(r["metadata"]) if r["metadata"] else _parse_frontmatter(r["content"] or "")
            body_md = r["content"] or ""
            try:
                body_html = markdown.markdown(body_md, extensions=["extra"])
            except Exception:
                body_html = "<p>" + body_md.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
            items.append({
                "path": path,
                "title": fm.get("title", r["title"]),
                "type": r["type"],
                "temperature": entry_temp,
                "tags": fm.get("tags", []),
                "date": str(fm.get("date", "")),
                "status": fm.get("status", ""),
                "effort": fm.get("effort", ""),
                "project": fm.get("project", ""),
                "cost": fm.get("cost", ""),
                "proposta_id": fm.get("proposta_id", ""),
                "report": fm.get("report", ""),
                "llm_cost": fm.get("llm_cost", ""),
                "content_html": body_html,
            })

        total_pages = max(1, math.ceil(total / per_page))
        result = {"items": items, "page": page, "per_page": per_page,
                  "total": total, "total_pages": total_pages}
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/signals", methods=["GET"])
def api_signals_get():
    try:
        from dashboard_db import get_signals
        signal = request.args.get("signal")
        value = request.args.get("value")
        results = get_signals(signal=signal, value=value)
        return jsonify({"signals": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/signals", methods=["POST"])
def api_signals_post():
    try:
        from dashboard_db import set_signal
        body = request.get_json()
        doc_path = body.get("path", "")
        signal = body.get("signal", "")
        value = body.get("value")
        if not doc_path or not signal:
            return jsonify({"error": "path and signal are required"}), 400
        set_signal(doc_path, signal, value)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["GET"])
def api_chat_get():
    try:
        from dashboard_db import get_chats
        unprocessed = request.args.get("unprocessed", "0") == "1"
        pinned = request.args.get("pinned", "0") == "1"
        limit = int(request.args.get("limit", "100"))
        messages = get_chats(unprocessed_only=unprocessed, pinned_only=pinned, limit=limit)
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat_post():
    try:
        from dashboard_db import add_chat, mark_chat_processed, pin_chat, unpin_chat
        body = request.get_json()
        action = body.get("action", "add")
        if action == "add":
            author = body.get("author", "user")
            text = body.get("text", "").strip()
            if not text:
                return jsonify({"error": "text is required"}), 400
            chat_id = add_chat(author, text)
            return jsonify({"ok": True, "id": chat_id})
        elif action == "mark_processed":
            chat_id = body.get("id")
            if not chat_id:
                return jsonify({"error": "id is required"}), 400
            mark_chat_processed(chat_id)
            return jsonify({"ok": True})
        elif action == "pin":
            chat_id = body.get("id")
            if not chat_id:
                return jsonify({"error": "id is required"}), 400
            pin_chat(chat_id)
            return jsonify({"ok": True})
        elif action == "unpin":
            chat_id = body.get("id")
            if not chat_id:
                return jsonify({"error": "id is required"}), 400
            unpin_chat(chat_id)
            return jsonify({"ok": True})
        else:
            return jsonify({"error": f"unknown action: {action}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/comments", methods=["POST"])
def api_comments():
    try:
        body = request.get_json()
        entry_key = body.get("entryKey", "")
        action = body.get("action", "")

        data = load_comments()
        if entry_key not in data["entries"]:
            data["entries"][entry_key] = {"saved": False, "comments": []}

        entry = data["entries"][entry_key]

        if action == "comment":
            text = body.get("text", "").strip()
            author = body.get("author", "user")
            if text:
                entry["comments"].append({
                    "id": f"c_{int(time.time() * 1000)}",
                    "author": author,
                    "text": text,
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                })
        elif action == "save":
            entry["saved"] = True
        elif action == "unsave":
            entry["saved"] = False
        elif action == "delete":
            comment_id = body.get("commentId", "")
            if comment_id:
                entry["comments"] = [c for c in entry["comments"] if c.get("id") != comment_id]
        elif action == "mark_processed":
            comment_id = body.get("commentId", "")
            if comment_id:
                for c in entry["comments"]:
                    if c.get("id") == comment_id:
                        c["processed"] = True

        save_comments(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/diffs", methods=["POST"])
def api_diffs():
    try:
        body = request.get_json()
        slug = body.get("slug", "").strip()
        if not slug:
            return jsonify({"error": "slug is required"}), 400

        files = body.get("files", [])
        diff_path = DIFFS_DIR / f"{slug}.json"
        tmp = str(diff_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"files": files}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, str(diff_path))
        invalidate_cache()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/search")
def api_search():
    try:
        from search import search_with_sidecar, hybrid_search
        q = request.args.get("q", "")
        limit = int(request.args.get("limit", "10"))
        doc_type = request.args.get("type")
        if not q:
            return jsonify({"error": "q parameter is required"}), 400
        if doc_type == "workflow":
            results = hybrid_search(q, limit=limit, doc_type=doc_type)
            return jsonify({"results": results, "workflows": []})
        results, workflows = search_with_sidecar(q, limit=limit, doc_type=doc_type)
        return jsonify({"results": results, "workflows": workflows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/threads")
def api_threads():
    """Enriched threads with entries_count, resurface, next_step."""
    try:
        from blog.services import load_threads_enriched
        status = request.args.get("status")
        return jsonify(load_threads_enriched(status_filter=status))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/claims")
def api_claims():
    """Aggregated claims workbench for epistemic triage."""
    try:
        from blog.services import load_claims_dashboard
        return jsonify(load_claims_dashboard(limit=12))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/claims/<claim_id>/detail")
def api_claim_detail(claim_id):
    """Full claim detail: support, threads, reports, and steering history."""
    try:
        from blog.services import load_claim_detail
        detail = load_claim_detail(claim_id)
        if detail is None:
            return jsonify({"error": f"Claim '{claim_id}' not found"}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/claim/<claim_id>")
def claim_page(claim_id):
    """Render claim detail page."""
    from blog.services import load_claim_detail
    detail = load_claim_detail(claim_id)
    if detail is None:
        abort(404)
    return render_template("claim_detail.html", claim=detail)


@app.route("/api/threads/<thread_id>/detail")
def api_thread_detail(thread_id):
    """Full thread detail: metadata, body, linked entries, reports, claims."""
    try:
        from blog.services import load_thread_detail
        detail = load_thread_detail(thread_id)
        if detail is None:
            return jsonify({"error": f"Thread '{thread_id}' not found"}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/thread/<thread_id>")
def thread_page(thread_id):
    """Render thread detail page."""
    from blog.services import load_thread_detail
    detail = load_thread_detail(thread_id)
    if detail is None:
        abort(404)
    return render_template("thread_detail.html", thread=detail)


@app.route("/api/proposals/<proposal_id>/detail")
def api_proposal_detail(proposal_id):
    """Full proposal detail: evidence, linked surfaces, and steering history."""
    try:
        from blog.services import load_proposal_detail
        detail = load_proposal_detail(proposal_id)
        if detail is None:
            return jsonify({"error": f"Proposal '{proposal_id}' not found"}), 404
        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/proposal/<proposal_id>")
def proposal_page(proposal_id):
    """Render proposal detail page."""
    from blog.services import load_proposal_detail
    detail = load_proposal_detail(proposal_id)
    if detail is None:
        abort(404)
    return render_template("proposal_detail.html", proposal=detail)


@app.route("/api/thread-candidates")
def api_thread_candidates():
    """Detect recurring tags that could become threads."""
    try:
        from blog.services import compute_thread_candidates
        return jsonify({"candidates": compute_thread_candidates()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/thread-candidates/<tag>/promote", methods=["POST"])
def api_promote_candidate(tag):
    """Create a thread from a candidate tag."""
    from datetime import timedelta
    threads_dir = THREADS_DIR
    thread_path = threads_dir / f"{tag}.md"
    if thread_path.exists():
        return jsonify({"error": f"Thread '{tag}' already exists"}), 409
    today = datetime.now().strftime("%Y-%m-%d")
    resurface = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    title = tag.replace("-", " ").replace("_", " ").title()
    content = f"""---
id: {tag}
title: "{title}"
type: investigation
status: proposed
owner: agent
created: {today}
updated: {today}
resurface: {resurface}
goal: ""
done_when: ""
---

## Fio

Thread criado a partir de candidate (tag '{tag}').

## Próximo passo

[definir]
"""
    threads_dir.mkdir(parents=True, exist_ok=True)
    thread_path.write_text(content, encoding="utf-8")
    return jsonify({"ok": True, "thread_id": tag})


@app.route("/api/threads/<thread_id>/snooze", methods=["POST"])
def api_thread_snooze(thread_id):
    """Snooze: update resurface +7d."""
    from datetime import timedelta
    from blog.api_actions import _log_operator_action

    thread_path = THREADS_DIR / f"{thread_id}.md"
    if not thread_path.exists():
        return jsonify({"error": f"Thread {thread_id} not found"}), 404
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "snooze")
    raw = thread_path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return jsonify({"error": "Invalid thread file"}), 400
    fm = yaml.safe_load(parts[1]) or {}
    today = datetime.now().strftime("%Y-%m-%d")
    fm["resurface"] = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    if mode == "worked":
        fm["updated"] = today
    new_fm = yaml.dump(fm, default_flow_style=False, allow_unicode=True).rstrip("\n")
    thread_path.write_text(f"---\n{new_fm}\n---{parts[2]}", encoding="utf-8")
    _log_operator_action(
        thread_id,
        f"thread:{mode}",
        value=fm["resurface"],
        target_type="thread",
        label=fm.get("title") or thread_id,
        reference=thread_id,
        resulting_state="applied",
    )
    return jsonify({"ok": True, "resurface": fm["resurface"]})


@app.route("/blog/comments.json")
def comments_json():
    return jsonify(load_comments())


# ─── Static files from ~/edge/ root ───
@app.route("/reports/<path:filename>")
def serve_reports(filename):
    return send_from_directory(str(REPORTS_DIR), filename)


@app.route("/builds/<path:filename>")
def serve_builds(filename):
    return send_from_directory(str(BUILDS_DIR), filename)


@app.route("/notes/<path:filename>")
def serve_notes(filename):
    return send_from_directory(str(NOTES_DIR), filename)


@app.route("/blog/entries/<path:filename>")
def serve_blog_entry_file(filename):
    return send_from_directory(str(ENTRIES_DIR), filename)


@app.route("/blog/diffs/<path:filename>")
def serve_diffs(filename):
    return send_from_directory(str(DIFFS_DIR), filename)


@app.route("/meta-reports/<path:filename>")
def serve_meta_reports(filename):
    return send_from_directory(str(META_REPORTS_DIR), filename)


# ─── Dashboard ───
def _build_threads_data():
    """Build context for threads partial."""
    from blog.services import load_threads_enriched, compute_thread_candidates
    data = load_threads_enriched()
    threads = data["threads"]
    threads_attention = [
        t for t in threads
        if t["status"] in {"active", "waiting"} and t.get("needs_attention")
    ]
    threads_waiting = [
        t for t in threads
        if t["status"] == "waiting" and not t.get("needs_attention")
    ]
    threads_active_healthy = [
        t for t in threads
        if t["status"] == "active" and not t.get("needs_attention")
    ]
    threads_proposed = [t for t in threads if t["status"] == "proposed"]
    threads_backlog = [t for t in threads if t["status"] in {"dormant", "done"}]

    return {
        "threads_attention": threads_attention,
        "threads_waiting": threads_waiting,
        "threads_active_healthy": threads_active_healthy,
        "threads_proposed": threads_proposed,
        "threads_backlog": threads_backlog,
        "thread_candidates": compute_thread_candidates(),
        "thread_stats": data["stats"],
        "thread_summary": {
            "attention": len(threads_attention),
            "waiting": len(threads_waiting),
            "healthy": len(threads_active_healthy),
            "proposed": len(threads_proposed),
            "backlog": len(threads_backlog),
        },
    }


@app.route("/partials/threads")
def partial_threads():
    """HTMX partial: threads section."""
    return render_template("partials/threads.html", **_build_threads_data())


def get_health_data(entries):
    """Compute health strip data."""
    from datetime import datetime, timezone
    health = {
        "entries": len(entries),
        "errors": 0,
        "beats_today": 0,
        "last_heartbeat": "?",
        "heartbeat_ok": False,
        "last_pub": "?",
        "claims_total": 0,
        "claims_open": 0,
    }
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Last pub from entries
    if entries:
        health["last_pub"] = entries[0].get("date", "?")

    # Count heartbeat entries today
    for e in entries:
        if e.get("date") == today_str:
            title_lower = (e.get("title") or "").lower()
            if "heartbeat" in title_lower:
                health["beats_today"] += 1

    # Claims from snapshot (edge-claims uses blog entries)
    try:
        import subprocess
        result = subprocess.run(
            ["edge-claims", "stats"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if "total" in line.lower() or "Total" in line:
                nums = [int(x) for x in line.split() if x.isdigit()]
                if nums:
                    health["claims_total"] = nums[0]
            if "open" in line.lower() or "aberta" in line.lower():
                nums = [int(x) for x in line.split() if x.isdigit()]
                if nums:
                    health["claims_open"] = nums[0]
    except Exception:
        pass

    # Heartbeat: check systemd timer
    try:
        import subprocess
        result = subprocess.run(
            ["systemctl", "--user", "is-active", "claude-heartbeat.timer"],
            capture_output=True, text=True, timeout=3
        )
        if result.stdout.strip() == "active":
            health["heartbeat_ok"] = True
            health["last_heartbeat"] = "active"
    except Exception:
        pass

    return health


@app.route("/dashboard")
@app.route("/dashboard/")
def dashboard_page():
    """Operational dashboard — 30-second health check for operator."""
    dashboard_sections = [
        {"id": "overview", "label": "overview"},
        {"id": "runtime", "label": "runtime"},
        {"id": "work", "label": "work"},
        {"id": "epistemics", "label": "epistemics"},
        {"id": "threads", "label": "threads"},
        {"id": "knowledge", "label": "knowledge"},
    ]
    section_lookup = {item["id"]: item["label"] for item in dashboard_sections}
    dashboard_section = str(request.args.get("section") or "overview").strip().lower()
    if dashboard_section not in section_lookup:
        dashboard_section = "overview"

    status_strip = _build_status_strip_data()
    dashboard_context = {}

    if dashboard_section == "overview":
        dashboard_context["alerts"] = _build_alerts_data()
        dashboard_context.update(_build_pipeline_data())
        dashboard_context.update(_build_hotspots_data())
        dashboard_context.update(_build_corpus_data())
        dashboard_context.update(_build_briefing_data())
    elif dashboard_section == "runtime":
        dashboard_context.update(_build_runtime_data())
    elif dashboard_section == "work":
        dashboard_context.update(_build_interventions_data())
    elif dashboard_section == "epistemics":
        dashboard_context.update(_build_epistemic_data())
    elif dashboard_section == "threads":
        dashboard_context.update(_build_threads_data())
    elif dashboard_section == "knowledge":
        knowledge_clusters = load_knowledge_clusters()
        dashboard_context["knowledge_clusters"] = [
            {k: v for k, v in item.items() if k != "content"}
            for item in knowledge_clusters
        ]

    return render_template(
        "dashboard.html",
        tab="dashboard",
        page_title=f"edge_of_chaos — dashboard / {section_lookup[dashboard_section]}",
        header_sub=f"dashboard / {section_lookup[dashboard_section]}",
        stats=get_stats_data(),
        dashboard_sections=dashboard_sections,
        dashboard_section=dashboard_section,
        **status_strip,
        **dashboard_context,
    )


def _human_size(size_bytes):
    """Human-readable file size."""
    for unit in ("B", "K", "M", "G"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes}{unit}" if unit == "B" else f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}T"


_SETUP_MAX_CONTENT = 50_000  # truncate files larger than this in the setup view


def _load_proposals():
    """Load active proposals from state/proposals.json."""
    try:
        import json as _j
        return [p for p in _j.loads(PROPOSALS_FILE.read_text()) if p.get("status") == "active"]
    except Exception:
        return []


def _load_notification_config():
    """Load notification settings from features.yaml + keys.env."""
    features_path = ROOT / "config" / "features.yaml"
    keys_path = ROOT / "secrets" / "keys.env"
    config = {"channel": "none", "telegram": {}, "whatsapp": {}, "slack": {},
              "events": {"approval": True, "health": True, "heartbeat": False, "reports": False}}
    try:
        import yaml as _y
        feat = _y.safe_load(features_path.read_text()) or {}
        notif = feat.get("notifications", {})
        # Detect active channel
        for ch in ("telegram", "slack", "whatsapp"):
            ch_cfg = notif.get(ch, {})
            if str(ch_cfg.get("enabled", "")).lower() in ("true", "auto"):
                config["channel"] = ch
                break
        # Load slack channels
        slack_cfg = notif.get("slack", {})
        config["slack"]["channels"] = slack_cfg.get("channels", {})
    except Exception:
        pass
    # Load keys (mask values)
    try:
        for line in keys_path.read_text().splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k == "TELEGRAM_BOT_TOKEN":
                config["telegram"]["bot_token"] = bool(v)
            if k == "TELEGRAM_CHAT_ID":
                config["telegram"]["chat_id"] = v
            if k == "SLACK_BOT_TOKEN":
                config["slack"]["bot_token"] = bool(v)
            if k == "SLACK_WEBHOOK_URL":
                config["slack"]["webhook"] = bool(v)
            if k == "WHATSAPP_PHONE":
                config["whatsapp"]["phone"] = v
            if k == "WHATSAPP_API_URL":
                config["whatsapp"]["api_url"] = bool(v)
    except Exception:
        pass
    return config


@app.route("/api/setup/notifications", methods=["POST"])
def save_notifications():
    """Save notification channel config to keys.env and features.yaml."""
    data = request.get_json() or {}
    channel = data.get("channel", "none")
    keys_path = ROOT / "secrets" / "keys.env"
    features_path = ROOT / "config" / "features.yaml"

    # Update keys.env (append/replace notification keys)
    key_updates = {}
    if channel == "telegram":
        if data.get("telegram_bot_token"):
            key_updates["TELEGRAM_BOT_TOKEN"] = data["telegram_bot_token"]
        if data.get("telegram_chat_id"):
            key_updates["TELEGRAM_CHAT_ID"] = data["telegram_chat_id"]
    elif channel == "whatsapp":
        if data.get("whatsapp_phone"):
            key_updates["WHATSAPP_PHONE"] = data["whatsapp_phone"]
        if data.get("whatsapp_api_url"):
            key_updates["WHATSAPP_API_URL"] = data["whatsapp_api_url"]
    elif channel == "slack":
        if data.get("slack_bot_token"):
            key_updates["SLACK_BOT_TOKEN"] = data["slack_bot_token"]
        if data.get("slack_webhook"):
            key_updates["SLACK_WEBHOOK_URL"] = data["slack_webhook"]

    if key_updates:
        existing = {}
        try:
            for line in keys_path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()
        except FileNotFoundError:
            pass
        existing.update(key_updates)
        keys_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")

    # Update features.yaml notification enabled flags
    try:
        import yaml as _y
        feat = _y.safe_load(features_path.read_text()) or {}
        notif = feat.setdefault("notifications", {})
        for ch in ("telegram", "slack", "whatsapp"):
            ch_cfg = notif.setdefault(ch, {})
            ch_cfg["enabled"] = True if ch == channel else False
        features_path.write_text(_y.dump(feat, default_flow_style=False, allow_unicode=True))
    except Exception:
        pass

    return jsonify({"ok": True, "channel": channel})


@app.route("/api/setup/notifications/test", methods=["POST"])
def test_notifications():
    """Send a test notification through the configured channel."""
    import subprocess
    result = subprocess.run(
        ["bash", "-c", f'{ROOT / "tools" / "notify.sh"} --level info "Test notification from dashboard"'],
        capture_output=True, text=True, timeout=10,
    )
    ok = result.returncode == 0
    return jsonify({"ok": ok, "output": result.stdout[:200] if ok else result.stderr[:200]})


@app.route("/setup")
def setup_page():
    """Setup tab — configure agent files, view system state."""
    from blog.setup_examples import EDITABLE_FILES, SYSTEM_FILES, GROUP_ORDER

    groups = []
    for key, label, editable in GROUP_ORDER:
        source = EDITABLE_FILES if editable else SYSTEM_FILES
        files = [f for f in source if f["group"] == key]

        enriched = []
        for f in files:
            path = ROOT / f["path"]
            is_dir = f.get("is_dir", False)
            entry = {**f}

            if is_dir:
                if path.is_dir():
                    all_files = sorted(
                        [p for p in path.iterdir() if p.is_file() and not p.name.startswith(".")],
                        key=lambda p: p.stat().st_mtime, reverse=True,
                    )
                    entry["dir_count"] = len(all_files)
                    entry["dir_recent"] = [p.name for p in all_files[:5]]
                    entry["status"] = "configured"
                    # dir metadata: newest file mtime + total size
                    try:
                        if all_files:
                            entry["mtime"] = datetime.fromtimestamp(all_files[0].stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                        total = sum(p.stat().st_size for p in all_files)
                        entry["size"] = _human_size(total)
                    except OSError:
                        pass
                else:
                    entry["dir_count"] = 0
                    entry["dir_recent"] = []
                    entry["status"] = "missing"
            else:
                try:
                    content = path.read_text(encoding="utf-8")
                except (FileNotFoundError, PermissionError):
                    content = None

                # file metadata
                try:
                    st = path.stat()
                    entry["mtime"] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                    entry["size"] = _human_size(st.st_size)
                    entry["lines"] = content.count("\n") + 1 if content else 0
                except (FileNotFoundError, OSError):
                    pass

                # truncate very large files for the UI
                if content and len(content) > _SETUP_MAX_CONTENT:
                    full_size = _human_size(len(content.encode("utf-8")))
                    entry["content"] = content[:_SETUP_MAX_CONTENT] + f"\n\n[... truncado — {full_size} total ...]"
                    entry["truncated"] = True
                else:
                    entry["content"] = content or ""

                if content is None:
                    entry["status"] = "missing"
                elif not content.strip():
                    entry["status"] = "empty"
                elif "{{" in content or "PLACEHOLDER" in content:
                    entry["status"] = "placeholder"
                else:
                    entry["status"] = "configured"

            enriched.append(entry)

        groups.append({
            "key": key,
            "label": label,
            "editable": editable,
            "files": enriched,
        })

    # Load notification config for setup UI
    notif_config = _load_notification_config()

    return render_template(
        "setup.html",
        tab="setup",
        page_title="edge_of_chaos — setup",
        header_sub="setup",
        stats=get_stats_data(),
        health=get_health_data(get_entries()),
        groups=groups,
        notif=notif_config,
    )




# ─── Knowledge Clusters ───
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent / "config"))
from paths import MEMORY_DIR, TOPICS_DIR


def load_knowledge_clusters():
    """Load all knowledge cluster files for dashboard/knowledge view."""
    clusters = []

    # Core rules (always-loaded)
    core_path = MEMORY_DIR / "rules-core.md"
    if core_path.exists():
        raw = core_path.read_text(encoding="utf-8", errors="replace")
        rule_count = raw.count("\n- Quando ") + raw.count("\n- quando ")
        clusters.append({
            "name": "rules-core",
            "path": str(core_path),
            "type": "core",
            "rules": rule_count,
            "size": len(raw),
            "lines": raw.count("\n") + 1,
            "content": raw,
        })

    # Miss log
    misses_path = MEMORY_DIR / "misses.md"
    if misses_path.exists():
        raw = misses_path.read_text(encoding="utf-8", errors="replace")
        miss_count = raw.count("### 20")
        pending = raw.count("pendente")
        clusters.append({
            "name": "misses",
            "path": str(misses_path),
            "type": "misses",
            "rules": miss_count,
            "pending": pending,
            "size": len(raw),
            "lines": raw.count("\n") + 1,
            "content": raw,
        })

    # Topic files
    if TOPICS_DIR.exists():
        for fp in sorted(TOPICS_DIR.glob("*.md")):
            try:
                raw = fp.read_text(encoding="utf-8", errors="replace")
                rule_count = sum(1 for line in raw.splitlines()
                                 if line.strip().startswith("- Quando ") or
                                 line.strip().startswith("- quando "))
                # Extract first heading as description
                desc = ""
                for line in raw.splitlines():
                    if line.startswith("# "):
                        desc = line.lstrip("# ").strip()
                        break
                clusters.append({
                    "name": fp.stem,
                    "path": str(fp),
                    "type": "topic",
                    "rules": rule_count,
                    "size": len(raw),
                    "lines": raw.count("\n") + 1,
                    "description": desc,
                    "content": raw,
                })
            except Exception:
                continue

    return clusters


@app.route("/knowledge")
def knowledge_page():
    """Knowledge clusters — browse and curate topic files."""
    clusters = load_knowledge_clusters()

    total_rules = sum(c.get("rules", 0) for c in clusters)
    total_files = len(clusters)
    topics = [c for c in clusters if c["type"] == "topic"]
    core = [c for c in clusters if c["type"] == "core"]
    misses = [c for c in clusters if c["type"] == "misses"]

    # Check if a specific file was requested
    selected = request.args.get("file")
    selected_content = None
    selected_name = None
    if selected:
        for c in clusters:
            if c["name"] == selected:
                selected_content = c["content"]
                selected_name = c["name"]
                break

    return render_template(
        "knowledge.html",
        tab="knowledge",
        stats=get_stats_data(),
        clusters=clusters,
        topics=topics,
        core=core,
        misses=misses,
        total_rules=total_rules,
        total_files=total_files,
        selected=selected,
        selected_content=selected_content,
        selected_name=selected_name,
    )


@app.route("/api/knowledge", methods=["GET"])
def api_knowledge():
    """JSON API: list knowledge clusters."""
    clusters = load_knowledge_clusters()
    # Strip content for API overview
    summary = []
    for c in clusters:
        s = {k: v for k, v in c.items() if k != "content"}
        summary.append(s)
    return jsonify({"clusters": summary, "total": len(summary)})


@app.route("/api/knowledge/<name>", methods=["GET"])
def api_knowledge_detail(name):
    """JSON API: single knowledge cluster content."""
    clusters = load_knowledge_clusters()
    for c in clusters:
        if c["name"] == name:
            return jsonify(c)
    return jsonify({"error": "not found"}), 404


# Catch-all for other ~/edge/ files (images, etc.)
@app.route("/<path:filepath>")
def serve_edge_file(filepath):
    """Serve any file from ~/edge/ root (backward compat with old server)."""
    full = ROOT / filepath
    if full.is_file():
        return send_from_directory(str(full.parent), full.name)
    abort(404)


if __name__ == "__main__":
    # Warm up cache on startup
    print("Warming up entry cache and FTS index...")
    get_entries()
    port = int(os.environ.get("BLOG_PORT", 8766))
    host = os.environ.get("BLOG_HOST", "127.0.0.1")
    print(f"Dashboard server (legacy blog package) on http://localhost:{port}/dashboard")
    app.run(host=host, port=port, debug=False, threaded=True)
