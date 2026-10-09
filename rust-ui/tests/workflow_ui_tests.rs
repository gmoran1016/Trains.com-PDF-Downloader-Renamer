use std::path::PathBuf;

use eframe::egui::{self, Vec2};
use egui_kittest::{Harness, kittest::Queryable};
use trains_com_downloader::{
    app::{TrainsApp, UnavailableWorker},
    model::{AppPage, JobOutcome, LogLevel},
    settings::Settings,
    ui::organize::can_download_missing,
    worker::{JobKind, PROTOCOL_VERSION, WorkerEvent},
};

fn harness(data_dir: PathBuf) -> Harness<'static, TrainsApp> {
    harness_at(data_dir, Vec2::new(1440.0, 900.0))
}

fn harness_at(data_dir: PathBuf, size: Vec2) -> Harness<'static, TrainsApp> {
    Harness::builder()
        .with_size(size)
        .build_eframe(move |_| TrainsApp::new(data_dir, Box::new(UnavailableWorker)))
}

#[test]
fn navigation_switches_work_areas() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    assert_eq!(harness.state().active_page(), AppPage::Magazines);

    harness.get_by_label("Track Plans").click();
    harness.run();
    assert_eq!(harness.state().active_page(), AppPage::TrackPlans);

    harness.get_by_label("Organize").click();
    harness.run();
    assert_eq!(harness.state().active_page(), AppPage::Organize);

    harness.get_by_label("Magazines").click();
    harness.run();
    assert_eq!(harness.state().active_page(), AppPage::Magazines);
}

#[test]
fn desktop_layout_at_800x620_keeps_navigation_actions_and_activity_visible() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness_at(temp.path().to_path_buf(), Vec2::new(800.0, 620.0));

    for label in [
        "Magazines",
        "Track Plans",
        "Organize",
        "Account",
        "Download selected magazines",
        "Filter activity",
        "Copy errors",
        "Collapse Activity",
    ] {
        let bounds = harness.get_by_label(label).rect();
        assert!(
            bounds.min.x >= 0.0 && bounds.max.x <= 800.0,
            "{label}: {bounds:?}"
        );
        assert!(
            bounds.min.y >= 0.0 && bounds.max.y <= 620.0,
            "{label}: {bounds:?}"
        );
    }

    harness.get_by_label("Track Plans").click();
    harness.run();
    let action = harness.get_by_label("Download all track plans").rect();
    assert!(action.max.x <= 800.0 && action.max.y <= 620.0);

    harness.get_by_label("Organize").click();
    harness.run();
    let action = harness.get_by_label("Organize PDFs").rect();
    assert!(action.max.x <= 800.0 && action.max.y <= 620.0);
}

#[test]
fn magazine_options_map_to_protocol_v1() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    {
        let settings = harness.state_mut().settings_mut();
        settings.base_dir = "D:/Archive/Magazines".to_owned();
        settings.selected_magazines =
            vec!["Trains Magazine".to_owned(), "Classic Trains".to_owned()];
        settings.headless = true;
        settings.test_mode = true;
        settings.newest_first = false;
        settings.include_specials = false;
        settings.cookies_path = "D:/App/session_cookies.json".to_owned();
    }
    assert_eq!(
        harness.state().settings().selected_magazines,
        vec!["Trains Magazine", "Classic Trains"]
    );

    harness.get_by_label("Download selected magazines").click();
    harness.step();

    harness.get_by_label("Test mode (first 3 archive pages)");

    let request = harness
        .state()
        .pending_request()
        .expect("magazine request queued");
    assert_eq!(PROTOCOL_VERSION, 1);
    assert_eq!(request.job_kind, JobKind::Magazines);
    assert_eq!(request.options["base_dir"], "D:/Archive/Magazines");
    assert_eq!(
        request.options["magazines"],
        serde_json::json!(["Trains Magazine", "Classic Trains"])
    );
    assert_eq!(request.options["headless"], true);
    assert_eq!(request.options["test_mode"], true);
    assert_eq!(request.options["newest_first"], false);
    assert_eq!(request.options["include_specials"], false);
    assert_eq!(
        request.options["cookies_path"],
        "D:/App/session_cookies.json"
    );
}

