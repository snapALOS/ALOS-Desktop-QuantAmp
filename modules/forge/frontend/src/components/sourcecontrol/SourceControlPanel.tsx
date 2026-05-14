import React, { useState, useEffect, useCallback } from 'react';
import { Box, Button, TextField, Divider, CircularProgress, Chip, Tooltip } from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import AddIcon from '@mui/icons-material/Add';
import RemoveIcon from '@mui/icons-material/Remove';
import { useIDEStore } from '../../store/useIDEStore';

interface StatusFile {
  status: string;
  path: string;
  staged: boolean;
}

function parseGitStatus(raw: string): StatusFile[] {
  return raw
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const staged = line[0] !== ' ' && line[0] !== '?';
      const status = staged ? line[0] : line[1];
      const path = line.slice(3).trim();
      return { status: status ?? '?', path, staged };
    });
}

const STATUS_COLORS: Record<string, string> = {
  M: '#f59e0b',
  A: '#10b981',
  D: '#ef4444',
  '?': '#64748b',
  R: '#6366f1',
};

function gitFailureMessage(result: { stderr: string; stdout: string }): string {
  return (result.stderr || result.stdout || 'Git command failed.').trim();
}

const SourceControlPanel: React.FC = () => {
  const [files, setFiles] = useState<StatusFile[]>([]);
  const [commitMsg, setCommitMsg] = useState('');
  const [loading, setLoading] = useState(false);
  const [diffContent, setDiffContent] = useState<string | null>(null);
  const [diffFile, setDiffFile] = useState<string | null>(null);
  const [gitError, setGitError] = useState<string | null>(null);
  const { adapter, rootPath, setSourceControlState } = useIDEStore();

  const refresh = useCallback(async () => {
    if (!adapter || !rootPath) {
      setSourceControlState(null);
      return;
    }
    setLoading(true);
    setGitError(null);
    try {
      const result = await adapter.runGit(rootPath, ['status', '--porcelain']);
      if (!result.success) {
        const message = gitFailureMessage(result);
        setFiles([]);
        setGitError(message);
        setSourceControlState({ files: [], error: message, lastRefreshAt: Date.now() });
        return;
      }
      const nextFiles = parseGitStatus(result.stdout);
      setFiles(nextFiles);
      setSourceControlState({ files: nextFiles, error: null, lastRefreshAt: Date.now() });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setFiles([]);
      setGitError(message);
      setSourceControlState({ files: [], error: message, lastRefreshAt: Date.now() });
      console.error('Git status error:', e);
    } finally {
      setLoading(false);
    }
  }, [adapter, rootPath, setSourceControlState]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const stageFile = async (file: StatusFile) => {
    if (!adapter || !rootPath) return;
    const result = await adapter.runGit(rootPath, ['add', file.path]);
    if (!result.success) setGitError(gitFailureMessage(result));
    refresh();
  };

  const unstageFile = async (file: StatusFile) => {
    if (!adapter || !rootPath) return;
    const result = await adapter.runGit(rootPath, ['reset', 'HEAD', file.path]);
    if (!result.success) setGitError(gitFailureMessage(result));
    refresh();
  };

  const stageAll = async () => {
    if (!adapter || !rootPath) return;
    const result = await adapter.runGit(rootPath, ['add', '-A']);
    if (!result.success) setGitError(gitFailureMessage(result));
    refresh();
  };

  const commit = async () => {
    if (!adapter || !rootPath || !commitMsg.trim()) return;
    setLoading(true);
    try {
      const result = await adapter.runGit(rootPath, ['commit', '-m', commitMsg.trim()]);
      if (result.success) {
        setCommitMsg('');
        refresh();
      } else {
        setGitError(gitFailureMessage(result));
        console.error('Commit failed:', result.stderr);
      }
    } finally {
      setLoading(false);
    }
  };

  const showDiff = async (file: StatusFile) => {
    if (!adapter || !rootPath) return;
    const result = await adapter.runGit(rootPath, ['diff', 'HEAD', '--', file.path]);
    if (!result.success) {
      setGitError(gitFailureMessage(result));
    }
    setDiffContent(result.stdout || result.stderr || 'No diff available');
    setDiffFile(file.path);
  };

  const staged = files.filter((f) => f.staged);
  const unstaged = files.filter((f) => !f.staged);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: '#0f172a' }}>
      {/* Header */}
      <Box
        sx={{
          p: 1,
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <Box sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          Source Control
        </Box>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          <Tooltip title="Stage All Changes">
            <Button size="small" onClick={stageAll} sx={{ minWidth: 0, px: 0.5, color: '#64748b', '&:hover': { color: '#10b981' } }}>
              <AddIcon sx={{ fontSize: 16 }} />
            </Button>
          </Tooltip>
          <Tooltip title="Refresh">
            <Button size="small" onClick={refresh} sx={{ minWidth: 0, px: 0.5, color: '#64748b', '&:hover': { color: '#4f46e5' } }}>
              {loading ? (
                <CircularProgress size={14} sx={{ color: '#64748b' }} />
              ) : (
                <RefreshIcon sx={{ fontSize: 16 }} />
              )}
            </Button>
          </Tooltip>
        </Box>
      </Box>

      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {!rootPath && (
          <Box sx={{ p: 2, fontSize: '0.75rem', color: '#334155' }}>
            Open a folder to use source control.
          </Box>
        )}

        {rootPath && gitError && (
          <Box sx={{ p: 2, fontSize: '0.75rem', color: '#fca5a5', lineHeight: 1.45 }}>
            {gitError}
          </Box>
        )}

        {/* Staged files */}
        {staged.length > 0 && (
          <>
            <Box sx={{ px: 1.5, py: 0.5, fontSize: '0.65rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Staged Changes ({staged.length})
            </Box>
            {staged.map((f) => (
              <Box
                key={`staged-${f.path}`}
                sx={{ display: 'flex', alignItems: 'center', px: 1.5, py: 0.3, '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' } }}
              >
                <Chip
                  label={f.status}
                  size="small"
                  sx={{ height: 16, fontSize: '0.6rem', mr: 0.75, bgcolor: STATUS_COLORS[f.status] ?? '#64748b', color: '#0f172a', fontWeight: 700, flexShrink: 0 }}
                />
                <Box
                  onClick={() => showDiff(f)}
                  sx={{ flex: 1, fontSize: '0.75rem', color: '#94a3b8', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', '&:hover': { color: '#e2e8f0' } }}
                >
                  {f.path}
                </Box>
                <Tooltip title="Unstage">
                  <Button size="small" onClick={() => unstageFile(f)} sx={{ minWidth: 0, px: 0.25, color: '#334155', '&:hover': { color: '#ef4444' } }}>
                    <RemoveIcon sx={{ fontSize: 14 }} />
                  </Button>
                </Tooltip>
              </Box>
            ))}
            <Divider sx={{ borderColor: '#1e293b', my: 0.5 }} />
          </>
        )}

        {/* Unstaged files */}
        {unstaged.length > 0 && (
          <>
            <Box sx={{ px: 1.5, py: 0.5, fontSize: '0.65rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Changes ({unstaged.length})
            </Box>
            {unstaged.map((f) => (
              <Box
                key={`unstaged-${f.path}`}
                sx={{ display: 'flex', alignItems: 'center', px: 1.5, py: 0.3, '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' } }}
              >
                <Chip
                  label={f.status}
                  size="small"
                  sx={{ height: 16, fontSize: '0.6rem', mr: 0.75, bgcolor: STATUS_COLORS[f.status] ?? '#64748b', color: '#0f172a', fontWeight: 700, flexShrink: 0 }}
                />
                <Box
                  onClick={() => showDiff(f)}
                  sx={{ flex: 1, fontSize: '0.75rem', color: '#94a3b8', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', '&:hover': { color: '#e2e8f0' } }}
                >
                  {f.path}
                </Box>
                <Tooltip title="Stage this file">
                  <Button size="small" onClick={() => stageFile(f)} sx={{ minWidth: 0, px: 0.25, color: '#334155', '&:hover': { color: '#10b981' } }}>
                    <AddIcon sx={{ fontSize: 14 }} />
                  </Button>
                </Tooltip>
              </Box>
            ))}
          </>
        )}

        {files.length === 0 && rootPath && !loading && !gitError && (
          <Box sx={{ p: 2, fontSize: '0.75rem', color: '#334155' }}>No changes detected.</Box>
        )}

        {/* Diff viewer */}
        {diffContent && (
          <>
            <Divider sx={{ borderColor: '#1e293b', mt: 1 }} />
            <Box sx={{ px: 1.5, py: 0.5, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
              <Box sx={{ fontSize: '0.65rem', fontWeight: 700, color: '#475569', textTransform: 'uppercase', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                diff: {diffFile?.split('/').pop()}
              </Box>
              <Button size="small" onClick={() => setDiffContent(null)} sx={{ fontSize: '0.65rem', color: '#334155', textTransform: 'none', minWidth: 0, flexShrink: 0 }}>
                close
              </Button>
            </Box>
            <Box sx={{ px: 1.5, pb: 2, fontFamily: 'monospace', fontSize: '0.72rem' }}>
              {diffContent.split('\n').map((line, i) => (
                <Box
                  key={i}
                  sx={{
                    color: line.startsWith('+') && !line.startsWith('+++') ? '#10b981' : line.startsWith('-') && !line.startsWith('---') ? '#ef4444' : '#475569',
                    bgcolor: line.startsWith('+') && !line.startsWith('+++') ? 'rgba(16,185,129,0.05)' : line.startsWith('-') && !line.startsWith('---') ? 'rgba(239,68,68,0.05)' : 'transparent',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}
                >
                  {line || ' '}
                </Box>
              ))}
            </Box>
          </>
        )}
      </Box>

      {/* Commit box */}
      <Box sx={{ p: 1, borderTop: '1px solid #1e293b', flexShrink: 0 }}>
        <TextField
          size="small"
          fullWidth
          multiline
          rows={2}
          placeholder="Commit message (staged files only)..."
          value={commitMsg}
          onChange={(e) => setCommitMsg(e.target.value)}
          sx={{
            mb: 0.75,
            '& .MuiInputBase-root': { fontSize: '0.78rem', bgcolor: '#1e293b', color: '#cbd5e1' },
            '& .MuiOutlinedInput-notchedOutline': { borderColor: '#334155' },
            '& .Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#4f46e5' },
          }}
        />
        <Button
          fullWidth
          size="small"
          variant="contained"
          disabled={!commitMsg.trim() || loading || staged.length === 0}
          onClick={commit}
          sx={{ fontSize: '0.75rem', textTransform: 'none', bgcolor: '#4f46e5', '&:hover': { bgcolor: '#4338ca' } }}
        >
          Commit {staged.length > 0 ? `(${staged.length} file${staged.length === 1 ? '' : 's'})` : '— stage files first'}
        </Button>
      </Box>
    </Box>
  );
};

export default SourceControlPanel;
