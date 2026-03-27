---
name: ed-corpus-curation
description: "Corpus curation skill. Computes document health metrics, identifies redundancy clusters, proposes merge/archive/strengthen actions. Triggers on: curation, curadoria, corpus curation, corpus health, document curation, corpus cleanup, curadoria corpus."
user-invocable: true
---

# Corpus Curation

Evaluate corpus document health, identify redundancies, propose actions (KEEP/ARCHIVE/MERGE/STRENGTHEN), and maintain the corpus curated over time.

Can be invoked standalone or by /ed-reflection (which passes context of active threads and recent gaps).

---

## Operation Modes

| Mode | Invocation | Time | What it does |
|------|------------|------|--------------|
| **stats** | `/ed-corpus-curation stats` | ~10s | Per-document metrics (retrieval count, top3, query diversity) |
| **lite** | `/ed-corpus-curation lite` | ~30s | Stats + identification of stale candidates (age>45d, no recent retrieval) |
| **full** | `/ed-corpus-curation` | ~3min | Lite + self-probes + nearest-neighbor clustering + classification + strategic veto |
| **claims** | `/ed-corpus-curation claims` | ~2min | Consolidate claims into topics (duplicates, stale, answered gaps) |
| **procedures** | `/ed-corpus-curation procedures` | ~2min | Process procedure-claims, reinforce/heal workflows, crystallize new workflows |

---

## Arguments

- **mode**: `full` (default), `lite`, `stats`
- **active_threads**: list of active threads (passed by /ed-reflection or provided manually). Suppresses archive of related docs.
- **recent_gaps**: list of recent gaps (passed by /ed-reflection). Docs that cover gaps are not archived.

---

## Operational Signals

Before curation, read friction and serendipity signals to inform quality decisions:

```bash
cat ~/edge/state/signals/friction.md 2>/dev/null   # what's painful → procedures to fix
cat ~/edge/state/signals/serendipity.md 2>/dev/null # what's working → procedures to preserve
```

- friction "YAML report format consumes most tokens" → investigate related procedures
- serendipity "corpus search found perfect note" → that note/procedure has high value, protect it

---

## Protocol

### Step 1: Determine mode

Check argument passed by the user:
- No argument or `full` → full mode
- `lite` → lite mode
- `stats` → stats mode

### Step 2: Collect metrics (all modes)

Run curadoria_compute.py in the corresponding mode:

```bash
curadoria_compute --mode stats
```

This queries the `search_events` table in `~/edge/search/edge-memory.db` and computes per document:
- **retrieved_count**: total times the doc appeared in search results
- **top3_count**: times it appeared in the top-3
- **last_retrieved**: date of last retrieval
- **query_diversity**: number of distinct queries that retrieved the doc
- **age_days**: document age in days

Present summary to the user: total docs, docs with 0 retrievals, most accessed doc, oldest doc without access.

**If mode = stats, stop here.**

### Step 3: Identify stale candidates (lite and full)

```bash
curadoria_compute --mode lite
```

Stale criteria:
- **age > 45 days** AND **retrieved_30d = 0** (nobody searched in the last 30 days)
- OR **age > 45 days** AND **top3_30d = 0** (appeared in searches but never in the top-3)

List stale candidates with their metrics.

**If mode = lite, stop here.**

### Step 4: Self-probes (full only)

For each stale candidate, the script executes a self-probe:
- Constructs a query from the title + 2 rare terms from the content
- Executes `edge-search --no-telemetry "query"`
- Records the **self_rank** (position of the doc in results)

```bash
curadoria_compute --mode full --active-threads "thread1,thread2" --recent-gaps "gap1,gap2"
```

Interpretation:
- self_rank <= 3: doc is relevant for its own content → KEEP
- self_rank 4-5: doc is findable but not dominant → evaluate context
- self_rank > 5 or absent: doc is buried → candidate for ARCHIVE/MERGE

### Step 5: Nearest-neighbor clustering (full only)

The script groups stale candidates by semantic similarity:

**Algorithm (union-find):**
1. For each stale candidate, search top-3 neighbors of the same type in the corpus
2. Add edge if: `nn_sim >= 0.90` OR (`nn_sim >= 0.83` AND `title_overlap >= 0.5`)
3. Form clusters via union-find

### Step 6: Classification (full only)

