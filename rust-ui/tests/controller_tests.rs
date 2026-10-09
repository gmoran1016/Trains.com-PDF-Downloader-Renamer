use serde_json::json;
use trains_com_downloader::{
    app::{TrainsApp, UnavailableWorker},
    model::{JobOutcome, LogLevel},
    requests::{build_request, can_download_missing},
    settings::Settings,
    worker::{JobKind, WorkerEvent},
};

#[test]
fn requests_preserve_separate_destinations_and_shared_authentication() {
    let settings = Settings {
        base_dir: "D:/Magazines".into(),
        track_plans_dir: "D:/Plans".into(),
        cookies_path: "D:/Private/session.json".into(),
        ..Settings::default()
    };
    let magazines = build_request(JobKind::Magazines, &settings, None, "magazines".into()).unwrap();
    let plans = build_request(JobKind::TrackPlans, &settings, None, "plans".into()).unwrap();
    assert_eq!(magazines.options["base_dir"], "D:/Magazines");
    assert_eq!(plans.options["destination_dir"], "D:/Plans");
    assert_eq!(
        plans.options["cookies_path"],
        magazines.options["cookies_path"]
    );
    assert_eq!(magazines.options["include_specials"], true);
}

#[test]
fn incomplete_or_ambiguous_scan_never_allows_missing_downloads() {
    let complete =
        json!({"scan_complete": true,"missing_by_prefix_year":{"MRR":{"2024":["January"]}}});
    assert!(can_download_missing(&complete, JobOutcome::Success));
    assert!(!can_download_missing(&complete, JobOutcome::Failed));
    let mut incomplete = complete.clone();
    incomplete["scan_complete"] = json!(false);
    assert!(!can_download_missing(&incomplete, JobOutcome::Success));
    let mut ambiguous = complete;
    ambiguous["missing_by_prefix_year"]["TRN"] = json!({"2024":["January"]});
    assert!(!can_download_missing(&ambiguous, JobOutcome::Success));
}

#[test]
fn activity_is_paged_without_losing_history_and_snapshot_is_small() {
    let root = tempfile::tempdir().unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    for index in 0..2_000 {
        app.apply_worker_event(WorkerEvent::Log {
            level: LogLevel::Info,
            message: format!("Issue {index}"),
        });
    }
    assert_eq!(app.activity("", 0, 50).total, 2_000);
    assert_eq!(app.activity("", 0, 50).entries.len(), 50);
    assert_eq!(
        app.activity("Issue 1999", 0, 50).entries[0].message,
        "Issue 1999"
    );
    assert!(app.snapshot().job.logs.is_empty());
    assert_eq!(app.snapshot().log_count, 2_000);
    app.clear_activity();
    assert_eq!(app.activity("", 0, 50).total, 0);
}

#[test]
fn incomplete_organizer_result_is_retained_as_failure() {
    let root = tempfile::tempdir().unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    app.apply_worker_event(WorkerEvent::Completed {
        outcome: JobOutcome::Success,
        summary: Some(json!({"scan_complete":false,"moved":3})),
    });
    assert_eq!(app.job_state().outcome, JobOutcome::Failed);
    assert_eq!(app.job_state().summary.as_ref().unwrap()["moved"], 3);
}

#[test]
fn settings_patch_preserves_unknown_keys_without_exposing_them_to_frontend() {
    let root = tempfile::tempdir().unwrap();
    std::fs::write(
        root.path().join("settings.json"),
        r#"{"future_preference":{"keep":true},"dark_mode":false}"#,
    )
    .unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    app.update_settings(json!({"dark_mode":true})).unwrap();
    assert_eq!(
        Settings::load(root.path()).settings.extra["future_preference"],
        json!({"keep":true})
    );
    assert!(app.snapshot().settings.extra.is_empty());
    assert!(app.update_settings(json!({"cookies": "secret"})).is_err());
}

#[test]
fn bad_settings_are_preserved_and_input_errors_are_actionable() {
    let root = tempfile::tempdir().unwrap();
    std::fs::write(root.path().join("settings.json"), "invalid JSON").unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    assert!(app.snapshot().settings_error.is_some());
    assert!(app.update_settings(json!({"dark_mode":true})).is_err());
    assert_eq!(
        std::fs::read_to_string(root.path().join("settings.json")).unwrap(),
        "invalid JSON"
    );
    assert!(
        build_request(JobKind::Organize, app.settings(), None, "test".into())
            .unwrap_err()
            .contains("source")
    );
}

