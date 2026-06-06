"""wiki_render — project the graph into wiki pages (ADR-0005). Genotype render tool.

The wiki is a re-rendered projection of the graph, never edited. Two lenses over the SAME graph:
  threads      — cluster pages, each a 2-paragraph synthesis (default)
  dictionary   — terse definitional anchors grouped by section (aicodingdictionary style)
Reads the `render` router from agent.yaml (the cheap synthesis model) and the `Idiom` standing
page, queries current-valid facts / non-archived entities / grill-curated clusters. Re-run on
any graph change — change the lens, not the source.

Usage:  python wiki_render.py <group_id> [out_dir] [threads|dictionary]
Env:    OPENAI_API_KEY (or ~/.edge-sandbox-kit/openai.env), EDGE_NEO4J_URI/USER/PASSWORD
"""
import html
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEO4J = (os.environ.get("EDGE_NEO4J_URI", "bolt://localhost:7687"),
         os.environ.get("EDGE_NEO4J_USER", "neo4j"),
         os.environ.get("EDGE_NEO4J_PASSWORD", "edgepassword123"))


def _load_key():
    if os.environ.get("OPENAI_API_KEY"):
        return
    # The install's OWN secrets first (OSS: BYO key); ~/.edge-sandbox-kit is only a dev fallback.
    for f in (REPO / "secrets" / "openai.env", Path.home() / ".edge-sandbox-kit" / "openai.env"):
        if f.exists():
            for line in f.read_text().splitlines():
                if "OPENAI_API_KEY" in line:
                    os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
                    return


def render_model():
    """The `render` router model from agent.yaml (ADR-0005); falls back to a known mini id."""
    m = re.search(r"render:.*?\n(?:.*\n)*?\s*model:\s*(\S+)", (REPO / "agent.yaml").read_text())
    return m.group(1) if m else "gpt-5.4-mini"


def idiom():
    p = REPO / "state" / "idiom.md"
    return p.read_text() if p.exists() else "(no Idiom standing page yet)"


def project_vocab(root=None, max_each=3000, max_total=8000):
    """The mentee's project vocabulary: the available CONTEXT.md glossaries across their projects,
    deduped (clone worktrees share a CONTEXT.md). Frames cluster synthesis in the projects' terms."""
    root = Path(root) if root else Path.home()
    seen, parts, total = set(), [], 0
    for f in sorted(root.glob("*/CONTEXT.md")):
        try:
            txt = f.read_text()
        except Exception:
            continue
        key = hash(txt)
        if key in seen:
            continue
        seen.add(key)
        chunk = f"### {f.parent.name}/CONTEXT.md\n{txt[:max_each]}"
        if total + len(chunk) > max_total:
            break
        parts.append(chunk)
        total += len(chunk)
    return "\n\n".join(parts) or "(no project CONTEXT.md found)"


