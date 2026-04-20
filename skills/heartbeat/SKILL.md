---
name: ed-heartbeat
description: "Autonomous heartbeat dispatcher. Scans sessions, processes feedback, dispatches skill, logs errors. Triggers on: heartbeat, pulse autonomo, autonomous cycle."
user-invocable: true
---

# Heartbeat — Autonomous Dispatcher (v2 — post-cutover)

Three steps: look, do, log.

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

### 0b: First steps check (onboarding)

```bash
cat ~/edge/state/first-steps.json 2>/dev/null | python3 -c "
import json, sys
try:
    steps = json.load(sys.stdin)
    pending = [s for s in steps if s.get('status') == 'pending']
    if pending:
        print(f'ONBOARDING: {len(pending)} first steps pending')
        for s in pending:
            print(f'  [{s[\"id\"]}] {s[\"task\"][:120]}')
    else:
        print('ONBOARDING_COMPLETE')
except: print('NO_FIRST_STEPS')
" 2>/dev/null
```

**If ONBOARDING with pending steps:** Execute the FIRST pending step. After completion, mark it as done:
```bash
python3 -c "
import json
steps = json.load(open('$HOME/edge/state/first-steps.json'))
for s in steps:
    if s['status'] == 'pending':
        s['status'] = 'done'
        break
json.dump(steps, open('$HOME/edge/state/first-steps.json', 'w'), indent=2)
" 2>/dev/null
```

Then continue to normal routing. One first step per heartbeat — don't rush them all at once.

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

### 1a0: Rolling chat digest (MANDATORY — runs FIRST, every beat)

**Every heartbeat updates a rolling LLM digest of the Claude Code chat.** Previous digest + delta (messages since last beat) → new digest. The digest replaces raw session scanning as the input to 1a.

State files:
- `~/edge/state/chat-digest.md` — current rolling digest (read this in 1a)
- `~/edge/state/chat-digest.offset.json` — last-processed message timestamp (ISO)

```bash
mkdir -p ~/edge/state
OFFSET_FILE=~/edge/state/chat-digest.offset.json
DIGEST_FILE=~/edge/state/chat-digest.md
DELTA_FILE=$(mktemp)

# 1. Collect delta: messages newer than last offset
python3 - "$OFFSET_FILE" "${MEMORY_PROJECT_DIR:--home-vboxuser}" > "$DELTA_FILE" <<'PY'
import json, os, glob, sys
offset_file, proj = sys.argv[1], sys.argv[2]
last_ts = ''
if os.path.exists(offset_file):
    try: last_ts = json.load(open(offset_file)).get('last_ts', '')
    except: pass
out, latest = [], last_ts
for jsonl in sorted(glob.glob(os.path.expanduser(f'~/.claude/projects/{proj}/*.jsonl')), key=os.path.getmtime):
    try:
        for line in open(jsonl):
            msg = json.loads(line)
            ts = msg.get('timestamp', '') or ''
            if ts and ts <= last_ts: continue
            if ts > latest: latest = ts
            mtype = msg.get('type')
            if mtype not in ('user', 'assistant'): continue
            m = msg.get('message', {})
            content = m.get('content', '') if isinstance(m, dict) else str(m)
            if isinstance(content, list):
                content = ' '.join(c.get('text','') for c in content if isinstance(c, dict) and c.get('type') == 'text')
            content = str(content).strip()
            if len(content) > 20:
                out.append(f'[{ts}] [{mtype}] {content[:600]}')
    except Exception: pass
print('\n'.join(out[-120:]))  # cap for token budget
# persist latest timestamp for next beat (written even if delta empty — keeps pointer monotonic)
if latest:
    json.dump({'last_ts': latest}, open(offset_file, 'w'))
PY

# 2. If delta empty → nothing to merge, skip LLM call
if [ ! -s "$DELTA_FILE" ]; then
    echo "CHAT_DIGEST: no delta since last beat — digest unchanged"
else
    prev=$(cat "$DIGEST_FILE" 2>/dev/null || echo '(no previous digest)')
    delta=$(cat "$DELTA_FILE")
    # 3. LLM merge via claude headless — use absolute path so it works under systemd/cron
    CLAUDE_BIN=$(command -v claude || echo ~/.nvm/versions/node/v24.13.0/bin/claude)
    new_digest=$("$CLAUDE_BIN" -p --output-format text <<EOF 2>/dev/null
You are maintaining a rolling digest of an autonomous agent's Claude Code chat.

PREVIOUS DIGEST:
$prev

NEW DELTA (messages since last beat):
$delta

Produce an UPDATED rolling digest (<=500 words, markdown). Preserve load-bearing context from the previous digest; integrate new information from the delta; drop stale details. Sections: Operator directives (standing rules), Active threads, Recent decisions/corrections, Pending work, Tone/signals. Output only the digest — no preamble.
EOF
)
    if [ -n "$new_digest" ]; then
        echo "$new_digest" > "$DIGEST_FILE"
        echo "CHAT_DIGEST: updated ($(wc -w < "$DIGEST_FILE") words)"
    else
        echo "CHAT_DIGEST: LLM returned empty — digest unchanged, offset NOT advanced" >&2
        # Roll back offset so next beat retries this delta
        git checkout -- "$OFFSET_FILE" 2>/dev/null || true
    fi
fi
rm -f "$DELTA_FILE"
```

