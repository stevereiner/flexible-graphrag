import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { FileItem, FileManager } from '@cubone/react-file-manager';
import '@cubone/react-file-manager/style.css';
import './sourceBrowser.css';
import './sourceBrowserDark.css';
import { useTheme } from '@mui/material/styles';
import { BrowseItem, BrowseProvider } from './types';
import { saveTrail, startTrail } from './lastFolder';

/**
 * A read-only picker over any BrowseProvider, on react-file-manager (MIT). The component wants
 * one flat list of items keyed by '/'-separated paths; here those are display paths built from
 * names ("/C:/Users/me"), and each item keeps its source item (`ref`) with the real id / path.
 * Folders load one level at a time when opened (onFolderChange).
 */
interface SourceBrowserProps {
  open: boolean;
  provider: BrowseProvider;
  title?: string;
  onClose: () => void;
  onSelect: (items: BrowseItem[]) => void;
  /** What the source's config can hold: files too (default yes), several (default yes), folders and
   *  files together (default yes; no = one folder, or files only: OneDrive folder_path / file_ids).
   *  files + multiple={false}: one folder or one file (CMIS folder_path, which may name a document). */
  files?: boolean;
  multiple?: boolean;
  mixed?: boolean;
}

type Entry = FileItem & { ref: BrowseItem };

const NO_EDITING = { create: false, upload: false, move: false, copy: false, rename: false, download: false, delete: false };
const MAX_PAGES = 50;