#[test]
fn a_later_worker_failure_keeps_partial_organizer_findings() {
    let root = tempfile::tempdir().unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    app.update_settings(json!({"org_src":"source","org_dst":"destination"}))
        .unwrap();
    app.start_job(JobKind::Organize).unwrap();
    app.apply_worker_event(WorkerEvent::Completed { outcome: JobOutcome::Success, summary: Some(json!({"scan_complete":true,"moved":3,"missing_by_prefix_year":{"MRR":{"2024":["January"]}}})) });
    app.apply_worker_event(WorkerEvent::Error {
        message: "The worker exited unexpectedly.".into(),
    });
    app.apply_worker_event(WorkerEvent::Completed {
        outcome: JobOutcome::Failed,
        summary: None,
    });
    let state = app.snapshot();
    assert_eq!(state.organizer_summary.unwrap()["moved"], 3);
    assert_eq!(state.job.summary.unwrap()["moved"], 3);
    assert_eq!(state.organizer_outcome, JobOutcome::Failed);
    assert!(!state.can_download_missing);
}

#[test]
fn failure_does_not_show_an_error_from_an_earlier_job() {
    let root = tempfile::tempdir().unwrap();
    let mut app = TrainsApp::new(root.path().into(), Box::new(UnavailableWorker));
    app.apply_worker_event(WorkerEvent::Error {
        message: "Earlier network failure".into(),
    });
    app.start_job(JobKind::Magazines).unwrap();
    app.apply_worker_event(WorkerEvent::Completed {
        outcome: JobOutcome::Failed,
        summary: Some(json!({"scan_complete":false})),
    });
    assert!(!app.job_state().message.contains("Earlier"));
    assert_eq!(app.snapshot().error_count, 1);
}

#[cfg(feature = "test-worker")]
mod lifecycle {
    use super::*;
    use std::{
        path::PathBuf,
        sync::{Mutex, mpsc},
        time::{Duration, Instant},
    };
    use trains_com_downloader::worker::{
        CommandWorkerLauncher, WorkerError, WorkerHandle, WorkerLauncher, WorkerRequest,
    };
    struct GatedLauncher {
        gate: Mutex<mpsc::Receiver<()>>,
        mode: &'static str,
    }
    impl WorkerLauncher for GatedLauncher {
        fn start(
            &self,
            mut request: WorkerRequest,
            root: PathBuf,
        ) -> Result<WorkerHandle, WorkerError> {
            self.gate.lock().unwrap().recv().unwrap();
            request.options = json!({"fake_mode":self.mode});
            CommandWorkerLauncher::new(env!("CARGO_BIN_EXE_fake_worker"), Vec::<String>::new())
                .start(request, root)
        }
    }
    fn wait(app: &mut TrainsApp, condition: impl Fn(&TrainsApp) -> bool) {
        let deadline = Instant::now() + Duration::from_secs(3);
        while Instant::now() < deadline {
            app.poll_worker();
            if condition(app) {
                return;
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        panic!("Worker lifecycle did not reach the expected state.");
    }
    #[test]
    fn stop_during_launch_is_forwarded_and_a_second_job_is_rejected() {
        let root = tempfile::tempdir().unwrap();
        let (release, gate) = mpsc::channel();
        let mut app = TrainsApp::new(
            root.path().into(),
            Box::new(GatedLauncher {
                gate: Mutex::new(gate),
                mode: "cancel",
            }),
        );
        app.start_job(JobKind::Magazines).unwrap();
        app.request_stop();
        assert!(app.start_job(JobKind::TrackPlans).is_err());
        release.send(()).unwrap();
        wait(&mut app, TrainsApp::can_start_job);
        assert_eq!(app.job_state().outcome, JobOutcome::Cancelled);
    }
    #[test]
    fn terminal_message_does_not_release_a_process_that_is_still_running() {
        let root = tempfile::tempdir().unwrap();
        let (release, gate) = mpsc::channel();
        let mut app = TrainsApp::new(
            root.path().into(),
            Box::new(GatedLauncher {
                gate: Mutex::new(gate),
                mode: "completed-delayed-close",
            }),
        );
        app.start_job(JobKind::Magazines).unwrap();
        release.send(()).unwrap();
        wait(&mut app, |app| {
            app.job_state().outcome == JobOutcome::Success
        });
        assert!(!app.can_start_job());
        assert!(app.start_job(JobKind::TrackPlans).is_err());
        wait(&mut app, TrainsApp::can_start_job);
    }
}
