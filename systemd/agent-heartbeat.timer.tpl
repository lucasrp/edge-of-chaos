[Unit]
Description=Claude Code Heartbeat Timer ({{ AGENT_NAME }})

[Timer]
# Frequency set by installer based on HEARTBEAT_INTERVAL
OnActiveSec={{ SYSTEMD_INTERVAL }}
OnUnitActiveSec={{ SYSTEMD_INTERVAL }}
Persistent=true

[Install]
WantedBy=timers.target
