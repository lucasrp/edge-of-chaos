[Unit]
Description=Claude Code Heartbeat ({{ AGENT_NAME }})

[Service]
Type=oneshot
WorkingDirectory=%h
ExecStart=%h/.local/bin/heartbeat.sh
Environment="HOME=%h"
# IMPORTANT: Adjust PATH to include node/claude binary location
# The installer will update this line with the correct PATH
Environment="PATH=%h/.local/bin:%h/.nvm/versions/node/v22.0.0/bin:/usr/local/bin:/usr/bin:/bin"
TimeoutStartSec=2700
