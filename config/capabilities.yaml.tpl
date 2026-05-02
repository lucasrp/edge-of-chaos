capabilities:
  - name: sources.aggregate
    kind: external_cli
    description: Unified external source search wrapper over edge-sources.
    command: ["edge-sources"]
    passthrough: true
    probe: ["edge-sources", "--help"]
    required: true
    roles: ["search", "source", "external_context"]
    skills: ["sources", "research", "discovery", "report", "planner", "heartbeat"]

  - name: signals.aggregate
    kind: external_cli
    description: State-oriented signal aggregation wrapper over edge-signals for routing, gating, and primitive health visibility.
    command: ["edge-signals"]
    passthrough: true
    probe: ["edge-signals", "--help"]
    required: true
    roles: ["signals", "observe", "routing", "health"]
    skills: ["heartbeat", "autonomy", "report", "research", "planner", "discovery"]

  - name: context.aggregate
    kind: external_cli
    description: Unified UX wrapper over distinct edge-signals and edge-sources lanes.
    command: ["edge-context"]
    passthrough: true
    probe: ["edge-context", "--help"]
    required: true
    roles: ["signals", "search", "context"]
    skills: ["heartbeat", "autonomy", "report", "research", "planner", "discovery"]

  - name: search.corpus
    kind: external_cli
    description: Corpus and workflow-aware local search wrapper over edge-search.
    command: ["edge-search"]
    passthrough: true
    probe: ["edge-search", "--help"]
    required: true
    skills: ["research", "discovery", "report", "planner", "autonomy"]

  - name: repo.status
    kind: external_cli
    description: Git status wrapper for quick repo cleanliness and drift inspection.
    command: ["git", "status", "--short"]
    passthrough: false
    probe: ["git", "--version"]
    required: true
    skills: ["autonomy", "heartbeat"]

  - name: repo.sync
    kind: external_cli
    description: Audit and exact-code synchronization wrapper for the genotype checkout.
    command: ["edge-repo-sync"]
    passthrough: true
    probe: ["edge-repo-sync", "--help"]
    required: true
    roles: ["sync", "audit", "repository"]
    skills: ["autonomy", "heartbeat"]

  - name: storage.sync
    kind: external_cli
    description: File synchronization wrapper over rclone sync.
    command: ["rclone", "sync"]
    passthrough: true
    probe: ["rclone", "version"]
    required: false
    skills: ["report", "autonomy"]
