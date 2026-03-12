#!/usr/bin/env python3
"""edge-dialogue — Multi-turn dialogue with GPT models via OpenAI Responses API.

Supports gpt-5.4-pro and other models that require the Responses API.
Logs full conversations to ~/edge/logs/dialogue/.

Usage:
    edge-dialogue.py --session NAME --turns 3 --model gpt-5.4-pro --system "You are..." --messages msg1.txt msg2.txt msg3.txt
    edge-dialogue.py --session NAME --turns 1 --model gpt-4o --system "..." --messages msg1.txt
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def load_api_key():
    """Load OpenAI API key from env or secrets file."""
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key
    secrets = Path.home() / "edge" / "secrets" / "openai.env"
    if secrets.exists():
        for line in secrets.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: No OPENAI_API_KEY found", file=sys.stderr)
    sys.exit(1)

def dialogue_responses_api(client, model, system_prompt, messages, session_name):
    """Multi-turn dialogue using OpenAI Responses API (for pro models)."""
    log = []
    prev_id = None

    for i, user_msg in enumerate(messages, 1):
        print(f"\n{'='*60}", flush=True)
        print(f"  Turn {i}/{len(messages)}", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"\n[USER]\n{user_msg[:200]}{'...' if len(user_msg) > 200 else ''}\n", flush=True)

        input_parts = []
        if i == 1 and system_prompt:
            input_parts.append({"role": "developer", "content": system_prompt})
        input_parts.append({"role": "user", "content": user_msg})

        kwargs = {
            "model": model,
            "input": input_parts,
        }
        if prev_id:
            kwargs["previous_response_id"] = prev_id

        print(f"  Sending request to {model}...", flush=True)
        response = client.responses.create(**kwargs)
        print(f"  Response received (id={response.id})", flush=True)
        prev_id = response.id

        # Extract text from response
        assistant_text = ""
        for item in response.output:
            if hasattr(item, "content") and item.content:
                for part in item.content:
                    if hasattr(part, "text"):
                        assistant_text += part.text
            elif hasattr(item, "text"):
                assistant_text += item.text

        print(f"[{model}]\n{assistant_text[:500]}{'...' if len(assistant_text) > 500 else ''}\n", flush=True)

        log.append({
            "turn": i,
            "user": user_msg,
            "assistant": assistant_text,
            "response_id": response.id,
            "model": model,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    return log

def dialogue_chat_api(client, model, system_prompt, messages, session_name):
    """Multi-turn dialogue using Chat Completions API (for standard models)."""
    log = []
    chat_messages = []
    if system_prompt:
        chat_messages.append({"role": "system", "content": system_prompt})

    for i, user_msg in enumerate(messages, 1):
        print(f"\n{'='*60}")
        print(f"  Turn {i}/{len(messages)}")
        print(f"{'='*60}")
        print(f"\n[USER]\n{user_msg[:200]}{'...' if len(user_msg) > 200 else ''}\n")

        chat_messages.append({"role": "user", "content": user_msg})

        response = client.chat.completions.create(
            model=model,
            messages=chat_messages,
        )
        assistant_text = response.choices[0].message.content or ""
        chat_messages.append({"role": "assistant", "content": assistant_text})

        print(f"[{model}]\n{assistant_text[:500]}{'...' if len(assistant_text) > 500 else ''}\n")

        log.append({
            "turn": i,
            "user": user_msg,
            "assistant": assistant_text,
            "model": model,
            "ts": datetime.now(timezone.utc).isoformat(),
        })

    return log

def main():
    parser = argparse.ArgumentParser(description="Multi-turn GPT dialogue")
    parser.add_argument("--session", required=True, help="Session name for log file")
    parser.add_argument("--model", default=os.environ.get("EDGE_DEFAULT_MODEL", "gpt-5.4-pro"),
                        help="Model to use")
    parser.add_argument("--system", default="", help="System prompt")
    parser.add_argument("--system-file", help="File containing system prompt")
    parser.add_argument("--messages", nargs="+", required=True, help="Message files (one per turn)")
    parser.add_argument("--log-dir", default=str(Path.home() / "edge" / "logs" / "dialogue"),
                        help="Directory for conversation logs")
    args = parser.parse_args()

    # Load system prompt
    system_prompt = args.system
    if args.system_file:
        system_prompt = Path(args.system_file).read_text()

    # Load messages
    messages = []
    for mf in args.messages:
        messages.append(Path(mf).read_text().strip())

    # Setup
    api_key = load_api_key()
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=300)  # 5min timeout per request

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Run dialogue
    is_pro = "pro" in args.model.lower()
    if is_pro:
        log = dialogue_responses_api(client, args.model, system_prompt, messages, args.session)
    else:
        log = dialogue_chat_api(client, args.model, system_prompt, messages, args.session)

    # Save log
    log_file = log_dir / f"{args.session}.json"
    with open(log_file, "w") as f:
        json.dump({
            "session": args.session,
            "model": args.model,
            "system_prompt": system_prompt[:500],
            "turns": len(messages),
            "started_at": log[0]["ts"] if log else None,
            "finished_at": log[-1]["ts"] if log else None,
            "conversation": log,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nLog saved: {log_file}")
    # Print cost estimate
    total_chars = sum(len(t["user"]) + len(t["assistant"]) for t in log)
    print(f"Total chars: {total_chars:,}")

if __name__ == "__main__":
    main()
