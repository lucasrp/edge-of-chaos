capabilities:
  - name: sources.aggregate
    kind: external_cli
    description: Unified external source search wrapper over edge-sources.
    command: ["edge-sources"]
    passthrough: true
    probe: ["edge-sources", "--help"]
    required: true
    skills: ["sources", "research", "discovery", "report", "strategy", "planner", "heartbeat"]

  - name: search.corpus
    kind: external_cli
    description: Corpus and workflow-aware local search wrapper over edge-search.
    command: ["edge-search"]
    passthrough: true
    probe: ["edge-search", "--help"]
    required: true
    skills: ["research", "discovery", "report", "planner", "strategy", "reflection", "autonomy"]

  - name: workflow.recommend
    kind: external_cli
    description: Workflow recommendation surface over edge-workflows recommend.
    command: ["edge-workflows", "recommend"]
    passthrough: true
    probe: ["edge-workflows", "status", "--json"]
    required: true
    skills: ["research", "report", "strategy", "planner", "reflection", "autonomy"]

  - name: repo.status
    kind: external_cli
    description: Git status wrapper for quick repo cleanliness and drift inspection.
    command: ["git", "status", "--short"]
    passthrough: false
    probe: ["git", "--version"]
    required: true
    skills: ["reflection", "autonomy", "heartbeat"]

  - name: storage.sync
    kind: external_cli
    description: File synchronization wrapper over rclone sync.
    command: ["rclone", "sync"]
    passthrough: true
    probe: ["rclone", "version"]
    required: false
    skills: ["report", "execute", "autonomy"]
