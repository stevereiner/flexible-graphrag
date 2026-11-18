//! Flexible GraphRAG desktop app: hosts the React UI (frontend-react, built in desktop mode) and
//! gives it what a browser page can't have: the local disk (fs_browse, open_file) and its own
//! backend, started and stopped with the app (backend), kept running in the tray (tray).

mod backend;
mod fs_browse;
mod links;
mod open_file;
mod tray;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            links::create_main_window(app)?;
            tray::create(app)?;
            backend::start(app.handle());
            tray::show_status(app.handle(), &backend::status_line(app.handle()));
            tray::show_backend_files(app.handle());
            Ok(())
        })
        .on_window_event(|window, event| {
            // With the app's own backend, closing the window keeps it running in the tray
            // (auto sync keeps watching); Quit in the tray menu ends both.
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if backend::managed(window.app_handle()) {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            fs_browse::fs_roots,
            fs_browse::fs_list_dir,
            fs_browse::fs_start,
            open_file::open_local_file,
            backend::backend_info,
            backend::backend_status,
        ])
        .build(tauri::generate_context!())
        .expect("error while building the Flexible GraphRAG desktop app")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                backend::stop(app);
            }
        });
}
