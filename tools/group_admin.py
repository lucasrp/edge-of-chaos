"""group_admin — tenant surgery on a shared Bolt: migrate a group_id, bury a dead one (#634).

`group_id` IS identity. Changing `name`/`codename`/`graph_group` in agent.yaml does NOT migrate
the graph: the `n.group_id = $g` fence simply stops matching the past. Nothing is deleted, so
nothing looks broken — the agent just forgets, and the next backbone projection MERGEs a SECOND
`:Genesis` under the new name. Rename without migrate is a FORK (the fleet carries `peter tosh`
269 nodes / `petertosh` 2490 — one agent, two tenants), and a forked-off tenant is a tomb nobody
buries (the fleet's abandoned 476-node tenant).

`group_health` (#636) is the READ side of the same wound and owns the fleet verdicts — including
`leftovers()`, which names groups with no install on this host and nodes with no `group_id` at
all. This module is the WRITE side and does not re-decide any of that: `gc` prints
`group_health.leftovers` verbatim and adds only the per-group EVIDENCE (spine root, last
activity) that a delete decision needs and a read-only report has no reason to compute.

Both verbs are PLAN-FIRST:

    plan → print → apply(plan)

`*_plan` reads and returns a plain dict the CLI prints verbatim; `*_apply` re-derives its work
from THAT dict inside ONE write transaction and asserts, still inside the transaction, that what
it touched equals what the plan advertised. A graph that moved in between raises
`GroupAdminError`, rolling the transaction back — so "the dry-run listed exactly what the write
did" is enforced by the code, not promised by the docstring.

WHAT A RENAME MOVES. Node `group_id`, and RELATIONSHIP `group_id` — graphiti stamps the fence on
`MENTIONS`/`RELATES_TO`/`HAS_EPISODE`/`NEXT_EPISODE` too, and a migration that moved only nodes
would leave every extracted edge fenced into a dead tenant. Repo-projected edges (`SERVES`,
`ANCHORS`, `GROUNDS`, `CITES`…) carry no `group_id` and ride along with their endpoints.

WHAT A RENAME DOES WITH A COLLIDING SPINE. When both tenants own a spine — their own `:Genesis`,
their own `:Objective` — the migration is a MERGE, and the policy (operator, 2026-08-16) is that
THE DESTINATION'S SPINE WINS: `peter tosh` → `petertosh` keeps petertosh's Genesis and its six
Closavo Objectives, and the worthwhile-test spine that came with the 269 adopted nodes is
discarded. The policy exists, so the tool executes it — but never quietly. Discarding a declared
norte is printed as its own step in the dry-run, node by node with its body, and `--apply` needs
a second token (`--discard-source-spine`) beyond the retyped destination, because the keystroke
that destroys somebody's stated direction should not be the same keystroke that moves nodes.

And the leftovers of a discard are not orphans. Every edge that pointed at a discarded node is
REWIRED to that node's heir — the destination's node of the same label — whenever the heir is
unambiguous (one `:Genesis` on each side always is). Where the destination carries SEVERAL nodes
of the label (petertosh's six Objectives) there is no non-arbitrary heir, so those edges are
DROPPED, counted and listed by type in the plan: an edge invented toward a norte the operator did
not choose would be a fabrication, and the canonical sweep's own SERVES backfill and ANCHORS
rebuild are what re-attach the adopted corpus to the surviving spine. Trading duplication for
silent orphans would not be a fix; trading it for a printed, counted removal is.

WHAT GC REQUIRES BEFORE IT DELETES. After 2026-08-16 this is enforced rather than intended: the
delete leg once protected only *this* install's own group, which left every other unix user's
tenant on the shared Bolt one correctly-typed command from deletion — and that is how the live
`turing` tenant (141 nodes) was destroyed while this file was being exercised by hand. Burying a
tenant IS a supported operation — the fleet's abandoned 476-node tenant is meant to be buried —
but it now costs four independent, non-defaultable assertions: the group named in `--delete`, retyped in
`--confirm`, a `--stale-since DATE` that the group's own last activity must be strictly older
than, and — for any group holding a `:Genesis`, i.e. an identity root — an explicit
`--bury-rooted`. A group with no activity timestamp at all FAILS the staleness test rather than
passing it by default: absence of evidence is not evidence of death. The command that destroyed
`turing` is refused three times over by those rules.

Nodes with a NULL `group_id` are NOT this module's garbage and it never touches them. A node
written without a tenant stamp means some write-path is not stamping — a bug in the writer, not
dirt on the floor. `group_health.leftovers` LISTS them, which is diagnosis; deleting them would
destroy the evidence.
"""
import json
import re
import sys