def _clusters(q, group):
    """The grill-curated clusters and their non-archived entities (display + raw name)."""
    labels = [r["l"] for r in q("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                                "RETURN DISTINCT e.curated_cluster AS l", g=group)]
    out = []
    for label in labels:
        ents = q("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster=$l "
                 "AND coalesce(e.archived,false)=false "
                 "RETURN coalesce(e.curated_name,e.name) AS d, e.name AS n, e.merged_into AS m, "
                 "(e.grilled_at IS NOT NULL) AS g", g=group, l=label)
        out.append((label, [e for e in ents if not e.get("m")]))
    return out


def _facts(q, name, limit=5):
    """Current-valid facts for an entity, deduped in order. Contested facts are **shown flagged**,
    not withheld (ADR-0008/#12): the non-curated tier carries ambiguity, the grill resolves it."""
    rows = q("MATCH (x:Entity {name:$n})-[r:RELATES_TO]-() WHERE r.invalid_at IS NULL "
             "RETURN r.fact AS f, coalesce(r.contested,false) AS c LIMIT $k", n=name, k=limit)
    out = []
    for r in rows:
        f = r.get("f")
        if not f:
            continue
        f = ("⚠ contested — " + f) if r.get("c") else f
        if f not in out:
            out.append(f)
    return out


def _uncurated(q, group, limit=60):
    """The non-curated (hypothesis) tier: entities the grill has not yet clustered — **shown, not
    hidden** (ADR-0008/#12). Non-archived, non-merged, no curated_cluster: the eager-extraction tier."""
    return q("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NULL "
             "AND coalesce(e.archived,false)=false AND e.merged_into IS NULL "
             "RETURN coalesce(e.curated_name,e.name) AS d, e.name AS n ORDER BY d LIMIT $k",
             g=group, k=limit)


def cluster_tag(grilled, total):
    """The honest tag (ADR-0005): `curated` only when the grill has reached every entity."""
    if total and grilled == total:
        return "curated"
    if grilled == 0:
        return "draft"
    return f"{grilled}/{total} grilled"


ENGLISH_IDIOM_RULE = (
    "Write the prose in English. 'Idiom' here means the mentee's coined terminology, not their "
    "language: keep their coined terms (e.g. Mundo, Atividade, Voz, beat, grill, Knowledge cluster) "
    "verbatim; do not translate them.")


def synthesis_prompt(label, facts, idiom, vocab):
    """The cluster-synthesis prompt: English prose, the coined idiom kept verbatim (R2), framed in
    the projects' own vocabulary (their CONTEXT.md glossaries)."""
    return (f"{ENGLISH_IDIOM_RULE}\nThe mentee idiom:\n{idiom}\n\n"
            f"The projects' vocabulary (CONTEXT.md glossaries) — use these terms and meanings:\n{vocab}\n\n"
            f"Write a 2-paragraph synthesis for the knowledge cluster '{label}' in edge-next. Facts:\n"
            + "\n".join(f"- {f}" for f in facts[:30])
            + "\nSay what it is and the decision it implies. Plain prose.")


THREAD_CSS = ("body{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#222}"
              "h1{border-bottom:2px solid #2a7}.meta{color:#888;font-size:.85em}a{color:#06c}"
              ".tag{font-size:.72em;color:#fff;background:#2a7;border-radius:3px;padding:1px 6px}")

DICT_CSS = """
:root{--ink:#1a1a1a;--mut:#6b7280;--acc:#2a7f62;--line:#e5e7eb;--bg:#fafaf9}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:17px/1.65 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:4rem 1.5rem 6rem}
header h1{font-size:2.4rem;margin:0 0 .3rem;letter-spacing:-.02em}
header p{color:var(--mut);font-size:1.1rem;margin:0 0 .5rem}.sub{font-size:.85rem;color:var(--acc)}
section{margin-top:3rem}section>h2{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;
color:var(--acc);border-bottom:1px solid var(--line);padding-bottom:.5rem;margin-bottom:1.2rem}
.term{margin:1.1rem 0}.term dt{font-weight:650;font-size:1.02rem}.term dd{margin:.15rem 0 0;color:#374151}
footer{margin-top:4rem;color:var(--mut);font-size:.8rem;border-top:1px solid var(--line);padding-top:1rem}a{color:var(--acc)}
"""


def _doc(title, css, body):
    return (f'<!doctype html><html lang=en><head><meta charset=utf-8>'
            f'<meta name=viewport content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title><style>{css}</style></head><body>{body}</body></html>')


def render_threads(q, group, out, oai, model, idi, voc):
    out.mkdir(parents=True, exist_ok=True)
    links = []
    grilled_all = total_all = 0
    for label, ents in _clusters(q, group):
        shown = sorted({e["d"] for e in ents})
        facts = [f for e in ents[:10] for f in _facts(q, e["n"])]
        grilled = sum(1 for e in ents if e.get("g"))
        grilled_all, total_all = grilled_all + grilled, total_all + len(ents)
        tag = cluster_tag(grilled, len(ents))
        r = oai.chat.completions.create(model=model, messages=[{"role": "user", "content":
            synthesis_prompt(label, facts, idi, voc)}], max_completion_tokens=600)
        synth = r.choices[0].message.content or ""
        body = (f'<h1>{html.escape(label)} <span class=tag>{html.escape(tag)}</span></h1>'
                f'<p class=meta>knowledge cluster · {len(shown)} entities · {model} (ADR-0005)</p>'
                f'<div>{html.escape(synth)}</div><h3>entities</h3>'
                + "".join(f"<p>• {html.escape(d)}</p>" for d in shown) + '<p><a href="index.html">← index</a></p>')
        fn = f"cluster-{re.sub(r'[^a-z]', '', label.lower())}.html"
        (out / fn).write_text(_doc(label, THREAD_CSS, body))
        links.append((label, fn, len(shown)))
    # --- non-curated (hypothesis) tier — shown, not hidden (ADR-0008/#12) ---
    unc = _uncurated(q, group)
    if unc:
        seen = {}
        for e in unc:
            seen.setdefault(e["d"], e["n"])
        items = "".join(
            "<p>• " + html.escape(d)
            + "".join(f"<br><span class=meta>{html.escape(f)}</span>" for f in _facts(q, n, 3))
            + "</p>" for d, n in list(seen.items())[:40])
        body = (f'<h1>Non-curated <span class=tag>hypothesis</span></h1>'
                f'<p class=meta>{len(seen)} entities awaiting the grill · the eager-extraction tier, '
                f'contested shown flagged (ADR-0008 · #12)</p>{items}'
                f'<p><a href="index.html">← index</a></p>')
        (out / "cluster-noncurated.html").write_text(_doc("Non-curated (hypothesis)", THREAD_CSS, body))
        links.append(("Non-curated (hypothesis)", "cluster-noncurated.html", len(seen)))
    idx = (f'<h1>edge-next wiki <span class=tag>{html.escape(cluster_tag(grilled_all, total_all))}</span></h1>'
           f'<p class=meta>{len(links)} clusters · {model} · framed in the Idiom · ADR-0005 projection</p>'
           + "".join(f'<p>• <a href="{f}">{html.escape(t)}</a> <span class=meta>({n})</span></p>' for t, f, n in links))
    (out / "index.html").write_text(_doc("edge-next wiki", THREAD_CSS, idx))
    print(f"threads: {len(links)} clusters with {model} → {out/'index.html'}")


def render_dictionary(q, group, out, oai, model, idi, voc):
    out.mkdir(parents=True, exist_ok=True)
    body = ['<div class=wrap><header><h1>edge-next dictionary</h1>',
            '<p>The vocabulary of the edge, in plain English.</p>',
            '<p class=sub>a rendered projection of the wiki graph — grown from sessions, curated by the grill (ADR-0005)</p></header>']
    nsec = 0
    for label, ents in _clusters(q, group):
        seen = {}
        for e in ents:
            seen.setdefault(e["d"], e["n"])
        tf = "\n".join(f"- {t}: {' | '.join(_facts(q, n, 4))}" for t, n in seen.items())
        r = oai.chat.completions.create(model=model, messages=[{"role": "user", "content":
            f"{ENGLISH_IDIOM_RULE}\nThe mentee idiom (do not redefine):\n{idi}\n\n"
            f"The projects' vocabulary (CONTEXT.md glossaries) — use these terms:\n{voc}\n\n"
            f"For the '{label}' section of an edge-next dictionary, write ONE plain-English line defining "
            f"each term (glossary style — concise, definitional, no examples). Terms and facts:\n{tf}\n"
            f"Reply ONLY a JSON object {{term: one-line definition}}."}], max_completion_tokens=700)
        mm = re.search(r"\{.*\}", r.choices[0].message.content or "{}", re.S)
        try:
            defs = json.loads(mm.group(0)) if mm else {}
        except Exception:
            defs = {}
        terms = "".join(f'<div class=term><dt>{html.escape(t)}</dt>'
                        f'<dd>{html.escape(defs.get(t) or defs.get(t.lower()) or "—")}</dd></div>'
                        for t in sorted(seen))
        body.append(f'<section><h2>{html.escape(label)}</h2><dl>{terms}</dl></section>')
        nsec += 1
    body.append(f'<footer>edge-next · {nsec} grill-curated sections · rendered by {model} · ADR-0005</footer></div>')
    (out / "dictionary.html").write_text(_doc("edge-next dictionary", DICT_CSS, "".join(body)))
    print(f"dictionary: {nsec} sections with {model} → {out/'dictionary.html'}")


def main(group, out_dir, style):
    _load_key()
    from openai import OpenAI
    from neo4j import GraphDatabase
    oai, model, idi, voc = OpenAI(), render_model(), idiom(), project_vocab()
    drv = GraphDatabase.driver(NEO4J[0], auth=(NEO4J[1], NEO4J[2]))

    def q(c, **kw):
        with drv.session() as s:
            return [r.data() for r in s.run(c, **kw)]

    (render_dictionary if style == "dictionary" else render_threads)(q, group, Path(out_dir), oai, model, idi, voc)
    drv.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "edge-next",
         sys.argv[2] if len(sys.argv) > 2 else str(REPO / "state" / "wiki"),
         sys.argv[3] if len(sys.argv) > 3 else "threads")