#[test]
fn track_plans_uses_separate_destination() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    {
        let settings = harness.state_mut().settings_mut();
        settings.base_dir = "D:/Archive/Magazines".to_owned();
        settings.track_plans_dir = "E:/Archive/Track Plans".to_owned();
        settings.cookies_path = "D:/App/session_cookies.json".to_owned();
    }

    harness.get_by_label("Track Plans").click();
    harness.run();
    harness.get_by_label("Download all track plans").click();
    harness.step();

    let request = harness
        .state()
        .pending_request()
        .expect("track plan request queued");
    assert_eq!(request.job_kind, JobKind::TrackPlans);
    assert_eq!(request.options["destination_dir"], "E:/Archive/Track Plans");
    assert_eq!(
        request.options["cookies_path"],
        "D:/App/session_cookies.json"
    );
    assert!(request.options.get("base_dir").is_none());
}

#[test]
fn clear_cache_removes_only_progress_and_special_files() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let files = [
        ("download_progress.json", b"progress".as_slice()),
        ("special_issues.json", b"specials".as_slice()),
        ("settings.json", b"settings".as_slice()),
        ("session_cookies.json", b"cookies".as_slice()),
        ("app.log", b"log".as_slice()),
    ];
    for (name, contents) in files {
        std::fs::write(temp.path().join(name), contents).expect("write isolated fixture file");
    }
    let mut harness = harness(temp.path().to_path_buf());

    harness.get_by_label("Clear cache").scroll_to_me();
    harness.run();
    harness.get_by_label("Clear cache").click();
    harness.run();
    assert!(temp.path().join("download_progress.json").exists());
    assert!(temp.path().join("special_issues.json").exists());

    harness.get_by_label("Remove cache files").click();
    harness.run();
    assert!(!temp.path().join("download_progress.json").exists());
    assert!(!temp.path().join("special_issues.json").exists());
    for (name, expected) in [
        ("settings.json", b"settings".as_slice()),
        ("session_cookies.json", b"cookies".as_slice()),
        ("app.log", b"log".as_slice()),
    ] {
        assert_eq!(
            std::fs::read(temp.path().join(name)).expect("preserved file"),
            expected
        );
    }
}

#[test]
fn organizer_shows_complete_summary() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Success,
            summary: Some(serde_json::json!({
                "moved": 7,
                "already_correct": 2,
                "unrecognized": 1,
                "corrupt": 3,
                "conflicts": 4,
                "metadata_stamped": 5,
                "report": ["MRR 2024: missing March", "TRN 2025: complete"],
                "missing_by_prefix_year": {"MRR": {"2024": ["March"]}},
                "scan_complete": true
            })),
        });

    harness.get_by_label("Organize").click();
    harness.run();

    for label in [
        "Moved: 7",
        "Already correct: 2",
        "Unrecognized: 1",
        "Corrupt: 3",
        "Conflicts: 4",
        "Metadata updated: 5",
        "MRR 2024: missing March",
        "Complete scan",
    ] {
        harness.get_by_label(label);
    }
}

#[test]
fn organizer_summary_wraps_counts_at_compact_width() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness_at(temp.path().to_path_buf(), Vec2::new(640.0, 480.0));
    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Success,
            summary: Some(serde_json::json!({
                "moved": 7,
                "already_correct": 2,
                "unrecognized": 1,
                "corrupt": 3,
                "conflicts": 4,
                "metadata_stamped": 5,
                "report": [],
                "scan_complete": true
            })),
        });

    harness.get_by_label("Organize").click();
    harness.run();

    let third_count = harness.get_by_label("Unrecognized: 1").rect();
    let fourth_count = harness.get_by_label("Corrupt: 3").rect();
    assert!(
        third_count.min.x < fourth_count.min.x,
        "the third count should start a new grid row in a compact layout: {third_count:?} vs {fourth_count:?}"
    );
}

