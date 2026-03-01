use anyhow::Result;
use bridge_rs::http::BridgeClient;
use serde_json::Value;
use std::collections::HashSet;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

use crate::config::ExecutionPolicy;
use crate::local_tools;

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
        info!("Job runner using device_id={} for pull/claim routing", did);
    } else {
        info!("Job runner using legacy source=native polling (no device_id configured)");
    }

    loop {
        let poll_result = match &device_id {
            Some(did) => pull_jobs_for_device(&client, did).await,
            None => poll_queued_jobs(&client).await,
        };

        match poll_result {
            Ok(jobs) => {
                for job in jobs {
                    let job_id = job["id"].as_str().unwrap_or("").to_string();

                    // Claim the job before execution to prevent double-execution
                    if let Some(ref did) = device_id {
                        match claim_job(&client, &job_id, did).await {
                            Ok(_) => info!("Claimed job {} on device {}", job_id, did),
                            Err(e) => {
                                // 409 = already claimed by another device — skip silently
                                warn!("Could not claim job {}: {} — skipping", job_id, e);
                                continue;
                            }
                        }
                    }

                    info!("Processing job {}", job_id);
                    if let Err(e) = run_job_with_plan(&client, &job_id, &policy).await {
                        error!("Job {} failed: {}", job_id, e);
                        let _ = patch_job_status_with_error(&client, &job_id, &e.to_string()).await;
                    }
                }
            }
            Err(e) => error!("Failed to poll jobs: {}", e),
        }

        // Wait for the poll interval OR a WebSocket push trigger (whichever comes first)
        tokio::select! {
            _ = tokio::time::sleep(tokio::time::Duration::from_secs(poll_interval_secs)) => {}
            _ = trigger_rx.recv() => {
                info!("WS push trigger received — polling immediately");
            }
        }
    }
}

/// Plan & Execute loop for a single job.
async fn run_job_with_plan(
    client: &BridgeClient,
    job_id: &str,
    policy: &ExecutionPolicy,
) -> Result<()> {
    // 1. Mark as running
    patch_job_status(client, job_id, "running").await?;

    // 2. Dispatch → get plan (returns existing plan if already dispatched)
    let plan = dispatch_job_plan(client, job_id).await?;

    let steps = match plan["steps"].as_array() {
        Some(s) => s.clone(),
        None => {
            warn!("Job {} plan has no steps, marking succeeded", job_id);
            patch_job_status(client, job_id, "succeeded").await?;
            return Ok(());
        }
    };

    // 3. Skip steps already completed (supports resume after daemon restart)
    let completed = get_completed_step_ids(client, job_id).await;

    // 4. Execute each step
    for step in &steps {
        let step_id = step["id"].as_str().unwrap_or("").to_string();
        let tool = step["tool"].as_str().unwrap_or("").to_string();
        let args = step["args"].clone();
        let risk = step["risk_level"].as_str().unwrap_or("low");

        if completed.contains(&step_id) {
            info!("Skipping already-completed step {}", step_id);
            continue;
        }

        info!(
            "Executing step {} (tool={}, risk={})",
            step_id, tool, risk
        );

        // Mark the current step so the UI can show a spinner
        let _ = set_current_step(client, job_id, Some(&step_id)).await;

        // High/critical risk steps require user approval
        if risk == "high" || risk == "critical" {
            info!("Step {} requires approval", step_id);
            patch_job_status(client, job_id, "needs_approval").await?;
            match wait_for_approval(client, job_id).await? {
                ApprovalResult::Approved => {
                    info!("Step {} approved, resuming", step_id);
                    patch_job_status(client, job_id, "running").await?;
                }
                ApprovalResult::Rejected => {
                    info!("Job {} rejected at step {}", job_id, step_id);
                    return Ok(());
                }
            }
        }

        // Execute the local tool (subject to execution policy)
        let tool_result = local_tools::dispatch_tool(policy, &tool, &args).await;

        // Persist step result
        patch_step_result(client, job_id, &step_id, tool_result).await?;
    }

    // 5. All steps complete — clear current_step
    let _ = set_current_step(client, job_id, None).await;
    patch_job_status(client, job_id, "succeeded").await?;
    Ok(())
}

enum ApprovalResult {
    Approved,
    Rejected,
}

// ─── API helpers (delegate to BridgeClient) ───────────────────────────────────

async fn poll_queued_jobs(client: &BridgeClient) -> Result<Vec<Value>> {
    client
        .get_vec("/api/jobs?source=native&status=queued&limit=10")
        .await
}

/// Device-targeted pull: only jobs assigned to this device (or auto-routed unclaimed).
async fn pull_jobs_for_device(client: &BridgeClient, device_id: &str) -> Result<Vec<Value>> {
    let path = format!(
        "/api/jobs/pull?device_id={}&status=queued&limit=10",
        urlencoding_simple(device_id)
    );
    client.get_vec(&path).await
}

