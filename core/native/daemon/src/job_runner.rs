use anyhow::Result;
use reqwest::RequestBuilder;
use serde_json::Value;
use std::collections::HashSet;
use tracing::{error, info, warn};

use crate::local_tools;

pub async fn run(api_base: String, token: String) -> Result<()> {
    let client = reqwest::Client::new();

    loop {
        match poll_queued_jobs(&client, &api_base, &token).await {
            Ok(jobs) => {
                for job in jobs {
                    let job_id = job["id"].as_str().unwrap_or("").to_string();
                    info!("Processing job {}", job_id);
                    if let Err(e) =
                        run_job_with_plan(&client, &api_base, &token, &job_id).await
                    {
                        error!("Job {} failed: {}", job_id, e);
                        let _ = patch_job_status_with_error(
                            &client, &api_base, &token, &job_id, &e.to_string(),
                        )
                        .await;
                    }
                }
            }
            Err(e) => error!("Failed to poll jobs: {}", e),
        }
        tokio::time::sleep(tokio::time::Duration::from_secs(10)).await;
    }
}

/// Plan & Execute loop for a single job.
async fn run_job_with_plan(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
) -> Result<()> {
    // 1. Mark as running
    patch_job_status(client, api_base, token, job_id, "running").await?;

    // 2. Dispatch → get plan (returns existing plan if already dispatched)
    let plan = dispatch_job_plan(client, api_base, token, job_id).await?;

    let steps = match plan["steps"].as_array() {
        Some(s) => s.clone(),
        None => {
            warn!("Job {} plan has no steps, marking succeeded", job_id);
            patch_job_status(client, api_base, token, job_id, "succeeded").await?;
            return Ok(());
        }
    };

    // 3. Skip steps already completed (supports resume after daemon restart)
    let completed = get_completed_step_ids(client, api_base, token, job_id).await;

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

        // High/critical risk steps require user approval
        if risk == "high" || risk == "critical" {
            info!("Step {} requires approval", step_id);
            patch_job_status(client, api_base, token, job_id, "needs_approval").await?;
            match wait_for_approval(client, api_base, token, job_id).await? {
                ApprovalResult::Approved => {
                    info!("Step {} approved, resuming", step_id);
                    patch_job_status(client, api_base, token, job_id, "running").await?;
                }
                ApprovalResult::Rejected => {
                    info!("Job {} rejected at step {}", job_id, step_id);
                    return Ok(());
                }
            }
        }

        // Execute the local tool
        let tool_result = local_tools::dispatch_tool(&tool, &args).await;

        // Persist step result
        patch_step_result(client, api_base, token, job_id, &step_id, tool_result).await?;
    }

    // 5. All steps complete
    patch_job_status(client, api_base, token, job_id, "succeeded").await?;
    Ok(())
}

enum ApprovalResult {
    Approved,
    Rejected,
}

// ─── API helpers ──────────────────────────────────────────────────────────────

fn with_auth(builder: RequestBuilder, token: &str) -> RequestBuilder {
    if token.is_empty() {
        builder
    } else {
        builder.bearer_auth(token)
    }
}

async fn poll_queued_jobs(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
) -> Result<Vec<Value>> {
    let req = client.get(format!(
        "{}/api/jobs?source=native&status=queued&limit=10",
        api_base
    ));
    let resp = with_auth(req, token)
        .send()
        .await?
        .json::<Vec<Value>>()
        .await?;
    Ok(resp)
}

async fn dispatch_job_plan(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
) -> Result<Value> {
    let req = client.post(format!("{}/api/jobs/{}/dispatch", api_base, job_id));
    let resp = with_auth(req, token).send().await?;
    if !resp.status().is_success() {
        let status = resp.status();
        let text = resp.text().await.unwrap_or_default();
        return Err(anyhow::anyhow!("dispatch failed {}: {}", status, text));
    }
    Ok(resp.json::<Value>().await?)
}

async fn get_completed_step_ids(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
) -> HashSet<String> {
    let req = client.get(format!("{}/api/jobs/{}", api_base, job_id));
    if let Ok(resp) = with_auth(req, token).send().await {
        if let Ok(job) = resp.json::<Value>().await {
            if let Some(results) = job["result"]["step_results"].as_array() {
                return results
                    .iter()
                    .filter_map(|r| r["step_id"].as_str().map(|s| s.to_string()))
                    .collect();
            }
        }
    }
    HashSet::new()
}

async fn patch_job_status(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
    status: &str,
) -> Result<()> {
    let req = client.patch(format!("{}/api/jobs/{}", api_base, job_id));
    with_auth(req, token)
        .json(&serde_json::json!({ "status": status }))
        .send()
        .await?;
    Ok(())
}

async fn patch_job_status_with_error(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
    error_log: &str,
) -> Result<()> {
    let req = client.patch(format!("{}/api/jobs/{}", api_base, job_id));
    with_auth(req, token)
        .json(&serde_json::json!({ "status": "failed", "error_log": error_log }))
        .send()
        .await?;
    Ok(())
}

async fn wait_for_approval(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
) -> Result<ApprovalResult> {
    loop {
        tokio::time::sleep(tokio::time::Duration::from_secs(3)).await;
        let req = client.get(format!("{}/api/jobs/{}", api_base, job_id));
        match with_auth(req, token).send().await {
            Ok(resp) => {
                if let Ok(job) = resp.json::<Value>().await {
                    match job["status"].as_str().unwrap_or("") {
                        "queued" | "running" => return Ok(ApprovalResult::Approved),
                        "rejected" | "failed" => return Ok(ApprovalResult::Rejected),
                        "needs_approval" => {
                            info!("Still waiting for approval on job {}", job_id);
                        }
                        other => {
                            warn!("Unexpected job status while waiting: {}", other);
                        }
                    }
                }
            }
            Err(e) => warn!("Failed to poll job status: {}", e),
        }
    }
}

/// Read-modify-write to append a step result to job.result.step_results.
async fn patch_step_result(
    client: &reqwest::Client,
    api_base: &str,
    token: &str,
    job_id: &str,
    step_id: &str,
    tool_result: local_tools::ToolResult,
) -> Result<()> {
    // Fetch current job to get existing result (preserves plan + prior step_results)
    let req = client.get(format!("{}/api/jobs/{}", api_base, job_id));
    let current_job = match with_auth(req, token).send().await {
        Ok(resp) => resp.json::<Value>().await.unwrap_or(Value::Null),
        Err(_) => Value::Null,
    };

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

    let req = client.patch(format!("{}/api/jobs/{}", api_base, job_id));
    with_auth(req, token)
        .json(&serde_json::json!({ "result": current_result }))
        .send()
        .await?;
    Ok(())
}
