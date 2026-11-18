//! The tray icon (Windows notification area, macOS menu bar), like Ollama's: the backend the app
//! started keeps running there with the window closed, so auto sync keeps watching the local
//! folders. Left click: open the window. Menu: open, the backend's state, its log, its settings
//! (.env), the app's own settings (desktop.json), restart, quit (which stops the backend).

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{App, AppHandle, Manager, Wry};

const TRAY_ID: &str = "main";

/// The menu line showing the backend's state, updated by backend.rs.
struct StatusItem(MenuItem<Wry>);

/// "Show backend log" and "Show backend settings": nothing to show for a backend on another machine.
struct BackendFileItems(MenuItem<Wry>, MenuItem<Wry>);

/// Called once the app knows which backend it uses.
pub fn show_backend_files(app: &AppHandle) {
    if crate::backend::on_this_machine(app) {
        return;
    }
    if let Some(items) = app.try_state::<BackendFileItems>() {
        let _ = items.0.set_text("Backend log: on the backend's machine");
        let _ = items.0.set_enabled(false);
        let _ = items.1.set_text("Backend settings: on the backend's machine");
        let _ = items.1.set_enabled(false);
    }
}

pub fn show_main(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

/// Show the backend's state in the menu and the tooltip.
pub fn show_status(app: &AppHandle, line: &str) {
    if let Some(item) = app.try_state::<StatusItem>() {
        let _ = item.0.set_text(line);
    }
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let _ = tray.set_tooltip(Some(format!("Flexible GraphRAG\n{line}")));
    }
}

pub fn create(app: &App) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Flexible GraphRAG", true, None::<&str>)?;
    let status = MenuItem::with_id(app, "status", "Backend: -", false, None::<&str>)?;
    let log = MenuItem::with_id(app, "log", "Show backend log", true, None::<&str>)?;
    let settings = MenuItem::with_id(app, "settings", "Show backend settings (.env)", true, None::<&str>)?;
    let app_settings =
        MenuItem::with_id(app, "app_settings", "Edit app settings (desktop.json)", true, None::<&str>)?;
    let restart = MenuItem::with_id(app, "restart", "Restart backend", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit (stops the backend)", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &open,
            &PredefinedMenuItem::separator(app)?,
            &status,
            &log,
            &settings,
            &app_settings,
            &restart,
            &PredefinedMenuItem::separator(app)?,
            &quit,
        ],
    )?;
    app.manage(StatusItem(status));
    app.manage(BackendFileItems(log.clone(), settings.clone()));

    let mut tray = TrayIconBuilder::with_id(TRAY_ID)
        .tooltip("Flexible GraphRAG")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_main(app),
            // off the UI thread: for a backend the app didn't start, these ask it where its files are
            "log" => {
                let app = app.clone();
                std::thread::spawn(move || {
                    if let Some(path) = crate::backend::log_path(&app) {
                        let _ = tauri_plugin_opener::open_path(&path, None::<&str>);
                    }
                });
            }
            "settings" => {
                // the backend's .env, selected in its folder (or the folder, when there's no .env yet)
                let app = app.clone();
                std::thread::spawn(move || {
                    if let Some(env) = crate::backend::settings_path(&app) {
                        let _ = if env.exists() {
                            tauri_plugin_opener::reveal_item_in_dir(&env)
                        } else {
                            env.parent().map_or(Ok(()), |dir| tauri_plugin_opener::open_path(dir, None::<&str>))
                        };
                    }
                });
            }
            "app_settings" => {
                // desktop.json (made if missing), in its editor; else selected in its folder.
                // Read at app start: quit and reopen the app after editing it.
                if let Some(file) = crate::backend::ensure_settings_file(app) {
                    if tauri_plugin_opener::open_path(&file, None::<&str>).is_err() {
                        let _ = tauri_plugin_opener::reveal_item_in_dir(&file);
                    }
                }
            }
            "restart" => {
                // stopping and starting take a moment: off the UI thread
                let app = app.clone();
                std::thread::spawn(move || crate::backend::restart(&app));
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                show_main(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        tray = tray.icon(icon.clone());
    }
    tray.build(app)?;
    Ok(())
}
