[Unit]
Description=edge sleep-time rationalization ({{codename}})
After=network-online.target

[Service]
Type=oneshot
ExecStart={{edge_home}}/tools/edge-python {{edge_home}}/tools/sweep.py --rationalize-only
WorkingDirectory={{edge_home}}
TimeoutStartSec=30min
KillMode=control-group
