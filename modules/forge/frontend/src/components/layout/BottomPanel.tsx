import React from 'react';
import { Box, Tabs, Tab, Switch, FormControlLabel, Tooltip } from '@mui/material';
import { useIDEStore } from '../../store/useIDEStore';
import VisibilityOutlined from '@mui/icons-material/VisibilityOutlined';
import VisibilityOffOutlined from '@mui/icons-material/VisibilityOffOutlined';
import Terminal from '../agentic/Terminal';
import ForgeAgentPanel from '../agentic/ForgeAgentPanel';

const BottomPanel: React.FC = () => {
  const { 
    activePanel, 
    setActivePanel, 
    isAgentObserving, 
    setAgentObserving 
  } = useIDEStore();

  return (
    <Box 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column', 
        bgcolor: '#0f172a',
        color: '#f8fafc'
      }}
    >
      {/* Panel Header */}
      <Box 
        sx={{ 
          height: 36, 
          display: 'flex', 
          alignItems: 'center', 
          px: 1, 
          borderBottom: '1px solid #1e293b',
          justifyContent: 'space-between'
        }}
      >
        <Tabs 
          value={activePanel} 
          onChange={(_, v) => setActivePanel(v)}
          textColor="inherit"
          indicatorColor="primary"
          sx={{ minHeight: 36, '& .MuiTab-root': { minHeight: 36, py: 0, fontSize: '0.75rem', color: '#94a3b8' } }}
        >
          <Tab value="terminal" label="TERMINAL" />
          <Tab value="agent" label="AGENT" />
          <Tab value="output" label="OUTPUT" />
          <Tab value="debug" label="DEBUG CONSOLE" />
        </Tabs>

        {/* Agent observation toggle */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Tooltip title={isAgentObserving ? "Agent is observing terminal" : "Agent observation disabled"}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              {isAgentObserving ? (
                <VisibilityOutlined sx={{ fontSize: 16, color: '#10b981' }} />
              ) : (
                <VisibilityOffOutlined sx={{ fontSize: 16, color: '#64748b' }} />
              )}
            </Box>
          </Tooltip>
          <FormControlLabel
            control={
              <Switch 
                size="small" 
                checked={isAgentObserving} 
                onChange={(e) => setAgentObserving(e.target.checked)}
                sx={{ 
                  '& .MuiSwitch-switchBase.Mui-checked': { color: '#10b981' },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#10b981' }
                }}
              />
            }
            label={<Box sx={{ fontSize: '0.7rem', color: '#94a3b8' }}>Agent Observation</Box>}
            labelPlacement="start"
          />
        </Box>
      </Box>

      {/* Panel Content (Terminal Placeholder) */}
      <Box sx={{ flex: 1, p: 1, overflow: 'hidden', position: 'relative' }}>
        {activePanel === 'terminal' && (
          <Terminal />
        )}
        {activePanel === 'agent' && (
          <ForgeAgentPanel />
        )}
        {activePanel === 'output' && (
          <Box sx={{ color: '#475569', fontSize: '0.75rem' }}>No output yet.</Box>
        )}
        {activePanel === 'debug' && (
          <Box sx={{ color: '#475569', fontSize: '0.75rem' }}>No debug session is running.</Box>
        )}
      </Box>
    </Box>
  );
};

export default BottomPanel;
