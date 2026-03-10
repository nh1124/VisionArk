mod activity;
mod bridge_client;
mod config;
mod device_registration;
mod job_runner;
mod local_tools;

use anyhow::Result;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::PathBuf;
use tracing::{info, warn};
use std::sync::Arc;
use tokio::sync::Mutex;

fn runtime_log_path() -> Option<PathBuf> {
    if let Ok(appdata) = std::env::var("APPDATA") {
        return Some(PathBuf::from(appdata).join("visionark").join("logs").join("daemon-runtime.log"));
    }
    if let Ok(home) = std::env::var("HOME") {
        return Some(PathBuf::from(home).join(".config").join("visionark").join("logs").join("daemon-runtime.log"));
    }
    None
}

fn append_runtime_log(level: &str, message: &str) {
    let path = match runtime_log_path() {
        Some(p) => p,
        None => return,
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(meta) = std::fs::metadata(&path) {
        if meta.len() > 5 * 1024 * 1024 {
            let rotated = path.with_extension("log.1");
            let _ = std::fs::remove_file(&rotated);
            let _ = std::fs::rename(&path, rotated);
        }
    }
    let mut file = match OpenOptions::new().create(true).append(true).open(&path) {
        Ok(f) => f,
        Err(_) => return,
    };
    let line = message.replace('\n', "\\n");
    let _ = writeln!(file, "[{:?}] [{}] {}", std::time::SystemTime::now(), level, line);
}

fn install_panic_hook() {
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
        append_runtime_log("PANIC", &format!("panic at {}: {}", location, payload));
    }));
}

async fn run_inner() -> Result<()> {
    let env_filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    tracing_subscriber::fmt().with_env_filter(env_filter).init();

    info!("VisionArk Daemon starting...");
    append_runtime_log("INFO", "daemon.run starting");

    // Load configuration: config file -> env var overrides -> defaults
    let cfg = config::load();
    info!(
        "API base: {} (poll every {}s, dry_run={})",
        cfg.api_url, cfg.poll_interval_secs, cfg.policy.dry_run
    );

    // Resolve device_id: use pre-configured value, or auto-register.
    // The device_id is shared between heartbeat_loop and job_runner via Arc<Mutex<String>>.
    // Empty string = not yet registered; heartbeat_loop will register on first tick.
    let initial_device_id = if let Some(id) = cfg.device_id.clone() {
        info!("Using pre-configured device_id={}", id);
        id
    } else if !cfg.token.is_empty() {
        match device_registration::register(&cfg.api_url, &cfg.token).await {
            Ok(id) => id,
            Err(e) => {
                warn!(
                    "Device registration failed (will retry via heartbeat): {}",
                    e
                );
                String::new()
            }
        }
    } else {
        warn!("No token configured; skipping device registration");
        String::new()
    };

    // Shared device_id: heartbeat_loop re-registers on 404 and updates this value;
    // job_runner reads it each poll cycle so it automatically picks up the new id.
    let device_id_shared: Option<Arc<Mutex<String>>> = if !cfg.token.is_empty() {
        Some(Arc::new(Mutex::new(initial_device_id)))
    } else {
        None
    };

    // Channel: bridge_client sends () to wake job_runner on push events
    let (trigger_tx, trigger_rx) = tokio::sync::mpsc::channel::<()>(32);

    // Start WebSocket bridge (passes trigger when job events arrive)
    let bridge_handle = tokio::spawn(bridge_client::run(
        cfg.api_url.clone(),
        cfg.token.clone(),
        trigger_tx,
    ));

    // Start activity monitor
    let activity_handle = tokio::spawn(activity::monitor_loop());

    // Start heartbeat loop (keeps device status online, re-registers on 404)
    if let Some(ref shared) = device_id_shared {
        tokio::spawn(device_registration::heartbeat_loop(
            cfg.api_url.clone(),
            cfg.token.clone(),
            shared.clone(),
        ));
    }

    // Start job runner
    let runner_handle = tokio::spawn(job_runner::run(
        cfg.api_url,
        cfg.token,
        cfg.policy,
        trigger_rx,
        cfg.poll_interval_secs,
        device_id_shared,
    ));

    let (r1, r2, r3) = tokio::try_join!(bridge_handle, activity_handle, runner_handle)?;
    r1?;
    r2?;
    r3?;

    Ok(())
}

#[tokio::main]
async fn main() -> Result<()> {
    install_panic_hook();
    match run_inner().await {
        Ok(()) => Ok(()),
        Err(e) => {
            append_runtime_log("ERROR", &format!("daemon exited with error: {}", e));
            Err(e)
        }
    }
}
