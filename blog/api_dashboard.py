"""Dashboard API Blueprint — aggregation endpoints for ops console."""

from flask import Blueprint, jsonify, render_template

from blog.services import (
    load_hotspots, load_git_signals, load_curadoria, load_threads_enriched,
    get_publish_commits, get_error_pressure_24h,
    get_heartbeat_status, get_production_stats, get_briefing_html,
    load_autonomy_summary, load_current_dispatch_state, load_primitive_runtime_summary,
    load_recent_dispatch_cycles, load_skill_evidence_summary,
)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/api/dashboard/overview")
def overview():
    """Aggregated overview for status strip and summary."""
    hotspots = load_hotspots()
    signals = load_git_signals()
    curadoria = load_curadoria()
    heartbeat = get_heartbeat_status()
    error_pressure = get_error_pressure_24h()
    production = get_production_stats()

    # Pipeline status from git-signals
    pipeline_failures = signals.get("pipeline_failures", [])
    last_pipeline_status = "ok"
    if pipeline_failures:
        last_pipeline_status = pipeline_failures[0].get("pipeline_status", "failed")

    # Claims
    claims = signals.get("claims_summary", {})

    # Thread count from thread_coverage
    active_threads = len(signals.get("thread_coverage", {}))

    # Alert count: critical conditions
    alert_count = 0
    if heartbeat["status"] == "stalled":
        alert_count += 1
    alert_count += len(pipeline_failures)
    alert_count += len(hotspots.get("top_pain", []))
    alert_count += len(hotspots.get("recovered_but_unstable", []))
    alert_count += len(hotspots.get("codify_now", []))
    alert_count += len(signals.get("fix_chains", []))
    alert_count += len(signals.get("state_violations", []))
    alert_count += len(signals.get("duplicate_slugs", []))

    data = {
        "system_status": {
            "heartbeat": heartbeat,
            "pipeline": {
                "last_status": last_pipeline_status,
                "failure_count": len(pipeline_failures),
            },
            "output": {
                "total_commits": signals.get("total_commits", 0),
                "entries_total": production["entries_total"],
                "reports_total": production["reports_total"],
                "published_today": production["published_today"],
            },
            "error_pressure": error_pressure,
            "claims_threads": {
                "claims_total": claims.get("total_learned", 0),
                "claims_open": claims.get("total_gaps", 0),
                "active_threads": active_threads,
            },
        },
        "alert_count": alert_count,
        "pipeline_summary": {
            "total_commits_7d": signals.get("total_commits", 0),
            "fix_chains": len(signals.get("fix_chains", [])),
            "duplicate_slugs": len(signals.get("duplicate_slugs", [])),
            "pipeline_failures": len(pipeline_failures),
        },
        "hotspot_summary": {
            "top_pain_count": len(hotspots.get("top_pain", [])),
            "incidents_count": len(hotspots.get("incidents", [])),
            "recovered_count": len(hotspots.get("recovered_but_unstable", [])),
            "codify_count": len(hotspots.get("codify_now", [])),
        },
        "corpus_summary": {
            "total_docs": curadoria.get("total_docs", 0),
            "stale_candidates": curadoria.get("stale_candidates", 0) if isinstance(curadoria.get("stale_candidates"), int) else len(curadoria.get("stale_candidates", [])),
            "archive_auto": len(curadoria.get("archive_auto", [])),
            "merge_review": len(curadoria.get("merge_review", [])),
            "strengthen_targets": len(curadoria.get("strengthen_targets", [])),
        },
    }
    return jsonify(data)


