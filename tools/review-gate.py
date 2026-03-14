#!/usr/bin/env python3
"""
review-gate — Quality gate for YAML report specs.

Three-phase pipeline with 2 hardcoded improvement rounds:
  Phase 1 (co-author): GPT with tools enriches/generates YAML draft
  Phase 2 (review+refine loop): Reviewer evaluates → Refiner rewrites YAML → repeat 2x
  Result: improved YAML written back to file

Usage:
    review-gate spec.yaml                          # Full pipeline (co-author + 2x review/refine)
    review-gate spec.yaml --review-only            # Review only (no co-authoring, no refinement)
    review-gate spec.yaml --coauthor-only          # Co-author only (no review)
    review-gate spec.yaml --entry blog-entry.md    # Include blog entry for consistency
    review-gate spec.yaml --skill pesquisa         # Include skill-specific rules
    review-gate spec.yaml --brief "autonomia #10, slack + pipeline + identity"
    review-gate spec.yaml --rounds 1               # Override: only 1 improvement round

Exit codes: 0 = pass, 1 = fail (after all rounds), 2 = error
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai package required: pip install openai")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent

# Load agent name from branding config
sys.path.insert(0, str(SCRIPT_DIR.parent / "config"))
try:
    from branding import load_branding
    _AGENT_NAME = load_branding().get("agent_name", "agent")
except Exception:
    _AGENT_NAME = "agent"
RUBRIC_PATH = Path.home() / ".claude/skills/_shared/report-template.md"
BLOG_RULES_PATH = Path.home() / ".claude/skills/ed-blog/SKILL.md"
SKILLS_DIR = Path.home() / ".claude/skills"
SECRETS_PATH = Path.home() / "edge/secrets/openai.env"
XAI_SECRETS_PATH = Path.home() / "edge/secrets/xai.env"
XAI_BASE_URL = "https://api.x.ai/v1"
GROK_MODEL = "grok-4.20-multi-agent-beta-0309"
_MEMORY_PROJECT = load_branding().get("memory_project_dir", "") if 'load_branding' in dir() else ""
if _MEMORY_PROJECT:
    MEMORY_DIR = Path.home() / ".claude/projects" / _MEMORY_PROJECT / "memory"
else:
    # Auto-detect: first project dir
    _proj_base = Path.home() / ".claude/projects"
    _candidates = [d for d in _proj_base.iterdir() if d.is_dir()] if _proj_base.exists() else []
    MEMORY_DIR = _candidates[0] / "memory" if _candidates else _proj_base / "memory"
REPORTS_DIR = Path.home() / "edge/reports"
NOTES_DIR = Path.home() / "edge/notes"

DEFAULT_MODEL = "gpt-5.4"

# ---------------------------------------------------------------------------
# Tool definitions for co-author phase
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": (
                "Read an agent memory file. Available files: "
                "debugging.md (recurring errors and lessons), "
                "personality.md (agent identity, tone, communication style), "
                "insights.md (user direction, preferences, corrections), "
                "metodo.md (Feynman method, derivation-first approach), "
                "working-state.md (current work context, timeline, active threads), "
                "breaks-active.md (last 5 research breaks). "
                "Use to enrich the YAML with relevant context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {
                        "type": "string",
                        "enum": [
                            "debugging.md", "personality.md", "insights.md",
                            "metodo.md", "working-state.md", "breaks-active.md",
                        ],
                        "description": "Memory file to read",
                    }
                },
                "required": ["file"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_previous_report",
            "description": (
                "Get the YAML spec of the most recent previous report on a topic. "
                "Searches ~/edge/reports/*.yaml for the best match. "
                "Use to check continuity, whether gaps were addressed, evolution over time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic keyword to search for (e.g. 'autonomia', 'pesquisa-llm', 'ssh')",
                    }
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_corpus",
            "description": (
                "Search the agent's knowledge base (~1200 docs) using hybrid search "
                "(FTS + embeddings). Returns top matches with title, path, and snippet. "
                "Use to find related prior work, verify claims, enrich linhagem."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (natural language or keywords)",
                    },
                    "k": {
                        "type": "integer",
                        "description": "Number of results (default 5, max 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_blog_entries",
            "description": (
                "Read recent blog entries, optionally filtered by tag. "
                "Returns title, date, tag, and content of each entry. "
                "Use to check what was recently published, find connections."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tag": {
                        "type": "string",
                        "description": "Filter by tag (pesquisa, descoberta, reflexao, etc.). Empty = all.",
                        "default": "",
                    },
                    "n": {
                        "type": "integer",
                        "description": "Number of recent entries to return (default 3, max 5)",
                        "default": 3,
                    },
                },
                "required": [],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_read_memory(file: str) -> str:
    """Read a memory file."""
    path = MEMORY_DIR / file
    if not path.exists():
        return f"File not found: {file}"
    content = path.read_text(encoding="utf-8")
    # Truncate to ~4K chars to keep context reasonable
    if len(content) > 4000:
        content = content[:4000] + f"\n\n[... truncated, {len(content)} chars total]"
    return content


def _tool_get_previous_report(topic: str) -> str:
    """Find and return the most recent previous report YAML on a topic."""
    yaml_files = sorted(REPORTS_DIR.glob("*.yaml"), key=lambda p: p.name, reverse=True)
    topic_lower = topic.lower()
    for yf in yaml_files[:50]:  # Check last 50
        if topic_lower in yf.name.lower():
            content = yf.read_text(encoding="utf-8")
            if len(content) > 6000:
                content = content[:6000] + f"\n\n[... truncated, {len(content)} chars total]"
            return f"Found: {yf.name}\n\n{content}"
    return f"No previous report found matching '{topic}'"


def _tool_search_corpus(query: str, k: int = 5) -> str:
    """Search the corpus using edge-search."""
    k = min(k, 10)
    try:
        result = subprocess.run(
            ["edge-search", query, "-k", str(k)],
            capture_output=True, text=True, timeout=15,
        )
        return result.stdout[:4000] if result.stdout else "No results found"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "edge-search not available"


def _tool_read_blog_entries(tag: str = "", n: int = 3) -> str:
    """Read recent blog entries."""
    n = min(n, 5)
    entries_dir = Path.home() / "edge/blog/entries"
    if not entries_dir.exists():
        return "Blog entries directory not found"

    files = sorted(entries_dir.glob("*.md"), key=lambda p: p.name, reverse=True)
    results = []
    for f in files:
        if len(results) >= n:
            break
        content = f.read_text(encoding="utf-8")
        # Parse frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            continue
        fm = parts[1].strip()
        body = parts[2].strip()[:500]

        if tag:
            # Check if tag matches (handle both tag: and tags: formats)
            tag_lower = tag.lower()
            if tag_lower not in fm.lower():
                continue

        results.append(f"### {f.name}\n```yaml\n{fm}\n```\n{body}\n")

    return "\n---\n".join(results) if results else f"No entries found (tag={tag})"


TOOL_DISPATCH = {
    "read_memory": lambda args: _tool_read_memory(**args),
    "get_previous_report": lambda args: _tool_get_previous_report(**args),
    "search_corpus": lambda args: _tool_search_corpus(**args),
    "read_blog_entries": lambda args: _tool_read_blog_entries(**args),
}


# ---------------------------------------------------------------------------
# Evaluation dimensions (for reviewer phase)
# ---------------------------------------------------------------------------

DIMENSIONS = {
    "structural_completeness": (
        "Required sections present: linhagem (first section), "
        "'O que Nao Sei' (penultimate), glossario (last), "
        "executive_summary, metrics, bibliography. "
        "All blocks use valid types from the report template."
    ),
    "content_depth": (
        "Sections have substance, not placeholders. "
        "Concrete details, data, numbers, real examples. "
        "No empty sections or stub content. "
        "Tables have real data, not lorem ipsum."
    ),
    "storytelling": (
        "The report tells a STORY, not just presents information. "
        "There is a narrative arc: setup (why this matters) → tension (the problem/question) "
        "→ exploration (what was tried/discovered) → resolution (what changed). "
        "Sections flow into each other with cause-effect or temporal logic. "
        "The reader should want to keep reading — not just scanning headers. "
        "The title and executive_summary hook the reader. "
        "Analogies and concrete scenarios make abstract ideas tangible. "
        "The conclusion connects back to the opening — the arc closes."
    ),
    "feynman_method": (
        "Evidence of derivation-first thinking: the author tried to reason from "
        "first principles BEFORE searching or citing external sources. "
        "Gaps in understanding are explicitly marked (gap-marker, gap-table, [GAP] tags). "
        "The report shows WHERE the author's knowledge stopped and research began. "
        "Explanations are written as if teaching someone intelligent but unfamiliar. "
        "No jargon without definition. Analogies used to test understanding. "
        "The process of thinking is visible — not just conclusions. "
        "If the report has a 'Derivacao' or equivalent section, it contains genuine "
        "reasoning steps (not just restating known facts). "
        "Uncertainty is quantified or bounded, not hand-waved."
    ),
    "writing_quality": (
        "Text in paragraph blocks is fluido (flowing prose), not telegráfico "
        "(bullet-point-only). Transitions between ideas. "
        "Reflective tone, not didactic or robotic. "
        "Blockquotes sound like crystallized thoughts. "
        "Titles are evocative, not descriptive."
    ),
    "visualization": (
        "At least 1 SVG visualization (inline in raw-html block). "
        "Data tables paired with charts when 3+ values compared. "
        "Diagrams where relationships/flows communicate better visually. "
        "SVG follows standards: viewBox, font-family, semantic colors."
    ),
    "intellectual_honesty": (
        "'O que Nao Sei' section has genuine, specific gaps — not boilerplate. "
        "Uncertainty stated clearly. Blind spots acknowledged. "
        "Assumptions marked as untested. gap-table with real IDs and descriptions. "
        "callout danger/warning for critical unknowns."
    ),
    "internal_consistency": (
        "Executive summary matches section content. "
        "Metrics match what's reported in sections. "
        "Title matches actual scope. Numbers consistent throughout. "
        "Linhagem references real prior work, not generic placeholders. "
        "Blog entry (if provided) is consistent with report content."
    ),
    "didactic_clarity": (
        "Every concept, acronym, and technical term is explained on first use. "
        "The reader should NEVER have to guess what a term means. "
        "Specific checks: "
        "(1) Acronyms expanded on first mention (e.g. 'MECE (Mutuamente Exclusivo, Coletivamente Exaustivo)'). "
        "(2) Domain jargon defined inline or in glossary (e.g. 'nuggets', 'Sheridan level', 'heartbeat'). "
        "(3) Tool/system names explained with what they DO, not just what they ARE "
        "(e.g. 'edge-search (busca semantica no corpus de 1300+ documentos)', not just 'edge-search'). "
        "(4) Concept boxes (concept-grid) used for new ideas — with analogy + practical definition. "
        "(5) The glossary section is not a dump of terms — each entry has a definition a newcomer can understand. "
        "(6) Numbers have context (e.g. '47% coverage' means nothing without '47% of nuggets were found in agent output'). "
        "Score 5 = a smart person unfamiliar with the project can read and understand everything. "
        "Score 3 = most things explained, a few insider terms slip through. "
        "Score 1 = reads like internal notes — full of unexplained jargon."
    ),
}

# Weights for weighted average (must match DIMENSIONS order and sum to 1.0)
# structural 15%, depth 15%, storytelling 12%, feynman 12%,
# didactic 12%, writing 8%, visualization 8%, honesty 10%, consistency 8%
DIMENSION_WEIGHTS = [0.15, 0.15, 0.12, 0.12, 0.08, 0.08, 0.10, 0.08, 0.12]

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

COAUTHOR_SYSTEM = f"""You are a co-author helping an autonomous AI agent ({_AGENT_NAME}) improve a YAML report specification before publication. The YAML will be converted to an HTML report, published to an internal blog, and indexed into long-term memory.

