"""group_health — o critério de saúde de frota da issue #636, como instrumento read-only.

A cerca de `group_id` funciona (zero aresta cross-group nos grafos medidos). O MAPA é que não:
nos installs velhos o write-path funciona e o read-path morreu — 788 Directions sem título no
roberto, 6 Objectives idênticos no petertosh, dois tenants para o mesmo agente, zero Community.

Este módulo responde "este group está navegável?" SEM VARRER BODY. Essa restrição não é
performance, é o teste: se para saber no que o agente trabalha for preciso abrir oitocentos
parágrafos, o grafo é diário, não memória. Um campo que só existe dentro da prosa não conta
como handle — e o relatório acusa isso como defeito em vez de silenciosamente ler o body.

READ-ONLY por construção: só executa MATCH/RETURN. Nada aqui escreve, renomeia ou apaga; o
rename e o GC são a #634 e moram noutro lugar, com dry-run e confirmação.
"""
import os

# Tetos do critério de frota. Não são leis da natureza — são a linha onde "muitas" vira
# "ninguém consegue ler". Ajustar aqui, não espalhado pelos chamadores.
OPEN_DIRECTIONS_CEILING = 25
HAS_TOPIC_DEGREE_CEILING = 1.2          # arestas HAS_TOPIC por nó do group


def _driver(uri=None, user=None, password=None):
    from neo4j import GraphDatabase
    uri = uri or os.environ.get("EDGE_NEO4J_URI", "bolt://127.0.0.1:7687")
    user = user or os.environ.get("EDGE_NEO4J_USER", "neo4j")
    password = password or os.environ.get("EDGE_NEO4J_PASSWORD")
    if not password:
        return None
    return GraphDatabase.driver(uri, auth=(user, password))


def groups(session):
    """Todo group_id presente no Bolt, com contagem — inclusive o balde `None` (unlabeled)."""
    rows = session.run(
        "MATCH (n) RETURN n.group_id AS g, count(n) AS c ORDER BY c DESC").data()
    return [(r["g"], r["c"]) for r in rows]


def health(session, group):
    """O cartão de saúde de UM group. Só MATCH/RETURN; nenhum body é lido."""
    def one(cypher, **kw):
        rec = session.run(cypher, g=group, **kw).single()
        return dict(rec) if rec else {}

    genesis = one("MATCH (n:Genesis {group_id:$g}) RETURN count(n) AS n")["n"]
    objectives = one("MATCH (n:Objective {group_id:$g}) RETURN count(n) AS n")["n"]

    # Directions: o handle é o que permite listar sem abrir. `title`/`name` ausentes são o
    # defeito da #632 — contados, não contornados lendo o body.
    d = one(
        "MATCH (n:Direction {group_id:$g}) "
        "RETURN count(n) AS total, "
        "  count(CASE WHEN coalesce(n.title, n.name) IS NOT NULL THEN 1 END) AS with_handle, "
        "  count(CASE WHEN n.expires_at IS NOT NULL OR n.supersedes IS NOT NULL THEN 1 END) "
        "    AS with_lifecycle")
    communities = one("MATCH (n:Community {group_id:$g}) RETURN count(n) AS n")["n"]
    nodes = one("MATCH (n {group_id:$g}) RETURN count(n) AS n")["n"]
    topics = one(
        "MATCH (a {group_id:$g})-[r:HAS_TOPIC]->() RETURN count(r) AS n")["n"]

    return {
        "group": group,
        "nodes": nodes,
        "genesis": genesis,
        "objectives": objectives,
        "directions_total": d.get("total", 0),
        "directions_with_handle": d.get("with_handle", 0),
        "directions_with_lifecycle": d.get("with_lifecycle", 0),
        "communities": communities,
        "has_topic_edges": topics,
        "has_topic_degree": round(topics / nodes, 2) if nodes else 0.0,
    }


