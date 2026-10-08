import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  LinearProgress,
  Paper,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Checkbox,
  IconButton,
  Chip,
  Alert,
  FormControlLabel,
  Tabs,
  Tab,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import { Theme } from '@mui/material/styles';
import axios from 'axios';
import { 
  IngestRequest, 
  AsyncProcessingResponse, 
  ProcessingStatusResponse,
  FileDisplayInfo 
} from '../types/api';

// Sources with no auto change sync: the "Enable auto change sync" checkbox is hidden for them
const NO_AUTO_SYNC_SOURCES = ['upload', 'cmis', 'web', 'wikipedia', 'youtube'];

// What a row is in, or should end up in: Search+Vector, and Graphs (property graph + RDF).
interface RowStores {
  sv: boolean;
  graphs: boolean;
  sync: boolean;  // Auto Sync: kept up to date with repository changes
}
type ColumnKind = 'sv' | 'graphs' | 'sync';
type ItemActionKind = 'ingest' | 'ingest_no_graph' | 'remove_graph' | 'remove_all' | 'keep';
const TERMINAL_JOB = ['completed', 'failed', 'cancelled'];
// Job list refresh: often while a job runs, seldom when idle (still picks up auto sync runs)
const JOBS_BUSY_MS = 3000;
const JOBS_IDLE_MS = 15000;

// A file the server refused to store (unsupported extension, bad name, too large)
interface SkippedFile {
  filename: string;
  reason: string;
}

interface ProcessingTabProps {
  currentTheme: Theme;
  isDarkMode: boolean;
  hasConfiguredSources: boolean;
  configuredDataSource: string;
  configuredFiles: File[];
  folderPath: string;
  cmisConfig?: any;
  alfrescoConfig?: any;
  nuxeoConfig?: any;
  webConfig?: any;
  wikipediaConfig?: any;
  youtubeConfig?: any;
  cloudConfig?: any;
  enterpriseConfig?: any;
  selectedFileIndices: Set<number>;
  repositoryItemsHidden: boolean;
  configurationVersion?: number;  // bumped each time the Sources tab is applied
  // Persistent processing state
  isProcessing: boolean;
  processingStatus: string;
  processingProgress: number;
  currentProcessingId: string | null;
  statusData: any;
  lastStatusData: any;
  onGoToSources: () => void;
  onRemoveProcessingFile: (index: number) => void;
  onRemoveSelectedFiles?: () => void;  // unused: the REMOVE SELECTED button is gone
  onSelectAllFiles: (checked: boolean, totalFiles: number) => void;
  onSelectFile: (index: number, checked: boolean) => void;
  onConfiguredFilesChange: (files: File[]) => void;
  onProcessingStateChange: (isProcessing: boolean) => void;
  onProcessingStatusChange: (status: string) => void;
  onProcessingProgressChange: (progress: number) => void;
  onCurrentProcessingIdChange: (id: string | null) => void;
  onStatusDataChange: (data: any) => void;
  onLastStatusDataChange: (data: any) => void;
  successMessage: string;
  onSuccessMessage: (message: string) => void;
  onError: (message: string) => void;
}

