from __future__ import annotations

import json
import os
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
        headers={"x-api-key": key, "Content-Type": "application/json"},
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
    if not os.environ.get("X_BEARER_TOKEN"):
        return [SearchResult("x", "X unavailable", "", "X_BEARER_TOKEN not configured; source recorded as unavailable.")]
    return [SearchResult("x", "X configured", "", "X search adapter is intentionally read-only placeholder in v2 initial core.")]


def _github_context(config: RuntimeConfig) -> list[SearchResult]:
    repos = ((config.agent.get("github") or {}).get("repos") or [])
    return [SearchResult("github", str(repo), f"https://github.com/{repo}", "Configured GitHub repository for contextual lookup.") for repo in repos[:5]]


def query_from_packet(packet: ContextPacket) -> str:
    terms = [packet.request]
    for obs in packet.observations[:5]:
        terms.append(obs.title)
    return " ".join(terms)[:240]


def broad_search(config: RuntimeConfig, packet: ContextPacket) -> list[SearchResult]:
    query = query_from_packet(packet)
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
