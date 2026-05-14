mod backend;
pub mod fs_ops;
pub mod lsp;
pub mod modules;
pub mod modules_ipc;
mod preflight;
pub mod terminal;
mod tray;

use std::path::PathBuf;
use std::time::Duration;

use lsp::{LspRegistry, LspSupervisor};
use tauri::{Emitter, Manager, RunEvent, State, WindowEvent};

/// Forward a Python-originated event to all frontend listeners via Tauri's
/// event system. The frontend event-bus bridge listens on "alos-event".
#[tauri::command]
fn emit_event(event_json: String, app: tauri::AppHandle) -> Result<(), String> {
    app.emit("alos-event", &event_json)
        .map_err(|e| e.to_string())
}

/// Stub for v0.2 — when the Python bridge is wired, this forwards frontend
/// events to the Python backend event bus.
#[tauri::command]
fn forward_event_to_backend(event_json: String) -> Result<(), String> {
    log::debug!(
        "forward_event_to_backend: {}",
        &event_json[..event_json.len().min(200)]
    );
    Ok(())
}

#[tauri::command]
async fn lsp_request_server(
    language: String,
    app: tauri::AppHandle,
    supervisor: State<'_, LspSupervisor>,
) -> Result<String, String> {
    let config = supervisor
        .registry
        .find_for_language(&language)
        .ok_or_else(|| format!("No LSP server registered for language: {}", language))?;

    supervisor
        .spawn_server(&config.id, app)
        .map_err(|e| e.to_string())?;

    Ok(config.id.clone())
}

#[tauri::command]
async fn lsp_send_message(
    server_id: String,
    message: String,
    supervisor: State<'_, LspSupervisor>,
) -> Result<(), String> {
    supervisor
        .send_message(&server_id, &message)
        .map_err(|e| e.to_string())
}

#[tauri::command]
async fn lsp_restart_server(
    server_id: String,
    app: tauri::AppHandle,
    supervisor: State<'_, LspSupervisor>,
) -> Result<(), String> {
    supervisor
        .stop_server(&server_id)
        .map_err(|e| e.to_string())?;
    supervisor
        .spawn_server(&server_id, app)
        .map_err(|e| e.to_string())?;
    Ok(())
}

// `#[rustfmt::skip]` is applied to the whole function so the
// `generate_handler!` list below retains its subsystem grouping and
// section-header comments. Attribute-on-expression is unstable, so applying it
// at the item level is the only portable form. Keep the groups here in sync
// with src/contracts/tauri-commands.ts.
#[rustfmt::skip]
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            // Core
            backend::backend_status,
            backend::launch_backend,
            modules::list_modules,
            modules::refresh_modules,
            emit_event,
            forward_event_to_backend,

            // Preflight
            preflight::preflight_check,
            preflight::preflight_install,

            // LSP
            lsp_request_server,
            lsp_send_message,
            lsp_restart_server,

            // Forge
            // (reserved for task 0018)

            // Current
            // (reserved for task 0034)

            // Atlas
            // (reserved for task 0053)

            // Terminal
            terminal::core_terminal_create,
            terminal::core_terminal_write,
            terminal::core_terminal_resize,

            // Filesystem
            fs_ops::core_fs_set_workspace_root,
            fs_ops::core_fs_get_workspace_root,
            fs_ops::core_fs_read_dir,
            fs_ops::core_fs_read_file,
            fs_ops::core_fs_write_file,
            fs_ops::core_fs_search,
            fs_ops::core_fs_run_git,
            fs_ops::core_fs_read_config,
            fs_ops::core_fs_write_config,
            fs_ops::core_get_platform,
        ])
        .manage(terminal::TerminalState::default())
        .manage(fs_ops::WorkspaceState::default())
        .plugin(
            tauri_plugin_log::Builder::default()
                // Keep `Info` in release too. Every backend spawn / preflight
                // line uses `log::info!`; filtering to `warn` in release left
                // us with a 0-byte log when diagnosing 0145. Promote noise vs.
                // flying blind: noise wins until we ship.
                .level(log::LevelFilter::Info)
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .on_window_event(|window, event| {
            // Intercept window close: hide instead of quit. The tray's "Quit"
            // menu item is the canonical way to exit so users can reopen ALOS
            // without a full cold start + backend respawn.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .setup(|app| {
            if let Err(e) = tray::install(app.handle()) {
                log::error!("tray: failed to install: {e:#}");
            }

            // Resolve base directories
            let resource_dir = app.path().resource_dir().unwrap_or_else(|_| PathBuf::from("."));
            
            // Initialise the module registry. 
            let mut modules_dir = resource_dir.join("modules");
            if !modules_dir.is_dir() {
                // Fallback for dev: workspace_root/modules
                modules_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .parent()
                    .map(|p| p.join("modules"))
                    .unwrap_or_else(|| PathBuf::from("modules"));
            }
            modules::init_registry(&modules_dir);

            // Initialise LSP Supervisor
            let lsp_registry_path = LspRegistry::ensure_config(&resource_dir).unwrap_or_else(|e| {
                log::error!("lsp: failed to ensure config: {e}");
                PathBuf::from("lsp.toml") // fallback
            });
            let lsp_registry = LspRegistry::load_from_file(&lsp_registry_path).unwrap_or_else(|e| {
                log::error!("lsp: failed to load registry: {e}");
                LspRegistry { config: Default::default() }
            });
            let lsp_supervisor = LspSupervisor::new(lsp_registry, resource_dir);
            app.manage(lsp_supervisor);

            // Run preflight synchronously.
            let handle = app.handle().clone();
            let report = preflight::preflight_check(handle.clone());
            if report.ok {
                if let Err(e) = backend::spawn(&handle) {
                    log::error!("backend: failed to spawn: {e:#}");
                }
            } else {
                log::info!(
                    "preflight: deferring backend spawn (python_ok={}, venv_exists={}, missing={})",
                    report.python_ok,
                    report.venv_exists,
                    report.missing_packages.len()
                );
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        if let RunEvent::Exit = event {
            backend::shutdown(Duration::from_secs(5));
        }
    });
}
