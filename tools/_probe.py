"""_probe — probe rápido do cortex pro loop de deploy (env pré-sourced pelo wrapper `rq`).
Cypher:  rq 'MATCH (c:Community {group_id:$g}) RETURN count(c) AS n'   (use $g pro group)
Python:  rq < snip.py    (globais: C=communities, d=driver, q(cypher,**p)->[dict], G=group)
Host-agnóstico: G vem SEMPRE do _identity do host — nunca de um literal de install (#21)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import communities as C

import _identity

# FAIL-LOUD, sem fallback (ADR-0015 / #21): q() injeta g=G em todo cypher, então um default
# embutido faz este probe LER E ESCREVER no grupo de outro tenant sempre que a identidade não
# resolver — em silêncio, que é o pior modo possível para uma ferramenta de query interativa.
G = _identity.require_group()

d = C._driver()


def q(cypher, **p):
    p.setdefault("g", G)
    with d.session() as s:
        return [dict(r) for r in s.run(cypher, **p)]


if __name__ == "__main__":
    if len(sys.argv) > 1:                       # cypher mode
        for row in q(sys.argv[1]):
            print(row)
    elif not sys.stdin.isatty():                # python mode: stdin runs with C,d,q,G in scope
        exec(compile(sys.stdin.read(), "<rq>", "exec"), {"C": C, "d": d, "q": q, "G": G})
