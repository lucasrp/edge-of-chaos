---
name: Implement means issue-commit-push-propagate
description: When user says "implement", follow the genotype flow — write GH issue, branch, commit, push, then propagate via edge-apply. Never edit deployed files directly.
type: feedback
originSessionId: f0de4e26-fe38-4f07-82e4-5a37a0b63e4c
---
When asked to "implement" a change: write a GitHub issue first, create a branch, commit, push, and only then propagate to the instance.

**Why:** The edge/ directory is a deployed instance. Direct edits bypass the genotype pipeline (issue → PR → merge → edge-apply). Changes must flow through the repo so they are versioned, reviewed, and propagate to all instances.

**How to apply:** Any code change — even "simple" ones — follows: issue → branch → commit → push → (optionally PR) → propagate. Never write files directly to ~/edge/tools/ or other genotype paths.