def verdicts(card):
    """As falhas do cartão, em linguagem do critério. Lista vazia = navegável.

    Cada item é (severidade, mensagem). `dark` é reservado para o que NÃO PUDE ser medido —
    distinto de `fail`, que é medido e ruim. Confundir os dois foi o defeito que fez os 0
    Community da frota passarem por escassez durante meses (#635)."""
    out = []
    g = card["group"]

    if card["genesis"] != 1:
        out.append(("fail", f"{g}: {card['genesis']} Genesis (esperado exatamente 1)"))
    if card["objectives"] > 1:
        out.append(("fail", f"{g}: {card['objectives']} Objectives vivos — o rito promete 1 (#633)"))
    elif card["objectives"] == 0 and card["nodes"]:
        out.append(("warn", f"{g}: nenhum Objective — o agente não tem norte declarado"))

    total, handled = card["directions_total"], card["directions_with_handle"]
    if total and handled < total:
        out.append(("fail",
                    f"{g}: {total - handled} de {total} Directions sem handle — não dá para "
                    f"listar no que este agente trabalha sem abrir o body (#632)"))
    if total > OPEN_DIRECTIONS_CEILING:
        out.append(("fail",
                    f"{g}: {total} Directions acima do teto de {OPEN_DIRECTIONS_CEILING} — "
                    "barato propor, caro encerrar (#632)"))
    if total and card["directions_with_lifecycle"] == 0:
        out.append(("warn",
                    f"{g}: nenhuma das {total} Directions tem expiry/supersedes — sem lifecycle "
                    "consolidate não tem o que fundir (#632)"))

    if card["communities"] == 0 and card["nodes"] > 50:
        out.append(("fail",
                    f"{g}: 0 Community em {card['nodes']} nós — grafo write-only; ZERO só é "
                    "legítimo se o consolidate falhou ALTO (#635)"))

    if card["has_topic_degree"] > HAS_TOPIC_DEGREE_CEILING:
        out.append(("fail",
                    f"{g}: HAS_TOPIC grau {card['has_topic_degree']} (>{HAS_TOPIC_DEGREE_CEILING}) "
                    "— tudo liga no mesmo punhado de tópicos; o grafo deixa de apontar (#635)"))
    return out


def leftovers(session, installed):
    """Groups sem install e nós sem group_id — o lixo que a cerca esconde (#634).

    `installed` é o conjunto de groups que ESTE host declara. Um group_id no Bolt que não está
    nele é tenant órfão: rename sem migrate, ou install morto que ninguém enterrou."""
    out = []
    for g, c in groups(session):
        if g is None:
            out.append(("fail", f"<sem group_id>: {c} nó(s) — invisíveis a qualquer filtro por "
                                "tenant, e uma query sem $g os vê como fantasma (#634)"))
        elif g not in installed:
            out.append(("warn", f"{g}: {c} nó(s) de um group que não é install deste host — "
                                "rename sem migrate, ou tenant morto sem GC (#634)"))
    return out


def report(session, installed=(), only=None):
    """O relatório da frota: um cartão por group + os leftovers. Devolve (linhas, falhas)."""
    lines, failures = [], 0
    for g, _count in groups(session):
        if g is None or (only and g != only):
            continue
        card = health(session, g)
        lines.append(
            f"{g:<14} nós={card['nodes']:<6} genesis={card['genesis']} "
            f"obj={card['objectives']} dir={card['directions_with_handle']}/"
            f"{card['directions_total']} com handle  comm={card['communities']}  "
            f"has_topic={card['has_topic_degree']}")
        for sev, msg in verdicts(card):
            lines.append(f"  [{sev}] {msg}")
            failures += sev == "fail"
    if not only:
        for sev, msg in leftovers(session, set(installed)):
            lines.append(f"  [{sev}] {msg}")
            failures += sev == "fail"
    return lines, failures


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    only = argv[0] if argv else None

    installed = set()
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import _identity
        g = _identity.group()
        if g:
            installed.add(g)
    except Exception:  # noqa: BLE001 — a saúde não depende de identidade resolver
        pass

    drv = _driver()
    if drv is None:
        print("group_health: DARK — sem EDGE_NEO4J_PASSWORD; nada medido (≠ 'tudo bem')")
        return 2
    try:
        with drv.session() as s:
            lines, failures = report(s, installed=installed, only=only)
    finally:
        drv.close()
    print("\n".join(lines) if lines else "group_health: nenhum group no Bolt")
    print(f"\ngroup_health: {failures} falha(s) de critério")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
