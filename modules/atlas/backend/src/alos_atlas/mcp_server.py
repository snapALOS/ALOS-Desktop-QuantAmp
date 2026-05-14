"""Small MCP-compatible stdio server for AlosAtlas tools.

This implements the JSON-RPC calls needed by common MCP clients:
`initialize`, `tools/list`, and `tools/call`. It intentionally depends only on
the Python standard library.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .tool_adapter import (
    alos_atlas_change_scope,
    alos_atlas_decrypt_archive,
    alos_atlas_file_context,
    alos_atlas_export_report,
    alos_atlas_export_encrypted,
    alos_atlas_export_index,
    alos_atlas_files,
    alos_atlas_graph,
    alos_atlas_graph_data,
    alos_atlas_impact,
    alos_atlas_index,
    alos_atlas_list_repos,
    alos_atlas_lock_index,
    alos_atlas_query,
    alos_atlas_recommend_tests,
    alos_atlas_route_context,
    alos_atlas_status,
    alos_atlas_symbols,
    alos_atlas_trace,
    alos_atlas_traces,
    alos_atlas_symbol_context,
    alos_atlas_unlock_index,
)


ToolFunc = Callable[..., dict[str, Any]]

TOOLS: dict[str, tuple[str, ToolFunc, dict[str, Any]]] = {
    "alos_atlas_list_repos": (
        "List registered AlosAtlas repositories.",
        alos_atlas_list_repos,
        {"type": "object", "properties": {"home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_status": (
        "Return repository freshness and index status.",
        alos_atlas_status,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}}},
    ),
    "alos_atlas_query": (
        "Search indexed structural evidence.",
        alos_atlas_query,
        {"type": "object", "required": ["repo", "query"], "properties": {"repo": {"type": "string"}, "query": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_symbol_context": (
        "Return bounded context for a symbol.",
        alos_atlas_symbol_context,
        {"type": "object", "required": ["repo", "symbol"], "properties": {"repo": {"type": "string"}, "symbol": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_file_context": (
        "Return bounded context for a file.",
        alos_atlas_file_context,
        {"type": "object", "required": ["repo", "path"], "properties": {"repo": {"type": "string"}, "path": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_route_context": (
        "Return bounded context for a route or endpoint.",
        alos_atlas_route_context,
        {"type": "object", "required": ["repo", "route"], "properties": {"repo": {"type": "string"}, "route": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_impact": (
        "Return an impact report for a target.",
        alos_atlas_impact,
        {"type": "object", "required": ["repo", "target"], "properties": {"repo": {"type": "string"}, "target": {"type": "string"}, "target_type": {"type": "string"}, "home": {"type": "string"}, "depth": {"type": "integer"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_change_scope": (
        "Return a change-scope report from files or git diff.",
        alos_atlas_change_scope,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}, "home": {"type": "string"}, "use_git": {"type": "boolean"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_recommend_tests": (
        "Recommend tests for a target or files.",
        alos_atlas_recommend_tests,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "target": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_graph": (
        "Return graph overview counts and top files.",
        alos_atlas_graph,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_graph_data": (
        "Return bounded graph nodes and edges.",
        alos_atlas_graph_data,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_files": (
        "List indexed or skipped files.",
        alos_atlas_files,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}, "indexed_only": {"type": "boolean"}}},
    ),
    "alos_atlas_symbols": (
        "List indexed symbols.",
        alos_atlas_symbols,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}, "type_": {"type": "string"}}},
    ),
    "alos_atlas_export_report": (
        "Export a Markdown report.",
        alos_atlas_export_report,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "target": {"type": "string"}, "target_type": {"type": "string"}}},
    ),
    "alos_atlas_export_index": (
        "Export a local index archive.",
        alos_atlas_export_index,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "destination": {"type": "string"}}},
    ),
    "alos_atlas_export_encrypted": (
        "Export an encrypted local index archive.",
        alos_atlas_export_encrypted,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "destination": {"type": "string"}, "passphrase": {"type": "string"}}},
    ),
    "alos_atlas_decrypt_archive": (
        "Decrypt a AlosAtlas encrypted index archive.",
        alos_atlas_decrypt_archive,
        {"type": "object", "required": ["repo", "encrypted_path"], "properties": {"repo": {"type": "string"}, "encrypted_path": {"type": "string"}, "home": {"type": "string"}, "destination": {"type": "string"}, "passphrase": {"type": "string"}}},
    ),
    "alos_atlas_lock_index": (
        "Encrypt and remove plaintext local index files.",
        alos_atlas_lock_index,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "passphrase": {"type": "string"}}},
    ),
    "alos_atlas_unlock_index": (
        "Restore local index files from an encrypted archive.",
        alos_atlas_unlock_index,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "encrypted_path": {"type": "string"}, "passphrase": {"type": "string"}}},
    ),
    "alos_atlas_traces": (
        "List runtime traces.",
        alos_atlas_traces,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "limit": {"type": "integer"}}},
    ),
    "alos_atlas_trace": (
        "Record a runtime trace.",
        alos_atlas_trace,
        {"type": "object", "required": ["repo", "trace"], "properties": {"repo": {"type": "string"}, "trace": {"type": "object"}, "home": {"type": "string"}}},
    ),
    "alos_atlas_index": (
        "Index a repository. Requires explicit allow_heavy_indexing=true.",
        alos_atlas_index,
        {"type": "object", "required": ["repo"], "properties": {"repo": {"type": "string"}, "home": {"type": "string"}, "allow_heavy_indexing": {"type": "boolean"}}},
    ),
}


def tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": schema,
        }
        for name, (description, _func, schema) in TOOLS.items()
    ]


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    try:
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "alos_atlas", "version": "0.1.0"},
                    "capabilities": {"tools": {}},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tool_list()}}
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS:
                raise KeyError(f"unknown tool: {name}")
            result = TOOLS[name][1](**arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, sort_keys=True)}],
                    "isError": False,
                },
            }
        if msg_id is None:
            return None
        raise KeyError(f"unsupported method: {method}")
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = handle(message)
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
