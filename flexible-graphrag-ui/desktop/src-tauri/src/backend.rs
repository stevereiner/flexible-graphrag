//! The Flexible GraphRAG backend the app talks to, and the API token it wants (its API_TOKEN, sent by
//! the UI as X-API-Token).
//!
//! - FLEXIBLE_GRAPHRAG_URL set: that backend (yours to run), token from FLEXIBLE_GRAPHRAG_API_TOKEN.
//! - Else `backend_url` in `desktop.json` in the app config dir: the same, with its `api_token`
//!   (the remote / client setup: no Python on this machine, the app starts nothing).
//! - Else, a backend already answering on 127.0.0.1:<port> is used (one you started, or one left
//!   from an earlier run of the app).
//! - Else the app starts one itself in the backend folder, on 127.0.0.1 only, with API_TOKEN = a
//!   token kept per install (app config dir, file `api-token`) and CORS limited to the app's own
//!   pages: `<python> start.py` in a source checkout, or the `flexible-graphrag` command of an
//!   install (`uv pip install flexible-graphrag` into a venv in the folder). A folder without a .env
//!   gets one from env-sample.txt first (an install also gets sample-docs/). Its output goes to
//!   `backend.log` in the app log dir; it is stopped when the app exits.
//!
//! Port: FLEXIBLE_GRAPHRAG_PORT (default 8000; the UI calls the backend's URL directly, under
//! `npm run dev` too, so any port works). Backend folder: FLEXIBLE_GRAPHRAG_BACKEND_DIR (default: this checkout's
//! `flexible-graphrag/`, else the app data dir). Python: FLEXIBLE_GRAPHRAG_PYTHON (default: the
//! first of .venv, venv, venv-3.14, venv-3.13 found in or next to the backend folder).

use serde::Serialize;
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Component, Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, State};

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How long a starting backend gets to answer /api/health (first start imports a lot).
const START_TIMEOUT: Duration = Duration::from_secs(300);

/// The app's own pages: the dev servers (React 5174, Vue 3000, Angular 4200: the app runs any of the
/// three UIs), and the built app's webview origin (Windows, macOS / Linux).
const APP_ORIGINS: &str = "http://localhost:5174,http://localhost:3000,http://localhost:4200,\
http://tauri.localhost,tauri://localhost";

#[derive(Clone, Serialize)]
pub struct BackendStatus {
    /// "starting" | "ready" | "external" | "failed"
    state: &'static str,
    message: Option<String>,
    log_path: Option<String>,
}

pub struct Backend {
    url: String,
    port: u16,
    token: Option<String>,
    managed: bool,
    log_path: Option<PathBuf>,
    status: Mutex<BackendStatus>,
    child: Mutex<Option<Child>>,
    /// bumped by each start, so a restart's watch replaces the earlier one
    generation: AtomicU64,
}

#[derive(Serialize)]
pub struct BackendInfo {
    url: Option<String>,
    token: Option<String>,
    /// started (and stopped) by the app
    managed: bool,
}

fn env_value(name: &str) -> Option<String> {
    std::env::var(name).ok().map(|v| v.trim().to_string()).filter(|v| !v.is_empty())
}

/// `desktop.json` in the app config dir: the app's own settings (not the backend's .env).
#[derive(Default, serde::Deserialize)]
struct DesktopSettings {
    /// a backend run elsewhere (another machine, Docker): the app then starts none
    backend_url: Option<String>,
    /// that backend's API_TOKEN, if it has one
    api_token: Option<String>,
}

pub fn settings_file(app: &AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("desktop.json"))
}

/// `desktop.json`, made first (both settings empty: no effect) when it isn't there, for the tray's
/// "Edit app settings" item: so nobody has to find the app config dir.
pub fn ensure_settings_file(app: &AppHandle) -> Option<PathBuf> {
    let file = settings_file(app)?;
    if !file.exists() {
        fs::create_dir_all(file.parent()?).ok()?;
        fs::write(&file, "{\n  \"backend_url\": \"\",\n  \"api_token\": \"\"\n}\n").ok()?;
    }
    Some(file)
}

