mod activity;
mod bridge_client;
mod config;
mod device_registration;
mod job_runner;
mod local_tools;

use anyhow::Result;
use tracing::{info, warn};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .init();

    info!("VisionArk Daemon starting...");

    // Load configuration: config file → env var overrides → defaults
    let cfg = config::load();
    info!(
        "API base: {} (poll every {}s, dry_run={})",
        cfg.api_url, cfg.poll_interval_secs, cfg.policy.dry_run
    );

    // ── Device registration ────────────────────────────────────────────────
    // Resolve device_id: use pre-configured value, or auto-register.
    // Registration requires a token; without one the daemon still works but
    // falls back to the legacy poll-all-jobs mode.
    let device_id = if let Some(id) = cfg.device_id.clone() {
        info!("Using pre-configured device_id={}", id);
        Some(id)
    } else if !cfg.token.is_empty() {
        match device_registration::register(&cfg.api_url, &cfg.token).await {
            Ok(id) => Some(id),
            Err(e) => {
                warn!(
                    "Device registration failed (running without device routing): {}",
                    e
                );
                None
            }
        }
    } else {
        warn!("No token configured — skipping device registration");
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

    // Start heartbeat loop (keeps device status "online")
    if let Some(ref id) = device_id {
        tokio::spawn(device_registration::heartbeat_loop(
            cfg.api_url.clone(),
            cfg.token.clone(),
            id.clone(),
        ));
    }

    // Start job runner
    let runner_handle = tokio::spawn(job_runner::run(
        cfg.api_url,
        cfg.token,
        cfg.policy,
        trigger_rx,
        cfg.poll_interval_secs,
        device_id,
    ));

    let (r1, r2, r3) = tokio::try_join!(bridge_handle, activity_handle, runner_handle)?;
    r1?;
    r2?;
    r3?;

    Ok(())
}
