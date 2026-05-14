import { invoke } from '@/api/tauri';

/**
 * Tauri Command Contracts
 * 
 * This file mirrors the Rust #[tauri::command] signatures in the backend. 
 * Any change here MUST be reflected in src-tauri/src/lib.rs and related modules.
 */

// --- LSP Supervisor ---

export interface LspMessage {
  serverId: string;
  message: string;
}

export const lspRequestServer = (language: string) => 
  invoke<string>('lsp_request_server', { language });

export const lspSendMessage = (serverId: string, message: string) => 
  invoke<void>('lsp_send_message', { serverId, message });

export const lspRestartServer = (serverId: string) => 
  invoke<void>('lsp_restart_server', { serverId });


// --- Backend Lifecycle ---

export interface BackendStatus {
  port: number;
  running: boolean;
  lastError: string | null;
}

export const getBackendStatus = () => 
  invoke<BackendStatus>('backend_status');

export const launchBackend = () => 
  invoke<void>('launch_backend');


// --- Module Registry ---

export interface ModuleManifest {
  name: string;
  display_name: string;
  version: string;
  description: string;
  nav?: {
    order: number;
    icon: string;
    route: string;
  };
}

export const listModules = () => 
  invoke<ModuleManifest[]>('list_modules');

export const refreshModules = () => 
  invoke<void>('refresh_modules');


// --- Filesystem Operations ---

export interface FileInfo {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
}

export interface SearchResult {
  file: string;
  line: number;
  text: string;
}

export interface AppConfig {
  theme: 'dark' | 'light';
  fontSize: number;
  terminalShell: string;
}

export const fsReadDir = (path: string) => 
  invoke<FileInfo[]>('core_fs_read_dir', { path });

export const fsReadFile = (path: string) => 
  invoke<string>('core_fs_read_file', { path });

export const fsWriteFile = (path: string, content: string) => 
  invoke<void>('core_fs_write_file', { path, content });

export const fsSearch = (root: string, query: string) => 
  invoke<SearchResult[]>('core_fs_search', { root, query });

export const fsSetWorkspaceRoot = (path: string) =>
  invoke<string>('core_fs_set_workspace_root', { path });

export const fsGetWorkspaceRoot = () =>
  invoke<string>('core_fs_get_workspace_root');

export const getAppConfig = () => 
  invoke<AppConfig>('core_fs_read_config');

export const writeAppConfig = (config: AppConfig) => 
  invoke<void>('core_fs_write_config', { config });


// --- Terminal & Shell ---

/**
 * Create a new PTY terminal session under the caller-provided `id`.
 *
 * The Rust side emits `terminal-data-<id>` for output and `terminal-exit-<id>`
 * when the PTY closes. Callers are responsible for generating a unique id
 * (e.g. `crypto.randomUUID()`) and for listening on the matching channels.
 */
export const terminalCreate = (id: string) =>
  invoke<void>('core_terminal_create', { id });

export const terminalWrite = (id: string, data: string) =>
  invoke<void>('core_terminal_write', { id, data });

export const terminalResize = (id: string, cols: number, rows: number) =>
  invoke<void>('core_terminal_resize', { id, cols, rows });


// --- Global Events ---

export const emitEvent = (eventJson: string) => 
  invoke<void>('emit_event', { eventJson });

export const forwardEventToBackend = (eventJson: string) => 
  invoke<void>('forward_event_to_backend', { eventJson });