fn desktop_settings(app: &AppHandle) -> Result<DesktopSettings, String> {
    let Some(file) = settings_file(app) else { return Ok(DesktopSettings::default()) };
    match fs::read_to_string(&file) {
        Ok(text) => serde_json::from_str(&text).map_err(|e| format!("{}: {e}", file.display())),
        Err(_) => Ok(DesktopSettings::default()),
    }
}

fn non_empty(v: Option<String>) -> Option<String> {
    v.map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

/// `a/b/../c` -> `a/c`, without canonicalize (which gives `\\?\` paths on Windows).
fn tidy(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// The token this install's backend runs with: made once, kept in the app config dir.
fn install_token(app: &AppHandle) -> Result<String, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    let file = dir.join("api-token");
    if let Ok(t) = fs::read_to_string(&file) {
        let t = t.trim().to_string();
        if t.len() >= 32 {
            return Ok(t);
        }
    }
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| e.to_string())?;
    let token: String = bytes.iter().map(|b| format!("{b:02x}")).collect();
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    fs::write(&file, &token).map_err(|e| format!("{}: {e}", file.display()))?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = fs::set_permissions(&file, fs::Permissions::from_mode(0o600));
    }
    Ok(token)
}

/// A plain GET to the backend on 127.0.0.1: (status code, whole response), None when nothing answers.
fn get(port: u16, path: &str, token: Option<&str>) -> Option<(u16, String)> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut s = TcpStream::connect_timeout(&addr, Duration::from_millis(500)).ok()?;
    let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
    let _ = s.set_write_timeout(Some(Duration::from_secs(3)));
    let auth = token.map(|t| format!("X-API-Token: {t}\r\n")).unwrap_or_default();
    let req = format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n{auth}\r\n");
    s.write_all(req.as_bytes()).ok()?;
    let mut resp = String::new();
    let _ = s.read_to_string(&mut resp);
    let code = resp.lines().next()?.split_whitespace().nth(1)?.parse().ok()?;
    Some((code, resp))
}

/// GET /api/health answers 200 (exempt from the token check).
fn healthy(port: u16) -> bool {
    matches!(get(port, "/api/health", None), Some((200, body)) if body.contains("\"ok\""))
}

/// Whether a running backend takes this token (or wants none): a route behind the token check.
fn token_accepted(port: u16, token: Option<&str>) -> bool {
    matches!(get(port, "/api/ingest-allowed-paths", token), Some((200, _)))
}

/// Windows: put the backend in a job object that is closed (killing everything in it) when this
/// app's process ends, however it ends (Ctrl-C on `npm run dev`, a crash, Task Manager). Without
/// it a backend started without a console outlives a killed app, keeping the port.
#[cfg(windows)]
fn end_with_app(child: &Child) {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation, SetInformationJobObject,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    // SAFETY: plain Win32 calls on a handle we own; the job handle is deliberately never closed
    // (the OS closes it when this process ends, which is what ends the backend).
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const std::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        AssignProcessToJobObject(job, child.as_raw_handle() as _);
    }
}

#[cfg(not(windows))]
fn end_with_app(_child: &Child) {}