def _build_alerts_data():
    """Build prioritized alert cards from multiple sources."""
    hotspots = load_hotspots()
    signals = load_git_signals()
    heartbeat = get_heartbeat_status()

    alert_cards = []

    # Heartbeat stalled = critical
    if heartbeat["status"] == "stalled":
        alert_cards.append({
            "title": "Heartbeat stalled",
            "severity": "critical",
            "detail": f"Heartbeat status: {heartbeat['status']}",
            "count": 1,
            "last_seen": None,
            "source": "heartbeat",
        })
    elif heartbeat["status"] == "late":
        alert_cards.append({
            "title": "Heartbeat late",
            "severity": "high",
            "detail": f"Heartbeat status: {heartbeat['status']}",
            "count": 1,
            "last_seen": None,
            "source": "heartbeat",
        })

    # Pipeline failures = high
    for pf in signals.get("pipeline_failures", []):
        alert_cards.append({
            "title": f"Pipeline failure: {pf.get('subject', '')[:60]}",
            "severity": "high",
            "detail": ", ".join(pf.get("failures", [])),
            "count": 1,
            "last_seen": None,
            "source": "git-signals",
        })

    # Fix chains = medium
    fix_chains = signals.get("fix_chains", [])
    if fix_chains:
        alert_cards.append({
            "title": f"Fix chains detected",
            "severity": "medium",
            "detail": f"{len(fix_chains)} publish commits needed fixes",
            "count": len(fix_chains),
            "last_seen": None,
            "source": "git-signals",
        })

    # State violations = high
    for sv in signals.get("state_violations", []):
        alert_cards.append({
            "title": "State violation",
            "severity": "high",
            "detail": str(sv),
            "count": 1,
            "last_seen": None,
            "source": "git-signals",
        })

    # Duplicate slugs = medium
    for ds in signals.get("duplicate_slugs", []):
        alert_cards.append({
            "title": f"Duplicate slug: {ds.get('slug', '')}",
            "severity": "medium",
            "detail": f"Found {ds.get('count', 0)} times",
            "count": ds.get("count", 0),
            "last_seen": None,
            "source": "git-signals",
        })

    # Ops hotspots: top_pain = high
    for tp in hotspots.get("top_pain", []):
        alert_cards.append({
            "title": f"Pain: {tp.get('signature', '')}",
            "severity": "high",
            "detail": f"Count: {tp.get('count', 0)}, wasted: {tp.get('total_wasted_ms', 0)}ms",
            "count": tp.get("count", 0),
            "last_seen": tp.get("last_seen"),
            "source": "ops-hotspots",
        })

    # recovered_but_unstable = medium
    for ru in hotspots.get("recovered_but_unstable", []):
        alert_cards.append({
            "title": f"Unstable: {ru.get('signature', '')}",
            "severity": "medium",
            "detail": f"Recovered but unstable. Count: {ru.get('count', 0)}",
            "count": ru.get("count", 0),
            "last_seen": ru.get("last_seen"),
            "source": "ops-hotspots",
        })

    # codify_now = medium
    for cn in hotspots.get("codify_now", []):
        alert_cards.append({
            "title": f"Codify: {cn.get('signature', '')}",
            "severity": "medium",
            "detail": "Workaround known, should be codified",
            "count": cn.get("count", 0),
            "last_seen": cn.get("last_seen"),
            "source": "ops-hotspots",
        })

    # Sort by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2}
    alert_cards.sort(key=lambda a: sev_order.get(a["severity"], 9))

    return alert_cards


@dashboard_bp.route("/api/dashboard/alerts")
def alerts():
    """Prioritized alert cards from multiple sources."""
    alert_cards = _build_alerts_data()
    return jsonify({"alerts": alert_cards, "total": len(alert_cards)})


@dashboard_bp.route("/partials/alerts")
def partial_alerts():
    """HTMX partial: attention panel with alert cards."""
    alert_cards = _build_alerts_data()
    return render_template("partials/alerts.html", alerts=alert_cards)


