# Building ALOS Desktop

This repo produces two things:

1. **Dev mode** — `bun run tauri dev` spins up the Tauri shell, the React
   frontend, and the Python backend using a developer-managed Python
   environment. Users of the app never run this.
2. **Release build** — `bun run tauri build` produces signed-ready
   `.dmg`/`.msi`/`.AppImage` installers that bundle Python, all
   dependencies, and the backend source into a single self-contained
   `alos-backend` binary. End users only ever install this.

---

## Dev mode (developers only)

You need:

- Node 20+ and Bun
- Rust stable
- Python 3.9+ on PATH

```bash
bun install
bun run tauri dev
```

On first launch the app detects missing Python dependencies and offers
to create a venv at `~/Library/Application Support/com.alos.desktop/venv`
and install `backend/requirements.txt` into it. Accept once; future
launches skip straight to the app.

Backend state (`.env`, logs, memory, SQLite DB) lives under
`~/Library/Application Support/com.alos.desktop/`. If you prefer the
pre-fork behavior of writing into `backend/`, run the backend directly:

```bash
cd backend
python -m uvicorn src.api.server:app --port 8000
```

The `pyproject.toml` presence check in `src/core/config.py` keeps dev
state local in that mode.

### First-run admin setup

On a fresh local data directory, ALOS creates the original admin from inside the
app after provider setup. The normal packaged-app path does not require running
`python -m src.auth.bootstrap_admin`.

Packaged macOS auth state lives in:

```text
~/Library/Application Support/com.alos.desktop/alos_memory.db
```

The terminal bootstrap script remains only for developer or explicit recovery
work. If you use it for a packaged-app recovery, set `ALOS_DATA_DIR` to the
packaged data directory so it does not create keys in the development database.

---

## Release build

A release requires:

- Everything from dev mode, **plus**
- A build-time Python environment with `pyinstaller` installed and every
  package from `backend/requirements.txt` imported successfully. The
  recommended layout:

  ```bash
  cd backend
  python3 -m venv .venv-build
  .venv-build/bin/pip install -r requirements.txt pyinstaller
  ```

### One command

```bash
bun run tauri build
```

`tauri.conf.json` chains the steps:

1. `bun run build` — Vite produces `dist/`
2. `python3 ../scripts/build_backend.py` — runs PyInstaller via
   `backend/alos_backend.spec`, stages the frozen binary tree into
   `src-tauri/resources/backend/`
3. Tauri bundler picks up `src-tauri/resources/backend/**` (declared in
   `bundle.resources`) and includes it in the final installer

### What ends up inside the installer

```
ALOS.app/Contents/Resources/
    resources/backend/
        alos-backend            # frozen executable entry point
        _internal/              # PyInstaller's unpacked bundle
            base_library.zip
            libpython3.*.dylib  (or .dll / .so)
            torch/ ...
            chromadb/ ...
            sentence_transformers/ ...
            ...
```

At runtime the Rust sidecar (`src-tauri/src/backend.rs`) looks for that
binary in `app.path().resource_dir()`. When present, it spawns it
directly and never touches the user's system Python. When absent (dev
mode), it falls back to the preflight-managed venv path.

### Expected size

ALOS's dependency stack is heavy:

- torch + transformers + sentence-transformers: ~700MB
- chromadb + onnxruntime: ~200MB
- everything else: ~100MB

Expect the final `.dmg` to land around **800MB–1.2GB** depending on
platform. UPX compression is disabled in the spec because it breaks
several of these native deps.

---

## Build environment caveats

### The PyInstaller build must be reproducible

PyInstaller produces a binary for **the OS and architecture it was built
on** — a Mac arm64 build won't run on Windows or Mac Intel. To ship all
three, you must run the build on each target platform. CI matrices or a
physical machine per target.

### Hidden imports will need iteration

`backend/alos_backend.spec` lists the libraries we know need explicit
`collect_submodules()` / `collect_all()` calls because their
import graphs defeat PyInstaller's automatic analysis. The first few
builds on a new host will likely surface more: watch for
`ModuleNotFoundError` in the frozen binary's stderr and add to the
`HIDDEN_LIBS` list.

### Model weights

`sentence-transformers` downloads `all-MiniLM-L6-v2` (~80MB) on first
use. The frozen backend sets `HF_HOME`, `SENTENCE_TRANSFORMERS_HOME`,
and `TRANSFORMERS_CACHE` to `{USER_DATA_DIR}/hf-cache` so the download
lands in a persistent, user-writable location — not in the read-only
app bundle and not in per-launch temp dirs.

If you want a fully offline-capable installer, pre-download the model
and include it as an additional `data` entry in the PyInstaller spec.

### Code signing

Not currently configured. On macOS, users will hit a Gatekeeper prompt
on first launch; they can right-click → Open to bypass. When an Apple
Developer ID becomes available, fill in `bundle.macOS.signingIdentity`
and add an `entitlements.plist`. Windows code signing (EV certificate)
ditto — `bundle.windows.certificateThumbprint`.

### Antivirus false positives

PyInstaller binaries trip some Windows AV engines. If users report
quarantines, the fix is code signing (above) plus submitting the binary
to the vendor for whitelisting.

---

## Troubleshooting

### "Backend failed to start: The ALOS runtime bundle appears to be damaged"

The Rust sidecar detected a Python `ImportError` or `ModuleNotFoundError`
in the frozen binary's stderr during the first 20 seconds of startup.
This almost always means a hidden import is missing from
`alos_backend.spec`. Reproduce locally:

```bash
./src-tauri/resources/backend/alos-backend --host 127.0.0.1 --port 8001
```

The traceback will tell you what to add to `HIDDEN_LIBS`.

### `bun run tauri dev` can't find Python

The preflight gate wants Python 3.9+ on PATH. On macOS, install via
Homebrew (`brew install python@3.11`) or from python.org. On Windows,
python.org's installer checks "Add to PATH" by default.

### "Can't create virtualenv" during preflight install

Happens when the system Python ships without `venv` (e.g. minimal Linux
images). `sudo apt install python3-venv` or equivalent. End users of
**packaged** builds never hit this — they have no Python.
