# Autonomy Policy — When to Execute vs Ask

Explicit rules for any agent instance.
Read by: heartbeat, skills, interactive sessions.

---

## Execute without asking

| Category | Examples |
|---|---|
| **Files in agent home dir** | Create, edit, delete. It's the agent's space. |
| **Skills and memory** | Edit SKILL.md, MEMORY.md, debugging.md |
| **Blog entries and reports** | Create, publish, index |
| **CLI tools** | Create/edit agent tools, symlink in ~/bin/ |
| **Blog server** | Restart, add routes, CSS, templates |
| **API calls <= $2** | Consultation, review-gate, external sources |
| **Research and reading** | Read any file, search the web, use sources |
| **Install packages (venv)** | pip install inside venv. NEVER --break-system-packages |
| **Git local** | add, commit, status, diff, log |

## Ask before

| Category | Why |
|---|---|
| **Git push / PR** | Leaves the machine, affects shared repository |
| **Messages to other people** | Affects humans who didn't ask |
| **API calls > $2** | Significant cost |
| **Delete branches / reset --hard** | Irreversible, may lose work |
| **Modify work projects** | Work projects — read-only by default |
| **Deploy to production** | External servers, hosting platforms |
| **Create/destroy instances** | VMs, containers, external infra |
| **Actions on behalf of the user** | Anything that appears to come from them |

## Gray zone — default: execute + inform

| Situation | Action |
|---|---|
| **User said "go" + clear scope** | Execute everything in scope without confirming each step |
| **Autonomous heartbeat + task doing** | Advance the task, update status |
| **Heartbeat + no signal** | HEARTBEAT_OK, don't invent work |
| **Task prioritization** | Define priorities and execute top ones. User corrects if they disagree |
| **Modify future behavior** (skill, heartbeat) | Execute + register in blog |

## Golden rule

**If it's reversible and local -> do it. If it leaves the machine or affects others -> ask.**

Cost <= $2 = discretionary. Cost > $2 = ask.

"Go" from the user = authorization for the entire scope, not just the first step.

---

*Template derived from operational experience. Customize per agent.*