@dashboard_bp.route("/api/dashboard/pipeline")
def pipeline():
    """Last 10 publish commits with status."""
    commits = get_publish_commits(limit=10)
    signals = load_git_signals()

    # Build set of fix-chain hashes for quick lookup
    fix_hashes = {fc.get("publish_hash") for fc in signals.get("fix_chains", [])}

    for c in commits:
        c["fix_chain"] = c["hash"] in fix_hashes
        # Check if this commit had pipeline failures
        for pf in signals.get("pipeline_failures", []):
            if pf.get("hash") == c["hash"]:
                c["status"] = pf.get("pipeline_status", "failed")
                c["failed_phases"] = pf.get("failures", [])
                break

    return jsonify({
        "commits": commits,
        "stats": {
            "total_commits_7d": signals.get("total_commits", 0),
            "fix_chains": len(signals.get("fix_chains", [])),
            "duplicate_slugs": len(signals.get("duplicate_slugs", [])),
            "pipeline_failures": len(signals.get("pipeline_failures", [])),
        },
    })


def _build_pipeline_data():
    """Build context dict for the pipeline partial."""
    commits = get_publish_commits(limit=10)
    signals = load_git_signals()

    fix_hashes = {fc.get("publish_hash") for fc in signals.get("fix_chains", [])}
    pipeline_failures = signals.get("pipeline_failures", [])
    pf_by_hash = {pf.get("hash"): pf for pf in pipeline_failures}

    for c in commits:
        c["fix_chain"] = c["hash"] in fix_hashes
        pf = pf_by_hash.get(c["hash"])
        if pf:
            c["status"] = pf.get("pipeline_status", "failed")
            c["failed_phases"] = pf.get("failures", [])
        else:
            c["failed_phases"] = []
        # Short timestamp for display
        try:
            ts = c.get("timestamp", "")
            c["timestamp_short"] = ts[:16].replace("T", " ") if ts else ""
        except Exception:
            c["timestamp_short"] = ""

    total_7d = signals.get("total_commits", 0)
    fail_count = len(pipeline_failures)
    success_rate = round((total_7d - fail_count) / total_7d * 100) if total_7d > 0 else 100

    return {
        "pipeline_commits": commits,
        "pipeline_stats": {
            "total_commits_7d": total_7d,
            "success_rate": success_rate,
            "fix_chains": len(signals.get("fix_chains", [])),
            "duplicate_slugs": len(signals.get("duplicate_slugs", [])),
        },
    }


@dashboard_bp.route("/partials/pipeline")
def partial_pipeline():
    """HTMX partial: pipeline health section fragment."""
    data = _build_pipeline_data()
    return render_template("partials/pipeline.html", **data)


@dashboard_bp.route("/api/dashboard/hotspots")
def hotspots():
    """Operational hotspots from ops-hotspots.json."""
    data = load_hotspots()
    return jsonify({
        "generated_at": data.get("generated_at"),
        "window": data.get("window", "7d"),
        "incidents": data.get("incidents", []),
        "top_pain": data.get("top_pain", []),
        "recovered_but_unstable": data.get("recovered_but_unstable", []),
        "codify_now": data.get("codify_now", []),
    })


def _build_hotspots_data():
    """Build context dict for the hotspots partial."""
    data = load_hotspots()
    return {
        "hotspots_generated": data.get("generated_at"),
        "hotspots_window": data.get("window", "7d"),
        "hotspots_top_pain": data.get("top_pain", [])[:5],
        "hotspots_recovered": data.get("recovered_but_unstable", []),
        "hotspots_codify": data.get("codify_now", []),
    }


@dashboard_bp.route("/partials/hotspots")
def partial_hotspots():
    """HTMX partial: operational hotspots section fragment."""
    data = _build_hotspots_data()
    return render_template("partials/hotspots.html", **data)


@dashboard_bp.route("/api/dashboard/corpus")
def corpus():
    """Corpus health from curadoria-candidates.json."""
    data = load_curadoria()
    stale = data.get("stale_candidates", 0)
    return jsonify({
        "generated_at": data.get("generated_at"),
        "total_docs": data.get("total_docs", 0),
        "stale_candidates": stale if isinstance(stale, int) else len(stale),
        "archive_auto": len(data.get("archive_auto", [])),
        "merge_review": len(data.get("merge_review", [])),
        "strengthen_targets": len(data.get("strengthen_targets", [])),
    })


