#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;

use eframe::egui;
use trains_com_downloader::{app::TrainsApp, worker::EmbeddedWorkerLauncher};

fn app_data_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.parent().map(PathBuf::from))
        .or_else(|| std::env::current_dir().ok())
        .unwrap_or_else(|| PathBuf::from("."))
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1120.0, 760.0])
            .with_min_inner_size([800.0, 620.0]),
        ..Default::default()
    };

    eframe::run_native(
        "Trains.com Archive",
        options,
        Box::new(|creation_context| {
            let mut app =
                TrainsApp::new(app_data_dir(), Box::new(EmbeddedWorkerLauncher::default()));
            app.install_desktop_tray(creation_context.egui_ctx.clone());
            Ok(Box::new(app))
        }),
    )
}
