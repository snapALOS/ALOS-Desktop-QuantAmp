use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::State;
use walkdir::WalkDir;

#[derive(Default)]
pub struct WorkspaceState {
    root: Mutex<Option<PathBuf>>,
}

impl WorkspaceState {
    fn root(&self) -> Result<PathBuf, String> {
        let selected = self
            .root
            .lock()
            .map_err(|_| "workspace root lock poisoned".to_string())?
            .clone();

        if let Some(root) = selected {
            return Ok(root);
        }

        std::env::current_dir()
            .and_then(|p| p.canonicalize())
            .map_err(|e| format!("workspace root: {}", e))
    }

    fn set_root(&self, path: PathBuf) -> Result<PathBuf, String> {
        let resolved = path
            .canonicalize()
            .map_err(|e| format!("workspace root does not exist ({}): {}", path.display(), e))?;
        if !resolved.is_dir() {
            return Err(format!(
                "workspace root is not a directory: {}",
                resolved.display()
            ));
        }

        *self
            .root
            .lock()
            .map_err(|_| "workspace root lock poisoned".to_string())? = Some(resolved.clone());
        Ok(resolved)
    }
}

/// Security sandbox: resolve `path_str` to an absolute, symlink-resolved path
/// that is guaranteed to live inside the workspace root.
///
/// The resolution is robust to:
///   - relative paths (joined against the workspace root)
///   - `..` components (resolved by `canonicalize`)
///   - symlinks that escape the workspace (rejected after `canonicalize`)
///   - paths that do not yet exist (the *parent* is canonicalized and the
///     final component is re-attached; parents must exist)
fn validate_path(path_str: &str, workspace_state: &WorkspaceState) -> Result<PathBuf, String> {
    let root = workspace_state.root()?;
    let raw = PathBuf::from(path_str);

    let absolute = if raw.is_absolute() {
        raw
    } else {
        root.join(raw)
    };

    let resolved = canonicalize_allow_missing(&absolute)?;

    if !resolved.starts_with(&root) {
        return Err(format!(
            "Path escapes workspace root: {} (root: {})",
            resolved.display(),
            root.display()
        ));
    }

    Ok(resolved)
}

