#!/usr/bin/env python3
"""
edge-consult — Cross-model deliberation tool.

Adversarial (default): finds flaws, steelmans the opposite, catches biases.
Collaborative: expands, connects, suggests unseen angles.

Supports multiple model providers: OpenAI (gpt-*), xAI (grok-*).

Usage:
    edge-consult "minha análise: X implica Y"
    edge-consult "tem furo?" --context spec.yaml notes.md
    edge-consult --model grok-4 "onde está mais fraco?"
    cat analysis.md | edge-consult "onde está mais fraco?"
    edge-consult --mode collab "que ângulos não estou vendo?"

Exit codes: 0 = success, 1 = error
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai package required: pip install openai")

SECRETS_DIR = Path.home() / "edge/secrets"
LOG_DIR = Path.home() / "edge/logs/consult"

# Provider configs: model prefix -> (secrets_file, env_var, base_url)
PROVIDERS = {
    "gpt": {
        "secrets_file": SECRETS_DIR / "openai.env",
        "env_var": "OPENAI_API_KEY",
        "base_url": None,  # default OpenAI
    },
    "grok": {
        "secrets_file": SECRETS_DIR / "xai.env",
        "env_var": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
    },
}

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

ADVERSARIAL_SYSTEM = """\
You are a rigorous, intellectually honest critic. Your job is to find the \
flaws in the reasoning presented. Do NOT agree. Do NOT soften your critique.

## Process:

1. **Weakest premise** — Which assumption is most likely wrong? Why?
2. **Missing evidence** — What data would change the conclusion? What's absent?
3. **Steelman the opposite** — The STRONGEST argument AGAINST the conclusion.
4. **Cognitive biases** — confirmation bias, availability heuristic, anchoring, \
sunk cost, survivorship bias, false consensus. Name it, show where it operates.
5. **Breaking scenario** — Under what conditions does this fail completely?
6. **Verdict** — 1-2 sentences: the single most important thing being ignored.

## Rules:
- Be SPECIFIC. Not "this might be wrong" — exactly WHERE and WHY.
- If the reasoning is solid, say so — but still identify the weakest link.
- No flattery. No "great analysis, but...". Straight to the critique.
- PT-BR.
- 200-400 words. Dense signal, no filler."""

COLLABORATIVE_SYSTEM = """\
You are a thought partner helping explore an idea. You are NOT critiquing — \
you are EXPANDING. Add value the author couldn't generate alone.

## Process:

1. **Unseen angles** — What perspectives haven't been considered?
2. **Cross-domain connections** — Concepts from physics, biology, economics, \
game theory, design, psychology that apply here?
3. **Strengthen** — What would make this MORE compelling? What evidence?
4. **Surprising implications** — If correct, what non-obvious consequences?
5. **Adjacent questions** — What questions might be MORE important?

