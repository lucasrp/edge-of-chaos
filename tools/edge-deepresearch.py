#!/usr/bin/env python3
"""edge-deepresearch — Deep research via OpenAI and Gemini with web search.

Sends a research query to BOTH providers in parallel. Each provider uses its
native web search capability to ground responses in real, cited sources.

Providers:
  - OpenAI: Responses API with web_search tool (gpt-4o / gpt-4.1)
  - Gemini: GenerativeAI API with google_search grounding (gemini-2.5-flash / gemini-2.5-pro)

Usage:
    edge-deepresearch "What are the best B2B supplier negotiation strategies in Brazil?"
    edge-deepresearch "market size for AI-powered recruitment in LATAM" --depth comprehensive
    edge-deepresearch "topic" --provider openai          # single provider
    edge-deepresearch "topic" --provider gemini           # single provider
    edge-deepresearch "topic" --context business.md       # attach context files
    cat analysis.md | edge-deepresearch "find counter-evidence"
    edge-deepresearch "topic" --json                      # JSON output

Depth levels:
    quick:          1-2 search rounds, summary (default)
    comprehensive:  multi-angle research, cross-referenced sources, structured report

Exit codes: 0 = success, 1 = error
"""

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOG_DIR = Path.home() / "edge" / "logs" / "deepresearch"
SECRETS_DIR = Path.home() / "edge" / "secrets"

