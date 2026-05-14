"""Command line interface for AlosAtlas."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import AlosAtlasConfig
from .indexer import index_repository, refresh_changed_repository
from .query import list_repositories, queries_for
from .server import serve
from .watcher import refresh_if_stale, watch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alos_atlas",
        description="RexBot Industries local code intelligence and impact analysis.",
    )
    parser.add_argument("--home", help="Override AlosAtlas storage home.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register", help="Register a repository.")
    register.add_argument("name")
    register.add_argument("path")

    sub.add_parser("list-repos", help="List registered repositories.")

    index = sub.add_parser("index", help="Index a registered repository.")
    index.add_argument("repo")

    status = sub.add_parser("status", help="Show repository index status.")
    status.add_argument("repo")

    search = sub.add_parser("search", help="Search indexed structural evidence.")
    search.add_argument("repo")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)

    file_context = sub.add_parser("file-context", help="Show context for a file.")
    file_context.add_argument("repo")
    file_context.add_argument("path")
    file_context.add_argument("--limit", type=int, default=20)

    symbol_context = sub.add_parser("symbol-context", help="Show context for a symbol.")
    symbol_context.add_argument("repo")
    symbol_context.add_argument("symbol")
    symbol_context.add_argument("--limit", type=int, default=20)

    route_context = sub.add_parser("route-context", help="Show context for a route or endpoint.")
    route_context.add_argument("repo")
    route_context.add_argument("route")
    route_context.add_argument("--limit", type=int, default=20)

    impact = sub.add_parser("impact", help="Report impact for a file, symbol, route, or config.")
    impact.add_argument("repo")
    impact.add_argument("--target", required=True)
    impact.add_argument("--type", default="auto", choices=["auto", "file", "route", "config", "symbol"])
    impact.add_argument("--depth", type=int, default=3)
    impact.add_argument("--limit", type=int, default=50)

    change_scope = sub.add_parser("change-scope", help="Report scope for changed files.")
    change_scope.add_argument("repo")
    change_scope.add_argument("--file", action="append", dest="files", default=[])
    change_scope.add_argument("--git", action="store_true", help="Use git diff --name-only HEAD.")
    change_scope.add_argument("--limit", type=int, default=50)

    recommend = sub.add_parser("recommend-tests", help="Recommend tests for a target or files.")
    recommend.add_argument("repo")
    recommend.add_argument("--target")
    recommend.add_argument("--file", action="append", dest="files", default=[])
    recommend.add_argument("--limit", type=int, default=20)

    graph = sub.add_parser("graph", help="Show graph overview.")
    graph.add_argument("repo")
    graph.add_argument("--limit", type=int, default=20)

    graph_data = sub.add_parser("graph-data", help="Show bounded graph nodes and edges.")
    graph_data.add_argument("repo")
    graph_data.add_argument("--limit", type=int, default=80)

    files = sub.add_parser("files", help="List indexed or skipped files.")
    files.add_argument("repo")
    files.add_argument("--all", action="store_true", help="Include skipped files.")
    files.add_argument("--limit", type=int, default=100)

    symbols = sub.add_parser("symbols", help="List indexed symbols.")
    symbols.add_argument("repo")
    symbols.add_argument("--type")
    symbols.add_argument("--limit", type=int, default=100)

    export = sub.add_parser("export-report", help="Export a Markdown report.")
    export.add_argument("repo")
    export.add_argument("--target")
    export.add_argument("--type", default="auto", choices=["auto", "file", "route", "config", "symbol"])

    export_index = sub.add_parser("export-index", help="Export index archive.")
    export_index.add_argument("repo")
    export_index.add_argument("--destination")

    export_encrypted = sub.add_parser("export-encrypted", help="Export encrypted index archive.")
    export_encrypted.add_argument("repo")
    export_encrypted.add_argument("--destination")
    export_encrypted.add_argument("--passphrase")

    decrypt_archive = sub.add_parser("decrypt-archive", help="Decrypt an encrypted AlosAtlas archive.")
    decrypt_archive.add_argument("repo")
    decrypt_archive.add_argument("encrypted_path")
    decrypt_archive.add_argument("--destination")
    decrypt_archive.add_argument("--passphrase")

    lock_index = sub.add_parser("lock-index", help="Encrypt and remove plaintext local index files.")
    lock_index.add_argument("repo")
    lock_index.add_argument("--passphrase")

    unlock_index = sub.add_parser("unlock-index", help="Restore local index files from encrypted archive.")
    unlock_index.add_argument("repo")
    unlock_index.add_argument("--encrypted-path")
    unlock_index.add_argument("--passphrase")

    delete_index = sub.add_parser("delete-index", help="Delete a repository index.")
    delete_index.add_argument("repo")
    delete_index.add_argument("--keep-files", action="store_true")
    delete_index.add_argument("--unregister", action="store_true")

    refresh = sub.add_parser("refresh", help="Refresh a repository only when stale.")
    refresh.add_argument("repo")
    refresh.add_argument("--full", action="store_true")

    watch_cmd = sub.add_parser("watch", help="Watch a repository and refresh when stale.")
    watch_cmd.add_argument("repo")
    watch_cmd.add_argument("--interval", type=float, default=5.0)
    watch_cmd.add_argument("--once", action="store_true")

    trace = sub.add_parser("trace", help="Record a runtime trace event.")
    trace.add_argument("repo")
    trace.add_argument("--event-type", required=True)
    trace.add_argument("--label", required=True)
    trace.add_argument("--path")
    trace.add_argument("--symbol")
    trace.add_argument("--route")
    trace.add_argument("--endpoint")

    traces = sub.add_parser("traces", help="List runtime traces.")
    traces.add_argument("repo")
    traces.add_argument("--limit", type=int, default=100)

    server = sub.add_parser("serve", help="Run the local AlosAtlas web app and API.")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true", help="Open the app in a browser.")
    server.add_argument("--verbose", action="store_true")
    server.add_argument("--token", help="Require this API token for /api requests.")

    sub.add_parser("mcp", help="Run the MCP-compatible stdio server.")

    return parser


def emit(data: Any, pretty: bool = False) -> None:
    indent = 2 if pretty else None
    print(json.dumps(data, indent=indent, sort_keys=pretty))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = AlosAtlasConfig(Path(args.home).expanduser().resolve() if args.home else None)

    try:
        if args.command == "register":
            profile = config.register(args.name, args.path)
            emit({"registered": profile.to_dict()}, args.pretty)
            return 0

        if args.command == "list-repos":
            emit({"repositories": list_repositories(config)}, args.pretty)
            return 0

        if args.command == "index":
            emit(index_repository(config, args.repo), args.pretty)
            return 0

        if args.command == "status":
            emit(queries_for(config, args.repo).status(), args.pretty)
            return 0

        if args.command == "search":
            emit(queries_for(config, args.repo).search(args.query, args.limit), args.pretty)
            return 0

        if args.command == "file-context":
            emit(queries_for(config, args.repo).file_context(args.path, args.limit), args.pretty)
            return 0

        if args.command == "symbol-context":
            emit(queries_for(config, args.repo).symbol_context(args.symbol, args.limit), args.pretty)
            return 0

        if args.command == "route-context":
            emit(queries_for(config, args.repo).route_context(args.route, args.limit), args.pretty)
            return 0

        if args.command == "impact":
            emit(
                queries_for(config, args.repo).impact(
                    args.target,
                    target_type=args.type,
                    depth=args.depth,
                    limit=args.limit,
                ),
                args.pretty,
            )
            return 0

        if args.command == "change-scope":
            emit(
                queries_for(config, args.repo).change_scope(
                    files=args.files,
                    use_git=args.git,
                    limit=args.limit,
                ),
                args.pretty,
            )
            return 0

        if args.command == "recommend-tests":
            emit(
                queries_for(config, args.repo).recommend_tests(
                    target=args.target,
                    files=args.files,
                    limit=args.limit,
                ),
                args.pretty,
            )
            return 0

        if args.command == "graph":
            emit(queries_for(config, args.repo).graph_overview(limit=args.limit), args.pretty)
            return 0

        if args.command == "graph-data":
            emit(queries_for(config, args.repo).graph_data(limit=args.limit), args.pretty)
            return 0

        if args.command == "files":
            emit(queries_for(config, args.repo).list_files(limit=args.limit, indexed_only=not args.all), args.pretty)
            return 0

        if args.command == "symbols":
            emit(queries_for(config, args.repo).list_symbols(limit=args.limit, type_=args.type), args.pretty)
            return 0

        if args.command == "export-report":
            data = queries_for(config, args.repo).export_report(target=args.target, target_type=args.type)
            print(data["report"], end="")
            return 0

        if args.command == "export-index":
            emit(queries_for(config, args.repo).export_index_archive(destination=args.destination), args.pretty)
            return 0

        if args.command == "export-encrypted":
            emit(
                queries_for(config, args.repo).export_encrypted_archive(
                    destination=args.destination,
                    passphrase=args.passphrase,
                ),
                args.pretty,
            )
            return 0

        if args.command == "decrypt-archive":
            emit(
                queries_for(config, args.repo).decrypt_archive(
                    args.encrypted_path,
                    destination=args.destination,
                    passphrase=args.passphrase,
                ),
                args.pretty,
            )
            return 0

        if args.command == "lock-index":
            emit(queries_for(config, args.repo).lock_index(passphrase=args.passphrase), args.pretty)
            return 0

        if args.command == "unlock-index":
            emit(
                queries_for(config, args.repo).unlock_index(
                    passphrase=args.passphrase,
                    encrypted_path=args.encrypted_path,
                ),
                args.pretty,
            )
            return 0

        if args.command == "delete-index":
            result = queries_for(config, args.repo).delete_index(remove_files=not args.keep_files)
            if args.unregister:
                config.unregister(args.repo)
                result["unregistered"] = True
            emit(result, args.pretty)
            return 0

        if args.command == "refresh":
            emit(
                {"refreshed": True, "status_after": index_repository(config, args.repo)}
                if args.full
                else refresh_if_stale(config, args.repo),
                args.pretty,
            )
            return 0

        if args.command == "watch":
            watch(args.repo, home=config.home, interval=args.interval, once=args.once)
            return 0

        if args.command == "trace":
            emit(
                queries_for(config, args.repo).add_runtime_trace(
                    {
                        "event_type": args.event_type,
                        "label": args.label,
                        "path": args.path,
                        "symbol": args.symbol,
                        "route": args.route,
                        "endpoint": args.endpoint,
                    }
                ),
                args.pretty,
            )
            return 0

        if args.command == "traces":
            emit(queries_for(config, args.repo).runtime_traces(limit=args.limit), args.pretty)
            return 0

        if args.command == "serve":
            serve(
                host=args.host,
                port=args.port,
                home=config.home,
                open_browser=args.open,
                verbose=args.verbose,
                auth_token=args.token,
            )
            return 0

        if args.command == "mcp":
            from .mcp_server import main as mcp_main

            return mcp_main()

    except Exception as exc:
        emit({"error": str(exc), "command": args.command}, args.pretty)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
