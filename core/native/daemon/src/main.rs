mod activity;
mod bridge_client;
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

    // Trim to remove any hidden whitespace (e.g. \r from Windows env vars)
    let api_base = std::env::var("VISIONARK_API_URL")
        .unwrap_or_else(|_| "http://localhost:8000".to_string())
        .trim()
        .to_string();
    let token = std::env::var("VISIONARK_TOKEN")
        .unwrap_or_default()
        .trim()
        .to_string();

    info!("API base: {}", api_base);

    // Start WebSocket bridge
    let bridge_handle = tokio::spawn(bridge_client::run(api_base.clone(), token.clone()));

    // Start activity monitor
    let activity_handle = tokio::spawn(activity::monitor_loop());

    // Start job runner
    let runner_handle = tokio::spawn(job_runner::run(api_base, token));

    let (r1, r2, r3) = tokio::try_join!(bridge_handle, activity_handle, runner_handle)?;
    r1?;
    r2?;
    r3?;

    Ok(())
}
