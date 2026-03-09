use crate::activity;
use crate::config::ExecutionPolicy;
use base64::Engine;
use bridge_rs::http::BridgeClient;
use serde_json::{json, Value};
use std::time::Duration;
use sysinfo::System;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::sync::mpsc;
use tracing::{info, warn};

pub enum ToolResult {
    Ok(Value),
    Err(String),
}

pub async fn dispatch_tool(
    policy: &ExecutionPolicy,
    tool: &str,
    args: &Value,
    client: &BridgeClient,
    run_id: &str,
    exec_id: &str,
    device_id: &str,
) -> ToolResult {
    // Dry-run: log without executing
    if policy.dry_run {
        info!("[dry-run] tool={} args={}", tool, args);
        return ToolResult::Ok(json!({ "dry_run": true, "tool": tool, "args": args }));
    }

    match tool {
        "run_shell" => {
            if !policy.shell_enabled {
                return ToolResult::Err(
                    "run_shell is disabled by execution policy (shell_enabled = false)".into(),
                );
            }
            run_shell(args, client, exec_id, device_id).await
        }
        "read_file" => {
            let path = args["path"].as_str().unwrap_or("");
            if !is_allowed_path(path, &policy.allowed_paths) {
                return ToolResult::Err(format!(
                    "read_file: path '{}' is outside allowed directories",
                    path
                ));
            }
            read_file(args, policy.max_read_kb).await
        }
        "write_file" => {
            if !policy.write_enabled {
                return ToolResult::Err(
                    "write_file is disabled by execution policy (write_enabled = false)".into(),
                );
            }
            let path = args["path"].as_str().unwrap_or("");
            if !is_allowed_path(path, &policy.allowed_paths) {
                return ToolResult::Err(format!(
                    "write_file: path '{}' is outside allowed directories",
                    path
                ));
            }
            write_file(args).await
        }
        "list_dir" => {
            let path = args["path"].as_str().unwrap_or("");
            if !is_allowed_path(path, &policy.allowed_paths) {
                return ToolResult::Err(format!(
                    "list_dir: path '{}' is outside allowed directories",
                    path
                ));
            }
            list_dir(args).await
        }
        "move_file" => {
            if !policy.write_enabled {
                return ToolResult::Err(
                    "move_file is disabled by execution policy (write_enabled = false)".into(),
                );
            }
            let src = args["src"].as_str().unwrap_or("");
            let dst = args["dst"].as_str().unwrap_or("");
            if !is_allowed_path(src, &policy.allowed_paths)
                || !is_allowed_path(dst, &policy.allowed_paths)
            {
                return ToolResult::Err(format!(
                    "move_file: path(s) outside allowed directories (src='{}', dst='{}')",
                    src, dst
                ));
            }
            move_file(args).await
        }
        "delete_file" => {
            if !policy.write_enabled {
                return ToolResult::Err(
                    "delete_file is disabled by execution policy (write_enabled = false)".into(),
                );
            }
            let path = args["path"].as_str().unwrap_or("");
            if !is_allowed_path(path, &policy.allowed_paths) {
                return ToolResult::Err(format!(
                    "delete_file: path '{}' is outside allowed directories",
                    path
                ));
            }
            delete_file(args).await
        }
        "open_app" => open_app(args).await,

        // ── Phase 1 tools ────────────────────────────────────────────────
        "get_native_environment" => get_native_environment().await,
        "get_active_window"     => get_active_window().await,
        "list_running_apps"     => list_running_apps().await,
        "launch_app"            => launch_app(args).await,
        "capture_screen"        => capture_screen(args).await,

        // ── Phase 2: Window control ──────────────────────────────────────
        "focus_window"  => focus_window(args).await,
        "close_window"  => close_window(args).await,

        // ── Phase 2: Mouse / Keyboard ────────────────────────────────────
        "mouse_move"     => mouse_move(args).await,
        "mouse_click"    => mouse_click(args).await,
        "mouse_drag"     => mouse_drag(args).await,
        "keyboard_type"  => keyboard_type(args).await,
        "keyboard_hotkey" => keyboard_hotkey(args).await,

        // ── Phase 3: Screen understanding ────────────────────────────────
        "capture_window" => capture_window(args).await,
        "find_on_screen" => find_on_screen(args).await,

        _ => ToolResult::Err(format!("Unknown tool: {}", tool)),
    }
}

/// Returns true if `path` is allowed by `allowed_paths`.
fn is_allowed_path(path: &str, allowed: &[String]) -> bool {
    if allowed.is_empty() {
        return true;
    }
    let target = std::path::Path::new(path);
    allowed
        .iter()
        .any(|a| target.starts_with(std::path::Path::new(a)))
}

// ── Helper: focus guard (expected_window safety check) ──────────────────────

fn check_expected_window(args: &Value) -> Result<(), String> {
    if let Some(expected) = args.get("expected_window").and_then(|v| v.as_str()) {
        if let Some(info) = activity::get_active_window_info() {
            if !info.title.to_lowercase().contains(&expected.to_lowercase())
                && !info.exe_name.to_lowercase().contains(&expected.to_lowercase())
            {
                return Err(format!(
                    "Focus guard: expected '{}' but foreground is '{}' ({}). Aborting.",
                    expected, info.title, info.exe_name
                ));
            }
        } else {
            return Err("Focus guard: no foreground window detected. Aborting.".into());
        }
    }
    Ok(())
}