/// The backend folder: FLEXIBLE_GRAPHRAG_BACKEND_DIR, else this checkout's `flexible-graphrag/`
/// (an app built here), else the app's data folder (an app installed elsewhere).
fn backend_dir(app: &AppHandle) -> PathBuf {
    if let Some(dir) = env_value("FLEXIBLE_GRAPHRAG_BACKEND_DIR") {
        return PathBuf::from(dir);
    }
    // desktop/src-tauri -> repo root -> flexible-graphrag/ (a source checkout)
    let checkout = tidy(&Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../flexible-graphrag"));
    if checkout.join("start.py").is_file() {
        return checkout;
    }
    app.path().app_data_dir().unwrap_or(checkout)
}

/// The folder whose `sample-docs/` the local browser starts in (when it has no folder of its own
/// to go back to), and which it lists among its top folders: the backend folder of an install, the
/// repo root of a source checkout.
pub fn app_folder(app: &AppHandle) -> PathBuf {
    let dir = backend_dir(app);
    if dir.join("start.py").is_file() {
        dir.parent().map(Path::to_path_buf).unwrap_or(dir)
    } else {
        dir
    }
}

const VENV_NAMES: [&str; 4] = [".venv", "venv", "venv-3.14", "venv-3.13"];

fn venv_bin(venv: &Path, name: &str) -> PathBuf {
    if cfg!(windows) {
        venv.join("Scripts").join(format!("{name}.exe"))
    } else {
        venv.join("bin").join(name)
    }
}

/// `name` (python, flexible-graphrag) in the first venv found in or next to `dir`, or beside
/// FLEXIBLE_GRAPHRAG_PYTHON when that is set.
fn find_in_venv(dir: &Path, name: &str) -> Option<PathBuf> {
    if let Some(p) = env_value("FLEXIBLE_GRAPHRAG_PYTHON") {
        let python = PathBuf::from(p);
        if name == "python" {
            return Some(python);
        }
        let file = if cfg!(windows) { format!("{name}.exe") } else { name.to_string() };
        return python.parent().map(|bin| bin.join(file)).filter(|f| f.is_file());
    }
    let bases = [Some(dir.to_path_buf()), dir.parent().map(Path::to_path_buf)];
    for base in bases.into_iter().flatten() {
        for venv in VENV_NAMES {
            let bin = venv_bin(&base.join(venv), name);
            if bin.is_file() {
                return Some(bin);
            }
        }
    }
    None
}

/// How the backend is run, from what its folder holds.
enum Launch {
    /// A source checkout (`start.py` in the folder): `<python> start.py`.
    Source { python: PathBuf },
    /// An install (`uv pip install flexible-graphrag` into a venv in or next to the folder): its
    /// `flexible-graphrag` command, run in the folder, which holds its .env, flows, schemas, uploads.
    Installed { command: PathBuf },
}

fn launch_plan(dir: &Path) -> Result<Launch, String> {
    if dir.join("start.py").is_file() {
        return find_python(dir).map(|python| Launch::Source { python }).ok_or_else(|| {
            format!("No Python venv found next to {}. Set FLEXIBLE_GRAPHRAG_PYTHON.", dir.display())
        });
    }
    find_in_venv(dir, "flexible-graphrag").map(|command| Launch::Installed { command }).ok_or_else(|| {
        format!(
            "No Flexible GraphRAG in {dir}. Install it there:\n  \
             cd \"{dir}\"\n  uv venv venv-3.14 --python 3.14\n  uv pip install --python venv-3.14 flexible-graphrag\n\
             then restart the backend (tray menu). Or set FLEXIBLE_GRAPHRAG_BACKEND_DIR to the folder that has it.",
            dir = dir.display()
        )
    })
}

fn find_python(dir: &Path) -> Option<PathBuf> {
    find_in_venv(dir, "python")
}

/// env-sample.txt as the install has it: the wheel puts it at the top of site-packages.
fn installed_env_sample(command: &Path) -> Option<PathBuf> {
    let venv = command.parent()?.parent()?;
    if cfg!(windows) {
        return Some(venv.join("Lib").join("site-packages").join("env-sample.txt")).filter(|p| p.is_file());
    }
    fs::read_dir(venv.join("lib")).ok()?.flatten()
        .filter(|e| e.file_name().to_string_lossy().starts_with("python"))
        .map(|e| e.path().join("site-packages").join("env-sample.txt"))
        .find(|p| p.is_file())
}

fn copy_dir(from: &Path, to: &Path) -> std::io::Result<()> {
    fs::create_dir_all(to)?;
    for entry in fs::read_dir(from)?.flatten() {
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &target)?;
        } else {
            fs::copy(entry.path(), &target)?;
        }
    }
    Ok(())
}

