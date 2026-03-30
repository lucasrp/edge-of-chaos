---
name: ed-autonomy
description: "Active proposal manager. Inventories capabilities, proposes experiments and executions based on what the agent already has access to. Manages a pool of max 3 live proposals — edits, removes stale, proposes new. Triggers on: autonomy, autonomia, self-improve, what do I need, capability review."
user-invocable: true
---

# Autonomy — Active Proposal Manager

Two jobs: **request access** to what's missing, and **propose action** with what's already available. Manages a live pool of max 3 proposals — each one curated, evidence-backed, and ready for operator approval.

**Principle:** More agency = more quality. But agency without initiative is just a bigger toolbox. The value is in seeing combinations that nobody asked for.

---

## The Job

1. Inventory what I have (APIs, dirs, DBs, SSH, tools, data)
2. Review live proposals — edit, strengthen, or remove
3. Identify what I can do with current access that nobody asked for
4. Propose 1 new action if a slot is free (max 3 active proposals)
5. Request access to what's missing (secondary — only if a proposal needs it)

---

## Arguments

- **No argument** (`/ed-autonomy`): full cycle — inventory, review proposals, propose/edit
- **`/ed-autonomy status`**: quick snapshot of capabilities + active proposals

---

## Proposal Pool

File: `~/edge/state/proposals.json`

```json
[
  {
    "id": "slug-identifier",
    "type": "experiment|execution",
    "title": "Short descriptive title",
    "hypothesis": "If X then Y, measured by Z (experiments only)",
    "action": "Concrete steps to execute (executions only)",
    "cost": "Estimated cost (tokens, API calls, time)",
    "evidence": ["Data point 1", "Data point 2"],
    "created": "2026-03-30",
    "updated": "2026-03-30",
    "revisions": 0,
    "status": "active"
  }
]
```

**Rules:**
- Max 3 active proposals at any time
- Each execution of /ed-autonomy can: edit existing, remove stale, add 1 new
- A proposal that survives 3+ revisions with growing evidence is strong signal
- A proposal the agent itself removes is weak signal — no operator action needed
- Proposals appear in the dashboard for operator approve/reject

---

## Protocol

### Step 0: Read signals + context

```bash
# Signals
for f in ~/edge/state/signals/*.md; do echo "=== $(basename $f) ==="; cat "$f" 2>/dev/null; done

# Current proposals
cat ~/edge/state/proposals.json 2>/dev/null || echo "[]"

# Recent activity
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
cd ~/edge && git log --oneline --since="$(date -d '3 days ago' +%Y-%m-%d)" | head -20
```

### Step 1: Inventory

What do I have access to right now?

```bash
# SSH hosts
grep "^Host " ~/.ssh/config 2>/dev/null | awk '{print $2}' | grep -v '*'

# API keys configured
grep -c "." ~/edge/secrets/keys.env 2>/dev/null || echo "0 keys"

# Directories with data
ls ~/edge/blog/entries/ ~/edge/reports/ ~/edge/notes/ ~/edge/threads/ 2>/dev/null | head -5

# Tools available
ls ~/.local/bin/edge-* 2>/dev/null | wc -l

# Databases
ls ~/edge/*.db ~/edge/search/*.db 2>/dev/null
```

Don't just list — **think about combinations**. API X + data Y = possibility Z that nobody asked for.

### Step 2: Review existing proposals

For each proposal in the pool:
- **Has new evidence appeared?** (New data, research from another beat, operator feedback) → Edit: add evidence, sharpen hypothesis
- **Context changed and invalidated it?** (Priority shifted, access lost, already done by another skill) → Remove: free the slot
- **Operator ignored for 3+ cycles?** → Either strengthen with better evidence or remove. Don't keep weak proposals alive.

```bash
# Update proposals.json after review
python3 -c "
import json, os
f = os.path.expanduser('~/edge/state/proposals.json')
proposals = json.load(open(f)) if os.path.exists(f) else []
# ... edit/remove logic ...
json.dump(proposals, open(f, 'w'), indent=2, ensure_ascii=False)
"
```

### Step 3: Propose new (if slot free)

Only if len(proposals) < 3. The proposal must meet ALL criteria:

- **Feasible now.** Uses only access the agent already has. If it needs new access, that's a separate request — the proposal itself must be executable.
- **Falsifiable hypothesis** (experiments) or **concrete deliverable** (executions). "It would be interesting to explore X" is not a proposal.
- **Estimated cost.** Tokens, API calls, time. The operator needs to know what they're approving.
- **Not already rejected.** Check `~/edge/state/signals/decision.md` for prior rejections.

Proposal types:

**Experiment** (`/ed-experiment`) — **does NOT change external state.** Read-only: measures, compares, analyzes. Produces a report with results. No deploys, no publishes, no API writes. Safe to auto-approve if cost is low.
```
"Hypothesis: articles with self-rank <= 3 have 2x more organic traffic.
 Method: correlate GA4 pageviews with edge-search self-rank for 8 GEO articles.
 Cost: 0 (all data local). Success metric: r² > 0.5."
```

**Execution** (`/ed-execute`) — **changes external state.** Deploys, publishes, creates, modifies. Always requires operator approval. Never auto-approve.
```
"Action: create automated weekly corpus health report and post to Slack.
 Uses: curadoria_compute + edge-signal + Slack webhook (already configured).
 Cost: ~5k tokens/week. Deliverable: recurring report in #alerts channel."
```

### Step 3.5: Adversarial sanity check

```bash
edge-consult "Current proposals: [list]. New proposal: [description]. Is this worth the operator's attention or am I gaming the system?" --context ~/edge/state/proposals.json
```

If adversarial review says the proposal is padding → don't add it. Wait for a better idea.

### Step 4: Access requests (secondary)

If a proposal would be much stronger with access the agent doesn't have:

```bash
edge-signal autonomy "Proposal [X] would benefit from access to [Y] — currently blocked"
```

This goes to the signals file, not the proposal pool. The operator sees it in the setup tab signals or in the next autonomy report.

### Step 5: Persist and publish

```bash
# Save updated proposals
python3 -c "
import json
proposals = [...]  # updated pool
with open(os.path.expanduser('~/edge/state/proposals.json'), 'w') as f:
    json.dump(proposals, f, indent=2, ensure_ascii=False)
"
```

Blog entry + report via consolidate-state:

```bash
consolidate-state ~/edge/blog/entries/<slug>.md /tmp/spec-autonomy.yaml
```

---

## Dashboard Integration

Proposals appear in the dashboard alongside workflow drafts. The operator sees:

- **Title** and type (experiment/execution)
- **Evidence** accumulated so far
- **Revisions** count (signal of maturity)
- **Approve** → heartbeat dispatches /ed-experiment or /ed-execute with the proposal context
- **Reject** → recorded in decision.md, proposal removed, autonomy won't re-propose without new evidence

**Auto-approve rule:** Experiments with cost = 0 and no external writes can be auto-approved (Sheridan level 5). Executions always require human approval.

---

## When to Run

- **In heartbeat meta rotation** (every ~9 beats alongside reflection, strategy)
- **After gaining new access** — new API key, new SSH host, new data
- **When friction signals accumulate** — pain points often suggest actionable proposals

---

## Anti-Gaming

- Max 1 new proposal per execution
- Adversarial review before adding
- Proposals the agent removes count as self-correction (positive signal)
- Proposals that survive 3+ revisions with growing evidence are strong
- Ratio of proposed:approved is tracked — if operator rejects >70%, autonomy is miscalibrated
