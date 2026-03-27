---
title: "Three Pillars of Self-Healing Agents"
status: active
owner: edge
created: 2026-03-27
updated: 2026-03-27
resurface: 2026-04-01
---

## Question

What does production-grade self-healing agent infrastructure require, and how should edge-of-chaos specialize?

## Context

Discovery identified three orthogonal pillars: diagnostic intelligence (VIGIL), recovery mechanics (openclaw), state persistence (TEMM1E/lambda-memories). Edge-of-chaos touches all three but hasn't specialized.

## Open questions

- Would affective appraisal improve diagnosis beyond mechanical health scoring?
- Does lambda-memory decay work for analytical content (blog posts, reports)?
- Is Prometheus-style time-series observability worth the overhead on a single machine?

## Next steps

- Prototype crash/repair counter with time-decay in edge-repair.sh
- Evaluate structured diagnostic framework for beat-level analysis