# The identity root — a per-group singleton (publisher MERGEs it by group_id alone). Its presence
# is the tool's definition of "this group belongs to a living install".
SPINE_ROOT = "Genesis"

# Labels whose presence on BOTH sides makes a rename a MERGE rather than a migration. Genesis is
# identity; Objective is the norte. Colliding either is an editorial decision, never a mechanical
# one — see the module docstring.
SPINE_COLLISION_LABELS = (SPINE_ROOT, "Objective")

_NONWORD = re.compile(r"[^a-z0-9]+")


class GroupAdminError(RuntimeError):
    """A planned migration/collection could not be carried out as planned — never a partial write.

    Raised INSIDE the write transaction, so the driver rolls back: the graph is left exactly as
    the plan found it rather than half-migrated across two group ids."""


# ---------------------------------------------------------------- reads


def normalize_group(group):
    """The collation key that makes `peter tosh`, `Peter-Tosh` and `petertosh` one name.

    Two group ids that normalize alike are almost certainly one agent that got renamed without a
    migrate — the whole defect of #634. Used only to RAISE SUSPICION (fork_candidates); never to
    match or rewrite, because the fence itself is and stays byte-exact."""
    return _NONWORD.sub("", str(group or "").strip().lower())


def fork_candidates(inventory_rows):
    """Group-id pairs that normalize to the same name — one agent living in two tenants.

    Takes the rows `inventory()` returns (anything with a `group` key). Returns sorted pairs,
    smallest id first, so the caller can print a stable orientation."""
    buckets = {}
    for row in inventory_rows:
        g = row["group"] if isinstance(row, dict) else row
        buckets.setdefault(normalize_group(g), []).append(g)
    pairs = []
    for names in buckets.values():
        names = sorted(set(names))
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                pairs.append((a, b))
    return sorted(pairs)


def _one(runner, query, key, default=0, **params):
    row = runner.run(query, **params).single()
    if row is None:
        return default
    value = row[key]
    return default if value is None else value


def group_nodes(runner, group):
    return _one(runner, "MATCH (n) WHERE n.group_id=$g RETURN count(n) AS n", "n", g=group)


def group_rels(runner, group):
    """Relationships FENCED into the group (graphiti stamps group_id on the edge itself)."""
    return _one(runner, "MATCH ()-[r]->() WHERE r.group_id=$g RETURN count(r) AS n", "n", g=group)


def label_census(runner, group):
    rows = runner.run(
        "MATCH (n) WHERE n.group_id=$g "
        "RETURN head(labels(n)) AS label, count(n) AS n ORDER BY label", g=group).data()
    return {r["label"]: r["n"] for r in rows}


def spine_nodes(runner, group, label):
    """Every node of `label` under `group`, with its properties — the material of a collision
    report: the operator has to SEE the two nortes before choosing between them."""
    rows = runner.run(
        f"MATCH (n:`{label}`) WHERE n.group_id=$g "
        "RETURN elementId(n) AS id, properties(n) AS props ORDER BY elementId(n)",
        g=group).data()
    return [{"id": r["id"], "label": label, "props": dict(r["props"] or {})} for r in rows]


def last_activity(runner, group):
    """The newest timestamp anywhere in the group, as a string, or None.

    Coalesces what the tree actually writes (graphiti `created_at`, the projections'
    `projected_at`, episodic `valid_at`). Spine nodes carry none, so a group can legitimately
    have no timestamp — which the delete gate treats as NO EVIDENCE OF DEATH, never as death."""
    return _one(runner,
                "MATCH (n) WHERE n.group_id=$g "
                "RETURN max(toString(coalesce(n.projected_at, n.created_at, n.valid_at))) AS n",
                "n", default=None, g=group)