fn missing_download_action_is_visible_and_clickable(size: Vec2) {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness_at(temp.path().to_path_buf(), size);
    {
        let settings = harness.state_mut().settings_mut();
        settings.org_src = "D:/Incoming".to_owned();
        settings.org_dst = "D:/Library".to_owned();
    }
    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Success,
            summary: Some(serde_json::json!({
                "report": ["MRR 2024: missing March"],
                "missing_by_prefix_year": {"MRR": {"2024": ["March"]}},
                "scan_complete": true
            })),
        });
    harness.get_by_label("Organize").click();
    harness.run();

    let organize = harness.get_by_label("Organize PDFs").rect();
    let missing = harness.get_by_label("Download Missing");
    let missing_rect = missing.rect();
    assert!(
        (organize.center().y - missing_rect.center().y).abs() < 3.0,
        "both organizer actions must fit in the fixed action row: {organize:?} vs {missing_rect:?}"
    );
    for (label, rect) in [
        ("Organize PDFs", organize),
        ("Download Missing", missing_rect),
    ] {
        assert!(
            rect.min.x >= 0.0 && rect.min.y >= 0.0 && rect.max.x <= size.x && rect.max.y <= size.y,
            "{label} exceeds the {size:?} window: {rect:?}"
        );
    }
    assert!(
        harness.state().can_start_job(),
        "Download Missing should be enabled for a completed scan"
    );
    missing.click();
    harness.step();

    let request = harness
        .state()
        .pending_request()
        .expect("Download Missing queues its request");
    assert_eq!(request.job_kind, JobKind::DownloadMissing);
}

#[test]
fn missing_download_action_fits_at_1440x900() {
    missing_download_action_is_visible_and_clickable(Vec2::new(1440.0, 900.0));
}

#[test]
fn missing_download_action_fits_at_800x620() {
    missing_download_action_is_visible_and_clickable(Vec2::new(800.0, 620.0));
}

#[test]
fn seasonal_coverage_uses_the_python_report_without_inference() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Success,
            summary: Some(serde_json::json!({
                "report": ["GRW 2024: schedule unknown/seasonal; completeness not inferred"],
                "missing_by_prefix_year": {"GRW": {"2024": []}},
                "scan_complete": true
            })),
        });
    harness.get_by_label("Organize").click();
    harness.run();

    harness.get_by_label("GRW 2024: schedule unknown/seasonal; completeness not inferred");
    assert_eq!(harness.query_all_by_label("GRW 2024: complete").count(), 0);
}

#[test]
fn cache_confirmation_cannot_open_while_a_worker_is_running() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    harness.state_mut().apply_worker_event(WorkerEvent::Started);
    harness.run();

    harness.get_by_label("Clear cache").click();
    harness.run();

    assert_eq!(harness.query_all_by_label("Remove cache files").count(), 0);
}

#[test]
fn large_activity_history_keeps_all_rows_but_only_builds_visible_widgets() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    for index in 0..2_000 {
        harness.state_mut().apply_worker_event(WorkerEvent::Log {
            level: LogLevel::Info,
            message: format!("large activity entry {index}"),
        });
    }
    harness.run();

    let visible_entries = harness
        .get_all_by_label_contains("large activity entry")
        .count();
    assert!(
        visible_entries < 40,
        "rendered {visible_entries} log entries"
    );
    assert_eq!(harness.state().job_state().logs.len(), 2_000);
}

#[test]
fn missing_download_requires_single_complete_target() {
    let valid = serde_json::json!({
        "missing_by_prefix_year": {"MRR": {"2024": ["March"]}},
        "scan_complete": true
    });
    assert!(can_download_missing(&valid, JobOutcome::Success));
    assert!(!can_download_missing(&valid, JobOutcome::Failed));

    let incomplete = serde_json::json!({
        "missing_by_prefix_year": {"MRR": {"2024": ["March"]}},
        "scan_complete": false
    });
    assert!(!can_download_missing(&incomplete, JobOutcome::Success));

    let multiple = serde_json::json!({
        "missing_by_prefix_year": {
            "MRR": {"2024": ["March"]},
            "CTR": {"2024": ["June"]}
        },
        "scan_complete": true
    });
    assert!(!can_download_missing(&multiple, JobOutcome::Success));

    let unsupported = serde_json::json!({
        "missing_by_prefix_year": {"XYZ": {"2024": ["March"]}},
        "scan_complete": true
    });
    assert!(!can_download_missing(&unsupported, JobOutcome::Success));
}

