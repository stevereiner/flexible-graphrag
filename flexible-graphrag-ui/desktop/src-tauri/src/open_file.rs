//! Open a local document named in search results and answers (frontend-react SourceDocs), with its
//! default app, or show it in its folder. The path comes from stored document metadata, so it is
//! checked here: an existing file, inside one of the folders the user added (`roots`), and not a
//! program or script (opening one would run it).

use std::path::{Path, PathBuf};

/// Extensions Windows (or a shell) runs rather than opens.
const RUNNABLE: &[&str] = &[
    "exe", "com", "bat", "cmd", "ps1", "psm1", "psd1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "msi",
    "msp", "mst", "lnk", "url", "scr", "pif", "cpl", "hta", "jar", "reg", "msc", "application",
    "appref-ms", "gadget", "inf", "sh", "command", "app", "desktop",
];

fn runnable(path: &Path) -> bool {
    let ext = path.extension().map(|e| e.to_string_lossy().to_lowercase()).unwrap_or_default();
    if RUNNABLE.contains(&ext.as_str()) {
        return true;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = std::fs::metadata(path) {
            return meta.permissions().mode() & 0o111 != 0;
        }
    }
    false
}

fn checked(path: &str, roots: &[String]) -> Result<PathBuf, String> {
    let file = std::fs::canonicalize(path).map_err(|e| format!("{path}: {e}"))?;
    if !file.is_file() {
        return Err(format!("not a file: {path}"));
    }
    let inside = roots
        .iter()
        .filter_map(|r| std::fs::canonicalize(r).ok())
        .any(|root| file.starts_with(&root));
    if !inside {
        return Err(format!("not in a folder added in this app: {path}"));
    }
    if runnable(&file) {
        return Err(format!("a program or script is not opened from here: {path}"));
    }
    Ok(file)
}

/// Open `path` with its default app, or (`reveal`) show it selected in its folder.
#[tauri::command]
pub async fn open_local_file(path: String, roots: Vec<String>, reveal: bool) -> Result<(), String> {
    let file = checked(&path, &roots)?;
    if reveal {
        tauri_plugin_opener::reveal_item_in_dir(&file).map_err(|e| e.to_string())
    } else {
        tauri_plugin_opener::open_path(&file, None::<&str>).map_err(|e| e.to_string())
    }
}
