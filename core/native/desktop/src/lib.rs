mod commands;

use std::sync::atomic::{AtomicU32, Ordering};

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    webview::WebviewWindowBuilder,
    Manager, WindowEvent,
};

static QUICK_NOTE_COUNTER: AtomicU32 = AtomicU32::new(0);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        if shortcut.matches(
                            tauri_plugin_global_shortcut::Modifiers::SUPER
                                | tauri_plugin_global_shortcut::Modifiers::ALT,
                            tauri_plugin_global_shortcut::Code::KeyN,
                        ) {
                            spawn_quick_note(app);
                        }
                    }
                })
                .build(),
        )
        .setup(|app| {
            // ── Register global shortcut ─────────────────────────────
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            if let Err(e) = app.global_shortcut().on_shortcut("Super+Alt+N", |_, _, _| {}) {
                eprintln!("Warning: could not register Super+Alt+N: {e}");
            }

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
        // Window close button: hide main window (stay in tray); destroy quick-note windows
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    window.hide().ok();
                }
                // quick-note windows: allow default close (destroy)
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

/// Spawn a new Quick Note window each time the shortcut is pressed.
fn spawn_quick_note(app: &tauri::AppHandle) {
    let id = QUICK_NOTE_COUNTER.fetch_add(1, Ordering::Relaxed);
    let label = format!("quick-note-{id}");

    let url = tauri::WebviewUrl::App("quick-note.html".into());

    match WebviewWindowBuilder::new(app, &label, url)
        .title("Quick Note")
        .inner_size(450.0, 300.0)
        .resizable(false)
        .decorations(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .center()
        .focused(true)
        .build()
    {
        Ok(_) => {}
        Err(e) => eprintln!("Failed to create quick-note window: {e}"),
    }
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
