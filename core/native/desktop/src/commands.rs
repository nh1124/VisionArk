use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tauri::{AppHandle, Manager};

// ─── App Config (shared with daemon via config file) ─────────────────────────

/// Subset of daemon config that the UI can read and write.
/// Stored at: {config_dir}/visionark/config.toml
/// The daemon reads this same file at startup (priority: env vars > file > defaults).
#[derive(Debug, Default, Deserialize, Serialize, Clone)]
pub struct AppConfig {
    #[serde(default)]
    pub api_url: String,
    #[serde(default)]
    pub run_daemon_in_background: bool,
}

const CONFIG_DIR_NAME: &str = "visionark";
const CONFIG_FILE_NAME: &str = "config.toml";

fn config_file_path(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    // Use config_dir() (no bundle-ID suffix) so the daemon can find the same file.
    app.path()
        .config_dir()
        .map(|d| d.join(CONFIG_DIR_NAME).join(CONFIG_FILE_NAME))
        .map_err(|e| e.to_string())
}

/// Returns the absolute path of the config file so the UI can display it.
/// The file may not yet exist if the user has never changed settings.
#[tauri::command]
pub fn get_config_file_path(app: AppHandle) -> Result<String, String> {
    config_file_path(&app).map(|p| p.to_string_lossy().into_owned())
}

#[tauri::command]
pub fn read_app_config(app: AppHandle) -> Result<AppConfig, String> {
    let path = config_file_path(&app)?;
    if !path.exists() {
        return Ok(AppConfig::default());
    }
    let content = std::fs::read_to_string(&path).map_err(|e| e.to_string())?;
    toml::from_str::<AppConfig>(&content).map_err(|e| e.to_string())
}

#[tauri::command]
pub fn write_app_config(app: AppHandle, config: AppConfig) -> Result<(), String> {
    let path = config_file_path(&app)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let content = toml::to_string_pretty(&config).map_err(|e| e.to_string())?;
    std::fs::write(&path, content).map_err(|e| e.to_string())
}

// ─── App Info ────────────────────────────────────────────────────────────────

#[tauri::command]
pub fn get_app_version(app: AppHandle) -> String {
    app.package_info().version.to_string()
}

#[tauri::command]
pub fn ping() -> &'static str {
    "pong"
}

#[tauri::command]
pub fn toggle_window(app: AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        if win.is_visible().unwrap_or(false) {
            win.hide().ok();
        } else {
            win.show().ok();
            win.set_focus().ok();
        }
    }
}

#[tauri::command]
pub fn send_notification(title: String, body: String, app: AppHandle) {
    use tauri_plugin_notification::NotificationExt;
    app.notification()
        .builder()
        .title(&title)
        .body(&body)
        .show()
        .ok();
}

#[tauri::command]
pub fn get_pending_count() -> u32 {
    // Placeholder — frontend polls the backend directly for pending count
    0
}

#[tauri::command]
pub fn set_secure_token(key: String, value: String) -> Result<(), String> {
    println!("[Keyring] set_secure_token called: key={}, value_len={}", key, value.len());
    let entry = keyring::Entry::new("visionark_app", &key).map_err(|e: keyring::Error| {
        eprintln!("[Keyring] Entry::new failed: {}", e);
        e.to_string()
    })?;
    println!("[Keyring] Entry created successfully for key={}", key);
    match entry.set_password(&value) {
        Ok(_) => {
            println!("[Keyring] set_password SUCCESS for key={}", key);
            Ok(())
        }
        Err(e) => {
            eprintln!("[Keyring] set_password FAILED for key={}: {}", key, e);
            Err(e.to_string())
        }
    }
}

#[tauri::command]
pub fn get_secure_token(key: String) -> Result<String, String> {
    println!("[Keyring] get_secure_token called: key={}", key);
    let entry = keyring::Entry::new("visionark_app", &key).map_err(|e: keyring::Error| {
        eprintln!("[Keyring] Entry::new failed: {}", e);
        e.to_string()
    })?;
    match entry.get_password() {
        Ok(pwd) => {
            println!("[Keyring] get_password SUCCESS for key={}, len={}", key, pwd.len());
            Ok(pwd)
        }
        Err(keyring::Error::NoEntry) => {
            println!("[Keyring] get_password NoEntry for key={}", key);
            Ok("".to_string())
        }
        Err(e) => {
            eprintln!("[Keyring] get_password FAILED for key={}: {}", key, e);
            Err(e.to_string())
        }
    }
}

#[tauri::command]
pub fn delete_secure_token(key: String) -> Result<(), String> {
    let entry = keyring::Entry::new("visionark_app", &key).map_err(|e: keyring::Error| e.to_string())?;
    match entry.delete_credential() {
        Ok(_) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(e) => {
            eprintln!("Failed to delete password: {}", e);
            Err(e.to_string())
        }
    }
}

// ─── Bridge HTTP transport (Phase 2: bridge-rs via Tauri invoke) ─────────────
//
// Allows TypeScript to route HTTP requests through Rust (bridge-rs).
// The TypeScript layer retains full control of auth injection, URL resolution,
// and retry logic — this command is a raw transport only.

#[derive(Serialize)]
pub struct BridgeResponse {
    pub status: u16,
    pub body: String,
}

/// Make an HTTP request via bridge-rs and return `{ status, body }`.
///
/// Called from TypeScript `bridge/api.ts` in Tauri mode:
///   invoke("bridge_request", { url, method, body, headers })
#[tauri::command]
pub async fn bridge_request(
    url: String,
    method: String,
    body: Option<String>,
    headers: Option<HashMap<String, String>>,
) -> Result<BridgeResponse, String> {
    let (status, body_str) = bridge_rs::http::raw_request_str(
        &url,
        &method,
        headers.unwrap_or_default(),
        body.as_deref(),
    )
    .await
    .map_err(|e| e.to_string())?;

    Ok(BridgeResponse {
        status,
        body: body_str,
    })
}

// ─── Daemon Control ─────────────────────────────────────────────────────────

#[tauri::command]
pub fn start_daemon_command(app: tauri::AppHandle, api_url: String, token: String, device_id: String) {
    let device_id = if device_id.trim().is_empty() {
        None
    } else {
        Some(device_id)
    };
    crate::daemon_manager::start_daemon(&app, api_url, token, device_id);
}

#[tauri::command]
pub fn stop_daemon_command(app: tauri::AppHandle) {
    crate::daemon_manager::stop_daemon(&app);
}