/// Claim a job before execution to prevent double-execution across daemons.
async fn claim_job(client: &BridgeClient, job_id: &str, device_id: &str) -> Result<Value> {
    let path = format!(
        "/api/jobs/{}/claim?device_id={}",
        job_id,
        urlencoding_simple(device_id)
    );
    client.post_value(&path).await
}

/// Minimal percent-encoding for device_id (UUIDs only need hyphens — safe as-is).
fn urlencoding_simple(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            'A'..='Z' | 'a'..='z' | '0'..='9' | '-' | '_' | '.' | '~' => c.to_string(),
            other => format!("%{:02X}", other as u32),
        })
        .collect()
}

async fn dispatch_job_plan(client: &BridgeClient, job_id: &str) -> Result<Value> {
    client
        .post_value(&format!("/api/jobs/{}/dispatch", job_id))
        .await
}

async fn get_completed_step_ids(client: &BridgeClient, job_id: &str) -> HashSet<String> {
    if let Ok(job) = client.get_value(&format!("/api/jobs/{}", job_id)).await {
        if let Some(results) = job["result"]["step_results"].as_array() {
            return results
                .iter()
                .filter_map(|r| r["step_id"].as_str().map(|s| s.to_string()))
                .collect();
        }
    }
    HashSet::new()
}

async fn patch_job_status(client: &BridgeClient, job_id: &str, status: &str) -> Result<()> {
    client
        .patch_ignore(
            &format!("/api/jobs/{}", job_id),
            &serde_json::json!({ "status": status }),
        )
        .await
}

async fn patch_job_status_with_error(
    client: &BridgeClient,
    job_id: &str,
    error_log: &str,
) -> Result<()> {
    client
        .patch_ignore(
            &format!("/api/jobs/{}", job_id),
            &serde_json::json!({ "status": "failed", "error_log": error_log }),
        )
        .await
}

async fn wait_for_approval(client: &BridgeClient, job_id: &str) -> Result<ApprovalResult> {
    loop {
        tokio::time::sleep(tokio::time::Duration::from_secs(3)).await;
        match client.get_value(&format!("/api/jobs/{}", job_id)).await {
            Ok(job) => match job["status"].as_str().unwrap_or("") {
                "queued" | "running" => return Ok(ApprovalResult::Approved),
                "rejected" | "failed" => return Ok(ApprovalResult::Rejected),
                "needs_approval" => {
                    info!("Still waiting for approval on job {}", job_id);
                }
                other => {
                    warn!("Unexpected job status while waiting: {}", other);
                }
            },
            Err(e) => warn!("Failed to poll job status: {}", e),
        }
    }
}

/// Read-modify-write to update job.result.current_step for live UI tracking.
async fn set_current_step(
    client: &BridgeClient,
    job_id: &str,
    step_id: Option<&str>,
) -> Result<()> {
    let current_job = client
        .get_value(&format!("/api/jobs/{}", job_id))
        .await
        .unwrap_or(Value::Null);
    let mut current_result = match current_job["result"].clone() {
        Value::Object(m) => m,
        _ => serde_json::Map::new(),
    };
    current_result.insert(
        "current_step".to_string(),
        match step_id {
            Some(id) => Value::String(id.to_string()),
            None => Value::Null,
        },
    );
    client
        .patch_ignore(
            &format!("/api/jobs/{}", job_id),
            &serde_json::json!({ "result": current_result }),
        )
        .await
}

/// Read-modify-write to append a step result to job.result.step_results.
async fn patch_step_result(
    client: &BridgeClient,
    job_id: &str,
    step_id: &str,
    tool_result: local_tools::ToolResult,
) -> Result<()> {
    // Fetch current job to get existing result (preserves plan + prior step_results)
    let current_job = client
        .get_value(&format!("/api/jobs/{}", job_id))
        .await
        .unwrap_or(Value::Null);

    let mut current_result = match current_job["result"].clone() {
        Value::Object(m) => m,
        _ => serde_json::Map::new(),
    };

    let mut step_results = current_result
        .get("step_results")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let (ok, data) = match tool_result {
        local_tools::ToolResult::Ok(v) => (true, v),
        local_tools::ToolResult::Err(e) => (false, serde_json::json!({ "error": e })),
    };

    step_results.push(serde_json::json!({
        "step_id": step_id,
        "ok": ok,
        "data": data,
    }));

    current_result.insert(
        "step_results".to_string(),
        Value::Array(step_results),
    );

    client
        .patch_ignore(
            &format!("/api/jobs/{}", job_id),
            &serde_json::json!({ "result": current_result }),
        )
        .await
}
