---
name: ed-heartbeat
description: "Autonomous heartbeat dispatcher. Scans sessions, processes feedback, dispatches skill, logs errors. Triggers on: heartbeat, pulse autonomo, autonomous cycle."
user-invocable: true
---

# Heartbeat — Autonomous Dispatcher (v2 — post-cutover)

Three steps: look, do, log.

---

## Step -1: Required context (BEFORE everything)

**Follow `~/.claude/skills/_shared/required-context.md`.**

1. Read: `memory/rules-core.md`, `memory/personality.md`, `memory/metodo.md`, `memory/debugging.md`
2. Read: `config/pre-skill.md`, `config/post-skill.md`, `config/strategy.md`
3. Execute the Boot Ritual defined in `pre-skill.md` procedure section
4. Only then proceed to Step 0.

---

## Step 0: Deterministic preflight (BEFORE everything)

```bash
preflight_output=$(bash ~/edge/tools/heartbeat-preflight.sh 2>/dev/null)
echo "$preflight_output"
```

### 0a: Health check (MANDATORY — read preflight result)

The preflight runs `edge-check.sh` automatically and reports health status. Read `health/current.json`:

```bash
cat ~/edge/health/current.json 2>/dev/null | python3 -c "
import json, sys
h = json.load(sys.stdin)
print(f'Health: {h.get(\"status\", \"unknown\")} (score: {h.get(\"score\", \"?\")})')
for k, v in h.get('components', {}).items():
    if isinstance(v, dict) and v.get('status') not in ('ok', None):
        print(f'  ⚠ {k}: {v.get(\"status\")} — {v.get(\"detail\", \"\")}')
" 2>/dev/null
```

**Follow SURVIVAL_POLICY.md:**
- **score >= 70 (normal):** Normal work + 1 remediation action if any component is degraded
- **score 40-69 (degraded):** Priority repair + limited work. Dedicate half the beat to fixing problem components
- **score < 40 (maintenance):** ONLY diagnosis and repair. DO NOT dispatch work skill. Create `health/operator-alert.flag` if repair fails

```bash
# If there is a degraded/fail component, attempt repair:
bash ~/edge/bin/edge-repair.sh 2>/dev/null
```

### 0b: First steps check

```bash
cat ~/edge/state/first-steps.json 2>/dev/null | python3 -c "
import json, sys
try:
    steps = json.load(sys.stdin)
    pending = [s for s in steps if s.get('status') == 'pending']
    if pending:
        print(f'WARNING: {len(pending)} first steps still pending — run them as a batch session outside heartbeat')
    else:
        print('ONBOARDING_COMPLETE')
except: print('NO_FIRST_STEPS')
" 2>/dev/null
```

**first_steps are NOT heartbeat work.** They run as a single batch session
after edge-apply, BEFORE the heartbeat timer starts. If pending steps
appear here, it means bootstrap didn't finish — log a warning but proceed
with normal heartbeat routing. Do NOT execute first_steps inside a beat.

When all steps are done, set `onboarding_mode: false` in agent.yaml.

### 0c: Routing decision

**If `HEALTH:CRITICAL`:** Maintenance mode. Repair and exit. Don't spend tokens on work.

**If `PREFLIGHT_WORK`:** Continue to Step 1 normally. Use detected signals to inform reading and decision.

**If `PREFLIGHT_CLEAN` (and health ok):** Use round-robin to pick the next skill.

```bash
python3 -c "
import json, pathlib
f = pathlib.Path.home() / 'edge' / 'state' / 'beat-rotation.json'
try:
    rot = json.loads(f.read_text())
except:
    rot = {'beat': 0, 'meta_idx': 0, 'content_idx': 0}

beat = rot['beat']
meta = ['reflection', 'autonomy', 'strategy']
content = ['discovery', 'research']

# Every 3rd beat is meta, others are content
if (beat + 1) % 3 == 0:
    skill = meta[rot['meta_idx'] % len(meta)]
    kind = 'META'
    rot['meta_idx'] += 1
else:
    skill = content[rot['content_idx'] % len(content)]
    kind = 'CONTENT'
    rot['content_idx'] += 1

rot['beat'] = beat + 1
f.write_text(json.dumps(rot))
print(f'ROTATION: {kind} → {skill} (beat #{beat + 1})')
" 2>/dev/null
```

Dispatch the skill from the rotation. Meta skills (reflection, autonomy, strategy) MUST run — they maintain the agent's self-awareness. Content skills (discovery, research) produce domain output.

Log:
```bash
echo "[$(date +%H:%M)] PREFLIGHT_CLEAN — rotation: $SKILL." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```

