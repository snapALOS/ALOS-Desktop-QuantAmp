import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.core.config import ENV_PATH, ROOT_DIR
from src.core.setup import REQUIRED_MODULES


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_SCAN_COUNT = 16
HEALTH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class LauncherCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class PortProbe:
    port: int
    available: bool
    occupied_by_alos: bool
    detail: str
    health: Optional[dict[str, Any]] = None


@dataclass(frozen=True)
class LaunchTarget:
    port: Optional[int]
    existing_alos: bool
    ok: bool
    detail: str


def venv_python_path(root: Path = ROOT_DIR) -> Path:
    if os.name == "nt":
        return root / "venv" / "Scripts" / "python.exe"
    return root / "venv" / "bin" / "python"


def pip_cache_dir(root: Path = ROOT_DIR) -> Path:
    return root / "data" / "pip-cache"


def pip_environment(root: Path = ROOT_DIR) -> dict[str, str]:
    env = os.environ.copy()
    cache_dir = pip_cache_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    env["PIP_CACHE_DIR"] = str(cache_dir)
    return env


def configure_pip_cache(python_path: Path, root: Path = ROOT_DIR) -> None:
    cache_dir = pip_cache_dir(root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    if "venv" in python_path.parts:
        venv_root = python_path.parents[1]
        config_path = venv_root / "pip.conf"
        config_path.write_text(f"[global]\ncache-dir = {cache_dir}\n", encoding="utf-8")


def ensure_venv_python(root: Path = ROOT_DIR) -> Path:
    python_path = venv_python_path(root)
    if python_path.exists():
        configure_pip_cache(python_path, root)
        return python_path

    print("ALOS is preparing its local Python environment.")
    subprocess.run([sys.executable, "-m", "venv", str(root / "venv")], check=True, cwd=str(root))
    if not python_path.exists():
        raise RuntimeError(f"Virtual environment was not created at {python_path}")
    configure_pip_cache(python_path, root)
    return python_path


def required_imports() -> list[str]:
    extras = ["pydantic_settings", "requests", "websockets"]
    return sorted(set(REQUIRED_MODULES + extras))


def missing_dependencies(python_path: Path) -> list[str]:
    script = (
        "import importlib.util, json, sys; "
        f"mods = {required_imports()!r}; "
        "missing = [m for m in mods if importlib.util.find_spec(m) is None]; "
        "print(json.dumps(missing)); "
        "sys.exit(1 if missing else 0)"
    )
    result = subprocess.run(
        [str(python_path), "-c", script],
        cwd=str(ROOT_DIR),
        env=pip_environment(),
        capture_output=True,
        text=True,
    )
    try:
        missing = json.loads((result.stdout or "[]").strip() or "[]")
    except json.JSONDecodeError:
        missing = required_imports()
    return missing if isinstance(missing, list) else required_imports()


def install_dependencies(python_path: Path, *, repair: bool = False) -> None:
    command = [str(python_path), "-m", "pip", "install"]
    if repair:
        command.append("--upgrade")
    command.extend(["-r", "requirements.txt"])
    print("ALOS is checking local dependencies.")
    configure_pip_cache(python_path)
    subprocess.run(command, check=True, cwd=str(ROOT_DIR), env=pip_environment())


def ensure_dependencies(python_path: Path, *, repair: bool = False) -> LauncherCheck:
    if repair:
        install_dependencies(python_path, repair=True)
    else:
        missing = missing_dependencies(python_path)
        if missing:
            print(f"ALOS needs dependencies: {', '.join(missing)}")
            install_dependencies(python_path)

    missing_after = missing_dependencies(python_path)
    if missing_after:
        return LauncherCheck(
            "dependencies",
            False,
            f"Missing Python packages after install: {', '.join(missing_after)}",
        )
    return LauncherCheck("dependencies", True, "Python dependencies are ready.")


def is_port_open(host: str, port: int, *, timeout_seconds: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_seconds)
        return sock.connect_ex((host, port)) == 0


def fetch_health(host: str, port: int, *, timeout_seconds: float = 0.75) -> Optional[dict[str, Any]]:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except (OSError, urllib.error.URLError):
        return None

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def health_is_alos(payload: Optional[dict[str, Any]]) -> bool:
    if not payload:
        return False
    return payload.get("status") == "ok" and "configured" in payload and "model" in payload


def probe_port(port: int, *, host: str = DEFAULT_HOST) -> PortProbe:
    if not is_port_open(host, port):
        return PortProbe(port, True, False, f"Port {port} is available.")

    health = fetch_health(host, port)
    if health_is_alos(health):
        return PortProbe(port, False, True, f"ALOS is already running on port {port}.", health)
    return PortProbe(port, False, False, f"Port {port} is occupied by another process.", health)


def choose_launch_target(
    *,
    explicit_port: Optional[int] = None,
    host: str = DEFAULT_HOST,
    start_port: int = DEFAULT_PORT,
    scan_count: int = PORT_SCAN_COUNT,
) -> LaunchTarget:
    if explicit_port is not None:
        probe = probe_port(explicit_port, host=host)
        if probe.occupied_by_alos:
            return LaunchTarget(explicit_port, True, True, probe.detail)
        if probe.available:
            return LaunchTarget(explicit_port, False, True, f"Using explicitly selected port {explicit_port}.")
        return LaunchTarget(explicit_port, False, False, probe.detail)

    probes = [probe_port(port, host=host) for port in range(start_port, start_port + scan_count)]
    for probe in probes:
        if probe.occupied_by_alos:
            return LaunchTarget(probe.port, True, True, probe.detail)
    for probe in probes:
        if probe.available:
            return LaunchTarget(probe.port, False, True, f"Using automatically selected port {probe.port}.")

    return LaunchTarget(
        None,
        False,
        False,
        f"No available local port found from {start_port} to {start_port + scan_count - 1}.",
    )


def validate_env_file(env_path: Path = ENV_PATH) -> LauncherCheck:
    if not env_path.exists():
        return LauncherCheck("env", True, "No .env file yet. The setup wizard will create it.")
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        return LauncherCheck("env", False, f".env could not be read: {exc}")

    malformed = [
        line
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#") and "=" not in line
    ]
    if malformed:
        return LauncherCheck("env", False, ".env contains lines without KEY=VALUE format.")
    return LauncherCheck("env", True, ".env is readable.")


def validate_database() -> LauncherCheck:
    try:
        from src.api import database

        database.init_db()
        with sqlite3.connect(database.DB_PATH) as conn:
            row = conn.execute("PRAGMA integrity_check").fetchone()
    except Exception as exc:
        return LauncherCheck("database", False, f"Database validation failed: {exc}")

    if row and row[0] == "ok":
        return LauncherCheck("database", True, f"Database is healthy: {database.DB_PATH}")
    return LauncherCheck("database", False, f"Database integrity check returned: {row[0] if row else 'unknown'}")


def repair_report(python_path: Path) -> list[LauncherCheck]:
    return [
        ensure_dependencies(python_path, repair=True),
        validate_database(),
        validate_env_file(),
    ]


def wait_for_alos(host: str, port: int, *, timeout_seconds: int = HEALTH_TIMEOUT_SECONDS, process=None) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if health_is_alos(fetch_health(host, port, timeout_seconds=0.5)):
            return True
        time.sleep(0.25)
    return False


def open_alos_browser(host: str, port: int, *, open_browser: bool = True) -> None:
    url = f"http://localhost:{port}"
    print(f"Opening ALOS at {url}")
    if open_browser:
        webbrowser.open(url)


def server_command(python_path: Path, *, host: str, port: int) -> list[str]:
    return [
        str(python_path),
        "-m",
        "uvicorn",
        "src.api.server:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def launch(
    *,
    port: Optional[int] = None,
    host: str = DEFAULT_HOST,
    repair: bool = False,
    open_browser: bool = True,
    diagnose_only: bool = False,
) -> int:
    python_path = ensure_venv_python()
    if repair:
        checks = repair_report(python_path)
    else:
        checks = [
            ensure_dependencies(python_path, repair=False),
            validate_env_file(),
            validate_database(),
        ]

    for check in checks:
        print(f"[{'OK' if check.ok else 'FIX'}] {check.name}: {check.detail}")
    if not all(check.ok for check in checks):
        print("ALOS needs repair before launch can continue.")
        return 1

    target = choose_launch_target(explicit_port=port, host=host)
    print(target.detail)
    if not target.ok or target.port is None:
        return 2

    if diagnose_only:
        return 0

    if target.existing_alos:
        open_alos_browser(host, target.port, open_browser=open_browser)
        return 0

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT_DIR))
    env["ALOS_PORT"] = str(target.port)
    env["PIP_CACHE_DIR"] = str(pip_cache_dir())

    command = server_command(python_path, host=host, port=target.port)
    print("Starting ALOS.")
    process = subprocess.Popen(command, cwd=str(ROOT_DIR), env=env)

    if wait_for_alos(host, target.port, process=process):
        open_alos_browser(host, target.port, open_browser=open_browser)
    elif process.poll() is None:
        print("ALOS is still starting. Opening the local UI now.")
        open_alos_browser(host, target.port, open_browser=open_browser)
    else:
        print("ALOS failed during startup.")
        return process.returncode or 1

    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 130


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch ALOS with guided local diagnostics.")
    parser.add_argument("--port", type=int, default=None, help="Advanced: explicitly select a local port.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Advanced: bind host. Defaults to 127.0.0.1.")
    parser.add_argument("--repair", action="store_true", help="Repair dependencies, database, and environment state before launch.")
    parser.add_argument("--diagnose-only", action="store_true", help="Run launch diagnostics without starting the server.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser after launch.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return launch(
        port=args.port,
        host=args.host,
        repair=args.repair,
        open_browser=not args.no_browser,
        diagnose_only=args.diagnose_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
