use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;

use anyhow::{anyhow, Result};
use tauri::{AppHandle, Emitter};

use super::registry::LspRegistry;

#[derive(serde::Serialize, Clone)]
pub struct LspMessage {
    pub server_id: String,
    pub message: String,
}

#[derive(Default)]
pub struct LspSupervisorState {
    pub active_servers: HashMap<String, Child>,
}

pub struct LspSupervisor {
    pub state: Arc<Mutex<LspSupervisorState>>,
    pub registry: LspRegistry,
    pub resource_dir: PathBuf,
}

impl LspSupervisor {
    pub fn new(registry: LspRegistry, resource_dir: PathBuf) -> Self {
        Self {
            state: Arc::new(Mutex::new(LspSupervisorState::default())),
            registry,
            resource_dir,
        }
    }

    /// Spawn a language server by ID.
    pub fn spawn_server(&self, server_id: &str, app: AppHandle) -> Result<()> {
        let mut guard = self.state.lock().unwrap();
        if guard.active_servers.contains_key(server_id) {
            return Ok(());
        }

        let config = self
            .registry
            .config
            .servers
            .iter()
            .find(|s| s.id == server_id)
            .ok_or_else(|| anyhow!("Server config not found: {}", server_id))?;

        if config.command.is_empty() {
            return Err(anyhow!("Invalid command for server: {}", server_id));
        }

        let program = self.resolve_command_path(&config.command[0]);
        let args: Vec<String> = config.command[1..]
            .iter()
            .map(|arg| self.resolve_command_path(arg))
            .collect();

        log::info!(
            "LspSupervisor: spawning {} -> {} {:?}",
            server_id,
            program,
            args
        );

        let mut child = Command::new(program)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| anyhow!("Failed to spawn LSP {}: {}", server_id, e))?;

        // Pipe stdout to frontend events (LSP Protocol Content-Length Framed)
        if let Some(mut stdout) = child.stdout.take() {
            let server_id = server_id.to_string();
            let app_handle = app.clone();
            thread::spawn(move || {
                loop {
                    match read_lsp_message(&mut stdout) {
                        Ok(Some(msg)) => {
                            let _ = app_handle.emit(
                                "lsp-message",
                                LspMessage {
                                    server_id: server_id.clone(),
                                    message: msg,
                                },
                            );
                        }
                        Ok(None) => break, // EOF
                        Err(e) => {
                            log::error!("lsp[{}][stdout] read error: {}", server_id, e);
                            break;
                        }
                    }
                }
            });
        }

        // Pipe stderr to logs
        if let Some(stderr) = child.stderr.take() {
            let server_id = server_id.to_string();
            thread::spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines().map_while(Result::ok) {
                    log::info!("lsp[{}][stderr]: {}", server_id, line);
                }
            });
        }

        guard.active_servers.insert(server_id.to_string(), child);
        Ok(())
    }

    /// Send a message to the server's stdin.
    pub fn send_message(&self, server_id: &str, message: &str) -> Result<()> {
        let mut guard = self.state.lock().unwrap();
        if let Some(child) = guard.active_servers.get_mut(server_id) {
            if let Some(mut stdin) = child.stdin.as_ref() {
                // Wrap in Content-Length header for valid LSP delivery
                let payload = format!("Content-Length: {}\r\n\r\n{}", message.len(), message);
                stdin.write_all(payload.as_bytes())?;
                stdin.flush()?;
                Ok(())
            } else {
                Err(anyhow!("Server {} has no stdin", server_id))
            }
        } else {
            Err(anyhow!("Server {} is not running", server_id))
        }
    }

    /// Check if a server is already running for a language.
    pub fn is_running_for_language(&self, language: &str) -> bool {
        let guard = self.state.lock().unwrap();
        if let Some(config) = self.registry.find_for_language(language) {
            guard.active_servers.contains_key(&config.id)
        } else {
            false
        }
    }

    /// Kill a server by ID.
    pub fn stop_server(&self, server_id: &str) -> Result<()> {
        let mut guard = self.state.lock().unwrap();
        if let Some(mut child) = guard.active_servers.remove(server_id) {
            child.kill()?;
            let _ = child.wait();
        }
        Ok(())
    }

    /// Kill all servers.
    pub fn stop_all(&self) {
        let mut guard = self.state.lock().unwrap();
        let servers: Vec<String> = guard.active_servers.keys().cloned().collect();
        for id in servers {
            if let Some(mut child) = guard.active_servers.remove(&id) {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }

    fn resolve_command_path(&self, tool: &str) -> String {
        tool.replace("${alos.resources}", &self.resource_dir.to_string_lossy())
    }
}

/// Robust Content-Length parser for LSP protocol framing.
fn read_lsp_message<R: Read>(reader: &mut R) -> Result<Option<String>> {
    let mut header = String::new();
    let mut buffer = [0u8; 1];

    // 1. Read headers until we hit \r\n\r\n
    loop {
        if reader.read_exact(&mut buffer).is_err() {
            return Ok(None); // EOF
        }
        header.push(buffer[0] as char);
        if header.ends_with("\r\n\r\n") {
            break;
        }
    }

    // 2. Parse Content-Length
    let content_length = header
        .lines()
        .find(|line| line.to_lowercase().starts_with("content-length:"))
        .and_then(|line| line.split(':').nth(1))
        .and_then(|val| val.trim().parse::<usize>().ok())
        .ok_or_else(|| anyhow!("Missing or invalid Content-Length in LSP header"))?;

    // 3. Read exactly content_length bytes
    let mut body = vec![0u8; content_length];
    reader.read_exact(&mut body).map_err(|e| {
        anyhow!(
            "Failed to read LSP body (expected {} bytes): {}",
            content_length,
            e
        )
    })?;

    Ok(Some(String::from_utf8_lossy(&body).into_owned()))
}
