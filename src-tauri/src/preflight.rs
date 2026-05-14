//! First-launch dependency preflight.
//!
//! Before the Python backend can be spawned, three things must be true:
//!
//!   1. A Python 3.9+ interpreter exists somewhere we can execute.
//!   2. A dedicated ALOS virtualenv exists under the app's data dir
//!      (`~/Library/Application Support/com.alos.desktop/venv` on macOS,
//!      `%APPDATA%/com.alos.desktop/venv` on Windows).
//!   3. Every package in `backend/requirements.txt` is importable from
//!      that venv.
//!
//! The frontend drives the remediation flow:
//!
//!   - `preflight_check()`     returns a report of what's missing.
//!   - `preflight_install()`   creates the venv and pip-installs the
//!                             missing packages, streaming progress via
//!                             the `preflight-progress` event.
//!
//! On success, the venv's Python is used by `backend::spawn` automatically
//! because `find_python` picks up `ALOS_PYTHON` — which we set here once
//! the venv is ready.

use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;

use anyhow::{anyhow, Context, Result};
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

const MIN_PY_MAJOR: u32 = 3;
const MIN_PY_MINOR: u32 = 9;

#[derive(Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub struct PreflightReport {
    pub ok: bool,
    pub python_ok: bool,
    pub python_path: Option<String>,
    pub python_version: Option<String>,
    pub python_error: Option<String>,
    pub venv_path: String,
    pub venv_exists: bool,
    pub missing_packages: Vec<String>,
    pub required_packages: Vec<String>,
    pub minimum_python: String,
    pub backend_dir: String,
}

#[derive(Clone, Serialize)]
struct ProgressEvent {
    phase: &'static str,
    line: String,
}

/// Run a full preflight check. Never returns an error — every failure
/// mode shows up as a field on the report so the UI can react appropriately.
#[tauri::command]
pub fn preflight_check(app: AppHandle) -> PreflightReport {
    // Packaged builds ship a frozen PyInstaller binary; no Python is
    // required on the user's machine. Short-circuit the whole preflight
    // so the UI goes straight to the normal launch flow.
    if crate::backend::bundled_binary_present(&app) {
        return PreflightReport {
            ok: true,
            python_ok: true,
            python_path: None,
            python_version: Some("bundled".into()),
            python_error: None,
            venv_path: String::new(),
            venv_exists: true,
            missing_packages: Vec::new(),
            required_packages: Vec::new(),
            minimum_python: format!("{MIN_PY_MAJOR}.{MIN_PY_MINOR}"),
            backend_dir: String::new(),
        };
    }

    let backend_dir = match crate::backend::resolve_backend_dir(&app) {
        Ok(p) => p,
        Err(e) => {
            return empty_report(app, format!("Could not locate the ALOS backend: {e:#}"));
        }
    };

    let venv_path = venv_dir(&app);
    let venv_python = venv_python_path(&venv_path);
    let venv_exists = venv_python.is_file();

    // Pick the best Python we can find. When the venv exists we use its
    // Python (that's the interpreter ALOS will actually run under); when
    // it doesn't, we fall back to a system interpreter so we can use it
    // to create the venv.
    let (python_path, python_error) = if venv_exists {
        match inspect_python(&venv_python) {
            Ok(_) => (Some(venv_python.clone()), None),
            Err(e) => (Some(venv_python.clone()), Some(format!("{e:#}"))),
        }
    } else {
        match find_system_python() {
            Some(p) => match inspect_python(&p) {
                Ok(_) => (Some(p), None),
                Err(e) => (Some(p), Some(format!("{e:#}"))),
            },
            None => (
                None,
                Some(format!(
                    "Python {}.{}+ was not found on PATH. Install it from python.org or via Homebrew.",
                    MIN_PY_MAJOR, MIN_PY_MINOR
                )),
            ),
        }
    };

    let python_version = python_path
        .as_ref()
        .and_then(|p| inspect_python(p).ok().map(|v| v.version_string));
    let python_ok = python_error.is_none() && python_path.is_some();

    let required = read_requirements(&backend_dir).unwrap_or_default();

    // We can only check which packages are missing once the venv exists
    // (otherwise we're testing the system Python, which is the wrong answer).
    let missing = if venv_exists && python_ok {
        missing_packages(&venv_python, &required).unwrap_or_default()
    } else {
        required.clone()
    };

    let ok = python_ok && venv_exists && missing.is_empty();

    // Once everything's good, point the backend spawn logic at the venv.
    if ok {
        std::env::set_var("ALOS_PYTHON", &venv_python);
    }

    PreflightReport {
        ok,
        python_ok,
        python_path: python_path.map(|p| p.display().to_string()),
        python_version,
        python_error,
        venv_path: venv_path.display().to_string(),
        venv_exists,
        missing_packages: missing,
        required_packages: required,
        minimum_python: format!("{MIN_PY_MAJOR}.{MIN_PY_MINOR}"),
        backend_dir: backend_dir.display().to_string(),
    }
}

