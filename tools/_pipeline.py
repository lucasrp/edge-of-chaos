"""Thin v0 pipeline — the 6 phases. Semantic logic lives in skills, not here.

Each phase dispatches to a skill (loads its SKILL.md prompt). The runtime only
orchestrates. Logic in the skill, not the runtime (ADR-0001/0002 of the rebuild).
Core logic is testable with injected LLM clients.
"""
import re
from datetime import date
from pathlib import Path

import _llm

REPO = Path(__file__).resolve().parent.parent


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


def load_skill(home, name: str) -> str:
    """Load a skill's prompt (its SKILL.md body). home/skills wins, repo/skills falls back."""
    for base in (Path(home) / "skills", REPO / "skills"):
        p = base / name / "SKILL.md"
        if p.exists():
            text = p.read_text()
            if text.startswith("---"):
                parts = text.split("---", 2)
                text = parts[2] if len(parts) >= 3 else text
            return text.strip()
    raise FileNotFoundError(f"skill not found: {name}")


def render(template: str, **kw) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _frontmatter_field(text: str, field: str):
    m = re.search(rf"^{field}:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else None


# 1. Contextualization — pick the target (round-robin: first active thread)
def pick_thread(home: Path):
    for f in sorted((home / "threads").glob("*.md")):
        txt = f.read_text()
        if re.search(r"^status:\s*active", txt, re.M):
            body = txt.split("---", 2)[-1].strip()
            return {"id": f.stem, "title": _frontmatter_field(txt, "title") or f.stem, "intent": body}
    return None


# 2. Research — dispatch to the research skill
def research(thread, chat_client, model, home):
    prompt = render(load_skill(home, "research"), title=thread["title"], intent=thread["intent"])
    return _llm.complete(chat_client, model, prompt)


# 3. Artifact — dispatch to the report skill
def build_artifact(thread, research_text, chat_client, model, home):
    prompt = render(load_skill(home, "report"), title=thread["title"], research=research_text)
    md = _llm.complete(chat_client, model, prompt)
    return {"title": thread["title"], "body_md": md, "thread_id": thread["id"]}


def render_html(artifact):
    try:
        import markdown
        body = markdown.markdown(artifact["body_md"], extensions=["tables", "fenced_code"])
    except Exception:
        body = "<pre>" + artifact["body_md"] + "</pre>"
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{artifact["title"]}</title>'
            f'<link rel="stylesheet" href="/static/style.css"></head>'
            f'<body><article class="report"><h1>{artifact["title"]}</h1>'
            f'<p class="meta">{date.today().isoformat()} · thread:{artifact["thread_id"]}</p>'
            f'{body}</article></body></html>')


# 4. Quality — two advisory gates
def gate_structure(html):
    checks = {
        "title": "<title>" in html and "<title></title>" not in html,
        "h1": "<h1>" in html,
        "body": len(re.sub(r"<[^>]+>", "", html).strip()) > 80,
    }
    return {"gate": "structure", "passed": all(checks.values()), "checks": checks, "advisory": True}


def gate_adversarial(html, review_client, model, home):
    if review_client is None:
        return {"gate": "adversarial", "skipped": True, "advisory": True}
    plain = re.sub(r"<[^>]+>", " ", html)[:4000]
    prompt = render(load_skill(home, "quality"), report=plain)
    crit = _llm.complete(review_client, model, prompt)
    return {"gate": "adversarial", "passed": True, "critique": crit[:300], "advisory": True}


# 5. Publish
def publish(home, artifact, html):
    entries = home / "blog" / "entries"
    entries.mkdir(parents=True, exist_ok=True)
    path = entries / f"{slug(artifact['title'])}.html"
    path.write_text(html)
    return path


# 6. Consolidation — record the beat + update the rolling digest (L2; deterministic stub in v0)
def consolidate(home, thread, artifact):
    state = home / "state"
    state.mkdir(parents=True, exist_ok=True)
    digest = state / "chat-digest.md"
    prev = digest.read_text() if digest.exists() else "# Rolling digest\n"
    digest.write_text(prev + f"- {date.today().isoformat()}: published '{artifact['title']}' (thread {thread['id']})\n")
    return {"digest": digest}


def run_beat(home, chat_client, model, review_client=None, review_model=None):
    home = Path(home)
    thread = pick_thread(home)
    if not thread:
        return {"ok": False, "reason": "no active thread"}
    research_text = research(thread, chat_client, model, home)
    artifact = build_artifact(thread, research_text, chat_client, model, home)
    html = render_html(artifact)
    gates = [gate_structure(html), gate_adversarial(html, review_client, review_model or model, home)]
    path = publish(home, artifact, html)
    consolidate(home, thread, artifact)
    return {"ok": True, "thread": thread["id"], "entry": str(path), "gates": gates}