def inventory(runner):
    """Every group id in this Bolt with the EVIDENCE a delete decision needs.

    Deliberately narrow: `group_health.groups()`/`leftovers()` already own the census and the
    orphan verdicts, and this does not restate them. What it adds is `genesis` and
    `last_activity` — is anyone living here, and when did they last move."""
    rows = runner.run(
        "MATCH (n) WHERE n.group_id IS NOT NULL "
        "RETURN n.group_id AS group, count(n) AS nodes, "
        "count(CASE WHEN '" + SPINE_ROOT + "' IN labels(n) THEN 1 END) AS genesis, "
        "max(toString(coalesce(n.projected_at, n.created_at, n.valid_at))) AS last_activity "
        "ORDER BY nodes DESC").data()
    rels = {r["group"]: r["rels"] for r in runner.run(
        "MATCH ()-[r]->() WHERE r.group_id IS NOT NULL "
        "RETURN r.group_id AS group, count(r) AS rels").data()}
    return [{"group": r["group"], "nodes": r["nodes"], "genesis": r["genesis"],
             "last_activity": r.get("last_activity"), "rels": rels.get(r["group"], 0)}
            for r in rows]


# ---------------------------------------------------------------- the guard


def tenant_verdict(runner, group):
    """Does `group` OWN this Bolt's identity root, or is it about to mint a second one?

    Statuses, and what each means to an installer:

      owner        — the group holds its own `:Genesis`. Nothing to decide.
      forked       — the group holds a root AND a near-twin group id also holds one. The fork
                     ALREADY happened (`peter tosh` ~ `petertosh`); closing it is a MERGE, which
                     `rename` deliberately refuses to perform unattended.
      fork_suspect — the group is EMPTY while other groups on this Bolt own roots. Either this
                     phenotype was renamed without migrating, or a genuinely new tenant is being
                     installed beside an existing one. The graph cannot tell those apart, so the
                     verdict REFUSES and names the candidates: refusing is recoverable, minting a
                     second silent Genesis is not.
      unrooted     — the group already holds nodes but no root yet (the backbone simply has not
                     been projected). Advisory.
      fresh        — nothing anywhere. Advisory.

    `ok` is True/False/None matching _validate's check convention (None = advisory)."""
    genesis = {r["group"]: r["n"] for r in runner.run(
        f"MATCH (n:{SPINE_ROOT}) WHERE n.group_id IS NOT NULL "
        "RETURN n.group_id AS group, count(n) AS n").data()}
    mine = group_nodes(runner, group)
    others = sorted(g for g in genesis if g != group)
    twins = [b if a == group else a
             for a, b in fork_candidates(inventory(runner)) if group in (a, b)]

    if group in genesis:
        if twins:
            return {"status": "forked", "ok": False, "group": group, "candidates": twins,
                    "detail": "group %r and %s are the SAME name under two ids — one agent, two "
                              "tenants (#634). Both hold a spine, so closing this is a MERGE: run "
                              "`edge-group rename %r %r` to see the collision report, and decide "
                              "which spine survives before anything is migrated."
                              % (group, ", ".join(repr(t) for t in twins), twins[0], group)}
        return {"status": "owner", "ok": True, "group": group, "candidates": [],
                "detail": "group %r owns its :%s (%d nodes)" % (group, SPINE_ROOT, mine)}
    if mine > 0:
        return {"status": "unrooted", "ok": None, "group": group, "candidates": others,
                "detail": "group %r holds %d nodes but no :%s yet — the backbone projects on the "
                          "next canonical sweep" % (group, mine, SPINE_ROOT)}
    if not others:
        return {"status": "fresh", "ok": None, "group": group, "candidates": [],
                "detail": "group %r is empty and no other tenant owns a :%s — fresh install"
                          % (group, SPINE_ROOT)}
    return {
        "status": "fork_suspect", "ok": False, "group": group, "candidates": others,
        "detail": "group %r is EMPTY while %s already own a :%s on this Bolt. If this install "
                  "was RENAMED, migrate instead of forking: `edge-group rename %r %r`. If %r is "
                  "genuinely a new tenant, declare it (EDGE_NEW_TENANT=1) — but a second "
                  ":%s must never be minted silently (#634)."
                  % (group, ", ".join(repr(o) for o in others), SPINE_ROOT,
                     others[0], group, group, SPINE_ROOT)}


# ---------------------------------------------------------------- rename


_REL_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _incident_edges(runner, node_id):
    """Every relationship touching one node, as (type, direction, other-endpoint) rows.

    Read at PLAN time so the dry-run can print what a discard costs in edges. Neo4j has no
    portable dynamic-type CREATE, so the apply leg interpolates the type into the statement —
    which is only safe because a type read back from the graph is re-validated as an identifier
    before it ever reaches a query string."""
    rows = runner.run(
        "MATCH (v) WHERE elementId(v)=$id "
        "MATCH (v)-[r]-(o) "
        "RETURN type(r) AS type, "
        "CASE WHEN startNode(r)=v THEN 'out' ELSE 'in' END AS direction, "
        "elementId(o) AS other, count(*) AS n "
        "ORDER BY type, direction, other", id=node_id).data()
    return [dict(r) for r in rows]


