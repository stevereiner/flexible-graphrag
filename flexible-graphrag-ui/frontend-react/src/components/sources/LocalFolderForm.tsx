import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, IconButton, List, ListItem, ListItemIcon, ListItemText, Tooltip, Typography,
} from '@mui/material';
import { Delete as DeleteIcon, Description as FileIcon, Folder as FolderIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { localProvider } from '../../browser/LocalProvider';
import { BrowseItem } from '../../browser/types';
import { addLocalRoots } from '../../desktop/localRoots';

/** A picked local file or folder: its native path. */
export interface LocalItem {
  path: string;
  isDirectory: boolean;
}

interface LocalFolderFormProps extends BaseSourceFormProps {
  items: LocalItem[];
  onItemsChange: (items: LocalItem[]) => void;
}

/**
 * Local files and folders (desktop app only): picked with the file browser, ingested by path as
 * the filesystem source (folders with everything below them), and kept in sync when Auto Sync is
 * on. The picked paths are added to the backend's allowed ingest folders (desktop/localRoots.ts).
 */
export const LocalFolderForm: React.FC<LocalFolderFormProps> = ({
  items,
  onItemsChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [browsing, setBrowsing] = useState(false);
  const [notice, setNotice] = useState<{ severity: 'warning' | 'info'; text: string } | null>(null);

  const config = useMemo(() => ({ paths: items.map((i) => i.path), items }), [items]);

  useEffect(() => {
    onValidationChange(items.length > 0);
    onConfigurationChange(config);
  }, [items, config, onValidationChange, onConfigurationChange]);

  // picks add up (several folders) until an ingest starts; App then empties the list (ingestSignal)
  const setItems = onItemsChange;

  const handleSelect = async (picked: BrowseItem[]) => {
    const add = picked
      .map((p) => ({ path: p.path || p.id, isDirectory: p.isDirectory }))
      .filter((p) => !items.some((i) => i.path === p.path));
    if (!add.length) return;
    onItemsChange([...items, ...add]);
    const result = await addLocalRoots(add.map((a) => a.path));
    setNotice(result.message ? { severity: result.ok ? 'info' : 'warning', text: result.message } : null);
  };

  return (
    <BaseSourceForm
      title="Local Files and Folders"
      description="Files and folders on this computer. A folder includes everything below it."
    >
      <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
        <Button variant="outlined" onClick={() => setBrowsing(true)}>Browse…</Button>
        {items.length > 0 && <Button onClick={() => setItems([])}>Clear</Button>}
      </Box>

      {items.length === 0 ? (
        <Typography variant="body2" sx={{ opacity: 0.7 }}>Nothing picked yet.</Typography>
      ) : (
        <List dense>
          {items.map((item) => (
            <ListItem
              key={item.path}
              secondaryAction={
                <Tooltip title="Leave out">
                  <IconButton edge="end" size="small" onClick={() => setItems(items.filter((i) => i.path !== item.path))}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              }
            >
              <ListItemIcon sx={{ minWidth: 32 }}>
                {item.isDirectory ? <FolderIcon fontSize="small" /> : <FileIcon fontSize="small" />}
              </ListItemIcon>
              <ListItemText primary={item.path} />
            </ListItem>
          ))}
        </List>
      )}

      {notice && <Alert severity={notice.severity} sx={{ mt: 1 }} onClose={() => setNotice(null)}>{notice.text}</Alert>}

      <SourceBrowser
        open={browsing}
        provider={localProvider}
        title="Add files and folders from this computer"
        onClose={() => setBrowsing(false)}
        onSelect={handleSelect}
      />
    </BaseSourceForm>
  );
};
