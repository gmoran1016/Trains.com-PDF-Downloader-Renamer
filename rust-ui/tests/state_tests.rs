use trains_com_downloader::{
    app::{TrainsApp, WorkerLauncher},
    model::{AppPage, JobOutcome, MagazineProgress},
    worker::WorkerEvent,
};

struct FakeWorker;

impl WorkerLauncher for FakeWorker {}

#[test]
fn outcome_labels_distinguish_all_six_states() {
    let states = [
        (JobOutcome::Idle, "Ready"),
        (JobOutcome::Running, "Running"),
        (JobOutcome::Success, "Complete"),
        (JobOutcome::NoResults, "No results"),
        (JobOutcome::Failed, "Failed"),
        (JobOutcome::Cancelled, "Cancelled"),
    ];

    for (outcome, expected) in states {
        assert_eq!(outcome.label(), expected);
    }
}

#[test]
fn startup_selects_magazines() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let app = TrainsApp::new(data_dir.path().to_path_buf(), Box::new(FakeWorker));

    assert_eq!(app.active_page(), AppPage::Magazines);
}

#[test]
fn status_only_progress_keeps_overall_and_magazine_counters() {
    let data_dir = tempfile::tempdir().expect("temporary data root");
    let mut app = TrainsApp::new(data_dir.path().to_path_buf(), Box::new(FakeWorker));
    let mut magazine_progress = std::collections::BTreeMap::new();
    magazine_progress.insert(
        "Model Railroader".to_owned(),
        MagazineProgress { done: 3, total: 9 },
    );

    app.apply_worker_event(WorkerEvent::Progress {
        done: Some(3),
        total: Some(20),
        message: None,
        per_magazine: Some(magazine_progress),
    });
    app.apply_worker_event(WorkerEvent::Progress {
        done: None,
        total: None,
        message: Some("3 / 20 issues · almost done".to_owned()),
        per_magazine: None,
    });

    assert_eq!(app.job_state().done, Some(3));
    assert_eq!(app.job_state().total, Some(20));
    assert_eq!(
        app.job_state().per_magazine.get("Model Railroader"),
        Some(&MagazineProgress { done: 3, total: 9 })
    );
    assert_eq!(app.job_state().message, "3 / 20 issues · almost done");

    app.apply_worker_event(WorkerEvent::Progress {
        done: None,
        total: None,
        message: None,
        per_magazine: Some(std::collections::BTreeMap::new()),
    });
    assert!(app.job_state().per_magazine.is_empty());
}
