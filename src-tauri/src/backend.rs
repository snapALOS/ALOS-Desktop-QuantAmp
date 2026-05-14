//! ALOS Python backend lifecycle management.
//!
//! Responsibilities:
//!   - Resolve the backend's working directory and the Python interpreter
//!     to use (dev vs. bundled-resource layouts).
//!   - Spawn the backend as a child process (uvicorn).
//!   - Forward stdout/stderr lines into the Tauri log plugin so they show
//!     up in the devtools and log files.
//!   - Expose graceful and forceful shutdown so the Tauri Exit handler
//!     can tear the backend down cleanly when the app quits.
//!
//! Production bundling (PyInstaller single-file) is out of scope for
//! this module; for now we assume a Python environment is available.
//! The `find_python` logic is future-proofed for a bundled interpreter.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Context, Result};
use tauri::{AppHandle, Emitter, Manager};

/// Default port the backend binds to. Matches hardcoded frontend base URL.
pub const BACKEND_PORT: u16 = 8000;

/// Global handle to the backend child process. `None` when not running.
static BACKEND_CHILD: Mutex<Option<Child>> = Mutex::new(None);

/// Last spawn error, if any — exposed via the `backend_status` Tauri command
/// so the splash screen can show an actionable message instead of a
/// generic "Backend offline".
static LAST_SPAWN_ERROR: Mutex<Option<String>> = Mutex::new(None);

#[derive(serde::Serialize)]
pub struct BackendStatus {
    pub port: u16,
    pub running: bool,
    pub last_error: Option<String>,
}

/// Frontend-invoked spawn. Called after the preflight gate clears so the
/// backend can come up without requiring an app restart.
#[tauri::command]
pub fn launch_backend(app: AppHandle) -> Result<(), String> {
    spawn(&app).map_err(|e| format!("{e:#}"))
}

#[tauri::command]
pub fn backend_status() -> BackendStatus {
    let running = BACKEND_CHILD.lock().map(|g| g.is_some()).unwrap_or(false);
    let last_error = LAST_SPAWN_ERROR.lock().ok().and_then(|g| g.clone());
    BackendStatus {
        port: BACKEND_PORT,
        running,
        last_error,
    }
}

fn record_spawn_error(err: &anyhow::Error) {
    if let Ok(mut guard) = LAST_SPAWN_ERROR.lock() {
        *guard = Some(format!("{err:#}"));
    }
}

fn clear_spawn_error() {
    if let Ok(mut guard) = LAST_SPAWN_ERROR.lock() {
        *guard = None;
    }
}

/// Describes how the backend was launched — used for logging and by the
/// preflight gate to decide whether runtime dependency checks are relevant.
#[derive(Clone, Copy, Debug)]
pub enum LaunchMode {
    /// Frozen PyInstaller binary shipping inside the app bundle. End-user path.
    Bundled,
    /// System Python + user venv. Developer path.
    Python,
}

