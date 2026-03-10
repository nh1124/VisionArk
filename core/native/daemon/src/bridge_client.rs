use anyhow::Result;
use bridge_rs::ws::WsClient;
use tokio::sync::mpsc;
use tracing::warn;

pub async fn run(api_base: String, token: String, trigger_tx: mpsc::Sender<()>) -> Result<()> {
    // WebSocket is optional - skip if no token is configured
    if token.is_empty() {
        warn!("No VISIONARK_TOKEN set; skipping WebSocket bridge");
        // Keep the task alive so tokio::try_join! doesn't exit
        std::future::pending::<()>().await;
        return Ok(());
    }

    WsClient::new(api_base, token, trigger_tx).run().await
}