/// Create the venv (if missing) and pip-install any missing packages.
/// Progress lines are streamed to the frontend via the `preflight-progress`
/// event. Returns a fresh report on success, or an error string on failure.
#[tauri::command]
pub fn preflight_install(app: AppHandle) -> Result<PreflightReport, String> {
    preflight_install_inner(app.clone()).map_err(|e| format!("{e:#}"))
}

fn preflight_install_inner(app: AppHandle) -> Result<PreflightReport> {
    let backend_dir =
        crate::backend::resolve_backend_dir(&app).context("could not locate backend directory")?;
    let venv_path = venv_dir(&app);
    let venv_python = venv_python_path(&venv_path);

    // Create the venv if it doesn't exist yet.
    if !venv_python.is_file() {
        let sys_python = find_system_python().ok_or_else(|| {
            anyhow!(
                "Python {MIN_PY_MAJOR}.{MIN_PY_MINOR}+ is required but not installed. \
                 Install Python first (python.org or Homebrew), then retry."
            )
        })?;
        emit(
            &app,
            "venv",
            format!("Creating virtualenv at {}…", venv_path.display()),
        );
        fs::create_dir_all(venv_path.parent().unwrap_or(Path::new("."))).ok();
        run_streaming(
            &app,
            "venv",
            Command::new(&sys_python).args([
                "-m",
                "venv",
                venv_path
                    .to_str()
                    .ok_or_else(|| anyhow!("non-utf8 venv path"))?,
            ]),
        )?;
    }

    // Upgrade pip first so modern resolver messages look right in logs.
    emit(&app, "pip", "Upgrading pip…".into());
    run_streaming(
        &app,
        "pip",
        Command::new(&venv_python).args(["-m", "pip", "install", "--upgrade", "pip"]),
    )
    .ok(); // Non-fatal — continue even if this fails.

    // Install requirements.
    let req_path = backend_dir.join("requirements.txt");
    emit(
        &app,
        "pip",
        format!("Installing ALOS dependencies from {}…", req_path.display()),
    );
    run_streaming(
        &app,
        "pip",
        Command::new(&venv_python).args([
            "-m",
            "pip",
            "install",
            "-r",
            req_path
                .to_str()
                .ok_or_else(|| anyhow!("non-utf8 requirements path"))?,
        ]),
    )?;

    emit(&app, "done", "Dependencies installed.".into());

    // Re-check and return the fresh report.
    Ok(preflight_check(app))
}

// ─── helpers ───────────────────────────────────────────────────────────

struct PythonInfo {
    version_string: String,
}

/// Run `python --version` and validate the result against our floor.
fn inspect_python(python: &Path) -> Result<PythonInfo> {
    let out = Command::new(python)
        .arg("--version")
        .output()
        .with_context(|| format!("failed to run {}", python.display()))?;
    let combined = String::from_utf8_lossy(if out.stdout.is_empty() {
        &out.stderr
    } else {
        &out.stdout
    })
    .trim()
    .to_string();
    // Expected form: "Python 3.11.5"
    let version = combined
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| anyhow!("unexpected `python --version` output: {combined:?}"))?;
    let mut parts = version.split('.');
    let major: u32 = parts
        .next()
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| anyhow!("could not parse major version in {version:?}"))?;
    let minor: u32 = parts
        .next()
        .and_then(|s| s.parse().ok())
        .ok_or_else(|| anyhow!("could not parse minor version in {version:?}"))?;

    if (major, minor) < (MIN_PY_MAJOR, MIN_PY_MINOR) {
        return Err(anyhow!(
            "Python {MIN_PY_MAJOR}.{MIN_PY_MINOR}+ is required; found Python {major}.{minor} at {}",
            python.display()
        ));
    }

    Ok(PythonInfo {
        version_string: combined,
    })
}