fn window_info_to_json(w: &activity::WindowInfo) -> Value {
    json!({
        "title": w.title,
        "pid": w.pid,
        "exe_name": w.exe_name,
        "bounds": { "x": w.x, "y": w.y, "width": w.width, "height": w.height },
    })
}

/// Return the tail of `s` capped by bytes while preserving UTF-8 boundaries.
/// This avoids panics from slicing at non-character boundaries.
fn utf8_safe_tail(s: &str, max_bytes: usize) -> String {
    if s.len() <= max_bytes {
        return s.to_string();
    }
    let mut start = s.len().saturating_sub(max_bytes);
    while start < s.len() && !s.is_char_boundary(start) {
        start += 1;
    }
    s[start..].to_string()
}

// ════════════════════════════════════════════════════════════════════════════════
// Existing tools (unchanged)
// ════════════════════════════════════════════════════════════════════════════════

async fn run_shell(args: &Value, client: &BridgeClient, exec_id: &str, device_id: &str) -> ToolResult {
    let timeout_secs = args["timeout"].as_u64().unwrap_or(30);
    let cwd = args["cwd"].as_str().map(|s| s.to_string());

    // completion_markers: when any stdout line CONTAINS one of these strings,
    // stdin is closed (EOF sent) so the child process can exit cleanly.
    // Used by codex_run to detect "tokens used" — codex's last output line.
    let completion_markers: Vec<String> = args["completion_markers"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_lowercase()))
                .collect()
        })
        .unwrap_or_default();

    // When `argv` is provided, spawn directly without a shell to avoid all
    // platform-specific quoting issues (cmd.exe on Windows mangles quoted args).
    let mut command = if let Some(argv_arr) = args["argv"].as_array() {
        let tokens: Vec<&str> = argv_arr.iter().filter_map(|v| v.as_str()).collect();
        if tokens.is_empty() {
            return ToolResult::Err("run_shell: argv array is empty".into());
        }
        info!("run_shell (argv): {:?}", tokens);
        #[cfg(target_os = "windows")]
        {
            let mut c = tokio::process::Command::new("cmd");
            c.arg("/C");
            c.args(&tokens);
            c
        }
        #[cfg(not(target_os = "windows"))]
        {
            let mut c = tokio::process::Command::new(tokens[0]);
            c.args(&tokens[1..]);
            c
        }
    } else {
        let cmd = match args["cmd"].as_str() {
            Some(c) => c.to_string(),
            None => return ToolResult::Err("run_shell: missing 'cmd' or 'argv'".into()),
        };
        info!("run_shell (cmd): {}", cmd);
        #[cfg(target_os = "windows")]
        {
            let mut c = tokio::process::Command::new("cmd");
            c.args(["/C", &cmd]);
            c
        }
        #[cfg(not(target_os = "windows"))]
        {
            let mut c = tokio::process::Command::new("sh");
            c.args(["-c", &cmd]);
            c
        }
    };

    if let Some(dir) = &cwd {
        command.current_dir(dir);
    }

    // Pipe all stdio.
    // stdin stays open so the agent can send input via codex_approval.
    // Piped stdout/stderr allow line-by-line streaming to the API.
    command.stdin(std::process::Stdio::piped());
    command.stdout(std::process::Stdio::piped());
    command.stderr(std::process::Stdio::piped());
    command.kill_on_drop(true);

    let mut child = match command.spawn() {
        Ok(c) => c,
        Err(e) => return ToolResult::Err(format!("run_shell error: {}", e)),
    };

    let child_pid = child.id();
    let mut stdin_writer = child.stdin.take();
    let stdout_handle = child.stdout.take().unwrap();
    let stderr_handle = child.stderr.take().unwrap();

    // ── Background readers ──────────────────────────────────────────────────
    let (out_tx, mut out_rx) = mpsc::channel::<String>(512);
    let (err_tx, mut err_rx) = mpsc::channel::<String>(512);

    tokio::spawn(async move {
        let mut reader = BufReader::new(stdout_handle).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            if out_tx.send(line).await.is_err() { break; }
        }
    });
    tokio::spawn(async move {
        let mut reader = BufReader::new(stderr_handle).lines();
        while let Ok(Some(line)) = reader.next_line().await {
            if err_tx.send(line).await.is_err() { break; }
        }
    });

    // ── Background child waiter ─────────────────────────────────────────────
    // We use a channel rather than child.wait() in the select loop so that
    // orphaned grandchildren (which keep the stdout/stderr pipe handles open
    // on Windows) do NOT prevent us from finishing once the top-level child exits.
    let (exit_tx, mut exit_rx) = mpsc::channel::<i32>(1);
    tokio::spawn(async move {
        let code = child.wait().await
            .ok().and_then(|s| s.code()).unwrap_or(-1);
        let _ = exit_tx.send(code).await;
    });

    // ── Scheduled kill channel ──────────────────────────────────────────────
    // Used by completion_markers: after marker fires we close stdin, then
    // wait 3 s and kill the entire process tree.  Node.js may refuse to exit
    // even after EOF if it has live child processes (python.exe, git.exe, …)
    // registered in its event loop.  taskkill /F /T is the only reliable fix.
    let (kill_tx, mut kill_rx) = mpsc::channel::<()>(1);
    let mut kill_scheduled = false;

    // ── Streaming loop ──────────────────────────────────────────────────────
    let mut full_stdout = String::new();
    let mut full_stderr = String::new();
    let mut pending_patch = String::new();
    let mut stdout_closed = false;
    let mut stderr_closed = false;
    let mut exit_code_opt: Option<i32> = None;

    let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);
    let mut patch_tick = tokio::time::interval(Duration::from_secs(3));
    let mut stdin_tick = tokio::time::interval(Duration::from_secs(2));
    patch_tick.tick().await; // consume first tick immediately
    stdin_tick.tick().await;

    'main: loop {
        if stdout_closed && stderr_closed {
            break;
        }

        tokio::select! {
            msg = out_rx.recv(), if !stdout_closed => {
                match msg {
                    Some(line) => {
                        full_stdout.push_str(&line);
                        full_stdout.push('\n');
                        pending_patch.push_str(&line);
                        pending_patch.push('\n');

                        // Completion marker: close stdin and schedule a forced kill.
                        // Closing stdin sends EOF to codex's readline, but node.js
                        // may keep running if child processes (python.exe, git.exe …)
                        // are still alive in its event loop.  We schedule taskkill
                        // /F /T in 3 s to kill the entire tree after output has flushed.
                        if !completion_markers.is_empty() && !kill_scheduled {
                            let line_lc = line.trim().to_lowercase();
                            if completion_markers.iter().any(|m| line_lc.contains(m.as_str())) {
                                info!("run_shell: completion marker '{}' — closing stdin, kill tree in 3s (exec={})", line.trim(), exec_id);
                                drop(stdin_writer.take());
                                kill_scheduled = true;
                                let ktx = kill_tx.clone();
                                tokio::spawn(async move {
                                    tokio::time::sleep(Duration::from_secs(3)).await;
                                    let _ = ktx.send(()).await;
                                });
                            }
                        }
                    }
                    None => { stdout_closed = true; }
                }
            }

            msg = err_rx.recv(), if !stderr_closed => {
                match msg {
                    Some(line) => {
                        full_stderr.push_str(&line);
                        full_stderr.push('\n');

                        // Also check completion_markers against stderr.
                        // codex outputs "tokens used" to stderr, not stdout.
                        if !completion_markers.is_empty() && !kill_scheduled {
                            let line_lc = line.trim().to_lowercase();
                            if completion_markers.iter().any(|m| line_lc.contains(m.as_str())) {
                                info!("run_shell: completion marker '{}' in stderr — closing stdin, kill tree in 3s (exec={})", line.trim(), exec_id);
                                drop(stdin_writer.take());
                                kill_scheduled = true;
                                let ktx = kill_tx.clone();
                                tokio::spawn(async move {
                                    tokio::time::sleep(Duration::from_secs(3)).await;
                                    let _ = ktx.send(()).await;
                                });
                            }
                        }
                    }
                    None => { stderr_closed = true; }
                }
            }

            _ = patch_tick.tick() => {
                if !exec_id.is_empty() && !pending_patch.is_empty() {
                    // Keep last 20 KB in the DB field
                    let stored = if full_stdout.len() > 20_480 {
                        utf8_safe_tail(&full_stdout, 20_480)
                    } else {
                        full_stdout.clone()
                    };
                    let _ = client
                        .patch_ignore(
                            &format!("/api/runs/executions/{}/stream?device_id={}", exec_id, device_id),
                            &serde_json::json!({ "stdout": stored }),
                        )
                        .await;
                    pending_patch.clear();
                }
            }

            _ = stdin_tick.tick() => {
                // Poll for agent-enqueued stdin
                if !exec_id.is_empty() {
                    if let Ok(val) = client
                        .get_value(&format!("/api/runs/executions/{}/stdin?device_id={}", exec_id, device_id))
                        .await
                    {
                        if let Some(pending) = val["pending"].as_array() {
                            for item in pending {
                                if let Some(text) = item.as_str() {
                                    if let Some(ref mut w) = stdin_writer {
                                        let _ = w.write_all(text.as_bytes()).await;
                                        info!("run_shell: wrote {} bytes to stdin (exec={})", text.len(), exec_id);
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Scheduled kill: completion marker fired 3 s ago — force-kill the tree.
            // node.exe may still be running (child processes keeping event loop alive).
            _ = kill_rx.recv(), if exit_code_opt.is_none() => {
                info!("run_shell: killing process tree (exec={})", exec_id);
                #[cfg(target_os = "windows")]
                if let Some(pid) = child_pid {
                    let _ = tokio::process::Command::new("taskkill")
                        .args(["/F", "/T", "/PID", &pid.to_string()])
                        .stdin(std::process::Stdio::null())
                        .stdout(std::process::Stdio::null())
                        .stderr(std::process::Stdio::null())
                        .spawn();
                }
                #[cfg(not(target_os = "windows"))]
                if let Some(pid) = child_pid {
                    let _ = tokio::process::Command::new("kill")
                        .args(["-TERM", &pid.to_string()])
                        .spawn();
                }
                // exit_rx fires on the next iteration when child.wait() returns.
            }

            // Primary exit path: top-level child process has exited.
            // On Windows, orphaned grandchildren may still hold the stdout/stderr
            // pipe handles open, so we cannot rely on stdout_closed/stderr_closed
            // alone. Drain remaining buffered output for up to 1 s then return.
            code = exit_rx.recv() => {
                exit_code_opt = Some(code.unwrap_or(-1));
                drop(stdin_writer.take());
                info!("run_shell: child exited (code={:?}, exec={})", exit_code_opt, exec_id);

                let drain_until = tokio::time::Instant::now() + Duration::from_millis(1000);
                loop {
                    if stdout_closed && stderr_closed { break; }
                    tokio::select! {
                        msg = out_rx.recv(), if !stdout_closed => {
                            match msg {
                                Some(line) => { full_stdout.push_str(&line); full_stdout.push('\n'); }
                                None => { stdout_closed = true; }
                            }
                        }
                        msg = err_rx.recv(), if !stderr_closed => {
                            match msg {
                                Some(line) => { full_stderr.push_str(&line); full_stderr.push('\n'); }
                                None => { stderr_closed = true; }
                            }
                        }
                        _ = tokio::time::sleep_until(drain_until) => { break; }
                    }
                }
                break 'main;
            }

            _ = tokio::time::sleep_until(deadline) => {
                drop(stdin_writer.take());
                #[cfg(target_os = "windows")]
                if let Some(pid) = child_pid {
                    let _ = tokio::process::Command::new("taskkill")
                        .args(["/F", "/T", "/PID", &pid.to_string()])
                        .stdin(std::process::Stdio::null())
                        .stdout(std::process::Stdio::null())
                        .stderr(std::process::Stdio::null())
                        .spawn();
                }
                return ToolResult::Err(format!("run_shell timed out after {}s", timeout_secs));
            }
        }
    }

    // If we exited via stdout/stderr closing (not via exit_rx), collect exit code.
    let exit_code = match exit_code_opt {
        Some(ec) => ec,
        None => {
            match tokio::time::timeout(
                Duration::from_secs(5),
                exit_rx.recv(),
            ).await {
                Ok(Some(ec)) => ec,
                _ => -1,
            }
        }
    };

    // Final stdout patch
    if !exec_id.is_empty() {
        let stored = if full_stdout.len() > 20_480 {
            utf8_safe_tail(&full_stdout, 20_480)
        } else {
            full_stdout.clone()
        };
        let _ = client
            .patch_ignore(
                &format!("/api/runs/executions/{}/stream?device_id={}", exec_id, device_id),
                &serde_json::json!({ "stdout": stored }),
            )
            .await;
    }

    ToolResult::Ok(json!({
        "stdout": full_stdout,
        "stderr": full_stderr,
        "exit_code": exit_code,
    }))
}

async fn read_file(args: &Value, max_read_kb: u64) -> ToolResult {
    let path = match args["path"].as_str() {
        Some(p) => p,
        None => return ToolResult::Err("read_file: missing 'path'".into()),
    };
    if max_read_kb > 0 {
        match tokio::fs::metadata(path).await {
            Ok(meta) => {
                let size_kb = meta.len() / 1024;
                if size_kb > max_read_kb {
                    return ToolResult::Err(format!(
                        "read_file: file size {}KB exceeds limit {}KB",
                        size_kb, max_read_kb
                    ));
                }
            }
            Err(e) => return ToolResult::Err(format!("read_file metadata error: {}", e)),
        }
    }
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
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    {
        ToolResult::Err("open_app: unsupported platform".into())
    }
}

// ════════════════════════════════════════════════════════════════════════════════
// Phase 1 tools
// ════════════════════════════════════════════════════════════════════════════════

async fn get_native_environment() -> ToolResult {
    info!("get_native_environment");
    let mut sys = System::new_all();
    sys.refresh_all();

    let os_name = System::name().unwrap_or_else(|| "unknown".into());
    let os_version = System::os_version().unwrap_or_else(|| "unknown".into());
    let kernel = System::kernel_version().unwrap_or_else(|| "unknown".into());
    let host = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown".into());
    let arch = std::env::consts::ARCH;

    let cpus = sys.cpus();
    let cpu_name = cpus.first().map(|c| c.brand().to_string()).unwrap_or_default();
    let cpu_count = cpus.len();
    let total_memory_mb = sys.total_memory() / (1024 * 1024);
    let used_memory_mb = sys.used_memory() / (1024 * 1024);
    let available_memory_mb = sys.available_memory() / (1024 * 1024);

    let disks = sysinfo::Disks::new_with_refreshed_list();
    let disk_info: Vec<Value> = disks.iter().map(|d| {
        json!({
            "mount": d.mount_point().to_string_lossy(),
            "total_gb": d.total_space() / (1024 * 1024 * 1024),
            "available_gb": d.available_space() / (1024 * 1024 * 1024),
            "fs": d.file_system().to_string_lossy(),
        })
    }).collect();

    let tz = iana_time_zone::get_timezone().unwrap_or_else(|_| "unknown".into());
    let monitors = screenshots::Screen::all().map(|s| s.len()).unwrap_or(0);
    let user = std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_else(|_| "unknown".into());
    let shell = if cfg!(target_os = "windows") {
        std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into())
    } else {
        std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".into())
    };

    // Permissions / admin check
    let is_admin = is_elevated();

    ToolResult::Ok(json!({
        "os": os_name,
        "os_version": os_version,
        "kernel": kernel,
        "arch": arch,
        "hostname": host,
        "user": user,
        "shell": shell,
        "timezone": tz,
        "cpu": cpu_name,
        "cpu_count": cpu_count,
        "total_memory_mb": total_memory_mb,
        "used_memory_mb": used_memory_mb,
        "available_memory_mb": available_memory_mb,
        "disks": disk_info,
        "monitor_count": monitors,
        "is_admin": is_admin,
    }))
}

fn is_elevated() -> bool {
    #[cfg(target_os = "windows")]
    {
        // Simple check: try to read a protected registry path
        std::process::Command::new("net")
            .args(["session"])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }
    #[cfg(not(target_os = "windows"))]
    {
        unsafe { libc::getuid() == 0 }
    }
}

async fn get_active_window() -> ToolResult {
    info!("get_active_window");
    match activity::get_active_window_info() {
        Some(info) => ToolResult::Ok(window_info_to_json(&info)),
        None => ToolResult::Ok(json!({
            "title": null,
            "pid": null,
            "exe_name": null,
            "bounds": null,
            "note": "No active window detected",
        })),
    }
}

async fn list_running_apps() -> ToolResult {
    info!("list_running_apps");
    let mut sys = System::new();
    sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);

    let mut apps: Vec<Value> = sys.processes().iter().map(|(pid, proc)| {
        json!({
            "pid": pid.as_u32(),
            "name": proc.name().to_string_lossy(),
        })
    }).collect();

    apps.sort_by(|a, b| {
        let na = a["name"].as_str().unwrap_or("");
        let nb = b["name"].as_str().unwrap_or("");
        na.to_lowercase().cmp(&nb.to_lowercase())
    });

    ToolResult::Ok(json!({ "count": apps.len(), "processes": apps }))
}

async fn launch_app(args: &Value) -> ToolResult {
    let name = match args["name"].as_str() {
        Some(n) => n,
        None => return ToolResult::Err("launch_app: missing 'name'".into()),
    };
    let timeout_secs = args["timeout"].as_u64().unwrap_or(5);
    let wait_for_process = args["wait"].as_bool().unwrap_or(true);

    info!("launch_app: {} (timeout={}s)", name, timeout_secs);

    #[cfg(target_os = "windows")]
    let launch_result = std::process::Command::new("cmd")
        .args(["/C", "start", "", name])
        .spawn();
    #[cfg(target_os = "macos")]
    let launch_result = std::process::Command::new("open").arg("-a").arg(name).spawn();
    #[cfg(target_os = "linux")]
    let launch_result = std::process::Command::new(name).spawn();
    #[cfg(not(any(target_os = "windows", target_os = "macos", target_os = "linux")))]
    let launch_result: Result<std::process::Child, std::io::Error> =
        Err(std::io::Error::new(std::io::ErrorKind::Unsupported, "unsupported platform"));

    if let Err(e) = launch_result {
        return ToolResult::Err(format!("launch_app error: {}", e));
    }

    if !wait_for_process {
        return ToolResult::Ok(json!({
            "launched": name, "verified": false,
            "note": "Launched without waiting for verification",
        }));
    }

    let name_lower = name.to_lowercase();
    let deadline = tokio::time::Instant::now() + Duration::from_secs(timeout_secs);
    while tokio::time::Instant::now() < deadline {
        tokio::time::sleep(Duration::from_millis(500)).await;
        let mut sys = System::new();
        sys.refresh_processes(sysinfo::ProcessesToUpdate::All, true);
        if sys.processes().values().any(|p| {
            p.name().to_string_lossy().to_lowercase().contains(&name_lower)
        }) {
            return ToolResult::Ok(json!({ "launched": name, "verified": true }));
        }
    }

    ToolResult::Ok(json!({
        "launched": name, "verified": false,
        "note": format!("Process not found within {}s", timeout_secs),
    }))
}

async fn capture_screen(args: &Value) -> ToolResult {
    let monitor_idx = args["monitor"].as_u64().unwrap_or(0) as usize;
    info!("capture_screen: monitor={}", monitor_idx);

    let screens = match screenshots::Screen::all() {
        Ok(s) => s,
        Err(e) => return ToolResult::Err(format!("capture_screen: failed to list screens: {}", e)),
    };
    if screens.is_empty() {
        return ToolResult::Err("capture_screen: no screens found".into());
    }
    let screen = if monitor_idx < screens.len() {
        &screens[monitor_idx]
    } else {
        warn!("capture_screen: monitor {} not found, using primary", monitor_idx);
        &screens[0]
    };

    let capture = match screen.capture() {
        Ok(img) => img,
        Err(e) => return ToolResult::Err(format!("capture_screen: capture failed: {}", e)),
    };

    let w = capture.width();
    let h = capture.height();
    let data = capture.into_raw();
    encode_capture_to_base64_raw(w, h, data)
}

// ════════════════════════════════════════════════════════════════════════════════
// Phase 2: Window control
// ════════════════════════════════════════════════════════════════════════════════

async fn focus_window(args: &Value) -> ToolResult {
    let title = args["title"].as_str();
    let pid = args["pid"].as_u64().map(|p| p as u32);
    let exe = args["exe_name"].as_str();

    if title.is_none() && pid.is_none() && exe.is_none() {
        return ToolResult::Err("focus_window: at least one of title, pid, exe_name is required".into());
    }

    info!("focus_window: title={:?} pid={:?} exe={:?}", title, pid, exe);

    match activity::focus_window(title, pid, exe) {
        Some(w) => ToolResult::Ok(json!({
            "focused": true,
            "window": window_info_to_json(&w),
        })),
        None => ToolResult::Err("focus_window: no matching window found".into()),
    }
}

async fn close_window(args: &Value) -> ToolResult {
    let title = args["title"].as_str();
    let pid = args["pid"].as_u64().map(|p| p as u32);
    let exe = args["exe_name"].as_str();
    let force = args["force"].as_bool().unwrap_or(false);

    if title.is_none() && pid.is_none() && exe.is_none() {
        return ToolResult::Err("close_window: at least one of title, pid, exe_name is required".into());
    }

    info!("close_window: title={:?} pid={:?} exe={:?} force={}", title, pid, exe, force);

    match activity::close_window(title, pid, exe, force) {
        Some(w) => ToolResult::Ok(json!({
            "closed": true,
            "force": force,
            "window": window_info_to_json(&w),
        })),
        None => ToolResult::Err("close_window: no matching window found".into()),
    }
}

// ════════════════════════════════════════════════════════════════════════════════
// Phase 2: Mouse / Keyboard
// ════════════════════════════════════════════════════════════════════════════════

async fn mouse_move(args: &Value) -> ToolResult {
    let x = match args["x"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_move: missing 'x'".into()),
    };
    let y = match args["y"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_move: missing 'y'".into()),
    };
    let relative = args["relative"].as_bool().unwrap_or(false);

    if let Err(e) = check_expected_window(args) {
        return ToolResult::Err(e);
    }

    info!("mouse_move: x={} y={} relative={}", x, y, relative);

    use enigo::{Enigo, Mouse, Settings, Coordinate};
    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => return ToolResult::Err(format!("mouse_move: enigo init error: {}", e)),
    };

    let coord = if relative { Coordinate::Rel } else { Coordinate::Abs };
    if let Err(e) = enigo.move_mouse(x, y, coord) {
        return ToolResult::Err(format!("mouse_move error: {}", e));
    }

    ToolResult::Ok(json!({ "moved": true, "x": x, "y": y, "relative": relative }))
}

async fn mouse_click(args: &Value) -> ToolResult {
    let button_str = args["button"].as_str().unwrap_or("left");
    let x = args["x"].as_i64();
    let y = args["y"].as_i64();
    let double = args["double"].as_bool().unwrap_or(false);

    if let Err(e) = check_expected_window(args) {
        return ToolResult::Err(e);
    }

    info!("mouse_click: button={} double={} x={:?} y={:?}", button_str, double, x, y);

    use enigo::{Enigo, Mouse, Button, Settings, Coordinate};
    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => return ToolResult::Err(format!("mouse_click: enigo init error: {}", e)),
    };

    let button = match button_str {
        "right" => Button::Right,
        "middle" => Button::Middle,
        _ => Button::Left,
    };

    // Move first if coordinates specified
    if let (Some(cx), Some(cy)) = (x, y) {
        if let Err(e) = enigo.move_mouse(cx as i32, cy as i32, Coordinate::Abs) {
            return ToolResult::Err(format!("mouse_click move error: {}", e));
        }
        std::thread::sleep(Duration::from_millis(50));
    }

    if let Err(e) = enigo.button(button, enigo::Direction::Click) {
        return ToolResult::Err(format!("mouse_click error: {}", e));
    }
    if double {
        std::thread::sleep(Duration::from_millis(50));
        if let Err(e) = enigo.button(button, enigo::Direction::Click) {
            return ToolResult::Err(format!("mouse_click double error: {}", e));
        }
    }

    ToolResult::Ok(json!({
        "clicked": true, "button": button_str, "double": double,
        "x": x, "y": y,
    }))
}

async fn mouse_drag(args: &Value) -> ToolResult {
    let from_x = match args["from_x"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_drag: missing 'from_x'".into()),
    };
    let from_y = match args["from_y"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_drag: missing 'from_y'".into()),
    };
    let to_x = match args["to_x"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_drag: missing 'to_x'".into()),
    };
    let to_y = match args["to_y"].as_i64() {
        Some(v) => v as i32,
        None => return ToolResult::Err("mouse_drag: missing 'to_y'".into()),
    };
    let button_str = args["button"].as_str().unwrap_or("left");

    if let Err(e) = check_expected_window(args) {
        return ToolResult::Err(e);
    }

    info!("mouse_drag: ({},{}) -> ({},{}) button={}", from_x, from_y, to_x, to_y, button_str);

    use enigo::{Enigo, Mouse, Button, Settings, Coordinate};
    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => return ToolResult::Err(format!("mouse_drag: enigo init error: {}", e)),
    };

    let button = match button_str {
        "right" => Button::Right,
        "middle" => Button::Middle,
        _ => Button::Left,
    };

    // Move to start
    if let Err(e) = enigo.move_mouse(from_x, from_y, Coordinate::Abs) {
        return ToolResult::Err(format!("mouse_drag move_to_start error: {}", e));
    }
    std::thread::sleep(Duration::from_millis(50));

    // Press
    if let Err(e) = enigo.button(button, enigo::Direction::Press) {
        return ToolResult::Err(format!("mouse_drag press error: {}", e));
    }
    std::thread::sleep(Duration::from_millis(50));

    // Move to end
    if let Err(e) = enigo.move_mouse(to_x, to_y, Coordinate::Abs) {
        return ToolResult::Err(format!("mouse_drag move_to_end error: {}", e));
    }
    std::thread::sleep(Duration::from_millis(50));

    // Release
    if let Err(e) = enigo.button(button, enigo::Direction::Release) {
        return ToolResult::Err(format!("mouse_drag release error: {}", e));
    }

    ToolResult::Ok(json!({
        "dragged": true, "from": [from_x, from_y], "to": [to_x, to_y], "button": button_str,
    }))
}