Then go straight to Step 2 with the rotated skill.

---

## Step 1: Look (what happened since the last beat?)

### 1a: Read user sessions (MANDATORY — DO NOT SKIP)

```bash
# Last 5 interactive sessions (not heartbeat)
ls -lt ~/.claude/projects/$MEMORY_PROJECT_DIR/*.jsonl 2>/dev/null | head -10
```

For each recent session, extract user messages:
```bash
python3 -c "
import json, sys
for line in open(sys.argv[1]):
    msg = json.loads(line)
    if msg.get('type') == 'user':
        text = msg.get('message', {}).get('content', '') if isinstance(msg.get('message'), dict) else str(msg.get('message', ''))
        if text and len(text) > 20:
            print(text[:300])
            print('---')
" FILE.jsonl 2>/dev/null | head -80
```

Look for: frustrations, course corrections, repeated requests, priority changes, tone, **operational directives**.

**Operator directives** — messages with patterns like "always", "from now on", "whenever", "never do X", "make sure to", "every time" that define how the agent should work. These are workflow-level instructions. Create an approved workflow immediately:

```bash
edge-crystallize --from-operator "the directive text"
```

This creates a `workflow` entry (operator authority = instant approval) that enters recall for all future skills.

**If unable to extract content, record the technical reason in debugging.md. DO NOT skip silently.**

### 1b: Read async chat (single channel)

```bash
curl -s 'http://localhost:8766/api/chat?unprocessed=true' | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('messages', []):
    if m.get('author') == 'user' and not m.get('processed'):
        print(f'CHAT ID: {m[\"id\"]} | TEXT: {m[\"text\"]}')
"
```

Chat is the async channel. Blog comments exist as a feature (annotate, save) but the heartbeat does not process them.

### 1c: Read previous beats (avoid repetition)

```bash
cat ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log 2>/dev/null
```

Know what already ran today. Avoid same topic/skill 3x in a row.

### 1d: Read debugging.md

```bash
cat ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/debugging.md
```

Check if the previous beat left a pending error.

### 1e: Read project context (lightweight)

```bash
cat ~/work/CLAUDE.md
```

Absorb priorities and project status. DO NOT run full /ed-context — the simplified heartbeat reads directly.

### 1e2: Read investigation threads (MANDATORY)

```bash
# Threads with resurface <= today and status active/waiting
today=$(date +%Y-%m-%d)
for f in ~/edge/threads/*.md; do
  status=$(grep '^status:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  resurface=$(grep '^resurface:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  title=$(grep '^title:' "$f" 2>/dev/null | head -1 | sed 's/^title: *//' | tr -d '"')
  owner=$(grep '^owner:' "$f" 2>/dev/null | head -1 | awk '{print $2}')
  if [ "$status" = "active" ] || [ "$status" = "waiting" ]; then
    if [ -n "$resurface" ] && [ "$resurface" \<= "$today" ]; then
      echo "RESURFACE: [$status] $title (owner:$owner, resurface:$resurface)"
    fi
  fi
done
```

Threads with overdue resurface inform the Step 2 decision:
- **active** thread with overdue resurface → consider as topic for the beat
- **waiting** thread with overdue resurface → check if the wait condition has changed
- Thread with **owner:lucas** → DO NOT dispatch skill, but note in the log that it depends on the user
- Thread with **owner:edge** → direct candidate for beat

For each thread with resurface, consult related claims:
```bash
edge-claims --thread THREAD_ID 2>/dev/null
```
Open claims (prefix `!`) are knowledge gaps — natural candidates for research or experiment. Verified claims show what we already know about the thread.

### 1f: Corpus check — "is this new?" (MANDATORY before dispatching)

After absorbing context (1a-1e2), identify 2-3 candidate topics for the beat. For each one, check if already covered:

```bash
edge-search "[candidate topic]" -k 3
```

**Decision:**
- High score (top result very relevant) → topic already covered. Change direction or focus on an open gap
- Low score or no results → new ground, can dispatch
- Partial result → go deeper on what's missing (gap-driven)

This avoids the anti-pattern of rediscovering the same concept in consecutive beats. Budget: 2-3 quick queries (~3s total).

### 1g: X serendipity scan (3 lateral queries)

After reading sessions (1a), identify the main topics of the user's work. Generate 3 **LATERAL** queries — not the direct topic, but adjacent concepts that bring unexpected connections.