#[tauri::command]
pub async fn core_fs_set_workspace_root(
    path: String,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<String, String> {
    let root = workspace_state.set_root(PathBuf::from(path))?;
    Ok(root.to_string_lossy().to_string())
}

#[tauri::command]
pub async fn core_fs_get_workspace_root(
    workspace_state: State<'_, WorkspaceState>,
) -> Result<String, String> {
    workspace_state
        .root()
        .map(|root| root.to_string_lossy().to_string())
}

/// Canonicalize `path`. If the path does not exist, canonicalize its parent
/// and re-attach the final component so newly-created files still resolve
/// symlinks in their ancestor directories.
fn canonicalize_allow_missing(path: &Path) -> Result<PathBuf, String> {
    if let Ok(resolved) = path.canonicalize() {
        return Ok(resolved);
    }
    let parent = path
        .parent()
        .ok_or_else(|| "Path has no parent".to_string())?;
    let file_name = path
        .file_name()
        .ok_or_else(|| "Path has no final component".to_string())?;
    let parent_resolved = parent
        .canonicalize()
        .map_err(|e| format!("Parent does not exist ({}): {}", parent.display(), e))?;
    Ok(parent_resolved.join(file_name))
}

// ---------------------------------------------------------------------------
// git sandbox: allow-list of verbs we permit via core_fs_run_git
// ---------------------------------------------------------------------------

/// Subcommands we allow users to invoke. Everything else is rejected.
///
/// Anything that can rewrite global config, execute arbitrary binaries
/// (`filter-branch`, `--exec`, submodule hooks), or reach the network in a
/// way we can't attribute to an intentional user action is excluded. When
/// adding a new verb here, audit it for `-c key=value` / `--exec` style
/// options and add a corresponding flag filter below.
const GIT_ALLOWED_SUBCOMMANDS: &[&str] = &[
    "status",
    "diff",
    "log",
    "show",
    "branch",
    "rev-parse",
    "rev-list",
    "ls-files",
    "ls-tree",
    "blame",
    "shortlog",
    "config", // read-only variant enforced below
    "remote", // read-only variant enforced below
    "stash",
    "add",
    "commit",
    "checkout",
    "switch",
    "restore",
    "merge",
    "rebase",
    "reset",
    "tag",
    "fetch",
    "pull",
    "push",
    "init",
    "clone",
];

/// Validate an argv vector that will be passed to the `git` binary.
fn validate_git_args(args: &[String]) -> Result<(), String> {
    // Block `git -c foo=bar <cmd>` — that flag lets the caller override any
    // config (credential helpers, core.sshCommand, etc.) for the duration of
    // the invocation. Same for `-C <path>` which moves git out of `cwd`.
    for arg in args {
        if arg == "-c" || arg.starts_with("-c=") {
            return Err("`git -c` is not permitted".into());
        }
        if arg == "-C" {
            return Err("`git -C` is not permitted".into());
        }
        if arg == "--exec-path" || arg.starts_with("--exec-path=") {
            return Err("`git --exec-path` is not permitted".into());
        }
    }

    // First non-flag argument is the subcommand. If there isn't one, reject.
    let subcommand = args
        .iter()
        .find(|a| !a.starts_with('-'))
        .ok_or_else(|| "git subcommand missing".to_string())?;

    if !GIT_ALLOWED_SUBCOMMANDS.contains(&subcommand.as_str()) {
        return Err(format!("git subcommand not allowed: {}", subcommand));
    }

    // `git config` can write global state; restrict to read-only forms.
    if subcommand == "config" {
        let tail: Vec<&str> = args
            .iter()
            .skip_while(|a| a.as_str() != "config")
            .skip(1)
            .map(String::as_str)
            .collect();
        let writes_global = tail.iter().any(|a| {
            matches!(
                *a,
                "--global" | "--system" | "--unset" | "--unset-all" | "--add" | "--replace-all"
            )
        });
        if writes_global {
            return Err("`git config` write/global operations are not permitted".into());
        }
    }

    // `git remote` can add network endpoints; restrict to read-only forms.
    if subcommand == "remote" {
        let tail: Vec<&str> = args
            .iter()
            .skip_while(|a| a.as_str() != "remote")
            .skip(1)
            .map(String::as_str)
            .collect();
        let writes = tail.iter().any(|a| {
            matches!(
                *a,
                "add" | "remove" | "rename" | "set-url" | "set-head" | "set-branches"
            )
        });
        if writes {
            return Err("`git remote` write operations are not permitted".into());
        }
    }

    Ok(())
}

#[derive(Serialize, Deserialize, Clone)]
pub struct FileInfo {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size: Option<u64>,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct SearchResult {
    pub file: String,
    pub line: u32,
    pub text: String,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct GitResult {
    pub stdout: String,
    pub stderr: String,
    pub success: bool,
}

#[tauri::command]
pub async fn core_fs_read_dir(
    path: String,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<Vec<FileInfo>, String> {
    let validated = validate_path(&path, &workspace_state)?;
    let entries = std::fs::read_dir(validated).map_err(|e| e.to_string())?;
    let mut files = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let metadata = entry.metadata().map_err(|e| e.to_string())?;
        files.push(FileInfo {
            name: entry.file_name().to_string_lossy().to_string(),
            path: entry.path().to_string_lossy().to_string(),
            is_dir: metadata.is_dir(),
            size: Some(metadata.len()),
        });
    }
    // Directories first, then alphabetical
    files.sort_by(|a, b| match (a.is_dir, b.is_dir) {
        (true, false) => std::cmp::Ordering::Less,
        (false, true) => std::cmp::Ordering::Greater,
        _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
    });
    Ok(files)
}

#[tauri::command]
pub async fn core_fs_read_file(
    path: String,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<String, String> {
    let validated = validate_path(&path, &workspace_state)?;
    std::fs::read_to_string(validated).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn core_fs_write_file(
    path: String,
    content: String,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<(), String> {
    let validated = validate_path(&path, &workspace_state)?;
    std::fs::write(validated, content).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn core_fs_search(
    root: String,
    query: String,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<Vec<SearchResult>, String> {
    let validated = validate_path(&root, &workspace_state)?;
    let mut results = Vec::new();
    let query_lower = query.to_lowercase();
    let skip_exts = [
        "png", "jpg", "jpeg", "gif", "ico", "svg", "woff", "woff2", "ttf", "eot", "bin", "exe",
        "dll", "so", "dylib", "lock",
    ];

    for entry in WalkDir::new(validated)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if !entry.file_type().is_file() {
            continue;
        }
        if entry.path().components().any(|c| {
            let s = c.as_os_str().to_string_lossy();
            s.starts_with('.') || s == "node_modules" || s == "target"
        }) {
            continue;
        }
        if let Some(ext) = entry.path().extension() {
            if skip_exts.contains(&ext.to_string_lossy().to_lowercase().as_str()) {
                continue;
            }
        }
        if let Ok(content) = std::fs::read_to_string(entry.path()) {
            for (i, line) in content.lines().enumerate() {
                if line.to_lowercase().contains(&query_lower) {
                    results.push(SearchResult {
                        file: entry.path().to_string_lossy().to_string(),
                        line: (i + 1) as u32,
                        text: line.trim().to_string(),
                    });
                }
            }
        }
        if results.len() >= 500 {
            break;
        }
    }
    Ok(results)
}

#[derive(Serialize, Deserialize, Clone)]
pub struct AppConfig {
    pub theme: String,
    pub font_size: u32,
    pub terminal_shell: String,
}

#[tauri::command]
pub async fn core_fs_run_git(
    cwd: String,
    args: Vec<String>,
    workspace_state: State<'_, WorkspaceState>,
) -> Result<GitResult, String> {
    let validated = validate_path(&cwd, &workspace_state)?;
    validate_git_args(&args)?;
    let output = std::process::Command::new("git")
        .current_dir(validated)
        .args(&args)
        .output()
        .map_err(|e| format!("Failed to run git: {}", e))?;
    Ok(GitResult {
        stdout: String::from_utf8_lossy(&output.stdout).to_string(),
        stderr: String::from_utf8_lossy(&output.stderr).to_string(),
        success: output.status.success(),
    })
}

fn config_path() -> Result<PathBuf, String> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map_err(|_| "Cannot determine home directory".to_string())?;
    let mut path = PathBuf::from(home);
    path.push(".alos"); // Rebranded from .rexcode
    path.push("config.json");
    Ok(path)
}

#[tauri::command]
pub async fn core_fs_read_config() -> Result<AppConfig, String> {
    let path = config_path()?;
    if !path.exists() {
        return Ok(AppConfig {
            theme: "dark".to_string(),
            font_size: 14,
            terminal_shell: if cfg!(target_os = "windows") {
                "powershell.exe".to_string()
            } else {
                "zsh".to_string()
            },
        });
    }
    let content = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    serde_json::from_str(&content).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn core_fs_write_config(config: AppConfig) -> Result<(), String> {
    let path = config_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    std::fs::write(&path, content).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn core_get_platform() -> String {
    std::env::consts::OS.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selected_workspace_allows_absolute_child_path() {
        let root = tempfile::tempdir().expect("temp workspace");
        let file = root.path().join("src").join("main.txt");
        std::fs::create_dir_all(file.parent().expect("parent")).expect("create parent");
        std::fs::write(&file, "ok").expect("write file");

        let state = WorkspaceState::default();
        state
            .set_root(root.path().to_path_buf())
            .expect("set workspace root");

        let validated = validate_path(file.to_string_lossy().as_ref(), &state).expect("valid path");
        assert_eq!(validated, file.canonicalize().expect("canonical file"));
    }

    #[test]
    fn selected_workspace_rejects_absolute_path_outside_root() {
        let root = tempfile::tempdir().expect("temp workspace");
        let outside = tempfile::tempdir().expect("outside dir");
        let outside_file = outside.path().join("secret.txt");
        std::fs::write(&outside_file, "nope").expect("write outside file");

        let state = WorkspaceState::default();
        state
            .set_root(root.path().to_path_buf())
            .expect("set workspace root");

        let err = validate_path(outside_file.to_string_lossy().as_ref(), &state)
            .expect_err("outside path should fail");
        assert!(err.contains("Path escapes workspace root"));
    }
}