The script classifies each document/cluster into one of 4 categories:

#### ARCHIVE (auto)
Criteria (ALL must be true):
- age > 120 days
- rrf_30d = 0 (no retrieval in the last 30 days)
- self_rank > 5 (not found even by self-probe)
- Has a strong neighbor (nn_sim >= 0.90) that covers the content

#### MERGE (review)
Criteria:
- Cluster with >= 3 documents
- Median similarity in cluster >= 0.83
- Requires human review before executing

#### STRENGTHEN
Criteria:
- Cluster with high demand (rrf above corpus p75)
- But no doc consistently in top-3
- Action: improve title/content of the most relevant doc

#### KEEP
- All remaining documents

### Step 7: Strategic veto (full only)

Suppression mechanism to protect active docs:
- If the title or content of a doc candidate for ARCHIVE mentions any **active_thread** → suppress (move to `suppressed_due_to_active_thread`)
- If the content covers any **recent_gap** → suppress

This prevents /ed-reflection from archiving documents that are relevant to ongoing work.

### Step 8: Persist results

The script automatically saves to:

```
~/edge/state/curadoria-candidates.json
```

JSON structure:
```json
{
  "generated_at": "ISO timestamp",
  "mode": "full|lite|stats",
  "total_docs": N,
  "stale_candidates": N,
  "archive_auto": [
    {"doc_id": 1, "title": "...", "age_days": N, "self_rank": N, "nn_sim": 0.95, "reason": "..."}
  ],
  "merge_review": [
    {"cluster_id": 1, "docs": [...], "median_sim": 0.87, "suggestion": "..."}
  ],
  "strengthen_targets": [
    {"doc_id": 2, "title": "...", "demand_rrf": N, "best_rank": N, "suggestion": "..."}
  ],
  "suppressed_due_to_active_thread": [
    {"doc_id": 3, "title": "...", "matching_thread": "...", "original_action": "ARCHIVE"}
  ]
}
```

### Step 9: Present results

Summarize for the user:
1. How many docs analyzed, how many stale
2. **Archive auto**: list docs that will be archived (automatic action, but confirm if > 3)
3. **Merge review**: list clusters that need human review
4. **Strengthen**: list docs that need improvement
5. **Suppressed**: list docs protected by strategic veto and the reason

---

## Claims Lifecycle (claims curation)

