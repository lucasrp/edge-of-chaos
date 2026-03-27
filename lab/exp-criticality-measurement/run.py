#!/usr/bin/env python3
"""
Experiment: Criticality Measurement — Is edge-of-chaos at the edge?

Measures three indicators on real system data and compares to null models.
"""

import json
import gzip
import os
import re
import math
import random
import statistics
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter

random.seed(42)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

BLOG_DIR = Path.home() / "edge" / "blog" / "entries"
EVENTS_LOG = Path.home() / "edge" / "logs" / "events.jsonl"
HEARTBEAT_LOG_DIR = Path.home() / "edge" / "logs"


def extract_beats():
    """Extract beat data from blog entries and events log."""
    beats = []

    # Parse blog entries for claims
    for md_file in sorted(BLOG_DIR.glob("*.md")):
        content = md_file.read_text()

        # Extract frontmatter
        if not content.startswith("---"):
            continue

        end = content.find("---", 3)
        if end == -1:
            continue
        frontmatter = content[3:end]

        # Extract title
        title_match = re.search(r'^title:\s*"?(.+?)"?\s*$', frontmatter, re.M)
        title = title_match.group(1) if title_match else md_file.stem

        # Extract tags
        tags_match = re.search(r'^tags:\s*\[(.+?)\]', frontmatter, re.M)
        tags = [t.strip().strip('"').strip("'") for t in tags_match.group(1).split(",")] if tags_match else []

        # Extract claims
        claims_all = []
        claims_gaps = []
        in_claims = False
        for line in frontmatter.split("\n"):
            if line.strip().startswith("claims:"):
                in_claims = True
                continue
            if in_claims:
                if line.strip().startswith('- "'):
                    claim = line.strip()[3:].rstrip('"')
                    claims_all.append(claim)
                    if claim.startswith("!"):
                        claims_gaps.append(claim)
                elif line.strip().startswith("- '"):
                    claim = line.strip()[3:].rstrip("'")
                    claims_all.append(claim)
                    if claim.startswith("!"):
                        claims_gaps.append(claim)
                else:
                    in_claims = False

        # Extract skill type from tags
        skill_type = "unknown"
        for t in tags:
            if t in ("discovery", "leisure", "research", "experiment", "reflection", "report", "strategy"):
                skill_type = t
                break

        beats.append({
            "file": md_file.name,
            "title": title,
            "skill": skill_type,
            "tags": tags,
            "claims_total": len(claims_all),
            "claims_gaps": len(claims_gaps),
            "claims_list": claims_all,
            "gaps_list": claims_gaps,
        })

    return beats


def extract_events():
    """Extract timestamped events from events log."""
    events = []
    if not EVENTS_LOG.exists():
        return events

    for line in EVENTS_LOG.read_text().strip().split("\n"):
        if not line.strip():
            continue
        try:
            evt = json.loads(line)
            ts = evt.get("timestamp", "")
            if ts:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                events.append({
                    "timestamp": dt,
                    "type": evt.get("type", ""),
                    "summary": evt.get("summary", ""),
                    "skill": evt.get("skill", ""),
                    "claims_count": evt.get("claims_count", 0),
                    "open_claims": evt.get("open_claims", 0),
                })
        except (json.JSONDecodeError, ValueError):
            continue

    return sorted(events, key=lambda e: e["timestamp"])


def compute_branching_ratio(beats):
    """Compute branching ratio: gap claims per beat."""
    if not beats:
        return {"sigma": 0, "values": [], "ci_low": 0, "ci_high": 0}

    gaps_per_beat = [b["claims_gaps"] for b in beats]
    sigma = statistics.mean(gaps_per_beat)

    # Bootstrap 95% CI
    n_bootstrap = 10000
    boot_means = []
    for _ in range(n_bootstrap):
        sample = random.choices(gaps_per_beat, k=len(gaps_per_beat))
        boot_means.append(statistics.mean(sample))
    boot_means.sort()
    ci_low = boot_means[int(0.025 * n_bootstrap)]
    ci_high = boot_means[int(0.975 * n_bootstrap)]

    return {
        "sigma": sigma,
        "values": gaps_per_beat,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n": len(gaps_per_beat),
    }


