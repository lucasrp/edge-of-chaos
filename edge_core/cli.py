from __future__ import annotations

import argparse
import json

from .async_chat import add_message, list_messages, mark_processed, pin_message, unpin_message
from .blog import serve_blog
from .config import load_config
from .install import apply, doctor, render
from .publication import build_blog
from .runner import run_beat, run_heartbeat


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edge", description="edge-of-chaos mentor-core v2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    sub.add_parser("apply")
    sub.add_parser("doctor")
    sub.add_parser("blog-build")
    serve = sub.add_parser("blog-serve")
    serve.add_argument("--port", type=int, default=8766)
    for name in ["heartbeat", "discovery", "report", "research"]:
        p = sub.add_parser(name)
        p.add_argument("request", nargs="*", help="Optional request/topic")
    chat_send = sub.add_parser("chat-send")
    chat_send.add_argument("text", nargs="+", help="Message text")
    chat_send.add_argument("--author", default="user")
    chat_send.add_argument("--pin", action="store_true")
    chat_list = sub.add_parser("chat-list")
    chat_list.add_argument("--limit", type=int, default=30)
    chat_list.add_argument("--unprocessed", action="store_true")
    chat_list.add_argument("--pinned", action="store_true")
    chat_list.add_argument("--json", action="store_true")
    chat_mark = sub.add_parser("chat-mark-processed")
    chat_mark.add_argument("message_id", type=int)
    chat_pin = sub.add_parser("chat-pin")
    chat_pin.add_argument("message_id", type=int)
    chat_unpin = sub.add_parser("chat-unpin")
    chat_unpin.add_argument("message_id", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    if args.cmd == "render":
        for path in render(config):
            print(path)
        return 0
    if args.cmd == "apply":
        render(config)
        for path in apply(config):
            print(path)
        return 0
    if args.cmd == "doctor":
        ok, checks = doctor(config)
        for check in checks:
            print(check)
        return 0 if ok else 1
    if args.cmd == "blog-build":
        print(build_blog(config))
        return 0
    if args.cmd == "blog-serve":
        serve_blog(config, port=args.port)
        return 0
    if args.cmd == "heartbeat":
        request = " ".join(args.request)
        result = run_heartbeat(config, request=request)
        print(f"{result.status}: kind={result.kind} report={result.report_path} thread={result.thread_id}")
        return 0
    if args.cmd in {"discovery", "report", "research"}:
        request = " ".join(args.request)
        result = run_beat(config, kind=args.cmd, request=request)
        print(f"{result.status}: kind={result.kind} report={result.report_path} thread={result.thread_id}")
        return 0
    if args.cmd == "chat-send":
        message = add_message(config, author=args.author, text=" ".join(args.text), pinned=args.pin)
        print(json.dumps(message, ensure_ascii=False))
        return 0
    if args.cmd == "chat-list":
        messages = list_messages(config, limit=args.limit, unprocessed_only=args.unprocessed, pinned_only=args.pinned)
        if args.json:
            print(json.dumps(messages, ensure_ascii=False, indent=2))
        else:
            for item in messages:
                flags = []
                if item.get("pinned"):
                    flags.append("pinned")
                if not item.get("processed"):
                    flags.append("pending")
                prefix = f"[{','.join(flags)}] " if flags else ""
                print(f"{item.get('id')}\t{item.get('ts')}\t{item.get('author')}\t{prefix}{item.get('text')}")
        return 0
    if args.cmd == "chat-mark-processed":
        updated = mark_processed(config, args.message_id)
        print(json.dumps(updated or {"error": "message not found"}, ensure_ascii=False))
        return 0 if updated else 1
    if args.cmd == "chat-pin":
        updated = pin_message(config, args.message_id)
        print(json.dumps(updated or {"error": "message not found"}, ensure_ascii=False))
        return 0 if updated else 1
    if args.cmd == "chat-unpin":
        updated = unpin_message(config, args.message_id)
        print(json.dumps(updated or {"error": "message not found"}, ensure_ascii=False))
        return 0 if updated else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