/// A backend folder without a .env (a new install): `.env` from env-sample.txt, and for an install
/// the app's sample documents in `sample-docs/`. Only then, so a sample-docs/ you delete stays
/// deleted. What was done, for the log.
fn first_start(app: &AppHandle, dir: &Path, plan: &Launch) -> Vec<String> {
    let mut notes = Vec::new();
    let env = dir.join(".env");
    if env.exists() {
        return notes;
    }
    let sample = match plan {
        Launch::Source { .. } => Some(dir.join("env-sample.txt")).filter(|p| p.is_file()),
        Launch::Installed { command } => installed_env_sample(command),
    };
    match sample {
        Some(sample) => match fs::copy(&sample, &env) {
            Ok(_) => notes.push(format!("Created {} from {}: edit it, then restart the backend (tray menu).",
                                        env.display(), sample.display())),
            Err(e) => notes.push(format!("Could not create {}: {e}", env.display())),
        },
        None => notes.push(format!("No .env in {}, and no env-sample.txt found to make one from.", dir.display())),
    }
    if let Launch::Installed { .. } = plan {
        let target = dir.join("sample-docs");
        let bundled = app.path().resource_dir().ok().map(|r| r.join("sample-docs")).filter(|p| p.is_dir());
        if let (false, Some(bundled)) = (target.exists(), bundled) {
            match copy_dir(&bundled, &target) {
                Ok(()) => notes.push(format!("Added the sample documents in {}.", target.display())),
                Err(e) => notes.push(format!("Could not add the sample documents in {}: {e}", target.display())),
            }
        }
    }
    notes
}

/// The last lines of the backend log, for a failure message.
fn log_tail(path: &Path) -> String {
    let Ok(mut f) = File::open(path) else { return String::new() };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    let _ = f.seek(SeekFrom::Start(len.saturating_sub(3000)));
    let mut buf = Vec::new();
    let _ = f.read_to_end(&mut buf);
    let text = String::from_utf8_lossy(&buf);
    let lines: Vec<&str> = text.lines().collect();
    lines[lines.len().saturating_sub(15)..].join("\n")
}

fn spawn(app: &AppHandle, port: u16, token: &str) -> Result<(Child, PathBuf), (String, Option<PathBuf>)> {
    let dir = backend_dir(app);
    fs::create_dir_all(&dir).map_err(|e| (format!("{}: {e}", dir.display()), None))?;
    let plan = launch_plan(&dir).map_err(|m| (m, None))?;
    let log_dir = app.path().app_log_dir().map_err(|e| (e.to_string(), None))?;
    fs::create_dir_all(&log_dir).map_err(|e| (e.to_string(), None))?;
    let log_path = log_dir.join("backend.log");
    let mut log = File::create(&log_path).map_err(|e| (format!("{}: {e}", log_path.display()), None))?;
    for note in first_start(app, &dir, &plan) {
        let _ = writeln!(log, "[desktop app] {note}");
    }
    let log_err = log.try_clone().map_err(|e| (e.to_string(), None))?;

    let (program, describe) = match &plan {
        Launch::Source { python } => (python.clone(), format!("{} start.py", python.display())),
        Launch::Installed { command } => (command.clone(), command.display().to_string()),
    };
    let mut cmd = Command::new(&program);
    if let Launch::Source { .. } = plan {
        cmd.arg("start.py");
    }
    cmd.current_dir(&dir)
        .env("FLEXIBLE_GRAPHRAG_HOST", "127.0.0.1")
        .env("FLEXIBLE_GRAPHRAG_PORT", port.to_string())
        // environment wins over the backend's .env (load_dotenv doesn't override, nor does pydantic)
        .env("API_TOKEN", token)
        .env("CORS_ORIGINS", APP_ORIGINS)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err));
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    let child = cmd
        .spawn()
        .map_err(|e| (format!("Couldn't start {describe}: {e}"), Some(log_path.clone())))?;
    end_with_app(&child);
    Ok((child, log_path))
}

fn set_status(app: &AppHandle, state: &'static str, message: Option<String>) {
    let backend = app.state::<Backend>();
    let log_path = backend.log_path.as_ref().map(|p| p.display().to_string());
    *backend.status.lock().unwrap() = BackendStatus { state, message, log_path };
    crate::tray::show_status(app, &status_line(app));
}

/// The backend's state in a few words (the tray menu and tooltip).
pub fn status_line(app: &AppHandle) -> String {
    let Some(backend) = app.try_state::<Backend>() else { return "Backend: -".into() };
    let state = backend.status.lock().unwrap().state;
    match state {
        "starting" => "Backend: starting…".into(),
        "ready" => format!("Backend: running on {}", backend.url),
        "external" => format!("Backend: using {}", backend.url),
        _ => "Backend: not running (see the log)".into(),
    }
}