### 1a: Read user sessions (MANDATORY — DO NOT SKIP)

Primary input: read the rolling digest produced in 1a0.

```bash
cat ~/edge/state/chat-digest.md 2>/dev/null || echo '(digest not yet populated)'
```

Fallback — raw session scan if digest is empty or looks stale (no recent offset):

```bash
ls -lt ~/.claude/projects/$MEMORY_PROJECT_DIR/*.jsonl 2>/dev/null | head -5
python3 -c "
import json, sys
for line in open(sys.argv[1]):
    msg = json.loads(line)
    if msg.get('type') == 'user':
        text = msg.get('message', {}).get('content', '') if isinstance(msg.get('message'), dict) else str(msg.get('message', ''))
        if text and len(text) > 20:
            print(text[:300]); print('---')
" FILE.jsonl 2>/dev/null | head -60
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

### 1g: Serendipity scan (3 lateral queries, multi-primitive)

After reading sessions (1a), identify the main topics of the user's work. Generate 3 **LATERAL** queries — not the direct topic, but adjacent concepts that bring unexpected connections.

**Query generation rules:**
- **DO NOT** repeat the exact topic (if the user works on "domain evaluation", DO NOT search for "domain evaluation")
- Search for the **ADJACENT**: related concepts from other domains, applicable phenomena, impactful trends
- **2-3 CONCEPTUAL words, not technical.** Many primitives (X in particular) AND-match short windows — long/specific queries return 0.
- Think in PHENOMENA, not in TOOLS. "benchmark gaming" > "LLM evaluation error taxonomy"
- One query should cross DOMAINS (connect the technical work with the institutional/market context)

**Example:**
- User's work: "inflated recall in evaluation" in an NLP pipeline
- Query 1: "benchmark gaming AI" (phenomenon: metrics that lie)
- Query 2: "coding agent workflow" (adjacent: how practitioners use agents)
- Query 3: "AI enterprise adoption" (domain crossing: AI + organizational context)

**Anti-pattern:** "LLM evaluation error taxonomy" (4 technical words → always 0 results)

**Fan out across primitives — never hardcode a single source.** `edge-sources` already routes to the right mix per intent (heartbeat intent fans out to HN + Reddit primary, X + GitHub + Exa secondary). Use it as the default lateral scan primitive:

```bash
# For each lateral query (3x) — multi-primitive fan-out:
edge-sources --intent heartbeat "LATERAL_QUERY" --json 2>/dev/null
```

**When to drop to a specific primitive:**
- `edge-x "QUERY"` — only when you specifically want X/Twitter real-time practitioner signal (labs announcements, agent-builder chatter). Not as default lateral scan.
- `edge-arxiv` / `edge-hn` / `edge-exa` / `edge-reddit` — when a previous lateral query surfaces a thread worth going deeper on.

**Graceful degradation:** edge-sources already handles per-source failures internally (missing API key, rate-limit, 0 results). If the whole fan-out returns nothing useful, proceed without — the beat does not block on lateral signal.

Note interesting results (high engagement, non-obvious connection) as **"serendipity"** — use to inform Step 2 (skill/topic choice) and include in blog entry if relevant.

**If no recent sessions:** use context from ~/work/CLAUDE.md as base.
**Budget:** 3 lateral queries, ~5-10 results each. Quick and cheap.

---

## Step 1.5: Classify the beat (BEFORE dispatching)

After reading all context from Step 1, classify the beat:

- **WORK:** There is a clear signal (chat, error, thread, session with correction). Dispatch targeted skill.
- **EXPLORE:** No urgent signal. Dispatch `/ed-discovery` or `/ed-research` (alternate). The value is in serendipity — seeing what we're doing and bringing the right terms, the right projects, the lateral connections.

**ABSOLUTE RULE:** The heartbeat ALWAYS dispatches a skill and the dispatched skill ALWAYS produces a full-rite artifact. There is no empty beat and no minimal-meta / voluntary-minimal / signal-only / blackout-degraded variant. Every skill follows the uniform rite in `_shared/report-template.md`. If an external adversarial provider is unavailable, fall back to Claude; never skip the rite.

**Anti-saturation** changes meaning: it's not "stop", it's "change topic". If the last 3 beats were on the same topic, switch to another. If they were all exploration, do /ed-research on a thread.

---

## Step 2.0: Lifecycle is already open (DO NOT reopen manually)

The heartbeat entrypoint opens the shadow dispatch cycle mechanically before
this skill body starts. That cycle keeps the PreToolUse guard
(`bin/heartbeat-dispatch-guard.sh`, #212) active until a skill is actually
dispatched.

From this point until `edge-skill-step <skill> start` runs, any Write/Edit
into `~/edge/blog/entries/**` or `~/edge/reports/**` will be refused by
the hook. During rollout, the runtime still mirrors the legacy
`state/current-beat.json` sentinel so older checks keep working.

Do **not** run `edge-dispatch open` again from inside the heartbeat skill.
Use `edge-dispatch status` only if debugging the lifecycle.

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

Run the chosen skill with step tracking (#113):

```bash
# Flip the dispatch-cycle state — authorizes artifact writes (#212)
edge-dispatch dispatch --skill <skill>

# Before dispatching
edge-skill-step <skill> start

# The skill runs — it produces blog entry + report + note per its own protocol.
# The dispatched skill already includes its own internal edge-consult (mandatory).

# After skill completes
edge-skill-step <skill> end
```

Individual steps within the skill should call `edge-skill-step <skill> <step_id>` as they execute. Silent skips (steps not logged as executed or skipped) are flagged by reflection.

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

## Step 2.95: Dispatch verification (MANDATORY — mechanical check)

Before logging, verify that a skill was actually dispatched. This is not optional.

```bash
# Check if edge-skill-step recorded a 'start' for this beat
today=$(date +%Y-%m-%d)
DISPATCHED=$(python3 -c "
import json, sys
try:
    steps = [json.loads(l) for l in open('$HOME/edge/logs/skill-steps.jsonl') if l.strip()]
    today_starts = [s for s in steps if s.get('step') == 'start' and '$today' in (s.get('ts') or s.get('timestamp', ''))]
    if today_starts:
        last = today_starts[-1]
        print(f'OK: {last.get(\"skill\", \"unknown\")}')
    else:
        print('FAIL: no skill dispatched')
except Exception as e:
    print(f'FAIL: {e}')
" 2>/dev/null)
echo "$DISPATCHED"
```

**If `FAIL`:** The heartbeat did work without dispatching a skill. This violates the protocol. Do NOT proceed to Step 3. Instead:
1. Log the violation to `debugging.md`
2. Log to the heartbeat log: `[HH:MM] Beat #N — VIOLATION: no skill dispatched. Work done inline without tracking.`
3. The beat is invalid. The work is invisible to reflection.

**If `OK`:** Proceed to Step 3.

**Note:** With `bin/heartbeat-dispatch-guard.sh` wired into `PreToolUse`
(#212), reaching this step without dispatching a skill is only possible if
the heartbeat never attempted to write an artifact. The hook is the
earliest checkpoint; this step is the mechanical double-check.

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

### 3e: Do not close the lifecycle manually

The heartbeat entrypoint closes the shadow dispatch cycle mechanically after
this skill exits. The hook will stop blocking writes there; do **not**
run `edge-dispatch close` from inside the heartbeat skill body.

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
