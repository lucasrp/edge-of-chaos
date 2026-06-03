"""Pipeline fino do v0 — as 6 fases. Lógica testável (clientes LLM injetados)."""
import re
from datetime import date
from pathlib import Path

import _llm


def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"[\s_]+", "-", s)


def read_secret(home, ref: str):
    fn, _, var = ref.partition(":")
    p = Path(home) / "secrets" / fn
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith(var + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _frontmatter_field(text: str, field: str):
    m = re.search(rf"^{field}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


# 1. Contextualização — escolhe o alvo (round-robin: primeiro thread ativo)
def pick_thread(home: Path):
    for f in sorted((home / "threads").glob("*.md")):
        txt = f.read_text()
        if re.search(r"^status:\s*active", txt, re.M):
            body = txt.split("---", 2)[-1].strip()
            return {"id": f.stem, "title": _frontmatter_field(txt, "title") or f.stem, "intent": body}
    return None


# 2. Pesquisa — 1 chamada LLM
def research(thread, chat_client, model):
    return _llm.complete(chat_client, model,
                         f"Pesquise e sintetize o essencial sobre: {thread['title']}. {thread['intent']}")


# 3. Artefato — gera o conteúdo via LLM
def build_artifact(thread, research_text, chat_client, model):
    md = _llm.complete(chat_client, model,
                       f"Escreva um relatório curto sobre '{thread['title']}'. Baseie-se em: {research_text}. "
                       "Formato: um resumo executivo de 2-3 frases, depois 2-3 seções com títulos '## '.")
    return {"title": thread["title"], "body_md": md, "thread_id": thread["id"]}


def render_html(artifact):
    try:
        import markdown
        body = markdown.markdown(artifact["body_md"], extensions=["tables", "fenced_code"])
    except Exception:
        body = "<pre>" + artifact["body_md"] + "</pre>"
    return (f'<!DOCTYPE html><html lang="pt"><head><meta charset="utf-8">'
            f'<title>{artifact["title"]}</title>'
            f'<link rel="stylesheet" href="/static/style.css"></head>'
            f'<body><article class="report"><h1>{artifact["title"]}</h1>'
            f'<p class="meta">{date.today().isoformat()} · thread:{artifact["thread_id"]}</p>'
            f'{body}</article></body></html>')


# 4. Qualidade — 2 gates advisory
def gate_forma(html):
    checks = {
        "title": "<title>" in html and "<title></title>" not in html,
        "h1": "<h1>" in html,
        "body": len(re.sub(r"<[^>]+>", "", html).strip()) > 80,
    }
    return {"gate": "forma", "passed": all(checks.values()), "checks": checks, "advisory": True}


def gate_adversarial(html, review_client, model):
    if review_client is None:
        return {"gate": "adversarial", "skipped": True, "advisory": True}
    plain = re.sub(r"<[^>]+>", " ", html)[:4000]
    crit = _llm.complete(review_client, model,
                         f"Avalie criticamente este relatório em 1 parágrafo; aponte a maior fraqueza:\n{plain}")
    return {"gate": "adversarial", "passed": True, "critique": crit[:300], "advisory": True}


# 5. Publicação
def publish(home, artifact, html):
    entries = home / "blog" / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    path = entries / f"{slug(artifact['title'])}.html"
    path.write_text(html)
    return path


# 6. Consolidação — registra o beat + atualiza rolling digest (L2; stub determinístico no v0)
def consolidate(home, thread, artifact):
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    digest = state / "chat-digest.md"
    prev = digest.read_text() if digest.exists() else "# Rolling digest\n"
    digest.write_text(prev + f"- {date.today().isoformat()}: publicou '{artifact['title']}' (thread {thread['id']})\n")
    return {"digest": digest}


def run_beat(home, chat_client, model, review_client=None, review_model=None):
    home = Path(home)
    thread = pick_thread(home)
    if not thread:
        return {"ok": False, "reason": "nenhum thread ativo"}
    research_text = research(thread, chat_client, model)
    artifact = build_artifact(thread, research_text, chat_client, model)
    html = render_html(artifact)
    gates = [gate_forma(html), gate_adversarial(html, review_client, review_model or model)]
    path = publish(home, artifact, html)
    consolidate(home, thread, artifact)
    return {"ok": True, "thread": thread["id"], "entry": str(path), "gates": gates}
