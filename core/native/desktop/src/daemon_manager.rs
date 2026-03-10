use std::sync::Mutex;
use tauri::{AppHandle, Manager, Emitter};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use tracing::{error, info};
use tokio::time::{Duration, Instant};
use std::fs::OpenOptions;
use std::io::Write;

const APP_DIR: &str = "visionark";
const LOG_DIR: &str = "logs";
const DAEMON_LOG_FILE: &str = "desktop-daemon.log";

fn append_daemon_log_file(app: &AppHandle, level: &str, line: &str) {
    let path = match app.path().config_dir() {
        Ok(dir) => dir.join(APP_DIR).join(LOG_DIR).join(DAEMON_LOG_FILE),
        Err(_) => return,
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    // simple rotate (5MB)
    if let Ok(meta) = std::fs::metadata(&path) {
        if meta.len() > 5 * 1024 * 1024 {
            let rotated = path.with_extension("log.1");
            let _ = std::fs::remove_file(&rotated);
            let _ = std::fs::rename(&path, rotated);
        }
    }
    let mut f = match OpenOptions::new().create(true).append(true).open(&path) {
        Ok(f) => f,
        Err(_) => return,
    };
    let msg = line.replace('\n', "\\n");
    let _ = writeln!(f, "[{:?}] [{}] {}", std::time::SystemTime::now(), level, msg);
}

pub struct DaemonState {
    pub child: Mutex<Option<CommandChild>>,
    pub launch_signature: Mutex<Option<String>>,
}

impl DaemonState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
            launch_signature: Mutex::new(None),
        }
    }
}

