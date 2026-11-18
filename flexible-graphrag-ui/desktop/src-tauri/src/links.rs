//! Web links in the UI (a document's Alfresco Share / Nuxeo Web UI page, any other http(s) link)
//! open in the system's default browser, where the user is signed in to those apps, not in a bare
//! window of this app (Windows) or nowhere (macOS / Linux, whose webviews open no new windows
//! without a handler). The exception is the backend's sign-in popup (Microsoft 365, Box): the UI
//! watches that window until it closes, so it opens as a window of the app.

use tauri::webview::NewWindowResponse;
use tauri::{App, Url, WebviewWindowBuilder};

/// The backend's sign-in popup page (`/api/auth/<source>/popup`, sources/oauth_popup.py).
fn sign_in_popup(url: &Url) -> bool {
    matches!(url.scheme(), "http" | "https")
        && url.path().starts_with("/api/auth/")
        && url.path().ends_with("/popup")
}

fn open_in_browser(url: &Url) {
    if matches!(url.scheme(), "http" | "https" | "mailto") {
        let _ = tauri_plugin_opener::open_url(url.as_str(), None::<&str>);
    }
}

/// The app's own pages: the built app's origin (`tauri://localhost`, `http://tauri.localhost` on
/// Windows), or the dev server's in development. Anything else leaves the app.
fn own_page(url: &Url, dev: Option<&Url>) -> bool {
    match url.scheme() {
        "http" | "https" => {
            url.host_str() == Some("tauri.localhost") || dev.is_some_and(|d| d.origin() == url.origin())
        }
        "mailto" => false,
        _ => true, // tauri:, about:, data:, blob:
    }
}

/// The main window, from the config's window (`"create": false` there, so it is made here, with
/// the link handlers).
pub fn create_main_window(app: &App) -> tauri::Result<()> {
    let config = app.config().app.windows.first().cloned().expect("tauri.conf.json has no window");
    let dev = if tauri::is_dev() { app.config().build.dev_url.clone() } else { None };
    WebviewWindowBuilder::from_config(app, &config)?
        // window.open() and target="_blank" links
        .on_new_window(|url, _features| {
            if sign_in_popup(&url) {
                NewWindowResponse::Allow
            } else {
                open_in_browser(&url);
                NewWindowResponse::Deny
            }
        })
        // a plain link that would replace the app's page
        .on_navigation(move |url| {
            if own_page(url, dev.as_ref()) {
                true
            } else {
                open_in_browser(url);
                false
            }
        })
        .build()?;
    Ok(())
}
