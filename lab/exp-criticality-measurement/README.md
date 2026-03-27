# Experiment: Criticality Measurement — Is edge-of-chaos Actually at the Edge?

## Hypothesis

The edge-of-chaos system produces criticality signatures (branching ratio,
compression ratio, inter-beat regularity) that are statistically
distinguishable from null models (shuffled baselines).

## Metrics

| Metric | Definition | Critical value |
|--------|-----------|---------------|
| Branching ratio σ | Mean gap-claims per beat | σ ≈ 1.0 = critical |
| Compression ratio | gzip(real) / gzip(shuffled) | < 1.0 = more structured than random |
| CV of inter-beat times | std(intervals) / mean(intervals) | ≈ 1.0 = Poisson-like |

## Success criterion

≥2 of 3 metrics show real ≠ null (Cohen's d > 0.5)

## Failure criterion

0-1 metrics distinguish real from null (d < 0.5 for ≥2 metrics)

## Predictions (BEFORE running)

1. **Branching ratio:** σ ≈ 1.5-2.5 (supercritical — system is young, expanding)
2. **Compression ratio:** real < shuffled (temporal structure exists)
3. **CV:** ≈ 0.3-0.5 (sub-Poisson — beats are clock-driven by systemd timer)

## How to reproduce

```bash
cd ~/edge/lab/exp-criticality-measurement
python3 run.py
# Results in results/
```

## Data sources

- Heartbeat log: `~/edge/logs/heartbeat-*.log`
- Blog entries: `~/edge/blog/entries/*.md`
- Events: `~/edge/logs/events.jsonl`
