[Unit]
Description=edge heartbeat timer ({{codename}}) — fires the beat on a cadence (agent.yaml)

[Timer]
OnUnitActiveSec={{heartbeat_interval}}
OnBootSec={{heartbeat_interval}}
Persistent=true

[Install]
WantedBy=timers.target