/// Whether the app runs the backend itself (then closing the window keeps it running in the tray).
pub fn managed(app: &AppHandle) -> bool {
    app.try_state::<Backend>().is_some_and(|b| b.managed)
}

/// The port of a backend URL on this machine (localhost, 127.0.0.1, [::1]); None for another host.
fn local_port(url: &str) -> Option<u16> {
    let rest = url.strip_prefix("http://")?;
    let host_port = rest.split('/').next()?;
    let (host, port) = host_port.rsplit_once(':')?;
    if !matches!(host.to_ascii_lowercase().as_str(), "localhost" | "127.0.0.1" | "[::1]") {
        return None;
    }
    port.parse().ok()
}

/// The port of the backend in use when it runs on this machine (the app's own, or one you run).
fn this_machine_port(app: &AppHandle) -> Option<u16> {
    let b = app.try_state::<Backend>()?;
    if b.port != 0 { Some(b.port) } else { local_port(&b.url) }
}

/// Whether the backend in use runs on this machine, so its log and .env can be shown.
pub fn on_this_machine(app: &AppHandle) -> bool {
    this_machine_port(app).is_some()
}

#[derive(Default, serde::Deserialize)]
struct BackendFiles {
    env_file: Option<String>,
    log_file: Option<String>,
}

/// Where a backend the app didn't start (on this machine) says its .env and log are.
fn backend_files(app: &AppHandle) -> BackendFiles {
    let Some(port) = this_machine_port(app) else { return BackendFiles::default() };
    let token = app.try_state::<Backend>().and_then(|b| b.token.clone());
    match get(port, "/api/backend-files", token.as_deref()) {
        Some((200, resp)) => resp
            .split_once("\r\n\r\n")
            .and_then(|(_, body)| serde_json::from_str(body).ok())
            .unwrap_or_default(),
        _ => BackendFiles::default(),
    }
}

/// The tray's "Show backend settings": the .env of the backend in use, when it runs on this
/// machine: the backend folder's for the app's own, else the one that backend says it loaded.
pub fn settings_path(app: &AppHandle) -> Option<PathBuf> {
    if managed(app) {
        return Some(backend_dir(app).join(".env"));
    }
    backend_files(app).env_file.map(PathBuf::from)
}

/// The tray's "Show backend log": the app's backend.log for its own backend, else the log file a
/// backend on this machine says it writes.
pub fn log_path(app: &AppHandle) -> Option<PathBuf> {
    if let Some(path) = app.try_state::<Backend>().and_then(|b| b.log_path.clone()) {
        return Some(path);
    }
    backend_files(app).log_file.map(PathBuf::from)
}

/// Wait for a started backend to answer, or to stop. `generation`: a restart starts a new watch.
fn watch(app: AppHandle, port: u16, generation: u64) {
    let started = Instant::now();
    loop {
        std::thread::sleep(Duration::from_millis(500));
        let backend = app.state::<Backend>();
        if backend.generation.load(Ordering::SeqCst) != generation {
            return;
        }
        let exited = {
            let mut child = backend.child.lock().unwrap();
            match child.as_mut().map(|c| c.try_wait()) {
                Some(Ok(Some(code))) => Some(code.to_string()),
                Some(Err(e)) => Some(e.to_string()),
                None => return, // stopped by the app
                _ => None,
            }
        };
        if let Some(code) = exited {
            let tail = backend.log_path.as_deref().map(log_tail).unwrap_or_default();
            set_status(&app, "failed", Some(format!("The backend stopped ({code}).\n{tail}")));
            return;
        }
        if healthy(port) {
            set_status(&app, "ready", None);
            return;
        }
        if started.elapsed() > START_TIMEOUT {
            set_status(&app, "failed", Some(format!("The backend didn't answer on port {port} within {} s.", START_TIMEOUT.as_secs())));
            return;
        }
    }
}

fn new_backend(url: String, port: u16, token: Option<String>, managed: bool, state: &'static str,
               message: Option<String>, log_path: Option<PathBuf>) -> Backend {
    Backend {
        url,
        port,
        token,
        managed,
        status: Mutex::new(BackendStatus {
            state,
            message,
            log_path: log_path.as_ref().map(|p| p.display().to_string()),
        }),
        log_path,
        child: Mutex::new(None),
        generation: AtomicU64::new(0),
    }
}