async fn keyboard_type(args: &Value) -> ToolResult {
    let text = match args["text"].as_str() {
        Some(t) => t.to_string(),
        None => return ToolResult::Err("keyboard_type: missing 'text'".into()),
    };

    if let Err(e) = check_expected_window(args) {
        return ToolResult::Err(e);
    }

    info!("keyboard_type: {} chars", text.len());

    use enigo::{Enigo, Keyboard, Settings};
    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => return ToolResult::Err(format!("keyboard_type: enigo init error: {}", e)),
    };

    if let Err(e) = enigo.text(&text) {
        return ToolResult::Err(format!("keyboard_type error: {}", e));
    }

    ToolResult::Ok(json!({ "typed": true, "length": text.len() }))
}

async fn keyboard_hotkey(args: &Value) -> ToolResult {
    let keys = match args["keys"].as_array() {
        Some(k) => k.iter().filter_map(|v| v.as_str()).collect::<Vec<_>>(),
        None => return ToolResult::Err("keyboard_hotkey: missing 'keys' array".into()),
    };
    if keys.is_empty() {
        return ToolResult::Err("keyboard_hotkey: keys array is empty".into());
    }

    if let Err(e) = check_expected_window(args) {
        return ToolResult::Err(e);
    }

    info!("keyboard_hotkey: {:?}", keys);

    use enigo::{Enigo, Keyboard, Key, Settings};
    let mut enigo = match Enigo::new(&Settings::default()) {
        Ok(e) => e,
        Err(e) => return ToolResult::Err(format!("keyboard_hotkey: enigo init error: {}", e)),
    };

    let parsed: Vec<Key> = keys.iter().map(|k| str_to_key(k)).collect();

    // Press all keys
    for key in &parsed {
        if let Err(e) = enigo.key(*key, enigo::Direction::Press) {
            return ToolResult::Err(format!("keyboard_hotkey press error: {}", e));
        }
        std::thread::sleep(Duration::from_millis(20));
    }

    // Release in reverse order
    for key in parsed.iter().rev() {
        if let Err(e) = enigo.key(*key, enigo::Direction::Release) {
            return ToolResult::Err(format!("keyboard_hotkey release error: {}", e));
        }
    }

    let key_names: Vec<String> = keys.iter().map(|s| s.to_string()).collect();
    ToolResult::Ok(json!({ "hotkey": true, "keys": key_names }))
}

