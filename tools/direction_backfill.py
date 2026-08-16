"""direction_backfill — give the Directions already in the graph a HANDLE (#632, part 4).

The fleet read of 2026-08-16 found 788 `:Direction` nodes in `roberto` and 577 in `petertosh`,
each carrying only a `body`. The write path now REQUIRES a title (eventlog.propose /
eventlog.set_direction), but that binds new writes only: the nodes already out there stay
unreadable until something names them. This is that something.

The rule, and its honesty clause: the title is DERIVED from the first sentence of the body
(`eventlog.derive_direction_title`) and every node it touches is stamped `title_generated = true`.
A derived handle is a legible placeholder for a steer nobody named — never a claim that somebody
named it. The grill can find every one of them with

    MATCH (d:Direction {group_id: $g}) WHERE d.title_generated RETURN d.title, d.body

and replace them with authored ones. `title_generated` is what keeps the backfill from laundering
machine guesses into curated memory.

DRY-RUN IS THE DEFAULT (BRIEF rule 3). `plan()` reads and returns what WOULD change; `apply()`
writes, and only when a caller asks for it explicitly. Nothing here deletes or merges a node: a
title is ADDED where there is none. A node that already has a title is never touched, so the tool
is idempotent and safe to re-run.

    tools/edge-python -m direction_backfill                 # dry-run, the plan
    tools/edge-python -m direction_backfill --apply         # write the derived titles
    tools/edge-python -m direction_backfill --group other   # a specific group (default: this host)

Out of scope, deliberately: DEDUPING the 788. The nodes are MERGE'd by body, so two rewordings of
one steer are two nodes, and collapsing them is a destructive migration that needs a human ruling
on which body survives. This tool makes the pile READABLE first — that is the input that ruling
needs, and it is the part that is safe to run unattended.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import communities  # noqa: E402
import eventlog  # noqa: E402

# Read every Direction in the group that has no usable handle yet. `coalesce(d.title,'') = ''`
# catches both the absent property and a blank one; a node whose title was already authored (or
# already backfilled) is out of the result set, which is what makes a re-run a no-op.
# The node is addressed by (group_id, body) — the same key the projection MERGEs on, so it is
# unique by construction and needs no internal node id (id() is deprecated, elementId() is not
# available on every Neo4j the fleet runs; the property key works on both).
UNTITLED_QUERY = (
    "MATCH (d:Direction {group_id:$g}) WHERE coalesce(d.title,'') = '' "
    "RETURN d.body AS node_id, d.id AS direction_id, d.body AS body "
    "ORDER BY coalesce(d.id,''), d.body")
COUNT_QUERY = (
    "MATCH (d:Direction {group_id:$g}) "
    "RETURN count(d) AS total, "
    "count(CASE WHEN coalesce(d.title,'') <> '' THEN 1 END) AS titled, "
    "count(CASE WHEN d.title_generated THEN 1 END) AS derived, "
    "count(CASE WHEN coalesce(d.expires_at,'') <> '' THEN 1 END) AS with_expiry")
# The write. `title_generated` rides with the title in the SAME SET so the two can never come
# apart — a title in the graph without its provenance mark would read as authored.
BACKFILL_QUERY = (
    "MATCH (d:Direction {group_id:$g, body:$node_id}) WHERE coalesce(d.title,'') = '' "
    "SET d.title = $title, d.title_generated = true "
    "RETURN d.body AS node_id")


def _group(group=None):
    if group:
        return group
    import _identity
    return _identity.require_group()  # fail-loud: never guess another tenant's group (ADR-0015)


def survey(group=None, driver=None):
    """Read-only census of the group's Directions: how many there are, how many carry a handle,
    how many of those handles are derived, how many declare an end. This is the number #632 is
    about — run it before and after."""
    g = _group(group)
    drv = driver or communities._driver()
    if drv is None:
        raise RuntimeError("no Neo4j driver — cannot survey (check EDGE_NEO4J_* / secrets)")
    with drv.session() as s:
        row = dict(s.run(COUNT_QUERY, g=g).single())
    row["group"] = g
    return row


def plan(group=None, driver=None):
    """DRY-RUN: what a backfill WOULD write, as a list of {node_id, direction_id, body, title}.
    Reads only. A node whose body yields no derivable title (empty/whitespace) is reported with
    `title=None` and would be SKIPPED — the tool never invents a handle out of nothing."""
    g = _group(group)
    drv = driver or communities._driver()
    if drv is None:
        raise RuntimeError("no Neo4j driver — cannot plan (check EDGE_NEO4J_* / secrets)")
    with drv.session() as s:
        rows = [dict(r) for r in s.run(UNTITLED_QUERY, g=g)]
    for r in rows:
        r["title"] = eventlog.derive_direction_title(r.get("body"))
    return rows


def apply(group=None, driver=None, rows=None):
    """WRITE the derived titles, each stamped `title_generated = true`. Additive only — no node is
    deleted, merged or reworded, and the guard in BACKFILL_QUERY re-checks emptiness at write time
    so a concurrent authored title is never overwritten. Returns the number of nodes titled."""
    g = _group(group)
    drv = driver or communities._driver()
    if drv is None:
        raise RuntimeError("no Neo4j driver — cannot apply (check EDGE_NEO4J_* / secrets)")
    rows = plan(group=g, driver=drv) if rows is None else rows
    written = 0
    with drv.session() as s:
        for r in rows:
            if not r.get("title"):
                continue  # nothing derivable — leave it, an empty handle is worse than none
            if s.run(BACKFILL_QUERY, g=g, node_id=r["node_id"], title=r["title"]).single():
                written += 1
    return written


def main(argv=None, driver=None, echo=print):
    """The CLI. `driver`/`echo` are injection seams so the whole dry-run/apply decision is testable
    against a fake graph — the one decision in this file that must never be wrong is "did a bare
    run write anything?", and that is not a question to answer by reading the source."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--group", default=None, help="group_id (default: this host's identity)")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE the derived titles (default is a dry-run plan)")
    ap.add_argument("--limit", type=int, default=20, help="rows to print in the plan")
    args = ap.parse_args(argv)

    census = survey(group=args.group, driver=driver)
    echo(f"group {census['group']}: {census['total']} Direction(s), {census['titled']} with a "
         f"handle ({census['derived']} derived), {census['with_expiry']} with a declared end")
    rows = plan(group=args.group, driver=driver)
    derivable = [r for r in rows if r.get("title")]
    echo(f"{len(rows)} without a handle; {len(derivable)} have a derivable one")
    for r in rows[:args.limit]:
        mark = r["title"] or "<NO DERIVABLE TITLE — skipped>"
        echo(f"  {r.get('direction_id') or '(no id)'}: {mark}")
    if len(rows) > args.limit:
        echo(f"  ... {len(rows) - args.limit} more")
    if not args.apply:
        echo("\nDRY-RUN — nothing written. Re-run with --apply to write these titles "
             "(each marked title_generated=true).")
        return 0
    written = apply(group=args.group, driver=driver, rows=rows)
    echo(f"\napplied: {written} node(s) titled (title_generated=true)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
