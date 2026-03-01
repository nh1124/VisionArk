mod activity;
mod bridge_client;
mod config;
mod job_runner;
mod local_tools;

use anyhow::Result;
use tracing::info;

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

    // Start job runner
    let runner_handle = tokio::spawn(job_runner::run(
        cfg.api_url,
        cfg.token,
        cfg.policy,
        trigger_rx,
        cfg.poll_interval_secs,
    ));

    let (r1, r2, r3) = tokio::try_join!(bridge_handle, activity_handle, runner_handle)?;
    r1?;
    r2?;
    r3?;

    Ok(())
}