DEFAULT_OPENAI_MODEL = os.environ.get("EDGE_MODEL_DEEPRESEARCH_OPENAI", "gpt-4.1")
DEFAULT_GEMINI_MODEL = os.environ.get("EDGE_MODEL_DEEPRESEARCH_GEMINI", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_QUICK = """\
You are a senior research analyst. Your job is to deeply research the given \
topic using web search, and produce a clear, well-sourced summary.

## Process:
1. Search for the most relevant, recent information on the topic
2. Cross-reference claims across multiple sources
3. Synthesize findings into a structured summary

## Output format:
- **Key Findings** — 3-5 bullet points with the most important discoveries
- **Sources** — list each source with URL and what it contributed
- **Confidence** — HIGH / MEDIUM / LOW with brief justification

## Rules:
- ALWAYS cite sources with URLs
- Prefer recent data (last 12 months)
- Flag contradictions between sources
- PT-BR unless the topic is in English
- 300-500 words. Dense signal, no filler."""

RESEARCH_SYSTEM_COMPREHENSIVE = """\
You are a senior research analyst conducting comprehensive deep research. \
Use web search extensively to build a thorough, multi-angle analysis.

## Process:
1. **Initial scan** — broad search to map the landscape
2. **Deep dive** — targeted searches on key sub-topics
3. **Cross-reference** — verify claims across independent sources
4. **Contrarian check** — actively search for counter-evidence and opposing views
5. **Synthesis** — integrate everything into a structured report

## Output format:

### Executive Summary
2-3 sentences capturing the key insight.

### Detailed Findings
Organized by sub-topic. Each finding must cite its source.

### Data Points
Specific numbers, statistics, market sizes, dates — with sources.

### Contrarian Evidence
What sources disagree? What counter-arguments exist?

### Source Quality Assessment
Rate each major source: credibility, recency, potential bias.

### Gaps & Unknowns
What couldn't be found? What needs primary research?

## Rules:
- ALWAYS cite sources with URLs
- Search MULTIPLE angles — don't stop at the first result
- Prefer recent data (last 12 months)
- Flag contradictions explicitly
- Distinguish between hard data and opinions
- PT-BR unless the topic is in English
- 800-1500 words. Thorough but focused."""


# ---------------------------------------------------------------------------
# API Key loading
# ---------------------------------------------------------------------------

def load_openai_key() -> str:
    """Load OpenAI API key from env or secrets."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    secrets_file = SECRETS_DIR / "openai.env"
    if secrets_file.exists():
        for line in secrets_file.read_text().strip().split("\n"):
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    # Try agent-specific env var
    key = os.environ.get("AGENT_OPENAI_API_KEY")
    if key:
        return key
    return ""


def load_gemini_key() -> str:
    """Load Gemini API key from env or secrets."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key:
        return key
    secrets_file = SECRETS_DIR / "gemini.env"
    if secrets_file.exists():
        for line in secrets_file.read_text().strip().split("\n"):
            if line.startswith(("GEMINI_API_KEY=", "GOOGLE_API_KEY=")):
                return line.split("=", 1)[1].strip()
    # Try agent-specific env var
    key = os.environ.get("AGENT_GOOGLE_API_KEY")
    if key:
        return key
    return ""


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> str:
    rates = {
        # OpenAI (per 1M tokens: input, output)
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        # Gemini (per 1M tokens: input, output)
        "gemini-2.5-pro": (1.25, 10.00),
        "gemini-2.5-flash": (0.15, 0.60),
        "gemini-2.0-flash": (0.10, 0.40),
    }
    input_rate, output_rate = rates.get(model, (1.0, 4.0))
    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    return f"${cost:.4f}"


# ---------------------------------------------------------------------------
# OpenAI deep research (Responses API + web_search)
# ---------------------------------------------------------------------------

def research_openai(query: str, system: str, context: str = "",
                    model: str = None) -> dict:
    """Run deep research via OpenAI Responses API with web_search tool."""
    try:
        from openai import OpenAI
    except ImportError:
        return {"provider": "openai", "error": "openai package not installed: pip install openai"}

    api_key = load_openai_key()
    if not api_key:
        return {"provider": "openai", "error": "OPENAI_API_KEY not found"}

    model = model or DEFAULT_OPENAI_MODEL
    client = OpenAI(api_key=api_key, timeout=180)

    user_msg = query
    if context:
        user_msg = f"--- Context ---\n{context}\n\n--- Research Query ---\n{query}"

    try:
        response = client.responses.create(
            model=model,
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )

        result_text = response.output_text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = estimate_cost("openai", model, input_tokens, output_tokens)

        # Extract citations from annotations if available
        citations = []
        for item in response.output:
            if hasattr(item, "content"):
                for part in item.content if item.content else []:
                    if hasattr(part, "annotations"):
                        for ann in part.annotations if part.annotations else []:
                            if hasattr(ann, "url"):
                                citations.append({
                                    "url": ann.url,
                                    "title": getattr(ann, "title", ""),
                                })

        return {
            "provider": "openai",
            "model": model,
            "text": result_text,
            "citations": citations,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "cost": cost,
        }
    except Exception as e:
        return {"provider": "openai", "model": model, "error": str(e)}


# ---------------------------------------------------------------------------
# Gemini deep research (google_search grounding)
# ---------------------------------------------------------------------------

def research_gemini(query: str, system: str, context: str = "",
                    model: str = None) -> dict:
    """Run deep research via Gemini API with google_search grounding."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"provider": "gemini", "error": "google-genai package not installed: pip install google-genai"}

    api_key = load_gemini_key()
    if not api_key:
        return {"provider": "gemini", "error": "GEMINI_API_KEY / GOOGLE_API_KEY not found"}

    model = model or DEFAULT_GEMINI_MODEL
    client = genai.Client(api_key=api_key)

    user_msg = query
    if context:
        user_msg = f"--- Context ---\n{context}\n\n--- Research Query ---\n{query}"

    try:
        response = client.models.generate_content(
            model=model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            ),
        )

        result_text = response.text

        # Extract grounding metadata (citations)
        citations = []
        if hasattr(response, "candidates") and response.candidates:
            candidate = response.candidates[0]
            grounding = getattr(candidate, "grounding_metadata", None)
            if grounding:
                chunks = getattr(grounding, "grounding_chunks", []) or []
                for chunk in chunks:
                    web = getattr(chunk, "web", None)
                    if web:
                        citations.append({
                            "url": getattr(web, "uri", ""),
                            "title": getattr(web, "title", ""),
                        })

        # Token usage
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0
        cost = estimate_cost("gemini", model, input_tokens, output_tokens)

        return {
            "provider": "gemini",
            "model": model,
            "text": result_text,
            "citations": citations,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "cost": cost,
        }
    except Exception as e:
        return {"provider": "gemini", "model": model, "error": str(e)}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_research(query: str, depth: str, results: list[dict]):
    """Log research results for audit trail."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "query": query[:500],
        "depth": depth,
        "results": [
            {
                "provider": r.get("provider"),
                "model": r.get("model"),
                "cost": r.get("cost"),
                "tokens": r.get("tokens"),
                "citations_count": len(r.get("citations", [])),
                "text_preview": r.get("text", "")[:500],
                "error": r.get("error"),
            }
            for r in results
        ],
    }
    log_file = LOG_DIR / f"{timestamp}.json"
    log_file.write_text(json.dumps(log_entry, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_markdown(query: str, depth: str, results: list[dict]) -> str:
    """Format research results as structured markdown."""
    lines = [
        f"## Deep Research — \"{query}\"",
        f"**Depth:** {depth} | **Providers:** {', '.join(r.get('provider', '?') for r in results)}",
        "",
    ]

    for r in results:
        provider = r.get("provider", "unknown")
        model = r.get("model", "unknown")

        if r.get("error"):
            lines.append(f"### {provider.upper()} ({model}) — ERROR")
            lines.append(f"```\n{r['error']}\n```\n")
            continue

        cost = r.get("cost", "$0.00")
        tokens = r.get("tokens", {})
        lines.append(f"### {provider.upper()} ({model})")
        lines.append(f"*Tokens: {tokens.get('total', 0)} | Cost: {cost}*\n")
        lines.append(r.get("text", "(no output)"))
        lines.append("")

        # Citations
        citations = r.get("citations", [])
        if citations:
            lines.append("#### Sources cited")
            seen = set()
            for c in citations:
                url = c.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    title = c.get("title", url)
                    lines.append(f"- [{title}]({url})")
            lines.append("")

    # Summary footer
    total_cost = sum(
        float(r.get("cost", "$0").replace("$", ""))
        for r in results if not r.get("error")
    )
    lines.append("---")
    lines.append(f"**Total cost:** ${total_cost:.4f}")

    return "\n".join(lines)


def format_json(query: str, depth: str, results: list[dict]) -> str:
    """Format research results as JSON."""
    return json.dumps({
        "query": query,
        "depth": depth,
        "timestamp": datetime.now().isoformat(),
        "results": results,
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main research function
# ---------------------------------------------------------------------------

def deep_research(query: str, depth: str = "quick", providers: list[str] = None,
                  context_files: list[str] = None, stdin_content: str = None,
                  openai_model: str = None, gemini_model: str = None) -> list[dict]:
    """Run deep research across selected providers."""
    if providers is None:
        providers = ["openai", "gemini"]

    # Build system prompt based on depth
    system = RESEARCH_SYSTEM_COMPREHENSIVE if depth == "comprehensive" else RESEARCH_SYSTEM_QUICK

    # Build context string
    context_parts = []
    if context_files:
        for f in context_files:
            p = Path(f)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                if len(content) > 12000:
                    content = content[:12000] + f"\n[... truncated, {len(content)} chars total]"
                context_parts.append(f"--- {p.name} ---\n{content}")
    if stdin_content:
        if len(stdin_content) > 12000:
            stdin_content = stdin_content[:12000] + "\n[... truncated]"
        context_parts.append(f"--- Piped input ---\n{stdin_content}")
    context = "\n\n".join(context_parts)

    # Dispatch functions
    dispatch = {
        "openai": lambda: research_openai(query, system, context, openai_model),
        "gemini": lambda: research_gemini(query, system, context, gemini_model),
    }

    results = []
    active = {p: fn for p, fn in dispatch.items() if p in providers}

    if len(active) > 1:
        # Run providers in parallel
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            futures = {pool.submit(fn): p for p, fn in active.items()}
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    results.append(future.result())
                except Exception as e:
                    results.append({"provider": provider, "error": str(e)})
    else:
        for p, fn in active.items():
            try:
                results.append(fn())
            except Exception as e:
                results.append({"provider": p, "error": str(e)})

    # Sort: openai first, then gemini
    order = {"openai": 0, "gemini": 1}
    results.sort(key=lambda r: order.get(r.get("provider", ""), 99))

    # Log
    log_research(query, depth, results)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Deep research via OpenAI (web_search) and Gemini (google_search)"
    )
    parser.add_argument("query", nargs="?", default=None,
                        help="Research question or topic")
    parser.add_argument("--depth", "-d", choices=["quick", "comprehensive"],
                        default="quick",
                        help="Research depth (default: quick)")
    parser.add_argument("--provider", "-p", choices=["openai", "gemini", "both"],
                        default="both",
                        help="Provider to use (default: both)")
    parser.add_argument("--context", "-c", nargs="+", default=None,
                        help="Context files to include")
    parser.add_argument("--openai-model", default=None,
                        help=f"OpenAI model (default: {DEFAULT_OPENAI_MODEL})")
    parser.add_argument("--gemini-model", default=None,
                        help=f"Gemini model (default: {DEFAULT_GEMINI_MODEL})")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    args = parser.parse_args()

    # Read from stdin if piped
    stdin_content = None
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()

    if not args.query and not stdin_content:
        parser.error("Provide a research query as argument or pipe content via stdin")

    query = args.query or "Research the following:"

    providers = ["openai", "gemini"] if args.provider == "both" else [args.provider]

    # Status
    print(f"Deep research: \"{query[:80]}\" (depth={args.depth}, providers={', '.join(providers)})",
          file=sys.stderr)

    results = deep_research(
        query=query,
        depth=args.depth,
        providers=providers,
        context_files=args.context,
        stdin_content=stdin_content,
        openai_model=args.openai_model,
        gemini_model=args.gemini_model,
    )

    # Output
    if args.json:
        print(format_json(query, args.depth, results))
    else:
        print(format_markdown(query, args.depth, results))

    # Print summary to stderr
    for r in results:
        if r.get("error"):
            print(f"  {r['provider']}: ERROR — {r['error'][:80]}", file=sys.stderr)
        else:
            tokens = r.get("tokens", {})
            cost = r.get("cost", "?")
            cites = len(r.get("citations", []))
            print(f"  {r['provider']} ({r.get('model', '?')}): {tokens.get('total', 0)} tokens, {cites} citations, {cost}",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
