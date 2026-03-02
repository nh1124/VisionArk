use tracing::debug;

/// Information about a window.
#[derive(Clone, Debug)]
pub struct WindowInfo {
    pub title: String,
    pub pid: u32,
    pub exe_name: String,
    pub x: i32,
    pub y: i32,
    pub width: i32,
    pub height: i32,
}

#[cfg(target_os = "windows")]
mod platform {
    use super::WindowInfo;
    use windows::Win32::Foundation::{BOOL, HWND, LPARAM, RECT};
    use windows::Win32::UI::WindowsAndMessaging::{
        EnumWindows, GetForegroundWindow, GetWindowRect, GetWindowTextLengthW,
        GetWindowTextW, GetWindowThreadProcessId, IsWindowVisible,
        PostMessageW, SetForegroundWindow, WM_CLOSE,
    };

    unsafe extern "system" fn enum_cb(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let list = &mut *(lparam.0 as *mut Vec<(HWND, String, u32)>);
        if !IsWindowVisible(hwnd).as_bool() {
            return BOOL(1);
        }
        let len = GetWindowTextLengthW(hwnd);
        if len == 0 {
            return BOOL(1);
        }
        let mut buf = vec![0u16; (len + 1) as usize];
        let actual = GetWindowTextW(hwnd, &mut buf);
        let title = String::from_utf16_lossy(&buf[..actual as usize]);
        if title.is_empty() {
            return BOOL(1);
        }
        let mut pid: u32 = 0;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
        list.push((hwnd, title, pid));
        BOOL(1)
    }

    /// Enumerate all visible windows with non-empty titles.
    pub fn enum_windows() -> Vec<(HWND, String, u32)> {
        let mut list: Vec<(HWND, String, u32)> = Vec::new();
        unsafe {
            let _ = EnumWindows(
                Some(enum_cb),
                LPARAM(&mut list as *mut _ as isize),
            );
        }
        list
    }

    fn hwnd_to_window_info(hwnd: HWND, title: String, pid: u32) -> WindowInfo {
        let mut rect = RECT::default();
        unsafe {
            let _ = GetWindowRect(hwnd, &mut rect);
        }
        let exe_name = if pid > 0 {
            let mut sys = sysinfo::System::new();
            sys.refresh_processes(
                sysinfo::ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(pid)]),
                true,
            );
            sys.process(sysinfo::Pid::from_u32(pid))
                .map(|p| p.name().to_string_lossy().to_string())
                .unwrap_or_default()
        } else {
            String::new()
        };

        WindowInfo {
            title,
            pid,
            exe_name,
            x: rect.left,
            y: rect.top,
            width: rect.right - rect.left,
            height: rect.bottom - rect.top,
        }
    }

    pub fn active_window_info() -> Option<WindowInfo> {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd.0.is_null() {
                return None;
            }
            let mut buf = [0u16; 512];
            let len = GetWindowTextW(hwnd, &mut buf);
            if len == 0 {
                return None;
            }
            let title = String::from_utf16_lossy(&buf[..len as usize]);
            let mut pid: u32 = 0;
            GetWindowThreadProcessId(hwnd, Some(&mut pid));
            Some(hwnd_to_window_info(hwnd, title, pid))
        }
    }

    /// Find windows matching criteria (title substring, pid, or exe_name substring).
    pub fn find_windows(
        title_match: Option<&str>,
        pid_match: Option<u32>,
        exe_match: Option<&str>,
    ) -> Vec<WindowInfo> {
        let all = enum_windows();
        let mut results = Vec::new();
        for (hwnd, title, pid) in &all {
            if let Some(t) = title_match {
                if !title.to_lowercase().contains(&t.to_lowercase()) {
                    continue;
                }
            }
            if let Some(p) = pid_match {
                if *pid != p {
                    continue;
                }
            }

            let info = hwnd_to_window_info(*hwnd, title.clone(), *pid);

            if let Some(e) = exe_match {
                if !info.exe_name.to_lowercase().contains(&e.to_lowercase()) {
                    continue;
                }
            }
            results.push(info);
        }
        results
    }

    /// Set foreground window by HWND.
    pub fn focus_window_by_match(
        title_match: Option<&str>,
        pid_match: Option<u32>,
        exe_match: Option<&str>,
    ) -> Option<WindowInfo> {
        let all = enum_windows();
        for (hwnd, title, pid) in &all {
            let mut ok = true;
            if let Some(t) = title_match {
                if !title.to_lowercase().contains(&t.to_lowercase()) {
                    ok = false;
                }
            }
            if let Some(p) = pid_match {
                if *pid != p {
                    ok = false;
                }
            }
            if ok {
                if let Some(e) = exe_match {
                    let mut sys = sysinfo::System::new();
                    sys.refresh_processes(
                        sysinfo::ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(*pid)]),
                        true,
                    );
                    let name = sys
                        .process(sysinfo::Pid::from_u32(*pid))
                        .map(|p| p.name().to_string_lossy().to_string())
                        .unwrap_or_default();
                    if !name.to_lowercase().contains(&e.to_lowercase()) {
                        continue;
                    }
                }
                unsafe {
                    let _ = SetForegroundWindow(*hwnd);
                }
                return Some(hwnd_to_window_info(*hwnd, title.clone(), *pid));
            }
        }
        None
    }

    /// Close a window by posting WM_CLOSE.
    pub fn close_window_by_match(
        title_match: Option<&str>,
        pid_match: Option<u32>,
        exe_match: Option<&str>,
        force: bool,
    ) -> Option<WindowInfo> {
        let all = enum_windows();
        for (hwnd, title, pid) in &all {
            let mut ok = true;
            if let Some(t) = title_match {
                if !title.to_lowercase().contains(&t.to_lowercase()) {
                    ok = false;
                }
            }
            if let Some(p) = pid_match {
                if *pid != p {
                    ok = false;
                }
            }
            if ok {
                if let Some(e) = exe_match {
                    let mut sys = sysinfo::System::new();
                    sys.refresh_processes(
                        sysinfo::ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(*pid)]),
                        true,
                    );
                    let name = sys
                        .process(sysinfo::Pid::from_u32(*pid))
                        .map(|p| p.name().to_string_lossy().to_string())
                        .unwrap_or_default();
                    if !name.to_lowercase().contains(&e.to_lowercase()) {
                        continue;
                    }
                }
                let info = hwnd_to_window_info(*hwnd, title.clone(), *pid);
                if force {
                    // Terminate process
                    let mut sys = sysinfo::System::new();
                    sys.refresh_processes(
                        sysinfo::ProcessesToUpdate::Some(&[sysinfo::Pid::from_u32(*pid)]),
                        true,
                    );
                    if let Some(proc) = sys.process(sysinfo::Pid::from_u32(*pid)) {
                        proc.kill();
                    }
                } else {
                    unsafe {
                        let _ = PostMessageW(*hwnd, WM_CLOSE, None, None);
                    }
                }
                return Some(info);
            }
        }
        None
    }

    /// Get window bounds for capture.
    pub fn get_window_rect_by_match(
        title_match: Option<&str>,
        pid_match: Option<u32>,
        exe_match: Option<&str>,
    ) -> Option<(i32, i32, i32, i32, WindowInfo)> {
        let found = find_windows(title_match, pid_match, exe_match);
        found.into_iter().next().map(|w| (w.x, w.y, w.width, w.height, w))
    }
}