def _build_corpus_data():
    """Build context dict for the corpus health partial."""
    data = load_curadoria()
    stale = data.get("stale_candidates", 0)
    return {
        "corpus_total_docs": data.get("total_docs", 0),
        "corpus_stale": stale if isinstance(stale, int) else len(stale),
        "corpus_archive": len(data.get("archive_auto", [])),
        "corpus_merge": len(data.get("merge_review", [])),
        "corpus_strengthen": len(data.get("strengthen_targets", [])),
    }


@dashboard_bp.route("/partials/corpus")
def partial_corpus():
    """HTMX partial: corpus health section fragment."""
    data = _build_corpus_data()
    return render_template("partials/corpus.html", **data)


def _build_status_strip_data():
    """Build context dict for the status strip partial."""
    signals = load_git_signals()
    heartbeat = get_heartbeat_status()
    error_pressure = get_error_pressure_24h()
    production = get_production_stats()
    claims = signals.get("claims_summary", {})
    thread_data = load_threads_enriched()
    thread_stats = thread_data.get("stats", {})

    pipeline_failures = signals.get("pipeline_failures", [])
    last_pipeline_status = "ok"
    if pipeline_failures:
        last_pipeline_status = pipeline_failures[0].get("pipeline_status", "failed")

    attention_count = 0
    if heartbeat["status"] == "stalled":
        attention_count += 1
    attention_count += len(pipeline_failures)
    if thread_stats.get("resurface_due", 0) > 0:
        attention_count += 1

    return {
        "heartbeat": heartbeat,
        "pipeline_status": last_pipeline_status,
        "pipeline_failure_count": len(pipeline_failures),
        "entries_total": production["entries_total"],
        "reports_total": production["reports_total"],
        "published_today": production["published_today"],
        "failures_24h": error_pressure["failures_24h"],
        "top_failing_tool": error_pressure["top_failing_tool"],
        "claims_total": claims.get("total_learned", 0),
        "claims_open": claims.get("total_gaps", 0),
        "threads_active_count": thread_stats.get("active", 0),
        "threads_proposed_count": thread_stats.get("proposed", 0),
        "threads_dormant_count": thread_stats.get("dormant", 0),
        "threads_resurface_due": thread_stats.get("resurface_due", 0),
        "attention_count": attention_count,
    }


@dashboard_bp.route("/partials/status-strip")
def partial_status_strip():
    """HTMX partial: expanded status strip fragment."""
    data = _build_status_strip_data()
    return render_template("partials/status_strip.html", **data)


def _build_briefing_data():
    """Build context dict for the briefing partial."""
    html_content = get_briefing_html(max_lines=50)
    return {
        "briefing_html": html_content,
        "briefing_available": html_content is not None,
    }


@dashboard_bp.route("/partials/briefing")
def partial_briefing():
    """HTMX partial: daily briefing section fragment."""
    data = _build_briefing_data()
    return render_template("partials/briefing.html", **data)


def _build_runtime_data():
    """Build context dict for runtime transparency surfaces."""
    return {
        "runtime_current_cycle": load_current_dispatch_state(),
        "runtime_recent_cycles": load_recent_dispatch_cycles(limit=6),
        "runtime_skill_evidence": load_skill_evidence_summary(limit=5),
        "runtime_primitives": load_primitive_runtime_summary(limit=5),
        "runtime_autonomy": load_autonomy_summary(),
    }


@dashboard_bp.route("/api/dashboard/runtime")
def runtime():
    """Runtime transparency read model for dispatch/evidence/primitives/autonomy."""
    return jsonify(_build_runtime_data())


@dashboard_bp.route("/partials/runtime")
def partial_runtime():
    """HTMX partial: runtime transparency section fragment."""
    data = _build_runtime_data()
    return render_template("partials/runtime.html", **data)
