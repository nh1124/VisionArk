use anyhow::Result;
use futures_util::StreamExt;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

/// Job-related WebSocket event types that should trigger immediate job polling.
const TRIGGER_EVENTS: &[&str] = &["job.created", "job.queued", "job.updated"];

// ─── WsClient ─────────────────────────────────────────────────────────────────
//
// Connects to the VisionArk notification WebSocket stream and sends a trigger
// on `trigger_tx` whenever a job-related event arrives (waking the job runner).
//
// Reconnects automatically on close/error (5 second back-off after user_id
// resolution failures, 10 seconds after connection loss).

pub struct WsClient {
    api_base: String,
    token: String,
    trigger_tx: mpsc::Sender<()>,
}

impl WsClient {
    pub fn new(
        api_base: impl Into<String>,
        token: impl Into<String>,
        trigger_tx: mpsc::Sender<()>,
    ) -> Self {
        Self {
            api_base: api_base.into(),
            token: token.into(),
            trigger_tx,
        }
    }

    /// Run the WebSocket client loop (reconnects forever).
    pub async fn run(self) -> Result<()> {
        let ws_base = self
            .api_base
            .replace("http://", "ws://")
            .replace("https://", "wss://");

        loop {
            match self.fetch_user_id().await {
                Ok(user_id) => {
                    let url = format!("{}/api/notifications/ws/{}", ws_base, user_id);
                    info!("Connecting to backend WebSocket: {}", url);

                    let request = match tokio_tungstenite::tungstenite::http::Request::builder()
                        .uri(&url)
                        .header(
                            tokio_tungstenite::tungstenite::http::header::AUTHORIZATION,
                            format!("Bearer {}", self.token),
                        )
                        .body(())
                    {
                        Ok(r) => r,
                        Err(e) => {
                            error!("Failed to build WebSocket request: {}", e);
                            tokio::time::sleep(tokio::time::Duration::from_secs(10)).await;
                            continue;
                        }
                    };

                    match connect_async(request).await {
                        Ok((mut stream, _)) => {
                            info!("WebSocket connected (user_id={})", user_id);
                            while let Some(msg) = stream.next().await {
                                match msg {
                                    Ok(Message::Text(text)) => {
                                        if let Ok(v) =
                                            serde_json::from_str::<serde_json::Value>(&text)
                                        {
                                            let event_type = v["type"].as_str().unwrap_or("");
                                            if TRIGGER_EVENTS.contains(&event_type) {
                                                info!(
                                                    "Push trigger: {} — waking job runner",
                                                    event_type
                                                );
                                                // try_send: drop if channel full (runner already awake)
                                                let _ = self.trigger_tx.try_send(());
                                            }
                                        }
                                    }
                                    Ok(Message::Close(_)) => {
                                        warn!("WebSocket closed by server");
                                        break;
                                    }
                                    Err(e) => {
                                        error!("WebSocket error: {}", e);
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                        }
                        Err(e) => {
                            error!("WebSocket connection failed: {}", e);
                        }
                    }
                }
                Err(e) => {
                    error!("Failed to resolve user_id for WebSocket: {}", e);
                }
            }

            tokio::time::sleep(tokio::time::Duration::from_secs(10)).await;
        }
    }

    /// Call GET /api/auth/me to resolve the user_id from the Bearer token.
    async fn fetch_user_id(&self) -> Result<String> {
        let client = reqwest::Client::new();
        let resp = client
            .get(format!("{}/api/auth/me", self.api_base))
            .bearer_auth(&self.token)
            .send()
            .await?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!(
                "GET /api/auth/me failed {}: {}",
                status,
                body
            ));
        }

        let json: serde_json::Value = resp.json().await?;
        json["user_id"]
            .as_str()
            .map(|s| s.to_string())
            .ok_or_else(|| anyhow::anyhow!("user_id not found in /api/auth/me response"))
    }
}