fn str_to_key(s: &str) -> enigo::Key {
    use enigo::Key;
    match s.to_lowercase().as_str() {
        "ctrl" | "control" => Key::Control,
        "alt" => Key::Alt,
        "shift" => Key::Shift,
        "meta" | "win" | "super" | "command" | "cmd" => Key::Meta,
        "tab" => Key::Tab,
        "return" | "enter" => Key::Return,
        "escape" | "esc" => Key::Escape,
        "space" => Key::Space,
        "backspace" => Key::Backspace,
        "delete" | "del" => Key::Delete,
        "up" => Key::UpArrow,
        "down" => Key::DownArrow,
        "left" => Key::LeftArrow,
        "right" => Key::RightArrow,
        "home" => Key::Home,
        "end" => Key::End,
        "pageup" => Key::PageUp,
        "pagedown" => Key::PageDown,
        "f1" => Key::F1,
        "f2" => Key::F2,
        "f3" => Key::F3,
        "f4" => Key::F4,
        "f5" => Key::F5,
        "f6" => Key::F6,
        "f7" => Key::F7,
        "f8" => Key::F8,
        "f9" => Key::F9,
        "f10" => Key::F10,
        "f11" => Key::F11,
        "f12" => Key::F12,
        other => {
            if let Some(ch) = other.chars().next() {
                Key::Unicode(ch)
            } else {
                Key::Unicode(' ')
            }
        }
    }
}

