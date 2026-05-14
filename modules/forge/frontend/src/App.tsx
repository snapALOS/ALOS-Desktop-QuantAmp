/**
 * ALOSForge — App.tsx
 *
 * The IDE layout component for the Forge module, mounted inside the ALOS shell.
 * Title bar and status bar are removed — those are provided by the shell.
 */

import React, { useEffect } from 'react';
import { Box, ThemeProvider, CssBaseline } from '@mui/material';
import { createTheme } from '@mui/material/styles';
import Sidebar from './components/layout/Sidebar';
import BottomPanel from './components/layout/BottomPanel';
import ExplorerPanel from './components/explorer/ExplorerPanel';
import SearchPanel from './components/search/SearchPanel';
import SourceControlPanel from './components/sourcecontrol/SourceControlPanel';
import ExtensionsPanel from './components/extensions/ExtensionsPanel';
import SettingsPanel from './components/settings/SettingsPanel';
import MonacoEditor from './components/editor/MonacoEditor';
import { useIDEStore } from './store/useIDEStore';
import { registerModuleAgentContextProvider } from '@/shell/agent-context';

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#4f46e5' },
    secondary: { main: '#6366f1' },
    background: { default: '#0f172a', paper: '#1e293b' },
    divider: '#1e293b',
  },
  typography: {
    fontFamily: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif'].join(','),
    h1: { fontSize: '1.5rem', fontWeight: 600 },
    body1: { fontSize: '0.875rem' },
  },
  components: {
    MuiTab: { styleOverrides: { root: { fontWeight: 600, textTransform: 'none' } } },
    MuiMenuItem: { styleOverrides: { root: { fontSize: '0.8rem' } } },
  },
});

const SECONDARY_PANEL_WIDTH = 240;

const App: React.FC = () => {
  const { activeSidebarView } = useIDEStore();

  useEffect(() => {
    return registerModuleAgentContextProvider('forge', () => ({
      module_id: 'forge',
      module_name: 'Forge',
      captured_at: new Date().toISOString(),
      payload: { ...useIDEStore.getState().getAgentContext() },
    }));
  }, []);

  const renderSecondaryPanel = () => {
    switch (activeSidebarView) {
      case 'explorer':      return <ExplorerPanel />;
      case 'search':        return <SearchPanel />;
      case 'sourceControl': return <SourceControlPanel />;
      case 'extensions':    return <ExtensionsPanel />;
      case 'settings':      return <SettingsPanel />;
      default:              return null;
    }
  };

  const secondaryContent = renderSecondaryPanel();

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {/* IDE Body — fills the shell container, no standalone title/status bars */}
      <Box sx={{ display: 'flex', height: '100%', overflow: 'hidden', bgcolor: '#0f172a' }}>

        {/* Activity Bar (icon strip) */}
        <Sidebar />

        {/* Secondary Panel (slides open based on active view) */}
        {secondaryContent && (
          <Box
            sx={{
              width: SECONDARY_PANEL_WIDTH,
              flexShrink: 0,
              borderRight: '1px solid #1e293b',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {secondaryContent}
          </Box>
        )}

        {/* Main workspace: editor + bottom panel */}
        <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>

          {/* Monaco Editor area */}
          <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <MonacoEditor />
          </Box>

          {/* Bottom Panel (terminal / output / debug) */}
          <Box sx={{ height: 320, flexShrink: 0, borderTop: '1px solid #1e293b' }}>
            <BottomPanel />
          </Box>

        </Box>
      </Box>
    </ThemeProvider>
  );
};

export default App;
