from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .api import serve
from .service import AlosCurrentService
from .storage import AlosCurrentStore


def emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alos_current-server")
    parser.add_argument("--home", default=".alos_current")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_cmd = sub.add_parser("serve")
    serve_cmd.add_argument("--host", default="127.0.0.1")
    serve_cmd.add_argument("--port", type=int, default=8770)
    serve_cmd.add_argument("--open", action="store_true")
    serve_cmd.add_argument("--verbose", action="store_true")
    serve_cmd.add_argument("--token")
    sub.add_parser("init")
    sub.add_parser("health")
    create = sub.add_parser("create-sample")
    create.add_argument("--name", default="AlosCurrent Sample")
    publish = sub.add_parser("publish")
    publish.add_argument("workflow_id")
    execute = sub.add_parser("execute")
    execute.add_argument("workflow_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = Path(args.home).expanduser().resolve()
    try:
        if args.command == "serve":
            serve(args.host, args.port, home=home, open_browser=args.open, verbose=args.verbose, auth_token=args.token)
            return 0
        service = AlosCurrentService(AlosCurrentStore(home))
        if args.command == "init":
            emit({"initialized": True, "home": str(home)})
        elif args.command == "health":
            emit(service.health())
        elif args.command == "create-sample":
            emit(service.create_workflow({"name": args.name}))
        elif args.command == "publish":
            emit(service.publish_workflow(args.workflow_id))
        elif args.command == "execute":
            emit(service.execute_workflow(args.workflow_id))
        return 0
    except Exception as exc:
        emit({"error": str(exc), "command": args.command})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
