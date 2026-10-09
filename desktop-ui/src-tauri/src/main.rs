#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{Value, json};
use std::{
    path::{Path, PathBuf},
    sync::Mutex,
    time::{Duration, Instant},
};
use tauri::{
    Emitter, Manager, State,
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};
use tauri_plugin_clipboard_manager::ClipboardExt;
use trains_com_downloader::{
    app::{ActivityPage, Snapshot, TrainsApp},
    worker::{EmbeddedWorkerLauncher, JobKind, WorkerLauncher},
};

struct DesktopState {
    core: Mutex<TrainsApp>,
    quit_after_worker: Mutex<bool>,
    tray_available: Mutex<bool>,
    pending_size: Mutex<Option<(f64, f64, Instant)>>,
}
#[derive(Serialize, Clone)]
struct DesktopSnapshot {
    #[serde(flatten)]
    core: Snapshot,
    tray_available: bool,
}
type CommandResult<T> = Result<T, String>;

fn snapshot(state: &DesktopState) -> DesktopSnapshot {
    DesktopSnapshot {
        core: state.core.lock().expect("application state").snapshot(),
        tray_available: *state.tray_available.lock().expect("tray state"),
    }
}
fn publish(app: &tauri::AppHandle) {
    let _ = app.emit("state-changed", snapshot(&app.state::<DesktopState>()));
}

#[tauri::command]
async fn get_snapshot(state: State<'_, DesktopState>) -> CommandResult<DesktopSnapshot> {
    Ok(snapshot(&state))
}
#[tauri::command]
async fn update_settings(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
    changes: Value,
) -> CommandResult<DesktopSnapshot> {
    state
        .core
        .lock()
        .map_err(|_| "Settings are unavailable.")?
        .update_settings(changes)?;
    publish(&app);
    Ok(snapshot(&state))
}
#[tauri::command]
async fn start_job(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
    kind: JobKind,
) -> CommandResult<DesktopSnapshot> {
    state
        .core
        .lock()
        .map_err(|_| "The job could not be started.")?
        .start_job(kind)?;
    publish(&app);
    Ok(snapshot(&state))
}
#[tauri::command]
async fn stop_job(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
) -> CommandResult<DesktopSnapshot> {
    state
        .core
        .lock()
        .map_err(|_| "The job could not be stopped.")?
        .request_stop();
    publish(&app);
    Ok(snapshot(&state))
}
#[tauri::command]
async fn get_activity(
    state: State<'_, DesktopState>,
    query: String,
    offset: usize,
    limit: usize,
) -> CommandResult<ActivityPage> {
    Ok(state
        .core
        .lock()
        .map_err(|_| "Activity is unavailable.")?
        .activity(&query, offset, limit))
}
#[tauri::command]
async fn clear_activity(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
) -> CommandResult<DesktopSnapshot> {
    state
        .core
        .lock()
        .map_err(|_| "Activity could not be cleared.")?
        .clear_activity();
    publish(&app);
    Ok(snapshot(&state))
}
#[tauri::command]
async fn copy_errors(app: tauri::AppHandle, state: State<'_, DesktopState>) -> CommandResult<()> {
    let text = state
        .core
        .lock()
        .map_err(|_| "Errors are unavailable.")?
        .error_text();
    app.clipboard()
        .write_text(text)
        .map_err(|_| "The errors could not be copied to the clipboard.".into())
}
#[tauri::command]
async fn clear_cache(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
) -> CommandResult<String> {
    let message = state
        .core
        .lock()
        .map_err(|_| "The cache could not be cleared.")?
        .clear_cache()?;
    publish(&app);
    Ok(message)
}
#[tauri::command]
async fn choose_path(field: String, initial: String) -> CommandResult<Option<String>> {
    if ![
        "base_dir",
        "track_plans_dir",
        "org_src",
        "org_dst",
        "cookies_path",
    ]
    .contains(&field.as_str())
    {
        return Err("Unsupported file selection.".into());
    }
    let mut dialog = rfd::AsyncFileDialog::new();
    let initial_path = Path::new(&initial);
    if !initial.trim().is_empty() {
        dialog = dialog.set_directory(if field == "cookies_path" {
            initial_path.parent().unwrap_or(initial_path)
        } else {
            initial_path
        });
    }
    let selected = if field == "cookies_path" {
        dialog
            .add_filter("JSON cookie file", &["json"])
            .pick_file()
            .await
    } else {
        dialog.pick_folder().await
    };
    Ok(selected.map(|file| file.path().to_string_lossy().into_owned()))
}
#[tauri::command]
async fn close_action(
    app: tauri::AppHandle,
    state: State<'_, DesktopState>,
    choice: String,
) -> CommandResult<()> {
    match choice.as_str() {
        "cancel" => Ok(()),
        "tray" => {
            if !*state
                .tray_available
                .lock()
                .map_err(|_| "Tray controls are unavailable.")?
            {
                return Err("The system tray is unavailable on this desktop.".into());
            }
            app.get_webview_window("main")
                .ok_or("The main window is unavailable.")?
                .hide()
                .map_err(|_| "The window could not be hidden.".into())
        }
        "stop-quit" => {
            *state
                .quit_after_worker
                .lock()
                .map_err(|_| "The app could not close.")? = true;
            state
                .core
                .lock()
                .map_err(|_| "The job could not be stopped.")?
                .request_stop();
            publish(&app);
            Ok(())
        }
        _ => Err("Unsupported close choice.".into()),
    }
}