def compute_null_branching(beats, n_shuffles=1000):
    """Null model: bootstrap resample gap counts from observed distribution."""
    if not beats:
        return {"null_sigmas": [], "mean": 0, "std": 0}

    gap_counts = [b["claims_gaps"] for b in beats]
    n_beats = len(beats)

    null_sigmas = []
    for _ in range(n_shuffles):
        # Bootstrap: resample with replacement from observed gap counts
        resampled = random.choices(gap_counts, k=n_beats)
        null_sigmas.append(statistics.mean(resampled))

    return {
        "null_sigmas": null_sigmas,
        "mean": statistics.mean(null_sigmas),
        "std": statistics.stdev(null_sigmas) if len(null_sigmas) > 1 else 0.001,
    }


def compression_ratio(sequence):
    """Compute gzip compression ratio for a string sequence."""
    data = " ".join(sequence).encode("utf-8")
    if len(data) == 0:
        return 1.0
    compressed = gzip.compress(data, compresslevel=9)
    return len(compressed) / len(data)


def compute_compression_analysis(beats, n_shuffles=1000):
    """Compare compression ratio of real sequence vs shuffled."""
    if not beats:
        return {}

    # Encode beat sequence as skill types
    sequence = [b["skill"] for b in beats]
    real_ratio = compression_ratio(sequence)

    # Null model: shuffle
    null_ratios = []
    for _ in range(n_shuffles):
        shuffled = sequence.copy()
        random.shuffle(shuffled)
        null_ratios.append(compression_ratio(shuffled))

    null_mean = statistics.mean(null_ratios)
    null_std = statistics.stdev(null_ratios) if len(null_ratios) > 1 else 0.001

    # Also try with topic keywords (richer encoding)
    topic_seq = [b["title"][:30] for b in beats]
    real_topic_ratio = compression_ratio(topic_seq)
    null_topic_ratios = []
    for _ in range(n_shuffles):
        shuffled_t = topic_seq.copy()
        random.shuffle(shuffled_t)
        null_topic_ratios.append(compression_ratio(shuffled_t))

    return {
        "real_skill_ratio": real_ratio,
        "null_skill_mean": null_mean,
        "null_skill_std": null_std,
        "real_topic_ratio": real_topic_ratio,
        "null_topic_mean": statistics.mean(null_topic_ratios),
        "null_topic_std": statistics.stdev(null_topic_ratios) if len(null_topic_ratios) > 1 else 0.001,
        "sequence": sequence,
        "topic_sequence": topic_seq,
    }


def compute_inter_beat_regularity(events):
    """Compute CV of inter-beat intervals."""
    # Filter to artifact_created events (beat completions)
    beat_times = [e["timestamp"] for e in events if e["type"] == "artifact_created"]

    if len(beat_times) < 3:
        return {"cv": None, "intervals_minutes": [], "n": len(beat_times)}

    intervals = []
    for i in range(1, len(beat_times)):
        delta = (beat_times[i] - beat_times[i - 1]).total_seconds() / 60.0
        intervals.append(delta)

    mean_int = statistics.mean(intervals)
    std_int = statistics.stdev(intervals) if len(intervals) > 1 else 0
    cv = std_int / mean_int if mean_int > 0 else 0

    return {
        "cv": cv,
        "intervals_minutes": intervals,
        "mean_interval": mean_int,
        "std_interval": std_int,
        "n": len(intervals),
    }


