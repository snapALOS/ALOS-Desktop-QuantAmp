/**
 * TauriAdapter — ALOS Forge environment adapter
 *
 * Routes all Forge operations through the ALOS core Tauri commands
 * (core_fs_*, core_terminal_*) via the typed wrappers in @/contracts/tauri-commands.
 * This replaces the old Rex-era direct invoke() calls.
 */

import {
  fsReadDir,
  fsReadFile,
  fsWriteFile,
  fsSearch,
  fsSetWorkspaceRoot,
  fsGetWorkspaceRoot,
  getAppConfig,
  writeAppConfig,
  terminalWrite,
  terminalResize,
} from '@/contracts/tauri-commands';
import { invoke, listen } from '@/api/tauri';
import type { EnvironmentAdapter, FileInfo, SearchResult, GitResult, AppConfig } from './EnvironmentAdapter';

type RawFileInfo = {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
};

type RawAppConfig = {
  theme?: string;
  fontSize?: number;
  font_size?: number;
  terminalShell?: string;
  terminal_shell?: string;
};

export class TauriAdapter implements EnvironmentAdapter {
  async setWorkspaceRoot(path: string): Promise<string> {
    return await fsSetWorkspaceRoot(path);
  }

  async getWorkspaceRoot(): Promise<string> {
    return await fsGetWorkspaceRoot();
  }

  async readDir(path: string): Promise<FileInfo[]> {
    // ALOS uses snake_case `is_dir`, EnvironmentAdapter uses camelCase `isDir`
    const raw = await fsReadDir(path) as RawFileInfo[];
    return raw.map((f) => ({
      name: f.name,
      path: f.path,
      isDir: f.is_dir,
      size: f.size ?? undefined,
    }));
  }

  async readFile(path: string): Promise<string> {
    return await fsReadFile(path);
  }

  async writeFile(path: string, content: string): Promise<void> {
    await fsWriteFile(path, content);
  }

  async searchFiles(root: string, query: string): Promise<SearchResult[]> {
    return await fsSearch(root, query);
  }

  async runGit(cwd: string, args: string[]): Promise<GitResult> {
    return await invoke<GitResult>('core_fs_run_git', { cwd, args });
  }

  async createTerminal(
    id: string,
    onData: (data: string) => void,
    onExit?: (payload: unknown) => void,
  ): Promise<() => void> {
    await invoke('core_terminal_create', { id });
    const unlistenData = await listen<string>(`terminal-data-${id}`, (data) => {
      onData(data);
    });
    const unlistenExit = await listen<unknown>(`terminal-exit-${id}`, (payload) => {
      onExit?.(payload);
    });
    return () => {
      unlistenData();
      unlistenExit();
    };
  }

  async writeToTerminal(id: string, data: string): Promise<void> {
    await terminalWrite(id, data);
  }

  async resizeTerminal(id: string, cols: number, rows: number): Promise<void> {
    await terminalResize(id, cols, rows);
  }

  async readConfig(): Promise<AppConfig> {
    const config = await getAppConfig() as RawAppConfig;
    // Map ALOS camelCase config to Forge snake_case interface
    return {
      theme: config.theme ?? 'dark',
      font_size: config.fontSize ?? config.font_size ?? 14,
      terminal_shell: config.terminalShell ?? config.terminal_shell ?? 'zsh',
    };
  }

  async writeConfig(config: AppConfig): Promise<void> {
    await writeAppConfig({
      theme: config.theme as 'dark' | 'light',
      fontSize: config.font_size,
      terminalShell: config.terminal_shell,
    });
  }

  async getPlatform(): Promise<string> {
    return await invoke<string>('core_get_platform');
  }
}