/// Called from the app's setup: decide which backend to use, start one if needed.
pub fn start(app: &AppHandle) {
    let env_token = env_value("FLEXIBLE_GRAPHRAG_API_TOKEN");

    if let Some(url) = env_value("FLEXIBLE_GRAPHRAG_URL") {
        app.manage(new_backend(url, 0, env_token, false, "external", None, None));
        return;
    }

    match desktop_settings(app) {
        Ok(s) => {
            if let Some(url) = non_empty(s.backend_url) {
                let token = env_token.clone().or(non_empty(s.api_token));
                let url = url.trim_end_matches('/').to_string();
                app.manage(new_backend(url, 0, token, false, "external", None, None));
                return;
            }
        }
        Err(e) => {
            // a broken desktop.json: say so rather than quietly starting a local backend
            let msg = format!("Can't read the app settings: {e}");
            app.manage(new_backend(String::new(), 0, None, false, "failed", Some(msg), None));
            return;
        }
    }

    let port: u16 = env_value("FLEXIBLE_GRAPHRAG_PORT").and_then(|p| p.parse().ok()).unwrap_or(8000);
    let url = format!("http://127.0.0.1:{port}");
    let own_token = install_token(app);

    if healthy(port) {
        // A backend already there: one you run (its API_TOKEN = FLEXIBLE_GRAPHRAG_API_TOKEN), or
        // one this app started earlier (our token). Use the token it takes.
        let candidates = [env_token.clone(), own_token.as_ref().ok().cloned()];
        let token = candidates.into_iter().flatten().find(|t| token_accepted(port, Some(t)));
        let using = format!("Using the backend already running on port {port}.");
        let backend = match token {
            Some(t) => new_backend(url, port, Some(t), false, "external", Some(using), None),
            None if token_accepted(port, None) => new_backend(url, port, None, false, "external", Some(using), None),
            None => new_backend(url, port, env_token, false, "failed", Some(format!(
                "A backend is already running on port {port}, and it wants an API token this app doesn't have.\n\
                 Stop that backend and restart the app: it then starts its own."
            )), None),
        };
        app.manage(backend);
        return;
    }

    let own_token = match own_token {
        Ok(t) => t,
        Err(e) => {
            let msg = format!("No API token for the backend: {e}");
            app.manage(new_backend(url, port, None, false, "failed", Some(msg), None));
            return;
        }
    };
    let log_path = app.path().app_log_dir().ok().map(|d| d.join("backend.log"));
    app.manage(new_backend(url, port, Some(own_token), true, "starting", None, log_path));
    launch(app);
}

/// Start the app's own backend (first start, or a restart) and watch it come up.
fn launch(app: &AppHandle) {
    let backend = app.state::<Backend>();
    let generation = backend.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let token = backend.token.clone().unwrap_or_default();
    match spawn(app, backend.port, &token) {
        Ok((child, _)) => {
            *backend.child.lock().unwrap() = Some(child);
            set_status(app, "starting", None);
            let handle = app.clone();
            let port = backend.port;
            std::thread::spawn(move || watch(handle, port, generation));
        }
        Err((message, _)) => set_status(app, "failed", Some(message)),
    }
}

/// Stop the app's own backend and start it again (tray menu). The window reloads, so its
/// startup screen waits for the new backend.
pub fn restart(app: &AppHandle) {
    if !managed(app) {
        return;
    }
    stop(app);
    launch(app);
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.eval("window.location.reload()");
    }
}

/// Stop the backend the app started (with its child processes): on exit, and before a restart.
pub fn stop(app: &AppHandle) {
    let Some(backend) = app.try_state::<Backend>() else { return };
    let Some(mut child) = backend.child.lock().unwrap().take() else { return };
    #[cfg(windows)]
    {
        // a hard stop of the process tree: Windows has no Ctrl-C for a windowless process
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[tauri::command]
pub fn backend_info(backend: State<'_, Backend>) -> BackendInfo {
    BackendInfo { url: Some(backend.url.clone()), token: backend.token.clone(), managed: backend.managed }
}

#[tauri::command]
pub fn backend_status(backend: State<'_, Backend>) -> BackendStatus {
    backend.status.lock().unwrap().clone()
}
