#!/usr/bin/env python3
"""edge-adversarial-research — Adversarial validation via cross-provider deep research.

Takes a research report or claim, sends it to a DIFFERENT provider that uses
its own web search to find counter-evidence, contradictions, and weaknesses.

The key principle: the VALIDATOR always uses a different search engine than the
original researcher. If OpenAI produced the claim, Gemini validates (and vice
versa). This creates genuine adversarial tension — different search indices,
ranking algorithms, and source databases.

Usage:
    edge-adversarial-research --claim "Brazil B2B SaaS market is $2B" --source openai
    edge-adversarial-research --claim-file research.md --source gemini --mode converge
    edge-adversarial-research --claim-file research.md --source both --mode full-tribunal
    cat research.md | edge-adversarial-research --source openai --mode converge --max-rounds 5
    edge-adversarial-research --claim "X" --source openai --json

Modes:
    counter-evidence (default):  Single-round: find data that contradicts/qualifies
    full-tribunal:               3-round: prosecution → defense → verdict
    converge:                    Iterative refinement until both providers agree

Exit codes: 0 = success, 1 = error
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / "edge" / "logs" / "adversarial-research"
SECRETS_DIR = Path.home() / "edge" / "secrets"

MAX_CONVERGE_ROUNDS = 5  # default max iterations for convergence

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

COUNTER_EVIDENCE_SYSTEM = """\
You are an adversarial research validator. You have been given a claim or \
research report produced by ANOTHER AI using a DIFFERENT search engine. \
Your job is to use YOUR web search to find COUNTER-EVIDENCE.

## Process:
1. **Identify claims** — Extract every factual claim, number, and causal assertion
2. **Search for counter-evidence** — For EACH major claim, actively search for:
   - Contradicting data from different sources
   - More recent data that supersedes the claim
   - Methodological problems in cited sources
   - Alternative explanations for the same data
3. **Source quality** — Assess the original sources: are they primary? Recent? Biased?
4. **Synthesize** — Rate each claim as CONFIRMED / QUALIFIED / CONTRADICTED / UNVERIFIABLE

## Output format:

### Claims Analyzed
For each major claim:
- **Claim:** [exact claim]
- **Verdict:** CONFIRMED | QUALIFIED | CONTRADICTED | UNVERIFIABLE
- **Evidence:** [what you found, with source URLs]
- **Confidence:** HIGH | MEDIUM | LOW

