import React from 'react';
import { Box, List, ListItem, ListItemButton, Tooltip } from '@mui/material';
import {
  FolderOutlined,
  SearchOutlined,
  AccountTreeOutlined,
  ExtensionOutlined,
  SettingsOutlined
} from '@mui/icons-material';
import { useIDEStore } from '../../store/useIDEStore';

type SidebarView = 'explorer' | 'search' | 'sourceControl' | 'extensions' | 'settings' | null;

const NAV_ITEMS: { icon: React.ReactNode; label: string; view: SidebarView }[] = [
  { icon: <FolderOutlined fontSize="small" />, label: 'Explorer', view: 'explorer' },
  { icon: <SearchOutlined fontSize="small" />, label: 'Search', view: 'search' },
  { icon: <AccountTreeOutlined fontSize="small" />, label: 'Source Control', view: 'sourceControl' },
  { icon: <ExtensionOutlined fontSize="small" />, label: 'Extensions', view: 'extensions' },
];

const Sidebar: React.FC = () => {
  const { activeSidebarView, setActiveSidebarView } = useIDEStore();

  const handleClick = (view: SidebarView) => {
    // Toggle off if already active, otherwise switch to clicked view
    setActiveSidebarView(activeSidebarView === view ? null : view);
  };

  return (
    <Box
      sx={{
        width: 50,
        bgcolor: '#f1f5f9',
        borderRight: '1px solid',
        borderColor: 'divider',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        py: 1
      }}
    >
      <List sx={{ width: '100%', px: 0 }}>
        {NAV_ITEMS.map((item) => {
          const isActive = activeSidebarView === item.view;
          return (
            <ListItem key={item.label} disablePadding sx={{ mb: 1 }}>
              <Tooltip title={item.label} placement="right">
                <ListItemButton
                  onClick={() => handleClick(item.view)}
                  sx={{
                    justifyContent: 'center',
                    px: 0,
                    color: isActive ? 'primary.main' : 'text.secondary',
                    borderLeft: isActive ? '2px solid' : '2px solid transparent',
                    borderColor: isActive ? 'primary.main' : 'transparent',
                    bgcolor: isActive ? 'rgba(79,70,229,0.08)' : 'transparent',
                    '&:hover': { color: 'primary.main' },
                  }}
                >
                  {item.icon}
                </ListItemButton>
              </Tooltip>
            </ListItem>
          );
        })}
      </List>
      <Box sx={{ flex: 1 }} />
      <Tooltip title="Settings" placement="right">
        <ListItemButton
          onClick={() => handleClick(null)}
          sx={{ color: 'text.secondary', '&:hover': { color: 'primary.main' } }}
        >
          <SettingsOutlined fontSize="small" />
        </ListItemButton>
      </Tooltip>
    </Box>
  );
};

export default Sidebar;