def rename_plan(runner, old, new):
    """Read the whole migration — including everything it would destroy — before writing a byte.

    `blockers` is the refusal list: non-empty means `rename_apply` raises rather than runs.
    `collisions` details every spine label present on BOTH sides with each node's properties;
    `discards` is the source-side spine the destination's spine displaces, and `rewires` /
    `dropped` account for every single edge those discarded nodes carried. Nothing that the apply
    leg destroys is absent from this dict — that is the whole point of it existing."""
    old = (old or "").strip()
    new = (new or "").strip()
    blockers = []
    if not old or not new:
        blockers.append("both OLD and NEW group ids are required")
    if old and old == new:
        blockers.append("OLD and NEW are the same group id — nothing to migrate")

    nodes = group_nodes(runner, old) if old else 0
    rels = group_rels(runner, old) if old else 0
    if old and nodes == 0:
        blockers.append("group %r holds no nodes — nothing to migrate (check the spelling: the "
                        "fence is byte-exact)" % old)

    by_label = label_census(runner, old) if old else {}
    target_by_label = label_census(runner, new) if new else {}

    # A COLLISION is a label both tenants carry. Policy (operator, 2026-08-16): the DESTINATION's
    # spine wins. The source's copies become `discards`; each one's heir is the destination's node
    # of that label when there is exactly one, and None when the destination carries several —
    # petertosh's six Objectives admit no non-arbitrary heir, so those edges are dropped, not
    # invented onto a norte nobody chose.
    collisions, discards, heirs = {}, [], {}
    if old and new:
        for label in SPINE_COLLISION_LABELS:
            source = spine_nodes(runner, old, label)
            target = spine_nodes(runner, new, label)
            if not (source and target):
                continue
            collisions[label] = {"source": source, "target": target}
            heirs[label] = target[0]["id"] if len(target) == 1 else None
            discards.extend(source)

    victim_heir = {}
    for node in discards:
        victim_heir[node["id"]] = heirs.get(node["label"])

    rewires, dropped = [], []
    for node in discards:
        heir = victim_heir[node["id"]]
        for edge in _incident_edges(runner, node["id"]):
            # An endpoint that is ITSELF discarded resolves to its own heir, so the edge between
            # two displaced spine nodes lands between their two survivors instead of dangling.
            other = victim_heir.get(edge["other"], edge["other"])
            reason = None
            if heir is None:
                reason = ("the destination carries %d :%s — no unambiguous heir"
                          % (len(collisions[node["label"]]["target"]), node["label"]))
            elif other is None:
                reason = "the other endpoint is itself discarded and has no heir"
            elif other == heir:
                reason = "would become a self-loop on the heir"
            elif not _REL_TYPE.fullmatch(edge["type"] or ""):
                reason = "relationship type %r is not a safe identifier" % edge["type"]
            if reason:
                dropped.append(dict(edge, victim=node["id"], label=node["label"], reason=reason))
            else:
                rewires.append(dict(edge, victim=node["id"], label=node["label"],
                                    heir=heir, other=other))

    after = dict(target_by_label)
    for label, n in by_label.items():
        after[label] = after.get(label, 0) + n
    for node in discards:
        after[node["label"]] = after.get(node["label"], 0) - 1

    return {"old": old, "new": new, "nodes": nodes, "rels": rels, "by_label": by_label,
            "target_nodes": group_nodes(runner, new) if new else 0,
            "target_rels": group_rels(runner, new) if new else 0,
            "target_by_label": target_by_label, "collisions": collisions,
            "discards": discards, "heirs": heirs, "rewires": rewires, "dropped": dropped,
            "after_by_label": {k: v for k, v in sorted(after.items())}, "blockers": blockers}


