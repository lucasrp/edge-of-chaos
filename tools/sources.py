"""sources — the agent.yaml `sources[].interfaces[]` / `acts:` loader (grounding S3, E3).

The freeform per-source `via` seam is superseded by a structured, READ-ONLY `interfaces[]` list:
`{interface_id, via, idiom?, canary?, dry_semantics?, secret_ref?, installed?}` — one seam, two
projections (design-emissao §2): the harvester's recognizers derive from `interfaces[].via` (S4),
the predispatch canary battery from `interfaces[].canary` (S5). Writes to the world live in a
separate top-level `acts:` section (HITL-only — E1.3/R1.3) that the harvester NEVER reads: no
recognizer is ever derived from an act, so an upload can never masquerade as a read.

Posture: DOCTOR-STYLE, warning-collecting, never raising (sibling of _validate, not of the
briefing's fail-closed identity gate — the briefing keeps its own floor). Findings are
`{"level": "warning"|"error", "where": ..., "msg": ...}`:

  - source without `interfaces:`  → WARNING (legacy tolerated, degradation DECLARED — the roadmap
    floor still renders from the prose description; no recognizer derives from it);
  - act smuggled into `sources:` (source `hitl:`/`act:` truthy, or an interface `mode: write` /
    `hitl:` truthy) → ERROR collected; an act-shaped SOURCE is dropped from the read roster
    entirely (interfaces never validated), a write INTERFACE never enters the read-only list —
    no write via exits by any path;
  - interface declared without its key installed (`installed: false`) → WARNING — a VISIBLE dead
    leg (the /sources panel shows it, S7), kept in the list so it never silently disappears;
  - malformed entries (no interface_id/via, duplicate ids, non-dict shapes) → ERROR, entry dropped,
    the rest of the roster survives.

Pure core (`validate_sources`/`validate_acts` over a parsed dict) + thin file-reading wrappers
(`load_sources`/`load_acts`), so tests and future callers can use either.

`parse_roadmap` is the read side of `state/source-roadmap.md` (the machine-readable skeleton this
slice ships): per-source sections (`## <id> — ...`), bold-key bullets (seed / idiom / canary /
dry_semantics / intent priors / yield notes), and dated yield rows carrying provenance
(`- YYYY-MM-DD [seed:loopR-...] text`). S7's never-blank seed lines come from here.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
import _identity as _id_state
AGENT_YAML = _id_state.identity_path("agent.yaml")
ROADMAP = _id_state.runtime_root() / "state" / "source-roadmap.md"

# The measured dry-semantics vocabulary (R2.5 / design-emissao B1). An unknown value is a WARNING
# with the raw value kept visible — never silently normalized (the fold must see what was declared).
DRY_SEMANTICS = ("real", "never-dry", "false-dry-prone")

_IFACE_OPTIONAL = ("idiom", "canary", "dry_semantics", "secret_ref", "hit_count")


def _finding(level, where, msg):
    return {"level": level, "where": where, "msg": msg}


def _is_act_shaped(entry):
    """An act smuggled where a read belongs: explicit hitl/act flag, or a write-mode interface."""
    return bool(entry.get("hitl") or entry.get("act"))


def _validate_interface(raw, where, findings, seen_ids):
    """One interfaces[] entry → normalized dict or None (dropped, finding collected)."""
    if not isinstance(raw, dict):
        findings.append(_finding("error", where, f"interface entry is not a mapping: {raw!r}"))
        return None
    iid, via = raw.get("interface_id"), raw.get("via")
    if not isinstance(iid, str) or not iid.strip() or not isinstance(via, str) or not via.strip():
        findings.append(_finding(
            "error", where,
            f"interface missing interface_id/via (both required non-empty strings): {raw!r}"))
        return None
    iid = iid.strip()
    if iid in seen_ids:
        findings.append(_finding("error", where, f"duplicate interface_id {iid!r}"))
        return None
    if raw.get("mode") == "write" or _is_act_shaped(raw):
        findings.append(_finding(
            "error", where,
            f"interface {iid!r} is an act (write/HITL) inside sources — acts belong in the "
            "top-level `acts:` section; the harvester never reads acts (E3/R1.3)"))
        return None
    iface = {"interface_id": iid, "via": via.strip(),
             "installed": raw.get("installed", True) is not False}
    for k in _IFACE_OPTIONAL:
        iface[k] = raw.get(k)
    ds = iface["dry_semantics"]
    if ds is not None and ds not in DRY_SEMANTICS:
        findings.append(_finding(
            "warning", where,
            f"interface {iid!r} declares unknown dry_semantics {ds!r} "
            f"(measured vocabulary: {', '.join(DRY_SEMANTICS)}) — value kept visible"))
    canary = iface["canary"]
    if canary is not None:
        if not isinstance(canary, dict):
            findings.append(_finding("warning", where,
                                     f"interface {iid!r} canary is not a mapping — unusable by "
                                     "the canary battery (S5)"))
        elif not (canary.get("query") or canary.get("params")):
            findings.append(_finding("warning", where,
                                     f"interface {iid!r} canary carries neither query nor params"))
    if not iface["installed"]:
        findings.append(_finding(
            "warning", where,
            f"interface {iid!r} declared WITHOUT its key installed — dead leg, kept visible "
            "(flips when the key lands; the /sources panel shows it)"))
    seen_ids.add(iid)
    return iface


def validate_sources(cfg):
    """Pure core: parsed agent.yaml dict → (sources, findings). Each returned source is the
    original mapping plus a normalized `interfaces` list (possibly [] — legacy, warned)."""
    findings = []
    raw = (cfg or {}).get("sources")
    if not raw:
        findings.append(_finding("error", "sources", "agent.yaml declares no sources"))
        return [], findings
    if not isinstance(raw, list):
        findings.append(_finding("error", "sources",
                                 f"`sources` is not a list ({type(raw).__name__})"))
        return [], findings
    out = []
    for s in raw:
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not s["name"].strip():
            findings.append(_finding("error", "sources",
                                     f"malformed source entry (needs a name): {s!r}"))
            continue
        name = s["name"].strip()
        where = f"sources.{name}"
        if _is_act_shaped(s):
            # DROPPED from the return, not degraded to interfaces:[] — an act inside sources is a
            # CATEGORY error, not a thin read: this list IS the read roster everything downstream
            # consumes (S4 recognizers, S5 canary battery, S7 roadmap floor), and no via of an
            # act-shaped entry may exit as read-only by any path (E3/R1.3). Its interfaces are
            # never validated (a write leg must not leak); the error finding is the visible trace.
            findings.append(_finding(
                "error", where,
                f"source {name!r} is act-shaped (hitl/act flag) inside sources — acts belong in "
                "the top-level `acts:` section; the harvester never reads acts (E3/R1.3); "
                "entry dropped from the read roster"))
            continue
        src = dict(s)
        raw_ifaces = s.get("interfaces")
        ifaces, seen = [], set()
        if raw_ifaces is None or raw_ifaces == []:
            findings.append(_finding(
                "warning", where,
                f"source {name!r} declared without structured interfaces — legacy tolerated, "
                "degradation declared: no recognizer derives from it (S4); roadmap floor renders "
                "from its prose description only"))
        elif not isinstance(raw_ifaces, list):
            findings.append(_finding("error", where,
                                     f"`interfaces` is not a list ({type(raw_ifaces).__name__})"))
        else:
            for ri in raw_ifaces:
                iface = _validate_interface(ri, where, findings, seen)
                if iface is not None:
                    ifaces.append(iface)
        src["interfaces"] = ifaces
        out.append(src)
    return out, findings


def validate_acts(cfg):
    """Pure core: parsed agent.yaml dict → (acts, findings). Acts are HITL-only external-state
    WRITES (R1.3) — a separate book: never returned by validate_sources, never harvested. An act
    without `hitl: true` is flagged (the boundary must be explicit); one without name/via drops."""
    findings = []
    raw = (cfg or {}).get("acts")
    if raw is None:
        return [], findings                       # no acts section is a fine install
    if not isinstance(raw, list):
        findings.append(_finding("error", "acts", f"`acts` is not a list ({type(raw).__name__})"))
        return [], findings
    out = []
    for a in raw:
        if (not isinstance(a, dict) or not isinstance(a.get("name"), str) or not a["name"].strip()
                or not isinstance(a.get("via"), str) or not a["via"].strip()):
            findings.append(_finding("error", "acts",
                                     f"malformed act entry (needs name + via): {a!r}"))
            continue
        act = dict(a)
        act["hitl"] = a.get("hitl") is True
        if not act["hitl"]:
            findings.append(_finding(
                "warning", f"acts.{act['name']}",
                f"act {act['name']!r} without explicit `hitl: true` — acts are HITL-only by "
                "definition (R1.3); declare the boundary"))
        out.append(act)
    return out, findings


def _read_cfg(agent_yaml, findings):
    import yaml
    p = Path(agent_yaml)
    if not p.exists():
        findings.append(_finding("error", str(p), "agent.yaml absent"))
        return None
    try:
        return yaml.safe_load(p.read_text()) or {}
    except Exception as e:                        # doctor-style: a broken yaml is a finding
        findings.append(_finding("error", str(p), f"agent.yaml unparseable: {e}"))
        return None


def load_sources(agent_yaml=AGENT_YAML):
    """(sources, findings) from the agent.yaml on disk — warning-collecting, never raising."""
    findings = []
    cfg = _read_cfg(agent_yaml, findings)
    if cfg is None:
        return [], findings
    srcs, more = validate_sources(cfg)
    return srcs, findings + more


def load_acts(agent_yaml=AGENT_YAML):
    """(acts, findings) from the agent.yaml on disk — warning-collecting, never raising."""
    findings = []
    cfg = _read_cfg(agent_yaml, findings)
    if cfg is None:
        return [], findings
    acts, more = validate_acts(cfg)
    return acts, findings + more


# --- source-roadmap.md, the read side -----------------------------------------------------------

_SECTION_RE = re.compile(r"^## +([A-Za-z0-9_-]+) +—", re.M)
_FIELD_RE = re.compile(r"^- \*\*([^*]+)\*\*")
_YIELD_RE = re.compile(r"^\s*- (\d{4}-\d{2}-\d{2}) \[([^\]]+)\] ?(.*)$")


def parse_roadmap(text):
    """The machine-readable skeleton of state/source-roadmap.md → per-source dict:
    {source_id: {"fields": {key: value-with-continuations}, "yield_notes":
    [{"date", "provenance", "text"}]}}. Lenient by design (a standing page humans also edit):
    sections are `## <id> — ...` headers; fields are `- **key** ...: value` bullets whose
    indented continuation lines join in; yield rows are dated `[provenance]` list items."""
    out = {}
    matches = list(_SECTION_RE.finditer(text))
    for n, m in enumerate(matches):
        body = text[m.end():matches[n + 1].start() if n + 1 < len(matches) else len(text)]
        fields, notes, current = {}, [], None
        for line in body.splitlines():
            ym = _YIELD_RE.match(line)
            if ym:
                notes.append({"date": ym.group(1), "provenance": ym.group(2),
                              "text": ym.group(3).strip()})
                continue
            fm = _FIELD_RE.match(line)
            if fm:
                key = fm.group(1).strip()
                rest = line[fm.end():]
                fields[key] = re.sub(r"^[^:]*:\s*", "", rest, count=1).strip() or rest.strip()
                current = key
            elif current and (line.startswith("  ") or line.startswith("\t")):
                fields[current] = (fields[current] + " " + line.strip()).strip()
            else:
                current = None
        out[m.group(1)] = {"fields": fields, "yield_notes": notes}
    return out
