use serde::{Deserialize, Serialize};
use ts_rs::TS;

// ─── Job enums ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
#[ts(export, export_to = "../../shared/bindings/")]
pub enum JobStatus {
    Queued,
    Running,
    NeedsApproval,
    Succeeded,
    Failed,
    Rejected,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, TS)]
#[serde(rename_all = "snake_case")]
#[ts(export, export_to = "../../shared/bindings/")]
pub enum RiskLevel {
    Low,
    Medium,
    High,
    Critical,
}

// ─── Domain structs ───────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../shared/bindings/")]
pub struct Job {
    pub id: String,
    pub user_id: String,
    pub project_id: Option<String>,
    pub source: String,
    #[serde(rename = "type")]
    #[ts(rename = "type")]
    pub job_type: String,
    pub tags: Vec<String>,
    pub status: JobStatus,
    pub risk_level: RiskLevel,
    pub payload: serde_json::Value,
    pub result: Option<serde_json::Value>,
    pub approved_by: Option<String>,
    pub error_log: Option<String>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
    pub updated_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../shared/bindings/")]
pub struct JobApproval {
    pub id: String,
    pub job_id: String,
    pub action_type: String,
    pub policy_mode: String,
    pub expires_at: Option<String>,
    pub decision: Option<String>,
    pub decided_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../shared/bindings/")]
pub struct IntegrationConnection {
    pub id: String,
    pub provider: String,
    pub account_ref: Option<String>,
    pub scopes: Vec<String>,
    pub health_status: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../shared/bindings/")]
pub struct AutomationRule {
    pub id: String,
    pub name: String,
    pub trigger: serde_json::Value,
    pub condition: Option<serde_json::Value>,
    pub action: serde_json::Value,
    pub approval_policy: String,
    pub limit: Option<serde_json::Value>,
    pub is_active: bool,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, TS)]
#[ts(export, export_to = "../../shared/bindings/")]
pub struct WsEvent {
    #[serde(rename = "type")]
    #[ts(rename = "type")]
    pub event_type: String,
    pub data: serde_json::Value,
}

// ─── Type export test (Phase 3: ts-rs bindings generation) ───────────────────
//
// Run `cargo test -p bridge-rs` from core/native/ to regenerate
// TypeScript type files in core/native/shared/bindings/.

#[cfg(test)]
mod tests {
    use super::*;
    use ts_rs::TS;

    #[test]
    fn export_bindings() {
        Job::export_all_to("../../shared/bindings/").unwrap();
        JobApproval::export_all_to("../../shared/bindings/").unwrap();
        IntegrationConnection::export_all_to("../../shared/bindings/").unwrap();
        AutomationRule::export_all_to("../../shared/bindings/").unwrap();
        WsEvent::export_all_to("../../shared/bindings/").unwrap();
    }
}
