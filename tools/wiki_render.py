"""wiki_render — project the graph into wiki pages (ADR-0005). Genotype render tool.

The wiki is a re-rendered projection of the graph, never edited. This tool reads the `render`
router from agent.yaml (the cheap synthesis model) and the `Idiom` standing page, queries the
graph (current-valid facts, non-archived entities, grill-curated clusters), and writes the pages:
mechanical entity pages + index, mini-synthesized cluster threads. Re-run on any graph change.

Usage:  python wiki_render.py <group_id> [out_dir]
Env:    OPENAI_API_KEY (or ~/.edge-sandbox-kit/openai.env), EDGE_NEO4J_URI/USER/PASSWORD
"""
import html
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
    f = Path.home() / ".edge-sandbox-kit" / "openai.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')


def render_model():
    """The `render` router model from agent.yaml (ADR-0005); falls back to a known mini id."""
    txt = (REPO / "agent.yaml").read_text()
    m = re.search(r"render:.*?\n(?:.*\n)*?\s*model:\s*(\S+)", txt)
    return m.group(1) if m else "gpt-5.4-mini"


def idiom():
    p = REPO / "state" / "idiom.md"
    return p.read_text() if p.exists() else "(no Idiom standing page yet)"


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#222}}
h1{{border-bottom:2px solid #2a7}}.meta{{color:#888;font-size:.85em}}a{{color:#06c}}
.tag{{font-size:.72em;color:#fff;background:#2a7;border-radius:3px;padding:1px 6px}}</style></head><body>{body}</body></html>"""


def main(group, out_dir):
    _load_key()
    from openai import OpenAI
    from neo4j import GraphDatabase
    oai, model, idi = OpenAI(), render_model(), idiom()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    drv = GraphDatabase.driver(NEO4J[0], auth=(NEO4J[1], NEO4J[2]))

    def q(c, **kw):
        with drv.session() as s:
            return [r.data() for r in s.run(c, **kw)]

    def synth(label, facts):
        r = oai.chat.completions.create(model=model, messages=[{"role": "user", "content":
            f"Frame strictly in this mentee idiom (their terms, do not redefine):\n{idi}\n\n"
            f"Write a 2-paragraph synthesis for the knowledge cluster '{label}' in edge-next. Facts:\n"
            + "\n".join(f"- {f}" for f in facts[:30])
            + "\nSay what the cluster is and the decision it implies. Plain prose, the mentee's voice."}],
            max_completion_tokens=600)
        return r.choices[0].message.content or ""

    # grill-curated clusters (non-archived), display by curated_name
    labels = [r["l"] for r in q("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster IS NOT NULL "
                                "RETURN DISTINCT e.curated_cluster AS l", g=group)]
    links = []
    for label in labels:
        ents = q("MATCH (e:Entity {group_id:$g}) WHERE e.curated_cluster=$l AND coalesce(e.archived,false)=false "
                 "RETURN coalesce(e.curated_name,e.name) AS d, e.name AS n", g=group, l=label)
        shown = sorted({e["d"] for e in ents})
        facts = []
        for e in ents[:10]:
            facts += [r["f"] for r in q("MATCH (x:Entity {name:$n})-[r:RELATES_TO]-() "
                      "WHERE r.invalid_at IS NULL RETURN r.fact AS f LIMIT 5", n=e["n"])]
        body = f'<h1>{html.escape(label)} <span class=tag>curated</span></h1>' \
               f'<p class=meta>knowledge cluster · {len(shown)} entities · rendered by {model} (ADR-0005)</p>' \
               f'<div>{html.escape(synth(label, facts))}</div><h3>entities</h3>' \
               + "".join(f"<p>• {html.escape(d)}</p>" for d in shown) + '<p><a href="index.html">← index</a></p>'
        fn = f"cluster-{re.sub(r'[^a-z]', '', label.lower())}.html"
        (out / fn).write_text(PAGE.format(title=html.escape(label), body=body))
        links.append((label, fn, len(shown)))

    idx = f'<h1>edge-next wiki <span class=tag>curated</span></h1>' \
          f'<p class=meta>{len(links)} clusters · rendered by {model} · framed in the Idiom · ADR-0005 projection</p>' \
          + "".join(f'<p>• <a href="{f}">{html.escape(t)}</a> <span class=meta>({n})</span></p>' for t, f, n in links)
    (out / "index.html").write_text(PAGE.format(title="edge-next wiki", body=idx))
    drv.close()
    print(f"rendered {len(links)} clusters with {model} → {out/'index.html'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "edge-next",
         sys.argv[2] if len(sys.argv) > 2 else str(REPO / "state" / "wiki"))
