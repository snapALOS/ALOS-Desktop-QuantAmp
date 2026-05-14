import React from 'react';
import { Box, Divider, Chip } from '@mui/material';
import ExtensionIcon from '@mui/icons-material/Extension';

const EXTENSIONS = [
  { name: 'Rust Analyzer', publisher: 'rust-lang', description: 'Rust language support with IntelliSense', version: '0.3.1', installed: true, color: '#f59e0b' },
  { name: 'Prettier', publisher: 'prettier', description: 'Opinionated code formatter', version: '10.1.0', installed: true, color: '#10b981' },
  { name: 'ESLint', publisher: 'dbaeumer', description: 'JavaScript and TypeScript linting', version: '2.4.4', installed: true, color: '#6366f1' },
  { name: 'GitLens', publisher: 'eamodio', description: 'Git supercharged — blame, history, compare', version: '14.9.0', installed: false, color: '#f43f5e' },
  { name: 'Docker', publisher: 'ms-azuretools', description: 'Docker container management', version: '1.28.0', installed: false, color: '#0ea5e9' },
  { name: 'Python', publisher: 'ms-python', description: 'Python language support', version: '2024.1.0', installed: false, color: '#eab308' },
];

const ExtensionsPanel: React.FC = () => (
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
      Extensions
    </Box>

    <Box sx={{ px: 1.5, pt: 1, pb: 0.25, fontSize: '0.65rem', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      Installed
    </Box>

    {EXTENSIONS.filter((e) => e.installed).map((ext) => (
      <Box
        key={ext.name}
        sx={{ px: 1.5, py: 0.75, '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' }, cursor: 'default' }}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              bgcolor: `${ext.color}22`,
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ExtensionIcon sx={{ fontSize: 18, color: ext.color }} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Box sx={{ fontSize: '0.8rem', color: '#e2e8f0', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {ext.name}
              </Box>
              <Chip label="✓" size="small" sx={{ height: 14, fontSize: '0.6rem', bgcolor: '#10b9811a', color: '#10b981', flexShrink: 0 }} />
            </Box>
            <Box sx={{ fontSize: '0.7rem', color: '#334155' }}>{ext.publisher} · v{ext.version}</Box>
            <Box sx={{ fontSize: '0.72rem', color: '#475569', mt: 0.25 }}>{ext.description}</Box>
          </Box>
        </Box>
      </Box>
    ))}

    <Divider sx={{ borderColor: '#1e293b', my: 0.75 }} />

    <Box sx={{ px: 1.5, pt: 0.25, pb: 0.25, fontSize: '0.65rem', fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
      Recommended
    </Box>

    {EXTENSIONS.filter((e) => !e.installed).map((ext) => (
      <Box
        key={ext.name}
        sx={{ px: 1.5, py: 0.75, opacity: 0.6, '&:hover': { bgcolor: 'rgba(255,255,255,0.02)', opacity: 0.9 }, cursor: 'default', transition: 'opacity 0.15s' }}
      >
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
          <Box
            sx={{
              width: 32,
              height: 32,
              bgcolor: '#1e293b',
              borderRadius: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ExtensionIcon sx={{ fontSize: 18, color: '#334155' }} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Box sx={{ fontSize: '0.8rem', color: '#64748b', fontWeight: 500 }}>{ext.name}</Box>
            <Box sx={{ fontSize: '0.7rem', color: '#1e293b' }}>{ext.publisher} · v{ext.version}</Box>
            <Box sx={{ fontSize: '0.72rem', color: '#2d3748', mt: 0.25 }}>{ext.description}</Box>
          </Box>
        </Box>
      </Box>
    ))}
  </Box>
);

export default ExtensionsPanel;
