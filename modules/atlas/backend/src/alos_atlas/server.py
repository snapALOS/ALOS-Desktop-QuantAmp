"""Local AlosAtlas web app and API server."""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import AlosAtlasConfig
from .indexer import index_repository
from .models import RepositoryProfile
from .query import list_repositories, queries_for
from .watcher import refresh_if_stale


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _param(params: dict[str, list[str]], name: str, default: str = "") -> str:
    values = params.get(name)
    return values[0] if values else default


class AlosAtlasRequestHandler(BaseHTTPRequestHandler):
    server: "AlosAtlasHTTPServer"

    def log_message(self, format: str, *args: object) -> None:
        if self.server.verbose:
            super().log_message(format, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("content-length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path.startswith("/api/"):
                if not self._authorized():
                    self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                self._handle_api_get(parsed.path, params)
            else:
                self._serve_static(parsed.path)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not parsed.path.startswith("/api/"):
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if not self._authorized():
                self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._handle_api_post(parsed.path, self._read_json())
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("content-length") or "0")
        if not length:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def _authorized(self) -> bool:
        token = self.server.auth_token
        if not token:
            return True
        header = self.headers.get("x-alos_atlas-token") or ""
        auth = self.headers.get("authorization") or ""
        return header == token or auth == f"Bearer {token}"

    def _handle_api_get(self, path: str, params: dict[str, list[str]]) -> None:
        config = self.server.config
        repo = _param(params, "repo")
        if path == "/api/health":
            self._send_json({"ok": True, "product": "AlosAtlas"})
        elif path == "/api/repos":
            self._send_json({"repositories": list_repositories(config)})
        elif path == "/api/status":
            self._send_json(queries_for(config, repo).status())
        elif path == "/api/search":
            self._send_json(queries_for(config, repo).search(_param(params, "q"), int(_param(params, "limit", "10"))))
        elif path == "/api/file-context":
            self._send_json(queries_for(config, repo).file_context(_param(params, "path"), int(_param(params, "limit", "20"))))
        elif path == "/api/symbol-context":
            self._send_json(queries_for(config, repo).symbol_context(_param(params, "symbol"), int(_param(params, "limit", "20"))))
        elif path == "/api/route-context":
            self._send_json(queries_for(config, repo).route_context(_param(params, "route"), int(_param(params, "limit", "20"))))
        elif path == "/api/impact":
            self._send_json(
                queries_for(config, repo).impact(
                    _param(params, "target"),
                    target_type=_param(params, "type", "auto"),
                    depth=int(_param(params, "depth", "3")),
                    limit=int(_param(params, "limit", "50")),
                )
            )
        elif path == "/api/change-scope":
            files_arg = _param(params, "files")
            file_list = [item.strip() for item in files_arg.split(",") if item.strip()]
            use_git = _param(params, "git", "false").lower() == "true"
            self._send_json(queries_for(config, repo).change_scope(files=file_list, use_git=use_git))
        elif path == "/api/recommend-tests":
            files_arg = _param(params, "files")
            file_list = [item.strip() for item in files_arg.split(",") if item.strip()]
            self._send_json(queries_for(config, repo).recommend_tests(target=_param(params, "target") or None, files=file_list))
        elif path == "/api/graph":
            self._send_json(queries_for(config, repo).graph_overview())
        elif path == "/api/graph-data":
            self._send_json(queries_for(config, repo).graph_data(limit=int(_param(params, "limit", "80"))))
        elif path == "/api/files":
            indexed_only = _param(params, "indexed_only", "true").lower() != "false"
            self._send_json(queries_for(config, repo).list_files(indexed_only=indexed_only))
        elif path == "/api/symbols":
            type_ = _param(params, "type") or None
            self._send_json(queries_for(config, repo).list_symbols(type_=type_))
        elif path == "/api/profile":
            profile = config.get_profile(repo)
            self._send_json({"profile": profile.to_dict()})
        elif path == "/api/export":
            self._send_json(
                queries_for(config, repo).export_report(
                    target=_param(params, "target") or None,
                    target_type=_param(params, "type", "auto"),
                )
            )
        elif path == "/api/traces":
            self._send_json(queries_for(config, repo).runtime_traces(limit=int(_param(params, "limit", "100"))))
        else:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _handle_api_post(self, path: str, data: dict[str, object]) -> None:
        config = self.server.config
        if path == "/api/register":
            name = str(data.get("name") or "").strip()
            repo_path = str(data.get("path") or "").strip()
            if not name or not repo_path:
                self._send_json({"error": "name and path are required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"registered": config.register(name, repo_path).to_dict()})
        elif path == "/api/index":
            repo = str(data.get("repo") or "").strip()
            if not repo:
                self._send_json({"error": "repo is required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(index_repository(config, repo))
        elif path == "/api/refresh":
            repo = str(data.get("repo") or "").strip()
            if not repo:
                self._send_json({"error": "repo is required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(refresh_if_stale(config, repo))
        elif path == "/api/delete-index":
            repo = str(data.get("repo") or "").strip()
            if not repo:
                self._send_json({"error": "repo is required"}, HTTPStatus.BAD_REQUEST)
                return
            query = queries_for(config, repo)
            result = query.delete_index(remove_files=bool(data.get("remove_files", True)))
            if data.get("unregister", False):
                config.unregister(repo)
                result["unregistered"] = True
            self._send_json(result)
        elif path == "/api/export-index":
            repo = str(data.get("repo") or "").strip()
            destination = data.get("destination")
            self._send_json(queries_for(config, repo).export_index_archive(str(destination) if destination else None))
        elif path == "/api/export-encrypted":
            repo = str(data.get("repo") or "").strip()
            destination = data.get("destination")
            passphrase = data.get("passphrase")
            self._send_json(
                queries_for(config, repo).export_encrypted_archive(
                    str(destination) if destination else None,
                    passphrase=str(passphrase) if passphrase else None,
                )
            )
        elif path == "/api/decrypt-archive":
            repo = str(data.get("repo") or "").strip()
            encrypted_path = str(data.get("encrypted_path") or "").strip()
            destination = data.get("destination")
            passphrase = data.get("passphrase")
            if not repo or not encrypted_path:
                self._send_json({"error": "repo and encrypted_path are required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(
                queries_for(config, repo).decrypt_archive(
                    encrypted_path,
                    destination=str(destination) if destination else None,
                    passphrase=str(passphrase) if passphrase else None,
                )
            )
        elif path == "/api/lock-index":
            repo = str(data.get("repo") or "").strip()
            passphrase = data.get("passphrase")
            self._send_json(queries_for(config, repo).lock_index(passphrase=str(passphrase) if passphrase else None))
        elif path == "/api/unlock-index":
            repo = str(data.get("repo") or "").strip()
            passphrase = data.get("passphrase")
            encrypted_path = data.get("encrypted_path")
            self._send_json(
                queries_for(config, repo).unlock_index(
                    passphrase=str(passphrase) if passphrase else None,
                    encrypted_path=str(encrypted_path) if encrypted_path else None,
                )
            )
        elif path == "/api/traces":
            repo = str(data.get("repo") or "").strip()
            trace = data.get("trace")
            if not repo or not isinstance(trace, dict):
                self._send_json({"error": "repo and trace object are required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send_json(queries_for(config, repo).add_runtime_trace(trace))
        elif path == "/api/profile":
            repo = str(data.get("repo") or "").strip()
            profile_data = data.get("profile")
            if not repo or not isinstance(profile_data, dict):
                self._send_json({"error": "repo and profile object are required"}, HTTPStatus.BAD_REQUEST)
                return
            current = config.get_profile(repo).to_dict()
            current.update(profile_data)
            profile = RepositoryProfile.from_dict(current)
            self._send_json({"profile": config.save_profile(profile).to_dict()})
        elif path == "/api/change-scope":
            repo = str(data.get("repo") or "").strip()
            files_value = data.get("files") or []
            if isinstance(files_value, str):
                file_list = [item.strip() for item in files_value.split(",") if item.strip()]
            else:
                file_list = [str(item) for item in files_value if str(item).strip()]
            self._send_json(
                queries_for(config, repo).change_scope(
                    files=file_list,
                    use_git=bool(data.get("git")),
                    limit=int(data.get("limit") or 50),
                )
            )
        else:
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _serve_static(self, path: str) -> None:
        clean = path.strip("/") or "index.html"
        if "/" in clean or "\\" in clean or clean.startswith("."):
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        resource = files("alos_atlas").joinpath("web", clean)
        if not resource.is_file():
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        data = resource.read_bytes()
        content_type = mimetypes.guess_type(clean)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)

    def _send_cors_headers(self) -> None:
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type, authorization, x-alos_atlas-token")
        self.send_header("access-control-max-age", "600")

    def _send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(data)


class AlosAtlasHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        config: AlosAtlasConfig,
        verbose: bool = False,
        auth_token: str | None = None,
    ) -> None:
        super().__init__(server_address, AlosAtlasRequestHandler)
        self.config = config
        self.verbose = verbose
        self.auth_token = auth_token


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    home: Path | None = None,
    open_browser: bool = False,
    verbose: bool = False,
    auth_token: str | None = None,
) -> None:
    config = AlosAtlasConfig(home)
    config.ensure()
    server = AlosAtlasHTTPServer((host, port), config, verbose=verbose, auth_token=auth_token or os.environ.get("REXNEXUS_API_TOKEN"))
    url = f"http://{host}:{server.server_port}/"
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    print(f"AlosAtlas running at {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