#[cfg(not(target_os = "windows"))]
mod platform {
    use super::WindowInfo;

    pub fn active_window_info() -> Option<WindowInfo> {
        None
    }

    pub fn find_windows(
        _title: Option<&str>,
        _pid: Option<u32>,
        _exe: Option<&str>,
    ) -> Vec<WindowInfo> {
        Vec::new()
    }

    pub fn focus_window_by_match(
        _title: Option<&str>,
        _pid: Option<u32>,
        _exe: Option<&str>,
    ) -> Option<WindowInfo> {
        None
    }

    pub fn close_window_by_match(
        _title: Option<&str>,
        _pid: Option<u32>,
        _exe: Option<&str>,
        _force: bool,
    ) -> Option<WindowInfo> {
        None
    }

    pub fn get_window_rect_by_match(
        _title: Option<&str>,
        _pid: Option<u32>,
        _exe: Option<&str>,
    ) -> Option<(i32, i32, i32, i32, WindowInfo)> {
        None
    }
}

// ── Public API ────────────────────────────────────────────────────────────────

pub fn get_active_window_info() -> Option<WindowInfo> {
    platform::active_window_info()
}

pub fn find_windows(
    title: Option<&str>,
    pid: Option<u32>,
    exe: Option<&str>,
) -> Vec<WindowInfo> {
    platform::find_windows(title, pid, exe)
}

pub fn focus_window(
    title: Option<&str>,
    pid: Option<u32>,
    exe: Option<&str>,
) -> Option<WindowInfo> {
    platform::focus_window_by_match(title, pid, exe)
}

pub fn close_window(
    title: Option<&str>,
    pid: Option<u32>,
    exe: Option<&str>,
    force: bool,
) -> Option<WindowInfo> {
    platform::close_window_by_match(title, pid, exe, force)
}

pub fn get_window_rect(
    title: Option<&str>,
    pid: Option<u32>,
    exe: Option<&str>,
) -> Option<(i32, i32, i32, i32, WindowInfo)> {
    platform::get_window_rect_by_match(title, pid, exe)
}

pub async fn monitor_loop() -> anyhow::Result<()> {
    loop {
        let info = platform::active_window_info();
        if let Some(ref w) = info {
            debug!(
                "Active window: '{}' (pid={}, exe={}, {}x{}+{}+{})",
                w.title, w.pid, w.exe_name, w.width, w.height, w.x, w.y
            );
        } else {
            debug!("Active window: None");
        }
        tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
    }
}
