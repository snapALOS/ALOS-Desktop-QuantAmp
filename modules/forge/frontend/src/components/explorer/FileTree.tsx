import React, { useState, useEffect, useCallback } from 'react';
import { Box, CircularProgress } from '@mui/material';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import InsertDriveFileOutlinedIcon from '@mui/icons-material/InsertDriveFileOutlined';
import { useIDEStore } from '../../store/useIDEStore';
import type { FileInfo } from '../../services/adapters/EnvironmentAdapter';

interface FileTreeNodeProps {
  item: FileInfo;
  depth: number;
}

const FileTreeNode: React.FC<FileTreeNodeProps> = ({ item, depth }) => {
  const [expanded, setExpanded] = useState(false);
  const [children, setChildren] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [nodeError, setNodeError] = useState<string | null>(null);
  const { adapter, activeFile, setActiveFile, setActiveFileContent, addOpenFile } = useIDEStore();

  const handleClick = useCallback(async () => {
    setNodeError(null);
    if (item.isDir) {
      if (!expanded && children.length === 0) {
        setLoading(true);
        try {
          const entries = await adapter!.readDir(item.path);
          setChildren(entries);
        } catch (e) {
          const message = e instanceof Error ? e.message : String(e);
          setNodeError(message);
          console.error('Failed to read directory:', e);
        } finally {
          setLoading(false);
        }
      }
      setExpanded((e) => !e);
    } else {
      try {
        const content = await adapter!.readFile(item.path);
        setActiveFile(item.path);
        setActiveFileContent(content);
        addOpenFile(item.path);
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e);
        setNodeError(message);
        console.error('Failed to read file:', e);
      }
    }
  }, [item, expanded, children, adapter, setActiveFile, setActiveFileContent, addOpenFile]);

  const isActive = activeFile === item.path;

  return (
    <>
      <Box
        onClick={handleClick}
        sx={{
          display: 'flex',
          alignItems: 'center',
          pl: `${depth * 12 + 4}px`,
          pr: 1,
          py: '2px',
          cursor: 'pointer',
          fontSize: '0.8rem',
          color: isActive ? '#e2e8f0' : '#94a3b8',
          bgcolor: isActive ? 'rgba(79,70,229,0.15)' : 'transparent',
          userSelect: 'none',
          '&:hover': { bgcolor: isActive ? 'rgba(79,70,229,0.2)' : 'rgba(255,255,255,0.04)' },
        }}
      >
        {item.isDir ? (
          <>
            {loading ? (
              <CircularProgress size={12} sx={{ mr: 0.5, color: '#64748b', flexShrink: 0 }} />
            ) : expanded ? (
              <ExpandMoreIcon sx={{ fontSize: 14, mr: 0.5, color: '#64748b', flexShrink: 0 }} />
            ) : (
              <ChevronRightIcon sx={{ fontSize: 14, mr: 0.5, color: '#64748b', flexShrink: 0 }} />
            )}
            {expanded ? (
              <FolderOpenIcon sx={{ fontSize: 14, mr: 0.75, color: '#f59e0b', flexShrink: 0 }} />
            ) : (
              <FolderIcon sx={{ fontSize: 14, mr: 0.75, color: '#f59e0b', flexShrink: 0 }} />
            )}
          </>
        ) : (
          <>
            <Box sx={{ width: 14, mr: 0.5, flexShrink: 0 }} />
            <InsertDriveFileOutlinedIcon sx={{ fontSize: 14, mr: 0.75, color: '#64748b', flexShrink: 0 }} />
          </>
        )}
        <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {item.name}
        </Box>
      </Box>
      {expanded &&
        children.map((child) => (
          <FileTreeNode key={child.path} item={child} depth={depth + 1} />
        ))}
      {nodeError ? (
        <Box
          sx={{
            pl: `${depth * 12 + 22}px`,
            pr: 1,
            py: 0.35,
            fontSize: '0.68rem',
            color: '#fca5a5',
            lineHeight: 1.35,
          }}
        >
          {nodeError}
        </Box>
      ) : null}
    </>
  );
};

interface FileTreeProps {
  root: string;
}

const FileTree: React.FC<FileTreeProps> = ({ root }) => {
  const [entries, setEntries] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { adapter } = useIDEStore();

  useEffect(() => {
    if (!adapter || !root) return;
    let cancelled = false;

    void Promise.resolve().then(async () => {
      if (cancelled) return;
      setLoading(true);
      setError(null);
      try {
        const nextEntries = await adapter.readDir(root);
        if (!cancelled) setEntries(nextEntries);
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [root, adapter]);

  if (loading)
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', pt: 2 }}>
        <CircularProgress size={20} sx={{ color: '#4f46e5' }} />
      </Box>
    );

  if (error)
    return (
      <Box sx={{ px: 2, py: 1, fontSize: '0.75rem', color: '#ef4444' }}>Error: {error}</Box>
    );

  return (
    <Box sx={{ overflow: 'auto', flex: 1 }}>
      {entries.map((entry) => (
        <FileTreeNode key={entry.path} item={entry} depth={0} />
      ))}
    </Box>
  );
};

export default FileTree;