### Overall Assessment
- Reliability score: X/10
- Biggest risk: [the claim most likely to be wrong]
- Missing context: [what the original research didn't consider]

## Rules:
- You MUST search — do not evaluate claims from memory alone
- Cite every counter-source with URL
- Be adversarial but FAIR — if a claim holds up, say so
- Distinguish "I couldn't find counter-evidence" from "the claim is confirmed"
- PT-BR unless the original is in English
- 400-800 words"""

TRIBUNAL_ATTACK_SYSTEM = """\
You are a PROSECUTOR in a research tribunal. Your ONLY job is to DEMOLISH the \
claims presented. Use web search aggressively to find every weakness.

## Process:
1. Find the WEAKEST claim and focus your attack there
2. Search for contradicting data, failed predictions, methodological flaws
3. Identify what the researcher DIDN'T search for (survivorship bias, etc.)
4. Present your case as a structured prosecution

## Rules:
- Be RUTHLESS but evidence-based. Every attack must cite a source.
- No ad hominem — attack the CLAIMS, not the researcher
- PT-BR unless the original is in English
- 300-500 words"""

TRIBUNAL_DEFEND_SYSTEM = """\
You are a DEFENSE ATTORNEY in a research tribunal. You've seen both the \
original research AND the prosecution's attack. Your job is to DEFEND the \
research where it's defensible and CONCEDE where it's not.

## Process:
1. For each prosecution point, search for SUPPORTING evidence for the original claim
2. Where the prosecution is right, concede gracefully and quantify the impact
3. Where the prosecution is wrong, present counter-counter-evidence
4. Identify which original claims STILL STAND after the attack

## Rules:
- Be honest. Conceding weak points STRENGTHENS your credibility.
- Every defense must cite a source
- PT-BR unless the original is in English
- 300-500 words"""

TRIBUNAL_VERDICT_SYSTEM = """\
You are the JUDGE in a research tribunal. You've seen:
1. The original research
2. The prosecution's attack
3. The defense's rebuttal

Render a final verdict using your own web search to verify any remaining disputes.

## Output format:

### Verdict
For each disputed claim:
- **Claim:** [claim]
- **Prosecution said:** [summary]
- **Defense said:** [summary]
- **Verdict:** SUSTAINED | OVERTURNED | MODIFIED
- **Modified version:** [if MODIFIED, the corrected claim with sources]

### Final Reliability Score: X/10

### Recommended Actions
What should the original researcher do next?

## Rules:
- Search to verify disputed facts — don't just arbitrate
- Be fair but decisive
- PT-BR unless the original is in English
- 400-600 words"""

# ---------------------------------------------------------------------------
# Convergence prompts
# ---------------------------------------------------------------------------

CONVERGE_CRITIQUE_SYSTEM = """\
You are an adversarial research reviewer. You have been given a research \
report produced by ANOTHER AI using a DIFFERENT search engine. Your job is \
to use YOUR web search to validate, critique, and identify what needs fixing.

## Process:
1. **Validate facts** — Search to verify each major claim and statistic
2. **Find gaps** — What important aspects were NOT covered?
3. **Check recency** — Is there more recent data available?
4. **Cross-reference** — Do independent sources confirm or contradict?

## Output format:

### Validated Claims
Claims that your own search CONFIRMS (with your own supporting sources).

### Issues Found
For each issue:
- **Issue:** [what's wrong]
- **Severity:** CRITICAL | MAJOR | MINOR
- **Evidence:** [your counter-evidence with URLs]
- **Suggested fix:** [how the researcher should address this]

### Missing Coverage
Topics or angles the research should have included.

### Agreement Level: X/10
(10 = fully agree, report is accurate; 1 = fundamentally flawed)

**IMPORTANT:** You MUST give an honest Agreement Level score. If the report \
is solid, say so (8-10). Don't artificially lower the score.

## Rules:
- You MUST search — verify claims through your own web search
- Cite every source with URL
- Be thorough but fair
- PT-BR unless the original is in English
- 400-800 words"""

CONVERGE_REFINE_SYSTEM = """\
You are refining your research report based on adversarial feedback from \
ANOTHER AI that used a DIFFERENT search engine to validate your work.

## Process:
1. **Address each issue** — For CRITICAL and MAJOR issues:
   - Search for updated/corrected information
   - Integrate the reviewer's valid counter-evidence
   - Remove or qualify claims that were contradicted
2. **Fill gaps** — Search for information on topics the reviewer flagged as missing
3. **Preserve strengths** — Keep confirmed claims as-is
4. **Acknowledge** — Where you couldn't resolve a disagreement, note the discrepancy

## Output:
Produce an UPDATED, COMPLETE version of the research report that:
- Fixes all CRITICAL and MAJOR issues
- Incorporates counter-evidence where valid
- Adds coverage for missing topics
- Cites all new sources with URLs
- Notes any remaining disagreements

## Rules:
- SEARCH to find better/corrected information — don't just rephrase
- The refined report must be SELF-CONTAINED (not a diff)
- Keep the same structure as the original where possible
- PT-BR unless the original is in English
- 600-1200 words"""

CONVERGE_FINAL_REVIEW_SYSTEM = """\
You are doing a FINAL review of a research report that has been through \
multiple rounds of adversarial refinement. Assess whether it's ready.

## Process:
1. Verify that previous issues have been addressed
2. Do ONE FINAL search for any remaining factual errors
3. Rate the final report

## Output format:

### Final Assessment
- **Agreement Level: X/10** (10 = ready to publish, fully accurate)
- **Remaining Issues:** [list any, or "None"]
- **Verdict:** APPROVED | NEEDS_MORE_WORK

If APPROVED, also provide:
### Quality Summary
- Strengths of this report
- Caveats the reader should be aware of
- Suggested follow-up research

## Rules:
- Be honest — if it's ready, approve it (score >= 8)
- Don't be artificially harsh on later rounds
- PT-BR unless the original is in English
- 200-400 words"""


# ---------------------------------------------------------------------------
# API Key loading
# ---------------------------------------------------------------------------

def load_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AGENT_OPENAI_API_KEY")
    if key:
        return key
    secrets_file = SECRETS_DIR / "openai.env"
    if secrets_file.exists():
        for line in secrets_file.read_text().strip().split("\n"):
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def load_gemini_key() -> str:
    key = (os.environ.get("GEMINI_API_KEY")
           or os.environ.get("GOOGLE_API_KEY")
           or os.environ.get("AGENT_GOOGLE_API_KEY"))
    if key:
        return key
    secrets_file = SECRETS_DIR / "gemini.env"
    if secrets_file.exists():
        for line in secrets_file.read_text().strip().split("\n"):
            if line.startswith(("GEMINI_API_KEY=", "GOOGLE_API_KEY=")):
                return line.split("=", 1)[1].strip()
    return ""


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> str:
    rates = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gemini-2.5-pro": (1.25, 10.00),
        "gemini-2.5-flash": (0.15, 0.60),
        "gemini-2.0-flash": (0.10, 0.40),
    }
    input_rate, output_rate = rates.get(model, (1.0, 4.0))
    cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
    return f"${cost:.4f}"


# ---------------------------------------------------------------------------
# Provider calls with web search
# ---------------------------------------------------------------------------

def call_openai(system: str, user_msg: str, model: str = None) -> dict:
    """Call OpenAI with web_search tool."""
    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package not installed"}

    api_key = load_openai_key()
    if not api_key:
        return {"error": "OPENAI_API_KEY not found"}

    model = model or os.environ.get("EDGE_MODEL_ADVERSARIAL_OPENAI", "gpt-4.1")
    client = OpenAI(api_key=api_key, timeout=180)

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
            "text": response.output_text,
            "citations": citations,
            "tokens": {
                "input": response.usage.input_tokens,
                "output": response.usage.output_tokens,
                "total": response.usage.input_tokens + response.usage.output_tokens,
            },
            "cost": estimate_cost(model, response.usage.input_tokens, response.usage.output_tokens),
        }
    except Exception as e:
        return {"provider": "openai", "model": model, "error": str(e)}


def call_gemini(system: str, user_msg: str, model: str = None) -> dict:
    """Call Gemini with google_search grounding."""
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return {"error": "google-genai package not installed"}

    api_key = load_gemini_key()
    if not api_key:
        return {"error": "GEMINI_API_KEY not found"}

    model = model or os.environ.get("EDGE_MODEL_ADVERSARIAL_GEMINI", "gemini-2.5-flash")
    client = genai.Client(api_key=api_key)

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

        citations = []
        if hasattr(response, "candidates") and response.candidates:
            grounding = getattr(response.candidates[0], "grounding_metadata", None)
            if grounding:
                for chunk in getattr(grounding, "grounding_chunks", []) or []:
                    web = getattr(chunk, "web", None)
                    if web:
                        citations.append({
                            "url": getattr(web, "uri", ""),
                            "title": getattr(web, "title", ""),
                        })

        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", 0) if usage else 0
        output_tokens = getattr(usage, "candidates_token_count", 0) if usage else 0

        return {
            "provider": "gemini",
            "model": model,
            "text": response.text,
            "citations": citations,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            },
            "cost": estimate_cost(model, input_tokens, output_tokens),
        }
    except Exception as e:
        return {"provider": "gemini", "model": model, "error": str(e)}


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

def get_validator_provider(source: str) -> str:
    return {"openai": "gemini", "gemini": "openai"}.get(source, "gemini")


def call_provider(provider: str, system: str, user_msg: str, model: str = None) -> dict:
    if provider == "openai":
        return call_openai(system, user_msg, model)
    elif provider == "gemini":
        return call_gemini(system, user_msg, model)
    return {"error": f"Unknown provider: {provider}"}


# ---------------------------------------------------------------------------
# Agreement level extraction
# ---------------------------------------------------------------------------

def extract_agreement_level(text: str) -> int:
    """Extract agreement level (1-10) from validator response."""
    patterns = [
        r"Agreement Level[:\s]*(\d+)\s*/\s*10",
        r"Agreement Level[:\s]*(\d+)",
        r"agreement[:\s]*(\d+)\s*/\s*10",
        r"agreement[:\s]*(\d+)",
        r"Reliability score[:\s]*(\d+)\s*/\s*10",
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return min(int(match.group(1)), 10)
    return 0  # couldn't extract


def is_approved(text: str) -> bool:
    """Check if the final review approved the report."""
    return bool(re.search(r"\bAPPROVED\b", text))


# ---------------------------------------------------------------------------
# Mode: counter-evidence (single round)
# ---------------------------------------------------------------------------

def counter_evidence(claim: str, source: str, context: str = "") -> dict:
    validator = get_validator_provider(source)

    user_msg = f"--- Original Research (produced by {source.upper()}) ---\n{claim}"
    if context:
        user_msg = f"--- Additional Context ---\n{context}\n\n{user_msg}"

    print(f"  Validator: {validator} (cross-checking {source} output)", file=sys.stderr)

    result = call_provider(validator, COUNTER_EVIDENCE_SYSTEM, user_msg)
    result["role"] = "validator"
    result["validating_source"] = source
    return {"mode": "counter-evidence", "rounds": [result]}


# ---------------------------------------------------------------------------
# Mode: full-tribunal (3 rounds)
# ---------------------------------------------------------------------------

def full_tribunal(claim: str, source: str, context: str = "") -> dict:
    validator = get_validator_provider(source)
    rounds = []
    base_context = f"--- Original Research (produced by {source.upper()}) ---\n{claim}"
    if context:
        base_context = f"--- Additional Context ---\n{context}\n\n{base_context}"

    # Round 1: Prosecution
    print(f"  Round 1/3: Prosecution ({validator})...", file=sys.stderr)
    attack = call_provider(validator, TRIBUNAL_ATTACK_SYSTEM, base_context)
    attack["role"] = "prosecution"
    rounds.append(attack)
    if attack.get("error"):
        return {"mode": "full-tribunal", "rounds": rounds, "error": "Prosecution failed"}

    # Round 2: Defense
    defense_ctx = f"{base_context}\n\n--- Prosecution ({validator}) ---\n{attack['text']}"
    print(f"  Round 2/3: Defense ({source})...", file=sys.stderr)
    defense = call_provider(source, TRIBUNAL_DEFEND_SYSTEM, defense_ctx)
    defense["role"] = "defense"
    rounds.append(defense)
    if defense.get("error"):
        return {"mode": "full-tribunal", "rounds": rounds, "error": "Defense failed"}

    # Round 3: Verdict
    verdict_ctx = (
        f"{base_context}\n\n"
        f"--- Prosecution ({validator}) ---\n{attack['text']}\n\n"
        f"--- Defense ({source}) ---\n{defense['text']}"
    )
    print(f"  Round 3/3: Verdict ({validator})...", file=sys.stderr)
    verdict = call_provider(validator, TRIBUNAL_VERDICT_SYSTEM, verdict_ctx)
    verdict["role"] = "verdict"
    rounds.append(verdict)

    return {"mode": "full-tribunal", "rounds": rounds}


# ---------------------------------------------------------------------------
# Mode: converge (iterative refinement until agreement)
# ---------------------------------------------------------------------------

CONVERGENCE_THRESHOLD = 8  # agreement level >= 8 = converged

def converge(claim: str, source: str, context: str = "",
             max_rounds: int = MAX_CONVERGE_ROUNDS,
             threshold: int = CONVERGENCE_THRESHOLD) -> dict:
    """Iterative adversarial refinement until both providers agree.

    Flow:
    1. Validator critiques the research (with web search)
    2. If agreement >= threshold → DONE
    3. Researcher refines (with web search) addressing critique
    4. Validator re-critiques refined version
    5. Repeat until convergence or max_rounds
    """
    validator_name = get_validator_provider(source)
    researcher_name = source

    rounds = []
    current_report = claim
    converged = False
    agreement_history = []

    for iteration in range(1, max_rounds + 1):
        is_final = iteration == max_rounds

        # --- Critique round ---
        critique_system = CONVERGE_FINAL_REVIEW_SYSTEM if is_final else CONVERGE_CRITIQUE_SYSTEM

        critique_msg = (
            f"--- Research Report (v{iteration}, by {researcher_name.upper()}) ---\n"
            f"{current_report}"
        )
        if context:
            critique_msg = f"--- Background Context ---\n{context}\n\n{critique_msg}"
        if iteration > 1 and rounds:
            # Include previous critique for continuity
            prev = rounds[-1]
            if prev.get("role") == "refinement":
                critique_msg += (
                    f"\n\n--- Previous Issues (round {iteration - 1}) ---\n"
                    f"The researcher addressed feedback from the previous round. "
                    f"Check if the issues were properly resolved."
                )

        print(f"  Round {iteration}/{max_rounds}: Critique ({validator_name})...",
              file=sys.stderr)

        critique = call_provider(validator_name, critique_system, critique_msg)
        critique["role"] = "critique"
        critique["iteration"] = iteration
        rounds.append(critique)

        if critique.get("error"):
            print(f"  ERROR: Critique failed — {critique['error'][:80]}", file=sys.stderr)
            break

        # Extract agreement level
        agreement = extract_agreement_level(critique.get("text", ""))
        agreement_history.append(agreement)
        approved = is_approved(critique.get("text", ""))

        print(f"  Agreement level: {agreement}/10 (threshold: {threshold})",
              file=sys.stderr)

        # Check convergence
        if agreement >= threshold or approved:
            print(f"  CONVERGED at round {iteration}! Agreement: {agreement}/10",
                  file=sys.stderr)
            converged = True
            break

        if is_final:
            print(f"  Max rounds reached. Final agreement: {agreement}/10",
                  file=sys.stderr)
            break

        # --- Refinement round ---
        refine_msg = (
            f"--- Your Current Research Report ---\n{current_report}\n\n"
            f"--- Adversarial Critique (by {validator_name.upper()}, round {iteration}) ---\n"
            f"{critique['text']}\n\n"
            f"Address ALL issues marked as CRITICAL and MAJOR. Use web search to find "
            f"corrected information. Produce the complete updated report."
        )
        if context:
            refine_msg = f"--- Background Context ---\n{context}\n\n{refine_msg}"

        print(f"  Round {iteration}/{max_rounds}: Refinement ({researcher_name})...",
              file=sys.stderr)

        refinement = call_provider(researcher_name, CONVERGE_REFINE_SYSTEM, refine_msg)
        refinement["role"] = "refinement"
        refinement["iteration"] = iteration
        rounds.append(refinement)

        if refinement.get("error"):
            print(f"  ERROR: Refinement failed — {refinement['error'][:80]}",
                  file=sys.stderr)
            break

        # Update current report for next iteration
        current_report = refinement.get("text", current_report)

    return {
        "mode": "converge",
        "converged": converged,
        "iterations": len(agreement_history),
        "agreement_history": agreement_history,
        "final_agreement": agreement_history[-1] if agreement_history else 0,
        "threshold": threshold,
        "researcher": researcher_name,
        "validator": validator_name,
        "final_report": current_report,
        "rounds": rounds,
    }


# ---------------------------------------------------------------------------
# Mode: both cross-validate
# ---------------------------------------------------------------------------

def both_cross_validate(claim: str, context: str = "") -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    user_msg = f"--- Original Research ---\n{claim}"
    if context:
        user_msg = f"--- Additional Context ---\n{context}\n\n{user_msg}"

    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(call_provider, "openai", COUNTER_EVIDENCE_SYSTEM, user_msg): "openai",
            pool.submit(call_provider, "gemini", COUNTER_EVIDENCE_SYSTEM, user_msg): "gemini",
        }
        for future in as_completed(futures):
            provider = futures[future]
            try:
                r = future.result()
                r["role"] = f"cross-validator ({provider})"
                results.append(r)
            except Exception as e:
                results.append({"provider": provider, "role": "cross-validator", "error": str(e)})

    return {"mode": "cross-validation", "rounds": results}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_adversarial(claim_preview: str, mode: str, source: str, result: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    total_cost = sum(
        float(r.get("cost", "$0").replace("$", ""))
        for r in result.get("rounds", []) if not r.get("error")
    )
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "claim_preview": claim_preview[:500],
        "mode": mode,
        "source": source,
        "rounds": len(result.get("rounds", [])),
        "converged": result.get("converged"),
        "final_agreement": result.get("final_agreement"),
        "agreement_history": result.get("agreement_history"),
        "total_cost": f"${total_cost:.4f}",
    }
    log_file = LOG_DIR / f"{timestamp}.json"
    log_file.write_text(json.dumps(log_entry, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_markdown(claim_preview: str, result: dict) -> str:
    mode = result.get("mode", "unknown")
    rounds = result.get("rounds", [])

    lines = [
        f"## Adversarial Research Validation",
        f"**Mode:** {mode} | **Rounds:** {len(rounds)}",
    ]

    # Convergence-specific header
    if mode == "converge":
        converged = result.get("converged", False)
        final_agreement = result.get("final_agreement", 0)
        iterations = result.get("iterations", 0)
        history = result.get("agreement_history", [])
        status = "CONVERGED" if converged else "DID NOT CONVERGE"
        lines.append(f"**Status:** {status} | **Iterations:** {iterations} | "
                      f"**Final agreement:** {final_agreement}/10")
        if history:
            lines.append(f"**Agreement trajectory:** {' → '.join(str(h) for h in history)}")
    lines.append("")

    for i, r in enumerate(rounds, 1):
        role = r.get("role", "unknown")
        provider = r.get("provider", "?")
        model = r.get("model", "?")
        iteration = r.get("iteration", "")
        iter_label = f" (iter {iteration})" if iteration else ""

        if r.get("error"):
            lines.append(f"### Round {i}: {role.upper()}{iter_label} ({provider}) — ERROR")
            lines.append(f"```\n{r['error']}\n```\n")
            continue

        cost = r.get("cost", "$0.00")
        tokens = r.get("tokens", {})
        cites = len(r.get("citations", []))

        lines.append(f"### Round {i}: {role.upper()}{iter_label} ({provider}/{model})")
        lines.append(f"*Tokens: {tokens.get('total', 0)} | Citations: {cites} | Cost: {cost}*\n")
        lines.append(r.get("text", "(no output)"))
        lines.append("")

        citations = r.get("citations", [])
        if citations:
            lines.append("#### Sources")
            seen = set()
            for c in citations:
                url = c.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    title = c.get("title", url)
                    lines.append(f"- [{title}]({url})")
            lines.append("")

    # Final report for converge mode
    if mode == "converge" and result.get("final_report"):
        lines.append("---")
        lines.append("## Final Validated Report")
        lines.append("")
        lines.append(result["final_report"])
        lines.append("")

    total_cost = sum(
        float(r.get("cost", "$0").replace("$", ""))
        for r in rounds if not r.get("error")
    )
    lines.append("---")
    lines.append(f"**Total cost:** ${total_cost:.4f}")
    return "\n".join(lines)


def format_json_output(claim_preview: str, result: dict) -> str:
    return json.dumps({
        "claim_preview": claim_preview[:500],
        "timestamp": datetime.now().isoformat(),
        **result,
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Adversarial validation via cross-provider deep research"
    )
    parser.add_argument("--claim", default=None,
                        help="Claim or research output to validate")
    parser.add_argument("--claim-file", default=None,
                        help="File containing claim/research to validate")
    parser.add_argument("--source", "-s", choices=["openai", "gemini", "both"],
                        required=True,
                        help="Which provider produced the original claim")
    parser.add_argument("--mode", "-m",
                        choices=["counter-evidence", "full-tribunal", "converge"],
                        default="counter-evidence",
                        help="Validation mode (default: counter-evidence)")
    parser.add_argument("--max-rounds", type=int, default=MAX_CONVERGE_ROUNDS,
                        help=f"Max rounds for converge mode (default: {MAX_CONVERGE_ROUNDS})")
    parser.add_argument("--threshold", type=int, default=CONVERGENCE_THRESHOLD,
                        help=f"Agreement threshold for convergence (default: {CONVERGENCE_THRESHOLD})")
    parser.add_argument("--context", "-c", nargs="+", default=None,
                        help="Additional context files")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    parser.add_argument("--gate", default=None, metavar="SPEC_PATH",
                        help="Save validation as .adversarial-review.json for pipeline enforcement")
    args = parser.parse_args()

    # Load claim
    claim = args.claim
    if args.claim_file:
        claim = Path(args.claim_file).read_text(encoding="utf-8")

    # Read from stdin if piped
    if not sys.stdin.isatty():
        stdin = sys.stdin.read()
        if claim:
            claim = f"{claim}\n\n{stdin}"
        else:
            claim = stdin

    if not claim:
        parser.error("Provide --claim, --claim-file, or pipe content via stdin")

    # Build context
    context = ""
    if args.context:
        parts = []
        for f in args.context:
            p = Path(f)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                if len(content) > 8000:
                    content = content[:8000] + "\n[... truncated]"
                parts.append(f"--- {p.name} ---\n{content}")
        context = "\n\n".join(parts)

    # Status
    mode_label = args.mode.upper()
    print(f"Adversarial validation [{mode_label}] (source={args.source})", file=sys.stderr)

    # Execute
    if args.mode == "converge":
        result = converge(
            claim, args.source, context,
            max_rounds=args.max_rounds,
            threshold=args.threshold,
        )
    elif args.source == "both" and args.mode == "counter-evidence":
        result = both_cross_validate(claim, context)
    elif args.mode == "full-tribunal":
        result = full_tribunal(claim, args.source, context)
    else:
        result = counter_evidence(claim, args.source, context)

    # Log
    log_adversarial(claim[:200], args.mode, args.source, result)

    # Gate: save for pipeline enforcement
    if args.gate:
        spec_path = Path(args.gate)
        review_path = spec_path.with_suffix(".adversarial-review.json")
        resolved_path = spec_path.with_suffix(".adversarial-resolved")
        if resolved_path.exists():
            resolved_path.unlink()
        total_cost = sum(
            float(r.get("cost", "$0").replace("$", ""))
            for r in result.get("rounds", []) if not r.get("error")
        )
        review_data = {
            "timestamp": datetime.now().isoformat(),
            "spec": str(spec_path),
            "mode": args.mode,
            "source": args.source,
            "converged": result.get("converged"),
            "final_agreement": result.get("final_agreement"),
            "rounds": len(result.get("rounds", [])),
            "cost": f"${total_cost:.4f}",
            "resolved": False,
        }
        review_path.write_text(json.dumps(review_data, indent=2, ensure_ascii=False))
        print(f"  Gate review saved: {review_path}", file=sys.stderr)

    # Output
    if args.json:
        print(format_json_output(claim[:200], result))
    else:
        print(format_markdown(claim[:200], result))


if __name__ == "__main__":
    main()
