use anyhow::Result;
use bridge_rs::http::BridgeClient;
use serde_json::Value;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

use crate::config::ExecutionPolicy;
use crate::local_tools;

/// Entry point: poll/run loop.
/// Phase 3: poll run_executions from /api/native-runs/pull.
/// Legacy /api/jobs polling is removed; this loop uses pull + claim.
pub async fn run(
    api_base: String,
    token: String,
    policy: ExecutionPolicy,
    mut trigger_rx: mpsc::Receiver<()>,
    poll_interval_secs: u64,
    device_id: Option<String>,
) -> Result<()> {
    let client = BridgeClient::new(api_base, token);

    if let Some(ref did) = device_id {
        info!("Run runner using device_id={} (run_executions mode)", did);
    } else {
        info!("Run runner: no device_id; skipping execution pull (configure VISIONARK_DEVICE_ID)");
    }

    loop {
        if let Some(ref did) = device_id {
            match pull_executions(&client, did).await {
                Ok(execs) => {
                    for exec in execs {
                        let exec_id = exec["id"].as_str().unwrap_or("").to_string();
                        let run_id = exec["run_id"].as_str().unwrap_or("").to_string();

                        // Pre-claim cancel check: skip if parent run is already canceled
                        match get_run_status(&client, &run_id).await {
                            Ok(ref s) if s == "canceled" || s == "cancelled" => {
                                info!("Run {} is canceled; skipping execution {}", run_id, exec_id);
                                continue;
                            }
                            Err(e) => warn!("Could not check run status for {}: {}; proceeding", run_id, e),
                            _ => {}
                        }

                        // Atomic claim to prevent double-execution
                        match claim_execution(&client, &exec_id, did).await {
                            Ok(_) => info!("Claimed execution {} on device {}", exec_id, did),
                            Err(e) => {
                                warn!("Could not claim execution {}: {}; skipping", exec_id, e);
                                continue;
                            }
                        }

                        info!("Processing execution {} (run={})", exec_id, run_id);
                        if let Err(e) = run_execution(&client, &run_id, &exec_id, &exec, &policy, did).await {
                            error!("Execution {} failed: {}", exec_id, e);
                            let _ = fail_execution(&client, &run_id, &exec_id, &e.to_string()).await;
                        }
                    }
                }
                Err(e) => error!("Failed to pull executions: {}", e),
            }
        }

        tokio::select! {
            _ = tokio::time::sleep(tokio::time::Duration::from_secs(poll_interval_secs)) => {}
            _ = trigger_rx.recv() => {
                info!("WS push trigger received; polling immediately");
            }
        }
    }
}

// Execution runner

async fn run_execution(
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
    exec: &Value,
    policy: &ExecutionPolicy,
    device_id: &str,
) -> Result<()> {
    let kind = exec["kind"].as_str().unwrap_or("").to_string();
    let risk = exec["risk_level"].as_str().unwrap_or("low");
    let payload = exec["payload"].clone();

    // Mark as running
    set_execution_status(client, run_id, exec_id, "running").await?;

    // High/critical risk: signal waiting_approval (backend auto-creates RunApproval)
    if risk == "high" || risk == "critical" {
        info!("Execution {} requires approval (risk={})", exec_id, risk);
        let reason = format!("Execution requires approval: {} (risk={})", kind, risk);
        // Single PATCH: sets status to waiting_approval + embeds reason in result
        client
            .patch_ignore(
                &format!("/api/native-runs/{}/executions/{}", run_id, exec_id),
                &serde_json::json!({
                    "status": "waiting_approval",
                    "result": { "approval_reason": reason }
                }),
            )
            .await?;

        match wait_for_approval(client, run_id, exec_id).await? {
            ApprovalResult::Approved => {
                info!("Execution {} approved, resuming", exec_id);
                set_execution_status(client, run_id, exec_id, "running").await?;
            }
            ApprovalResult::Rejected => {
                info!("Execution {} rejected", exec_id);
                return Ok(());
            }
        }
    }
    // Map kind -> local tool + args
    let (tool, args) = kind_to_tool(&kind, &payload);
    let tool_result = local_tools::dispatch_tool(policy, &tool, &args, client, run_id, exec_id, device_id).await;

    match tool_result {
        local_tools::ToolResult::Ok(data) => {
            patch_execution_result(client, run_id, exec_id, "succeeded", Some(data), None).await?;
        }
        local_tools::ToolResult::Err(e) => {
            patch_execution_result(
                client, run_id, exec_id, "failed", None,
                Some(e.clone()),
            ).await?;
        }
    }

    Ok(())
}

