from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .context import ContextPacket
from .llm_client import LLMClient
from .util import truncate

_LOCAL_COMMAND_PREFIXES = ("git ", "rg ", "grep ", "find ", "ls ", "sed ", "head ")
_WORKSPACE_TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt", ".sh", ".log", ".csv"}
_MAX_DIRECT_WORKSPACE_READS = 12
_PATHLIKE_RE = re.compile(r"(?P<path>(?:~|/|\.\.?/)?[A-Za-z0-9_.~/*?\[\]+=-]+(?:/[A-Za-z0-9_.~/*?\[\]+=-]+)+)")


@dataclass
class SearchResult:
    source: str
    title: str
    url: str
    summary: str
    query: str = ""
    status: str = "retrieved"
    round_index: int = 0
    fetch_status: str = "not_fetched"
    fetched_excerpt: str = ""
    reading_note: dict[str, Any] | None = None


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._ignore_depth = 0
        self._capture_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"}:
            self._ignore_depth += 1
        elif lower == "title":
            self._capture_title = True
        elif lower in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "div", "section", "article"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "noscript"} and self._ignore_depth:
            self._ignore_depth -= 1
        elif lower == "title":
            self._capture_title = False
        elif lower in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "div", "section", "article"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._capture_title:
            self.title_parts.append(text)
        self.text_parts.append(text)

    def extract(self) -> tuple[str, str]:
        title = " ".join(self.title_parts).strip()
        text = " ".join(self.text_parts)
        text = re.sub(r"\s+", " ", text).strip()
        return title, text


def _artifact(
    source: str,
    title: str,
    url: str,
    summary: str,
    *,
    query: str,
    status: str,
    round_index: int,
) -> SearchResult:
    return SearchResult(
        source=source,
        title=title,
        url=url,
        summary=summary,
        query=query,
        status=status,
        round_index=round_index,
    )


def _hn_search(query: str, *, round_index: int) -> list[SearchResult]:
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode({"query": query, "tags": "story", "hitsPerPage": 3})
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return [_artifact("hackernews", "HN request failed", "", "Hacker News source was attempted but did not respond cleanly.", query=query, status="failed", round_index=round_index)]
    results: list[SearchResult] = []
    for hit in payload.get("hits") or []:
        title = hit.get("title") or hit.get("story_title") or "HN result"
        link = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        points = hit.get("points")
        summary = f"points={points}; comments={hit.get('num_comments')}"
        results.append(_artifact("hackernews", title, link, summary, query=query, status="retrieved", round_index=round_index))
    if not results:
        return [_artifact("hackernews", "No HN results", "", "Hacker News was searched but returned no usable results.", query=query, status="no_results", round_index=round_index)]
    return results