def rename_apply(session, plan):
    """Execute `plan` in ONE write transaction, or leave the graph untouched.

    Order matters: move the tenant, rewire the edges of every displaced spine node onto its heir,
    then delete the displaced nodes (which takes their remaining, explicitly-listed edges with
    them). Every step re-counts what it touched and compares against the plan BEFORE the
    transaction commits; a mismatch raises `GroupAdminError` inside the transaction, so the
    driver rolls the whole migration back. That is what makes "atomic" more than a word: there is
    no state in which half a tenant lives under the old id and half under the new one, and no
    state in which a spine was discarded but its corpus never arrived."""
    if plan.get("blockers"):
        raise GroupAdminError("refusing to migrate: " + "; ".join(plan["blockers"]))
    old, new = plan["old"], plan["new"]
    discard_ids = [d["id"] for d in plan.get("discards") or []]
    rewires = plan.get("rewires") or []

    def _tx(tx):
        moved_nodes = _one(tx, "MATCH (n) WHERE n.group_id=$old SET n.group_id=$new "
                               "RETURN count(n) AS n", "n", old=old, new=new)
        moved_rels = _one(tx, "MATCH ()-[r]->() WHERE r.group_id=$old SET r.group_id=$new "
                              "RETURN count(r) AS n", "n", old=old, new=new)
        if moved_nodes != plan["nodes"] or moved_rels != plan["rels"]:
            raise GroupAdminError(
                "the graph changed under the plan (planned %d nodes / %d rels, moved %d / %d) — "
                "rolled back; re-run the dry-run" % (plan["nodes"], plan["rels"],
                                                     moved_nodes, moved_rels))

        rewired = 0
        for edge in rewires:
            kind = edge["type"]
            if not _REL_TYPE.fullmatch(kind or ""):      # re-validated at the write, not trusted
                raise GroupAdminError("unsafe relationship type in plan: %r" % kind)
            pattern = ("(h)-[:`%s`]->(o)" if edge["direction"] == "out"
                       else "(h)<-[:`%s`]-(o)") % kind
            rewired += _one(
                tx, "MATCH (h) WHERE elementId(h)=$heir MATCH (o) WHERE elementId(o)=$other "
                    f"MERGE {pattern} RETURN count(*) AS n", "n",
                heir=edge["heir"], other=edge["other"])

        discarded = 0
        if discard_ids:
            discarded = _one(tx, "MATCH (n) WHERE elementId(n) IN $ids AND n.group_id=$new "
                                 "WITH collect(n) AS victims, count(n) AS c "
                                 "FOREACH (v IN victims | DETACH DELETE v) "
                                 "RETURN c AS n", "n", ids=discard_ids, new=new)
            if discarded != len(discard_ids):
                raise GroupAdminError(
                    "planned to discard %d displaced spine node(s), found %d — rolled back"
                    % (len(discard_ids), discarded))

        left = _one(tx, "MATCH (n) WHERE n.group_id=$old RETURN count(n) AS n", "n", old=old)
        roots = _one(tx, f"MATCH (n:{SPINE_ROOT}) WHERE n.group_id=$new RETURN count(n) AS n",
                     "n", new=new)
        if left != 0:
            raise GroupAdminError(
                "group %r still holds %d nodes after the migration — rolled back" % (old, left))
        if roots > 1:
            raise GroupAdminError(
                "group %r would end with %d :%s — a migration must leave ONE identity root; "
                "rolled back" % (new, roots, SPINE_ROOT))
        return {"old": old, "new": new, "moved_nodes": moved_nodes, "moved_rels": moved_rels,
                "discarded": discarded, "rewired": rewired,
                "dropped_edges": len(plan.get("dropped") or []), "spine_roots": roots}

    return session.execute_write(_tx)


# ---------------------------------------------------------------- gc