/// Spawn the backend if it isn't already running.
///
/// Two modes:
///
///   1. `Bundled` — a PyInstaller binary shipped as a Tauri resource.
///      Used in production builds. Requires no Python on the user's system.
///
///   2. `Python` — invoke `python -m uvicorn` against the backend source
///      tree. Used for `tauri dev` and source-based dev workflows. Needs
///      the preflight gate to have installed deps into a venv first.
pub fn spawn(app: &AppHandle) -> Result<()> {
    let mut guard = BACKEND_CHILD.lock().expect("backend mutex poisoned");
    if guard.is_some() {
        log::info!("backend: already running");
        return Ok(());
    }

    let data_dir = resolve_user_data_dir(app);
    if let Some(dir) = &data_dir {
        let _ = std::fs::create_dir_all(dir);
    }

    let (mode, mut cmd) = if let Some(bundled) = find_bundled_binary(app) {
        log::info!(
            "backend: spawning bundled binary -> {} (data_dir={:?} port={})",
            bundled.display(),
            data_dir,
            BACKEND_PORT
        );
        let mut c = Command::new(&bundled);
        c.args([
            "--host",
            "127.0.0.1",
            "--port",
            &BACKEND_PORT.to_string(),
            "--log-level",
            "info",
        ]);
        (LaunchMode::Bundled, c)
    } else {
        let backend_dir = resolve_backend_dir(app).inspect_err(record_spawn_error)?;
        let python = find_python(&backend_dir).inspect_err(record_spawn_error)?;
        log::info!(
            "backend: spawning python -> {} (cwd={} data_dir={:?} port={})",
            python.display(),
            backend_dir.display(),
            data_dir,
            BACKEND_PORT
        );
        let mut c = Command::new(&python);
        c.current_dir(&backend_dir)
            .env("PYTHONPATH", backend_dir.as_os_str())
            .args([
                "-m",
                "uvicorn",
                "src.api.server:app",
                "--host",
                "127.0.0.1",
                "--port",
                &BACKEND_PORT.to_string(),
                "--log-level",
                "info",
            ]);
        (LaunchMode::Python, c)
    };

    cmd.env("PYTHONUNBUFFERED", "1");
    if let Some(dir) = &data_dir {
        cmd.env("ALOS_DATA_DIR", dir);
    }
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = cmd
        .spawn()
        .with_context(|| format!("failed to spawn backend ({:?})", mode))
        .inspect_err(record_spawn_error)?;

    let child_pid = child.id();
    log::info!("backend: spawned child pid={} (mode={:?})", child_pid, mode);

    // Liveness probe: `Command::spawn` returns Ok the moment fork/exec
    // succeeds. The child may die a millisecond later (codesigning gate,
    // dyld failure, instant import crash) and we'd never know, because
    // stderr is pipe-drained by the background thread without surfacing
    // exit status. Wait briefly, and if the child is already gone, capture
    // the exit code + drained stderr into LAST_SPAWN_ERROR so the splash
    // screen can show it instead of a generic "Backend offline".
    thread::sleep(Duration::from_millis(500));
    match child.try_wait() {
        Ok(Some(status)) => {
            // Child already exited. Drain stderr synchronously (no background
            // thread needed — the pipe is closed) and record the failure.
            let mut stderr_snapshot = String::new();
            if let Some(mut stderr) = child.stderr.take() {
                use std::io::Read;
                let _ = stderr.read_to_string(&mut stderr_snapshot);
            }
            let detail = stderr_snapshot.trim();
            let detail = if detail.is_empty() {
                "(no stderr output)".to_string()
            } else {
                // Cap to keep the error message small.
                let max = 2048;
                if detail.len() > max {
                    format!("…{}", &detail[detail.len() - max..])
                } else {
                    detail.to_string()
                }
            };
            let msg = format!(
                "backend exited immediately after spawn (mode={:?}, status={:?}, pid was {}): {}",
                mode, status, child_pid, detail
            );
            log::error!("{msg}");
            if let Ok(mut guard) = LAST_SPAWN_ERROR.lock() {
                *guard = Some(msg.clone());
            }
            return Err(anyhow!(msg));
        }
        Ok(None) => {
            // Still alive — good. Fall through to the pipe-reader setup.
        }
        Err(e) => {
            log::warn!("backend: try_wait probe failed: {e}; assuming child is alive");
        }
    }

    clear_spawn_error();

    // Stream stdout / stderr into the Tauri log pipeline. On stderr we
    // also watch for Python import failures during the first few seconds
    // of startup; those mean the bundled runtime is broken (corrupted
    // download, antivirus quarantine, missing shared library) and we want
    // to surface a friendlier message than a silent "Backend offline".
    if let Some(stdout) = child.stdout.take() {
        let handle = app.clone();
        thread::spawn(move || pipe_lines("stdout", stdout, Some(handle)));
    }
    if let Some(stderr) = child.stderr.take() {
        thread::spawn(move || watch_stderr(mode, stderr));
    }

    *guard = Some(child);
    Ok(())
}

/// If a frozen PyInstaller binary has been staged as a Tauri resource,
/// return its path. This is the production path — the Rust sidecar runs
/// the frozen binary directly, no Python on the user's machine required.
/// Public accessor so other modules (like preflight) can ask whether the
/// packaged app ships its own frozen runtime.
pub fn bundled_binary_present(app: &AppHandle) -> bool {
    find_bundled_binary(app).is_some()
}

