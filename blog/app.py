#!/usr/bin/env python3
"""Blog server: Flask + Jinja2 + htmx. Replaces server.py."""

import html as html_mod
import json
import math
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from flask import (
    Flask, jsonify, render_template, request, send_from_directory, abort
)
from flask_compress import Compress
import markdown
import yaml

# ─── Paths ───
ROOT = Path.home() / "continuum"
BLOG_DIR = ROOT / "blog"
ENTRIES_DIR = BLOG_DIR / "entries"
COMMENTS_FILE = BLOG_DIR / "comments.json"
DIFFS_DIR = BLOG_DIR / "diffs"
DIFFS_DIR.mkdir(parents=True, exist_ok=True)
META_REPORTS_DIR = ROOT / "meta-reports"
REPORTS_DIR = ROOT / "reports"

SEARCH_DIR = ROOT / "search"
sys.path.insert(0, str(SEARCH_DIR))
sys.path.insert(0, str(ROOT))

from blog.api_dashboard import dashboard_bp, _build_status_strip_data, _build_alerts_data, _build_pipeline_data, _build_hotspots_data, _build_corpus_data, _build_briefing_data
from blog.api_actions import actions_bp

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

PAGE_SIZE = 20

# ─── Tag normalization ───
TAG_MAP = {
    "leisure": "lazer", "reflection": "reflexao", "research": "pesquisa",
    "discovery": "descoberta", "strategy": "estrategia", "planning": "planejamento",
    "execution": "execucao", "calibration": "calibracao",
}

SKILL_GROUPS = [
    {"name": "producao", "label": "producao", "tags": ["pesquisa", "descoberta", "lazer"]},
    {"name": "planejamento", "label": "planejamento", "tags": ["planejamento", "estrategia"]},
    {"name": "meta", "label": "meta", "tags": ["reflexao", "execucao"]},
]


