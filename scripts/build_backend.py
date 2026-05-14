#!/usr/bin/env python3
"""
Freeze the ALOS Python backend into a standalone binary using PyInstaller
and stage it under `src-tauri/resources/` so the Tauri bundler picks it up.

Intended flow:

    # one-time: install the toolchain
    cd backend
    python3 -m venv .venv-build
    .venv-build/bin/pip install -r requirements.txt pyinstaller

    # every release:
    python3 scripts/build_backend.py

The resulting layout:

    src-tauri/resources/backend/
        alos-backend           # or alos-backend.exe on Windows
        _internal/             # PyInstaller bundle tree

Tauri then copies this entire directory into the final `.app`/`.msi`
because `tauri.conf.json` lists `resources/backend/**` as a bundle resource.

The Rust sidecar (`src-tauri/src/backend.rs`) prefers the frozen binary
when it exists; otherwise it falls back to the dev-mode Python interpreter
path we already support.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
SPEC_PATH = BACKEND_DIR / "alos_backend.spec"
OUTPUT_STAGE = REPO_ROOT / "src-tauri" / "resources" / "backend"


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print(f"[build_backend] $ {' '.join(cmd)} (cwd={cwd})")
    result = subprocess.run(cmd, cwd=str(cwd), env=env)
    if result.returncode != 0:
        sys.exit(f"[build_backend] command failed with exit code {result.returncode}")


def resolve_python(venv_hint: Path | None) -> Path:
    """
    Use an explicit venv when provided, otherwise fall back to the current
    interpreter. We require PyInstaller to be importable from whichever
    Python we use.
    """
    if venv_hint is not None:
        candidate = (
            venv_hint / ("Scripts" if os.name == "nt" else "bin") /
            ("python.exe" if os.name == "nt" else "python")
        )
        if not candidate.is_file():
            sys.exit(f"[build_backend] no Python found at {candidate}")
        return candidate
    return Path(sys.executable)


def ensure_pyinstaller(python: Path) -> None:
    check = subprocess.run(
        [str(python), "-c", "import PyInstaller; print(PyInstaller.__version__)"],
        capture_output=True,
        text=True,
    )
    if check.returncode != 0:
        sys.exit(
            "[build_backend] PyInstaller is not installed in the selected Python.\n"
            f"    pip install pyinstaller  (into {python})"
        )
    print(f"[build_backend] PyInstaller {check.stdout.strip()} OK")


def clean_prior_outputs() -> None:
    for name in ("build", "dist"):
        path = BACKEND_DIR / name
        if path.exists():
            print(f"[build_backend] removing stale {path}")
            shutil.rmtree(path)
    if OUTPUT_STAGE.exists():
        print(f"[build_backend] removing stale {OUTPUT_STAGE}")
        shutil.rmtree(OUTPUT_STAGE)


def run_pyinstaller(python: Path) -> Path:
    run(
        [str(python), "-m", "PyInstaller", "--clean", "--noconfirm", str(SPEC_PATH)],
        cwd=BACKEND_DIR,
    )
    built = BACKEND_DIR / "dist" / "alos-backend"
    if not built.is_dir():
        sys.exit(f"[build_backend] expected PyInstaller output at {built}, not found")
    return built


def stage_into_tauri(built: Path) -> None:
    OUTPUT_STAGE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(built, OUTPUT_STAGE)
    exe = OUTPUT_STAGE / ("alos-backend.exe" if os.name == "nt" else "alos-backend")
    if not exe.is_file():
        sys.exit(f"[build_backend] expected staged executable at {exe}, not found")
    # Mark executable bit on unix — copytree preserves mode, but belt-and-suspenders.
    if os.name != "nt":
        exe.chmod(0o755)
    print(f"[build_backend] staged frozen backend -> {OUTPUT_STAGE}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--venv",
        type=Path,
        default=None,
        help="Path to a venv whose Python has PyInstaller + requirements installed.",
    )
    parser.add_argument(
        "--skip-clean",
        action="store_true",
        help="Leave existing build/dist output in place (faster iteration).",
    )
    args = parser.parse_args()

    python = resolve_python(args.venv)
    ensure_pyinstaller(python)

    if not args.skip_clean:
        clean_prior_outputs()

    built = run_pyinstaller(python)
    stage_into_tauri(built)

    print("[build_backend] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
