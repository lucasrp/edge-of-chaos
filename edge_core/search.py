from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import RuntimeConfig
from .context import ContextPacket
from .util import truncate


@dataclass
class SearchResult:
    source: str
    title: str
    url: str
    summary: str


def _hn_search(query: str) -> list[SearchResult]:
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({"query": query, "tags": "story", "hitsPerPage": 3})
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return [SearchResult("hackernews", "HN request failed", "", "Hacker News source was attempted but did not respond cleanly.")]
    results = []
    for hit in payload.get("hits") or []:
        title = hit.get("title") or hit.get("story_title") or "HN result"
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        points = hit.get("points")
        summary = f"points={points}; comments={hit.get('num_comments')}"
        results.append(SearchResult("hackernews", title, link, summary))
    if not results:
        return [SearchResult("hackernews", "No HN results", "", "Hacker News was searched but returned no usable results.")]
    return results


def _exa_search(query: str) -> list[SearchResult]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return [SearchResult("exa", "Exa unavailable", "", "EXA_API_KEY not configured; source recorded as unavailable.")]
    body = {"query": query, "numResults": 3}
    request = urllib.request.Request(
        "https://api.exa.ai/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": key, "Content-Type": "application/json", "User-Agent": "edge-of-chaos/2.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return [SearchResult("exa", "Exa request failed", "", "Exa was configured but the request failed.")]
    results = []
    for item in payload.get("results") or []:
        results.append(SearchResult("exa", item.get("title") or "Exa result", item.get("url") or "", truncate(item.get("text") or "", 500)))
    return results


def _x_search(query: str) -> list[SearchResult]:
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        suffix = " XAI_API_KEY is present, but that is a Grok/xAI credential, not an X search bearer token." if os.environ.get("XAI_API_KEY") else ""
        return [SearchResult("x", "X unavailable", "", "X_BEARER_TOKEN not configured; source recorded as unavailable." + suffix)]
    terms = [
        term
        for term in re.findall(r"[A-Za-z][A-Za-z0-9]{2,}", query)
        if term.lower() not in {"current", "request", "recent", "files", "commits", "jsonl"}
    ]
    x_query = " ".join(terms[:12]) or query
    url = "https://api.twitter.com/2/tweets/search/recent?" + urllib.parse.urlencode(
        {
            "query": x_query,
            "max_results": 10,
            "tweet.fields": "created_at,public_metrics,author_id",
        }
    )
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "edge-of-chaos/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return [SearchResult("x", "X request failed", "", "X bearer token was configured, but recent search did not respond cleanly.")]
    results = []
    for item in payload.get("data") or []:
        metrics = item.get("public_metrics") or {}
        summary = truncate(item.get("text") or "", 280)
        if metrics:
            summary += f" likes={metrics.get('like_count')}; reposts={metrics.get('retweet_count')}; replies={metrics.get('reply_count')}"
        url = f"https://x.com/i/web/status/{item.get('id')}"
        results.append(SearchResult("x", "X recent search result", url, summary))
    if not results:
        return [SearchResult("x", "No X results", "", "X recent search was attempted but returned no usable results.")]
    return results[:3]


def _github_context(config: RuntimeConfig) -> list[SearchResult]:
    repos = ((config.agent.get("github") or {}).get("repos") or [])
    return [SearchResult("github", str(repo), f"https://github.com/{repo}", "Configured GitHub repository for contextual lookup.") for repo in repos[:5]]


def query_from_packet(packet: ContextPacket, hints: list[str] | None = None) -> str:
    terms = [packet.request]
    terms.extend(hints or [])
    for obs in packet.observations[:5]:
        terms.append(obs.title)
    return " ".join(terms)[:240]


def broad_search(config: RuntimeConfig, packet: ContextPacket, hints: list[str] | None = None) -> list[SearchResult]:
    query = query_from_packet(packet, hints)
    configured = {str(item.get("name")): item for item in (config.agent.get("sources") or []) if isinstance(item, dict) and item.get("enabled", True)}
    results: list[SearchResult] = []
    if "exa" in configured:
        results.extend(_exa_search(query))
    if "hackernews" in configured:
        results.extend(_hn_search(query))
    if "x" in configured:
        results.extend(_x_search(query))
    if "github" in configured:
        results.extend(_github_context(config))
    if not results:
        results.append(SearchResult("local", "No external sources configured", "", "Broad search fell back to local context only."))
    return results
