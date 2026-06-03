#!/usr/bin/env python3
"""Blog server for agent heartbeat visualization, gate approval, and history."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import markdown
import yaml
from flask import Flask, jsonify, request

BASE_DIR = Path(__file__).parent
ENTRIES_DIR = BASE_DIR / "entries"
STATE_DIR = BASE_DIR.parent / "state"
AGENT_DISPLAY_NAME = os.environ.get("AGENT_NAME", BASE_DIR.parent.name)

app = Flask(__name__)


def parse_entry(filepath: Path) -> dict | None:
    """Parse a markdown blog entry with YAML frontmatter."""
    text = filepath.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        return None
    meta = yaml.safe_load(match.group(1)) or {}
    body_md = match.group(2)
    body_html = markdown.markdown(body_md, extensions=["tables", "fenced_code"])
    return {
        "slug": filepath.stem,
        "title": meta.get("title", filepath.stem),
        "date": str(meta.get("date", "")),
        "tags": meta.get("tags", []),
        "type": meta.get("type", "note"),
        "status": meta.get("status", ""),
        "body_html": body_html,
        "body_md": body_md,
        "meta": meta,
    }


def load_entries() -> list[dict]:
    """Load all entries sorted by date descending."""
    entries = []
    for f in sorted(ENTRIES_DIR.glob("*.md"), reverse=True):
        entry = parse_entry(f)
        if entry:
            entries.append(entry)
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


COLORS = {
    "primary": "#2b6cb0",
    "green": "#38a169",
    "yellow": "#ed8936",
    "bg": "#0f172a",
    "card": "#1e293b",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "border": "#334155",
}

TYPE_BADGES = {
    "heartbeat": ("&#x1f4a1;", COLORS["primary"]),
    "diagnosis": ("&#x1f50d;", COLORS["yellow"]),
    "implementation": ("&#x2699;&#xfe0f;", COLORS["green"]),
    "investigation": ("&#x1f50e;", COLORS["yellow"]),
    "note": ("&#x1f4dd;", COLORS["muted"]),
}


def render_page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — {AGENT_DISPLAY_NAME}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
    background: {COLORS['bg']}; color: {COLORS['text']};
    line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 2rem 1rem;
  }}
  a {{ color: {COLORS['primary']}; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.3rem; margin: 1.5rem 0 0.5rem; color: {COLORS['text']}; }}
  h3 {{ font-size: 1.1rem; margin: 1rem 0 0.3rem; }}
  .subtitle {{ color: {COLORS['muted']}; margin-bottom: 2rem; font-size: 0.9rem; }}
  .card {{
    background: {COLORS['card']}; border: 1px solid {COLORS['border']};
    border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem;
    transition: border-color 0.2s;
  }}
  .card:hover {{ border-color: {COLORS['primary']}; }}
  .card-title {{ font-size: 1.1rem; font-weight: 600; margin-bottom: 0.3rem; }}
  .card-meta {{ color: {COLORS['muted']}; font-size: 0.8rem; margin-bottom: 0.5rem; }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.75rem; font-weight: 600; margin-right: 0.3rem;
  }}
  .tag {{ background: {COLORS['border']}; color: {COLORS['muted']}; }}
  pre {{
    background: {COLORS['bg']}; border: 1px solid {COLORS['border']};
    border-radius: 6px; padding: 1rem; overflow-x: auto;
    font-size: 0.85rem; margin: 0.5rem 0;
  }}
  code {{ font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.85rem; }}
  p {{ margin: 0.5rem 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 0.5rem 0; }}
  th, td {{
    border: 1px solid {COLORS['border']}; padding: 0.5rem 0.8rem;
    text-align: left; font-size: 0.85rem;
  }}
  th {{ background: {COLORS['bg']}; font-weight: 600; }}
  ul, ol {{ margin: 0.5rem 0 0.5rem 1.5rem; }}
  .back {{ margin-bottom: 1.5rem; }}
  .status-ok {{ color: {COLORS['green']}; }}
  .status-warn {{ color: {COLORS['yellow']}; }}
  hr {{ border: none; border-top: 1px solid {COLORS['border']}; margin: 1.5rem 0; }}
  .empty {{ text-align: center; padding: 3rem; color: {COLORS['muted']}; }}
  /* Gate UI styles */
  .gate-section {{ margin-bottom: 2rem; }}
  .gate-section h2 {{ margin-bottom: 1rem; }}
  .approval-item {{
    background: {COLORS['card']}; border: 1px solid {COLORS['border']};
    border-radius: 8px; padding: 1rem 1.2rem; margin-bottom: 0.75rem;
    transition: border-color 0.2s;
  }}
  .approval-item.approved {{ border-color: {COLORS['green']}; }}
  .approval-item-header {{
    display: flex; align-items: flex-start; gap: 0.75rem;
  }}
  .approval-checkbox {{
    display: flex; align-items: center; gap: 0.4rem; cursor: pointer;
    flex-shrink: 0; user-select: none;
  }}
  .approval-checkbox input[type="checkbox"] {{
    width: 18px; height: 18px; accent-color: {COLORS['green']}; cursor: pointer;
  }}
  .check-label {{
    font-size: 0.75rem; font-weight: 600; color: {COLORS['muted']};
    text-transform: uppercase; letter-spacing: 0.03em;
    transition: color 0.15s;
  }}
  .approval-item.approved .check-label {{ color: {COLORS['green']}; }}
  .approval-item-label {{ flex: 1; font-size: 0.95rem; }}
  .approval-item-label.checked {{ color: {COLORS['muted']}; }}
  .feedback-input {{
    width: 100%; margin-top: 0.6rem; padding: 0.5rem 0.75rem;
    background: {COLORS['bg']}; border: 1px solid {COLORS['border']};
    border-radius: 6px; color: {COLORS['text']}; font-size: 0.85rem;
    font-family: inherit; resize: vertical; min-height: 36px;
  }}
  .feedback-input::placeholder {{ color: {COLORS['muted']}; }}
  .feedback-input:focus {{ outline: none; border-color: {COLORS['primary']}; }}
  .submit-bar {{
    position: sticky; bottom: 0; background: {COLORS['bg']};
    border-top: 1px solid {COLORS['border']}; padding: 1rem 0;
    display: flex; align-items: center; gap: 1rem;
  }}
  .btn {{
    padding: 0.6rem 1.5rem; border: none; border-radius: 6px;
    font-size: 0.9rem; font-weight: 600; cursor: pointer; transition: opacity 0.2s;
  }}
  .btn:hover {{ opacity: 0.85; }}
  .btn-primary {{ background: {COLORS['primary']}; color: #fff; }}
  .btn-success {{ background: {COLORS['green']}; color: #fff; }}
  .submit-status {{ color: {COLORS['muted']}; font-size: 0.85rem; }}
  .general-feedback {{
    width: 100%; padding: 0.6rem 0.75rem; margin-top: 0.5rem;
    background: {COLORS['card']}; border: 1px solid {COLORS['border']};
    border-radius: 6px; color: {COLORS['text']}; font-size: 0.9rem;
    font-family: inherit; resize: vertical; min-height: 60px;
  }}
  .general-feedback::placeholder {{ color: {COLORS['muted']}; }}
  .general-feedback:focus {{ outline: none; border-color: {COLORS['primary']}; }}
  .proposed-item {{
    background: {COLORS['card']}; border: 1px solid {COLORS['border']};
    border-radius: 8px; padding: 0.8rem 1.2rem; margin-bottom: 0.5rem;
  }}
  .gate-status {{
    display: inline-block; padding: 4px 12px; border-radius: 12px;
    font-size: 0.8rem; font-weight: 600;
  }}
  .gate-waiting {{ background: {COLORS['yellow']}; color: #000; }}
  .gate-responded {{ background: {COLORS['green']}; color: #fff; }}
  .summary-text {{ color: {COLORS['text']}; line-height: 1.7; }}
  .nav-link {{
    display: inline-block; padding: 0.4rem 0.8rem; margin-right: 0.5rem;
    background: {COLORS['card']}; border: 1px solid {COLORS['border']};
    border-radius: 6px; font-size: 0.85rem; color: {COLORS['primary']};
  }}
  .nav-link:hover {{ border-color: {COLORS['primary']}; text-decoration: none; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


@app.route("/")
@app.route("/blog/")
def index():
    entries = load_entries()
    if not entries:
        body = """
        <h1>{AGENT_DISPLAY_NAME} — Blog</h1>
        <p class="subtitle">Heartbeat insights, diagnostics, and implementation notes</p>
        <div class="empty">
            <p>Nenhuma entrada ainda.</p>
            <p>Execute o heartbeat para gerar a primeira entrada.</p>
        </div>"""
        return render_page("Blog", body)

    cards = ""
    for e in entries:
        icon, color = TYPE_BADGES.get(e["type"], TYPE_BADGES["note"])
        tags_html = "".join(f'<span class="badge tag">{t}</span>' for t in e["tags"])
        status_class = "status-ok" if e["status"] in ("done", "ok", "completed") else "status-warn"
        status_html = f' <span class="{status_class}">[{e["status"]}]</span>' if e["status"] else ""
        cards += f"""
        <a href="/blog/{e['slug']}" style="text-decoration:none;color:inherit;">
        <div class="card">
            <div class="card-title">{icon} {e['title']}{status_html}</div>
            <div class="card-meta">{e['date']} &middot;
                <span class="badge" style="background:{color};color:#fff;">{e['type']}</span>
                {tags_html}
            </div>
        </div>
        </a>"""

    gate = _load_gate()
    gate_link = ""
    if gate and gate.get("status") == "waiting":
        gate_link = f'<a href="/gate/" class="nav-link">&#x1f6a8; Gate ativo — aguardando feedback</a>'

    body = f"""
    <h1>{AGENT_DISPLAY_NAME} — Blog</h1>
    <p class="subtitle">Heartbeat insights, diagnostics, and implementation notes &middot; {len(entries)} entries</p>
    <div style="margin-bottom:1rem;">
      {gate_link}
      <a href="/gate/history/" class="nav-link">Historico de Gates</a>
    </div>
    {cards}"""
    return render_page("Blog", body)


@app.route("/blog/<slug>")
def entry(slug):
    filepath = ENTRIES_DIR / f"{slug}.md"
    if not filepath.exists():
        return "Not found", 404
    e = parse_entry(filepath)
    if not e:
        return "Parse error", 500

    icon, color = TYPE_BADGES.get(e["type"], TYPE_BADGES["note"])
    tags_html = "".join(f'<span class="badge tag">{t}</span>' for t in e["tags"])
    body = f"""
    <div class="back"><a href="/blog/">&larr; All entries</a></div>
    <h1>{icon} {e['title']}</h1>
    <div class="card-meta" style="margin-bottom:1.5rem;">
        {e['date']} &middot;
        <span class="badge" style="background:{color};color:#fff;">{e['type']}</span>
        {tags_html}
    </div>
    <div>{e['body_html']}</div>"""
    return render_page(e["title"], body)


@app.route("/api/entries")
def api_entries():
    entries = load_entries()
    for e in entries:
        del e["body_html"]
    return jsonify(entries)


@app.route("/api/chat", methods=["GET", "POST"])
def api_chat():
    if request.method == "GET":
        return jsonify({"messages": [], "status": "ok"})
    data = request.get_json(silent=True) or {}
    return jsonify({"received": data, "status": "ok"})


def _load_gate() -> dict | None:
    gate_file = STATE_DIR / "human-gate.json"
    if not gate_file.exists():
        return None
    try:
        return json.loads(gate_file.read_text(encoding="utf-8"))
    except Exception:
        return None


@app.route("/gate/")
def gate_ui():
    gate = _load_gate()
    if not gate:
        body = """
        <h1>Human Gate</h1>
        <p class="subtitle">Nenhum gate ativo no momento.</p>
        <div class="empty"><p>O heartbeat ainda não gerou um gate.</p></div>
        <a href="/blog/" class="nav-link">&larr; Blog</a>"""
        return render_page("Gate", body)

    status = gate.get("status", "unknown")
    created = gate.get("created_at", "")
    summary = gate.get("summary", "")
    current_state = gate.get("current_state", "")
    pending = gate.get("pending_approvals", [])
    proposed = gate.get("proposed_next", [])

    status_class = "gate-waiting" if status == "waiting" else "gate-responded"
    status_label = "Aguardando feedback" if status == "waiting" else status.capitalize()

    # Build approval items
    approval_items = ""
    for i, item in enumerate(pending):
        approval_items += f"""
        <div class="approval-item" id="item-{i}">
          <div class="approval-item-header">
            <label class="approval-checkbox">
              <input type="checkbox" id="check-{i}" onchange="toggleCheck({i})">
              <span class="checkmark"></span>
              <span class="check-label">Aprovado</span>
            </label>
            <span class="approval-item-label" id="label-{i}">{item}</span>
          </div>
          <input type="text" class="feedback-input" id="feedback-{i}"
                 placeholder="Feedback opcional para este item...">
        </div>"""

    # Build proposed next items
    proposed_items = ""
    for i, item in enumerate(proposed):
        proposed_items += f"""
        <div class="approval-item" id="next-item-{i}">
          <div class="approval-item-header">
            <label class="approval-checkbox">
              <input type="checkbox" id="next-check-{i}" onchange="toggleNext({i})">
              <span class="checkmark"></span>
              <span class="check-label">Aprovado</span>
            </label>
            <span class="approval-item-label" id="next-label-{i}">{item}</span>
          </div>
          <input type="text" class="feedback-input" id="next-feedback-{i}"
                 placeholder="Feedback opcional para este item...">
        </div>"""

    body = f"""
    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.5rem;">
      <a href="/blog/" class="nav-link">&larr; Blog</a>
      <a href="/gate/history/" class="nav-link">Historico</a>
    </div>

    <h1>Human Gate</h1>
    <p class="subtitle">
      <span class="gate-status {status_class}">{status_label}</span>
      &middot; {created}
    </p>

    <div class="gate-section">
      <h2>Resumo do Beat</h2>
      <div class="card">
        <p class="summary-text">{summary}</p>
      </div>
    </div>

    {"<div class='gate-section'><h2>Estado Atual</h2><div class='card'><p class='summary-text'>" + current_state + "</p></div></div>" if current_state else ""}

    <form id="gate-form" onsubmit="return submitFeedback(event)">
      <div class="gate-section">
        <h2>Pendencias ({len(pending)})</h2>
        {approval_items if pending else '<p style="color:' + COLORS["muted"] + '">Nenhuma pendencia.</p>'}
      </div>

      <div class="gate-section">
        <h2>Proximo Beat (proposta)</h2>
        {proposed_items if proposed else '<p style="color:' + COLORS["muted"] + '">Nenhuma proposta.</p>'}
      </div>

      <div class="gate-section">
        <h2>Feedback Geral</h2>
        <textarea class="general-feedback" id="general-feedback"
                  placeholder="Instrucoes adicionais, ajustes de prioridade, contexto..."></textarea>
      </div>

      <div class="submit-bar">
        <button type="submit" class="btn btn-primary">Aprovar</button>
        <button type="button" class="btn btn-success" onclick="approveAllAndSubmit()">Aprovar Tudo</button>
        <span class="submit-status" id="submit-status"></span>
      </div>
    </form>

    <script>
    function toggleCheck(i) {{
      const cb = document.getElementById('check-' + i);
      const label = document.getElementById('label-' + i);
      const item = document.getElementById('item-' + i);
      if (cb.checked) {{
        label.classList.add('checked');
        item.classList.add('approved');
      }} else {{
        label.classList.remove('checked');
        item.classList.remove('approved');
      }}
    }}

    function toggleNext(i) {{
      const cb = document.getElementById('next-check-' + i);
      const label = document.getElementById('next-label-' + i);
      const item = document.getElementById('next-item-' + i);
      if (cb.checked) {{
        label.classList.add('checked');
        item.classList.add('approved');
      }} else {{
        label.classList.remove('checked');
        item.classList.remove('approved');
      }}
    }}

    function approveAllAndSubmit() {{
      for (let i = 0; i < {len(pending)}; i++) {{
        const cb = document.getElementById('check-' + i);
        cb.checked = true;
        document.getElementById('label-' + i).classList.add('checked');
        document.getElementById('item-' + i).classList.add('approved');
      }}
      for (let i = 0; i < {len(proposed)}; i++) {{
        const cb = document.getElementById('next-check-' + i);
        cb.checked = true;
        document.getElementById('next-label-' + i).classList.add('checked');
        document.getElementById('next-item-' + i).classList.add('approved');
      }}
      document.getElementById('gate-form').requestSubmit();
    }}

    async function submitFeedback(e) {{
      e.preventDefault();
      const status = document.getElementById('submit-status');
      status.textContent = 'Enviando...';

      const items = [];
      for (let i = 0; i < {len(pending)}; i++) {{
        items.push({{
          index: i,
          text: document.getElementById('label-' + i).textContent,
          approved: document.getElementById('check-' + i).checked,
          feedback: document.getElementById('feedback-' + i).value.trim()
        }});
      }}

      const proposed_items = [];
      for (let i = 0; i < {len(proposed)}; i++) {{
        proposed_items.push({{
          index: i,
          text: document.getElementById('next-label-' + i).textContent,
          approved: document.getElementById('next-check-' + i).checked,
          feedback: document.getElementById('next-feedback-' + i).value.trim()
        }});
      }}

      const payload = {{
        items: items,
        proposed_next: proposed_items,
        general_feedback: document.getElementById('general-feedback').value.trim(),
        responded_at: new Date().toISOString()
      }};

      try {{
        const resp = await fetch('/api/gate/feedback', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(payload)
        }});
        const result = await resp.json();
        if (result.status === 'ok') {{
          window.location.href = '/blog/';
        }} else {{
          status.textContent = 'Erro: ' + (result.error || 'unknown');
          status.style.color = '{COLORS["yellow"]}';
        }}
      }} catch (err) {{
        status.textContent = 'Erro de rede: ' + err.message;
        status.style.color = '{COLORS["yellow"]}';
      }}
    }}
    </script>"""
    return render_page("Human Gate", body)


@app.route("/api/gate", methods=["GET"])
def api_gate():
    gate = _load_gate()
    if not gate:
        return jsonify({"status": "no_gate"}), 404
    return jsonify(gate)


@app.route("/api/gate/feedback", methods=["POST"])
def api_gate_feedback():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "error": "no data"}), 400

    gate = _load_gate()
    if not gate:
        return jsonify({"status": "error", "error": "no active gate"}), 404

    # Save feedback to gate file
    gate["status"] = "responded"
    gate["feedback"] = {
        "items": data.get("items", []),
        "proposed_next": data.get("proposed_next", []),
        "general_feedback": data.get("general_feedback", ""),
        "responded_at": data.get("responded_at",
                                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")),
    }

    gate_file = STATE_DIR / "human-gate.json"
    gate_file.write_text(json.dumps(gate, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also post to chat API for audit trail
    approved_count = sum(1 for it in data.get("items", []) if it.get("approved"))
    total = len(data.get("items", []))
    general = data.get("general_feedback", "")

    chat_msg = f"Gate feedback: {approved_count}/{total} items approved."
    if general:
        chat_msg += f" Note: {general}"

    chat_file = STATE_DIR / "gate-feedback-log.jsonl"
    log_entry = json.dumps({
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "feedback": data,
    }, ensure_ascii=False)
    with open(chat_file, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

    return jsonify({"status": "ok", "approved": approved_count, "total": total})


def _load_gate_history() -> list[dict]:
    """Load all archived gates sorted by date descending."""
    history_dir = STATE_DIR / "gate-history"
    if not history_dir.exists():
        return []
    entries = []
    for f in sorted(history_dir.glob("gate-*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            data["_filename"] = f.stem
            entries.append(data)
        except Exception:
            continue
    return entries


@app.route("/gate/history/")
def gate_history():
    entries = _load_gate_history()

    if not entries:
        body = """
        <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
          <a href="/gate/" class="nav-link">&larr; Gate</a>
          <a href="/blog/" class="nav-link">Blog</a>
        </div>
        <h1>Gate History</h1>
        <div class="empty"><p>Nenhuma iteracao arquivada ainda.</p></div>"""
        return render_page("Gate History", body)

    cards = ""
    for e in entries:
        created = e.get("created_at", "?")
        summary = e.get("summary", "No summary")
        if len(summary) > 200:
            summary = summary[:200] + "..."
        feedback = e.get("feedback", {})
        items = feedback.get("items", [])
        proposed = feedback.get("proposed_next", [])
        has_feedback = bool(feedback)

        if has_feedback:
            approved = sum(1 for it in items if it.get("approved"))
            total = len(items)
            proposed_approved = sum(1 for it in proposed if it.get("approved"))
            proposed_total = len(proposed)
            badge = f'<span class="badge" style="background:{COLORS["green"]};color:#fff;">{approved}/{total} aprovados</span>'
            if proposed_total:
                badge += f' <span class="badge" style="background:{COLORS["primary"]};color:#fff;">{proposed_approved}/{proposed_total} proximos</span>'
        else:
            badge = f'<span class="badge" style="background:{COLORS["yellow"]};color:#000;">sem feedback</span>'

        cards += f"""
        <a href="/gate/history/{e['_filename']}" style="text-decoration:none;color:inherit;">
        <div class="card">
          <div class="card-title">{created} {badge}</div>
          <div class="card-meta" style="margin-top:0.4rem;">{summary}</div>
        </div>
        </a>"""

    body = f"""
    <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
      <a href="/gate/" class="nav-link">&larr; Gate</a>
      <a href="/blog/" class="nav-link">Blog</a>
    </div>
    <h1>Gate History</h1>
    <p class="subtitle">{len(entries)} iteracoes arquivadas</p>
    {cards}"""
    return render_page("Gate History", body)


def _render_history_items(items: list[dict], section_title: str) -> str:
    """Render a list of gate items with approval status and feedback."""
    if not items:
        return ""
    html = f'<div class="gate-section"><h2>{section_title}</h2>'
    for it in items:
        approved = it.get("approved", False)
        text = it.get("text", "")
        fb = it.get("feedback", "")
        icon = f'<span style="color:{COLORS["green"]}">&#x2714;</span>' if approved else f'<span style="color:{COLORS["yellow"]}">&#x2718;</span>'
        status_text = "Aprovado" if approved else "Nao aprovado"
        border_color = COLORS["green"] if approved else COLORS["border"]
        html += f"""
        <div class="approval-item" style="border-color:{border_color};">
          <div class="approval-item-header">
            <span style="flex-shrink:0;font-size:1.1rem;">{icon}</span>
            <span class="approval-item-label">{text}</span>
            <span class="badge" style="background:{COLORS["green"] if approved else COLORS["border"]};color:#fff;flex-shrink:0;">{status_text}</span>
          </div>
          {"<div style='margin-top:0.5rem;padding:0.5rem 0.75rem;background:" + COLORS["bg"] + ";border:1px solid " + COLORS["border"] + ";border-radius:6px;font-size:0.85rem;color:" + COLORS["text"] + ";'><strong>Feedback:</strong> " + fb + "</div>" if fb else ""}
        </div>"""
    html += "</div>"
    return html


@app.route("/gate/history/<filename>")
def gate_history_detail(filename):
    history_dir = STATE_DIR / "gate-history"
    filepath = history_dir / f"{filename}.json"
    if not filepath.exists():
        return "Not found", 404

    try:
        gate = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return "Parse error", 500

    created = gate.get("created_at", "?")
    summary = gate.get("summary", "")
    current_state = gate.get("current_state", "")
    feedback = gate.get("feedback", {})
    items = feedback.get("items", [])
    proposed = feedback.get("proposed_next", [])
    general_fb = feedback.get("general_feedback", "")
    responded_at = feedback.get("responded_at", "")

    items_html = _render_history_items(items, f"Pendencias ({len(items)})")
    proposed_html = _render_history_items(proposed, f"Proximos Passos ({len(proposed)})")

    body = f"""
    <div style="display:flex;gap:0.5rem;margin-bottom:1rem;">
      <a href="/gate/history/" class="nav-link">&larr; Historico</a>
      <a href="/gate/" class="nav-link">Gate</a>
      <a href="/blog/" class="nav-link">Blog</a>
    </div>

    <h1>Gate — {created}</h1>
    <p class="subtitle">
      {"Respondido em " + responded_at if responded_at else "Sem resposta"}
    </p>

    <div class="gate-section">
      <h2>Resumo do Beat</h2>
      <div class="card"><p class="summary-text">{summary}</p></div>
    </div>

    {"<div class='gate-section'><h2>Estado Atual</h2><div class='card'><p class='summary-text'>" + current_state + "</p></div></div>" if current_state else ""}

    {items_html}
    {proposed_html}

    {"<div class='gate-section'><h2>Feedback Geral</h2><div class='card'><p class='summary-text'>" + general_fb + "</p></div></div>" if general_fb else ""}
    """
    return render_page(f"Gate {created}", body)


if __name__ == "__main__":
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("BLOG_PORT", 8766))
    print(f"Blog server starting on http://localhost:{port}/blog/")
    app.run(host="0.0.0.0", port=port, debug=False)
