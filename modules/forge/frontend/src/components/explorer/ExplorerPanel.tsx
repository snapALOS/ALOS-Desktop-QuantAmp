import React, { useState } from 'react';
import { Box, Button } from '@mui/material';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import { open } from '@tauri-apps/plugin-dialog';
import { isTauri } from '@/api/tauri';
import { useIDEStore } from '../../store/useIDEStore';
import FileTree from './FileTree';

const ExplorerPanel: React.FC = () => {
  const { adapter, rootPath, setRootPath, setActiveFile, setActiveFileContent } = useIDEStore();
  const [openError, setOpenError] = useState<string | null>(null);

  const handleOpenFolder = async () => {
    setOpenError(null);
    try {
      if (!isTauri()) {
        throw new Error('Local folder picking is available in the ALOS desktop app. The browser preview cannot open a native folder picker.');
      }
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === 'string') {
        const workspaceRoot = adapter ? await adapter.setWorkspaceRoot(selected) : selected;
        setRootPath(workspaceRoot);
        setActiveFile(null);
        setActiveFileContent('');
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setOpenError(message);
      console.error('Forge failed to open folder picker', error);
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: '#0f172a' }}>
      {/* Header */}
      <Box
        sx={{
          px: 1.5,
          py: 0.75,
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <Box
          sx={{
            fontSize: '0.65rem',
            fontWeight: 700,
            color: '#94a3b8',
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
          }}
        >
          Explorer
        </Box>
        <Button
          size="small"
          onClick={handleOpenFolder}
          startIcon={<FolderOpenIcon sx={{ fontSize: '13px !important' }} />}
          sx={{
            fontSize: '0.7rem',
            color: '#cbd5e1',
            textTransform: 'none',
            minWidth: 0,
            px: 0.75,
            '&:hover': { color: '#4f46e5', bgcolor: 'rgba(79,70,229,0.08)' },
          }}
        >
          Open
        </Button>
      </Box>

      {/* Content */}
      {rootPath ? (
        <>
          <Box
            sx={{
              px: 1.5,
              py: 0.5,
              fontSize: '0.65rem',
              fontWeight: 600,
              color: '#94a3b8',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              flexShrink: 0,
            }}
          >
            {rootPath.split('/').pop() ?? rootPath}
          </Box>
          <FileTree root={rootPath} />
        </>
      ) : (
        <Box
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1.5,
            px: 2,
          }}
        >
          <Box sx={{ fontSize: '0.75rem', color: '#cbd5e1', textAlign: 'center', lineHeight: 1.5 }}>
            Open a folder to start exploring your workspace
          </Box>
          {openError ? (
            <Box
              sx={{
                fontSize: '0.7rem',
                color: '#fca5a5',
                textAlign: 'center',
                lineHeight: 1.45,
                maxWidth: 220,
              }}
            >
              Folder picker failed: {openError}
            </Box>
          ) : null}
          <Button
            variant="outlined"
            size="small"
            onClick={handleOpenFolder}
            sx={{
              fontSize: '0.75rem',
              textTransform: 'none',
              borderColor: '#475569',
              color: '#e2e8f0',
              '&:hover': { borderColor: '#4f46e5', color: '#4f46e5' },
            }}
          >
            Open Folder
          </Button>
        </Box>
      )}
    </Box>
  );
};

export default ExplorerPanel;