def _exa_search(query: str, *, round_index: int) -> list[SearchResult]:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return [_artifact("exa", "Exa unavailable", "", "EXA_API_KEY not configured; source recorded as unavailable.", query=query, status="unavailable", round_index=round_index)]
    body = {"query": query, "numResults": 4}
    request = urllib.request.Request(
        "https://api.exa.ai/search",
        data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": key, "Content-Type": "application/json", "User-Agent": "edge-of-chaos/2.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = f"HTTP {exc.code}"
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except OSError:
            body = ""
        if exc.code == 402 and "exceeded your credits limit" in body.lower():
            detail = "Exa credits exhausted"
        return [_artifact("exa", "Exa request failed", "", f"Exa was configured but the request failed: {detail}.", query=query, status="failed", round_index=round_index)]
    except Exception:
        return [_artifact("exa", "Exa request failed", "", "Exa was configured but the request failed.", query=query, status="failed", round_index=round_index)]
    results = []
    for item in payload.get("results") or []:
        results.append(
            _artifact(
                "exa",
                item.get("title") or "Exa result",
                item.get("url") or "",
                truncate(item.get("text") or "", 500),
                query=query,
                status="retrieved",
                round_index=round_index,
            )
        )
    if not results:
        return [_artifact("exa", "No Exa results", "", "Exa was searched but returned no usable results.", query=query, status="no_results", round_index=round_index)]
    return results


def _x_search(query: str, *, round_index: int) -> list[SearchResult]:
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        suffix = " XAI_API_KEY is present, but that is a Grok/xAI credential, not an X search bearer token." if os.environ.get("XAI_API_KEY") else ""
        return [_artifact("x", "X unavailable", "", "X_BEARER_TOKEN not configured; source recorded as unavailable." + suffix, query=query, status="unavailable", round_index=round_index)]
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
        return [_artifact("x", "X request failed", "", "X bearer token was configured, but recent search did not respond cleanly.", query=query, status="failed", round_index=round_index)]
    results = []
    for item in payload.get("data") or []:
        metrics = item.get("public_metrics") or {}
        summary = truncate(item.get("text") or "", 280)
        if metrics:
            summary += f" likes={metrics.get('like_count')}; reposts={metrics.get('retweet_count')}; replies={metrics.get('reply_count')}"
        link = f"https://x.com/i/web/status/{item.get('id')}"
        results.append(_artifact("x", "X recent search result", link, summary, query=query, status="retrieved", round_index=round_index))
    if not results:
        return [_artifact("x", "No X results", "", "X recent search was attempted but returned no usable results.", query=query, status="no_results", round_index=round_index)]
    return results[:3]


def _github_context(config: RuntimeConfig, query: str, *, round_index: int) -> list[SearchResult]:
    repos = ((config.agent.get("github") or {}).get("repos") or [])
    return [
        _artifact("github", str(repo), f"https://github.com/{repo}", "Configured GitHub repository for contextual lookup.", query=query, status="context", round_index=round_index)
        for repo in repos[:5]
    ]


def _is_local_command_hint(value: str) -> bool:
    lowered = value.strip().lower()
    return any(lowered.startswith(prefix) for prefix in _LOCAL_COMMAND_PREFIXES)


def _normalized_query_hint(value: str) -> str:
    hint = re.sub(r"\s+", " ", value.strip())
    if not hint:
        return ""
    if _is_local_command_hint(hint):
        return ""
    if hint[0] in "{[":
        return ""
    if "path/to" in hint or ("{" in hint and "}" in hint and ":" in hint):
        return ""
    return truncate(hint, 140)


def query_from_packet(packet: ContextPacket, hints: list[str] | None = None) -> str:
    terms = [packet.request]
    if packet.operator_pressure:
        terms.append(packet.operator_pressure[:220])
    for message in packet.operator_messages[:3]:
        terms.append(str(message.get("text") or "")[:180])
    for hint in hints or []:
        normalized = _normalized_query_hint(hint)
        if normalized:
            terms.append(normalized)
    for obs in packet.observations[:5]:
        terms.append(obs.title)
    return " ".join(term for term in terms if term).strip()[:240]


def _local_authoritative_context(packet: ContextPacket, query: str, *, round_index: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in packet.authoritative_reads[:8]:
        excerpt = str(item.get("excerpt") or "").strip()
        if not excerpt:
            continue
        results.append(
            _artifact(
                "local-state",
                str(item.get("title") or item.get("path") or "local state"),
                str(item.get("path") or ""),
                truncate(excerpt, 500),
                query=query,
                status="context",
                round_index=round_index,
            )
        )
    return results


def _workspace_candidate_paths(packet: ContextPacket) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()
    for observation in packet.observations:
        root_text = str(observation.path or "").strip()
        if observation.source == "filesystem" and observation.title.endswith(": recent files") and root_text:
            root = Path(root_text)
            for raw_line in observation.detail.splitlines():
                relative = raw_line.strip()
                if not relative:
                    continue
                path = (root / relative).resolve()
                key = str(path)
                if key in seen or not path.is_file() or path.suffix.lower() not in _WORKSPACE_TEXT_SUFFIXES:
                    continue
                seen.add(key)
                candidates.append(path)
            continue
        if observation.source == "filesystem" and observation.title.endswith(": recent file snippets") and root_text:
            root = Path(root_text)
            for match in re.finditer(r"^##\s+(.+)$", observation.detail, flags=re.M):
                relative = match.group(1).strip()
                if not relative:
                    continue
                path = (root / relative).resolve()
                key = str(path)
                if key in seen or not path.is_file() or path.suffix.lower() not in _WORKSPACE_TEXT_SUFFIXES:
                    continue
                seen.add(key)
                candidates.append(path)
    return candidates


def _score_workspace_candidate(path: Path, query: str) -> tuple[int, int]:
    lowered_query = query.lower()
    path_text = str(path).lower()
    tokens = {token for token in re.findall(r"[a-z0-9_./-]{3,}", lowered_query) if token not in {"with", "this", "that", "from", "into"}}
    overlap = sum(1 for token in tokens if token in path_text)
    semantic_bonus = 0
    for token in ["manifest", "aggregate", "log", "chat", "operator", "experiment", "result", "dispatch", "heartbeat", "workflow", "report"]:
        if token in path_text:
            semantic_bonus += 2
    suffix_bonus = {
        ".json": 4,
        ".log": 4,
        ".md": 3,
        ".yaml": 3,
        ".yml": 3,
        ".sh": 2,
        ".py": 2,
    }.get(path.suffix.lower(), 1)
    return (overlap + semantic_bonus + suffix_bonus, len(path_text))


def _workspace_observation_reads(packet: ContextPacket, query: str, *, round_index: int) -> list[SearchResult]:
    candidates = _workspace_candidate_paths(packet)
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda path: _score_workspace_candidate(path, query), reverse=True)
    results: list[SearchResult] = []
    for path in ordered[:4]:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not content.strip():
            continue
        result = _artifact(
            "workspace-search",
            f"Workspace file: {path.name}",
            str(path),
            truncate(content, 500),
            query=query,
            status="retrieved",
            round_index=round_index,
        )
        result.fetch_status = "fetched"
        result.fetched_excerpt = truncate(content, 900)
        result.reading_note = _read_fetched_document(packet, result, content[:12000])
        results.append(result)
    return results


def _workspace_roots(config: RuntimeConfig, command: str) -> list[tuple[str, Path]]:
    workspace_first = not any(token in command for token in ["state/", "reports/", "blog/", "agent.yaml", "tools/edge"])
    workspace_roots: list[tuple[str, Path]] = []
    for item in config.agent.get("workspaces") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("path") or ".")
        path = Path(os.path.expanduser(raw))
        if not path.is_absolute():
            path = config.root / path
        workspace_roots.append((str(item.get("name") or raw), path.resolve()))
    ordered = ([("edge", config.root.resolve())] + workspace_roots) if not workspace_first else (workspace_roots + [("edge", config.root.resolve())])
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for name, path in ordered:
        key = str(path)
        if key in seen or not path.exists():
            continue
        seen.add(key)
        deduped.append((name, path))
    return deduped


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _direct_read_roots(config: RuntimeConfig) -> list[tuple[str, Path]]:
    return _workspace_roots(config, "")


