from __future__ import annotations

import argparse

from .blog import serve_blog
from .config import load_config
from .install import apply, doctor, render
from .reports import build_blog
from .runner import run_beat


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edge", description="edge-of-chaos mentor-core v2")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("render")
    sub.add_parser("apply")
    sub.add_parser("doctor")
    sub.add_parser("blog-build")
    serve = sub.add_parser("blog-serve")
    serve.add_argument("--port", type=int, default=8766)
    for name in ["heartbeat", "discovery", "report"]:
        p = sub.add_parser(name)
        p.add_argument("request", nargs="*", help="Optional request/topic")
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
    if args.cmd in {"heartbeat", "discovery", "report"}:
        request = " ".join(args.request)
        result = run_beat(config, kind=args.cmd, request=request)
        print(f"{result.status}: {result.report_path} thread={result.thread_id}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