**Query generation rules:**
- **DO NOT** repeat the exact topic (if the user works on "domain evaluation", DO NOT search for "domain evaluation")
- Search for the **ADJACENT**: related concepts from other domains, applicable phenomena, impactful trends
- **2-3 CONCEPTUAL words, not technical.** X Basic tier searches AND between words, 7-day window. Long/specific queries return 0.
- Think in PHENOMENA, not in TOOLS. "benchmark gaming" > "LLM evaluation error taxonomy"
- One query should cross DOMAINS (connect the technical work with the institutional/market context)

**Example:**
- User's work: "inflated recall in evaluation" in an NLP pipeline
- Query 1: "benchmark gaming AI" (phenomenon: metrics that lie)
- Query 2: "coding agent workflow" (adjacent: how practitioners use agents)
- Query 3: "AI enterprise adoption" (domain crossing: AI + organizational context)

**Anti-pattern:** "LLM evaluation error taxonomy" (4 technical words → always 0 results)

```bash
# For each lateral query (3x):
edge-x "LATERAL_QUERY" --max 3 --json 2>/dev/null
```

Note interesting results (high engagement, non-obvious connection) as **"serendipity"** — use to inform Step 2 (skill/topic choice) and include in blog entry if relevant.

**If no recent sessions:** use context from ~/work/CLAUDE.md as base.
**If X returns nothing useful:** proceed without — it doesn't block the beat.
**Budget:** 3 queries, ~5 results each. Quick and cheap.

---

## Step 1.5: Classify the beat (BEFORE dispatching)

After reading all context from Step 1, classify the beat:

- **WORK:** There is a clear signal (chat, error, thread, session with correction). Dispatch targeted skill.
- **EXPLORE:** No urgent signal. Dispatch `/ed-discovery` or `/ed-research` (alternate). The value is in serendipity — seeing what we're doing and bringing the right terms, the right projects, the lateral connections.

**ABSOLUTE RULE:** The heartbeat ALWAYS dispatches a skill. There is no empty beat.

**Anti-saturation** changes meaning: it's not "stop", it's "change topic". If the last 3 beats were on the same topic, switch to another. If they were all exploration, do /ed-research on a thread.

---

## Step 2: Do (dispatch ONE skill)

### Decision tree (simple)

1. **User asked for something?** (message in chat/comment with direction) → Address it. If it's an internal change → do it. If it's a project → note it, reply that it needs /ed-execute.

2. **Dispatch queue has pending items?** → Check `state/dispatch-queue.json` for queued dispatches from reflection or other skills:

```bash
python3 -c "
import json, os
f = os.path.expanduser('~/edge/state/dispatch-queue.json')
if os.path.exists(f):
    queue = json.load(open(f))
    if queue:
        item = queue[0]
        print(f'DISPATCH_PENDING: {item[\"skill\"]} (from {item[\"source\"]}: {item[\"reason\"]})')
        # Consume the item
        queue.pop(0)
        with open(f, 'w') as fh:
            json.dump(queue, fh, indent=2)
    else:
        print('DISPATCH_QUEUE_EMPTY')
else:
    print('DISPATCH_QUEUE_EMPTY')
" 2>/dev/null
```

If `DISPATCH_PENDING` → dispatch the indicated internal skill (e.g., `/ed-corpus-curation procedures`). Internal skills (`invocation: internal`) are only dispatched by explicit signal from another skill, never by the normal rotation.

3. **Pending error in debugging.md that I can resolve?** → Resolve.

4. **Thread with overdue resurface and owner:edge?** → Use the thread as topic. Read the thread file (`~/edge/threads/ID.md`), understand the next step, and dispatch the appropriate skill. Consult `edge-claims --thread THREAD_ID` to see verified and open claims for the thread. Open claims (`!`) are knowledge gaps — natural candidates for `/ed-research` or `/ed-experiment`. Update `resurface` and `updated` in the thread after the beat.

5. **Open claim without a resurfacing thread?** → `edge-claims --open` shows what I don't know yet. If any open claim has matured (more context available, new research that could answer it), consider it as a topic for `/ed-research`.

6. **None of the above?** → Choose ONE skill based on what seems most useful NOW:
   - `/ed-research [topic]` — when there is an open question or hot topic
   - `/ed-discovery` — when context suggests an interesting lateral connection
   - `/ed-strategy` — every ~5 beats, or when context changed
   - `/ed-reflection` — when there is user feedback to process
   - `/ed-planner` — when there is a mature insight to turn into a proposal

7. **Absolute fallback (NEVER skip):** If nothing above applies, dispatch `/ed-discovery` or `/ed-research` (alternate with the last one). The heartbeat NEVER ends without dispatching.

