# Edge Fleet Observability

This stack is separate from AcessoVerde observability. It is for Edge fleet
runtime telemetry only.

## Components

- `publish_dispatch_projection.py` reads the local `~/edge/state/events/log.jsonl`
  and publishes a compact `DispatchCycleProjectionPublished` event to Fleet
  Loki.
- `systemd/fleet-dispatch-projection.*` runs the publisher every five minutes
  on each fleet host.
- `docker-compose.yml` starts a dedicated local Grafana on `127.0.0.1:3002`.
- `grafana/provisioning` provisions the Fleet Loki datasource and dashboards.

## Deploy

On the Grafana host:

```bash
mkdir -p ~/observability/fleet
rsync -a observability/fleet/ ~/observability/fleet/
cp ~/edge/secrets/grafana-loki.env ~/observability/fleet/.env
cd ~/observability/fleet
docker compose up -d
```

On each fleet host:

```bash
mkdir -p ~/fleet-observe
cp observability/fleet/publish_dispatch_projection.py ~/fleet-observe/
cp observability/fleet/systemd/fleet-dispatch-projection.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now fleet-dispatch-projection.timer
systemctl --user start fleet-dispatch-projection.service
```

The dashboard intentionally reads Fleet Loki, not the AcessoVerde Postgres or
AcessoVerde Grafana instance.