Beyond documents, this skill manages the claims lifecycle — consolidating short-term memory (claims in frontmatter) into long-term memory (topics/*.md).

### Claims mode

Invocation: `/ed-corpus-curation claims` or `/ed-corpus-curation claims --thread THREAD_ID`

### Step C1: Collection

For the specified thread (or all active threads):
1. Pull all claims that touch the thread (claims are 1:N with threads — a claim can belong to multiple threads via entry)
2. Separate verified ones and open ones (!)

```bash
edge-claims -t THREAD_ID
```

### Step C2: Automatic triage (no LLM)

For the collected set of claims:

**Duplicates** — embedding similarity > 0.92 between claims of the same thread. Group candidates.

**Stale factuals** — claims containing numbers, dates, or counts whose entry is older than 30 days AND more recent entries exist in the thread. Mark as `stale_candidate`.

**Potentially answered gaps** — open claim (`!`) with similar embedding (> 0.85) to a later verified claim (more recent date) in the same thread. Mark as `answered_candidate`.

### Step C3: Consolidation (LLM)

Send the batch of claims to `edge-consult` with a structured prompt:

```bash
edge-consult "Claims for thread [ID]:
[list of claims]

Classify each claim:
- keep: independent knowledge that survives
- merge(claim_ids): duplicates that say the same thing
- superseded_by(claim_text): was updated by a more recent version
- answered_by(claim_text): gap that was answered
- stale: factual with outdated data
- keep_as_is: conceptual/timeless, do not touch

Output: JSON array with {claim_text, action, target, reason}" --context ~/edge/threads/THREAD_ID.md
```

### Step C4: Consolidation proposal for the topic

Based on C3 output:
1. `keep` claims that form a cluster (3+ on the same subtopic) → propose consolidated paragraph for the topic
2. Each paragraph includes provenance: `← entry-slug-1, entry-slug-2`
3. `answered_by` gaps → list as resolved
4. `stale` claims → list for review
5. `merge` claims → identify canonical one

Save proposal to `~/edge/state/claims-curation-{thread_id}.json`:
```json
{
  "thread_id": "...",
  "generated_at": "ISO",
  "total_claims": N,
  "actions": [
    {"claim": "...", "action": "keep|merge|superseded|answered|stale", "target": "...", "reason": "..."}
  ],
  "topic_patches": [
    {"section": "Nugget extraction", "content": "...", "sources": ["entry-1", "entry-2"]}
  ],
  "gaps_resolved": [
    {"gap": "!...", "answered_by": "...", "evidence_entry": "..."}
  ]
}
```

### Step C5: Application

- In interactive session: present proposal to Lucas, apply with confirmation
- In autonomous session: apply automatically if all actions are low-risk (merge, answered, stale factual). Hold high-risk (conceptual, decisions) for human review.

Applying means:
1. Update the corresponding topic (add paragraphs with provenance)
2. Resolved gaps remain in the original frontmatter but the topic reflects the current state

---

## Procedures Lifecycle (workflow curation)

Third curation mode: process procedure-claims, workflows_used and workflows_broken from frontmatters to maintain a healthy workflow lifecycle.

### Mode: procedures

Invocation: `/ed-corpus-curation procedures`

### Step P1: Collection

Read frontmatter from all recent entries (last 60 days) and extract:
- `procedure:` — procedure-claims (atoms)
- `workflows_used:` — reinforcement citations
- `workflows_broken:` — healing citations

```bash
# Extract procedure fields from recent entries
grep -rl "procedure:\|workflows_used:\|workflows_broken:" ~/edge/blog/entries/ | head -50
```

### Step P2: Reinforcement (workflows_used)

Count citations per workflow slug:
- Frequently cited workflows → boost relevance (confirmed_useful)
- Never-cited workflows (0 citations, age > 60 days) → candidate for decay/archive

Save counts to `~/edge/state/workflow-health.json`:
```json
{
  "generated_at": "ISO",
  "citations": {
    "sources-research-consult-report": {"used": 5, "broken": 0, "last_cited": "2026-03-27"},
    "playwright-screenshot-validation": {"used": 0, "broken": 3, "last_cited": "2026-03-25"}
  }
}
```

### Step P3: Healing (workflows_broken)

Workflows cited as broken:
- 1 citation → flag for review
- 2+ citations → high priority: update or convert to anti-pattern
- Action: present to user with context (which entries cited, what was the problem)

### Step P4: Crystallization (procedure-claims)

Cluster procedure-claims by semantic similarity:
1. Extract embeddings for all procedure-claims
2. Group by similarity (threshold: 0.85)
3. Clusters with 3+ claims → candidate for crystallization into workflow entry

For each candidate cluster:
- Synthesize claims into a full workflow (format: Trigger, Steps, Secrets, When works, When fails, Cost)
- Present proposal to user
- If approved → create workflow blog entry with tag `workflow`

### Step P5: Persist and report

Save to `~/edge/state/procedure-curation.json`:
```json
{
  "generated_at": "ISO",
  "total_procedures": N,
  "total_workflows_used": N,
  "total_workflows_broken": N,
  "crystallization_candidates": [
    {
      "cluster_id": 1,
      "claims": ["When X...", "When Y...", "When Z..."],
      "median_sim": 0.89,
      "suggested_workflow_title": "workflow: X pattern"
    }
  ],
  "broken_workflows": [
    {"slug": "...", "broken_count": N, "citing_entries": ["entry-1", "entry-2"]}
  ],
  "never_cited_workflows": [
    {"slug": "...", "age_days": N}
  ]
}
```

---

## Integration with /ed-reflection

When invoked by /ed-reflection in manual mode:
1. /ed-reflection passes `active_threads` (from git_signals thread_coverage) and `recent_gaps` (from claims_summary persistent_gaps)
2. /ed-corpus-curation runs in full mode with those parameters
3. /ed-reflection reads the result from `curadoria-candidates.json` and makes strategic decisions

---

## Files

| File | Read/Write | Description |
|------|------------|-------------|
| `~/edge/search/edge-memory.db` | Read | documents and search_events tables |
| `~/edge/state/curadoria-candidates.json` | Write | Curation result |
| `~/edge/tools/curadoria_compute.py` | Execute | Computation engine |
