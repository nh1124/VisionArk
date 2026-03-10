use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use tracing::{info, warn};

/// Runtime configuration for the VisionArk daemon.
///
/// Priority (highest first):
///   1. Environment variables  (`VISIONARK_API_URL`, `VISIONARK_TOKEN`, `VISIONARK_DEVICE_ID`)
///   2. Config file            (`{config_dir}/visionark/config.toml`)
///   3. Compiled-in defaults   (`http://localhost:8000`)
///
/// The config file is shared with the Tauri desktop app, which writes it
/// via the `write_app_config` command.  Both processes use the same path:
///   Windows : %APPDATA%\visionark\config.toml
///   macOS   : ~/Library/Application Support/visionark/config.toml
///   Linux   : ~/.config/visionark/config.toml
///
/// Device IDs are stored per server under [device_ids]:
///
/// ```toml
/// api_url = "http://localhost:8000"
///
/// [device_ids]
/// "http://localhost:8000" = "uuid-aaa..."
/// "https://prod.example.com" = "uuid-bbb..."
/// ```

const CONFIG_DIR_NAME: &str = "visionark";
const CONFIG_FILE_NAME: &str = "config.toml";
const DEFAULT_API_URL: &str = "http://localhost:8000";

/// Execution safety policy for local tool calls.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct ExecutionPolicy {
    pub shell_enabled: bool,
    pub write_enabled: bool,
    pub allowed_paths: Vec<String>,
    pub max_read_kb: u64,
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

/// On-disk shape of config.toml (deserialized/serialized).
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
struct RawConfig {
    #[serde(default)]
    api_url: String,
    #[serde(default = "default_poll_interval")]
    poll_interval_secs: u64,
    #[serde(default)]
    policy: ExecutionPolicy,
    /// Per-server device IDs: api_url -> device_id.
    #[serde(default)]
    device_ids: HashMap<String, String>,
}

/// Runtime configuration (includes resolved device_id for the active api_url).
#[derive(Debug, Clone)]
pub struct DaemonConfig {
    pub api_url: String,
    /// Bearer token — populated from env var only, never written to disk.
    pub token: String,
    pub poll_interval_secs: u64,
    pub policy: ExecutionPolicy,
    /// Resolved device ID for the current api_url (runtime only).
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

/// Returns the platform-appropriate config file path.
pub fn config_file_path() -> Option<PathBuf> {
    dirs::config_dir().map(|d| d.join(CONFIG_DIR_NAME).join(CONFIG_FILE_NAME))
}

/// Persist a device_id for the given api_url into the [device_ids] table in
/// config.toml.  Other fields are preserved.  Best-effort — errors are ignored.
pub fn save_device_id(api_url: &str, device_id: &str) {
    let path = match config_file_path() {
        Some(p) => p,
        None => return,
    };
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }

    // Read existing TOML as a generic Value to preserve unknown fields/comments.
    let raw = if path.exists() {
        std::fs::read_to_string(&path).unwrap_or_default()
    } else {
        String::new()
    };

    let mut root: toml::Value = raw
        .parse::<toml::Value>()
        .unwrap_or_else(|_| toml::Value::Table(toml::map::Map::new()));

    if let toml::Value::Table(ref mut root_map) = root {
        // Ensure [device_ids] subtable exists.
        let table = root_map
            .entry("device_ids".to_string())
            .or_insert_with(|| toml::Value::Table(toml::map::Map::new()));

        if let toml::Value::Table(ref mut ids) = table {
            ids.insert(api_url.to_string(), toml::Value::String(device_id.to_string()));
        }

        // Remove the legacy flat `device_id` field if present.
        root_map.remove("device_id");
    }

    if let Ok(serialized) = toml::to_string_pretty(&root) {
        let _ = std::fs::write(&path, serialized);
    }
}

/// Load configuration.  Never panics — falls back to defaults on any error.
pub fn load() -> DaemonConfig {
    let mut cfg = DaemonConfig::default();

    // -- 1. Read config file -------------------------------------------------
    if let Some(path) = config_file_path() {
        if path.exists() {
            match std::fs::read_to_string(&path) {
                Ok(content) => match toml::from_str::<RawConfig>(&content) {
                    Ok(raw) => {
                        info!("Loaded config from {}", path.display());
                        let parsed_api = raw.api_url.trim();
                        if !parsed_api.is_empty() {
                            cfg.api_url = parsed_api.to_string();
                        }
                        cfg.poll_interval_secs = raw.poll_interval_secs;
                        cfg.policy = raw.policy;
                        // Resolve device_id for the active api_url.
                        cfg.device_id = raw.device_ids.get(&cfg.api_url).cloned();
                    }
                    Err(e) => warn!("Config parse error ({}): {}", path.display(), e),
                },
                Err(e) => warn!("Config read error ({}): {}", path.display(), e),
            }
        } else {
            info!("No config file found at {} — using defaults", path.display());
        }
    }

    // -- 2. Environment variable overrides -----------------------------------
    if let Ok(url) = std::env::var("VISIONARK_API_URL") {
        let url = url.trim().to_string();
        if !url.is_empty() {
            info!("VISIONARK_API_URL env override: {}", url);
            // When api_url changes via env, re-resolve device_id from config file.
            if url != cfg.api_url {
                cfg.device_id = load_device_id_for_url(&url);
            }
            cfg.api_url = url;
        }
    }
    if let Ok(token) = std::env::var("VISIONARK_TOKEN") {
        let token = token.trim().to_string();
        if !token.is_empty() {
            cfg.token = token;
        }
    }
    // VISIONARK_DEVICE_ID env var takes highest precedence and bypasses per-server lookup.
    if let Ok(device_id) = std::env::var("VISIONARK_DEVICE_ID") {
        let device_id = device_id.trim().to_string();
        if !device_id.is_empty() {
            cfg.device_id = Some(device_id);
        }
    }

    cfg
}

/// Read the [device_ids] table from config.toml and return the id for `api_url`.
fn load_device_id_for_url(api_url: &str) -> Option<String> {
    let path = config_file_path()?;
    let content = std::fs::read_to_string(&path).ok()?;
    let raw: RawConfig = toml::from_str(&content).ok()?;
    raw.device_ids.get(api_url).cloned()
}
