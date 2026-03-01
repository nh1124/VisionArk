use anyhow::Result;
use reqwest::RequestBuilder;
use serde_json::Value;
use std::collections::HashMap;

// ─── BridgeClient ─────────────────────────────────────────────────────────────
//
// Authenticated HTTP client for VisionArk API paths.
// Used by the daemon's job_runner to call the backend REST API.
//
// api_base: e.g. "http://localhost:8000"
// token   : Bearer token (empty string = unauthenticated)

pub struct BridgeClient {
    client: reqwest::Client,
    pub api_base: String,
    pub token: String,
}

impl BridgeClient {
    pub fn new(api_base: impl Into<String>, token: impl Into<String>) -> Self {
        Self {
            client: reqwest::Client::new(),
            api_base: api_base.into(),
            token: token.into(),
        }
    }

    fn with_auth(&self, builder: RequestBuilder) -> RequestBuilder {
        if self.token.is_empty() {
            builder
        } else {
            builder.bearer_auth(&self.token)
        }
    }

    /// GET `{api_base}{path}` → deserialise body as `serde_json::Value`.
    pub async fn get_value(&self, path: &str) -> Result<Value> {
        let req = self.client.get(format!("{}{}", self.api_base, path));
        let resp = self.with_auth(req).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("GET {} failed {}: {}", path, status, text));
        }
        Ok(resp.json().await?)
    }

    /// GET `{api_base}{path}` → deserialise body as `Vec<serde_json::Value>`.
    pub async fn get_vec(&self, path: &str) -> Result<Vec<Value>> {
        let req = self.client.get(format!("{}{}", self.api_base, path));
        let resp = self.with_auth(req).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("GET {} failed {}: {}", path, status, text));
        }
        Ok(resp.json().await?)
    }

    /// POST `{api_base}{path}` (no request body) → deserialise body as `serde_json::Value`.
    pub async fn post_value(&self, path: &str) -> Result<Value> {
        let req = self.client.post(format!("{}{}", self.api_base, path));
        let resp = self.with_auth(req).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("POST {} failed {}: {}", path, status, text));
        }
        Ok(resp.json().await?)
    }

    /// POST `{api_base}{path}` with JSON body → deserialise body as `serde_json::Value`.
    pub async fn post_json(&self, path: &str, body: &Value) -> Result<Value> {
        let req = self.client.post(format!("{}{}", self.api_base, path));
        let resp = self.with_auth(req).json(body).send().await?;
        if !resp.status().is_success() {
            let status = resp.status();
            let text = resp.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("POST {} failed {}: {}", path, status, text));
        }
        Ok(resp.json().await?)
    }

    /// PATCH `{api_base}{path}` with JSON body; response body is discarded.
    pub async fn patch_ignore(&self, path: &str, body: &Value) -> Result<()> {
        let req = self.client.patch(format!("{}{}", self.api_base, path));
        self.with_auth(req).json(body).send().await?;
        Ok(())
    }
}

// ─── Raw HTTP transport (used by the Tauri bridge_request command) ────────────
//
// These functions take a full URL (not a path) and caller-supplied headers,
// so the TypeScript layer retains control of auth injection and URL resolution.

/// Make a raw HTTP request with the given full URL, method, headers, and body.
/// Returns `(status_code, response_body_text)`.
pub async fn raw_request(
    url: &str,
    method: reqwest::Method,
    headers: HashMap<String, String>,
    body: Option<&str>,
) -> Result<(u16, String)> {
    let client = reqwest::Client::new();
    let mut req = client.request(method, url);
    for (k, v) in &headers {
        req = req.header(k, v);
    }
    if let Some(b) = body {
        req = req.body(b.to_string());
    }
    let resp = req.send().await?;
    let status = resp.status().as_u16();
    let body_str = resp.text().await?;
    Ok((status, body_str))
}

/// Convenience wrapper that accepts the HTTP method as a string (e.g. `"GET"`).
pub async fn raw_request_str(
    url: &str,
    method: &str,
    headers: HashMap<String, String>,
    body: Option<&str>,
) -> Result<(u16, String)> {
    let method: reqwest::Method = method
        .parse()
        .map_err(|_| anyhow::anyhow!("Invalid HTTP method: {}", method))?;
    raw_request(url, method, headers, body).await
}
