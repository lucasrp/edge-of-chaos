[Unit]
Description=edge heartbeat ({{codename}}) — single-shot autonomous beat (ADR-0003)
After=network-online.target

[Service]
Type=oneshot
ExecStart={{heartbeat_bin}} --home {{edge_home}}
WorkingDirectory={{edge_home}}
TimeoutStartSec=35min
KillMode=control-group