def compute_null_regularity(intervals, n_shuffles=1000):
    """Null model: Poisson process with same mean rate."""
    if not intervals or len(intervals) < 2:
        return {"null_cvs": [], "mean": 0, "std": 0}

    mean_int = statistics.mean(intervals)
    n = len(intervals)

    null_cvs = []
    for _ in range(n_shuffles):
        # Generate Poisson-like intervals (exponential)
        fake_intervals = [random.expovariate(1.0 / mean_int) for _ in range(n)]
        fake_mean = statistics.mean(fake_intervals)
        fake_std = statistics.stdev(fake_intervals) if len(fake_intervals) > 1 else 0
        null_cvs.append(fake_std / fake_mean if fake_mean > 0 else 0)

    return {
        "null_cvs": null_cvs,
        "mean": statistics.mean(null_cvs),
        "std": statistics.stdev(null_cvs) if len(null_cvs) > 1 else 0,
    }


def cohens_d(real_value, null_distribution):
    """Compute Cohen's d: (real - null_mean) / null_std."""
    if not null_distribution:
        return 0
    null_mean = statistics.mean(null_distribution)
    null_std = statistics.stdev(null_distribution) if len(null_distribution) > 1 else 0
    if null_std < 1e-10:
        return 0.0  # Cannot distinguish if null has no variance
    return (real_value - null_mean) / null_std


