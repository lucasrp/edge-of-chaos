[Unit]
Description=Blog Server ({{ AGENT_NAME }})
After=network.target

[Service]
Type=simple
ExecStart={{ WORK_DIR }}/blog/.venv/bin/python3 {{ WORK_DIR }}/blog/app.py
Restart=always
RestartSec=3
WorkingDirectory={{ WORK_DIR }}/blog
Environment="HOME=%h"
Environment="BLOG_PORT={{ BLOG_PORT }}"

[Install]
WantedBy=default.target
