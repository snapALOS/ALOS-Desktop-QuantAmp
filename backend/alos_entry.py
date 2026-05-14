"""
PyInstaller entry point for the frozen ALOS backend binary.

When users install the packaged app, this is what Rust spawns — a single
self-contained executable that bundles Python, uvicorn, and every
`requirements.txt` dependency. No system Python needed.

Usage (invoked by the Rust sidecar):

    alos-backend --host 127.0.0.1 --port 8000

CLI flags are deliberately kept in parity with `python -m uvicorn` so the
Rust spawn logic can stay oblivious to whether it's running the frozen
binary or a dev-mode Python interpreter.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="alos-backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Override ALOS_DATA_DIR (where logs, memory, and .env are written).",
    )
    args = parser.parse_args()

    # Forward --data-dir into the env so src.core.config picks it up. When
    # launched by the Rust sidecar this is also set via ALOS_DATA_DIR, but
    # supporting the flag form keeps the binary usable standalone.
    if args.data_dir:
        os.environ["ALOS_DATA_DIR"] = args.data_dir

    # PyInstaller sets `sys.frozen` and `sys._MEIPASS` (the unpack dir).
    # When frozen, we want the HuggingFace/Transformers caches to land in
    # the user's data dir — not in the per-launch MEIPASS tmpdir (which
    # gets blown away on exit) and not in ~/.cache (which isn't portable).
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        data_dir = Path(os.environ.get("ALOS_DATA_DIR", "")).expanduser()
        if str(data_dir):
            hf_home = data_dir / "hf-cache"
            hf_home.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("HF_HOME", str(hf_home))
            os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(hf_home))
            os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_home))

    # Import uvicorn lazily so any crash during FastAPI/LangChain import
    # surfaces as a clean traceback *after* argparse has printed usage.
    import uvicorn

    uvicorn.run(
        "src.api.server:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        # `reload` is dev-only and relies on inotify/fsevents; disable
        # unconditionally in the frozen binary.
        reload=False,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