// ════════════════════════════════════════════════════════════════════════════════
// Phase 3: Screen understanding
// ════════════════════════════════════════════════════════════════════════════════

async fn capture_window(args: &Value) -> ToolResult {
    let title = args["title"].as_str();
    let pid = args["pid"].as_u64().map(|p| p as u32);
    let exe = args["exe_name"].as_str();

    if title.is_none() && pid.is_none() && exe.is_none() {
        return ToolResult::Err(
            "capture_window: at least one of title, pid, exe_name is required".into(),
        );
    }

    info!("capture_window: title={:?} pid={:?} exe={:?}", title, pid, exe);

    let (wx, wy, ww, wh, win_info) = match activity::get_window_rect(title, pid, exe) {
        Some(r) => r,
        None => return ToolResult::Err("capture_window: no matching window found".into()),
    };

    // Use screenshots crate to capture a specific region
    let screens = match screenshots::Screen::all() {
        Ok(s) => s,
        Err(e) => return ToolResult::Err(format!("capture_window: screen list error: {}", e)),
    };
    if screens.is_empty() {
        return ToolResult::Err("capture_window: no screens found".into());
    }

    // Capture primary screen and crop to window bounds
    let capture = match screens[0].capture_area(wx, wy, ww as u32, wh as u32) {
        Ok(img) => img,
        Err(e) => {
            // Fallback: capture full screen and crop manually
            warn!("capture_window: area capture failed ({}), trying full screen crop", e);
            match screens[0].capture() {
                Ok(img) => img,
                Err(e2) => return ToolResult::Err(format!("capture_window: fallback failed: {}", e2)),
            }
        }
    };

    let w = capture.width();
    let h = capture.height();
    let data = capture.into_raw();
    match encode_capture_to_base64_raw(w, h, data) {
        ToolResult::Ok(mut result) => {
            result["window"] = window_info_to_json(&win_info);
            ToolResult::Ok(result)
        }
        err => err,
    }
}