fn find_bundled_binary(app: &AppHandle) -> Option<PathBuf> {
    let resource_dir = app.path().resource_dir().ok()?;
    let exe_name = if cfg!(windows) {
        "alos-backend.exe"
    } else {
        "alos-backend"
    };
    let candidate = resource_dir
        .join("resources")
        .join("backend")
        .join(exe_name);
    if candidate.is_file() {
        return Some(candidate);
    }
    // Tauri's resource path layout varies by platform; also try the flatter form.
    let flatter = resource_dir.join("backend").join(exe_name);
    if flatter.is_file() {
        return Some(flatter);
    }
    None
}

/// Read stderr line-by-line. Forwards everything to the log pipeline, and
/// for the first ~20 seconds scans for the distinctive shapes of Python
/// import-time failures so we can surface an actionable message.
fn watch_stderr<R: std::io::Read + Send + 'static>(mode: LaunchMode, stream: R) {
    use std::time::Instant;
    let reader = BufReader::new(stream);
    let deadline = Instant::now() + Duration::from_secs(20);
    let mut startup_window = true;
    let mut recent: Vec<String> = Vec::with_capacity(32);

    for line in reader.lines().map_while(Result::ok) {
        log::info!("backend[stderr]: {line}");

        if startup_window {
            recent.push(line.clone());
            if recent.len() > 32 {
                recent.remove(0);
            }
            if Instant::now() >= deadline {
                startup_window = false;
                continue;
            }
            if is_fatal_import_line(&line) {
                let hint = match mode {
                    LaunchMode::Bundled => {
                        "The ALOS runtime bundle appears to be damaged. Try reinstalling the app."
                    }
                    LaunchMode::Python => {
                        "A Python dependency is missing or broken. Re-run the dependency install from the welcome screen."
                    }
                };
                let message = format!("{hint}\n\nDetails: {}", line.trim());
                log::error!("backend: fatal import failure detected: {line}");
                if let Ok(mut guard) = LAST_SPAWN_ERROR.lock() {
                    *guard = Some(message);
                }
                startup_window = false;
            }
        }
    }
}

/// Heuristic: does this stderr line look like a hard Python import failure
/// that will prevent the backend from ever coming up?
fn is_fatal_import_line(line: &str) -> bool {
    const PATTERNS: &[&str] = &[
        "ModuleNotFoundError:",
        "ImportError:",
        "OSError: dlopen",
        "ImportError: DLL load failed",
        "cannot import name",
        "No module named",
    ];
    PATTERNS.iter().any(|p| line.contains(p))
}

/// Gracefully shut the backend down. Sends SIGTERM on Unix so uvicorn can
/// run its shutdown handlers; waits up to `grace` for the process to exit
/// before falling back to a SIGKILL-equivalent `Child::kill()`.
pub fn shutdown(grace: Duration) {
    let mut guard = match BACKEND_CHILD.lock() {
        Ok(g) => g,
        Err(poisoned) => poisoned.into_inner(),
    };
    let Some(mut child) = guard.take() else {
        return;
    };

    let pid = child.id();
    log::info!("backend: shutdown requested (pid={})", pid);

    #[cfg(unix)]
    unsafe {
        // Request a graceful exit first.
        libc::kill(pid as libc::pid_t, libc::SIGTERM);
    }

    let deadline = Instant::now() + grace;
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                log::info!("backend: exited cleanly (status={:?})", status);
                return;
            }
            Ok(None) if Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(100));
            }
            Ok(None) => {
                log::warn!("backend: grace period expired, killing");
                break;
            }
            Err(e) => {
                log::warn!("backend: try_wait failed: {e}; killing");
                break;
            }
        }
    }

    if let Err(e) = child.kill() {
        log::warn!("backend: kill failed: {e}");
    }
    let _ = child.wait();
}

// RFC-0005 Decision 5 bridge: if a line starts with "__ALOS_EVENT__",
// we parse the JSON and emit it as a Tauri event named "alos-event".
fn pipe_lines<R: std::io::Read + Send + 'static>(
    tag: &'static str,
    stream: R,
    app_handle: Option<AppHandle>,
) {
    let reader = BufReader::new(stream);
    for line in reader.lines().map_while(Result::ok) {
        if line.starts_with("__ALOS_EVENT__") {
            if let Some(handle) = &app_handle {
                let event_json = &line["__ALOS_EVENT__".len()..];
                if let Err(e) = handle.emit("alos-event", event_json) {
                    log::error!("backend: failed to emit alos-event: {e}");
                }
            }
            continue;
        }
        log::info!("backend[{tag}]: {line}");
    }
}

