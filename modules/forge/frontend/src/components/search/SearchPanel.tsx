import React, { useState } from 'react';
import { Box, TextField, Button, CircularProgress, Divider } from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { useIDEStore } from '../../store/useIDEStore';
import type { SearchResult } from '../../services/adapters/EnvironmentAdapter';

const SearchPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { adapter, rootPath, setActiveFile, setActiveFileContent, addOpenFile } = useIDEStore();

  const handleSearch = async () => {
    if (!query.trim() || !adapter) return;
    if (!rootPath) {
      setSearched(true);
      setResults([]);
      setError('Open a workspace folder before searching.');
      return;
    }
    const root = rootPath;
    setLoading(true);
    setSearched(true);
    setError(null);
    try {
      const r = await adapter.searchFiles(root, query);
      setResults(r);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setResults([]);
      console.error('Search error:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleResultClick = async (result: SearchResult) => {
    if (!adapter) return;
    setError(null);
    try {
      const content = await adapter.readFile(result.file);
      setActiveFile(result.file);
      setActiveFileContent(content);
      addOpenFile(result.file);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      console.error('Failed to open file:', e);
    }
  };

  // Group by file
  const grouped = results.reduce<Record<string, SearchResult[]>>((acc, r) => {
    (acc[r.file] ??= []).push(r);
    return acc;
  }, {});

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: '#0f172a' }}>
      {/* Search input */}
      <Box sx={{ p: 1, borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        <Box sx={{ display: 'flex', gap: 0.5 }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Search in files..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            sx={{
              '& .MuiInputBase-root': {
                fontSize: '0.8rem',
                bgcolor: '#1e293b',
                color: '#cbd5e1',
                borderRadius: 1,
              },
              '& .MuiOutlinedInput-notchedOutline': { borderColor: '#334155' },
              '& .Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#4f46e5' },
            }}
          />
          <Button
            onClick={handleSearch}
            disabled={loading}
            variant="contained"
            size="small"
            sx={{ minWidth: 36, px: 1, bgcolor: '#4f46e5', '&:hover': { bgcolor: '#4338ca' } }}
          >
            {loading ? (
              <CircularProgress size={16} sx={{ color: 'white' }} />
            ) : (
              <SearchIcon sx={{ fontSize: 18 }} />
            )}
          </Button>
        </Box>
        {searched && !loading && (
          <Box sx={{ mt: 0.5, fontSize: '0.7rem', color: error ? '#fca5a5' : '#475569' }}>
            {error
              ? error
              : results.length === 0
                ? 'No results'
                : `${results.length} result${results.length === 1 ? '' : 's'} in ${Object.keys(grouped).length} file${Object.keys(grouped).length === 1 ? '' : 's'}`}
          </Box>
        )}
      </Box>

      {/* Results */}
      <Box sx={{ flex: 1, overflow: 'auto' }}>
        {!searched && (
          <Box sx={{ p: 2, fontSize: '0.75rem', color: '#334155' }}>
            Enter a search term and press Enter.
          </Box>
        )}
        {Object.entries(grouped).map(([file, fileResults]) => {
          const parts = file.split('/');
          const shortFile = parts.slice(-2).join('/');
          return (
            <Box key={file}>
              <Box
                sx={{
                  px: 1.5,
                  py: 0.5,
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  color: '#64748b',
                  bgcolor: '#0a0f1e',
                  position: 'sticky',
                  top: 0,
                  display: 'flex',
                  justifyContent: 'space-between',
                }}
              >
                <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {shortFile}
                </Box>
                <Box sx={{ color: '#334155', flexShrink: 0, ml: 1 }}>{fileResults.length}</Box>
              </Box>
              {fileResults.map((r, i) => (
                <Box
                  key={i}
                  onClick={() => handleResultClick(r)}
                  sx={{
                    px: 2,
                    py: 0.3,
                    cursor: 'pointer',
                    display: 'flex',
                    gap: 1.5,
                    alignItems: 'baseline',
                    '&:hover': { bgcolor: 'rgba(79,70,229,0.08)' },
                  }}
                >
                  <Box sx={{ fontSize: '0.68rem', color: '#334155', minWidth: 28, textAlign: 'right', flexShrink: 0 }}>
                    {r.line}
                  </Box>
                  <Box
                    sx={{
                      fontSize: '0.75rem',
                      color: '#cbd5e1',
                      fontFamily: 'monospace',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {r.text}
                  </Box>
                </Box>
              ))}
              <Divider sx={{ borderColor: '#0a0f1e' }} />
            </Box>
          );
        })}
      </Box>
    </Box>
  );
};

export default SearchPanel;