async fn find_on_screen(args: &Value) -> ToolResult {
    // Strategy: capture screen, overlay grid coordinates, return as base64
    // so the agent's vision model can identify elements by grid position.
    let grid_size = args["grid_size"].as_u64().unwrap_or(50) as u32;
    let monitor_idx = args["monitor"].as_u64().unwrap_or(0) as usize;

    info!("find_on_screen: grid_size={} monitor={}", grid_size, monitor_idx);

    let screens = match screenshots::Screen::all() {
        Ok(s) => s,
        Err(e) => return ToolResult::Err(format!("find_on_screen: screen list error: {}", e)),
    };
    if screens.is_empty() {
        return ToolResult::Err("find_on_screen: no screens found".into());
    }
    let screen = if monitor_idx < screens.len() { &screens[monitor_idx] } else { &screens[0] };

    let capture = match screen.capture() {
        Ok(img) => img,
        Err(e) => return ToolResult::Err(format!("find_on_screen: capture failed: {}", e)),
    };

    let width = capture.width();
    let height = capture.height();
    let rgba_data = capture.into_raw();

    // Convert BGRA → RGBA on Windows
    let mut data = rgba_data;
    if cfg!(target_os = "windows") {
        for pixel in data.chunks_exact_mut(4) {
            pixel.swap(0, 2);
        }
    }

    let mut img_buf = image::RgbaImage::from_raw(width, height, data)
        .unwrap_or_else(|| image::RgbaImage::new(1, 1));

    // Draw grid lines for coordinate reference
    let grid_color = image::Rgba([255, 0, 0, 120]); // semi-transparent red
    for x in (0..width).step_by(grid_size as usize) {
        for y in 0..height {
            img_buf.put_pixel(x, y, grid_color);
        }
    }
    for y in (0..height).step_by(grid_size as usize) {
        for x in 0..width {
            img_buf.put_pixel(x, y, grid_color);
        }
    }

    // Encode
    let mut png_bytes: Vec<u8> = Vec::new();
    let encoder = image::codecs::png::PngEncoder::new(&mut png_bytes);
    if let Err(e) = image::ImageEncoder::write_image(
        encoder,
        &img_buf,
        width,
        height,
        image::ExtendedColorType::Rgba8,
    ) {
        return ToolResult::Err(format!("find_on_screen: PNG encode error: {}", e));
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_bytes);

    // Build grid coordinate map
    let cols = (width + grid_size - 1) / grid_size;
    let rows = (height + grid_size - 1) / grid_size;

    ToolResult::Ok(json!({
        "format": "png",
        "encoding": "base64",
        "width": width,
        "height": height,
        "size_bytes": png_bytes.len(),
        "grid_size": grid_size,
        "grid_cols": cols,
        "grid_rows": rows,
        "data": b64,
        "note": "Image has red grid overlay. Grid cell (col, row) maps to pixel (col * grid_size, row * grid_size). Use these coordinates for mouse operations.",
    }))
}