/// Resolve the backend directory.
///
/// Priority:
///   1. `ALOS_BACKEND_DIR` env var (lets devs point at a custom tree).
///   2. Bundled resources under the app resource dir (`backend/`).
///   3. Project-local dev layout: `{exe_parent}/../backend` and sibling
///      workspace layouts searched upward.
pub fn resolve_backend_dir(app: &AppHandle) -> Result<PathBuf> {
    if let Ok(from_env) = std::env::var("ALOS_BACKEND_DIR") {
        let p = PathBuf::from(from_env);
        if has_backend(&p) {
            return Ok(p);
        }
    }

    // Bundled resources — populated when we add `backend/` to tauri.conf.json
    // `bundle.resources` for production builds. Safe to ignore if missing.
    if let Ok(resource_dir) = app.path().resource_dir() {
        let candidate = resource_dir.join("backend");
        if has_backend(&candidate) {
            return Ok(candidate);
        }
    }

    // Dev layout — walk up from the current exe looking for `backend/src/api/server.py`.
    let exe = std::env::current_exe().context("current_exe failed")?;
    for ancestor in exe.ancestors().take(8) {
        let candidate = ancestor.join("backend");
        if has_backend(&candidate) {
            return Ok(candidate);
        }
    }

    // Final fallback — cwd/../backend (useful when running `cargo tauri dev` from src-tauri).
    if let Ok(cwd) = std::env::current_dir() {
        for ancestor in cwd.ancestors().take(4) {
            let candidate = ancestor.join("backend");
            if has_backend(&candidate) {
                return Ok(candidate);
            }
        }
    }

    Err(anyhow!(
        "could not locate the ALOS backend directory; set ALOS_BACKEND_DIR"
    ))
}

fn has_backend(dir: &Path) -> bool {
    dir.join("src").join("api").join("server.py").is_file()
}

/// Where the Python backend should write per-user state (`.env`, logs,
/// memory, SQLite DB, etc).
///
/// Priority:
///   1. `ALOS_DATA_DIR` env var override (respected unchanged).
///   2. Tauri's `app_data_dir` — e.g. `~/Library/Application Support/com.alos.desktop`.
///
/// Returns `None` when we're running with a dev backend layout and the
/// user hasn't explicitly overridden — in that case we let Python fall
/// back to its own ROOT_DIR-rooted paths (the pre-existing dev behavior).
fn resolve_user_data_dir(app: &AppHandle) -> Option<PathBuf> {
    if let Ok(from_env) = std::env::var("ALOS_DATA_DIR") {
        let trimmed = from_env.trim();
        if !trimmed.is_empty() {
            return Some(PathBuf::from(trimmed));
        }
    }
    app.path().app_data_dir().ok()
}

/// Locate a Python interpreter.
///
/// Order:
///   1. `ALOS_PYTHON` env var — explicit override.
///   2. `{backend}/.venv/bin/python` (or `Scripts/python.exe` on Windows).
///   3. First `python3` / `python` on `PATH`.
fn find_python(backend_dir: &Path) -> Result<PathBuf> {
    if let Ok(from_env) = std::env::var("ALOS_PYTHON") {
        let p = PathBuf::from(from_env);
        if p.is_file() {
            return Ok(p);
        }
    }

    let venv_python = if cfg!(windows) {
        backend_dir.join(".venv").join("Scripts").join("python.exe")
    } else {
        backend_dir.join(".venv").join("bin").join("python")
    };
    if venv_python.is_file() {
        return Ok(venv_python);
    }

    for candidate in ["python3", "python"] {
        if let Some(found) = which(candidate) {
            return Ok(found);
        }
    }

    Err(anyhow!(
        "no Python interpreter found; install Python 3 or set ALOS_PYTHON"
    ))
}

/// Minimal `which` — scans `PATH` for the first executable named `name`.
fn which(name: &str) -> Option<PathBuf> {
    let path = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path) {
        let candidate = if cfg!(windows) {
            dir.join(format!("{name}.exe"))
        } else {
            dir.join(name)
        };
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}
