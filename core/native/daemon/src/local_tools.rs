use serde_json::{json, Value};
use std::time::Duration;
use tracing::info;

pub enum ToolResult {
    Ok(Value),
    Err(String),
}

pub async fn dispatch_tool(tool: &str, args: &Value) -> ToolResult {
    match tool {
        "run_shell" => run_shell(args).await,
        "read_file" => read_file(args).await,
        "write_file" => write_file(args).await,
        "list_dir" => list_dir(args).await,
        "move_file" => move_file(args).await,
        "delete_file" => delete_file(args).await,
        "open_app" => open_app(args).await,
        _ => ToolResult::Err(format!("Unknown tool: {}", tool)),
    }
}

async fn run_shell(args: &Value) -> ToolResult {
    let cmd = match args["cmd"].as_str() {
        Some(c) => c.to_string(),
        None => return ToolResult::Err("run_shell: missing 'cmd'".into()),
    };
    let timeout_secs = args["timeout"].as_u64().unwrap_or(30);
    let cwd = args["cwd"].as_str().map(|s| s.to_string());

    info!("run_shell: {}", cmd);

    #[cfg(target_os = "windows")]
    let mut command = {
        let mut c = tokio::process::Command::new("cmd");
        c.args(["/C", &cmd]);
        c
    };
    #[cfg(not(target_os = "windows"))]
    let mut command = {
        let mut c = tokio::process::Command::new("sh");
        c.args(["-c", &cmd]);
        c
    };

    if let Some(dir) = cwd {
        command.current_dir(&dir);
    }

    match tokio::time::timeout(Duration::from_secs(timeout_secs), command.output()).await {
        Ok(Ok(output)) => ToolResult::Ok(json!({
            "stdout": String::from_utf8_lossy(&output.stdout).to_string(),
            "stderr": String::from_utf8_lossy(&output.stderr).to_string(),
            "exit_code": output.status.code().unwrap_or(-1),
        })),
        Ok(Err(e)) => ToolResult::Err(format!("run_shell error: {}", e)),
        Err(_) => ToolResult::Err(format!("run_shell timed out after {}s", timeout_secs)),
    }
}

async fn read_file(args: &Value) -> ToolResult {
    let path = match args["path"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("read_file: missing 'path'".into()),
    };
    match tokio::fs::read_to_string(path).await {
        Ok(content) => ToolResult::Ok(json!({ "content": content })),
        Err(e) => ToolResult::Err(format!("read_file error: {}", e)),
    }
}

async fn write_file(args: &Value) -> ToolResult {
    let path = match args["path"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("write_file: missing 'path'".into()),
    };
    let content = args["content"].as_str().unwrap_or("");
    match tokio::fs::write(path, content).await {
        Ok(()) => ToolResult::Ok(json!({ "written": true, "path": path })),
        Err(e) => ToolResult::Err(format!("write_file error: {}", e)),
    }
}

async fn list_dir(args: &Value) -> ToolResult {
    let path = match args["path"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("list_dir: missing 'path'".into()),
    };
    let mut read_dir = match tokio::fs::read_dir(path).await {
        Ok(rd) => rd,
        Err(e) => return ToolResult::Err(format!("list_dir error: {}", e)),
    };
    let mut entries = Vec::new();
    loop {
        match read_dir.next_entry().await {
            Ok(Some(entry)) => {
                let name = entry.file_name().to_string_lossy().to_string();
                let is_dir = entry.file_type().await.map(|t| t.is_dir()).unwrap_or(false);
                let size = entry.metadata().await.map(|m| m.len()).unwrap_or(0);
                entries.push(json!({ "name": name, "is_dir": is_dir, "size": size }));
            }
            Ok(None) => break,
            Err(e) => return ToolResult::Err(format!("list_dir entry error: {}", e)),
        }
    }
    ToolResult::Ok(json!({ "entries": entries }))
}

async fn move_file(args: &Value) -> ToolResult {
    let src = match args["src"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("move_file: missing 'src'".into()),
    };
    let dst = match args["dst"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("move_file: missing 'dst'".into()),
    };
    match tokio::fs::rename(src, dst).await {
        Ok(()) => ToolResult::Ok(json!({ "moved": true, "src": src, "dst": dst })),
        Err(e) => ToolResult::Err(format!("move_file error: {}", e)),
    }
}

async fn delete_file(args: &Value) -> ToolResult {
    let path = match args["path"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("delete_file: missing 'path'".into()),
    };
    match tokio::fs::remove_file(path).await {
        Ok(()) => ToolResult::Ok(json!({ "deleted": true, "path": path })),
        Err(e) => ToolResult::Err(format!("delete_file error: {}", e)),
    }
}

async fn open_app(args: &Value) -> ToolResult {
    let name = match args["name"].as_str() {
        Some(n) => n,
        None => return ToolResult::Err("open_app: missing 'name'".into()),
    };
    info!("open_app: {}", name);

    #[cfg(target_os = "windows")]
    {
        match std::process::Command::new("cmd")
            .args(["/C", "start", "", name])
            .spawn()
        {
            Ok(_) => ToolResult::Ok(json!({ "launched": name })),
            Err(e) => ToolResult::Err(format!("open_app error: {}", e)),
        }
    }
    #[cfg(target_os = "macos")]
    {
        match std::process::Command::new("open").arg("-a").arg(name).spawn() {
            Ok(_) => ToolResult::Ok(json!({ "launched": name })),
            Err(e) => ToolResult::Err(format!("open_app error: {}", e)),
        }
    }
    #[cfg(target_os = "linux")]
    {
        match std::process::Command::new(name).spawn() {
            Ok(_) => ToolResult::Ok(json!({ "launched": name })),
            Err(e) => ToolResult::Err(format!("open_app error: {}", e)),
        }
    }
}
