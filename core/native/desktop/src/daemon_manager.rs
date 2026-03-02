use std::sync::Mutex;
use tauri::{AppHandle, Manager, Emitter};
use tauri_plugin_shell::{process::CommandChild, ShellExt};
use tracing::{error, info};

pub struct DaemonState {
    pub child: Mutex<Option<CommandChild>>,
}

impl DaemonState {
    pub fn new() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }
}

pub fn start_daemon(app: &AppHandle, api_url: String, token: String, device_id: String) {
    let state = app.state::<DaemonState>();
    let mut child_guard = state.child.lock().unwrap();

    // If already running, kill the old one
    if let Some(mut existing) = child_guard.take() {
        info!("Killing existing daemon process...");
        let _ = existing.kill();
    }

    info!("Starting visionark-daemon sidecar with device_id={}", device_id);

    // Provide config via env vars
    let command = app.shell().sidecar("visionark-daemon")
        .expect("visionark-daemon sidecar not found")
        .env("VISIONARK_API_URL", api_url)
        .env("VISIONARK_TOKEN", token)
        .env("VISIONARK_DEVICE_ID", device_id);

    match command.spawn() {
        Ok((rx, child)) => {
            *child_guard = Some(child);
            info!("Daemon started successfully.");
            
            // Optionally, we could spawn a task to drain `rx` (stdout/stderr)
            // and pipe it to Tracing or a log file.
            let app_clone = app.clone();
            tauri::async_runtime::spawn(async move {
                let mut rx = rx;
                while let Some(event) = rx.recv().await {
                    match event {
                        tauri_plugin_shell::process::CommandEvent::Stdout(line) => {
                            let s = String::from_utf8_lossy(&line);
                            info!("[daemon] {}", s);
                            app_clone.emit("daemon-log", s.to_string()).ok();
                        }
                        tauri_plugin_shell::process::CommandEvent::Stderr(line) => {
                            let s = String::from_utf8_lossy(&line);
                            error!("[daemon] {}", s);
                            app_clone.emit("daemon-log", s.to_string()).ok();
                        }
                        tauri_plugin_shell::process::CommandEvent::Terminated(payload) => {
                            info!("[daemon] Terminated with code {:?}", payload.code);
                            app_clone.emit("daemon-log", format!("Terminated with code {:?}", payload.code)).ok();
                            break;
                        }
                        tauri_plugin_shell::process::CommandEvent::Error(err) => {
                            error!("[daemon] Error: {}", err);
                            app_clone.emit("daemon-log", format!("Error: {}", err)).ok();
                            break;
                        }
                        _ => {}
                    }
                }
            });
        }
        Err(e) => {
            error!("Failed to spawn visionark-daemon sidecar: {}", e);
        }
    }
}

pub fn stop_daemon(app: &AppHandle) {
    if let Ok(mut lock) = app.state::<DaemonState>().child.lock() {
        if let Some(child) = lock.take() {
            info!("Stopping visionark-daemon sidecar...");
            let _ = child.kill();
        }
    }
}
