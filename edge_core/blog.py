from __future__ import annotations

import html
import json
import http.server
import socketserver
from functools import partial
from urllib.parse import parse_qs, urlparse

from .async_chat import add_message, list_messages, mark_processed, pin_message, unpin_message
from .config import RuntimeConfig
from .publication import build_blog
from .util import truncate


def _operator_pressure_html(config: RuntimeConfig) -> str:
    if not config.operator_pressure_path.exists():
        return "<p class='pressure-empty'>No explicit operator pressure file is present.</p>"
    text = config.operator_pressure_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return "<p class='pressure-empty'>Operator pressure file is empty.</p>"
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
    return "".join(f"<p>{html.escape(truncate(part, 520))}</p>" for part in paragraphs[:6])


def _chat_page_html(config: RuntimeConfig) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>edge async chat</title>"
        "<style>"
        "@import url('https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700&display=swap');"
        "body{font-family:'Libre Franklin',system-ui,sans-serif;max-width:1080px;margin:0 auto;padding:2.2rem 1.2rem 3rem;line-height:1.6;color:#17202a;background:linear-gradient(180deg,#edf4ff 0,#f9fafb 320px)}"
        "nav{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:1.2rem}nav a{display:inline-flex;padding:.5rem .8rem;border-radius:999px;background:#fff;border:1px solid #d7dce4;color:#1c519b;text-decoration:none;font-weight:600}"
        ".layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(260px,1fr);gap:1rem}.panel{background:#fff;border:1px solid #d8e2f0;border-radius:16px;padding:1rem 1.05rem;box-shadow:0 12px 30px rgba(20,52,97,.06)}"
        ".messages{display:flex;flex-direction:column;gap:.8rem;min-height:420px;max-height:72vh;overflow:auto}.message{padding:.8rem .9rem;border-radius:12px;background:#f8fafc;border:1px solid #e2e8f0}.message-meta{font-size:.82rem;color:#52606d;margin-bottom:.35rem}"
        ".badge{display:inline-flex;padding:.12rem .45rem;border-radius:999px;background:#edf4ff;color:#22426c;font-size:.72rem;margin-left:.35rem}.pending{background:#fff7d6;color:#8a6700}.pinned{background:#dff7e9;color:#11653a}"
        "textarea{width:100%;min-height:120px;padding:.8rem;border:1px solid #d7dce4;border-radius:12px;font:inherit}button{margin-top:.75rem;padding:.68rem 1rem;border:0;border-radius:12px;background:#1c519b;color:#fff;font-weight:600;cursor:pointer}"
        ".pressure-empty{color:#52606d}.hint{color:#52606d;font-size:.94rem}@media (max-width:900px){.layout{grid-template-columns:1fr}}"
        "</style></head><body>"
        "<nav><a href='/'>Report Archive</a><a href='/chat'>Async Chat</a></nav>"
        "<header><h1>Async Operator Chat</h1><p class='hint'>This lane stays outside the report archive. New beats read it as operator context, and successful cycles acknowledge what they consumed.</p></header>"
        f"<div class='layout'><section class='panel'><div id='messages' class='messages'></div><form id='chat-form'><textarea id='chat-text' placeholder='Send async guidance for the next beat...'></textarea><button type='submit'>Send message</button></form></section><aside class='panel'><h2>Operator Pressure</h2>{_operator_pressure_html(config)}</aside></div>"
        "<script>"
        "async function loadMessages(){const r=await fetch('/api/chat?limit=60');const p=await r.json();const root=document.getElementById('messages');root.innerHTML='';"
        "(p.messages||[]).forEach((item)=>{const box=document.createElement('article');box.className='message';"
        "const flags=[item.pinned?\"<span class=\\'badge pinned\\'>pinned</span>\":\"\",!item.processed?\"<span class=\\'badge pending\\'>pending</span>\":\"\"].join('');"
        "box.innerHTML=`<div class='message-meta'>${item.ts} · ${item.author}${flags}</div><div>${String(item.text).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>`;root.appendChild(box);});"
        "root.scrollTop=root.scrollHeight;}"
        "document.getElementById('chat-form').addEventListener('submit', async (ev)=>{ev.preventDefault();const input=document.getElementById('chat-text');const text=input.value.trim();if(!text)return;"
        "await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'add',author:'user',text})});input.value='';await loadMessages();});"
        "loadMessages();setInterval(loadMessages,10000);"
        "</script></body></html>"
    )


class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class BlogHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, config: RuntimeConfig, **kwargs):
        self.config = config
        super().__init__(*args, directory=str(config.root / "blog"), **kwargs)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat_get(parsed)
            return
        if parsed.path in {"/chat", "/chat/"}:
            self._write_html(_chat_page_html(self.config))
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat_post()
            return
        self.send_error(404, "unsupported path")

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _write_json(self, payload: dict[str, object], *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, html_text: str, *, status: int = 200) -> None:
        body = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_chat_get(self, parsed) -> None:
        params = parse_qs(parsed.query)
        limit = int((params.get("limit") or ["100"])[0])
        messages = list_messages(
            self.config,
            limit=limit,
            unprocessed_only=(params.get("unprocessed") or ["0"])[0] == "1",
            pinned_only=(params.get("pinned") or ["0"])[0] == "1",
        )
        self._write_json({"messages": messages})

    def _handle_chat_post(self) -> None:
        body = self._read_json_body()
        action = str(body.get("action") or "add").strip()
        if action == "add":
            text = str(body.get("text") or "").strip()
            if not text:
                self._write_json({"error": "text is required"}, status=400)
                return
            message = add_message(self.config, author=str(body.get("author") or "user"), text=text, pinned=bool(body.get("pinned")))
            self._write_json({"ok": True, "id": message.get("id"), "message": message})
            return
        if action == "mark_processed":
            updated = mark_processed(self.config, int(body.get("id") or 0))
            self._write_json({"ok": bool(updated), "message": updated}, status=200 if updated else 404)
            return
        if action == "pin":
            updated = pin_message(self.config, int(body.get("id") or 0))
            self._write_json({"ok": bool(updated), "message": updated}, status=200 if updated else 404)
            return
        if action == "unpin":
            updated = unpin_message(self.config, int(body.get("id") or 0))
            self._write_json({"ok": bool(updated), "message": updated}, status=200 if updated else 404)
            return
        self._write_json({"error": f"unknown action: {action}"}, status=400)


def serve_blog(config: RuntimeConfig, *, port: int) -> None:
    build_blog(config)
    handler = partial(BlogHandler, config=config)
    with ThreadingTCPServer(("", port), handler) as server:
        print(f"Serving edge blog at http://127.0.0.1:{port}/")
        server.serve_forever()