def gc_plan(runner, group, stale_since=None, bury_rooted=False):
    """Everything a delete of `group` would remove, plus every reason not to.

    The blockers are the lesson of 2026-08-16, when this tool deleted a live tenant belonging to
    another unix user. Burying a genuinely dead tenant IS supported — the fleet's abandoned
    476-node tenant is meant to be buried — but each assertion has to be made separately, and
    none of them defaults to yes:

      * `stale_since` — a DATE the caller asserts, which the group's own last activity must be
        strictly older than. A group with no timestamp at all FAILS: absence of evidence is not
        evidence of death.
      * `bury_rooted` — required when the group holds a `:%s`, because an identity root means an
        install claimed this tenant. On a shared Bolt that is very possibly another user's agent,
        and the operator has to say out loud that they mean to destroy it.

    `group` is always a named tenant: nodes with a NULL `group_id` are never a target here (they
    are a write-path bug to diagnose, not garbage to collect).
    """ % SPINE_ROOT
    group = (group or "").strip()
    blockers = [] if group else ["a group id is required"]
    nodes = group_nodes(runner, group) if group else 0
    if group and nodes == 0:
        blockers.append("group %r holds no nodes — nothing to collect" % group)
    roots = len(spine_nodes(runner, group, SPINE_ROOT)) if group else 0
    seen = last_activity(runner, group) if group else None

    if roots and not bury_rooted:
        blockers.append(
            "group %r holds %d :%s — an identity root means an install claimed this tenant (on a "
            "shared Bolt, very possibly another user's). Burying it needs --bury-rooted said out "
            "loud, on top of --confirm and --stale-since." % (group, roots, SPINE_ROOT))
    if not stale_since:
        blockers.append(
            "no staleness evidence: pass --stale-since YYYY-MM-DD and the group's last activity "
            "must be strictly older than that date")
    elif seen is None:
        blockers.append(
            "group %r has no activity timestamp at all — staleness cannot be established, and "
            "absence of evidence is not evidence of death" % group)
    elif str(seen) >= str(stale_since):
        blockers.append(
            "group %r moved at %s, which is not older than --stale-since %s"
            % (group, seen, stale_since))

    # Every relationship incident to those nodes dies with them, including edges carrying no
    # group_id of their own (the repo-projected spine) — so count by INCIDENCE, not by fence.
    rels = _one(runner, "MATCH (n)-[r]-() WHERE n.group_id=$g RETURN count(DISTINCT r) AS n",
                "n", g=group) if group else 0
    return {"group": group, "nodes": nodes, "rels": rels,
            "by_label": label_census(runner, group) if group else {},
            "spine_roots": roots, "last_activity": seen, "stale_since": stale_since,
            "bury_rooted": bool(bury_rooted), "blockers": blockers}


def gc_apply(session, plan):
    """Delete exactly the plan, in one transaction, or delete nothing.

    The delete counts its own casualties and compares them with the plan before committing, so
    the property the dry-run promises ("this is what would go") is verified against the write
    itself rather than re-derived by the same code twice."""
    if plan.get("blockers"):
        raise GroupAdminError("refusing to collect: " + "; ".join(plan["blockers"]))
    group = plan["group"]

    def _tx(tx):
        rels = _one(tx, "MATCH (n)-[r]-() WHERE n.group_id=$g RETURN count(DISTINCT r) AS n",
                    "n", g=group)
        deleted = _one(tx, "MATCH (n) WHERE n.group_id=$g "
                           "WITH collect(n) AS victims, count(n) AS c "
                           "FOREACH (v IN victims | DETACH DELETE v) "
                           "RETURN c AS n", "n", g=group)
        if deleted != plan["nodes"] or rels != plan["rels"]:
            raise GroupAdminError(
                "the graph changed under the plan (planned %d nodes / %d rels, found %d / %d) — "
                "NOTHING deleted; re-run the dry-run"
                % (plan["nodes"], plan["rels"], deleted, rels))
        left = _one(tx, "MATCH (n) WHERE n.group_id=$g RETURN count(n) AS n", "n", g=group)
        if left != 0:
            raise GroupAdminError("group %r still holds %d nodes — rolled back" % (group, left))
        return {"group": group, "deleted_nodes": deleted, "deleted_rels": rels}

    return session.execute_write(_tx)


# ---------------------------------------------------------------- CLI


def _props(node):
    return json.dumps({k: v for k, v in node["props"].items()
                       if k not in ("group_id", "name_embedding")},
                      sort_keys=True, ensure_ascii=False)[:160]


