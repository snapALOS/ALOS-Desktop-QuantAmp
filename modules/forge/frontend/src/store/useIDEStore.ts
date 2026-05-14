import { create } from 'zustand';
import type { EnvironmentAdapter } from '../services/adapters/EnvironmentAdapter';

type SidebarView = 'explorer' | 'search' | 'sourceControl' | 'extensions' | 'settings' | null;
type PanelView = 'terminal' | 'agent' | 'debug' | 'output';

export interface ForgeSourceControlState {
  files: Array<{ status: string; path: string; staged: boolean }>;
  error: string | null;
  lastRefreshAt: number | null;
}

export interface ForgeAgentContext {
  rootPath: string;
  activeFile: string | null;
  openFiles: string[];
  activePanel: PanelView;
  sourceControl: ForgeSourceControlState | null;
  terminal: {
    observing: boolean;
    recentOutput: string[];
  };
}

interface IDEState {
  // Environment
  adapter: EnvironmentAdapter | null;
  setAdapter: (adapter: EnvironmentAdapter) => void;
  platform: string;
  setPlatform: (platform: string) => void;

  // UI State
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  activeSidebarView: SidebarView;
  setActiveSidebarView: (view: SidebarView) => void;
  activePanel: PanelView;
  setActivePanel: (panel: PanelView) => void;

  // Agent State
  isAgentObserving: boolean;
  setAgentObserving: (observing: boolean) => void;

  // Workspace State
  rootPath: string;
  setRootPath: (path: string) => void;
  activeFile: string | null;
  setActiveFile: (file: string | null) => void;
  activeFileContent: string;
  setActiveFileContent: (content: string) => void;
  openFiles: string[];
  addOpenFile: (path: string) => void;
  removeOpenFile: (path: string) => void;

  // Structured agent context
  sourceControlState: ForgeSourceControlState | null;
  setSourceControlState: (state: ForgeSourceControlState | null) => void;
  terminalTranscript: string[];
  appendTerminalTranscript: (chunk: string) => void;
  clearTerminalTranscript: () => void;
  getAgentContext: () => ForgeAgentContext;
}

export const useIDEStore = create<IDEState>((set, get) => ({
  adapter: null,
  setAdapter: (adapter) => set({ adapter }),
  platform: 'unknown',
  setPlatform: (platform) => set({ platform }),

  sidebarCollapsed: false,
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  activeSidebarView: 'explorer',
  setActiveSidebarView: (activeSidebarView) => set({ activeSidebarView }),
  activePanel: 'terminal',
  setActivePanel: (activePanel) => set({ activePanel }),

  isAgentObserving: false,
  setAgentObserving: (isAgentObserving) => set({ isAgentObserving }),

  rootPath: '',
  setRootPath: (rootPath) => set({ rootPath }),
  activeFile: null,
  setActiveFile: (activeFile) => set({ activeFile }),
  activeFileContent: '',
  setActiveFileContent: (activeFileContent) => set({ activeFileContent }),
  openFiles: [],
  addOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.includes(path) ? state.openFiles : [...state.openFiles, path],
  })),
  removeOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.filter((f) => f !== path),
    activeFile: state.activeFile === path
      ? (state.openFiles.find((f) => f !== path) ?? null)
      : state.activeFile,
  })),

  sourceControlState: null,
  setSourceControlState: (sourceControlState) => set({ sourceControlState }),
  terminalTranscript: [],
  appendTerminalTranscript: (chunk) => set((state) => {
    const next = [...state.terminalTranscript, chunk].slice(-80);
    return { terminalTranscript: next };
  }),
  clearTerminalTranscript: () => set({ terminalTranscript: [] }),
  getAgentContext: () => {
    const state = get();
    return {
      rootPath: state.rootPath,
      activeFile: state.activeFile,
      openFiles: state.openFiles,
      activePanel: state.activePanel,
      sourceControl: state.sourceControlState,
      terminal: {
        observing: state.isAgentObserving,
        recentOutput: state.terminalTranscript.slice(-40),
      },
    };
  },
}));