fn data_dir_for_executable(path: &Path) -> PathBuf {
    let parent = path.parent().unwrap_or(Path::new("."));
    if parent.file_name().is_some_and(|name| name == "MacOS")
        && parent
            .parent()
            .and_then(Path::file_name)
            .is_some_and(|name| name == "Contents")
    {
        return parent
            .parent()
            .and_then(Path::parent)
            .and_then(Path::parent)
            .unwrap_or(parent)
            .to_path_buf();
    }
    parent.to_path_buf()
}
fn data_directory() -> PathBuf {
    // Explicit override keeps automated checks away from account and library files.
    let args = std::env::args().collect::<Vec<_>>();
    if let Some(index) = args.iter().position(|arg| arg == "--data-dir")
        && let Some(path) = args.get(index + 1)
    {
        return PathBuf::from(path);
    }
    // AppImage's current_exe lives in a temporary mount. Keep portable data beside
    // the original image, just as it lived beside the previous Linux executable.
    #[cfg(target_os = "linux")]
    if let Some(path) = std::env::var_os("APPIMAGE") {
        let image = PathBuf::from(path);
        if image.is_absolute() && image.is_file() {
            return data_dir_for_executable(&image);
        }
    }
    std::env::current_exe()
        .map(|path| data_dir_for_executable(&path))
        .unwrap_or_else(|_| PathBuf::from("."))
}
fn show_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}
fn request_quit(app: &tauri::AppHandle) {
    if app
        .state::<DesktopState>()
        .core
        .lock()
        .expect("application state")
        .can_start_job()
    {
        app.exit(0);
    } else {
        show_window(app);
        let _ = app.emit("close-requested", ());
    }
}
fn install_tray(app: &tauri::App) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Show Window", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;
    let mut builder = TrayIconBuilder::new()
        .tooltip("Trains.com Archive")
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => show_window(app),
            "quit" => request_quit(app),
            _ => {}
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)?;
    Ok(())
}
fn main() {
    let launcher: Box<dyn WorkerLauncher> = Box::new(EmbeddedWorkerLauncher::default());
    #[cfg(feature = "ui-qa")]
    let launcher: Box<dyn WorkerLauncher> = if std::env::args().any(|arg| arg == "--qa")
        && std::env::args().any(|arg| arg == "--data-dir")
    {
        Box::new(trains_com_downloader::worker::FakeWorkerLauncher)
    } else {
        launcher
    };
    let core = TrainsApp::new(data_directory(), launcher);
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .manage(DesktopState {
            core: Mutex::new(core),
            quit_after_worker: Mutex::new(false),
            tray_available: Mutex::new(false),
            pending_size: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            get_snapshot,
            update_settings,
            start_job,
            stop_job,
            get_activity,
            clear_activity,
            copy_errors,
            clear_cache,
            choose_path,
            close_action
        ])
        .setup(|app| {
            *app.state::<DesktopState>()
                .tray_available
                .lock()
                .expect("tray state") = install_tray(app).is_ok();
            if let Some(window) = app.get_webview_window("main") {
                let settings = app
                    .state::<DesktopState>()
                    .core
                    .lock()
                    .expect("application state")
                    .settings()
                    .clone();
                let _ = window.set_size(tauri::LogicalSize::new(
                    settings.window_width.max(640.0),
                    settings.window_height.max(480.0),
                ));
            }
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    let state = handle.state::<DesktopState>();
                    let changed = state.core.lock().expect("application state").poll_worker();
                    if changed {
                        publish(&handle);
                    }
                    if *state.quit_after_worker.lock().expect("quit state")
                        && state
                            .core
                            .lock()
                            .expect("application state")
                            .can_start_job()
                    {
                        handle.exit(0);
                        break;
                    }
                    let size = {
                        let mut pending = state.pending_size.lock().expect("window size");
                        if pending
                            .as_ref()
                            .is_some_and(|(_, _, at)| at.elapsed() > Duration::from_millis(400))
                        {
                            pending.take()
                        } else {
                            None
                        }
                    };
                    if let Some((width, height, _)) = size {
                        let _ = state
                            .core
                            .lock()
                            .expect("application state")
                            .update_settings(json!({"window_width":width,"window_height":height}));
                    }
                    tokio::time::sleep(Duration::from_millis(
                        if state
                            .core
                            .lock()
                            .expect("application state")
                            .can_start_job()
                        {
                            200
                        } else {
                            50
                        },
                    ))
                    .await;
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| match event {
            tauri::WindowEvent::CloseRequested { api, .. } => {
                if !window
                    .state::<DesktopState>()
                    .core
                    .lock()
                    .expect("application state")
                    .can_start_job()
                {
                    api.prevent_close();
                    let _ = window.emit("close-requested", ());
                }
            }
            tauri::WindowEvent::Resized(size) if size.width > 0 && size.height > 0 => {
                let logical = size.to_logical::<f64>(window.scale_factor().unwrap_or(1.0));
                *window
                    .state::<DesktopState>()
                    .pending_size
                    .lock()
                    .expect("window size") = Some((
                    logical.width.max(640.0),
                    logical.height.max(480.0),
                    Instant::now(),
                ));
            }
            _ => {}
        })
        .build(tauri::generate_context!())
        .expect("The desktop application could not start.")
        .run(|app, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event
                && !app
                    .state::<DesktopState>()
                    .core
                    .lock()
                    .expect("application state")
                    .can_start_job()
            {
                api.prevent_exit();
                show_window(app);
                let _ = app.emit("close-requested", ());
            }
        });
}

#[cfg(test)]
mod tests {
    use super::data_dir_for_executable;
    use std::path::Path;
    #[test]
    fn macos_bundle_keeps_data_beside_the_application() {
        assert_eq!(
            data_dir_for_executable(Path::new("/Downloads/Archive.app/Contents/MacOS/archive")),
            Path::new("/Downloads")
        );
        assert_eq!(
            data_dir_for_executable(Path::new("/Downloads/archive")),
            Path::new("/Downloads")
        );
    }
}