def _render_rename(plan):
    out = ["rename plan: %r → %r" % (plan["old"], plan["new"]),
           "  source: %d nodes, %d fenced relationships" % (plan["nodes"], plan["rels"]),
           "  target (before): %d nodes, %d fenced relationships"
           % (plan["target_nodes"], plan["target_rels"])]
    for label, n in sorted(plan["by_label"].items()):
        out.append("    move  %-14s %d" % (label, n))
    for label, sides in sorted(plan["collisions"].items()):
        out.append("  SPINE COLLISION on :%s — both tenants carry one. Policy: the DESTINATION's "
                   "spine survives." % label)
        for node in sides["target"]:
            out.append("    KEEP    %r  %s" % (plan["new"], _props(node)))
        for node in sides["source"]:
            out.append("    DISCARD %r  %s" % (plan["old"], _props(node)))
    if plan["discards"]:
        out.append("  discarding %d source spine node(s): %s"
                   % (len(plan["discards"]),
                      ", ".join(sorted({d["label"] for d in plan["discards"]}))))
        by_kind = {}
        for e in plan["rewires"]:
            by_kind[e["type"]] = by_kind.get(e["type"], 0) + 1
        out.append("    rewire onto the surviving spine: "
                   + (", ".join("%s×%d" % kv for kv in sorted(by_kind.items())) or "none"))
        dropped = {}
        for e in plan["dropped"]:
            dropped.setdefault((e["type"], e["reason"]), 0)
            dropped[(e["type"], e["reason"])] += 1
        for (kind, reason), n in sorted(dropped.items()):
            out.append("    DROP %s ×%d — %s" % (kind, n, reason))
        if not plan["dropped"]:
            out.append("    drop: none — every edge found an heir")
    out.append("  target (after): " + ", ".join(
        "%s=%d" % (k, v) for k, v in plan["after_by_label"].items()))
    for b in plan["blockers"]:
        out.append("  BLOCKED: " + b)
    return "\n".join(out)


def _render_gc(rows, leftover_lines, forks, stale_only, live):
    out = ["groups on this Bolt (evidence for a delete decision):"]
    for r in rows:
        rooted = r["genesis"] > 0
        tag = "LIVE(self)" if r["group"] == live else ("rooted" if rooted else "unrooted")
        if stale_only and (rooted or r["group"] == live):
            continue
        out.append("  [%-10s] %-28s %6d nodes %5d rels  genesis=%d  last=%s"
                   % (tag, r["group"], r["nodes"], r["rels"], r["genesis"],
                      r["last_activity"] or "-"))
    out.append("group_health.leftovers (#636 — groups with no install here, ungrouped nodes):")
    out.extend("  [%s] %s" % (sev, msg) for sev, msg in leftover_lines)
    if not leftover_lines:
        out.append("  (none)")
    for a, b in forks:
        out.append("FORK SUSPECT: %r and %r are the same name under two ids — "
                   "`edge-group rename %r %r` reports the collision (#634)" % (a, b, a, b))
    out.append("nothing above was deleted. Burying one group takes --delete G --confirm G "
               "--stale-since YYYY-MM-DD (plus --bury-rooted when it holds a :%s). Ungrouped "
               "nodes are listed as DIAGNOSIS — a write-path that does not stamp a tenant is a "
               "bug to fix, never garbage for this tool to collect." % SPINE_ROOT)
    return "\n".join(out)


def _live_group():
    try:
        import _identity
        return _identity.group()
    except Exception:                                    # noqa: BLE001 — CLI must still list
        return None


def _open_session():
    import _identity
    from neo4j import GraphDatabase
    uri, user, pw = _identity.neo4j_conn()
    if not pw:
        raise GroupAdminError("no EDGE_NEO4J_PASSWORD — cannot reach the graph (CONTRACT C4)")
    return GraphDatabase.driver(uri, auth=(user, pw)).session()