**Anti-saturation rule:** If the last 3 beats were on the same topic, CHANGE TOPIC (don't stop).

**Variety rule:** Don't repeat the same skill 3x in a row. Alternate work/exploration.

### Step 2.5: Decision sanity check (edge-consult — MANDATORY)

Before dispatching, submit the decision to edge-consult:

```bash
edge-consult "Context: [summary of what I read in steps 1a-1g]. Decision: dispatch [skill] about [topic]. Am I choosing correctly or is there something more urgent?"
```

If GPT suggests a better direction, consider it. The entire beat costs ~2h of timing — getting the choice right matters more than speed.

### Dispatch

Run the chosen skill. It produces: blog entry + report + note (per its own protocol). The dispatched skill already includes its own internal edge-consult (mandatory in every skill).

---

## Step 2.9: Post-skill execution (MANDATORY after work completes)

After the skill's main work is done (Step 2) and before logging (Step 3):

1. Re-read `config/post-skill.md`
2. Execute EVERY procedure defined there, one by one
3. **CRITICAL: each procedure is independent. A failure in one MUST NOT
   stop the others.** Execute all of them, every time, regardless of
   prior failures. The sequence is:
   - Procedure 1 (e.g. LaTeX render) → try → log success or failure → CONTINUE
   - Procedure 2 (e.g. Overleaf mirror) → try → log success or failure → CONTINUE
   - Procedure 3 (e.g. notify operator) → try → log success or failure → CONTINUE
4. For each procedure, log the outcome to `logs/post-skill.log`:
   ```
   [TIMESTAMP] procedure: LaTeX render | status: FAIL | reason: pandoc not installed
   [TIMESTAMP] procedure: Overleaf mirror | status: OK | files: 2
   [TIMESTAMP] procedure: notify | status: SKIP | reason: no notification channel configured
   ```
5. If a tool is missing (pandoc, latexmk), log it and move on — do not
   attempt to install packages mid-beat. **Dependency remediation
   happens during reflection, not mid-beat** (see reflection HN-1c)
6. If a primitive exists for the task (e.g. `libexec/<codename>/overleaf-sync`),
   use it instead of raw git commands
7. notify.sh is ALWAYS the last call, even if everything else failed —
   the operator needs to know what happened

**A post-skill that stops at the first failure is a bug, not caution.**

---

## Step 3: Log

### 3a: Respond to user (MANDATORY if there is a pending message)

Respond WITH FOLLOW-UP — what the beat did, how it connects with the request.

```bash
# Respond in chat
curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"author":"claude","text":"RESPONSE"}'

# Mark user message as processed
curl -s -X POST http://localhost:8766/api/chat \
  -H "Content-Type: application/json" \
  -d '{"action":"mark_processed","id":CHAT_ID}'
```

**RULE:** Every response MUST be followed by mark_processed on the user's message. No exceptions.

### 3b: Capture errors in debugging.md

If something failed, a workaround was needed, or the result was below expectations:
1. Read debugging.md
2. Check if it's already recorded
3. If new: add entry

### 3c: Validation gate

```bash
python3 ~/edge/blog/validate.py --recent 2>/dev/null
```

Fix issues from this session before closing.

### 3d: Beat log + event log (MANDATORY)

Append to the day's log:
```bash
echo "[$(date +%H:%M)] Beat — [skill] [topic]. [1-line summary of what was done]." >> ~/edge/logs/heartbeat-$(date +%Y-%m-%d).log
```

Record structured event (closes the continuity loop):
```bash
# Every beat dispatches a skill:
edge-event log -t skill_dispatched -s "[summary of what was done]" --skill [skill] --thread [thread_id] --artifacts "[created artifacts]" --update-thread [days until next resurface]

# If an error occurred:
edge-event log -t error_logged -s "[error description]" --thread [thread_id]
```

The `--update-thread N` automatically updates `updated:` and `resurface:` in the thread file. Without this, threads age silently.

**Follow ~/.claude/skills/_shared/state-protocol.md for status management.**

---

## Infrastructure

- **Timer:** systemd (claude-heartbeat.timer)
- **Logs:** `~/edge/logs/heartbeat-YYYY-MM-DD.log`
- **Manually:** `/ed-heartbeat`

## Isolation Rule

- **NEVER** modify files in `~/work/*/` — read-only
- All output goes in `~/edge/` (blog, notes, reports, builds)
- Use `ultrathink` (thinkmax) in the Step 2 decision

## What the Heartbeat Does NOT Do

- Does NOT execute tasks in projects (reserved for /ed-execute)
- Does NOT push, PR, or perform destructive actions
- Does NOT update ~/work/CLAUDE.md (reserved for /ed-reflection)
