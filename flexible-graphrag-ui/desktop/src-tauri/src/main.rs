// No console window in release builds on Windows
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    flexible_graphrag_desktop_lib::run()
}