/// Map run execution kind -> (tool_name, args).
/// kind format: "local.<tool>" or direct tool name.
fn kind_to_tool(kind: &str, payload: &Value) -> (String, Value) {
    // Strip "local." prefix if present
    let tool = kind.strip_prefix("local.").unwrap_or(kind).to_string();
    (tool, payload.clone())
}

// Approval helpers

enum ApprovalResult {
    Approved,
    Rejected,
}

/// Poll the execution until it transitions out of waiting_approval.
/// Also polls the parent run and aborts if the run is canceled.
async fn wait_for_approval(
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
) -> Result<ApprovalResult> {
    loop {
        tokio::time::sleep(tokio::time::Duration::from_secs(3)).await;

        // Check parent run cancellation first
        match get_run_status(client, run_id).await {
            Ok(ref s) if s == "canceled" || s == "cancelled" => {
                info!("Run {} canceled during approval wait; aborting execution {}", run_id, exec_id);
                return Ok(ApprovalResult::Rejected);
            }
            Err(e) => warn!("Could not check run status during approval wait: {}", e),
            _ => {}
        }

        match client
            .get_value(&format!("/api/native-runs/{}/executions/{}", run_id, exec_id))
            .await
        {
            Ok(exec) => match exec["status"].as_str().unwrap_or("") {
                "running" => return Ok(ApprovalResult::Approved),
                "rejected" | "failed" => return Ok(ApprovalResult::Rejected),
                "waiting_approval" => {
                    info!("Still waiting for approval on execution {}", exec_id);
                }
                other => {
                    warn!("Unexpected execution status while waiting: {}", other);
                }
            },
            Err(e) => warn!("Failed to poll execution status: {}", e),
        }
    }
}

// API helpers

/// Fetch the status string of a Run from the backend.
async fn get_run_status(client: &BridgeClient, run_id: &str) -> Result<String> {
    let val = client.get_value(&format!("/api/native-runs/{}", run_id)).await?;
    let status = val["status"].as_str().unwrap_or("").to_string();
    Ok(status)
}

async fn pull_executions(client: &BridgeClient, device_id: &str) -> Result<Vec<Value>> {
    let path = format!(
        "/api/native-runs/pull?device_id={}&limit=10",
        urlencoding_simple(device_id)
    );
    client.get_vec(&path).await
}

async fn claim_execution(client: &BridgeClient, exec_id: &str, device_id: &str) -> Result<Value> {
    let path = format!(
        "/api/native-runs/executions/{}/claim?device_id={}",
        exec_id,
        urlencoding_simple(device_id)
    );
    client.post_value(&path).await
}

async fn set_execution_status(
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
    status: &str,
) -> Result<()> {
    client
        .patch_ignore(
            &format!("/api/native-runs/{}/executions/{}", run_id, exec_id),
            &serde_json::json!({ "status": status }),
        )
        .await
}

async fn fail_execution(
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
    error_log: &str,
) -> Result<()> {
    client
        .patch_ignore(
            &format!("/api/native-runs/{}/executions/{}", run_id, exec_id),
            &serde_json::json!({ "status": "failed", "error_log": error_log }),
        )
        .await
}

async fn patch_execution_result(
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
    status: &str,
    result: Option<Value>,
    error_log: Option<String>,
) -> Result<()> {
    let mut body = serde_json::json!({ "status": status });
    if let Some(r) = result {
        body["result"] = r;
    }
    if let Some(e) = error_log {
        body["error_log"] = Value::String(e);
    }
    client
        .patch_ignore(
            &format!("/api/native-runs/{}/executions/{}", run_id, exec_id),
            &body,
        )
        .await
}

/// Minimal percent-encoding for device_id (UUIDs are mostly safe as-is).
fn urlencoding_simple(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' | '.' | '~' => c.to_string(),
            other => format!("%{:02X}", other as u32),
        })
        .collect()
}

