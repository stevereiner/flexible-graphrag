//! The local disk for the UI's file browser (frontend-react/src/browser/LocalProvider.ts): the top
//! level (home folder, drives) and one level of a folder at a time. Read-only.

use serde::Serialize;
use std::fs::Metadata;
use std::path::PathBuf;
use std::time::UNIX_EPOCH;
use tauri::AppHandle;

#[cfg(windows)]
#[link(name = "kernel32")]
extern "system" {
    /// Bit 0 = A:, bit 1 = B:, ... (Win32)
    fn GetLogicalDrives() -> u32;
}

#[derive(Serialize)]
pub struct FsEntry {
    name: String,
    path: String,
    is_dir: bool,
    size: Option<u64>,
    modified_ms: Option<u64>,
}

fn folder(name: String, path: String) -> FsEntry {
    FsEntry { name, path, is_dir: true, size: None, modified_ms: None }
}

const APP_FOLDER_NAME: &str = "Flexible GraphRAG";

/// The app's folder (the backend folder of an install, the repo root of a source checkout) as a
/// top folder, when it is there.
fn app_root(app: &AppHandle) -> Option<FsEntry> {
    let dir = crate::backend::app_folder(app);
    dir.is_dir().then(|| folder(APP_FOLDER_NAME.into(), dir.to_string_lossy().into_owned()))
}

/// Where the browser starts when it has no folder of its own to go back to: the app folder's
/// sample-docs/, as the folders from the top down. Empty: the top level.
#[tauri::command]
pub async fn fs_start(app: AppHandle) -> Vec<FsEntry> {
    let Some(root) = app_root(&app) else { return Vec::new() };
    let samples = PathBuf::from(&root.path).join("sample-docs");
    if !samples.is_dir() {
        return Vec::new();
    }
    vec![root, folder("sample-docs".into(), samples.to_string_lossy().into_owned())]
}

/// The top level: the user's home folder, the app's folder, then the drives (Windows) or "/"
/// (macOS, Linux).
#[tauri::command]
pub async fn fs_roots(app: AppHandle) -> Vec<FsEntry> {
    let mut roots = Vec::new();
    let home = std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" });
    if let Some(home) = home {
        roots.push(folder("Home".into(), home.to_string_lossy().into_owned()));
    }
    roots.extend(app_root(&app));
    // The drive list from Windows itself: checking each letter (Path::exists) can stall for
    // seconds on a disconnected network drive or an empty card reader
    #[cfg(windows)]
    {
        let mask = unsafe { GetLogicalDrives() };
        for (i, letter) in ('A'..='Z').enumerate() {
            if mask & (1 << i) != 0 {
                roots.push(folder(format!("{letter}:"), format!("{letter}:\\")));
            }
        }
    }
    #[cfg(not(windows))]
    roots.push(folder("System (/)".into(), "/".into()));
    roots
}

/// The files and folders directly in `path` (absolute), folders first, then by name. Hidden and
/// system entries are left out; entries that can't be read are skipped.
#[tauri::command]
pub async fn fs_list_dir(path: String) -> Result<Vec<FsEntry>, String> {
    let dir = PathBuf::from(&path);
    if !dir.is_absolute() {
        return Err(format!("not an absolute path: {path}"));
    }
    let entries = std::fs::read_dir(&dir).map_err(|e| format!("{path}: {e}"))?;
    let mut out = Vec::new();
    for entry in entries.flatten() {
        let entry_path = entry.path();
        // The listing's own metadata (on Windows it comes with the directory read; fs::metadata
        // would open every file). Only a symbolic link is followed, to show what it points to;
        // a broken one stays the link itself.
        let meta = match entry.metadata() {
            Ok(m) if m.file_type().is_symlink() => std::fs::metadata(&entry_path).unwrap_or(m),
            Ok(m) => m,
            Err(_) => continue,
        };
        let name = entry.file_name().to_string_lossy().into_owned();
        if is_hidden(&name, &meta) {
            continue;
        }
        let is_dir = meta.is_dir();
        out.push(FsEntry {
            name,
            path: entry_path.to_string_lossy().into_owned(),
            is_dir,
            size: if is_dir { None } else { Some(meta.len()) },
            modified_ms: meta
                .modified()
                .ok()
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_millis() as u64),
        });
    }
    out.sort_by(|a, b| {
        b.is_dir.cmp(&a.is_dir).then_with(|| a.name.to_lowercase().cmp(&b.name.to_lowercase()))
    });
    Ok(out)
}

#[cfg(windows)]
fn is_hidden(name: &str, meta: &Metadata) -> bool {
    use std::os::windows::fs::MetadataExt;
    const HIDDEN: u32 = 0x2;
    const SYSTEM: u32 = 0x4;
    name.starts_with('.') || meta.file_attributes() & (HIDDEN | SYSTEM) != 0
}

#[cfg(not(windows))]
fn is_hidden(name: &str, _meta: &Metadata) -> bool {
    name.starts_with('.')
}
