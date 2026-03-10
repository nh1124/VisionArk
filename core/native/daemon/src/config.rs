use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use tracing::{info, warn};

/// Runtime configuration for the VisionArk daemon.
///
/// Priority (highest first):
///   1. Environment variables  (`VISIONARK_API_URL`, `VISIONARK_TOKEN`)
///   2. Config file            (`{config_dir}/visionark/config.toml`)
///   3. Compiled-in defaults   (`http://localhost:8000`)
///
/// The config file is shared with the Tauri desktop app, which writes it
/// via the `write_app_config` command.  Both processes use the same path:
///   Windows : %APPDATA%\visionark\config.toml
///   macOS   : ~/Library/Application Support/visionark/config.toml
///   Linux   : ~/.config/visionark/config.toml

const CONFIG_DIR_NAME: &str = "visionark";
const CONFIG_FILE_NAME: &str = "config.toml";
const DEFAULT_API_URL: &str = "http://localhost:8000";

/// Execution safety policy for local tool calls.
///
/// Add a `[policy]` section to config.toml to customise:
///
/// ```toml
/// [policy]
/// shell_enabled  = true          # set false to disable run_shell entirely
/// write_enabled  = true          # set false to block write/move/delete
/// allowed_paths  = []            # empty = no restriction; list roots to restrict
/// max_read_kb    = 0             # 0 = no limit; e.g. 10240 = 10 MB cap
/// dry_run        = false         # true = log but do not execute any tool
/// ```
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct ExecutionPolicy {
    /// Allow shell command execution via run_shell.
    pub shell_enabled: bool,
    /// Allow write_file / move_file / delete_file operations.
    pub write_enabled: bool,
    /// Restrict file ops to these directory roots (empty = no restriction).
    pub allowed_paths: Vec<String>,
    /// Maximum file size in KB for read_file (0 = no limit).
    pub max_read_kb: u64,
    /// If true, log tool calls without actually executing them.
    pub dry_run: bool,
}

impl Default for ExecutionPolicy {
    fn default() -> Self {
        Self {
            shell_enabled: true,
            write_enabled: true,
            allowed_paths: Vec::new(),
            max_read_kb: 0,
            dry_run: false,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct DaemonConfig {
    pub api_url: String,
    /// Bearer token - populated from env var or keyring, never written to disk.
    #[serde(default, skip_serializing)]
    pub token: String,
    /// Job polling interval in seconds (can be overridden per deployment).
    #[serde(default = "default_poll_interval")]
    pub poll_interval_secs: u64,
    /// Local tool execution safety policy.
    #[serde(default)]
    pub policy: ExecutionPolicy,
    /// Registered device ID for pull/claim routing.
    /// Populated by the daemon after calling /api/native/devices/register.
    /// Can also be set via env var VISIONARK_DEVICE_ID or config file.
    #[serde(default)]
    pub device_id: Option<String>,
}

fn default_poll_interval() -> u64 {
    10
}

impl Default for DaemonConfig {
    fn default() -> Self {
        Self {
            api_url: DEFAULT_API_URL.to_string(),
            token: String::new(),
            poll_interval_secs: default_poll_interval(),
            policy: ExecutionPolicy::default(),
            device_id: None,
        }
    }
}

/// Returns the platform-appropriate config file path, or `None` if the OS
/// config directory cannot be determined.
pub fn config_file_path() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join(CONFIG_DIR_NAME).join(CONFIG_FILE_NAME))
}

/// Load configuration.  Never panics - falls back to defaults on any error.
pub fn load() -> DaemonConfig {
    let mut cfg = DaemonConfig::default();

    // -- 1. Read config file ------------------------------------------------
    if let Some(path) = config_file_path() {
        if path.exists() {
            match std::fs::read_to_string(&path) {
                Ok(content) => match toml::from_str::<DaemonConfig>(&content) {
                    Ok(parsed) => {
                        info!("Loaded config from {}", path.display());
                        let parsed_api = parsed.api_url.trim();
                        if !parsed_api.is_empty() {
                            cfg.api_url = parsed_api.to_string();
                        }
                        cfg.poll_interval_secs = parsed.poll_interval_secs;
                        cfg.policy = parsed.policy;
                    }
                    Err(e) => warn!("Config parse error ({}): {}", path.display(), e),
                },
                Err(e) => warn!("Config read error ({}): {}", path.display(), e),
            }
        } else {
            info!("No config file found at {} - using defaults", path.display());
        }
    }

    // -- 2. Environment variable overrides ---------------------------------
    // Env vars allow CI/CD and Docker to override without touching the GUI.
    if let Ok(url) = std::env::var("VISIONARK_API_URL") {
        let url = url.trim().to_string();
        if !url.is_empty() {
            info!("VISIONARK_API_URL env override: {}", url);
            cfg.api_url = url;
        }
    }
    if let Ok(token) = std::env::var("VISIONARK_TOKEN") {
        let token = token.trim().to_string();
        if !token.is_empty() {
            cfg.token = token;
        }
    }
    if let Ok(device_id) = std::env::var("VISIONARK_DEVICE_ID") {
        let device_id = device_id.trim().to_string();
        if !device_id.is_empty() {
            cfg.device_id = Some(device_id);
        }
    }

    cfg
}