def generate_svg_results(branching, null_branching, compression, regularity, null_regularity, results):
    """Generate SVG visualization of results."""
    svg_parts = []

    # Header
    svg_parts.append("""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 700" font-family="monospace">
  <style>
    .title { font-size: 18px; font-weight: bold; fill: #1a1a2e; }
    .subtitle { font-size: 12px; fill: #666; }
    .metric-label { font-size: 11px; fill: #333; }
    .metric-value { font-size: 14px; font-weight: bold; }
    .bar-real { fill: #e74c3c; }
    .bar-null { fill: #95a5a6; }
    .bar-ci { fill: #e74c3c; opacity: 0.2; }
    .verdict-pass { fill: #27ae60; }
    .verdict-fail { fill: #e74c3c; }
    .grid-line { stroke: #eee; stroke-width: 1; }
    .axis { stroke: #333; stroke-width: 1; }
  </style>
""")

    # Title
    svg_parts.append("""
  <text x="450" y="35" text-anchor="middle" class="title">Criticality Measurement — Real vs Null Models</text>
  <text x="450" y="55" text-anchor="middle" class="subtitle">edge-of-chaos system, N={n_beats} beats, {n_events} events</text>
""".format(n_beats=branching["n"], n_events=regularity["n"]))

    # Panel 1: Branching Ratio (top left)
    panel_x, panel_y = 50, 80
    svg_parts.append(f'<text x="{panel_x}" y="{panel_y + 15}" class="metric-label" font-weight="bold">1. Branching Ratio (gap claims/beat)</text>')

    sigma = branching["sigma"]
    null_mean = null_branching["mean"]
    d_branching = results["d_branching"]

    max_val = max(sigma, null_mean) * 1.5
    bar_width = 60
    bar_max_h = 120

    # Real bar
    real_h = (sigma / max_val) * bar_max_h if max_val > 0 else 0
    svg_parts.append(f'<rect x="{panel_x + 40}" y="{panel_y + 170 - real_h}" width="{bar_width}" height="{real_h}" class="bar-real" rx="3"/>')
    svg_parts.append(f'<text x="{panel_x + 70}" y="{panel_y + 185}" text-anchor="middle" class="metric-label">Real</text>')
    svg_parts.append(f'<text x="{panel_x + 70}" y="{panel_y + 165 - real_h}" text-anchor="middle" class="metric-value" fill="#e74c3c">σ={sigma:.2f}</text>')

    # CI whiskers
    ci_low_h = (branching["ci_low"] / max_val) * bar_max_h if max_val > 0 else 0
    ci_high_h = (branching["ci_high"] / max_val) * bar_max_h if max_val > 0 else 0
    cx = panel_x + 70
    svg_parts.append(f'<line x1="{cx}" y1="{panel_y + 170 - ci_low_h}" x2="{cx}" y2="{panel_y + 170 - ci_high_h}" stroke="#e74c3c" stroke-width="2"/>')
    svg_parts.append(f'<line x1="{cx-8}" y1="{panel_y + 170 - ci_low_h}" x2="{cx+8}" y2="{panel_y + 170 - ci_low_h}" stroke="#e74c3c" stroke-width="2"/>')
    svg_parts.append(f'<line x1="{cx-8}" y1="{panel_y + 170 - ci_high_h}" x2="{cx+8}" y2="{panel_y + 170 - ci_high_h}" stroke="#e74c3c" stroke-width="2"/>')

    # Null bar
    null_h = (null_mean / max_val) * bar_max_h if max_val > 0 else 0
    svg_parts.append(f'<rect x="{panel_x + 140}" y="{panel_y + 170 - null_h}" width="{bar_width}" height="{null_h}" class="bar-null" rx="3"/>')
    svg_parts.append(f'<text x="{panel_x + 170}" y="{panel_y + 185}" text-anchor="middle" class="metric-label">Null</text>')
    svg_parts.append(f'<text x="{panel_x + 170}" y="{panel_y + 165 - null_h}" text-anchor="middle" class="metric-value" fill="#666">μ={null_mean:.2f}</text>')

    # Critical line at σ=1
    crit_h = (1.0 / max_val) * bar_max_h if max_val > 0 else 0
    svg_parts.append(f'<line x1="{panel_x + 20}" y1="{panel_y + 170 - crit_h}" x2="{panel_x + 220}" y2="{panel_y + 170 - crit_h}" stroke="#f39c12" stroke-width="1.5" stroke-dasharray="6,3"/>')
    svg_parts.append(f'<text x="{panel_x + 222}" y="{panel_y + 174 - crit_h}" class="metric-label" fill="#f39c12">σ=1 (critical)</text>')

    # Cohen's d
    d_class = "verdict-pass" if abs(d_branching) > 0.5 else "verdict-fail"
    svg_parts.append(f'<text x="{panel_x}" y="{panel_y + 210}" class="metric-label">Cohen\'s d = {d_branching:.2f}</text>')
    svg_parts.append(f'<text x="{panel_x + 200}" y="{panel_y + 210}" class="{d_class}" font-size="12" font-weight="bold">{"DISTINGUISHABLE" if abs(d_branching) > 0.5 else "INDISTINGUISHABLE"}</text>')

    # Panel 2: Compression Ratio (top right)
    panel_x2 = 480
    svg_parts.append(f'<text x="{panel_x2}" y="{panel_y + 15}" class="metric-label" font-weight="bold">2. Compression Ratio (gzip)</text>')

    if compression:
        real_cr = compression["real_skill_ratio"]
        null_cr = compression["null_skill_mean"]
        d_compression = results["d_compression"]

        max_cr = max(real_cr, null_cr) * 1.3
        # Real
        cr_real_h = (real_cr / max_cr) * bar_max_h if max_cr > 0 else 0
        svg_parts.append(f'<rect x="{panel_x2 + 40}" y="{panel_y + 170 - cr_real_h}" width="{bar_width}" height="{cr_real_h}" class="bar-real" rx="3"/>')
        svg_parts.append(f'<text x="{panel_x2 + 70}" y="{panel_y + 185}" text-anchor="middle" class="metric-label">Real</text>')
        svg_parts.append(f'<text x="{panel_x2 + 70}" y="{panel_y + 165 - cr_real_h}" text-anchor="middle" class="metric-value" fill="#e74c3c">{real_cr:.3f}</text>')

        # Null
        cr_null_h = (null_cr / max_cr) * bar_max_h if max_cr > 0 else 0
        svg_parts.append(f'<rect x="{panel_x2 + 140}" y="{panel_y + 170 - cr_null_h}" width="{bar_width}" height="{cr_null_h}" class="bar-null" rx="3"/>')
        svg_parts.append(f'<text x="{panel_x2 + 170}" y="{panel_y + 185}" text-anchor="middle" class="metric-label">Null</text>')
        svg_parts.append(f'<text x="{panel_x2 + 170}" y="{panel_y + 165 - cr_null_h}" text-anchor="middle" class="metric-value" fill="#666">{null_cr:.3f}</text>')

        d_class2 = "verdict-pass" if abs(d_compression) > 0.5 else "verdict-fail"
        svg_parts.append(f'<text x="{panel_x2}" y="{panel_y + 210}" class="metric-label">Cohen\'s d = {d_compression:.2f}</text>')
        svg_parts.append(f'<text x="{panel_x2 + 200}" y="{panel_y + 210}" class="{d_class2}" font-size="12" font-weight="bold">{"DISTINGUISHABLE" if abs(d_compression) > 0.5 else "INDISTINGUISHABLE"}</text>')

    # Panel 3: Inter-beat Regularity (bottom left)
    panel_y3 = 330
    svg_parts.append(f'<text x="{panel_x}" y="{panel_y3 + 15}" class="metric-label" font-weight="bold">3. Inter-beat Regularity (CV of intervals)</text>')

    if regularity["cv"] is not None:
        real_cv = regularity["cv"]
        null_cv_mean = null_regularity["mean"]
        d_regularity = results["d_regularity"]

        max_cv = max(real_cv, null_cv_mean, 1.2) * 1.2

        # Real
        cv_real_h = (real_cv / max_cv) * bar_max_h if max_cv > 0 else 0
        svg_parts.append(f'<rect x="{panel_x + 40}" y="{panel_y3 + 170 - cv_real_h}" width="{bar_width}" height="{cv_real_h}" class="bar-real" rx="3"/>')
        svg_parts.append(f'<text x="{panel_x + 70}" y="{panel_y3 + 185}" text-anchor="middle" class="metric-label">Real</text>')
        svg_parts.append(f'<text x="{panel_x + 70}" y="{panel_y3 + 165 - cv_real_h}" text-anchor="middle" class="metric-value" fill="#e74c3c">CV={real_cv:.2f}</text>')

        # Null (Poisson)
        cv_null_h = (null_cv_mean / max_cv) * bar_max_h if max_cv > 0 else 0
        svg_parts.append(f'<rect x="{panel_x + 140}" y="{panel_y3 + 170 - cv_null_h}" width="{bar_width}" height="{cv_null_h}" class="bar-null" rx="3"/>')
        svg_parts.append(f'<text x="{panel_x + 170}" y="{panel_y3 + 185}" text-anchor="middle" class="metric-label">Poisson</text>')
        svg_parts.append(f'<text x="{panel_x + 170}" y="{panel_y3 + 165 - cv_null_h}" text-anchor="middle" class="metric-value" fill="#666">CV={null_cv_mean:.2f}</text>')

        # Reference line at CV=1 (Poisson)
        poisson_h = (1.0 / max_cv) * bar_max_h if max_cv > 0 else 0
        svg_parts.append(f'<line x1="{panel_x + 20}" y1="{panel_y3 + 170 - poisson_h}" x2="{panel_x + 220}" y2="{panel_y3 + 170 - poisson_h}" stroke="#f39c12" stroke-width="1.5" stroke-dasharray="6,3"/>')
        svg_parts.append(f'<text x="{panel_x + 222}" y="{panel_y3 + 174 - poisson_h}" class="metric-label" fill="#f39c12">CV=1 (Poisson)</text>')

        d_class3 = "verdict-pass" if abs(d_regularity) > 0.5 else "verdict-fail"
        svg_parts.append(f'<text x="{panel_x}" y="{panel_y3 + 210}" class="metric-label">Cohen\'s d = {d_regularity:.2f}</text>')
        svg_parts.append(f'<text x="{panel_x + 200}" y="{panel_y3 + 210}" class="{d_class3}" font-size="12" font-weight="bold">{"DISTINGUISHABLE" if abs(d_regularity) > 0.5 else "INDISTINGUISHABLE"}</text>')

    # Panel 4: Verdict (bottom right)
    svg_parts.append(f'<text x="{panel_x2}" y="{panel_y3 + 15}" class="metric-label" font-weight="bold">VERDICT</text>')

    verdict = results["verdict"]
    v_color = "#27ae60" if "CONFIRMED" in verdict else "#e74c3c" if "REFUTED" in verdict else "#f39c12"

    svg_parts.append(f'<rect x="{panel_x2}" y="{panel_y3 + 25}" width="380" height="180" rx="8" fill="{v_color}" opacity="0.1" stroke="{v_color}" stroke-width="2"/>')
    svg_parts.append(f'<text x="{panel_x2 + 190}" y="{panel_y3 + 60}" text-anchor="middle" font-size="16" font-weight="bold" fill="{v_color}">{verdict}</text>')

    y_offset = panel_y3 + 85
    for line in results["verdict_details"]:
        svg_parts.append(f'<text x="{panel_x2 + 15}" y="{y_offset}" class="metric-label" font-size="10">{line}</text>')
        y_offset += 16

    # Beat sequence visualization (bottom)
    seq_y = 580
    svg_parts.append(f'<text x="50" y="{seq_y}" class="metric-label" font-weight="bold">Beat Sequence (temporal order):</text>')

    skill_colors = {
        "reflection": "#9b59b6", "discovery": "#3498db", "report": "#e67e22",
        "leisure": "#2ecc71", "research": "#1abc9c", "experiment": "#e74c3c",
        "unknown": "#95a5a6",
    }

    if compression and compression.get("sequence"):
        box_w = min(80, 800 // max(len(compression["sequence"]), 1))
        for i, skill in enumerate(compression["sequence"]):
            color = skill_colors.get(skill, "#95a5a6")
            x = 50 + i * (box_w + 5)
            svg_parts.append(f'<rect x="{x}" y="{seq_y + 10}" width="{box_w}" height="30" rx="4" fill="{color}"/>')
            svg_parts.append(f'<text x="{x + box_w//2}" y="{seq_y + 30}" text-anchor="middle" fill="white" font-size="9">{skill[:6]}</text>')

        # Legend
        leg_y = seq_y + 55
        leg_x = 50
        for skill, color in skill_colors.items():
            svg_parts.append(f'<rect x="{leg_x}" y="{leg_y}" width="12" height="12" rx="2" fill="{color}"/>')
            svg_parts.append(f'<text x="{leg_x + 16}" y="{leg_y + 10}" font-size="9" fill="#333">{skill}</text>')
            leg_x += 100

    # Claims per beat bar chart
    claims_y = seq_y + 75
    svg_parts.append(f'<text x="50" y="{claims_y}" class="metric-label" font-weight="bold">Gap Claims per Beat:</text>')
    if branching["values"]:
        max_gaps = max(branching["values"]) if max(branching["values"]) > 0 else 1
        for i, g in enumerate(branching["values"]):
            bh = (g / max_gaps) * 40
            x = 50 + i * 50
            svg_parts.append(f'<rect x="{x}" y="{claims_y + 50 - bh}" width="40" height="{bh}" fill="#e74c3c" opacity="0.7" rx="2"/>')
            svg_parts.append(f'<text x="{x + 20}" y="{claims_y + 65}" text-anchor="middle" font-size="9" fill="#333">{g}</text>')

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def main():
    print("=" * 60)
    print("EXPERIMENT: Criticality Measurement")
    print("=" * 60)
    print()

    # Collect data
    beats = extract_beats()
    events = extract_events()

    print(f"Data: {len(beats)} blog entries, {len(events)} events")
    print()

    # Metric 1: Branching ratio
    print("--- METRIC 1: Branching Ratio ---")
    branching = compute_branching_ratio(beats)
    null_branching = compute_null_branching(beats)
    d_branching = cohens_d(branching["sigma"], null_branching["null_sigmas"])

    print(f"  Real σ = {branching['sigma']:.2f} [95% CI: {branching['ci_low']:.2f} - {branching['ci_high']:.2f}]")
    print(f"  Null μ = {null_branching['mean']:.2f} ± {null_branching['std']:.2f}")
    print(f"  Cohen's d = {d_branching:.2f}")
    print(f"  Per-beat gaps: {branching['values']}")
    print(f"  Prediction was: σ ≈ 1.5-2.5 (supercritical)")
    print(f"  Actual: σ = {branching['sigma']:.2f}")
    print()

    # Metric 2: Compression ratio
    print("--- METRIC 2: Compression Ratio ---")
    compression = compute_compression_analysis(beats)
    d_compression = 0
    if compression:
        d_compression = cohens_d(
            compression["real_skill_ratio"],
            [compression["null_skill_mean"]] * 1000  # Approximate
        ) if compression["null_skill_std"] > 0 else cohens_d(
            compression["real_skill_ratio"],
            [random.gauss(compression["null_skill_mean"], 0.001) for _ in range(1000)]
        )
        # Actually compute properly with the null distribution
        # Regenerate null ratios for d computation
        null_ratios = []
        seq = compression["sequence"]
        for _ in range(1000):
            s = seq.copy()
            random.shuffle(s)
            null_ratios.append(compression_ratio(s))
        d_compression = cohens_d(compression["real_skill_ratio"], null_ratios)

        print(f"  Real (skill seq) = {compression['real_skill_ratio']:.4f}")
        print(f"  Null (skill seq) = {compression['null_skill_mean']:.4f} ± {compression['null_skill_std']:.4f}")
        print(f"  Real (topic seq) = {compression['real_topic_ratio']:.4f}")
        print(f"  Null (topic seq) = {compression['null_topic_mean']:.4f} ± {compression['null_topic_std']:.4f}")
        print(f"  Cohen's d (skill) = {d_compression:.2f}")
        print(f"  Sequence: {' → '.join(compression['sequence'])}")
        print(f"  Prediction was: real < shuffled (more structured)")
        print()

    # Metric 3: Inter-beat regularity
    print("--- METRIC 3: Inter-beat Regularity ---")
    regularity = compute_inter_beat_regularity(events)
    null_regularity = compute_null_regularity(regularity["intervals_minutes"])
    d_regularity = 0
    if regularity["cv"] is not None:
        d_regularity = cohens_d(regularity["cv"], null_regularity["null_cvs"])
        print(f"  Real CV = {regularity['cv']:.3f}")
        print(f"  Mean interval = {regularity['mean_interval']:.1f} min")
        print(f"  Std interval = {regularity['std_interval']:.1f} min")
        print(f"  Null (Poisson) CV = {null_regularity['mean']:.3f} ± {null_regularity['std']:.3f}")
        print(f"  Cohen's d = {d_regularity:.2f}")
        print(f"  Intervals (min): {[f'{x:.1f}' for x in regularity['intervals_minutes']]}")
        print(f"  Prediction was: CV ≈ 0.3-0.5 (sub-Poisson, clock-driven)")
    else:
        print("  Insufficient data for CV computation")
    print()

    # Verdict
    print("=" * 60)
    print("VERDICT")
    print("=" * 60)

    distinguishable = 0
    details = []

    if abs(d_branching) > 0.5:
        distinguishable += 1
        details.append(f"Branching: DISTINGUISHABLE (d={d_branching:.2f})")
    else:
        details.append(f"Branching: indistinguishable (d={d_branching:.2f})")

    if abs(d_compression) > 0.5:
        distinguishable += 1
        details.append(f"Compression: DISTINGUISHABLE (d={d_compression:.2f})")
    else:
        details.append(f"Compression: indistinguishable (d={d_compression:.2f})")

    if regularity["cv"] is not None and abs(d_regularity) > 0.5:
        distinguishable += 1
        details.append(f"Regularity: DISTINGUISHABLE (d={d_regularity:.2f})")
    elif regularity["cv"] is not None:
        details.append(f"Regularity: indistinguishable (d={d_regularity:.2f})")
    else:
        details.append("Regularity: INSUFFICIENT DATA")

    if distinguishable >= 2:
        verdict = "CONFIRMED"
        verdict_text = f"CONFIRMED — {distinguishable}/3 metrics distinguish real from null"
    elif distinguishable == 1:
        verdict = "INCONCLUSIVA"
        verdict_text = f"INCONCLUSIVA — only {distinguishable}/3 metrics distinguish (need ≥2)"
    else:
        verdict = "REFUTED"
        verdict_text = f"REFUTED — {distinguishable}/3 metrics distinguish real from null"

    # Add interpretation
    if branching["sigma"] > 1.2:
        details.append(f"System is SUPERCRITICAL (σ={branching['sigma']:.2f} > 1.0)")
        details.append("More questions generated than resolved — expanding frontier")
    elif branching["sigma"] > 0.8:
        details.append(f"System is NEAR-CRITICAL (σ={branching['sigma']:.2f} ≈ 1.0)")
    else:
        details.append(f"System is SUBCRITICAL (σ={branching['sigma']:.2f} < 1.0)")
        details.append("Ideas dying out — not enough generativity")

    print(f"\n  {verdict_text}")
    for d in details:
        print(f"  • {d}")
    print()

    results = {
        "verdict": verdict_text,
        "verdict_details": details,
        "d_branching": d_branching,
        "d_compression": d_compression,
        "d_regularity": d_regularity,
        "distinguishable_count": distinguishable,
        "branching_sigma": branching["sigma"],
        "branching_ci": [branching["ci_low"], branching["ci_high"]],
    }

    # Save results JSON
    results_full = {
        "branching": {
            "sigma": branching["sigma"],
            "ci_95": [branching["ci_low"], branching["ci_high"]],
            "values": branching["values"],
            "null_mean": null_branching["mean"],
            "null_std": null_branching["std"],
            "cohens_d": d_branching,
        },
        "compression": {
            "real_skill": compression.get("real_skill_ratio"),
            "null_skill_mean": compression.get("null_skill_mean"),
            "real_topic": compression.get("real_topic_ratio"),
            "null_topic_mean": compression.get("null_topic_mean"),
            "cohens_d": d_compression,
            "sequence": compression.get("sequence", []),
        },
        "regularity": {
            "cv": regularity["cv"],
            "mean_interval_min": regularity.get("mean_interval"),
            "std_interval_min": regularity.get("std_interval"),
            "null_cv_mean": null_regularity.get("mean"),
            "cohens_d": d_regularity,
            "intervals_min": regularity.get("intervals_minutes", []),
        },
        "verdict": verdict_text,
        "distinguishable": distinguishable,
        "n_beats": len(beats),
        "n_events": len(events),
    }

    with open(RESULTS_DIR / "results.json", "w") as f:
        json.dump(results_full, f, indent=2, default=str)
    print(f"Results saved: {RESULTS_DIR / 'results.json'}")

    # Generate SVG
    svg = generate_svg_results(branching, null_branching, compression, regularity, null_regularity, results)
    svg_path = RESULTS_DIR / "criticality-measurement.svg"
    with open(svg_path, "w") as f:
        f.write(svg)
    print(f"SVG saved: {svg_path}")

    return results_full


if __name__ == "__main__":
    main()