pub fn start_daemon(app: &AppHandle, api_url: String, token: String, device_id: Option<String>) {
    let effective_api_url = if api_url.trim().is_empty() {
        "http://localhost:8000".to_string()
    } else {
        api_url.trim().to_string()
    };
    append_daemon_log_file(
        app,
        "INFO",
        &format!(
            "start_daemon requested input_api_url={} effective_api_url={} token_present={} device_id={}",
            api_url,
            effective_api_url,
            if token.trim().is_empty() { "false" } else { "true" },
            device_id.clone().unwrap_or_default()
        ),
    );
    crate::core_log::append_with_app(
        app,
        "INFO",
        &format!(
            "start_daemon requested input_api_url={} effective_api_url={} token_present={} device_id={}",
            api_url,
            effective_api_url,
            if token.trim().is_empty() { "false" } else { "true" },
            device_id.clone().unwrap_or_default()
        ),
    );
    let Some(state) = app.try_state::<DaemonState>() else {
        append_daemon_log_file(
            app,
            "WARN",
            "start_daemon skipped: DaemonState not initialized yet",
        );
        crate::core_log::append_with_app(
            app,
            "WARN",
            "start_daemon skipped: DaemonState not initialized yet",
        );
        return;
    };
    let mut child_guard = state.child.lock().unwrap();
    let mut signature_guard = state.launch_signature.lock().unwrap();
    let requested_signature = format!(
        "{}|{}|{}",
        effective_api_url,
        device_id.clone().unwrap_or_default(),
        token
    );

    if child_guard.is_some() {
        info!("Daemon process already exists, skipping start request.");
        append_daemon_log_file(app, "INFO", "start_daemon skipped because child process already exists");
        crate::core_log::append_with_app(app, "INFO", "start_daemon skipped (child already exists)");
        if signature_guard.is_none() {
            *signature_guard = Some(requested_signature);
        }
        return;
    }

    let device_id_for_log = device_id
        .as_deref()
        .filter(|id| !id.is_empty())
        .unwrap_or("(empty)");
    info!(
        "Starting visionark-daemon sidecar with device_id={} api_url={} (input={})",
        device_id_for_log,
        effective_api_url,
        api_url
    );

    // Provide config via env vars
    let mut command = app.shell().sidecar("visionark-daemon")
        .expect("visionark-daemon sidecar not found")
        .env("VISIONARK_API_URL", effective_api_url)
        .env("VISIONARK_TOKEN", token);

    if let Some(id) = device_id.filter(|id| !id.is_empty()) {
        command = command.env("VISIONARK_DEVICE_ID", id);
    }

    match command.spawn() {
        Ok((rx, child)) => {
            *child_guard = Some(child);
            *signature_guard = Some(requested_signature);
            info!("Daemon started successfully.");
            append_daemon_log_file(app, "INFO", "daemon sidecar spawned successfully");
            crate::core_log::append_with_app(app, "INFO", "daemon sidecar spawned successfully");
            
            // Optionally, we could spawn a task to drain `rx` (stdout/stderr)
            // and pipe it to Tracing or a log file.
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                let mut rx = rx;
                // Guardrail: avoid renderer overload when daemon emits very chatty logs.
                // Emit to UI at most 1 line / 200ms.
                let mut last_emit_at = Instant::now()
                    .checked_sub(Duration::from_millis(200))
                    .unwrap_or_else(Instant::now);
                while let Some(event) = rx.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                            let s = String::from_utf8_lossy(&line);
                            info!("[daemon] {}", s);
                            append_daemon_log_file(&app_clone, "STDOUT", &s);
                            let has_console = app_clone.get_webview_window("console").is_some();
                            if has_console && last_emit_at.elapsed() >= Duration::from_millis(200) {
                                let payload: String = s.chars().take(2048).collect();
                                app_clone.emit("daemon-log", payload).ok();
                                last_emit_at = Instant::now();
                            }
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                            let s = String::from_utf8_lossy(&line);
                            error!("[daemon] {}", s);
                            append_daemon_log_file(&app_clone, "STDERR", &s);
                            let has_console = app_clone.get_webview_window("console").is_some();
                            if has_console && last_emit_at.elapsed() >= Duration::from_millis(200) {
                                let payload: String = s.chars().take(2048).collect();
                                app_clone.emit("daemon-log", payload).ok();
                                last_emit_at = Instant::now();
                            }
                        }
                        tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                            info!("[daemon] Terminated with code {:?}", payload.code);
                            if let Some(state) = app_clone.try_state::<DaemonState>() {
                                if let Ok(mut lock) = state.child.lock() {
                                    let _ = lock.take();
                                }
                                if let Ok(mut lock) = state.launch_signature.lock() {
                                    *lock = None;
                                }
                            }
                            append_daemon_log_file(
                                &app_clone,
                                "TERM",
                                &format!("Terminated with code {:?}", payload.code),
                            );
                            crate::core_log::append_with_app(
                                &app_clone,
                                "WARN",
                                &format!("daemon terminated code={:?}", payload.code),
                            );
                            if app_clone.get_webview_window("console").is_some() {
                                app_clone.emit("daemon-log", format!("Terminated with code {:?}", payload.code)).ok();
                            }
                            break;
                        }
                        tauri_plugin_shell::process::CommandEvent::Error(err) => {
                            error!("[daemon] Error: {}", err);
                            if let Some(state) = app_clone.try_state::<DaemonState>() {
                                if let Ok(mut lock) = state.child.lock() {
                                    let _ = lock.take();
                                }
                                if let Ok(mut lock) = state.launch_signature.lock() {
                                    *lock = None;
                                }
                            }
                            append_daemon_log_file(&app_clone, "ERROR", &err);
                            crate::core_log::append_with_app(
                                &app_clone,
                                "ERROR",
                                &format!("daemon command error: {}", err),
                            );
                            if app_clone.get_webview_window("console").is_some() {
                                app_clone.emit("daemon-log", format!("Error: {}", err)).ok();
                            }
                            break;
                        }
                        _ => {}
                    }
                }
            });
        }
        Err(e) => {
            *signature_guard = None;
            error!("Failed to spawn visionark-daemon sidecar: {}", e);
            append_daemon_log_file(app, "ERROR", &format!("failed to spawn daemon sidecar: {}", e));
            crate::core_log::append_with_app(
                app,
                "ERROR",
                &format!("failed to spawn daemon sidecar: {}", e),
            );
        }
    }
}

pub fn stop_daemon(app: &AppHandle) {
    let Some(state) = app.try_state::<DaemonState>() else {
        append_daemon_log_file(app, "WARN", "stop_daemon skipped: DaemonState not initialized");
        crate::core_log::append_with_app(
            app,
            "WARN",
            "stop_daemon skipped: DaemonState not initialized",
        );
        return;
    };
    if let Ok(mut lock) = state.child.lock() {
        if let Some(child) = lock.take() {
            info!("Stopping visionark-daemon sidecar...");
            let _ = child.kill();
        }
    }
    if let Ok(mut sig) = state.launch_signature.lock() {
        *sig = None;
    };
}
