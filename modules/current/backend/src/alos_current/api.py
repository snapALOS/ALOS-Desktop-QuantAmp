from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .compiler import ValidationError
from .service import AlosCurrentService
from .storage import AlosCurrentStore


def _json(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


class AlosCurrentHandler(BaseHTTPRequestHandler):
    server: "AlosCurrentHTTPServer"

    def log_message(self, format: str, *args: object) -> None:
        if self.server.verbose:
            super().log_message(format, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("content-length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if not parsed.path.startswith("/api/"):
                self._serve_static(parsed.path)
                return
            if not self._authorized(params):
                self._send({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            self._handle_get(parsed.path, params)
        except Exception as exc:
            self._handle_error(exc)

    def do_POST(self) -> None:
        self._method_with_body("POST")

    def do_PUT(self) -> None:
        self._method_with_body("PUT")

    def do_DELETE(self) -> None:
        self._method_with_body("DELETE")

    def _method_with_body(self, method: str) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if method == "POST" and parsed.path.startswith("/webhook/"):
                if not self._authorized(params):
                    self._send({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                self._send(self.server.service.execute_webhook(parsed.path, self._read_json()))
                return
            if not parsed.path.startswith("/api/"):
                self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            if not self._authorized(params):
                self._send({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                return
            data = self._read_json()
            self._handle_write(method, parsed.path, data)
        except Exception as exc:
            self._handle_error(exc)

    def _authorized(self, params: dict[str, list[str]] | None = None) -> bool:
        token = self.server.auth_token
        if not token:
            return True
        header = self.headers.get("x-alos_current-token") or ""
        auth = self.headers.get("authorization") or ""
        query_token = _first(params or {}, "token") or ""
        return header == token or auth == f"Bearer {token}" or query_token == token

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("content-length") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_get(self, path: str, params: dict[str, list[str]]) -> None:
        service = self.server.service
        parts = [part for part in path.split("/") if part]
        if path == "/api/health":
            self._send(service.health())
        elif path == "/api/events/stream":
            self._stream_events(params)
        elif path == "/api/nodes":
            self._send(service.nodes())
        elif path == "/api/workflows":
            self._send(service.list_workflows())
        elif len(parts) == 3 and parts[:2] == ["api", "workflows"]:
            self._send({"workflow": service.get_workflow(parts[2])})
        elif len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "versions":
            self._send(service.versions(parts[2]))
        elif path == "/api/executions":
            self._send(service.executions())
        elif len(parts) == 3 and parts[:2] == ["api", "executions"]:
            execution_id = parts[2]
            self._send({"execution": service.get_execution(execution_id), "steps": service.steps(execution_id)["steps"]})
        elif len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "steps":
            self._send(service.steps(parts[2]))
        elif len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "events":
            self._send(service.events(execution_id=parts[2]))
        elif path == "/api/events":
            execution_id = _first(params, "executionId")
            self._send(service.events(execution_id=execution_id))
        elif path == "/api/tasks":
            self._send(service.tasks())
        elif len(parts) == 3 and parts[:2] == ["api", "tasks"]:
            self._send({"task": service.get_task(parts[2])})
        elif path == "/api/swarm":
            self._send(service.swarm())
        elif path == "/api/audit":
            self._send(service.audit_log())
        else:
            self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _handle_write(self, method: str, path: str, data: dict[str, object]) -> None:
        service = self.server.service
        parts = [part for part in path.split("/") if part]
        if method == "POST" and path == "/api/workflows":
            self._send(service.create_workflow(data))
        elif method == "PUT" and len(parts) == 3 and parts[:2] == ["api", "workflows"]:
            self._send(service.update_workflow(parts[2], data))
        elif method == "DELETE" and len(parts) == 3 and parts[:2] == ["api", "workflows"]:
            self._send(service.archive_workflow(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "duplicate":
            self._send(service.duplicate_workflow(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "validate":
            self._send(service.validate_workflow(parts[2]))
        elif method == "POST" and path == "/api/validate":
            graph = data.get("graph")
            if not isinstance(graph, dict):
                self._send({"error": "graph object required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send(service.validate_workflow(graph=graph))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "publish":
            self._send(service.publish_workflow(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "workflows"] and parts[3] == "execute":
            variables = data.get("variables") if isinstance(data.get("variables"), dict) else {}
            self._send(service.execute_workflow(parts[2], variables=variables))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "resume":
            self._send(service.resume_execution(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "retry":
            self._send(service.retry_execution(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "cancel":
            self._send(service.cancel_execution(parts[2]))
        elif method == "POST" and len(parts) == 4 and parts[:2] == ["api", "executions"] and parts[3] == "approve":
            node_id = str(data.get("nodeId") or "")
            if not node_id:
                self._send({"error": "nodeId required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send(service.approve_execution(parts[2], node_id=node_id, approved=bool(data.get("approved", True))))
        elif method == "POST" and path == "/api/recover":
            self._send(service.recover())
        elif method == "POST" and path == "/api/triggers/rexhub":
            event_type = str(data.get("eventType") or data.get("type") or "")
            if not event_type:
                self._send({"error": "eventType required"}, HTTPStatus.BAD_REQUEST)
                return
            self._send(service.execute_rexhub_event(event_type, data))
        elif method == "POST" and path == "/api/schedules/run":
            schedule = data.get("schedule")
            self._send(service.run_schedules(str(schedule) if schedule else None))
        elif method == "POST" and path == "/api/tasks":
            self._send(service.create_task(data))
        elif method == "PUT" and len(parts) == 3 and parts[:2] == ["api", "tasks"]:
            self._send(service.update_task(parts[2], data))
        else:
            self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _handle_error(self, exc: Exception) -> None:
        status = HTTPStatus.BAD_REQUEST if isinstance(exc, (KeyError, ValueError, ValidationError)) else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send({"error": str(exc)}, status)

    def _cors(self) -> None:
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type, authorization, x-alos_current-token")
        self.send_header("access-control-max-age", "600")

    def _send(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = _json(payload)
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _stream_events(self, params: dict[str, list[str]]) -> None:
        execution_id = _first(params, "executionId")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache")
        self.send_header("connection", "keep-alive")
        self._cors()
        self.end_headers()
        seen: set[str] = set()
        try:
            for _ in range(120):
                events = self.server.service.events(execution_id=execution_id, limit=50)["events"]
                fresh = [event for event in reversed(events) if event["id"] not in seen]
                for event in fresh:
                    seen.add(event["id"])
                    payload = json.dumps(event, sort_keys=True)
                    self.wfile.write(f"id: {event['id']}\nevent: alos_current\ndata: {payload}\n\n".encode("utf-8"))
                if not fresh:
                    self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _serve_static(self, path: str) -> None:
        root = Path(__file__).resolve().parents[3] / "app" / "dist"
        clean = path.split("?", 1)[0].lstrip("/") or "index.html"
        if clean.endswith("/"):
            clean += "index.html"
        target = (root / clean).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            self._send({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        if not target.exists() or not target.is_file():
            target = root / "index.html"
        if not target.exists():
            self._send({"error": "frontend build not found; run npm run build in app"}, HTTPStatus.NOT_FOUND)
            return
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("content-length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


class AlosCurrentHTTPServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], service: AlosCurrentService, verbose: bool = False, auth_token: str | None = None) -> None:
        super().__init__(address, AlosCurrentHandler)
        self.service = service
        self.verbose = verbose
        self.auth_token = auth_token


def serve(
    host: str = "127.0.0.1",
    port: int = 8770,
    home: str | Path | None = None,
    open_browser: bool = False,
    verbose: bool = False,
    auth_token: str | None = None,
) -> None:
    service = AlosCurrentService(AlosCurrentStore(home))
    token = auth_token or os.environ.get("REXFLOW_API_TOKEN")
    server = AlosCurrentHTTPServer((host, port), service, verbose=verbose, auth_token=token)
    url = f"http://{host}:{server.server_port}/api/health"
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"AlosCurrent API running at http://{host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values else None