def _extract_path_patterns(text: str) -> list[str]:
    patterns: list[str] = []
    for match in _PATHLIKE_RE.finditer(text):
        raw = match.group("path").strip().strip("`'\"")
        raw = raw.rstrip(".,;:)]}\"'")
        if not raw or raw.startswith("//") or "://" in raw:
            continue
        if raw not in patterns:
            patterns.append(raw)
    return patterns


def _direct_read_texts(packet: ContextPacket, hints: list[str] | None) -> list[str]:
    texts = [packet.request, packet.operator_pressure]
    texts.extend(str(message.get("text") or "") for message in packet.operator_messages[:6])
    texts.extend(str(hint) for hint in hints or [])
    for observation in packet.observations:
        if observation.source in {"operator", "async-chat"}:
            texts.append(observation.detail)
    return [text for text in texts if text]


def _expand_direct_read_pattern(raw: str, roots: list[tuple[str, Path]]) -> list[Path]:
    raw_path = Path(os.path.expanduser(raw))
    has_glob = any(char in raw for char in "*?[")
    candidates: list[Path] = []
    if raw_path.is_absolute():
        if has_glob:
            candidates.extend(Path(item) for item in sorted(Path("/").glob(str(raw_path).lstrip("/"))))
        else:
            candidates.append(raw_path)
    else:
        for _name, root in roots:
            if has_glob:
                candidates.extend(sorted(root.glob(raw)))
            else:
                candidates.append(root / raw)
    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            continue
        key = str(path)
        if key in seen or not path.exists():
            continue
        if not any(_path_is_under(path, root) for _name, root in roots):
            continue
        seen.add(key)
        resolved.append(path)
        if len(resolved) >= _MAX_DIRECT_WORKSPACE_READS:
            break
    return resolved


def _directory_summary(path: Path) -> str:
    entries: list[tuple[float, str]] = []
    try:
        for child in path.iterdir():
            try:
                stat = child.stat()
            except OSError:
                continue
            marker = "/" if child.is_dir() else ""
            entries.append((stat.st_mtime, f"{child.name}{marker}\tsize={stat.st_size}"))
    except OSError:
        return ""
    entries.sort(reverse=True)
    return "\n".join(item for _mtime, item in entries[:40])


