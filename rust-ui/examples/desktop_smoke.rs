use std::path::Path;

use eframe::egui;
use trains_com_downloader::{
    app::TrainsApp,
    model::{AppPage, LogLevel},
    worker::{FakeWorkerLauncher, WorkerEvent},
};

fn parse_dimension(value: Option<String>, fallback: f32, minimum: f32) -> f32 {
    value
        .and_then(|value| value.parse().ok())
        .filter(|value: &f32| *value >= minimum)
        .unwrap_or(fallback)
}

fn dimension(name: &str, fallback: f32, minimum: f32) -> f32 {
    parse_dimension(std::env::var(name).ok(), fallback, minimum)
}

fn requested_page() -> Option<AppPage> {
    match std::env::var("TRAINS_UI_SMOKE_PAGE").ok()?.as_str() {
        "magazines" => Some(AppPage::Magazines),
        "track-plans" => Some(AppPage::TrackPlans),
        "organize" => Some(AppPage::Organize),
        _ => None,
    }
}

fn running_scene_requested() -> bool {
    std::env::var("TRAINS_UI_SMOKE_STATE").is_ok_and(|state| state == "running")
}

fn dark_theme_requested() -> bool {
    std::env::var("TRAINS_UI_SMOKE_THEME").is_ok_and(|theme| theme == "dark")
}

fn configure_isolated_paths(app: &mut TrainsApp, root: &Path) {
    let settings = app.settings_mut();
    settings.base_dir = root.join("magazines").to_string_lossy().into_owned();
    settings.track_plans_dir = root.join("track-plans").to_string_lossy().into_owned();
    settings.cookies_path = root
        .join("session_cookies.json")
        .to_string_lossy()
        .into_owned();
    settings.org_src = root.join("organize-source").to_string_lossy().into_owned();
    settings.org_dst = root
        .join("organize-destination")
        .to_string_lossy()
        .into_owned();
}

fn main() -> eframe::Result<()> {
    let data_dir = tempfile::tempdir().expect("create isolated smoke-test data root");
    let data_root = data_dir.path().to_path_buf();
    let page = requested_page();
    let running_scene = running_scene_requested();
    let dark_theme = dark_theme_requested();

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([
                dimension("TRAINS_UI_SMOKE_WIDTH", 1120.0, 640.0),
                dimension("TRAINS_UI_SMOKE_HEIGHT", 760.0, 480.0),
            ])
            .with_min_inner_size([640.0, 480.0]),
        ..Default::default()
    };

    let result = eframe::run_native(
        "Trains.com Archive — Desktop Smoke",
        options,
        Box::new(move |creation_context| {
            let mut app = TrainsApp::new(data_root.clone(), Box::new(FakeWorkerLauncher));
            configure_isolated_paths(&mut app, &data_root);
            app.settings_mut().dark_mode = dark_theme;
            if let Some(page) = page {
                app.set_active_page(page);
            }
            if running_scene {
                app.apply_worker_event(WorkerEvent::Started);
                app.apply_worker_event(WorkerEvent::Progress {
                    done: Some(5),
                    total: Some(24),
                    message: Some("Downloading Model Railroader issues".to_owned()),
                    per_magazine: None,
                });
                app.apply_worker_event(WorkerEvent::Log {
                    level: LogLevel::Info,
                    message: "Archive scan found 24 available issues".to_owned(),
                });
                app.apply_worker_event(WorkerEvent::Log {
                    level: LogLevel::Info,
                    message: "Downloaded Model Railroader 2026-10".to_owned(),
                });
            }
            app.install_desktop_tray(creation_context.egui_ctx.clone());
            Ok(Box::new(app))
        }),
    );
    drop(data_dir);
    result
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    use trains_com_downloader::{app::TrainsApp, worker::UnavailableWorker};

    use super::{configure_isolated_paths, parse_dimension};

    #[test]
    fn desktop_smoke_targets_are_confined_to_the_temporary_root() {
        let temp = tempfile::tempdir().expect("temporary smoke-test data root");
        let root = temp.path().to_path_buf();
        let mut app = TrainsApp::new(root.clone(), Box::new(UnavailableWorker));

        configure_isolated_paths(&mut app, &root);

        let settings = app.settings();
        for path in [
            &settings.base_dir,
            &settings.track_plans_dir,
            &settings.cookies_path,
            &settings.org_src,
            &settings.org_dst,
        ] {
            assert!(
                PathBuf::from(path).starts_with(&root),
                "smoke path escaped the temporary root: {path}"
            );
        }
    }

    #[test]
    fn smoke_viewport_accepts_approved_compact_dimensions() {
        assert_eq!(
            parse_dimension(Some("640".to_owned()), 1120.0, 640.0),
            640.0
        );
        assert_eq!(parse_dimension(Some("480".to_owned()), 760.0, 480.0), 480.0);
    }

    #[test]
    fn smoke_viewport_rejects_dimensions_below_each_axis_minimum() {
        assert_eq!(
            parse_dimension(Some("639".to_owned()), 1120.0, 640.0),
            1120.0
        );
        assert_eq!(parse_dimension(Some("479".to_owned()), 760.0, 480.0), 760.0);
    }
}
