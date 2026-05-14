use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/// A single sidebar entry exposed to the frontend via the `list_modules` command.
#[derive(Debug, Serialize, Clone)]
pub struct ModuleEntry {
    pub id: String,
    pub display_name: String,
    pub version: String,
    pub order: u16,
    pub icon: String,
    pub route: String,
    pub available: bool,
    pub error_message: Option<String>,
    pub hidden: bool,
    pub kind: String, // "module" or "builtin"
}

// ---------------------------------------------------------------------------
// TOML deserialization types (private)
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
struct ModuleToml {
    module: Option<ModuleSection>,
    nav: Option<NavSection>,
    // Other sections (capabilities, contracts, standalone) are not needed for
    // the registry — we only care about identity + navigation.
}

#[derive(Debug, Deserialize)]
struct ModuleSection {
    name: Option<String>,
    display_name: Option<String>,
    version: Option<String>,
    #[allow(dead_code)]
    description: Option<String>,
}

#[derive(Debug, Deserialize)]
struct NavSection {
    order: Option<u16>,
    icon: Option<String>,
    route: Option<String>,
}

// ---------------------------------------------------------------------------
// Built-in entries
// ---------------------------------------------------------------------------

/// Returns the hard-coded built-in sidebar entries that are not backed by a
/// MODULE.toml on disk.
pub fn builtin_entries() -> Vec<ModuleEntry> {
    let version = env!("CARGO_PKG_VERSION").to_string();
    vec![
        ModuleEntry {
            id: "chat".into(),
            display_name: "Chat".into(),
            version: version.clone(),
            order: 90,
            icon: "message-square".into(),
            route: "/chat".into(),
            available: true,
            error_message: None,
            hidden: false,
            kind: "builtin".into(),
        },
        ModuleEntry {
            id: "extensions".into(),
            display_name: "Extensions".into(),
            version: version.clone(),
            order: 95,
            icon: "puzzle".into(),
            route: "/extensions".into(),
            available: true,
            error_message: None,
            hidden: false,
            kind: "builtin".into(),
        },
        ModuleEntry {
            id: "scout".into(),
            display_name: "Scout".into(),
            version: version.clone(),
            order: 97,
            icon: "activity".into(),
            route: "/scout".into(),
            available: true,
            error_message: None,
            hidden: false,
            kind: "builtin".into(),
        },
        ModuleEntry {
            id: "settings".into(),
            display_name: "Settings".into(),
            version,
            order: 99,
            icon: "settings".into(),
            route: "/settings".into(),
            available: true,
            error_message: None,
            hidden: false,
            kind: "builtin".into(),
        },
    ]
}

// ---------------------------------------------------------------------------
// Single-file loader
// ---------------------------------------------------------------------------

/// Parse a single `MODULE.toml` file and return a `ModuleEntry`.
///
/// Returns `Err` with an actionable message when the file cannot be read, the
/// TOML is invalid, or required fields (`module.name`, `nav.order`,
/// `nav.icon`, `nav.route`) are missing.
pub fn load_module_manifest(path: &Path) -> Result<ModuleEntry, String> {
    let content = std::fs::read_to_string(path)
        .map_err(|e| format!("cannot read {}: {e}", path.display()))?;

    let parsed: ModuleToml =
        toml::from_str(&content).map_err(|e| format!("invalid TOML in {}: {e}", path.display()))?;

    let module = parsed
        .module
        .ok_or_else(|| format!("{}: missing [module] section", path.display()))?;

    let name = module
        .name
        .ok_or_else(|| format!("{}: missing required field module.name", path.display()))?;

    let display_name = module.display_name.unwrap_or_else(|| name.clone());
    let version = module.version.unwrap_or_else(|| "0.0.0".into());

    let nav = parsed
        .nav
        .ok_or_else(|| format!("{}: missing [nav] section", path.display()))?;

    let order = nav
        .order
        .ok_or_else(|| format!("{}: missing required field nav.order", path.display()))?;
    let icon = nav
        .icon
        .ok_or_else(|| format!("{}: missing required field nav.icon", path.display()))?;
    let route = nav
        .route
        .ok_or_else(|| format!("{}: missing required field nav.route", path.display()))?;

    Ok(ModuleEntry {
        id: name,
        display_name,
        version,
        order,
        icon,
        route,
        available: true,
        error_message: None,
        hidden: false,
        kind: "module".into(),
    })
}

