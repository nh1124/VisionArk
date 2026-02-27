use anyhow::Result;
use futures_util::StreamExt;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

pub async fn run(api_base: String, token: String) -> Result<()> {
    // WebSocket is optional — skip if no token is configured
    if token.is_empty() {
        warn!("No VISIONARK_TOKEN set; skipping WebSocket bridge");
        // Keep the task alive so tokio::try_join! doesn't exit
        std::future::pending::<()>().await;
        return Ok(());
    }

    let ws_base = api_base
        .replace("http://", "ws://")
        .replace("https://", "wss://");

    loop {
        // 1. Resolve user_id from the REST API using the Bearer token
        match fetch_user_id(&api_base, &token).await {
            Ok(user_id) => {
                let url = format!("{}/api/notifications/ws/{}", ws_base, user_id);
                info!("Connecting to backend WebSocket: {}", url);

                // 2. Build HTTP request with Authorization header
                let request = match tokio_tungstenite::tungstenite::http::Request::builder()
                    .uri(&url)
                    .header(
                        tokio_tungstenite::tungstenite::http::header::AUTHORIZATION,
                        format!("Bearer {}", token),
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
                                    info!("WS message: {}", text);
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
async fn fetch_user_id(api_base: &str, token: &str) -> Result<String> {
    let client = reqwest::Client::new();
    let resp = client
        .get(format!("{}/api/auth/me", api_base))
        .bearer_auth(token)
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