#[test]
fn activity_filters_and_copies_errors() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    for (level, message) in [
        (LogLevel::Info, "Archive scan started"),
        (LogLevel::Warning, "Unrelated retry notice"),
    ] {
        harness.state_mut().apply_worker_event(WorkerEvent::Log {
            level,
            message: message.to_owned(),
        });
    }
    harness.state_mut().apply_worker_event(WorkerEvent::Error {
        message: "Network request failed".to_owned(),
    });
    harness.run();

    let filter = harness.get_by_label("Filter activity");
    filter.focus();
    harness.run();
    harness.get_by_label("Filter activity").type_text("Archive");
    harness.run();
    assert_eq!(
        harness.get_by_label("Filter activity").value().as_deref(),
        Some("Archive")
    );

    harness.get_by_label("Copy errors").click();
    harness.step();
    assert!(harness.output().platform_output.commands.iter().any(|command| {
        matches!(command, egui::OutputCommand::CopyText(text) if text.contains("Network request failed"))
    }));

    harness.get_by_label("Download selected magazines").click();
    harness.step();
    assert!(
        harness
            .state()
            .job_state()
            .logs
            .iter()
            .any(|entry| entry.message == "Network request failed")
    );

    harness.get_by_label("Download selected magazines").click();
    harness.step();
    assert!(
        harness
            .state()
            .job_state()
            .logs
            .iter()
            .any(|entry| entry.message == "Network request failed")
    );
}

#[test]
fn activity_resize_persists() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    let initial = harness.state().settings().activity_height;
    let handle_start = harness.get_by_label("Resize Activity").rect().center();
    let handle_end = egui::pos2(handle_start.x, handle_start.y - 54.0);
    harness.drag_at(handle_start);
    harness.step();
    harness.hover_at(handle_end);
    harness.step();
    harness.drop_at(handle_end);
    harness.step();

    assert!(harness.state().settings().activity_height > initial + 30.0);
    let loaded = Settings::load(temp.path()).settings;
    assert!(loaded.activity_height > initial + 30.0);
}

#[test]
fn activity_can_be_collapsed_and_reopened() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness_at(temp.path().to_path_buf(), Vec2::new(800.0, 620.0));
    assert!(!harness.state().settings().activity_collapsed);

    harness.get_by_label("Collapse Activity").click();
    harness.run();
    assert!(harness.state().settings().activity_collapsed);
    harness.get_by_label("Expand Activity").click();
    harness.run();

    assert!(!harness.state().settings().activity_collapsed);
}

#[test]
fn stop_changes_only_after_worker_ack() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    harness.state_mut().apply_worker_event(WorkerEvent::Started);
    harness.run();

    assert_eq!(harness.state().job_state().outcome, JobOutcome::Running);
    harness.get_by_label("Stop job").click();
    harness.run();
    assert_eq!(harness.state().job_state().outcome, JobOutcome::Running);
    assert!(harness.state().job_state().stop_requested);

    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Cancelled,
            summary: None,
        });
    harness.run();
    assert_eq!(harness.state().job_state().outcome, JobOutcome::Cancelled);
}

#[test]
fn account_settings_round_trip() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    harness.state_mut().settings_mut().cookies_path.clear();
    harness.get_by_label("Account").click();
    harness.run();

    let cookie_path = harness.get_by_label("Cookie file path");
    cookie_path.focus();
    harness.run();
    harness
        .get_by_label("Cookie file path")
        .type_text("D:/Trains/session_cookies.json");
    harness.run();
    harness.get_by_label("Keep magazine browser hidden").click();
    harness.run();
    harness
        .get_by_label("Hide browser for missing-issue downloads")
        .click();
    harness.run();
    harness.get_by_label("Save settings").click();
    harness.run();

    let restored = TrainsApp::new(temp.path().to_path_buf(), Box::new(UnavailableWorker));
    assert_eq!(
        restored.settings().cookies_path,
        "D:/Trains/session_cookies.json"
    );
    assert!(restored.settings().headless);
    assert!(restored.settings().org_headless);
}

#[test]
fn primary_controls_have_accessible_labels() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf());
    for label in [
        "Magazines",
        "Track Plans",
        "Organize",
        "Account",
        "Download selected magazines",
        "Filter activity",
        "Copy errors",
        "Clear activity",
        "Collapse Activity",
    ] {
        harness.get_by_label(label);
    }
    harness.get_by_label("Organize").click();
    harness.run();
    harness.get_by_label("Organize PDFs");
}
