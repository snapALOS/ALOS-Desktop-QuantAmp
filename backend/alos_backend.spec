# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the ALOS backend.

The goal is a single binary (`alos-backend` on macOS/Linux,
`alos-backend.exe` on Windows) that the Rust sidecar can spawn without
requiring Python on the user's machine.

Known painful dependencies we handle explicitly below:

  - chromadb            -> dynamic imports via entry points, onnxruntime
                           native libs, sqlite extensions.
  - sentence-transformers -> pulls torch + transformers + tokenizers;
                           model weights are downloaded at first use and
                           cached under ALOS_DATA_DIR (see alos_entry.py).
  - pydantic v2         -> compiled core, needs pydantic._internal stubs.
  - uvicorn/fastapi     -> fine in recent PyInstaller releases, but
                           uvicorn dynamically imports loop/http/ws impls.
  - langchain*          -> lots of optional submodules; we force-include
                           the providers we actually use.
  - bcrypt              -> ships native wheels per platform.

Build from the `backend/` directory with:

    pyinstaller --clean alos_backend.spec
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
)

block_cipher = None

# Make alos_atlas importable for PyInstaller's static analyzer. The
# source lives outside backend/, under modules/atlas/backend/src — we
# add it to pathex so collect_submodules('alos_atlas') works at spec
# evaluation time and so the package gets bundled into the final exe.
_SPEC_DIR = Path(SPECPATH).resolve()
_REPO_ROOT = _SPEC_DIR.parent
_ATLAS_SRC = _REPO_ROOT / "modules" / "atlas" / "backend" / "src"
if _ATLAS_SRC.is_dir():
    sys.path.insert(0, str(_ATLAS_SRC))
else:
    print(f"[spec] WARNING: Atlas source not found at {_ATLAS_SRC}", file=sys.stderr)

# ── Explicit submodule harvesting for libraries PyInstaller's auto-dep
# ── walker doesn't fully resolve. Each entry below was chosen because the
# ── library imports through strings / entry points / registries.
HIDDEN_LIBS = [
    "chromadb",
    "chromadb.telemetry.product.posthog",
    "chromadb.api",
    "chromadb.api.segment",
    "chromadb.db.impl.sqlite",
    "chromadb.segment.impl.manager.local",
    "chromadb.segment.impl.vector.local_persistent_hnsw",
    "chromadb.segment.impl.metadata.sqlite",
    "sentence_transformers",
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "langchain_core",
    "langchain_openai",
    "langchain_anthropic",
    "langgraph",
    "langgraph.graph",
    "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "uvicorn",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "pydantic",
    "pydantic._internal",
    "pydantic.deprecated",
    "passlib.handlers.bcrypt",
    "bcrypt",
    "duckduckgo_search",
    "websockets",
    "websockets.legacy",
    "websockets.legacy.client",
    "websockets.legacy.server",
    # Atlas — code graph indexer (modules/atlas/backend/src/alos_atlas).
    # alos_atlas itself isn't on sys.path until the FastAPI mount pass
    # adds it, so PyInstaller can't auto-discover it. We pre-list every
    # submodule. tree_sitter_languages bundles compiled grammars per
    # language; collect_all (below) pulls the .so/.dylib grammar files
    # into datas so live indexing works inside the frozen sidecar.
    "tree_sitter",
    "tree_sitter_languages",
]

hiddenimports: list[str] = []
datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []

for lib in HIDDEN_LIBS:
    try:
        hiddenimports.extend(collect_submodules(lib))
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect_submodules({lib!r}) failed: {exc}", file=sys.stderr)

# Libraries that ship data files (tokenizer rules, schemas, etc.) need
# `collect_all` instead of just submodules.
for lib in ("chromadb", "transformers", "tokenizers", "huggingface_hub", "tree_sitter_languages"):
    try:
        b, d, h = collect_all(lib)
        binaries.extend(b)
        datas.extend(d)
        hiddenimports.extend(h)
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] collect_all({lib!r}) failed: {exc}", file=sys.stderr)

# Atlas backend source — sits outside the sidecar's import root
# (modules/atlas/backend/src). Vendored at packaging time so the live
# code-graph indexer is available wherever the frozen sidecar runs.
_atlas_src = _REPO_ROOT / "modules" / "atlas" / "backend" / "src"
if _atlas_src.is_dir():
    for py in _atlas_src.rglob("*.py"):
        rel = py.relative_to(_atlas_src.parent)  # keeps "src/alos_atlas/..." prefix
        datas.append((str(py), str(rel.parent)))
    # Web assets + JS parser bridge (kept under alos_atlas/ for runtime use).
    for asset in (_atlas_src / "alos_atlas").rglob("*"):
        if asset.is_file() and asset.suffix in {".js", ".html", ".css", ".json"}:
            rel = asset.relative_to(_atlas_src.parent)
            datas.append((str(asset), str(rel.parent)))
else:
    print(f"[spec] Atlas source not found at {_atlas_src}; skipping bundle.", file=sys.stderr)

# Module backend routers and their support packages. The FastAPI backend
# discovers modules from a filesystem `modules/` tree at startup; PyInstaller
# does not include those dynamically loaded routers unless we stage them as
# data files.
_modules_root = _REPO_ROOT / "modules"
if _modules_root.is_dir():
    for backend_src in _modules_root.glob("*/backend/src"):
        if not backend_src.is_dir():
            continue
        for asset in backend_src.rglob("*"):
            if not asset.is_file() or "__pycache__" in asset.parts or asset.suffix == ".pyc":
                continue
            rel = asset.relative_to(_REPO_ROOT)
            datas.append((str(asset), str(rel.parent)))
else:
    print(f"[spec] Modules root not found at {_modules_root}; skipping module routers.", file=sys.stderr)

# The backend source tree itself — imported via `src.api.server:app`.
datas.extend(collect_data_files("src", include_py_files=True))

a = Analysis(
    ["alos_entry.py"],
    pathex=[str(Path(".").resolve())],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Excludes trim the bundle. We deliberately ship pytest for the
    # backend's test endpoints to still work, but anything GUI-heavy is
    # dead weight in a headless server binary.
    excludes=[
        "tkinter",
        "PyQt5",
        "PyQt6",
        "PySide2",
        "PySide6",
        "matplotlib",
        "IPython",
        "notebook",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="alos-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="alos-backend",
)
