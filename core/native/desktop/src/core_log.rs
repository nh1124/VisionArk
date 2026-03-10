use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use std::sync::Once;
use tauri::{AppHandle, Manager};

const APP_DIR: &str = "visionark";
const LOG_DIR: &str = "logs";
const CORE_LOG_FILE: &str = "desktop-core.log";

fn resolve_log_path_from_app(app: &AppHandle) -> Option<PathBuf> {
    let base = app.path().config_dir().ok()?;
    Some(base.join(APP_DIR).join(LOG_DIR).join(CORE_LOG_FILE))
}

fn resolve_log_path_fallback() -> Option<PathBuf> {
    if let Ok(appdata) = std::env::var("APPDATA") {
        return Some(PathBuf::from(appdata).join(APP_DIR).join(LOG_DIR).join(CORE_LOG_FILE));
    }
    if let Ok(home) = std::env::var("HOME") {
        return Some(PathBuf::from(home).join(".config").join(APP_DIR).join(LOG_DIR).join(CORE_LOG_FILE));
    }
    None
}

fn append_line(path: &PathBuf, level: &str, message: &str) {
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(meta) = std::fs::metadata(path) {
        if meta.len() > 5 * 1024 * 1024 {
            let rotated = path.with_extension("log.1");
            let _ = std::fs::remove_file(&rotated);
            let _ = std::fs::rename(path, rotated);
        }
    }
    let mut file = match OpenOptions::new().create(true).append(true).open(path) {
        Ok(f) => f,
        Err(_) => return,
    };
    let line = message.replace('\n', "\\n");
    let _ = writeln!(file, "[{:?}] [{}] {}", std::time::SystemTime::now(), level, line);
}

pub fn append_with_app(app: &AppHandle, level: &str, message: &str) {
    if let Some(path) = resolve_log_path_from_app(app) {
        append_line(&path, level, message);
    }
}

pub fn append_fallback(level: &str, message: &str) {
    if let Some(path) = resolve_log_path_fallback() {
        append_line(&path, level, message);
    }
}

pub fn install_panic_hook() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        std::panic::set_hook(Box::new(|panic_info| {
            let location = panic_info
                .location()
                .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
                .unwrap_or_else(|| "(unknown)".to_string());
            let payload = if let Some(s) = panic_info.payload().downcast_ref::<&str>() {
                (*s).to_string()
            } else if let Some(s) = panic_info.payload().downcast_ref::<String>() {
                s.clone()
            } else {
                "non-string panic payload".to_string()
            };
            append_fallback("PANIC", &format!("panic at {}: {}", location, payload));
        }));
    });
}
