mod commands;

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            // ── Tray menu ──────────────────────────────────────────────
            let show = MenuItem::with_id(app, "show", "VisionArk を表示", true, None::<&str>)?;
            let jobs = MenuItem::with_id(app, "jobs", "Jobs を開く", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "終了", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &jobs, &sep, &quit])?;

            let mut builder = TrayIconBuilder::new()
                .menu(&menu)
                .show_menu_on_left_click(false)
                .tooltip("VisionArk");

            // Use the app's default icon if available
            if let Some(icon) = app.default_window_icon() {
                builder = builder.icon(icon.clone());
            }

            builder
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => toggle_main_window(app),
                    "jobs" => open_main_window(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        toggle_main_window(tray.app_handle());
                    }
                })
                .build(app)?;

            Ok(())
        })
        // Window close button → hide (stay resident in tray)
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                window.hide().ok();
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_app_version,
            commands::ping,
            commands::toggle_window,
            commands::send_notification,
            commands::get_pending_count,
            commands::set_secure_token,
            commands::get_secure_token,
            commands::delete_secure_token,
        ])
        .run(tauri::generate_context!())
        .expect("error while running VisionArk");
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        if win.is_visible().unwrap_or(false) {
            win.hide().ok();
        } else {
            win.show().ok();
            win.set_focus().ok();
        }
    }
}

fn open_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        win.show().ok();
        win.set_focus().ok();
    }
}
