import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box } from '@mui/material';
import Editor from '@monaco-editor/react';
import { useIDEStore } from '../../store/useIDEStore';

const LANGUAGE_MAP: Record<string, string> = {
  ts: 'typescript', tsx: 'typescript', js: 'javascript', jsx: 'javascript',
  rs: 'rust', py: 'python', json: 'json', md: 'markdown',
  html: 'html', css: 'css', scss: 'scss', sh: 'shell',
  toml: 'toml', yaml: 'yaml', yml: 'yaml', txt: 'plaintext',
  go: 'go', java: 'java', cpp: 'cpp', c: 'c', cs: 'csharp',
  rb: 'ruby', php: 'php', swift: 'swift', kt: 'kotlin',
};

function getLanguage(filePath: string | null): string {
  if (!filePath) return 'plaintext';
  const ext = filePath.split('.').pop()?.toLowerCase() ?? '';
  return LANGUAGE_MAP[ext] ?? 'plaintext';
}

const MonacoEditor: React.FC = () => {
  const { activeFile, activeFileContent, setActiveFileContent, adapter } = useIDEStore();
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saveStatus, setSaveStatus] = useState<{
    file: string | null;
    state: 'idle' | 'saving' | 'saved' | 'error';
    error: string | null;
  }>({ file: null, state: 'idle', error: null });

  const saveState = saveStatus.file === activeFile ? saveStatus.state : 'idle';
  const saveError = saveStatus.file === activeFile ? saveStatus.error : null;

  const handleChange = useCallback(
    (value: string | undefined) => {
      if (value === undefined || !activeFile || !adapter) return;
      setActiveFileContent(value);
      // Auto-save with 1 second debounce
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        setSaveStatus({ file: activeFile, state: 'saving', error: null });
        adapter
          .writeFile(activeFile, value)
          .then(() => setSaveStatus({ file: activeFile, state: 'saved', error: null }))
          .catch((error) => {
            const message = error instanceof Error ? error.message : String(error);
            setSaveStatus({ file: activeFile, state: 'error', error: message });
            console.error('Forge save failed:', error);
          });
      }, 1000);
    },
    [activeFile, adapter, setActiveFileContent]
  );

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
  }, []);

  if (!activeFile) {
    return (
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          bgcolor: '#0f172a',
          flexDirection: 'column',
          gap: 1.25,
          px: 3,
          textAlign: 'center',
        }}
      >
        <Box sx={{ fontSize: '1.5rem', color: '#64748b' }}>{'</>'}</Box>
        <Box sx={{ fontSize: '0.9rem', color: '#e2e8f0', fontWeight: 700 }}>
          Forge IDE
        </Box>
        <Box sx={{ fontSize: '0.8rem', color: '#94a3b8', maxWidth: 300, lineHeight: 1.5 }}>
          Open a file from the Explorer to start editing
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      {/* File tab bar */}
      <Box
        sx={{
          height: 35,
          bgcolor: '#0f172a',
          borderBottom: '1px solid #1e293b',
          display: 'flex',
          alignItems: 'center',
          px: 1,
          flexShrink: 0,
        }}
      >
        <Box
          sx={{
            px: 1.5,
            py: 0.5,
            fontSize: '0.78rem',
            color: '#e2e8f0',
            bgcolor: '#1e293b',
            borderRadius: '4px 4px 0 0',
            borderTop: '1px solid #4f46e5',
            fontFamily: 'monospace',
          }}
        >
          {activeFile.split('/').pop()}
        </Box>
        <Box
          sx={{
            ml: 'auto',
            fontSize: '0.68rem',
            color: saveState === 'error' ? '#fca5a5' : '#64748b',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            maxWidth: '45%',
          }}
          title={saveError ?? undefined}
        >
          {saveState === 'saving'
            ? 'Saving...'
            : saveState === 'saved'
              ? 'Saved'
              : saveState === 'error'
                ? `Save failed: ${saveError}`
                : ''}
        </Box>
      </Box>
      <Editor
        key={activeFile}
        value={activeFileContent}
        language={getLanguage(activeFile)}
        theme="vs-dark"
        onChange={handleChange}
        options={{
          fontSize: 13,
          fontFamily: 'Menlo, Monaco, "Courier New", monospace',
          minimap: { enabled: true },
          scrollBeyondLastLine: false,
          renderLineHighlight: 'all',
          lineNumbers: 'on',
          wordWrap: 'on',
          automaticLayout: true,
          tabSize: 2,
          insertSpaces: true,
          formatOnPaste: true,
        }}
      />
    </Box>
  );
};

export default MonacoEditor;
