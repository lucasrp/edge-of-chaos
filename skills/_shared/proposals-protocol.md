# Proposals Protocol — Shared Backlog for Meta-Skills

`state/proposals.json` is the shared backlog where meta-skills coordinate.
Strategy and reflection produce proposals. Autonomy curates and executes.

---

## Roles

| Role | Skills | What they do |
|------|--------|---|
| **Producer** | strategy, reflection | Add proposals, add evidence to existing ones |
| **Curator + Executor** | autonomy | Prioritize, execute, remove stale, enforce max 3 |

Any meta-skill can strengthen or weaken a proposal by adding evidence.
Only autonomy removes proposals or changes their status to `done`.

---

## Proposal format

```json
{
  "id": "slug-description",
  "what": "Human-readable description of what needs to happen",
  "created_by": "strategy|reflection|autonomy",
  "created_at": "2026-04-07T12:00:00",
  "status": "active|executing|done|stale",
  "evidence": [
    {"from": "reflection", "date": "2026-04-07", "note": "edge-x failed 70% in last 24h"},
    {"from": "strategy", "date": "2026-04-07", "note": "X is declared source, priority 1"}
  ],
  "strength": 2
}
```

- `id` — slug, unique, descriptive (e.g., `materialize-edge-x`, `dedup-signals`)
- `strength` — count of distinct skills that contributed evidence
- `status` — lifecycle state (see below)

---

## Lifecycle

```
created (active) → evidence grows → strong enough → executing → done
                 → no evidence in 5 beats → stale → removed
```

### Autonomy's curation rules

| Condition | Action |
|---|---|
| Evidence from 2+ distinct skills | **Strong** — execute this beat |
| Evidence from 1 skill for 3+ beats | **Mature** — execute |
| No new evidence in 5 beats | **Stale** — remove with note |
| 4th active proposal arrives | Weakest (lowest strength) exits |
| Proposal executed successfully | Status → `done`, keep for 3 beats then remove |

### Adding a proposal (producer)

```python
import json, os
from datetime import datetime

f = os.path.expanduser("~/edge/state/proposals.json")
proposals = json.load(open(f)) if os.path.exists(f) else []

# Check if proposal already exists
existing = next((p for p in proposals if p["id"] == "SLUG"), None)
if existing:
    # Strengthen with new evidence
    existing["evidence"].append({
        "from": "THIS_SKILL",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "note": "WHAT WAS OBSERVED"
    })
    existing["strength"] = len(set(e["from"] for e in existing["evidence"]))
else:
    # Create new (only if < 3 active)
    active = [p for p in proposals if p["status"] == "active"]
    if len(active) < 3:
        proposals.append({
            "id": "SLUG",
            "what": "DESCRIPTION",
            "created_by": "THIS_SKILL",
            "created_at": datetime.now().isoformat(),
            "status": "active",
            "evidence": [{"from": "THIS_SKILL", "date": datetime.now().strftime("%Y-%m-%d"), "note": "REASON"}],
            "strength": 1
        })

with open(f, "w") as fh:
    json.dump(proposals, fh, indent=2)
```

### Curating proposals (autonomy only)

Autonomy reads the full list, applies the rules above, and rewrites the file.
When removing a stale proposal, log the reason in the blog entry for traceability.

---

## What does NOT go in proposals

- Immediate fixes (→ reflection fixes directly or queues via dispatch)
- Operator decisions (→ strategy.md "Proposals" section, operator reviews)
- Content work (→ threads and beats)

Proposals are for **capability changes**: new primitives, source materialization,
workflow crystallization, config changes, infrastructure improvements.

---

## Relation to dispatch queue

The dispatch queue (`state/dispatch-queue.json`) is for **immediate routing**:
"reflection found X, autonomy should handle it next beat."

Proposals are for **accumulated evidence**: "multiple signals point to X,
it's worth investing a beat to fix." A dispatch can trigger reading a proposal,
but they serve different purposes.