def main(argv=None, session=None, live_group=None):
    """`edge-group` — the CLI. `--dry-run` is the DEFAULT for every verb; the write legs need the
    destination retyped in `--confirm`. `session`/`live_group` are injected by the tests."""
    import argparse
    ap = argparse.ArgumentParser(
        prog="edge-group",
        description="Migrate a graph tenant (group_id) and collect dead ones (#634).")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rename", help="migrate every node/edge from OLD group_id to NEW")
    r.add_argument("old")
    r.add_argument("new")
    r.add_argument("--dry-run", action="store_true", default=True,
                   help="print the plan and write nothing (the DEFAULT)")
    r.add_argument("--apply", action="store_true",
                   help="execute the plan (requires --confirm NEW)")
    r.add_argument("--confirm", default=None,
                   help="retype the NEW group id to authorize the write")
    r.add_argument("--discard-source-spine", action="store_true",
                   help="acknowledge that the source's colliding :%s/:Objective are DESTROYED "
                        "(the destination's spine wins). Required whenever the plan lists a "
                        "DISCARD; moving nodes and destroying a declared norte must not be the "
                        "same keystroke." % SPINE_ROOT)

    g = sub.add_parser("gc", help="list groups and ungrouped nodes; delete one, explicitly")
    g.add_argument("--stale", action="store_true",
                   help="list only unrooted groups (a rooted one is never a delete candidate)")
    g.add_argument("--keep", action="append", default=[],
                   help="a group id that IS live (repeatable) — protects it from --delete")
    g.add_argument("--delete", default=None, metavar="GROUP",
                   help="delete ONE group (requires --confirm GROUP and --stale-since). "
                        "Never a batch, and never a group holding a :" + SPINE_ROOT)
    g.add_argument("--confirm", default=None,
                   help="retype the group id to authorize the delete")
    g.add_argument("--stale-since", default=None, metavar="YYYY-MM-DD",
                   help="assert the group has not moved since this date; the group's own last "
                        "activity must be strictly older, or the delete is refused")
    g.add_argument("--bury-rooted", action="store_true",
                   help="acknowledge that the group holds a :%s — an install claimed this "
                        "tenant, and you mean to destroy it anyway" % SPINE_ROOT)

    sub.add_parser("list", help="alias for `gc` without the staleness filter")

    args = ap.parse_args(argv)
    live = live_group if live_group is not None else _live_group()
    own = session is None
    if own:
        session = _open_session()
    try:
        if args.cmd == "rename":
            plan = rename_plan(session, args.old, args.new)
            print(json.dumps(plan, indent=2, default=str) if args.json else _render_rename(plan))
            if not args.apply:
                if not plan["blockers"]:
                    print("dry-run (default). To execute: --apply --confirm %r" % plan["new"])
                return 0
            if plan["blockers"]:
                print("refused — see BLOCKED above", file=sys.stderr)
                return 2
            if args.confirm != plan["new"]:
                print("refused: --apply needs --confirm %r (retype the DESTINATION group id)"
                      % plan["new"], file=sys.stderr)
                return 2
            if plan["discards"] and not args.discard_source_spine:
                print("refused: this plan DISCARDS %d source spine node(s) — pass "
                      "--discard-source-spine to authorize destroying them (see the DISCARD "
                      "lines above)" % len(plan["discards"]), file=sys.stderr)
                return 2
            result = rename_apply(session, plan)
            print(json.dumps(result, indent=2) if args.json
                  else "migrated: %d nodes, %d relationships → %r "
                       "(%d spine discarded, %d edges rewired, %d dropped)"
                       % (result["moved_nodes"], result["moved_rels"], result["new"],
                          result["discarded"], result["rewired"], result["dropped_edges"]))
            return 0

        keep = list(getattr(args, "keep", []))
        target = getattr(args, "delete", None)
        # `is not None`, never truthiness: `--delete ''` must land in the REFUSAL path (gc_plan
        # blocks a blank group id), not fall through to the harmless listing. gc's target is
        # always a NAMED tenant — ungrouped nodes are a write-path bug to diagnose, and there is
        # deliberately no way to aim this verb at them.
        if target is not None:
            plan = gc_plan(session, target, stale_since=getattr(args, "stale_since", None),
                           bury_rooted=bool(getattr(args, "bury_rooted", False)))
            print(json.dumps(plan, indent=2, default=str) if args.json else
                  "gc plan: %r → %d nodes, %d relationships (%s)"
                  % (plan["group"], plan["nodes"], plan["rels"],
                     ", ".join("%s=%d" % kv for kv in sorted(plan["by_label"].items())) or "-"))
            if plan["blockers"]:
                print("refused: " + "; ".join(plan["blockers"]), file=sys.stderr)
                return 2
            if target == live or target in keep:
                print("refused: %r is a LIVE group (this install's own, or named by --keep)"
                      % target, file=sys.stderr)
                return 2
            if args.confirm != target:
                print("refused: --delete needs --confirm %r (retype the group id)" % target,
                      file=sys.stderr)
                return 2
            result = gc_apply(session, plan)
            print(json.dumps(result, indent=2) if args.json
                  else "collected: %d nodes, %d relationships under %r"
                       % (result["deleted_nodes"], result["deleted_rels"], result["group"]))
            return 0

        import group_health
        inv = inventory(session)
        installed = {g for g in [live] + keep if g}
        leftover_lines = group_health.leftovers(session, installed)
        forks = fork_candidates(inv)
        if args.json:
            print(json.dumps({"groups": inv, "leftovers": leftover_lines, "forks": forks,
                              "live": live}, indent=2, default=str))
        else:
            print(_render_gc(inv, leftover_lines, forks, getattr(args, "stale", False), live))
        return 0
    finally:
        if own:
            session.close()


if __name__ == "__main__":                               # pragma: no cover — shim entry
    sys.exit(main())
