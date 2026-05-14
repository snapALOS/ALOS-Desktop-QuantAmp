use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use std::path::Path;
use std::{
    collections::HashMap,
    io::{Read, Write},
    sync::{Arc, Mutex},
    thread,
};
use tauri::{Emitter, State, Window};

// ---------------------------------------------------------------------------
// Terminal State
// ---------------------------------------------------------------------------

pub struct TerminalSession {
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    #[allow(dead_code)]
    master: Arc<Mutex<Box<dyn MasterPty + Send>>>,
}

#[derive(Default)]
pub struct TerminalState {
    pub sessions: Arc<Mutex<HashMap<String, TerminalSession>>>,
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

/// Create a new PTY terminal session.
///
/// Emits `terminal-data-<id>` events with raw output for the UI.
#[tauri::command]
pub fn core_terminal_create(
    id: String,
    window: Window,
    state: State<'_, TerminalState>,
) -> Result<(), String> {
    let pty_system = native_pty_system();

    // Default size for xterm.js
    let pair = pty_system
        .openpty(PtySize {
            rows: 24,
            cols: 80,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;

    // Determine shell based on OS logic.
    // TODO: prioritize $SHELL env var on Unix.
    let shell = if cfg!(target_os = "windows") {
        "powershell.exe"
    } else {
        "/bin/zsh" // Prefer zsh on modern macOS/Linux if available, or just "/bin/sh"
    };

    // Check if zsh exists, else fallback to bash
    let shell = if !cfg!(target_os = "windows") && !Path::new(shell).exists() {
        "/bin/bash"
    } else {
        shell
    };

    let cmd = CommandBuilder::new(shell);
    let mut child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;

    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;

    let master = Arc::new(Mutex::new(pair.master));
    let writer_shared = Arc::new(Mutex::new(writer));

    let sessions_arc = state.sessions.clone();
    {
        let mut sessions = sessions_arc.lock().unwrap();
        sessions.insert(
            id.clone(),
            TerminalSession {
                writer: writer_shared,
                master,
            },
        );
    }

    // Reader thread: stream PTY output to frontend.
    //
    // Emit failures are logged but never panic — the frontend may have
    // unmounted the terminal view (window closed, route changed) before the
    // child exits, and emitting into a dead channel is expected, not fatal.
    let window_clone = window.clone();
    let id_clone = id.clone();
    let sessions_for_cleanup = sessions_arc.clone();
    thread::spawn(move || {
        let mut reader = reader;
        let mut buffer = [0u8; 4096];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => break,
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buffer[..n]).to_string();
                    if let Err(err) =
                        window_clone.emit(&format!("terminal-data-{}", id_clone), data)
                    {
                        eprintln!("[terminal] emit terminal-data-{} failed: {}", id_clone, err);
                    }
                }
                Err(_) => break,
            }
        }
        // Notify frontend that the session has ended.
        if let Err(err) = window_clone.emit(&format!("terminal-exit-{}", id_clone), true) {
            eprintln!("[terminal] emit terminal-exit-{} failed: {}", id_clone, err);
        }
        // Drop the session from state so writer/master handles are released
        // and the id can be reused. This runs exactly once per PTY.
        if let Ok(mut sessions) = sessions_for_cleanup.lock() {
            sessions.remove(&id_clone);
        }
    });

    // Wait for child process to exit in background (detached).
    thread::spawn(move || {
        child.wait().ok();
    });

    Ok(())
}

/// Write data (keystrokes) to a PTY session.
#[tauri::command]
pub fn core_terminal_write(
    id: String,
    data: String,
    state: State<'_, TerminalState>,
) -> Result<(), String> {
    let sessions = state.sessions.lock().unwrap();
    if let Some(session) = sessions.get(&id) {
        let mut writer = session.writer.lock().unwrap();
        writer
            .write_all(data.as_bytes())
            .map_err(|e| e.to_string())?;
        writer.flush().map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err(format!("Terminal session '{}' not found", id))
    }
}

/// Resize a PTY session.
#[tauri::command]
pub fn core_terminal_resize(
    id: String,
    cols: u16,
    rows: u16,
    state: State<'_, TerminalState>,
) -> Result<(), String> {
    let sessions = state.sessions.lock().unwrap();
    if let Some(session) = sessions.get(&id) {
        let master = session.master.lock().unwrap();
        master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err(format!("Terminal session '{}' not found", id))
    }
}