// '/' separates display path segments: keep it out of names (Box / Drive names may have one)
const segment = (name: string) => name.replace(/\//g, '\u2215');

const toEntry = (item: BrowseItem, parentPath: string): Entry => ({
  name: item.name,
  isDirectory: item.isDirectory,
  path: `${parentPath}/${segment(item.name)}`,
  updatedAt: item.modified,
  size: item.size,
  ref: item,
});

export const SourceBrowser: React.FC<SourceBrowserProps> = ({
  open, provider, title, onClose, onSelect, files: allowFiles = true, multiple = true, mixed = true,
}) => {
  const dark = useTheme().palette.mode === 'dark';
  const [files, setFiles] = useState<Entry[]>([]);
  const [selection, setSelection] = useState<FileItem[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('');
  // where the file manager opens (it reads it once, with the first files)
  const [startPath, setStartPath] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const loaded = useRef<Set<string>>(new Set());
  const filesRef = useRef<Entry[]>([]);
  filesRef.current = files;

  // all of one folder's children, page by page
  const listAll = useCallback(async (folder: BrowseItem): Promise<BrowseItem[]> => {
    const children: BrowseItem[] = [];
    let token: string | null | undefined = null;
    for (let page = 0; page < MAX_PAGES; page++) {
      const listing = await provider.list(folder, token);
      children.push(...listing.items);
      token = listing.nextPageToken;
      if (!token) break;
    }
    return children;
  }, [provider]);

  const loadChildren = useCallback(async (folder: Entry, replace = false) => {
    setLoading(true);
    setError('');
    try {
      const children = (await listAll(folder.ref)).map((i) => toEntry(i, folder.path));
      setFiles((prev) => {
        const prefix = `${folder.path}/`;
        // replace: drop what was listed below this folder before (refresh)
        const kept = replace ? prev.filter((f) => !f.path.startsWith(prefix)) : prev;
        const have = new Set(kept.map((f) => f.path));
        return [...kept, ...children.filter((c) => !have.has(c.path))];
      });
      loaded.current.add(folder.path);
    } catch (e: any) {
      setError(`Could not list ${folder.ref.path || folder.name}: ${e?.message || e}`);
    } finally {
      setLoading(false);
    }
  }, [listAll]);

  // A fresh start each time the browser opens: the roots, then the folder last open in this
  // source's browser when its root is still there and it still lists
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    loaded.current = new Set(['']);
    setFiles([]);
    setSelection([]);
    setCurrentPath('');
    setStartPath('');
    setError('');
    setLoading(true);
    (async () => {
      try {
        const roots = await provider.roots();
        const entries = roots.map((r) => toEntry(r, ''));
        let start = '';
        const trail = await startTrail(provider);
        const root = trail.length ? roots.find((r) => r.id === trail[0].id) : undefined;
        if (root) {
          try {
            // the trail's folders (the ones above the last load when opened), then the last's children
            const chain: Entry[] = [];
            let parent = '';
            for (const folder of [root, ...trail.slice(1)]) {
              const entry = toEntry(folder, parent);
              chain.push(entry);
              parent = entry.path;
            }
            const last = chain[chain.length - 1];
            const children = await listAll(last.ref);
            entries.push(...chain.slice(1), ...children.map((c) => toEntry(c, last.path)));
            loaded.current.add(last.path);
            start = last.path;
          } catch { /* gone or unreadable now: the roots */ }
        }
        if (cancelled) return;
        setStartPath(start);
        setCurrentPath(start);
        setFiles(entries);
      } catch (e: any) {
        if (!cancelled) setError(`Could not list ${provider.label}: ${e?.message || e}`);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, provider, listAll]);

  const handleFolderChange = useCallback((path: string) => {
    setCurrentPath(path);
    setSelection([]);
    // remember it: the folders from the root down ("/a/b" -> /a, /a/b)
    const trail: BrowseItem[] = [];
    let prefix = '';
    for (const seg of path.split('/').slice(1)) {
      prefix += `/${seg}`;
      const folder = filesRef.current.find((f) => f.path === prefix);
      if (!folder) break;
      trail.push(folder.ref);
    }
    saveTrail(provider.key, trail);
    if (!path || loaded.current.has(path)) return;
    const folder = filesRef.current.find((f) => f.path === path);
    if (folder) loadChildren(folder);
  }, [loadChildren, provider]);

  const handleRefresh = useCallback(() => {
    const folder = filesRef.current.find((f) => f.path === currentPath);
    if (folder) {
      loadChildren(folder, true);
    } else if (!currentPath) {
      provider.roots().then((roots) => {
        setFiles(roots.map((r) => toEntry(r, '')));
        loaded.current = new Set(['']);
      });
    }
  }, [currentPath, loadChildren, provider]);

  const currentFolder = files.find((f) => f.path === currentPath);

  // why the selection can't be added (the source's config can't hold it), '' when it can
  const folderCount = selection.filter((s) => s.isDirectory).length;
  const selectionProblem =
    !allowFiles && selection.some((s) => !s.isDirectory) ? 'Pick a folder: this source takes a folder, not files.'
    : !multiple && selection.length > 1
      ? (allowFiles ? 'Pick one folder or file: this source takes a single path.'
        : 'Pick one folder: this source takes a single folder.')
    : !mixed && folderCount > 0 && selection.length > 1
      ? 'Pick one folder, or files only: this source takes a folder or a list of files.'
    : '';
  // the pick replaces what the form had (one folder / one list), rather than adding to it
  const replaces = !multiple || !mixed;

  const pick = (entries: FileItem[]) => {
    // by path: the component may hand back copies without our `ref`
    const byPath = new Map(files.map((f) => [f.path, f]));
    onSelect(entries.map((e) => byPath.get(e.path)?.ref).filter((r): r is BrowseItem => !!r));
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle>{title || `Browse ${provider.label}`}</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}</Alert>}
        <Box className={dark ? 'fg-browser fg-browser-dark' : 'fg-browser'} sx={{ color: dark ? '#e0e0e0' : 'black' }}>
          <FileManager
            files={files}
            isLoading={loading}
            permissions={NO_EDITING}
            enableFilePreview={false}
            layout="list"
            height="60vh"
            initialPath={startPath}
            primaryColor="#1976d2"
            onFolderChange={handleFolderChange}
            onSelectionChange={setSelection}
            onRefresh={handleRefresh}
            onFileOpen={() => { /* no preview: opening a file does nothing */ }}
          />
        </Box>
        <Typography variant="caption" sx={{ display: 'block', mt: 1, opacity: 0.7 }}>
          {!multiple && allowFiles
            ? 'Open a folder to see what is in it. Select one folder or file, or use the folder you are in.'
            : !mixed && allowFiles
            ? 'Open a folder to see what is in it. Select one folder or several files (Ctrl / Shift), or use the folder you are in.'
            : multiple || allowFiles
            ? 'Open a folder to see what is in it. Select files and folders (Ctrl / Shift for several), or add the folder you are in.'
            : 'Open a folder to see what is in it. Select a folder, or use the folder you are in.'}
        </Typography>
        {selectionProblem && (
          <Typography variant="caption" color="warning.main" sx={{ display: 'block' }}>{selectionProblem}</Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button disabled={!currentFolder} onClick={() => currentFolder && pick([currentFolder])}>
          {replaces ? 'Use this folder' : 'Add this folder'}
        </Button>
        <Button variant="contained" disabled={!selection.length || !!selectionProblem} onClick={() => pick(selection)}>
          {`${replaces ? 'Use' : 'Add'} selected${multiple && selection.length ? ` (${selection.length})` : ''}`}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