// ---------------------------------------------------------------------------
// Directory scanner
// ---------------------------------------------------------------------------

/// Scan `modules_dir` for subdirectories containing `MODULE.toml`.
///
/// Directories whose name starts with `_` are silently skipped.
/// Invalid manifests produce a WARN log and are included in the result with
/// `available: false` so the frontend can surface the issue.
pub fn load_all_modules(modules_dir: &Path) -> Vec<ModuleEntry> {
    let mut entries = Vec::new();

    let read_dir = match std::fs::read_dir(modules_dir) {
        Ok(rd) => rd,
        Err(e) => {
            log::warn!("modules: cannot read {}: {e}", modules_dir.display());
            return entries;
        }
    };

    for dir_entry in read_dir.flatten() {
        let path = dir_entry.path();
        if !path.is_dir() {
            continue;
        }

        // Skip directories starting with `_` (e.g. `_fixtures/`).
        let dir_name = match path.file_name().and_then(|n| n.to_str()) {
            Some(n) => n.to_string(),
            None => continue,
        };
        if dir_name.starts_with('_') {
            continue;
        }

        let manifest = path.join("MODULE.toml");
        if !manifest.exists() {
            continue;
        }

        match load_module_manifest(&manifest) {
            Ok(entry) => entries.push(entry),
            Err(msg) => {
                log::warn!("modules: {msg}");
                entries.push(ModuleEntry {
                    id: dir_name.clone(),
                    display_name: dir_name,
                    version: "0.0.0".into(),
                    order: u16::MAX,
                    icon: "alert-triangle".into(),
                    route: String::new(),
                    available: false,
                    error_message: Some(msg),
                    hidden: false,
                    kind: "module".into(),
                });
            }
        }
    }

    entries
}

// ---------------------------------------------------------------------------
// Registry (cached at startup, reloadable)
// ---------------------------------------------------------------------------

static MODULE_REGISTRY: Mutex<Option<Vec<ModuleEntry>>> = Mutex::new(None);
static MODULES_ROOT: OnceLock<PathBuf> = OnceLock::new();

/// Initialise the global module registry. Should be called exactly once during
/// Tauri `.setup()`. Subsequent calls are no-ops.
pub fn init_registry(modules_dir: &Path) {
    MODULES_ROOT.get_or_init(|| modules_dir.to_path_buf());
    refresh_modules();
}

/// Re-scans the modules directory and refreshes the global cache.
/// Can be invoked at runtime via Tauri command.
#[tauri::command]
pub fn refresh_modules() {
    let modules_dir = MODULES_ROOT.get().expect("init_registry not called");
    let mut entries = load_all_modules(modules_dir);
    entries.extend(builtin_entries());
    entries.sort_by(|a, b| a.order.cmp(&b.order).then_with(|| a.id.cmp(&b.id)));

    // Log collisions (same `order` value).
    for window in entries.windows(2) {
        if window[0].order == window[1].order {
            log::warn!(
                "module order collision: '{}' and '{}' both have order {}",
                window[0].id,
                window[1].id,
                window[0].order
            );
        }
    }

    if let Ok(mut guard) = MODULE_REGISTRY.lock() {
        *guard = Some(entries);
    }
}

/// Tauri command — returns the cached module list.
#[tauri::command]
pub fn list_modules() -> Vec<ModuleEntry> {
    MODULE_REGISTRY
        .lock()
        .map(|g| g.clone().unwrap_or_default())
        .unwrap_or_default()
}