export const ProcessingTab: React.FC<ProcessingTabProps> = ({
  currentTheme,
  isDarkMode,
  hasConfiguredSources,
  configuredDataSource,
  configuredFiles,
  folderPath,
  cmisConfig,
  alfrescoConfig,
  nuxeoConfig,
  webConfig,
  wikipediaConfig,
  youtubeConfig,
  cloudConfig,
  enterpriseConfig,
  selectedFileIndices,
  repositoryItemsHidden,
  configurationVersion = 0,
  isProcessing,
  processingStatus,
  processingProgress,
  currentProcessingId,
  statusData,
  lastStatusData,
  onGoToSources,
  onRemoveProcessingFile,
  onSelectAllFiles,
  onSelectFile,
  onConfiguredFilesChange,
  onProcessingStateChange,
  onProcessingStatusChange,
  onProcessingProgressChange,
  onCurrentProcessingIdChange,
  onStatusDataChange,
  onLastStatusDataChange,
  successMessage,
  onSuccessMessage,
  onError,
}) => {
  // Local UI state (only for state that doesn't need persistence)
  // Processing state now comes from props for persistence

  // Skip graph state
  const [skipGraph, setSkipGraph] = useState<boolean>(false);
  
  // Enable sync state (for incremental updates)
  const [enableSync, setEnableSync] = useState<boolean>(false);

  // File upload state
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // Debug state
  const [showDebugPanel, setShowDebugPanel] = useState<boolean>(false);

  // Ingest status of the current rows: auto sync or an earlier ingest (see the effect below)
  const [ingestStatus, setIngestStatus] = useState<any[]>([]);
  const ingestStatusKey = useRef('');
  const ingestStatusRequest = useRef<any>(null);  // the request behind `ingestStatus` (rows line up)
  const [ingestStatusRefresh, setIngestStatusRefresh] = useState<number>(0);
  // Which stores are configured; any can be "none" in .env (from the ingest-status response)
  const [stores, setStores] = useState<Record<string, boolean>>({});

  // What each row should end up in, by row name, once the user changed it (see wantFor)
  const [wantSearch, setWantSearch] = useState<Record<string, boolean>>({});
  const [wantGraphs, setWantGraphs] = useState<Record<string, boolean>>({});
  const [wantSync, setWantSync] = useState<Record<string, boolean>>({});
  // Run in the background: START returns at once and the job is followed on the Jobs sub-tab
  const [runInBackground, setRunInBackground] = useState<boolean>(false);
  const [subTab, setSubTab] = useState<number>(0);  // 0 Processing, 1 Jobs
  const [jobs, setJobs] = useState<any[]>([]);
  const watchedJobs = useRef<Set<string>>(new Set());  // background jobs started here
  const [watchedCount, setWatchedCount] = useState<number>(0);
  // Between the end of a run and the fresh ingest status: check nothing automatically
  const awaitingStatus = useRef(false);

  // File size formatting
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) {
      return bytes === 0 ? "0 B" : "1 KB";
    } else if (bytes < 1024 * 1024) {
      return `${Math.ceil(bytes / 1024)} KB`;
    } else {
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
  };

  // Phase display name
  const getPhaseDisplayName = (phase: string): string => {
    const phaseNames: { [key: string]: string } = {
      'ready': 'Ready',
      'waiting': 'Waiting',
      'loading': 'Loading',
      'loaded': 'Loaded',
      'cocoindex': 'Processing',
      'downloading': 'Downloading',
      'downloaded': 'Downloaded',
      'parsing': 'Parsing',
      'parsed': 'Parsed',
      'chunked': 'Chunked',
      'embedded': 'Embedded',
      'docling': 'Converting',
      'chunking': 'Chunking',
      'kg_extracting': 'Extracting Graph',
      'kg_extracted': 'Graph Extracted',
      'vector_indexing': 'Vector Index',
      'graph_indexing': 'Property Graph',
      'kg_extraction': 'Extracting Graph',
      'search_indexing': 'Search Index',
      'rdf_indexing': 'RDF Graph',
      'indexing_complete': 'Complete',
      'indexing': 'Indexing',
      'completed': 'Completed',
      'error': 'Error'
    };
    return phaseNames[phase] || phase;
  };

  // Generate file entries for display based on data source type
  const getDisplayFiles = (): FileDisplayInfo[] => {
    if (!hasConfiguredSources) return [];
    
    if (configuredDataSource === 'upload') {
      return configuredFiles.map(file => ({
        name: file.name,
        size: file.size,
        type: 'file' as const
      }));
    } else if (configuredDataSource === 'cmis' || configuredDataSource === 'alfresco' || configuredDataSource === 'nuxeo') {
      // If repository items are explicitly hidden, show nothing
      if (repositoryItemsHidden) {
        return [];
      }
      
      // The selection decides the rows, before, during and after a run. The backend's per-file
      // list used to replace them once a run started, so a folder row could turn into one of
      // its files (and stay that way), and the rows stopped lining up with the ingest status.
      // Progress for the folder row is the overall figure (getFileProgressData).
      return [{
        name: folderPath || 'Repository Path',
        size: 0,
        type: 'repository' as const
      }];
    } else if (configuredDataSource === 'web') {
      // Web page source
      const url = webConfig?.url || 'Web Page';
      return [{
        name: url,
        size: 0,
        type: 'web-source' as const
      }];
    } else if (configuredDataSource === 'wikipedia') {
      // Wikipedia source
      const query = wikipediaConfig?.query || wikipediaConfig?.url || 'Wikipedia Article';
      return [{
        name: `Wikipedia: ${query}`,
        size: 0,
        type: 'wikipedia-source' as const
      }];
    } else if (configuredDataSource === 'youtube') {
      // YouTube source
      const url = youtubeConfig?.url || 'YouTube Video';
      return [{
        name: url,
        size: 0,
        type: 'youtube-source' as const
      }];
    } else if (['s3', 'gcs', 'azure_blob', 'google_drive', 'onedrive', 'sharepoint', 'box'].includes(configuredDataSource)) {
      // Cloud storage sources
      const config = cloudConfig || enterpriseConfig;
      let displayName = 'Cloud Storage';
      
      if (configuredDataSource === 's3') {
        const bucket = config?.bucket_name || config?.bucket || 'Bucket';
        const prefix = config?.prefix || '';
        displayName = prefix ? `s3://${bucket}/${prefix}` : `s3://${bucket}`;
      } else if (configuredDataSource === 'gcs') {
        displayName = `GCS: ${config?.bucket || 'Bucket'}/${config?.prefix || ''}`;
      } else if (configuredDataSource === 'azure_blob') {
        displayName = `Azure: ${config?.container || 'Container'}/${config?.blob_name || ''}`;
      } else if (configuredDataSource === 'google_drive') {
        const folderId = config?.folder_id;
        displayName = folderId ? `Google Drive: ${folderId}` : 'Google Drive';
      } else if (configuredDataSource === 'onedrive') {
        displayName = `OneDrive: ${config?.folder_path || 'Folder'}`;
      } else if (configuredDataSource === 'sharepoint') {
        displayName = `SharePoint: ${config?.site_url || 'Site'}`;
      } else if (configuredDataSource === 'box') {
        displayName = `Box: ${config?.folder_id || 'Folder'}`;
      }
      
      // Check for individual files from status data (like CMIS/Alfresco)
      const individualFiles = (isProcessing || currentProcessingId) ? 
        (statusData?.individual_files || lastStatusData?.individual_files || []) : [];
      
      // If we have individual_files data, show it (this shows the single source entry with progress)
      if (individualFiles.length > 0) {
        return individualFiles.map((file: any, index: number) => {
          // Use the filename from status (should be the bucket/source path)
          const fileName = file.filename || displayName;
          
          return {
            name: fileName,
            size: 0,
            type: 'cloud-source' as const
          };
        });
      }
      
      // Default to cloud source path when no individual files yet
      return [{
        name: displayName,
        size: 0,
        type: 'cloud-source' as const
      }];
    }
    return [];
  };

  // ── Ingest status: which rows are already in the stores ──────────────────────────
  // An auto change sync covers them, or an earlier ingest put them there; they start
  // unchecked instead of being ingested again. Quietly nothing on an older backend.
  const looksLikeFile = (path: string): boolean =>
    /\.[A-Za-z0-9]{1,8}$/.test((path || '').split('/').pop() || '');

  const ingestStatusFor = (index: number): any | null => {
    // Rows and ingest status line up one-to-one, except after a run, when the rows can be the
    // backend's per-file list instead of the one path that was checked.
    if (ingestStatus.length !== getDisplayFiles().length) return null;
    const c = ingestStatus[index];
    return c && c.status !== 'none' ? c : null;
  };

  const ingestStatusLabel = (index: number): string => {
    const c = ingestStatusFor(index);
    const synced = !!c?.datasources?.some((m: any) => m.auto_sync && m.status === c.status);
    switch (c?.status) {
      case 'synced': return synced ? 'already synced' : 'already ingested';
      case 'partial': return synced ? 'synced, no subfolders' : 'ingested, no subfolders';
      case 'overlaps': return synced ? 'contains synced' : 'contains ingested';
      case 'removed': return 'removed';
      default: return '';
    }
  };

  const ingestStatusTooltip = (index: number): string => {
    const c = ingestStatusFor(index);
    if (!c) return '';
    const lines = c.datasources.map((m: any) => {
      const how = m.auto_sync ? 'synced by' : 'ingested (no auto sync) by';
      const what = m.relation === 'indexed' ? 'indexed by'
        : m.relation === 'contains' ? `contains ${m.root}, ${how}`
        : `${m.root}${m.recursive ? ' (with subfolders)' : ''}, ${how}`;
      return `${what} ${m.source_name || m.config_id}${m.skip_graph ? ' [no graph]' : ''}`;
    });
    if (c.indexed) {
      const where = ['vector', 'search', 'graph'].filter((t) => c.indexed[t]);
      lines.push(`in: ${where.join(', ') || 'none'}`);
    }
    lines.push(c.status === 'synced'
      ? 'Left unchecked. Check it, set Search+Vector / Graphs, and click START PROCESSING to update it.'
      : c.status === 'removed'
        ? 'Removed from the stores and kept out of its auto sync, even when it changes. Ingest it to put it back.'
        : 'Part of it is already in the stores; ingesting it again refreshes that part.');
    return lines.join('\n');
  };

  const showIngestStatus = (index: number): boolean =>
    !!ingestStatusFor(index) && !isProcessing && processingProgress === 0;

  const ingestedRowCount = getDisplayFiles()
    .filter((_, i) => ingestStatusFor(i)?.status === 'synced').length;

  // Uploaded files: rows by file name (the backend finds them under its upload directory)
  const uploadNames = configuredDataSource === 'upload' ? configuredFiles.map((f) => f.name).join('\n') : '';

  useEffect(() => {
    const repoConfig = configuredDataSource === 'alfresco' ? alfrescoConfig
      : configuredDataSource === 'nuxeo' ? nuxeoConfig : null;
    const isUpload = configuredDataSource === 'upload';
    if (!isUpload && configuredDataSource !== 'alfresco' && configuredDataSource !== 'nuxeo') {
      setIngestStatus([]);
      ingestStatusKey.current = '';
      return;
    }
    if (isUpload && !uploadNames) {
      setIngestStatus([]);
      ingestStatusKey.current = '';
      return;
    }
    if ((!isUpload && repositoryItemsHidden) || isProcessing) return;
    const path = repoConfig?.path || folderPath || '/';
    const request = isUpload
      ? { data_source: 'upload', recursive: false,
          items: uploadNames.split('\n').map((name) => ({ path: name, is_folder: false })) }
      : {
          data_source: configuredDataSource,
          url: repoConfig?.url,
          recursive: !!repoConfig?.recursive,
          items: [{ path, is_folder: !looksLikeFile(path) }],
        };
    // configurationVersion in the key: re-applying the same configuration (e.g. after a run
    // that just ingested it) must ask again, or the answer from before that run is reused.
    const key = JSON.stringify(request) + '#' + configurationVersion + '#' + ingestStatusRefresh;
    if (key === ingestStatusKey.current) return;
    ingestStatusKey.current = key;
    ingestStatusRequest.current = request;
    setIngestStatus([]);
    axios.post('/api/sync/ingest-status', request)
      .then((res) => {
        if (key !== ingestStatusKey.current) return;  // configuration changed while in flight
        const items = res.data?.enabled ? res.data.items : [];
        setIngestStatus(items);
        setStores(res.data?.stores || {});
        // uncheck rows already in the stores
        items.forEach((c: any, i: number) => {
          if (c?.status === 'synced' && selectedFileIndices.has(i)) onSelectFile(i, false);
        });
      })
      .catch((err) => console.warn('Ingest status check unavailable:', err));
  }, [configuredDataSource, alfrescoConfig, nuxeoConfig, folderPath, repositoryItemsHidden,
      isProcessing, currentProcessingId, configurationVersion, ingestStatusRefresh, uploadNames]);

  // Auto Sync only for repository sources (uploads are not kept in sync)
  const showAutoSync = configuredDataSource !== 'upload';

  // ── Search+Vector / Graphs columns ──────────────────────────────────────────────────
  // Offered once the ingest-status check answered with `stores` (a 0.8.2 backend has none).
  const columnsMode = ingestStatus.length > 0 && ingestStatusRequest.current !== null && Object.keys(stores).length > 0;
  const canSearchVector = !!(stores.vector || stores.search);
  const canGraphs = !!stores.graph;
  const inStores = (index: number): boolean =>
    ['synced', 'partial', 'overlaps'].includes(ingestStatusFor(index)?.status);

  /** What a row is in now, from the ingest status. */
  const currentFor = (index: number): RowStores => {
    const c = ingestStatusFor(index);
    const sync = !!c?.auto_sync;
    if (!c || !inStores(index)) return { sv: false, graphs: false, sync };
    if (c.indexed) return { sv: !!(c.indexed.vector || c.indexed.search), graphs: !!c.indexed.graph, sync };
    return { sv: true, graphs: (c.datasources || []).some((m: any) => !m.skip_graph), sync };
  };

  /** Whether an auto sync already covers the row (so Auto Sync on resumes, not starts, it). */
  const coveredBySync = (index: number): boolean =>
    !!(ingestStatusFor(index)?.datasources || []).some((m: any) => m.auto_sync);

  /** What a row should end up in: the user's choice, else what it is in now, else everything. */
  const wantFor = (index: number): RowStores => {
    const name = getDisplayFiles()[index]?.name;
    const cur = currentFor(index);
    const fresh = !inStores(index);
    const sv = wantSearch[name] ?? (fresh ? canSearchVector : cur.sv);
    const graphs = wantGraphs[name] ?? (fresh ? canGraphs : cur.graphs);
    const sync = wantSync[name] ?? cur.sync;
    // Graphs and Auto Sync both need Search+Vector: a sync with nothing indexed would only
    // put the document back on its next change
    return { sv, graphs: sv && graphs, sync: sv && sync };
  };

  /** Changing a row's Search+Vector / Graphs checks the row: START PROCESSING applies it. */
  const setWant = (indices: number[], kind: ColumnKind, value: boolean) => {
    const names = indices.map((i) => getDisplayFiles()[i]?.name).filter(Boolean);
    const all = (v: boolean) => (w: Record<string, boolean>) => ({ ...w, ...Object.fromEntries(names.map((n) => [n, v])) });
    if (kind === 'sv') {
      setWantSearch(all(value));
      if (!value) {  // no graphs and no sync without search + vector
        setWantGraphs(all(false));
        setWantSync(all(false));
      }
    } else if (kind === 'graphs') {
      setWantGraphs(all(value));
      if (value) setWantSearch(all(true));
    } else {
      setWantSync(all(value));
      if (value) setWantSearch(all(true));
    }
    indices.forEach((i) => { if (!selectedFileIndices.has(i)) onSelectFile(i, true); });
  };
  const allRows = (): number[] => getDisplayFiles().map((_, i) => i);
  const countWant = (kind: ColumnKind): number => allRows().filter((i) => wantFor(i)[kind]).length;

  /** What START PROCESSING does with a checked row, or null when there is nothing to do. */
  const actionFor = (index: number): ItemActionKind | null => {
    const cur = currentFor(index);
    const want = wantFor(index);
    if (!want.sv) return cur.sv || cur.graphs ? 'remove_all' : null;
    if (want.graphs) return 'ingest';
    return cur.sv && cur.graphs ? 'remove_graph' : 'ingest_no_graph';
  };

  /** The Status column in columns mode: which stores the row is in now. */
  const storesLabel = (index: number): string => {
    const c = ingestStatusFor(index);
    if (c?.status === 'removed') return 'removed';
    const cur = currentFor(index);
    if (!cur.sv && !cur.graphs) return 'not ingested';
    return (cur.graphs ? 'search+vector, graphs' : 'search+vector') + (cur.sync ? ' (synced)' : '');
  };

  /** A sync change for a checked row: false stops it, true resumes it, null = none. */
  const syncChange = (index: number): boolean | null => {
    const want = wantFor(index).sync;
    return want !== currentFor(index).sync ? want : null;
  };

  /**
   * What START PROCESSING sends for the checked rows: per row a store action and/or an Auto
   * Sync change. A row no sync covers yet, with Auto Sync checked, is ingested with
   * auto_sync: true: the backend makes this run\'s datasource an auto sync watching it.
   */
  const itemActions = () => {
    const base = ingestStatusRequest.current;
    const rows: any[] = [];
    for (const i of Array.from(selectedFileIndices).sort((a, b) => a - b)) {
      const item = base?.items?.[i];
      if (!item) continue;
      const ref = { path: item.path, id: item.id, is_folder: !!item.is_folder };
      const sync = syncChange(i);
      if (sync === true && !coveredBySync(i)) {
        rows.push({ ...ref, action: actionFor(i) ?? (wantFor(i).graphs ? 'ingest' : 'ingest_no_graph'), auto_sync: true });
        continue;
      }
      const action = actionFor(i);
      if (!action && sync === null) continue;
      rows.push({ ...ref, action: action ?? 'keep', ...(sync === null ? {} : { auto_sync: sync }) });
    }
    return rows;
  };

  /**
   * A run is over. The rows' choices go back to their defaults -- rows in the stores unchecked,
   * columns showing what each row is in now -- so a second START does not repeat the run. The
   * ingest status is asked again once the run's document_state rows are written.
   */
  const afterRun = () => {
    setWantSearch({});
    setWantGraphs({});
    setWantSync({});
    awaitingStatus.current = true;
    allRows().forEach((i) => { if (selectedFileIndices.has(i)) onSelectFile(i, false); });
    setTimeout(() => {
      awaitingStatus.current = false;
      setIngestStatusRefresh((n) => n + 1);
    }, 4000);
  };

  const wasProcessing = useRef(false);
  useEffect(() => {
    if (wasProcessing.current && !isProcessing) afterRun();
    wasProcessing.current = isProcessing;
  }, [isProcessing]);

  // ── Jobs sub-tab ────────────────────────────────────────────────────────────────────
  const showFinishedJob = async (job: any) => {
    if (!isProcessing) {
      try {
        const res = await axios.get(`/api/processing-status/${job.processing_id}`);
        const status = res.data;
        onStatusDataChange(null);
        onLastStatusDataChange(status);
        onProcessingProgressChange(status.status === 'completed' ? 100 : status.progress || 0);
        if (status.status === 'completed') onSuccessMessage(status.message || 'Background job finished.');
        else onError(`Background job ${status.status}: ${status.error || status.message || ''}`);
      } catch { /* the job may have been cleared */ }
    }
    afterRun();
  };

  const loadJobs = async (): Promise<any[]> => {
    try {
      const res = await axios.get('/api/processing-status');
      const list = res.data?.jobs || [];
      setJobs(list);
      for (const job of list) {
        if (watchedJobs.current.has(job.processing_id) && TERMINAL_JOB.includes(job.status)) {
          watchedJobs.current.delete(job.processing_id);
          setWatchedCount(watchedJobs.current.size);
          showFinishedJob(job);
        }
      }
      return list;
    } catch (err) {
      console.warn('Job list unavailable:', err);
      return [];
    }
  };

  // Refresh the job list while it is shown or a background job started here is still going:
  // every 3 s while a job runs, every 15 s when none does
  useEffect(() => {
    if (subTab !== 1 && watchedCount === 0) return;
    let timer: any = null;
    let stopped = false;
    const tick = async () => {
      const list = await loadJobs();
      if (stopped) return;
      const busy = watchedJobs.current.size > 0 || list.some((j) => !TERMINAL_JOB.includes(j.status));
      timer = setTimeout(tick, busy ? JOBS_BUSY_MS : JOBS_IDLE_MS);
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [subTab, watchedCount]);

  const clearJobs = async () => {
    try {
      await axios.delete('/api/processing-status');
    } catch (err: any) {
      onError(`Clear failed: ${err?.response?.data?.detail || err?.message || err}`);
    }
    loadJobs();
  };

  const cancelJob = async (job: any) => {
    try {
      await axios.post(`/api/cancel-processing/${job.processing_id}`, {});
    } catch (err: any) {
      onError(`Cancel failed: ${err?.response?.data?.detail || err?.message || err}`);
    }
    loadJobs();
  };

  const jobRunning = (job: any): boolean => !TERMINAL_JOB.includes(job.status);
  const runningJobCount = jobs.filter(jobRunning).length;

  // A new selection opens on the Processing sub-tab
  useEffect(() => {
    setSubTab(0);
    setWantSearch({});
    setWantGraphs({});
    setWantSync({});
  }, [configurationVersion]);

  // Get file progress data
  const getFileProgressData = (filename: string) => {
    // For repository path placeholder, use overall progress
    const folderName = folderPath.split(/[/\\]/).pop() || folderPath;
    if (filename === folderName || filename === folderPath) {
      return {
        status: isProcessing ? 'processing' : (processingProgress === 100 ? 'completed' : 'ready'),
        progress: processingProgress,
        phase: isProcessing ? 'processing' : (processingProgress === 100 ? 'completed' : 'ready')
      };
    }
    
    const files = statusData?.individual_files || lastStatusData?.individual_files || [];
    
    if (import.meta.env.DEV && files.length > 0) {
      console.log('🔍 Looking for progress data for:', filename);
      console.log('📋 Available progress files:', files.map((f: any) => f.filename));
      console.log('📁 Current display files:', getDisplayFiles().map(f => f.name));
    }
    
    let match = files.find((file: any) => file.filename === filename);
    if (!match) {
      match = files.find((file: any) => {
        const fileBasename = file.filename?.split(/[/\\]/).pop();
        return fileBasename === filename;
      });
    }
    if (!match) {
      match = files.find((file: any) => 
        file.filename?.includes(filename) || filename.includes(file.filename)
      );
    }
    
    if (import.meta.env.DEV) {
      console.log('✅ Progress match for', filename, ':', match ? `Found (${match.progress}% - ${match.phase})` : 'NOT FOUND');
    }
    
    // If no match found but processing is completed, return completed status
    if (!match && !isProcessing && processingProgress === 100) {
      return {
        status: 'completed',
        progress: 100,
        phase: 'completed'
      };
    }
    
    return match;
  };

  // Polling function for processing status
  const pollProcessingStatus = useCallback(async (processingId: string) => {
    try {
      const response = await axios.get<ProcessingStatusResponse>(`/api/processing-status/${processingId}`);
      const status = response.data;
      
      onProcessingStatusChange(status.message);
      onProcessingProgressChange(status.progress);
      onStatusDataChange(status);
      onLastStatusDataChange(status);
      
      console.log('Processing status data:', status);
      localStorage.setItem('lastProcessingStatus', JSON.stringify(status));
      
      if (status.status === 'completed') {
        console.log('FINAL STATUS (COMPLETED):', JSON.stringify(status, null, 2));
        console.log('Individual files data:', status.individual_files);
        onProcessingStateChange(false);
        onProcessingStatusChange(status.message || 'Processing completed');
        onProcessingProgressChange(100); // Keep at 100% to show completion
        onCurrentProcessingIdChange(null);
        onSuccessMessage(status.message || 'Documents ingested successfully!');
      } else if (status.status === 'failed') {
        onProcessingStateChange(false);
        onProcessingStatusChange('');
        onProcessingProgressChange(0);
        onCurrentProcessingIdChange(null);
        onError(status.error || 'Processing failed');
      } else if (status.status === 'cancelled') {
        onProcessingStateChange(false);
        onProcessingStatusChange('Processing cancelled');
        onProcessingProgressChange(0); // 0% for cancelled
        onCurrentProcessingIdChange(null);
        onSuccessMessage('Processing cancelled successfully');
      } else if (status.status === 'started' || status.status === 'processing') {
        setTimeout(() => pollProcessingStatus(processingId), 2000);
      }
    } catch (err) {
      console.error('Error checking processing status:', err);
      onError('Error checking processing status');
      onProcessingStateChange(false);
      onCurrentProcessingIdChange(null);
    }
  }, []);

  // Cancel processing
  const cancelProcessing = async (): Promise<void> => {
    if (!currentProcessingId) return;
    
    try {
      const response = await axios.post(`/api/cancel-processing/${currentProcessingId}`, {});
      
      if (response.data.success) {
        // Success will be handled by the polling status check
      } else {
        onError('Failed to cancel processing');
      }
    } catch (err) {
      console.error('Error cancelling processing:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error cancelling processing'
        : 'An unknown error occurred';
      onError(errorMessage);
    }
  };

  const formatSkipped = (skipped: SkippedFile[]): string =>
    skipped.map(file => `${file.filename}: ${file.reason}`).join('\n');

  // Upload files (for upload data source)
  const uploadFiles = async (): Promise<{ paths: string[]; skipped: SkippedFile[] }> => {
    if (configuredFiles.length === 0) return { paths: [], skipped: [] };
    
    setIsUploading(true);
    setUploadProgress(0);
    
    try {
      const formData = new FormData();
      configuredFiles.forEach(file => {
        formData.append('files', file);
      });
      
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(progress);
          }
        },
      });
      
      if (response.data.success) {
        // Skipped files are returned rather than reported here: only the caller knows
        // whether anything survived, and "all skipped" needs a different message than
        // "some skipped".
        const skipped: SkippedFile[] = response.data.skipped || [];

        // Update configured files with the saved filenames for progress matching
        const uploadedFiles = response.data.files.map((uploadedFile: any) => {
          // Find the original file and create a new file object with the saved filename
          const originalFile = configuredFiles.find((f: File) => f.name === uploadedFile.filename);
          if (originalFile) {
            // Create a new File object with the saved filename
            return new File([originalFile], uploadedFile.saved_as, { type: originalFile.type });
          }
          return originalFile;
        }).filter(Boolean);
        
        // Update the parent's configured files
        onConfiguredFilesChange(uploadedFiles);
        
        return { paths: response.data.files.map((file: any) => file.path), skipped };
      } else {
        throw new Error('Upload failed');
      }
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  // Process documents
  const processDocuments = async (): Promise<void> => {
    if (!hasFilesToProcess() || isProcessing) return;
    
    try {
      onProcessingStateChange(true);
      onStatusDataChange(null);
      onLastStatusDataChange(null);
      
      const request: IngestRequest = {
        data_source: configuredDataSource
      };

      // Search+Vector / Graphs columns: each checked row says what it should end up as
      const planned = columnsMode ? itemActions() : null;
      const actions = planned;
      if (planned && planned.length === 0) {
        onSuccessMessage('Nothing to do: the checked rows already match their Search+Vector / Graphs settings.');
        onProcessingStateChange(false);
        return;
      }
      if (planned) {
        (request as any).item_actions = actions;
      } else if (skipGraph) {
        request.skip_graph = true;
        console.log('✓ skip_graph flag set to true - Knowledge graph extraction will be skipped');
      }
      
      // Add enable_sync flag if checked
      // Only for a source that shows the checkbox: the value survives switching sources, so
      // a sync left ticked on Alfresco would otherwise make a later upload a live sync too.
      if (!planned && enableSync && !NO_AUTO_SYNC_SOURCES.includes(configuredDataSource)) {
        request.enable_sync = true;
        console.log('✓ enable_sync flag set to true - Incremental updates will be enabled');
      }

      if (configuredDataSource === 'upload') {
        const { paths: uploadedPaths, skipped } = await uploadFiles();

        // Nothing survived the upload (e.g. every file had an unsupported extension).
        // Stop here: posting paths: [] starts a job that can only fail, and its "failed"
        // status then overwrites the skip reasons the user actually needs to read.
        if (uploadedPaths.length === 0) {
          onError(
            skipped.length > 0
              ? `No files could be uploaded:\n${formatSkipped(skipped)}`
              : 'No files could be uploaded'
          );
          onProcessingStateChange(false);
          return;
        }

        if (skipped.length > 0) {
          onError(`Some files were skipped:\n${formatSkipped(skipped)}`);
        }

        request.paths = uploadedPaths;
        request.data_source = 'filesystem';
      } else if (configuredDataSource === 'cmis') {
        request.paths = [folderPath];
        request.cmis_config = cmisConfig;
      } else if (configuredDataSource === 'alfresco') {
        request.paths = [folderPath];
        request.alfresco_config = alfrescoConfig;
      } else if (configuredDataSource === 'nuxeo') {
        request.nuxeo_config = nuxeoConfig;
      } else if (configuredDataSource === 'web') {
        request.web_config = webConfig;
      } else if (configuredDataSource === 'wikipedia') {
        request.wikipedia_config = wikipediaConfig;
      } else if (configuredDataSource === 'youtube') {
        console.log('YouTube config:', youtubeConfig);
        request.youtube_config = youtubeConfig;
      } else if (['s3', 'gcs', 'azure_blob'].includes(configuredDataSource)) {
        // Cloud storage sources - strip the 'type' field before sending
        const { type, ...cleanConfig } = cloudConfig || {};
        if (configuredDataSource === 's3') {
          request.s3_config = cleanConfig;
        } else if (configuredDataSource === 'gcs') {
          request.gcs_config = cleanConfig;
        } else if (configuredDataSource === 'azure_blob') {
          request.azure_blob_config = cleanConfig;
        }
      } else if (['onedrive', 'sharepoint', 'box', 'google_drive'].includes(configuredDataSource)) {
        // Enterprise sources - strip the 'type' field before sending
        const { type, ...cleanConfig } = enterpriseConfig || {};
        if (configuredDataSource === 'onedrive') {
          request.onedrive_config = cleanConfig;
        } else if (configuredDataSource === 'sharepoint') {
          request.sharepoint_config = cleanConfig;
        } else if (configuredDataSource === 'box') {
          request.box_config = cleanConfig;
        } else if (configuredDataSource === 'google_drive') {
          request.google_drive_config = cleanConfig;
        }
      }


      const response = await axios.post<AsyncProcessingResponse>('/api/ingest', request);
      
      if (response.data.status === 'started' && runInBackground) {
        // The job carries on in the backend; this tab is free to start another one
        watchedJobs.current.add(response.data.processing_id);
        setWatchedCount(watchedJobs.current.size);
        wasProcessing.current = false;  // not a foreground run: no reset when the flag drops
        onProcessingStateChange(false);
        onSuccessMessage(`Started in the background (job ${response.data.processing_id}). Follow it on the Jobs tab.`);
      } else if (response.data.status === 'started') {
        onProcessingStatusChange(response.data.message);
        onProcessingProgressChange(0);
        onCurrentProcessingIdChange(response.data.processing_id);
        onSuccessMessage(`Processing started: ${response.data.estimated_time || 'Please wait...'}`);
        setTimeout(() => pollProcessingStatus(response.data.processing_id), 2000);
      } else if (response.data.status === 'completed') {
        onProcessingStateChange(false);
        onProcessingStatusChange('Processing completed');
        onProcessingProgressChange(100); // Keep at 100% to show completion
        onSuccessMessage('Documents ingested successfully!');
      } else if (response.data.status === 'failed') {
        onProcessingStateChange(false);
        onError(response.data.error || 'Processing failed');
      }
    } catch (err) {
      console.error('Error processing documents:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error processing documents'
        : 'An unknown error occurred';
      onError(errorMessage);
      onProcessingStateChange(false);
      onCurrentProcessingIdChange(null);
    }
  };

  // Check if there are files ready to process
  const hasFilesToProcess = (): boolean => {
    if (!hasConfiguredSources) return false;
    
    if (configuredDataSource === 'upload') {
      return selectedFileIndices.size > 0 && configuredFiles.length > 0;
    } else {
      const displayFiles = getDisplayFiles();
      return displayFiles.length === 0 || selectedFileIndices.size > 0;
    }
  };

  // File table management - now using prop handlers
  const handleSelectAllFiles = (checked: boolean) => {
    onSelectAllFiles(checked, getDisplayFiles().length);
  };

  const handleSelectFile = (index: number, checked: boolean) => {
    onSelectFile(index, checked);
  };

  const removeProcessingFile = (index: number) => {
    onRemoveProcessingFile(index);
  };

  // Auto-select files when they are configured for single-source data types.
  // Applied only when the rows themselves (or their ingest status) change -- NOT on every selection
  // change: that re-ran this on each click and forced the selection straight back, so a row
  // left unchecked as "already ingested" could never be checked to ingest it again.
  const autoSelectKey = useRef('');
  useEffect(() => {
    if (configuredDataSource === 'cmis' || configuredDataSource === 'alfresco' || configuredDataSource === 'nuxeo' ||
        configuredDataSource === 'web' || configuredDataSource === 'wikipedia' ||
        configuredDataSource === 'youtube' ||
        ['s3', 'gcs', 'azure_blob', 'google_drive', 'onedrive', 'sharepoint', 'box'].includes(configuredDataSource)) {
      if (awaitingStatus.current) return;  // a run just ended: wait for the fresh ingest status
      const displayFiles = getDisplayFiles();
      const rowsKey = JSON.stringify([
        configuredDataSource, configurationVersion, displayFiles.map((f) => f.name),
        ingestStatus.map((c: any) => c?.status),
      ]);
      if (rowsKey === autoSelectKey.current) return;
      autoSelectKey.current = rowsKey;
      // Auto-select all files (both repository path and individual files when discovered),
      // except rows already in the stores (see the ingest-status effect)
      const newSelection = new Set<number>();
      displayFiles.forEach((_, index) => {
        if (ingestStatusFor(index)?.status !== 'synced') newSelection.add(index);
      });
      
      // Only update if selection has actually changed
      const currentSelection = Array.from(selectedFileIndices).sort();
      const newSelectionArray = Array.from(newSelection).sort();
      const hasChanged = currentSelection.length !== newSelectionArray.length || 
                        currentSelection.some((val, idx) => val !== newSelectionArray[idx]);
      
      if (hasChanged) {
        // Update selection by calling the individual select handlers
        // First clear all selections
        const currentFiles = getDisplayFiles();
        for (let i = 0; i < currentFiles.length; i++) {
          if (selectedFileIndices.has(i) && !newSelection.has(i)) {
            onSelectFile(i, false);
          }
        }
        // Then add new selections
        for (const index of newSelection) {
          if (!selectedFileIndices.has(index)) {
            onSelectFile(index, true);
          }
        }
      }
    }
  }, [statusData, lastStatusData, configuredDataSource, selectedFileIndices, onSelectFile, ingestStatus,
      configurationVersion]);

  // Note: File selection is now handled by parent component

  return (
    <Box sx={{ p: 3 }}>
      <Tabs value={subTab} onChange={(_, v) => setSubTab(v)} sx={{ mb: 2 }}>
        <Tab label="Processing" />
        <Tab label={runningJobCount ? `Jobs (${runningJobCount} running)` : 'Jobs'} />
      </Tabs>
      {subTab === 0 && (<>
      {/* Header with Skip Graph Checkbox */}
      <Box sx={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        mb: 3 
      }}>
        <Typography variant="h6">
          File Processing
        </Typography>
        {!columnsMode && (
        <FormControlLabel
          control={
            <Checkbox
              checked={skipGraph}
              onChange={(e) => setSkipGraph(e.target.checked)}
              disabled={isProcessing}
            />
          }
          label="Skip graph (search + vector only)"
        />
        )}
        {/* Only show Enable Sync for datasources that support auto-sync */}
        {/* Hidden for: upload, cmis, webpage, wikipedia, youtube */}
        {!columnsMode &&
         configuredDataSource !== 'upload' &&
         configuredDataSource !== 'cmis' &&
         configuredDataSource !== 'web' &&
         configuredDataSource !== 'wikipedia' &&
         configuredDataSource !== 'youtube' && (
          <FormControlLabel
            control={
              <Checkbox
                checked={enableSync}
                onChange={(e) => setEnableSync(e.target.checked)}
                disabled={isProcessing}
              />
            }
            label="Enable auto change sync"
          />
        )}
      </Box>
      
      {/* Show prompt only when not configured */}
      {!hasConfiguredSources && (
        <Paper sx={{ 
          p: 3, 
          mb: 3, 
          textAlign: 'center', 
          bgcolor: isDarkMode ? '#2d2d2d' : currentTheme.palette.primary.light, 
          border: `1px solid ${currentTheme.palette.primary.main}` 
        }}>
          <Typography variant="h6" sx={{ color: currentTheme.palette.text.primary, fontWeight: 600 }} gutterBottom>
            No Data Source Configured
          </Typography>
          <Typography variant="body2" sx={{ color: currentTheme.palette.text.secondary, mb: 2 }}>
            Please go to the Sources tab to configure your data source first.
          </Typography>
          <Button
            variant="outlined"
            onClick={onGoToSources}
            color="primary"
          >
            ← Go to Sources
          </Button>
        </Paper>
      )}
      
      {/* File Table - Show for all configured sources */}
      {hasConfiguredSources && ingestedRowCount > 0 && !isProcessing && processingProgress === 0 && (
        <Typography variant="body2" sx={{ mb: 1, opacity: 0.8 }}>
          {ingestedRowCount} of {getDisplayFiles().length} already in the stores, so left unchecked.
          {columnsMode
            ? ' Check rows, set Search+Vector / Graphs, and click START PROCESSING to update them.'
            : ' Check rows and click START PROCESSING to update them.'}
          Hover the status for details.
        </Typography>
      )}

      {hasConfiguredSources && (
        <TableContainer component={Paper} sx={{ mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" sx={{ width: 50 }}>
                  <Checkbox
                    indeterminate={selectedFileIndices.size > 0 && selectedFileIndices.size < getDisplayFiles().length}
                    checked={getDisplayFiles().length > 0 && selectedFileIndices.size === getDisplayFiles().length}
                    onChange={(e) => handleSelectAllFiles(e.target.checked)}
                  />
                </TableCell>
                <TableCell sx={{ width: 200 }}>Filename</TableCell>
                <TableCell sx={{ width: 100 }}>File Size</TableCell>
                <TableCell sx={{ minWidth: 400 }}>Progress</TableCell>
                {columnsMode && (
                  <TableCell padding="checkbox" sx={{ whiteSpace: 'nowrap', pr: 2 }} title="Vector and full-text search stores, for every row">
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Checkbox
                        // the cell strips its direct child's padding; this one sits in a Box,
                        // so drop it here too or it sits 9px right of the row checkboxes
                        sx={{ p: 0, mr: 1 }}
                        checked={countWant('sv') === getDisplayFiles().length && getDisplayFiles().length > 0}
                        indeterminate={countWant('sv') > 0 && countWant('sv') < getDisplayFiles().length}
                        disabled={isProcessing || !canSearchVector}
                        onChange={(e) => setWant(allRows(), 'sv', e.target.checked)}
                      />
                      Search+Vector
                    </Box>
                  </TableCell>
                )}
                {columnsMode && (
                  <TableCell padding="checkbox" sx={{ whiteSpace: 'nowrap', pr: 2 }} title={canGraphs ? 'Property graph and RDF, for every row' : 'No graph store configured in .env'}>
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Checkbox
                        // the cell strips its direct child's padding; this one sits in a Box,
                        // so drop it here too or it sits 9px right of the row checkboxes
                        sx={{ p: 0, mr: 1 }}
                        checked={countWant('graphs') === getDisplayFiles().length && getDisplayFiles().length > 0}
                        indeterminate={countWant('graphs') > 0 && countWant('graphs') < getDisplayFiles().length}
                        disabled={isProcessing || !canGraphs}
                        onChange={(e) => setWant(allRows(), 'graphs', e.target.checked)}
                      />
                      Graphs
                    </Box>
                  </TableCell>
                )}
                {columnsMode && showAutoSync && (
                  <TableCell padding="checkbox" sx={{ whiteSpace: 'nowrap', pr: 2 }} title="Keep every row up to date with repository changes">
                    <Box sx={{ display: 'flex', alignItems: 'center' }}>
                      <Checkbox
                        sx={{ p: 0, mr: 1 }}
                        checked={countWant('sync') === getDisplayFiles().length && getDisplayFiles().length > 0}
                        indeterminate={countWant('sync') > 0 && countWant('sync') < getDisplayFiles().length}
                        disabled={isProcessing}
                        onChange={(e) => setWant(allRows(), 'sync', e.target.checked)}
                      />
                      Auto Sync
                    </Box>
                  </TableCell>
                )}
                <TableCell sx={{ width: 50 }}></TableCell>
                <TableCell sx={{ width: 100 }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {getDisplayFiles().map((file, index) => {
                const progressData = getFileProgressData(file.name);
                const isSelected = selectedFileIndices.has(index);
                
                return (
                  <TableRow key={index} selected={isSelected}>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={isSelected}
                        onChange={(e) => handleSelectFile(index, e.target.checked)}
                      />
                    </TableCell>
                    <TableCell sx={{ width: '30%' }}>
                      <Typography 
                        variant="body2" 
                        title={file.name}
                        sx={{ 
                          wordBreak: 'break-all', 
                          lineHeight: 1.2,
                          whiteSpace: 'normal'
                        }}
                      >
                        {file.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {file.size > 0 ? formatFileSize(file.size) : 
                         file.type === 'path' ? 'Folder' : 
                         file.type === 'repository' ? 'Repository' : '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                        <Box sx={{ flex: 1, mr: 1 }}>
                          <Box
                            sx={{
                              width: '100%',
                              height: 8,
                              borderRadius: 4,
                              backgroundColor: currentTheme.palette.action.hover,
                              position: 'relative',
                              overflow: 'hidden'
                            }}
                          >
                            <Box
                              sx={{
                                width: `${Math.max(progressData?.progress || 0, 2)}%`,
                                height: '100%',
                                backgroundColor: currentTheme.palette.primary.main,
                                borderRadius: 4,
                                transition: 'width 0.3s ease'
                              }}
                            />
                          </Box>
                        </Box>
                        <Typography variant="caption" sx={{ flex: 'none', whiteSpace: 'nowrap', color: currentTheme.palette.text.primary }}>
                          {progressData?.progress || 0}% - {getPhaseDisplayName(progressData?.phase || 'ready')}
                        </Typography>
                      </Box>
                    </TableCell>
                    {columnsMode && (
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={wantFor(index).sv}
                          disabled={isProcessing || !canSearchVector}
                          onChange={(e) => setWant([index], 'sv', e.target.checked)}
                        />
                      </TableCell>
                    )}
                    {columnsMode && (
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={wantFor(index).graphs}
                          disabled={isProcessing || !canGraphs}
                          onChange={(e) => setWant([index], 'graphs', e.target.checked)}
                        />
                      </TableCell>
                    )}
                    {columnsMode && showAutoSync && (
                      <TableCell padding="checkbox">
                        <Checkbox
                          checked={wantFor(index).sync}
                          disabled={isProcessing}
                          onChange={(e) => setWant([index], 'sync', e.target.checked)}
                          title="Unchecking stops this row's auto sync; for a datasource's own root it also stops watching it"
                        />
                      </TableCell>
                    )}
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>
                      <IconButton
                        size="small"
                        onClick={() => removeProcessingFile(index)}
                        color="error"
                        title="Take this row off the list (the stores are not touched)"
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                    <TableCell>
                      {columnsMode && !isProcessing && processingProgress === 0 ? (
                        // Before a run: which stores the row is in now
                        <Chip
                          label={storesLabel(index)}
                          size="small"
                          variant="outlined"
                          color={inStores(index) ? 'info' : 'default'}
                          title={ingestStatusTooltip(index)}
                          sx={{ cursor: 'help' }}
                        />
                      ) : showIngestStatus(index) ? (
                        // Before a run: say when this row is already in the stores
                        <Chip
                          label={ingestStatusLabel(index)}
                          size="small"
                          variant="outlined"
                          color={ingestStatusFor(index)?.status === 'synced' ? 'info' : 'warning'}
                          title={ingestStatusTooltip(index)}
                          sx={{ cursor: 'help' }}
                        />
                      ) : (
                        <Chip
                          label={progressData?.status || 'ready'}
                          size="small"
                          color={
                            progressData?.status === 'completed' ? 'success' :
                            progressData?.status === 'failed' ? 'error' :
                            progressData?.status === 'processing' ? 'primary' : 'default'
                          }
                        />
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      
      {/* Upload Progress */}
      {isUploading && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" gutterBottom>
            Uploading files... {uploadProgress}%
          </Typography>
          <LinearProgress variant="determinate" value={uploadProgress} />
        </Box>
      )}
      
      {/* Processing Status */}
      {isProcessing && (
        <Box sx={{ mb: 2 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Box display="flex" alignItems="center">
              <CircularProgress size={20} sx={{ mr: 1 }} />
              <Typography variant="body2">
                {processingStatus || 'Processing documents...'}
              </Typography>
            </Box>
            <Button 
              variant="outlined" 
              color="error" 
              size="small" 
              onClick={cancelProcessing}
              disabled={!currentProcessingId}
            >
              Cancel
            </Button>
          </Box>
          
          <Box sx={{ mb: 2 }}>
            <LinearProgress 
              variant="determinate" 
              value={processingProgress} 
              sx={{ mb: 1 }} 
            />
            <Typography variant="caption" color="text.secondary">
              Overall Progress: {processingProgress}% complete
              {statusData?.estimated_time_remaining && (
                <span> • Est. time remaining: {statusData.estimated_time_remaining}</span>
              )}
            </Typography>
          </Box>
        </Box>
      )}
      
      {/* Action Buttons */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        <Button
          variant="contained"
          onClick={processDocuments}
          disabled={!hasConfiguredSources || isProcessing || !hasFilesToProcess()}
          sx={{ minWidth: 200 }}
        >
          {isProcessing ? 'Processing...' : 
           !hasConfiguredSources ? 'Configure Sources First' :
           !hasFilesToProcess() ? 'Select Files to Process' :
           'Start Processing'}
        </Button>

        <FormControlLabel
          title="Start the job and keep this tab free; follow it on the Jobs tab"
          control={
            <Checkbox
              checked={runInBackground}
              onChange={(e) => setRunInBackground(e.target.checked)}
              disabled={isProcessing}
            />
          }
          label="Run in background"
        />
        
        {/* Debug toggle */}
        <Button
          variant="text"
          size="small"
          onDoubleClick={() => setShowDebugPanel(!showDebugPanel)}
          sx={{ 
            minWidth: 'auto', 
            color: 'transparent',
            '&:hover': { color: currentTheme.palette.text.secondary }
          }}
          title="Double-click to toggle debug panel"
        >
          🔧
        </Button>
      </Box>
      
      {/* Success Message */}
      {successMessage && (
        <Alert severity="success" sx={{ mt: 2 }}>
          {successMessage}
        </Alert>
      )}
      
      {/* Debug Panel */}
      {showDebugPanel && (statusData || isProcessing || lastStatusData) && (
        <Box sx={{ 
          mt: 2, 
          p: 2, 
          bgcolor: isDarkMode ? '#2d3748' : '#f5f5f5', 
          border: `1px solid ${currentTheme.palette.divider}`,
          borderRadius: 1,
          fontSize: '0.8rem', 
          fontFamily: 'monospace',
          color: currentTheme.palette.text.primary
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <strong>Debug Status Data {!statusData && lastStatusData ? '(LAST STATUS)' : '(CURRENT)'}:</strong>
            <button 
              onClick={() => {
                const saved = localStorage.getItem('lastProcessingStatus');
                if (saved) {
                  const parsed = JSON.parse(saved);
                  onLastStatusDataChange(parsed);
                  console.log('Retrieved from localStorage:', parsed);
                } else {
                  console.log('No saved status found in localStorage');
                }
              }}
              style={{ 
                fontSize: '0.7rem', 
                padding: '2px 6px', 
                backgroundColor: currentTheme.palette.action.hover, 
                color: currentTheme.palette.text.primary, 
                border: `1px solid ${currentTheme.palette.divider}`,
                borderRadius: '3px',
                cursor: 'pointer'
              }}
            >
              Load Last
            </button>
          </div>
          <pre style={{ 
            fontSize: '0.7rem', 
            margin: '4px 0', 
            backgroundColor: isDarkMode ? '#1a202c' : '#ffffff',
            color: currentTheme.palette.text.primary,
            padding: '8px',
            borderRadius: '4px',
            overflow: 'auto',
            maxHeight: '200px'
          }}>
            {JSON.stringify(statusData || lastStatusData, null, 2)}
          </pre>
        </Box>
      )}

      </>)}

      {subTab === 1 && (
        <Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6">Jobs</Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Button variant="outlined" size="small" onClick={loadJobs}>Refresh</Button>
              <Button
                variant="outlined"
                size="small"
                disabled={jobs.every(jobRunning)}
                onClick={clearJobs}
                title="Remove finished jobs from the list (running ones stay)"
              >
                Clear finished
              </Button>
            </Box>
          </Box>
          {jobs.length === 0 ? (
            <Typography variant="body2" sx={{ opacity: 0.75 }}>
              No jobs yet. Jobs started from the Processing tab -- and auto sync runs -- are listed
              here, oldest first. The backend keeps them until it restarts.
            </Typography>
          ) : (
            <TableContainer component={Paper}>
              <Table size="small" sx={{ minWidth: 900 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>Started</TableCell>
                    <TableCell>Job</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell sx={{ minWidth: 140 }}>Progress</TableCell>
                    <TableCell>Message</TableCell>
                    <TableCell></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {jobs.map((job) => (
                    <TableRow key={job.processing_id}>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                        {job.started_at ? new Date(job.started_at).toLocaleString() : ''}
                      </TableCell>
                      <TableCell title={job.label || job.processing_id}
                                 sx={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {job.kind === 'sync' ? ('auto sync ' + (job.sync_action || '') + (job.label ? ': ' + job.label : '')) : (job.label || job.processing_id)}
                      </TableCell>
                      <TableCell>{job.data_source}</TableCell>
                      <TableCell>
                        <Chip
                          label={job.status}
                          size="small"
                          color={job.status === 'completed' ? 'success' : job.status === 'failed' ? 'error'
                            : jobRunning(job) ? 'primary' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        <LinearProgress variant="determinate" value={job.progress || 0} />
                        <Typography variant="caption">{job.progress || 0}%</Typography>
                      </TableCell>
                      <TableCell sx={{ minWidth: 320, whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                        {job.message}
                      </TableCell>
                      <TableCell>
                        {jobRunning(job) && job.kind === 'ingest' && (
                          <Button variant="outlined" color="error" size="small" onClick={() => cancelJob(job)}>
                            Cancel
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </Box>
      )}
    </Box>
  );
};