def _read_workspace_path(packet: ContextPacket, path: Path, query: str, *, round_index: int) -> SearchResult | None:
    if path.is_dir():
        content = _directory_summary(path)
        if not content:
            return None
        title = f"Workspace directory: {path.name}"
    elif path.is_file() and path.suffix.lower() in _WORKSPACE_TEXT_SUFFIXES:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
        if not content.strip():
            return None
        title = f"Workspace file: {path.name}"
    else:
        return None
    result = _artifact(
        "workspace-read",
        title,
        str(path),
        truncate(content, 500),
        query=query,
        status="retrieved",
        round_index=round_index,
    )
    result.fetch_status = "fetched"
    result.fetched_excerpt = truncate(content, 1200)
    result.reading_note = _read_fetched_document(packet, result, content[:12000])
    return result


def _direct_workspace_reads(config: RuntimeConfig, packet: ContextPacket, hints: list[str] | None, query: str, *, round_index: int) -> list[SearchResult]:
    roots = _direct_read_roots(config)
    if not roots:
        return []
    patterns: list[str] = []
    for text in _direct_read_texts(packet, hints):
        for pattern in _extract_path_patterns(text):
            if pattern not in patterns:
                patterns.append(pattern)
    results: list[SearchResult] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in _expand_direct_read_pattern(pattern, roots):
            key = str(path)
            if key in seen:
                continue
            result = _read_workspace_path(packet, path, query, round_index=round_index)
            if not result:
                continue
            seen.add(key)
            results.append(result)
            if len(results) >= _MAX_DIRECT_WORKSPACE_READS:
                return results
    return results


def _command_hints(hints: list[str] | None) -> list[str]:
    commands: list[str] = []
    for raw in hints or []:
        command = re.sub(r"\s+", " ", raw.strip())
        if not command or not _is_local_command_hint(command):
            continue
        if any(token in command for token in ["path/to", "<path", "..."]):
            continue
        if command not in commands:
            commands.append(command)
    return commands[:4]


