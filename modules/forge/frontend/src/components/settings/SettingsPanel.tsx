import React, { useState, useEffect } from 'react';
import { Box, Slider, Select, MenuItem, FormControl, Button } from '@mui/material';
import { useIDEStore } from '../../store/useIDEStore';
import type { AppConfig } from '../../services/adapters/EnvironmentAdapter';

const SettingsPanel: React.FC = () => {
  const { adapter } = useIDEStore();
  const [config, setConfig] = useState<AppConfig>({
    theme: 'dark',
    font_size: 14,
    terminal_shell: 'bash',
  });
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!adapter) return;
    adapter
      .readConfig()
      .then(setConfig)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [adapter]);

  const handleSave = async () => {
    if (!adapter) return;
    try {
      await adapter.writeConfig(config);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save config:', e);
    }
  };

  const labelSx = { fontSize: '0.72rem', color: '#64748b', mb: 0.75, fontWeight: 500 };
  const sectionSx = { mb: 2.5 };
  const selectSx = {
    bgcolor: '#1e293b',
    color: '#cbd5e1',
    fontSize: '0.8rem',
    '.MuiOutlinedInput-notchedOutline': { borderColor: '#334155' },
    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#4f46e5' },
    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#4f46e5' },
    '.MuiSvgIcon-root': { color: '#64748b' },
  };

  if (loading) return <Box sx={{ bgcolor: '#0f172a', flex: 1 }} />;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', bgcolor: '#0f172a', overflow: 'auto' }}>
      <Box
        sx={{
          px: 1.5,
          py: 0.75,
          borderBottom: '1px solid #1e293b',
          fontSize: '0.65rem',
          fontWeight: 700,
          color: '#475569',
          textTransform: 'uppercase',
          letterSpacing: '0.08em',
          flexShrink: 0,
        }}
      >
        Settings
      </Box>

      <Box sx={{ p: 2, flex: 1 }}>
        {/* Theme */}
        <Box sx={sectionSx}>
          <Box sx={labelSx}>Color Theme</Box>
          <FormControl size="small" fullWidth>
            <Select value={config.theme} onChange={(e) => setConfig((c) => ({ ...c, theme: e.target.value }))} sx={selectSx}>
              <MenuItem value="dark">Dark (default)</MenuItem>
              <MenuItem value="light">Light</MenuItem>
            </Select>
          </FormControl>
        </Box>

        {/* Font size */}
        <Box sx={sectionSx}>
          <Box sx={labelSx}>Editor Font Size — {config.font_size}px</Box>
          <Slider
            value={config.font_size}
            onChange={(_, v) => setConfig((c) => ({ ...c, font_size: v as number }))}
            min={10}
            max={24}
            step={1}
            marks
            valueLabelDisplay="auto"
            sx={{
              color: '#4f46e5',
              '& .MuiSlider-markLabel': { fontSize: '0.65rem', color: '#334155' },
            }}
          />
        </Box>

        {/* Terminal shell */}
        <Box sx={sectionSx}>
          <Box sx={labelSx}>Terminal Shell</Box>
          <FormControl size="small" fullWidth>
            <Select value={config.terminal_shell} onChange={(e) => setConfig((c) => ({ ...c, terminal_shell: e.target.value }))} sx={selectSx}>
              <MenuItem value="bash">bash</MenuItem>
              <MenuItem value="zsh">zsh</MenuItem>
              <MenuItem value="sh">sh</MenuItem>
              <MenuItem value="fish">fish</MenuItem>
              <MenuItem value="powershell.exe">PowerShell</MenuItem>
            </Select>
          </FormControl>
        </Box>

        <Button
          variant="contained"
          fullWidth
          onClick={handleSave}
          sx={{
            bgcolor: saved ? '#10b981' : '#4f46e5',
            '&:hover': { bgcolor: saved ? '#059669' : '#4338ca' },
            textTransform: 'none',
            fontSize: '0.8rem',
            transition: 'background-color 0.25s',
          }}
        >
          {saved ? '✓ Settings Saved' : 'Save Settings'}
        </Button>
      </Box>
    </Box>
  );
};

export default SettingsPanel;
