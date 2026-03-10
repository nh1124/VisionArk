//! Auto-registration and heartbeat for the VisionArk daemon.
//!
//! On daemon startup, `register()` calls `POST /api/native/devices/register`
//! and returns the assigned device_id (idempotent upsert by display_name + platform).
//!
//! `heartbeat_loop()` runs in the background, pinging every 30 seconds.
//! If the backend returns 404 (device not found), it automatically re-registers
//! and updates the shared device_id so the job_runner picks it up on the next poll.

use anyhow::Result;
use bridge_rs::http::BridgeClient;
use serde_json::json;
use std::sync::Arc;
use tokio::sync::Mutex;
use tokio::time::{interval, Duration};
use tracing::{info, warn};

use crate::config;

const HEARTBEAT_INTERVAL_SECS: u64 = 30;

/// Detect the current OS as a platform string matching the backend enum.
fn detect_platform() -> &'static str {
    match std::env::consts::OS {
        "windows" => "windows",
        "macos" => "macos",
        "linux" => "linux",
        _ => "other",
    }
}

/// Try to get a reasonable hostname for the display name.
fn get_hostname() -> String {
    for var in &["COMPUTERNAME", "HOSTNAME"] {
        if let Ok(name) = std::env::var(var) {
            let name = name.trim().to_string();
            if !name.is_empty() {
                return name;
            }
        }
    }
    "daemon".to_string()
}

/// Register this machine as a native device.
/// Returns the assigned `device_id`.
///
/// The registration endpoint is idempotent: if a device with the same
/// display_name already exists for this user, the backend returns the
/// existing record.
pub async fn register(api_url: &str, token: &str) -> Result<String> {
    let client = BridgeClient::new(api_url, token);
    let platform = detect_platform();
    let hostname = get_hostname();
    let display_name = format!("{} ({})", hostname, platform);

    let body = json!({
        "display_name": display_name,
        "device_kind": "desktop",
        "platform": platform,
        "capabilities": ["run_shell", "file_rw", "open_app"],
    });

    info!(
        "Registering device: display_name={:?} platform={}",
        display_name, platform
    );

    let resp = client
        .post_json("/api/native/devices/register", &body)
        .await?;

    let device_id = resp["id"]
        .as_str()
        .ok_or_else(|| anyhow::anyhow!("Register response missing 'id' field"))?
        .to_string();

    info!("Device registered: id={}", device_id);
    // Persist per-server so the daemon survives restarts without re-registering.
    config::save_device_id(api_url, &device_id);
    Ok(device_id)
}

/// Heartbeat loop — runs forever, pinging the backend every 30 seconds.
///
/// The device_id is shared with the job_runner via `Arc<Mutex<String>>`.
/// On 404 (device deleted from DB), the loop automatically re-registers and
/// updates the shared device_id so the job_runner uses the new one on the
/// next poll cycle.
pub async fn heartbeat_loop(
    api_url: String,
    token: String,
    device_id: Arc<Mutex<String>>,
) {
    let client = BridgeClient::new(&api_url, &token);
    info!("Starting heartbeat loop");

    let mut ticker = interval(Duration::from_secs(HEARTBEAT_INTERVAL_SECS));
    loop {
        ticker.tick().await;

        let id = device_id.lock().await.clone();
        if id.is_empty() {
            // No device yet — try to register
            match register(&api_url, &token).await {
                Ok(new_id) => {
                    info!("heartbeat_loop: registered device_id={}", new_id);
                    *device_id.lock().await = new_id;
                }
                Err(e) => warn!("heartbeat_loop: registration attempt failed: {}", e),
            }
            continue;
        }

        let path = format!("/api/native/devices/{}/heartbeat", id);
        match client.post_value(&path).await {
            Ok(_) => {}
            Err(e) => {
                let err_str = e.to_string();
                warn!("Heartbeat failed for device_id={}: {}", id, e);

                // On 404 the device no longer exists in the DB — re-register.
                if err_str.contains("404") {
                    info!("Device not found; re-registering...");
                    match register(&api_url, &token).await {
                        Ok(new_id) => {
                            info!("Re-registered device: new_id={}", new_id);
                            *device_id.lock().await = new_id;
                        }
                        Err(e) => warn!("Re-registration failed: {}", e),
                    }
                }
            }
        }
    }
}