## Rules:
- Generative, not evaluative. Add, don't subtract.
- Bring concepts the author probably doesn't know about.
- Concrete > abstract. "Like X in Y because Z" > "consider perspectives".
- PT-BR.
- 200-400 words. Dense signal, no filler."""


# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

def get_provider(model: str) -> dict:
    """Determine provider config from model name prefix."""
    for prefix, config in PROVIDERS.items():
        if model.startswith(prefix):
            return config
    # Fallback to OpenAI
    return PROVIDERS["gpt"]


def load_api_key(model: str) -> tuple[str, str | None]:
    """Load API key for the given model. Returns (api_key, base_url)."""
    provider = get_provider(model)
    env_var = provider["env_var"]
    base_url = provider["base_url"]

    # Check environment variable first
    key = os.environ.get(env_var)
    if key:
        return key, base_url

    # Check secrets file
    secrets_file = provider["secrets_file"]
    if secrets_file.exists():
        for line in secrets_file.read_text().strip().split("\n"):
            if line.startswith(f"{env_var}="):
                return line.split("=", 1)[1].strip(), base_url

    print(f"ERROR: {env_var} not found (needed for {model}).", file=sys.stderr)
    print(f"Set env var or create {secrets_file}", file=sys.stderr)
    sys.exit(1)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> str:
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
        "grok-4": (3.00, 15.00),
        "grok-3": (3.00, 15.00),
    }
    input_rate, output_rate = rates.get(model, (1.0, 3.0))
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return f"${cost:.4f}"


def log_consultation(mode: str, question: str, context_files: list,
                     response: str, model: str, cost: str, tokens: dict):
    """Log consultation for audit trail (/ed-reflexao can review these)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "model": model,
        "question": question[:500],
        "context_files": context_files,
        "response": response[:2000],
        "cost": cost,
        "tokens": tokens,
    }
    log_file = LOG_DIR / f"{timestamp}.json"
    log_file.write_text(json.dumps(log_entry, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Dual-model consultation (always both GPT + Grok)
# ---------------------------------------------------------------------------

DUAL_MODELS = ["gpt-5.4", "grok-4.20-multi-agent-beta-0309"]


def _build_user_msg(question: str, context_files: list = None,
                    stdin_content: str = None) -> str:
    """Build user message from question, context files, and stdin."""
    parts = []

    if context_files:
        for f in context_files:
            p = Path(f)
            if p.exists():
                content = p.read_text(encoding="utf-8")
                if len(content) > 8000:
                    content = content[:8000] + f"\n\n[... truncated, {len(content)} chars total]"
                parts.append(f"--- Context: {p.name} ---\n{content}")
            else:
                parts.append(f"--- Context: {f} (file not found) ---")

    if stdin_content:
        if len(stdin_content) > 8000:
            stdin_content = stdin_content[:8000] + "\n\n[... truncated]"
        parts.append(f"--- Piped input ---\n{stdin_content}")

    parts.append(f"--- Question ---\n{question}")
    return "\n\n".join(parts)


# Models that require Responses API instead of Chat Completions
RESPONSES_API_MODELS = {"grok-4.20-multi-agent-beta-0309", "gpt-5.4-pro"}


def _call_model(model: str, system: str, user_msg: str) -> tuple[str, dict, str]:
    """Call a single model. Returns (response_text, tokens_dict, cost_str)."""
    api_key, base_url = load_api_key(model)
    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    if model in RESPONSES_API_MODELS:
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        result = response.output_text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
    else:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        result = response.choices[0].message.content
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

    cost = estimate_cost(model, prompt_tokens, completion_tokens)
    tokens = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens,
    }
    return result, tokens, cost


def consult(question: str, mode: str = "adversarial", context_files: list = None,
            stdin_content: str = None, gate_spec: str = None) -> str:
    """Send consultation to BOTH GPT-5.4 and Grok-4.20 and return combined response.

    If gate_spec is provided, saves review as {spec}.review.json for
    consolidar-estado to enforce resolution before publishing.
    """
    system = ADVERSARIAL_SYSTEM if mode == "adversarial" else COLLABORATIVE_SYSTEM
    user_msg = _build_user_msg(question, context_files, stdin_content)

    models = list(DUAL_MODELS)

    results = []
    all_tokens = []
    all_costs = []

    for m in models:
        try:
            result, tokens, cost = _call_model(m, system, user_msg)
            results.append((m, result))
            all_tokens.append(tokens)
            all_costs.append(cost)

            # Log each model separately
            log_consultation(
                mode=mode,
                question=question,
                context_files=[str(f) for f in (context_files or [])],
                response=result,
                model=m,
                cost=cost,
                tokens=tokens,
            )

            # Metadata to stderr
            mode_label = "\033[31mADVERSARIAL\033[0m" if mode == "adversarial" else "\033[36mCOLLABORATIVE\033[0m"
            print(f"\n{'='*55}", file=sys.stderr)
            print(f"  edge-consult [{mode_label}]  ({m})", file=sys.stderr)
            print(f"  Tokens: {tokens['total']} | Cost: {cost}", file=sys.stderr)
            print(f"{'='*55}", file=sys.stderr)

        except Exception as e:
            print(f"  WARN: {m} failed: {e}", file=sys.stderr)
            results.append((m, f"[{m} error: {e}]"))

    # Combine outputs from both models
    combined = "\n\n".join(
        f"── {m} ──\n{text}" for m, text in results
    )

    # Gate: save combined review alongside YAML spec
    if gate_spec:
        spec_path = Path(gate_spec)
        review_path = spec_path.with_suffix(".review.json")
        resolved_path = spec_path.with_suffix(".resolved")
        if resolved_path.exists():
            resolved_path.unlink()
        total_cost = sum(
            float(c.replace("$", "")) for c in all_costs
        )
        review_data = {
            "timestamp": datetime.now().isoformat(),
            "spec": str(spec_path),
            "mode": mode,
            "models": [m for m, _ in results],
            "question": question[:500],
            "response": combined[:4000],
            "cost": f"${total_cost:.4f}",
            "resolved": False,
        }
        review_path.write_text(json.dumps(review_data, indent=2, ensure_ascii=False))
        print(f"\n  Gate review saved: {review_path}", file=sys.stderr)
        print(f"  To resolve: address feedback, then touch {resolved_path}", file=sys.stderr)

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Cross-model deliberation: adversarial (default) or collaborative"
    )
    parser.add_argument("question", nargs="?", default=None,
                        help="Question or reasoning to challenge/explore")
    parser.add_argument("--mode", "-m", choices=["adversarial", "collab"],
                        default="adversarial",
                        help="Mode: adversarial (default) or collab")
    parser.add_argument("--context", "-c", nargs="+", default=None,
                        help="Context files to include")
    parser.add_argument("--gate", default=None, metavar="SPEC_PATH",
                        help="Save review as .review.json alongside SPEC_PATH for consolidar-estado enforcement")
    args = parser.parse_args()

    # Read from stdin if piped
    stdin_content = None
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()

    if not args.question and not stdin_content:
        parser.error("Provide a question as argument or pipe content via stdin")

    question = args.question or "Analyze this:"

    result = consult(
        question=question,
        mode=args.mode,
        context_files=args.context,
        stdin_content=stdin_content,
        gate_spec=args.gate,
    )

    print(result)


if __name__ == "__main__":
    main()
