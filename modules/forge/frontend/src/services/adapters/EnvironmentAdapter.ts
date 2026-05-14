export interface FileInfo {
  name: string;
  path: string;
  isDir: boolean;
  size?: number;
}

export interface SearchResult {
  file: string;
  line: number;
  text: string;
}

export interface GitResult {
  stdout: string;
  stderr: string;
  success: boolean;
}

export interface AppConfig {
  theme: string;
  font_size: number;
  terminal_shell: string;
}

export interface EnvironmentAdapter {
  // Workspace operations
  setWorkspaceRoot(path: string): Promise<string>;
  getWorkspaceRoot(): Promise<string>;

  // File operations
  readDir(path: string): Promise<FileInfo[]>;
  readFile(path: string): Promise<string>;
  writeFile(path: string, content: string): Promise<void>;

  // Search
  searchFiles(root: string, query: string): Promise<SearchResult[]>;

  // Git
  runGit(cwd: string, args: string[]): Promise<GitResult>;

  // Terminal operations
  createTerminal(
    id: string,
    onData: (data: string) => void,
    onExit?: (payload: unknown) => void,
  ): Promise<() => void>;
  writeToTerminal(id: string, data: string): Promise<void>;
  resizeTerminal(id: string, cols: number, rows: number): Promise<void>;

  // Config
  readConfig(): Promise<AppConfig>;
  writeConfig(config: AppConfig): Promise<void>;

  // System info
  getPlatform(): Promise<string>;
}
