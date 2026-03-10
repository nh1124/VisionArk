//! Auto-registration and heartbeat for the VisionArk daemon.
//!
//! On daemon startup (when no device_id is configured), `register()` calls
//! `POST /api/native/devices/register` and returns the assigned device_id.
//!
//! `heartbeat_loop()` then runs in the background, calling
//! `POST /api/native/devices/{id}/heartbeat` every 30 seconds to keep the
//! device status "online" in the backend.

use anyhow::Result;
use bridge_rs::http::BridgeClient;
use serde_json::json;
use tokio::time::{interval, Duration};
use tracing::{info, warn};

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
    // Windows sets COMPUTERNAME; Linux/macOS set HOSTNAME
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
    Ok(device_id)
}

/// Heartbeat loop - runs forever, pinging the backend every 30 seconds.
/// Errors are logged and swallowed so the loop never exits unexpectedly.
pub async fn heartbeat_loop(api_url: String, token: String, device_id: String) {
    let client = BridgeClient::new(&api_url, &token);
    let path = format!("/api/native/devices/{}/heartbeat", device_id);

    info!("Starting heartbeat loop for device_id={}", device_id);

    let mut ticker = interval(Duration::from_secs(HEARTBEAT_INTERVAL_SECS));
    loop {
        ticker.tick().await;
        if let Err(e) = client.post_value(&path).await {
            warn!("Heartbeat failed for device_id={}: {}", device_id, e);
        }
    }
}