Your role: ENRICH the YAML by pulling relevant context using your tools. You are NOT rewriting from scratch — you are adding what's missing, deepening what's shallow, and connecting to prior work.

Language: Portuguese (PT-BR).

## What to do:
1. Read the YAML spec carefully
2. Use your tools to pull relevant context (memory files, previous reports, corpus search, blog entries)
3. Return a JSON object with specific, actionable enrichments

## Report Template Rules
{rubric}

## Blog Writing Style Rules
{blog_rules}

{skill_rules}

## Tools available:
- read_memory: Read agent memory files (debugging.md, personality.md, insights.md, metodo.md, working-state.md, breaks-active.md)
- get_previous_report: Get previous report YAML on same topic (for continuity)
- search_corpus: Search ~1200 docs for related work
- read_blog_entries: Read recent blog entries (for connections)

## Process:
1. First, identify what the YAML is about and what context might help
2. Call tools to gather relevant context (be selective — only pull what's useful)
3. Return JSON with enrichments

## Output Format (JSON only, no markdown):
{{
  "tools_called": ["list of tools used"],
  "context_gathered": "brief summary of what you found",
  "enrichments": [
    {{
      "section": "section title or 'executive_summary' or 'new_section'",
      "action": "add|replace|deepen|connect",
      "target": "specific block or field to modify",
      "content": "the actual content to add/replace",
      "reason": "why this enrichment matters"
    }}
  ],
  "missing_connections": ["things the YAML should reference but doesn't"],
  "factual_issues": ["any claims in the YAML that contradict what you found in context"]
}}
"""

REVIEWER_SYSTEM = f"""You are a quality reviewer for YAML report specifications used by an autonomous AI agent ({_AGENT_NAME}). These specs get converted to HTML reports via yaml_to_html.py, published to an internal blog, and indexed into long-term memory.

Your job: evaluate the YAML spec against the rubric and provide structured, SPECIFIC feedback. Cite section titles, block types, and exact content when pointing out issues. Your feedback will be used by the agent to improve the spec in a self-refinement loop.

IMPORTANT: You are evaluating the artifact AS-IS. You have no tools and no external context. Judge only what's in front of you. If a claim seems unverified, flag it. If context seems missing, note it.

Language: respond in Portuguese (PT-BR).

## Evaluation Dimensions

{dimensions}

## Report Template Rules

{rubric}

## Blog Writing Style Rules

{blog_rules}

{skill_rules}

## Scoring Scale

Rate each dimension 0-5:
- 0: Completely missing or broken
- 1: Present but severely deficient — major rework needed
- 2: Below minimum bar — significant issues
- 3: Meets minimum bar — acceptable with minor fixes
- 4: Good quality — minor suggestions only
- 5: Excellent — no issues found

## Critical Issues (blocking)

Flag as critical_issues if ANY of these:
- Required section completely missing (linhagem, "O que Nao Sei", glossario)
- executive_summary or metrics missing at top level
- Empty sections (title present but no blocks/content)
- Zero SVG visualizations in entire spec
- "O que Nao Sei" is clearly boilerplate (vague generic text, not specific to this report's topic)
- Sections reference data/events not present elsewhere in the spec (internal contradiction)
- Blog entry says one thing, report says another (if blog entry provided)
- 3+ acronyms or technical terms used without any explanation (reader cannot understand the report)
- Glossary section missing or contains terms without definitions

## Output Format

Respond with ONLY valid JSON (no markdown fences, no text outside JSON):
{{
  "pass": true/false,
  "overall": 0.0,
  "dimensions": {{
    "structural_completeness": {{"score": 0, "feedback": "..."}},
    "content_depth": {{"score": 0, "feedback": "..."}},
    "storytelling": {{"score": 0, "feedback": "..."}},
    "feynman_method": {{"score": 0, "feedback": "..."}},
    "writing_quality": {{"score": 0, "feedback": "..."}},
    "visualization": {{"score": 0, "feedback": "..."}},
    "intellectual_honesty": {{"score": 0, "feedback": "..."}},
    "internal_consistency": {{"score": 0, "feedback": "..."}},
    "didactic_clarity": {{"score": 0, "feedback": "..."}}
  }},
  "critical_issues": [],
  "suggestions": []
}}

Rules for pass/fail:
- pass = true ONLY when: ALL dimensions >= 3 AND zero critical_issues AND overall >= {threshold}
- overall = weighted average (structural 15%, depth 15%, storytelling 12%, feynman 12%, didactic 12%, writing 8%, visualization 8%, honesty 10%, consistency 8%)
- suggestions: 3-7 specific, actionable improvements
"""


REFINER_SYSTEM = """You are a YAML report spec editor. You receive a YAML report spec and reviewer feedback (scores + issues + suggestions). Your job: APPLY the feedback by rewriting the YAML.

Language: Portuguese (PT-BR). Output: ONLY the complete, corrected YAML. No markdown fences, no commentary, no explanation — just the YAML content.

## Rules:
- Fix ALL critical_issues first — these are blockers
- Address suggestions where possible (skip if genuinely inapplicable)
- Do NOT remove existing good content — only add, improve, or restructure
- Preserve the YAML structure (title, subtitle, date, executive_summary, metrics, sections, bibliography)
- If the reviewer says a section is shallow, DEEPEN it with concrete content (not lorem ipsum)
- If an SVG is missing and the reviewer flagged it, add a simple but real SVG visualization
- If "O que Nao Sei" is flagged as boilerplate, rewrite with genuine, specific gaps
- Keep all existing metadata intact (title, date, etc.)

## Report Template Rules (summary)
- Required sections: linhagem (first), "O que Nao Sei" (penultimate), glossario (last)
- Required top-level keys: executive_summary, metrics, bibliography
- At least 1 SVG visualization (inline raw-html block)
- Tables paired with charts when 3+ values compared
"""


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    if SECRETS_PATH.exists():
        for line in SECRETS_PATH.read_text().strip().split("\n"):
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: OPENAI_API_KEY not found.", file=sys.stderr)
    sys.exit(2)


def load_xai_key() -> str | None:
    """Load xAI API key. Returns None if not available (non-fatal)."""
    key = os.environ.get("XAI_API_KEY")
    if key:
        return key
    if XAI_SECRETS_PATH.exists():
        for line in XAI_SECRETS_PATH.read_text().strip().split("\n"):
            if line.startswith("XAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def get_xai_client() -> OpenAI | None:
    """Get xAI client. Returns None if key not available."""
    key = load_xai_key()
    if not key:
        return None
    return OpenAI(api_key=key, base_url=XAI_BASE_URL)


def load_rubric() -> str:
    if RUBRIC_PATH.exists():
        return RUBRIC_PATH.read_text(encoding="utf-8")
    return "(Report template not found)"


def load_blog_rules() -> str:
    if not BLOG_RULES_PATH.exists():
        return "(Blog rules not found)"
    content = BLOG_RULES_PATH.read_text(encoding="utf-8")
    lines = content.split("\n")
    in_style = False
    style_lines = []
    for line in lines:
        if "Estilo de Escrita" in line:
            in_style = True
        elif in_style and line.startswith("## ") and "Estilo" not in line:
            break
        if in_style:
            style_lines.append(line)
    return "\n".join(style_lines) if style_lines else ""


def load_skill_rules(skill_name: str) -> str:
    if not skill_name:
        return ""
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        return ""
    content = skill_path.read_text(encoding="utf-8")
    return f"\n## Skill-Specific Rules: {skill_name}\n\n{content}"


def load_entry(entry_path: str) -> str:
    if not entry_path:
        return ""
    p = Path(entry_path)
    if not p.exists():
        return ""
    return f"\n## Blog Entry Content (must be consistent with report)\n\n{p.read_text(encoding='utf-8')}"


# ---------------------------------------------------------------------------
# Phase 1: Co-author
# ---------------------------------------------------------------------------

def coauthor(yaml_path: str, skill: str = None, model: str = DEFAULT_MODEL,
             entry_path: str = None, brief: str = None) -> dict:
    """Run co-author phase with tool use. Returns enrichment suggestions."""
    api_key = load_api_key()
    client = OpenAI(api_key=api_key)

    yaml_content = Path(yaml_path).read_text(encoding="utf-8")

    system = COAUTHOR_SYSTEM.format(
        rubric=load_rubric(),
        blog_rules=load_blog_rules(),
        skill_rules=load_skill_rules(skill) if skill else "",
    )

    user_msg = f"Enrich this YAML report spec:\n\n{yaml_content}"
    if entry_path:
        entry_content = load_entry(entry_path)
        if entry_content:
            user_msg += f"\n\n---\n\nAssociated blog entry:\n{entry_content}"
    if brief:
        user_msg += f"\n\n---\n\nSession brief: {brief}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    total_prompt_tokens = 0
    total_completion_tokens = 0
    tool_calls_made = []

    # Tool-use loop (max 10 rounds)
    for _round in range(10):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
            )
        except Exception as e:
            print(f"ERROR: OpenAI API call failed: {e}", file=sys.stderr)
            sys.exit(2)

        total_prompt_tokens += response.usage.prompt_tokens
        total_completion_tokens += response.usage.completion_tokens

        msg = response.choices[0].message

        # If no tool calls, we have the final response
        if not msg.tool_calls:
            messages.append(msg)
            break

        # Process tool calls
        messages.append(msg)
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)
            tool_calls_made.append(f"{fn_name}({json.dumps(fn_args, ensure_ascii=False)})")

            print(f"  [co-author] tool: {fn_name}({', '.join(f'{k}={v!r}' for k,v in fn_args.items())})",
                  file=sys.stderr)

            handler = TOOL_DISPATCH.get(fn_name)
            if handler:
                result_text = handler(fn_args)
            else:
                result_text = f"Unknown tool: {fn_name}"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })

    # Parse final response
    content = msg.content or ""
    # Try to extract JSON from the response
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError:
                result = {"raw_response": content[:2000], "enrichments": []}
        else:
            result = {"raw_response": content[:2000], "enrichments": []}

    # Usage tracking
    class _Usage:
        def __init__(self, p, c):
            self.prompt_tokens = p
            self.completion_tokens = c

    result["_meta"] = {
        "phase": "co-author",
        "model": model,
        "tool_calls": tool_calls_made,
        "tokens": {
            "prompt": total_prompt_tokens,
            "completion": total_completion_tokens,
            "total": total_prompt_tokens + total_completion_tokens,
        },
        "cost_estimate": _estimate_cost(model, _Usage(total_prompt_tokens, total_completion_tokens)),
    }

    return result


# ---------------------------------------------------------------------------
# Phase 2: Reviewer (no tools, evaluates blind)
# ---------------------------------------------------------------------------

def review(yaml_path: str, skill: str = None, model: str = DEFAULT_MODEL,
           threshold: float = 3.5, entry_path: str = None) -> dict:
    """Run review phase. Returns structured feedback dict."""
    if model.startswith("grok"):
        client = get_xai_client()
        if not client:
            raise RuntimeError("xAI API key not available for Grok model")
    else:
        api_key = load_api_key()
        client = OpenAI(api_key=api_key)

    yaml_content = Path(yaml_path).read_text(encoding="utf-8")

    dim_text = "\n".join(
        f"- **{name}**: {desc}" for name, desc in DIMENSIONS.items()
    )

    system = REVIEWER_SYSTEM.format(
        dimensions=dim_text,
        rubric=load_rubric(),
        blog_rules=load_blog_rules(),
        skill_rules=load_skill_rules(skill) if skill else "",
        threshold=threshold,
    )

    user_msg = f"Review this YAML report spec:\n\n{yaml_content}"
    if entry_path:
        entry_content = load_entry(entry_path)
        if entry_content:
            user_msg += f"\n\n---\n\n{entry_content}"

    try:
        if model == GROK_MODEL:
            # Grok-4.20 multi-agent requires Responses API
            response = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": system + "\n\nRespond with valid JSON only."},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
            )
            raw_text = response.output_text
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
        else:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
            )
            raw_text = response.choices[0].message.content
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
    except Exception as e:
        print(f"ERROR: API call failed ({model}): {e}", file=sys.stderr)
        sys.exit(2)

    # Strip markdown fences if present
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON: {e}", file=sys.stderr)
        sys.exit(2)

    # Compute pass/fail programmatically
    dims = result.get("dimensions", {})
    scores = [d.get("score", 0) for d in dims.values()]
    critical = result.get("critical_issues", [])

    if scores:
        weighted = sum(s * w for s, w in zip(scores, DIMENSION_WEIGHTS[:len(scores)]))
        result["overall"] = round(weighted, 1)
        min_score = min(scores)
        result["pass"] = (
            min_score >= 3
            and len(critical) == 0
            and result["overall"] >= threshold
        )
    else:
        result["overall"] = 0
        result["pass"] = False

    result["_meta"] = {
        "phase": "reviewer",
        "model": model,
        "threshold": threshold,
        "skill": skill,
        "tokens": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        },
        "cost_estimate": _estimate_cost(model, type("U", (), {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens})()),
    }

    return result


# ---------------------------------------------------------------------------
# Phase 3: Refiner (applies reviewer feedback to YAML)
# ---------------------------------------------------------------------------

def refine(yaml_path: str, review_result: dict, model: str = DEFAULT_MODEL) -> dict:
    """Apply reviewer feedback to YAML. Rewrites the file in-place. Returns metadata."""
    api_key = load_api_key()
    client = OpenAI(api_key=api_key)

    yaml_content = Path(yaml_path).read_text(encoding="utf-8")

    # Build feedback summary for the refiner
    dims = review_result.get("dimensions", {})
    feedback_parts = []
    for name, data in dims.items():
        score = data.get("score", 0)
        fb = data.get("feedback", "")
        if score < 4 and fb:  # Only include dimensions that need work
            feedback_parts.append(f"- **{name}** ({score}/5): {fb}")

    critical = review_result.get("critical_issues", [])
    suggestions = review_result.get("suggestions", [])

    feedback_text = f"Overall score: {review_result.get('overall', 0)}/5.0\n\n"
    if critical:
        feedback_text += "CRITICAL ISSUES (must fix):\n"
        feedback_text += "\n".join(f"  - {c}" for c in critical)
        feedback_text += "\n\n"
    if feedback_parts:
        feedback_text += "Dimension feedback (needs improvement):\n"
        feedback_text += "\n".join(feedback_parts)
        feedback_text += "\n\n"
    if suggestions:
        feedback_text += "Suggestions:\n"
        feedback_text += "\n".join(f"  {i+1}. {s}" for i, s in enumerate(suggestions))

    user_msg = f"## YAML to improve:\n\n{yaml_content}\n\n---\n\n## Reviewer feedback:\n\n{feedback_text}"

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": REFINER_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.3,
        )
    except Exception as e:
        print(f"ERROR: Refiner API call failed: {e}", file=sys.stderr)
        return {"error": str(e)}

    refined_yaml = response.choices[0].message.content or ""

    # Strip markdown fences if model wrapped it
    refined_yaml = refined_yaml.strip()
    if refined_yaml.startswith("```"):
        lines = refined_yaml.split("\n")
        # Remove first line (```yaml) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        refined_yaml = "\n".join(lines)

    # Write back
    Path(yaml_path).write_text(refined_yaml, encoding="utf-8")

    meta = {
        "phase": "refiner",
        "model": model,
        "critical_fixed": len(critical),
        "suggestions_given": len(suggestions),
        "tokens": {
            "prompt": response.usage.prompt_tokens,
            "completion": response.usage.completion_tokens,
            "total": response.usage.total_tokens,
        },
        "cost_estimate": _estimate_cost(model, response.usage),
    }
    return meta


def print_refine_report(meta: dict, round_num: int):
    """Print refiner report."""
    tokens = meta.get("tokens", {})
    print(f"\n  \033[36m[Refine R{round_num}]\033[0m "
          f"Fixed {meta.get('critical_fixed', 0)} critical issues, "
          f"applied {meta.get('suggestions_given', 0)} suggestions | "
          f"Tokens: {tokens.get('total', '?')} | "
          f"Cost: {meta.get('cost_estimate', '?')}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def _estimate_cost(model: str, usage) -> str:
    rates = {
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-5.4": (2.50, 15.00),
        "gpt-5.4-pro": (30.00, 180.00),
        "grok-4.20-multi-agent-beta-0309": (2.00, 6.00),
        "grok-4-0709": (3.00, 15.00),
        "grok-3": (3.00, 15.00),
    }
    input_rate, output_rate = rates.get(model, (1.0, 3.0))
    cost = (usage.prompt_tokens * input_rate + usage.completion_tokens * output_rate) / 1_000_000
    return f"${cost:.4f}"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_coauthor_report(result: dict):
    """Print co-author enrichment suggestions."""
    meta = result.get("_meta", {})
    tools = meta.get("tool_calls", [])
    enrichments = result.get("enrichments", [])
    missing = result.get("missing_connections", [])
    factual = result.get("factual_issues", [])

    print(f"\n{'='*55}", file=sys.stderr)
    print(f"  Co-Author Phase: {len(enrichments)} enrichments", file=sys.stderr)
    print(f"{'='*55}\n", file=sys.stderr)

    if tools:
        print(f"  \033[36mTOOLS USED ({len(tools)}):\033[0m", file=sys.stderr)
        for t in tools:
            print(f"    {t}", file=sys.stderr)
        print(file=sys.stderr)

    context = result.get("context_gathered", "")
    if context:
        print(f"  \033[36mCONTEXT:\033[0m {context[:200]}", file=sys.stderr)
        print(file=sys.stderr)

    for i, e in enumerate(enrichments, 1):
        action = e.get("action", "?")
        section = e.get("section", "?")
        reason = e.get("reason", "")
        color = "\033[32m" if action in ("add", "connect") else "\033[33m"
        print(f"  {color}{i}. [{action.upper()}] {section}\033[0m", file=sys.stderr)
        if reason:
            print(f"     {reason[:120]}", file=sys.stderr)
        raw_content = e.get("content", "")
        content_preview = (str(raw_content) if not isinstance(raw_content, str) else raw_content)[:150]
        if content_preview:
            print(f"     → {content_preview}...", file=sys.stderr)
        print(file=sys.stderr)

    if missing:
        print(f"  \033[33mMISSING CONNECTIONS:\033[0m", file=sys.stderr)
        for m in missing:
            print(f"    - {m}", file=sys.stderr)
        print(file=sys.stderr)

    if factual:
        print(f"  \033[31mFACTUAL ISSUES:\033[0m", file=sys.stderr)
        for f_issue in factual:
            print(f"    - {f_issue}", file=sys.stderr)
        print(file=sys.stderr)

    tokens = meta.get("tokens", {})
    print(f"  Model: {meta.get('model', '?')} | "
          f"Tokens: {tokens.get('total', '?')} | "
          f"Tools: {len(tools)} | "
          f"Cost: {meta.get('cost_estimate', '?')}", file=sys.stderr)
    print(file=sys.stderr)


def print_review_report(result: dict):
    """Print review report."""
    passed = result.get("pass", False)
    overall = result.get("overall", 0)
    status = f"\033[32mPASS\033[0m" if passed else f"\033[31mFAIL\033[0m"

    print(f"\n{'='*55}", file=sys.stderr)
    print(f"  Review Gate: {status}  (overall: {overall}/5.0)", file=sys.stderr)
    print(f"{'='*55}\n", file=sys.stderr)

    dims = result.get("dimensions", {})
    for name, data in dims.items():
        score = data.get("score", 0)
        bar = "█" * score + "░" * (5 - score)
        feedback = data.get("feedback", "")
        color = "\033[32m" if score >= 4 else "\033[33m" if score >= 3 else "\033[31m"
        print(f"  {color}{bar} {score}/5\033[0m  {name}", file=sys.stderr)
        if feedback:
            words = feedback.split()
            line = "         "
            for w in words:
                if len(line) + len(w) + 1 > 95:
                    print(line, file=sys.stderr)
                    line = "         " + w
                else:
                    line += " " + w if line.strip() else "         " + w
            if line.strip():
                print(line, file=sys.stderr)
        print(file=sys.stderr)

    issues = result.get("critical_issues", [])
    if issues:
        print(f"  \033[31mCRITICAL ISSUES:\033[0m", file=sys.stderr)
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}", file=sys.stderr)
        print(file=sys.stderr)

    suggestions = result.get("suggestions", [])
    if suggestions:
        print(f"  \033[33mSUGGESTIONS:\033[0m", file=sys.stderr)
        for i, sug in enumerate(suggestions, 1):
            print(f"    {i}. {sug}", file=sys.stderr)
        print(file=sys.stderr)

    meta = result.get("_meta", {})
    tokens = meta.get("tokens", {})
    print(f"  Model: {meta.get('model', '?')} | "
          f"Tokens: {tokens.get('total', '?')} | "
          f"Cost: {meta.get('cost_estimate', '?')}", file=sys.stderr)
    print(file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Quality gate for YAML report specs (co-author + 2x review/refine)"
    )
    parser.add_argument("yaml", help="YAML spec file to review")
    parser.add_argument("--skill", "-s", default=None,
                        help="Skill name for skill-specific rules")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL,
                        help=f"OpenAI model (default: {DEFAULT_MODEL})")
    parser.add_argument("--threshold", "-t", type=float, default=3.5,
                        help="Overall score threshold for pass (default: 3.5)")
    parser.add_argument("--entry", "-e", default=None,
                        help="Blog entry .md file (for consistency check)")
    parser.add_argument("--brief", "-b", default=None,
                        help="Session brief for co-author context")
    parser.add_argument("--rounds", "-r", type=int, default=2,
                        help="Number of review+refine rounds (default: 2)")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON to stdout")
    parser.add_argument("--review-only", action="store_true",
                        help="Skip co-author phase and refinement, only review")
    parser.add_argument("--coauthor-only", action="store_true",
                        help="Skip review phase, only co-author")
    args = parser.parse_args()

    yaml_path = Path(args.yaml)
    if not yaml_path.exists():
        print(f"ERROR: File not found: {yaml_path}", file=sys.stderr)
        sys.exit(2)

    results = {}
    total_cost = 0.0

    # Phase 1: Co-author (enrich with tools)
    if not args.review_only:
        print("── Phase 1: Co-Author ──", file=sys.stderr)
        ca_result = coauthor(
            str(yaml_path),
            skill=args.skill,
            model=args.model,
            entry_path=args.entry,
            brief=args.brief,
        )
        results["coauthor"] = ca_result

        if not args.json:
            print_coauthor_report(ca_result)

        if args.coauthor_only:
            if args.json:
                print(json.dumps(results, indent=2, ensure_ascii=False))
            sys.exit(0)

    # Phase 2: Review + Refine loop (hardcoded N rounds)
    if not args.coauthor_only:
        rounds = max(1, args.rounds)
        results["rounds"] = []

        for r in range(1, rounds + 1):
            print(f"\n── Round {r}/{rounds}: Review ──", file=sys.stderr)

            rv_result = review(
                str(yaml_path),
                skill=args.skill,
                model=args.model,
                threshold=args.threshold,
                entry_path=args.entry,
            )

            if not args.json:
                print_review_report(rv_result)

            round_data = {"round": r, "review": rv_result}

            # If passed or last round, don't refine
            if rv_result.get("pass") or r == rounds:
                results["rounds"].append(round_data)
                results["final_review"] = rv_result
                break

            # Refine: apply feedback to YAML
            print(f"── Round {r}/{rounds}: Refine ──", file=sys.stderr)
            refine_meta = refine(
                str(yaml_path),
                rv_result,
                model=args.model,
            )
            round_data["refine"] = refine_meta

            if not args.json:
                print_refine_report(refine_meta, r)

            results["rounds"].append(round_data)

        # ── Grok cross-review (second opinion) ──
        xai_client = get_xai_client()
        if xai_client:
            print(f"\n── Cross-Review: {GROK_MODEL} ──", file=sys.stderr)
            try:
                grok_rv = review(
                    str(yaml_path),
                    skill=args.skill,
                    model=GROK_MODEL,
                    threshold=args.threshold,
                    entry_path=args.entry,
                )
                results["grok_review"] = grok_rv
                if not args.json:
                    print_review_report(grok_rv)

                # Merge: final = worst of both reviewers
                gpt_final = results.get("final_review", {})
                grok_overall = grok_rv.get("overall", 0)
                gpt_overall = gpt_final.get("overall", 0)

                if grok_overall < gpt_overall:
                    results["final_review"] = grok_rv
                    results["final_review"]["_cross_review"] = {
                        "gpt_overall": gpt_overall,
                        "grok_overall": grok_overall,
                        "decisive_model": GROK_MODEL,
                    }
                else:
                    gpt_final["_cross_review"] = {
                        "gpt_overall": gpt_overall,
                        "grok_overall": grok_overall,
                        "decisive_model": args.model,
                    }

                # If either fails, gate fails
                if not grok_rv.get("pass"):
                    results["final_review"]["pass"] = False

            except Exception as e:
                print(f"  WARN: Grok cross-review failed: {e}", file=sys.stderr)
        else:
            print("\n  WARN: xAI key not found — skipping Grok cross-review", file=sys.stderr)

        # Final summary
        final = results.get("final_review", {})
        passed = final.get("pass", False)
        overall = final.get("overall", 0)
        n_rounds = len(results["rounds"])

        status = "\033[32mPASS\033[0m" if passed else "\033[31mFAIL\033[0m"
        cross = final.get("_cross_review", {})
        cross_info = ""
        if cross:
            cross_info = f"  [GPT: {cross.get('gpt_overall', '?')}, Grok: {cross.get('grok_overall', '?')}]"
        print(f"\n{'='*55}", file=sys.stderr)
        print(f"  Final: {status}  ({overall}/5.0 after {n_rounds} round(s)){cross_info}", file=sys.stderr)

        # Aggregate costs
        for rd in results["rounds"]:
            rv_meta = rd.get("review", {}).get("_meta", {})
            rf_meta = rd.get("refine", {})
            for m in [rv_meta, rf_meta]:
                cost_str = m.get("cost_estimate", "$0")
                try:
                    total_cost += float(cost_str.replace("$", ""))
                except (ValueError, AttributeError):
                    pass
        ca_cost = results.get("coauthor", {}).get("_meta", {}).get("cost_estimate", "$0")
        try:
            total_cost += float(ca_cost.replace("$", ""))
        except (ValueError, AttributeError):
            pass
        grok_cost = results.get("grok_review", {}).get("_meta", {}).get("cost_estimate", "$0")
        try:
            total_cost += float(grok_cost.replace("$", ""))
        except (ValueError, AttributeError):
            pass

        print(f"  Total cost: ${total_cost:.4f}", file=sys.stderr)
        print(f"{'='*55}\n", file=sys.stderr)

    # Output JSON
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif not args.coauthor_only:
        print(json.dumps(results.get("final_review", {}), ensure_ascii=False))

    # Exit code
    final = results.get("final_review", {})
    if final:
        sys.exit(0 if final.get("pass") else 1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
