use tracing::debug;

#[cfg(target_os = "windows")]
mod platform {
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowTextW};

    pub fn active_window_title() -> Option<String> {
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
            Some(String::from_utf16_lossy(&buf[..len as usize]))
        }
    }
}

#[cfg(not(target_os = "windows"))]
mod platform {
    pub fn active_window_title() -> Option<String> {
        None
    }
}

pub async fn monitor_loop() -> anyhow::Result<()> {
    loop {
        let title = platform::active_window_title();
        debug!("Active window: {:?}", title);
        tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
    }
}