// ── Shared capture helper ───────────────────────────────────────────────────

fn encode_capture_to_base64_raw(width: u32, height: u32, mut rgba_data: Vec<u8>) -> ToolResult {
    // screenshots on Windows returns BGRA, swap B and R
    if cfg!(target_os = "windows") {
        for i in (0..rgba_data.len()).step_by(4) {
            rgba_data.swap(i, i + 2);
        }
    }

    let rgba_buf: image::RgbaImage = image::RgbaImage::from_raw(width, height, rgba_data)
        .unwrap_or_else(|| image::RgbaImage::new(1, 1));

    let mut png_bytes: Vec<u8> = Vec::new();
    let encoder = image::codecs::png::PngEncoder::new(&mut png_bytes);
    if let Err(e) = image::ImageEncoder::write_image(
        encoder,
        &rgba_buf,
        width,
        height,
        image::ExtendedColorType::Rgba8,
    ) {
        return ToolResult::Err(format!("PNG encode error: {}", e));
    }

    let b64 = base64::engine::general_purpose::STANDARD.encode(&png_bytes);
    ToolResult::Ok(json!({
        "format": "png",
        "encoding": "base64",
        "width": width,
        "height": height,
        "size_bytes": png_bytes.len(),
        "data": b64,
    }))
}

