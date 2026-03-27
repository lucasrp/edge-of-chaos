---
name: ed-status
description: "Concrete state inspection of all managed artifacts. Counts, categorizes, checks health, produces a factual snapshot — not narrative, not strategic. Triggers on: status, state, dashboard, inventory, status dos artefatos."
user-invocable: true
---

# State — Factual Inventory of Artifacts

Inspects the concrete status of all managed artifacts (state files, proposals, discoveries, breaks, notes, labs, git projects). Produces a quantitative and factual snapshot — numbers, counts, timestamps, health.

NOT context (qualitative, orientation). NOT strategy (priorities, decisions). It is pure inventory.

---

## The Job

1. Count and categorize each artifact type
2. Check health (sizes, timestamps, consistency)
3. Detect anomalies (orphan files, inconsistent statuses, accumulations)
4. Produce structured snapshot — factual, no recommendations

---

## Protocol (follow in order)

### Step 1: State Files (autonomy system memory)

```bash
echo "=== STATE FILES ==="
for f in breaks-active.md breaks-archive.md propostas.md discoverys.md personality.md reflection-log.md; do
  path="$HOME/.claude/projects/$MEMORY_PROJECT_DIR/memory/$f"
  if [ -f "$path" ]; then
    lines=$(wc -l < "$path")
    size=$(du -h "$path" | cut -f1)
    mod=$(stat -c %Y "$path" 2>/dev/null)
    age=$(( ($(date +%s) - mod) / 86400 ))
    echo "$f: ${lines} lines, ${size}, modified ${age} days ago"
  else
    echo "$f: DOES NOT EXIST"
  fi
done
```

**Health of breaks-active.md:**
- <150 lines → healthy
- 150-200 → growing (reflection should consolidate)
- >200 → critical (urgent consolidation)

### Step 2: Proposals

```bash
echo "=== PROPOSALS ==="
file="$HOME/.claude/projects/$MEMORY_PROJECT_DIR/memory/propostas.md"
if [ -f "$file" ]; then
  echo "Total proposals: $(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)"
  for status in PROPOSTA APROVADA "EM EXECUCAO" CONCLUIDA REJEITADA SUPERSEDED; do
    count=$(grep -c "\[$status\]" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  [$status]: $count"
  done
fi
```

List each proposal with: number, summarized title, status, date.

### Step 3: Discoveries

```bash
echo "=== DISCOVERIES ==="
file="$HOME/.claude/projects/$MEMORY_PROJECT_DIR/memory/discoverys.md"
if [ -f "$file" ]; then
  echo "Total: $(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)"
  for status in PENDENTE ADOTADA ARQUIVADA "EXPLORAR MAIS"; do
    count=$(grep -c "\[$status\]" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  [$status]: $count"
  done
fi
```

### Step 4: Breaks and Heartbeat

```bash
echo "=== HEARTBEAT ==="
# Extract heartbeat status from breaks-active.md
grep -A 5 "Estado do Heartbeat" ~/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-active.md 2>/dev/null

echo ""
echo "=== BREAKS (archive) ==="
file="$HOME/.claude/projects/$MEMORY_PROJECT_DIR/memory/breaks-archive.md"
if [ -f "$file" ]; then
  total=$(grep -c '^\## \[' "$file" 2>/dev/null || echo 0)
  echo "Total breaks: $total"
  for tipo in leisure research discovery strategy reflection planejamento execucao; do
    count=$(grep -ci "tipo.*$tipo\|$tipo —" "$file" 2>/dev/null || echo 0)
    [ "$count" -gt 0 ] && echo "  $tipo: $count"
  done
  echo ""
  echo "Last break:"
  grep '^\## \[' "$file" | tail -1
fi
```

### Step 5: Skills

```bash
echo "=== SKILLS ==="
total=$(ls ~/.claude/skills/*/SKILL.md 2>/dev/null | wc -l)
echo "Total: $total skills"
ls -1 ~/.claude/skills/ 2>/dev/null | while read dir; do
  if [ -f "$HOME/.claude/skills/$dir/SKILL.md" ]; then
    echo "  $dir"
  fi
done
```

### Step 6: Output Artifacts (edge/)

```bash
echo "=== ARTIFACTS (~/edge/) ==="

echo "Notes:"
notes_count=$(ls ~/edge/notes/*.md 2>/dev/null | wc -l)
echo "  $notes_count notes"
[ -f ~/edge/notes/INDEX.md ] && echo "  INDEX.md exists" || echo "  INDEX.md DOES NOT EXIST"

echo "Labs:"
labs=$(ls -d ~/edge/labs/*/ 2>/dev/null | wc -l)
echo "  $labs labs"
ls -d ~/edge/labs/*/ 2>/dev/null | while read d; do
  name=$(basename "$d")
  echo "    $name"
done

echo "Reports:"
reports=$(ls ~/edge/reports/*.html 2>/dev/null | wc -l)
echo "  $reports reports"

echo "Builds:"
ls -d ~/edge/builds/*/ 2>/dev/null | wc -l | xargs -I{} echo "  {} builds"

echo "Blog:"
[ -f ~/edge/blog/index.html ] && echo "  exists" || echo "  DOES NOT EXIST"

echo "Netlify pages:"
ls -d ~/edge/netlify/*/ 2>/dev/null | wc -l | xargs -I{} echo "  {} pages"
```