def _normalize_local_command(command: str) -> tuple[list[str] | None, str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None, "parse_error"
    if not tokens:
        return None, "empty_command"
    name = tokens[0]
    if name == "rg":
        pattern = ""
        paths: list[str] = []
        for token in tokens[1:]:
            if token.startswith("-"):
                continue
            if not pattern:
                pattern = token
            else:
                paths.append(token)
        if not pattern:
            return None, "rg_missing_pattern"
        return ["grep", "-RInE", pattern, *(paths or ["."])], ""
    if name in {"git", "grep", "find", "ls", "sed", "head"}:
        return tokens, ""
    return None, "unsupported_command"


def _run_local_command(argv: list[str], cwd: Path) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("GIT_PAGER", "cat")
    try:
        result = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=20, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    return result.returncode, output


def _local_workspace_search(config: RuntimeConfig, packet: ContextPacket, hints: list[str] | None, *, round_index: int) -> list[SearchResult]:
    results: list[SearchResult] = []
    for command in _command_hints(hints):
        argv, error = _normalize_local_command(command)
        if not argv:
            results.append(
                _artifact(
                    "workspace-search",
                    f"Local query skipped: {command}",
                    "",
                    f"Suggested local query was skipped: {error}.",
                    query=command,
                    status="failed",
                    round_index=round_index,
                )
            )
            continue
        roots = _workspace_roots(config, command)
        last_output = ""
        hit = False
        for root_name, root_path in roots:
            code, output = _run_local_command(argv, root_path)
            last_output = output or last_output
            if code == 0 and output:
                result = _artifact(
                    "workspace-search",
                    f"{root_name}: {command}",
                    str(root_path),
                    truncate(output, 500),
                    query=command,
                    status="retrieved",
                    round_index=round_index,
                )
                result.fetch_status = "fetched"
                result.fetched_excerpt = truncate(output, 900)
                result.reading_note = _read_fetched_document(packet, result, output[:12000])
                results.append(result)
                hit = True
                break
            if code == 1 and argv[0] == "grep":
                continue
        if hit:
            continue
        status = "failed" if last_output else "no_results"
        summary = last_output or f"Executed locally across {len(roots)} roots and found no matching evidence."
        results.append(
            _artifact(
                "workspace-search",
                f"Local search: {command}",
                "",
                truncate(summary, 500),
                query=command,
                status=status,
                round_index=round_index,
            )
        )
    return results


def _fetch_candidates(results: list[SearchResult]) -> list[tuple[int, SearchResult]]:
    candidates: list[tuple[int, SearchResult]] = []
    for index, result in enumerate(results):
        if result.status != "retrieved":
            continue
        if result.source not in {"exa", "hackernews", "x", "github"}:
            continue
        if result.source == "x" and result.summary:
            candidates.append((index, result))
            continue
        parsed = urllib.parse.urlparse(result.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            candidates.append((index, result))
    return candidates


def _select_fetch_targets(packet: ContextPacket, results: list[SearchResult], query: str, *, round_index: int) -> list[int]:
    candidates = _fetch_candidates(results)
    if not candidates:
        return []
    compact = [
        {
            "index": index,
            "source": result.source,
            "title": result.title,
            "url": result.url,
            "summary": truncate(result.summary, 220),
        }
        for index, result in candidates[:12]
    ]
    client = LLMClient(role="search")
    llm = client.complete_json(
        system=(
            "You are triaging search hits for a private mentor report. "
            "Choose up to 4 items whose full text should be fetched next. "
            "Prioritize items that are most likely to change the current judgement, close a named gap, or add concrete domain evidence. "
            "Ignore placeholders, availability telemetry, and redundant links. "
            "Return JSON with selected_indices and summary."
        ),
        prompt=json.dumps(
            {
                "round": round_index,
                "request": packet.request,
                "query": query,
                "observations": [obs.__dict__ for obs in packet.observations[:6]],
                "candidates": compact,
            },
            ensure_ascii=False,
        )[:18000],
    )
    if isinstance(llm, dict):
        picked: list[int] = []
        for raw in llm.get("selected_indices") or []:
            try:
                value = int(raw)
            except (TypeError, ValueError):
                continue
            if any(candidate_index == value for candidate_index, _result in candidates):
                picked.append(value)
        deduped: list[int] = []
        for value in picked:
            if value not in deduped:
                deduped.append(value)
        if deduped:
            return deduped[:4]
    dedup_urls: set[str] = set()
    chosen: list[int] = []
    priority = {"exa": 0, "github": 1, "hackernews": 2, "x": 3}
    for index, result in sorted(candidates, key=lambda item: (priority.get(item[1].source, 9), item[0])):
        key = result.url or f"{result.source}:{result.title}"
        if key in dedup_urls:
            continue
        dedup_urls.add(key)
        chosen.append(index)
        if len(chosen) >= 4:
            break
    return chosen


def _fetch_url_text(url: str) -> tuple[str, str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "edge-of-chaos/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(250000)
    except Exception as exc:
        return "", "", f"fetch:{type(exc).__name__}"
    text = body.decode("utf-8", errors="ignore")
    if "html" in content_type.lower():
        parser = _HTMLTextExtractor()
        try:
            parser.feed(text)
        except Exception:
            pass
        title, article_text = parser.extract()
        return title, truncate(article_text, 12000), ""
    if "json" in content_type.lower():
        try:
            payload = json.loads(text)
            pretty = json.dumps(payload, ensure_ascii=False, indent=2)
            return "", truncate(pretty, 12000), ""
        except json.JSONDecodeError:
            return "", truncate(text, 12000), ""
    return "", truncate(re.sub(r"\s+", " ", text).strip(), 12000), ""


def _read_fetched_document(packet: ContextPacket, result: SearchResult, content: str) -> dict[str, Any]:
    client = LLMClient(role="search")
    llm = client.complete_json(
        system=(
            "You are reading one fetched source for a private mentor report. "
            "Extract only what materially changes the beat. "
            "Return JSON with summary, why_it_matters, useful_claims (max 4), tensions (max 2), and confidence."
        ),
        prompt=json.dumps(
            {
                "request": packet.request,
                "kind": packet.kind,
                "source": result.source,
                "title": result.title,
                "url": result.url,
                "query": result.query,
                "context": [obs.__dict__ for obs in packet.observations[:6]],
                "content": content[:12000],
            },
            ensure_ascii=False,
        )[:18000],
    )
    if isinstance(llm, dict):
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        return llm
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    useful = [truncate(sentence, 240) for sentence in sentences[:3] if sentence.strip()]
    return {
        "summary": truncate(content, 280),
        "why_it_matters": "Fetched content was available, but no LLM reading note could be produced.",
        "useful_claims": useful,
        "tensions": [],
        "confidence": "low",
        "_llm_provider": client.last_provider,
        "_llm_error": client.last_error or "llm:no-reading-note",
    }


def _enrich_with_fetch(packet: ContextPacket, results: list[SearchResult], query: str, *, round_index: int) -> list[SearchResult]:
    selected = _select_fetch_targets(packet, results, query, round_index=round_index)
    for index in selected:
        result = results[index]
        if result.source == "x":
            content = result.summary
            result.fetch_status = "fetched"
            result.fetched_excerpt = truncate(content, 900)
            result.reading_note = _read_fetched_document(packet, result, content)
            continue
        title, content, error = _fetch_url_text(result.url)
        if error or not content:
            result.fetch_status = "fetch_failed"
            result.fetched_excerpt = truncate(error or "fetch produced empty content", 280)
            continue
        if title and title != result.title:
            result.summary = truncate(f"title={title}; {result.summary}", 500)
        result.fetch_status = "fetched"
        result.fetched_excerpt = truncate(content, 900)
        result.reading_note = _read_fetched_document(packet, result, content)
    digest = _synthesize_round(packet, query, results, round_index=round_index)
    if digest:
        results.append(digest)
    return results


def _synthesize_round(packet: ContextPacket, query: str, results: list[SearchResult], *, round_index: int) -> SearchResult | None:
    fetched = [result for result in results if result.fetch_status == "fetched" and result.reading_note]
    if not fetched:
        return None
    client = LLMClient(role="search")
    llm = client.complete_json(
        system=(
            "You are synthesizing fetched evidence for the next mentor-report step. "
            "Read the per-document notes and return JSON with summary, evidence_worth_using (max 5 bullets), "
            "tensions (max 3), and missing_next_reads (max 4)."
        ),
        prompt=json.dumps(
            {
                "round": round_index,
                "request": packet.request,
                "query": query,
                "documents": [
                    {
                        "source": result.source,
                        "title": result.title,
                        "url": result.url,
                        "summary": result.summary,
                        "reading_note": result.reading_note,
                    }
                    for result in fetched[:4]
                ],
            },
            ensure_ascii=False,
        )[:18000],
    )
    if isinstance(llm, dict):
        llm["_llm_provider"] = client.last_provider
        if client.last_error:
            llm["_llm_error"] = client.last_error
        summary = str(llm.get("summary") or "Fetched search evidence was synthesized for the next report step.")
        return SearchResult(
            source="search-digest",
            title=f"Round {round_index} reading synthesis",
            url="",
            summary=summary,
            query=query,
            status="synthesized",
            round_index=round_index,
            fetch_status="fetched",
            fetched_excerpt=truncate(
                "\n".join(str(item) for item in (llm.get("evidence_worth_using") or [])[:5]),
                900,
            ),
            reading_note=llm,
        )
    summary = "Fetched sources were available and should inform the next report draft, but no cross-document synthesis was produced."
    return SearchResult(
        source="search-digest",
        title=f"Round {round_index} reading synthesis",
        url="",
        summary=summary,
        query=query,
        status="synthesized",
        round_index=round_index,
        fetch_status="fetched",
        fetched_excerpt="",
        reading_note={"summary": summary, "_llm_provider": client.last_provider, "_llm_error": client.last_error or "llm:no-search-digest"},
    )


def broad_search(config: RuntimeConfig, packet: ContextPacket, hints: list[str] | None = None, *, round_index: int = 1) -> list[SearchResult]:
    query = query_from_packet(packet, hints)
    configured = {str(item.get("name")): item for item in (config.agent.get("sources") or []) if isinstance(item, dict) and item.get("enabled", True)}
    results: list[SearchResult] = _local_authoritative_context(packet, query, round_index=round_index)
    results.extend(_direct_workspace_reads(config, packet, hints, query, round_index=round_index))
    results.extend(_workspace_observation_reads(packet, query, round_index=round_index))
    results.extend(_local_workspace_search(config, packet, hints, round_index=round_index))
    if "exa" in configured:
        results.extend(_exa_search(query, round_index=round_index))
    if "hackernews" in configured:
        results.extend(_hn_search(query, round_index=round_index))
    if "x" in configured:
        results.extend(_x_search(query, round_index=round_index))
    if "github" in configured:
        results.extend(_github_context(config, query, round_index=round_index))
    if not results:
        results.append(_artifact("local", "No external sources configured", "", "Broad search fell back to local context only.", query=query, status="fallback", round_index=round_index))
    return _enrich_with_fetch(packet, results, query, round_index=round_index)