# ─── FTS5 index ───
FTS_DB_PATH = BLOG_DIR / "blog_fts.db"


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

        # Pipeline enforcement: entry is "published" only if meta-report exists
        published = bool(meta_report)

        entries.append({
            "title": fm.get("title", fp.stem),
            "tag": tag,
            "tags": tags_list,
            "date": str(fm.get("date", "")),
            "context": fm.get("context", ""),
            "report": os.path.basename(fm.get("report", "")) if fm.get("report") else "",
            "meta_report": meta_report,
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
        if not e.get("content_html") and not e["body_html"] and e.get("body_md"):
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
    """Get metadata from DB for entries (status, effort, project, proposta_id, content_html)."""
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
        # Pipeline enforcement: hide unpublished entries unless explicitly requested
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
    }


# ─── Routes: Main pages ───
@app.route("/blog/")
@app.route("/blog")
def blog_index():
    tab = request.args.get("tab", "feed")
    if tab not in ("feed", "chat"):
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

    elif tab == "chat":
        return render_template("chat.html", tab=tab, stats=stats,
                               is_htmx=request.headers.get("HX-Request") == "true")


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
    """Read autonomy capabilities and compute stats."""
    import re
    try:
        cap_path = ROOT / "autonomy" / "capabilities.md"
        frontier_path = ROOT / "autonomy" / "frontier.md"
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
        limit = int(request.args.get("limit", "100"))
        messages = get_chats(unprocessed_only=unprocessed, limit=limit)
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat_post():
    try:
        from dashboard_db import add_chat, mark_chat_processed
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
        from search import hybrid_search
        q = request.args.get("q", "")
        limit = int(request.args.get("limit", "10"))
        doc_type = request.args.get("type")
        if not q:
            return jsonify({"error": "q parameter is required"}), 400
        results = hybrid_search(q, limit=limit, doc_type=doc_type)
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/blog/comments.json")
def comments_json():
    return jsonify(load_comments())


# ─── Static files from root ───
@app.route("/reports/<path:filename>")
def serve_reports(filename):
    return send_from_directory(str(ROOT / "reports"), filename)


@app.route("/builds/<path:filename>")
def serve_builds(filename):
    return send_from_directory(str(ROOT / "builds"), filename)


@app.route("/blog/entries/<path:filename>")
def serve_blog_entry_file(filename):
    return send_from_directory(str(ENTRIES_DIR), filename)


@app.route("/blog/diffs/<path:filename>")
def serve_diffs(filename):
    return send_from_directory(str(DIFFS_DIR), filename)


@app.route("/meta-reports/<path:filename>")
def serve_meta_reports(filename):
    return send_from_directory(str(META_REPORTS_DIR), filename)


# ─── Task Ledger + Dashboard ───
STATE_DIR = ROOT / "state"
TASKS_JSONL = STATE_DIR / "tasks.jsonl"
TASKS_SNAPSHOT = STATE_DIR / "tasks.snapshot.json"
THREADS_DIR = ROOT / "threads"


def load_tasks_snapshot():
    """Load materialized task snapshot."""
    if TASKS_SNAPSHOT.exists():
        try:
            return json.loads(TASKS_SNAPSHOT.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def task_age(created_at):
    """Human-readable age from ISO timestamp."""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m"
        if hours < 24:
            return f"{int(hours)}h"
        return f"{int(hours / 24)}d"
    except Exception:
        return "?"


def enrich_task(t):
    """Add computed fields for template rendering."""
    t["age"] = task_age(t.get("created_at", t.get("updated_at", "")))
    # Human-readable last updated timestamp
    updated = t.get("updated_at", "")
    if updated:
        try:
            t["last_updated"] = updated[:16].replace("T", " ")
        except Exception:
            t["last_updated"] = ""
    else:
        t["last_updated"] = ""
    return t


def load_threads_summary():
    """Load thread YAML frontmatter for dashboard."""
    threads = []
    if not THREADS_DIR.exists():
        return threads
    for fp in sorted(THREADS_DIR.glob("*.md")):
        try:
            raw = fp.read_text(encoding="utf-8")
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1]) or {}
                if fm.get("status") in ("active", "waiting"):
                    threads.append({
                        "id": fp.stem,
                        "name": fm.get("title", fp.stem),
                        "status": fm.get("status", "?"),
                        "owner": fm.get("owner", "?"),
                    })
        except Exception:
            continue
    return threads


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

    # Claims from snapshot
    try:
        import subprocess
        result = subprocess.run(
            # NOTE: Replace with your claims tool name if different
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
def dashboard_page():
    """Operational dashboard — 30-second health check for operator."""
    snap = load_tasks_snapshot()
    entries = get_entries()

    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    all_tasks = sorted(
        snap.values(),
        key=lambda t: (prio_order.get(t.get("priority", "P3"), 9), t.get("updated_at", ""))
    )

    # Categorize
    tasks_doing = [enrich_task(t) for t in all_tasks if t.get("status") == "doing"]
    tasks_blocked = [enrich_task(t) for t in all_tasks if t.get("status") == "blocked"]
    tasks_todo = [enrich_task(t) for t in all_tasks if t.get("status") == "todo"][:7]
    tasks_done = [enrich_task(t) for t in all_tasks if t.get("status") == "done"][:5]

    # Stale: active tasks not updated in 48h
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    tasks_stale = []
    for t in all_tasks:
        if t.get("status") in ("done", "dropped"):
            continue
        updated = t.get("updated_at", "")
        if updated:
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if (now - dt).total_seconds() > 48 * 3600:
                    tasks_stale.append(enrich_task(t))
            except Exception:
                pass

    # Stats
    active_tasks = [t for t in all_tasks if t.get("status") not in ("done", "dropped")]
    task_stats = {
        "total": len(all_tasks),
        "doing": len([t for t in all_tasks if t.get("status") == "doing"]),
        "blocked": len([t for t in all_tasks if t.get("status") == "blocked"]),
        "todo": len([t for t in all_tasks if t.get("status") == "todo"]),
        "done": len([t for t in all_tasks if t.get("status") == "done"]),
    }

    health = get_health_data(entries)
    threads = load_threads_summary()
    knowledge_clusters = load_knowledge_clusters()
    # Strip content for dashboard summary
    kc_summary = [{k: v for k, v in c.items() if k != "content"} for c in knowledge_clusters]

    # Status strip data for initial render (HTMX refreshes after)
    status_strip = _build_status_strip_data()
    # Alerts data for initial render (HTMX refreshes after)
    alerts = _build_alerts_data()
    # Pipeline data for initial render (HTMX refreshes after)
    pipeline = _build_pipeline_data()
    # Hotspots data for initial render (HTMX refreshes after)
    hotspots_data = _build_hotspots_data()
    # Corpus data for initial render (HTMX refreshes after)
    corpus_data = _build_corpus_data()
    # Briefing data for initial render (HTMX refreshes after)
    briefing_data = _build_briefing_data()

    return render_template(
        "dashboard.html",
        tab="dashboard",
        page_title="continuum -- ops console",
        header_sub="ops console",
        stats=get_stats_data(),
        health=health,
        tasks_doing=tasks_doing,
        tasks_blocked=tasks_blocked,
        tasks_todo=tasks_todo,
        tasks_done=tasks_done,
        tasks_stale=tasks_stale,
        task_stats=task_stats,
        threads=threads,
        knowledge_clusters=kc_summary,
        alerts=alerts,
        **status_strip,
        **pipeline,
        **hotspots_data,
        **corpus_data,
        **briefing_data,
    )


@app.route("/api/tasks", methods=["GET"])
def api_tasks_get():
    """JSON API: list tasks with optional filters."""
    snap = load_tasks_snapshot()
    tasks = list(snap.values())
    status = request.args.get("status")
    priority = request.args.get("priority")
    owner = request.args.get("owner")
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    if priority:
        tasks = [t for t in tasks if t.get("priority") == priority]
    if owner:
        tasks = [t for t in tasks if t.get("owner") == owner]
    # Remove history from API response (too verbose)
    for t in tasks:
        t.pop("history", None)
    return jsonify({"tasks": tasks, "count": len(tasks)})


@app.route("/api/tasks/<task_id>", methods=["GET"])
def api_task_detail(task_id):
    """JSON API: single task with history."""
    snap = load_tasks_snapshot()
    if task_id not in snap:
        return jsonify({"error": "not found"}), 404
    return jsonify(snap[task_id])


# ─── Knowledge Clusters ───
# NOTE: Adjust MEMORY_DIR to match your Claude project memory path
MEMORY_DIR = Path.home() / ".claude" / "projects" / "memory"
TOPICS_DIR = MEMORY_DIR / "topics"


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
    """Knowledge clusters -- browse and curate topic files."""
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


# Catch-all for other files (images, etc.)
@app.route("/<path:filepath>")
def serve_edge_file(filepath):
    """Serve any file from root (backward compat with old server)."""
    full = ROOT / filepath
    if full.is_file():
        return send_from_directory(str(full.parent), full.name)
    abort(404)


if __name__ == "__main__":
    # Warm up cache on startup
    print("Warming up entry cache and FTS index...")
    get_entries()
    print(f"Blog server (Flask) on http://localhost:8766/blog/")
    app.run(host="127.0.0.1", port=8766, debug=False, threaded=True)
