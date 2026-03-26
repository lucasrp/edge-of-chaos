[Unit]
Description=Blog Server ({{ AGENT_NAME }})
After=network.target

[Service]
Type=simple
ExecStart={{ WORK_DIR }}/blog/.venv/bin/python3 {{ WORK_DIR }}/blog/app.py
Restart=always
RestartSec=3
WorkingDirectory={{ WORK_DIR }}
Environment="HOME=%h"
EnvironmentFile=-{{ WORK_DIR }}/secrets/keys.env

[Install]
WantedBy=default.target