### Step 7: Git Projects

```bash
echo "=== GIT PROJECTS ==="
for proj in project-a project-b project-c; do  # customize with your project names
  dir="$HOME/work/$proj"
  if [ -d "$dir/.git" ]; then
    branch=$(git -C "$dir" rev-parse --abbrev-ref HEAD 2>/dev/null)
    last_commit=$(git -C "$dir" log -1 --format="%ar" 2>/dev/null)
    dirty=$(git -C "$dir" status --porcelain 2>/dev/null | wc -l)
    echo "$proj: branch=$branch, last_commit=$last_commit, dirty_files=$dirty"
  else
    echo "$proj: NOT FOUND"
  fi
done
```

### Step 8: User Feedback

```bash
echo "=== FEEDBACK ==="
# Count pending vs processed feedback in ~/work/CLAUDE.md
pending=$(grep -c '^\d\.' ~/work/CLAUDE.md 2>/dev/null || echo 0)
processed=$(grep -c '\[PROCESSADO\]' ~/work/CLAUDE.md 2>/dev/null || echo 0)
unprocessed=$(grep '^\d\.' ~/work/CLAUDE.md 2>/dev/null | grep -v '\[PROCESSADO\]' | wc -l)
echo "Total feedback: $pending (processed: $processed, pending: $unprocessed)"
if [ "$unprocessed" -gt 0 ]; then
  echo "PENDING:"
  grep '^\d\.' ~/work/CLAUDE.md 2>/dev/null | grep -v '\[PROCESSADO\]'
fi
```

### Step 9: Anomalies

After collecting all data, check:

1. **Proposal-file consistency:** Each proposal references a proposal file — does the file exist?
2. **Stagnant discoveries:** Any [PENDENTE] for more than 3 heartbeats?
3. **Orphan notes:** Notes in `~/edge/notes/` that are not in INDEX.md?
4. **Abandoned labs:** Labs without recent commits?
5. **Bloated breaks-active.md:** >150 lines = flag
6. **Growing reflection-log:** >300 lines without consolidation?
7. **Pending feedback:** Any item without [PROCESSADO] = flag

---

## Output

Produce the snapshot in the format below. Exact numbers, no narrative.

```markdown
# State — [YYYY-MM-DD HH:MM]

## State Files
| File | Lines | Size | Modified | Health |
|------|-------|------|----------|--------|
| breaks-active.md | N | Xk | N days | ok/growing/critical |
| breaks-archive.md | N | Xk | N days | — |
| propostas.md | N | Xk | N days | — |
| discoverys.md | N | Xk | N days | — |
| personality.md | N | Xk | N days | — |
| reflection-log.md | N | Xk | N days | — |

## Proposals
| # | Title | Status | Date |
|---|-------|--------|------|
| N | ... | [STATUS] | YYYY-MM-DD |

## Discoveries
| Title | Status | Date |
|-------|--------|------|
| ... | [STATUS] | YYYY-MM-DD |

## Heartbeat
- Last beat: #N
- Type: ...
- Beats since strategy: N
- Beats since planner: N

## Skills: N total
[simple list]

## Artifacts
- Notes: N (INDEX: yes/no)
- Labs: N [names]
- Reports: N
- Builds: N
- Blog: yes/no
- Netlify pages: N

## Git Projects
| Project | Branch | Last Commit | Dirty |
|---------|--------|-------------|-------|
| ... | ... | ... | N |

## Feedback
- Processed: N
- Pending: N
[list of pending if any]

## Anomalies
- [factual list of detected inconsistencies, or "None"]
```

---

## Arguments

- `/ed-status` — complete snapshot (default)
- `/ed-status proposals` — proposals section only
- `/ed-status health` — state files + anomalies only (quick)

---

## When to Use

- **Standalone:** `/ed-status` — when you want a factual dashboard
- **Before /ed-heartbeat:** to inform dispatch with concrete data
- **After /ed-reflection:** to verify the state was updated correctly
- **Debug:** when something seems inconsistent — `/ed-status health`

---

## What /ed-status Does NOT Do

- Does NOT interpret (that's /ed-context)
- Does NOT recommend actions (that's /ed-strategy)
- Does NOT modify any files (read-only)
- Does NOT read CLI sessions or conversation logs (that's /ed-context)
- Does NOT do detailed git log (only branch, last commit, dirty count)

---

## Isolation Rule (MANDATORY)

**Read-only.** This skill does NOT modify ANY files — not state files, not projects, nothing.
All commands are read-only (cat, wc, ls, grep, git status, stat).

---

## Notes

- Output is factual and concise. No "I think", no "maybe". Numbers or "DOES NOT EXIST"
- Anomalies are factual, not recommendations. E.g.: "proposal #3 references nonexistent file" — not "should create the file"
- If a state file doesn't exist, report as anomaly — don't create it
- Expected execution time: <30 seconds (all local, no network)
