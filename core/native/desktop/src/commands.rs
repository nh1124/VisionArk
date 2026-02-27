use tauri::{AppHandle, Manager};

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
