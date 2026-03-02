mod commands;
mod daemon_manager;

use std::sync::atomic::{AtomicU32, Ordering};

use tauri::{
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    webview::WebviewWindowBuilder,
    Manager, WindowEvent, Emitter,
};

static QUICK_NOTE_COUNTER: AtomicU32 = AtomicU32::new(0);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
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
            // ── Register state ───────────────────────────────────────────
            app.manage(daemon_manager::DaemonState::new());

            // ── Start daemon if we have a token ─────────────────────────
            // Best effort startup (don't block). If the user hasn't logged in yet,
            // they can start it later via commands.
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                // Sleep briefly to let UI load/keyring settle if needed
                tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;
                if let Ok(config) = commands::read_app_config(app_handle.clone()) {
                    if let Ok(token) = commands::get_secure_token("atmos_access_token".into()) {
                        if !token.is_empty() {
                            // The daemon handles its own auto-registration if device_id isn't provided,
                            // AS LONG AS VISIONARK_TOKEN is there. However, to keep it in sync with the frontend,
                            // we only start it if we have a locally stored device_id.
                            let device_id = commands::get_secure_token("va_device_id".into()).unwrap_or_default();
                            if !device_id.is_empty() {
                                daemon_manager::start_daemon(&app_handle, config.api_url, token, device_id);
                            }
                        }
                    }
                }
            });

            // ── Register global shortcut ─────────────────────────────
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            if let Err(e) = app.global_shortcut().on_shortcut("Super+Alt+N", |_, _, _| {}) {
                eprintln!("Warning: could not register Super+Alt+N: {e}");
            }

            // ── Tray menu ──────────────────────────────────────────────
            let show = MenuItem::with_id(app, "show", "VisionArk を表示", true, None::<&str>)?;
            let jobs = MenuItem::with_id(app, "jobs", "Jobs を開く", true, None::<&str>)?;
            let console = MenuItem::with_id(app, "console", "Daemon Console", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit = MenuItem::with_id(app, "quit", "終了", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &jobs, &console, &sep, &quit])?;

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
                    "console" => {
                        if let Some(console_window) = app.get_webview_window("console") {
                            console_window.show().ok();
                            console_window.set_focus().ok();
                        }
                    },
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
        // Window close button: hide main window (stay in tray) OR exit, depending on config.
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    // Check background setting
                    let app_handle = window.app_handle().clone();
                    let run_in_bg = match commands::read_app_config(app_handle.clone()) {
                        Ok(cfg) => cfg.run_daemon_in_background,
                        Err(_) => false,
                    };

                    if run_in_bg {
                        api.prevent_close();
                        window.hide().ok();
                    } else {
                        // User wants to close completely.
                        // Wait, stopping the app will automatically kill sidecars spawned by tauri-plugin-shell if not detached.
                        // But let's be safe and kill it explicitly.
                        daemon_manager::stop_daemon(&app_handle);
                        // Do not prevent_close(); let it close gracefully, which exits the app if it's the main window.
                        std::process::exit(0);
                    }
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
            commands::get_config_file_path,
            commands::read_app_config,
            commands::write_app_config,
            commands::bridge_request,
            commands::start_daemon_command,
            commands::stop_daemon_command,
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