/// Scan PATH for the newest suitable Python. Tries `python3.13` down to
/// `python3.9`, then generic `python3`, then `python`.
fn find_system_python() -> Option<PathBuf> {
    let specific = (MIN_PY_MINOR..=13)
        .rev()
        .map(|m| format!("python3.{m}"))
        .collect::<Vec<_>>();
    let mut candidates: Vec<&str> = specific.iter().map(String::as_str).collect();
    candidates.push("python3");
    candidates.push("python");

    for name in candidates {
        if let Some(path) = which(name) {
            if inspect_python(&path).is_ok() {
                return Some(path);
            }
        }
    }
    None
}

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

fn venv_dir(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("venv")
}

fn venv_python_path(venv: &Path) -> PathBuf {
    if cfg!(windows) {
        venv.join("Scripts").join("python.exe")
    } else {
        venv.join("bin").join("python")
    }
}

/// Read requirement names from `requirements.txt`, stripping version
/// specifiers and comments. Conservative parser — good enough for our
/// hand-curated file.
fn read_requirements(backend_dir: &Path) -> Result<Vec<String>> {
    let text = fs::read_to_string(backend_dir.join("requirements.txt"))
        .context("could not read requirements.txt")?;
    let mut out = Vec::new();
    for line in text.lines() {
        let line = line.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }
        // Drop any extras, version specifiers, or environment markers.
        let name_end = line
            .find(|c: char| matches!(c, '<' | '>' | '=' | '!' | '~' | ';' | '[' | ' '))
            .unwrap_or(line.len());
        let name = line[..name_end].trim().to_string();
        if !name.is_empty() {
            out.push(name);
        }
    }
    Ok(out)
}

/// Ask the given Python which of these packages are missing.
fn missing_packages(python: &Path, required: &[String]) -> Result<Vec<String>> {
    if required.is_empty() {
        return Ok(Vec::new());
    }
    let script = r#"
import importlib.metadata as m, sys
missing = []
for name in sys.stdin.read().splitlines():
    name = name.strip()
    if not name:
        continue
    try:
        m.distribution(name)
    except Exception:
        missing.append(name)
print("\n".join(missing))
"#;
    let mut child = Command::new(python)
        .args(["-c", script])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("failed to invoke Python to check packages")?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(required.join("\n").as_bytes()).ok();
    }

    let out = child.wait_with_output()?;
    if !out.status.success() {
        return Err(anyhow!(
            "package probe exited with status {}: {}",
            out.status,
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect())
}

/// Spawn a command and stream its stdout+stderr into the progress event.
fn run_streaming(app: &AppHandle, phase: &'static str, cmd: &mut Command) -> Result<()> {
    let mut child = cmd
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("failed to spawn preflight command")?;

    let app_out = app.clone();
    let app_err = app.clone();
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let t_out = stdout.map(|s| {
        thread::spawn(move || {
            for line in BufReader::new(s).lines().map_while(Result::ok) {
                emit(&app_out, phase, line);
            }
        })
    });
    let t_err = stderr.map(|s| {
        thread::spawn(move || {
            for line in BufReader::new(s).lines().map_while(Result::ok) {
                emit(&app_err, phase, line);
            }
        })
    });

    let status = child.wait()?;
    if let Some(h) = t_out {
        let _ = h.join();
    }
    if let Some(h) = t_err {
        let _ = h.join();
    }
    if !status.success() {
        return Err(anyhow!(
            "preflight step '{phase}' failed with status {status}"
        ));
    }
    Ok(())
}

fn emit(app: &AppHandle, phase: &'static str, line: String) {
    log::info!("preflight[{phase}]: {line}");
    let _ = app.emit("preflight-progress", ProgressEvent { phase, line });
}

fn empty_report(app: AppHandle, python_error: String) -> PreflightReport {
    let venv_path = venv_dir(&app);
    PreflightReport {
        ok: false,
        python_ok: false,
        python_path: None,
        python_version: None,
        python_error: Some(python_error),
        venv_path: venv_path.display().to_string(),
        venv_exists: false,
        missing_packages: Vec::new(),
        required_packages: Vec::new(),
        minimum_python: format!("{MIN_PY_MAJOR}.{MIN_PY_MINOR}"),
        backend_dir: String::new(),
    }
}
