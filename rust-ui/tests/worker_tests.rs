use std::{
    path::PathBuf,
    time::{Duration, Instant},
};

use trains_com_downloader::model::JobOutcome;
use trains_com_downloader::worker::{
    CommandWorkerLauncher, JobKind, WorkerEvent, WorkerLauncher, WorkerRequest,
};

fn launcher() -> CommandWorkerLauncher {
    CommandWorkerLauncher::new(env!("CARGO_BIN_EXE_fake_worker"), Vec::<String>::new())
}

fn request(job_id: &str, mode: &str) -> WorkerRequest {
    WorkerRequest {
        job_id: job_id.to_owned(),
        job_kind: JobKind::Magazines,
        options: serde_json::json!({"fake_mode": mode}),
    }
}

fn terminal_events(handle: &mut trains_com_downloader::worker::WorkerHandle) -> Vec<WorkerEvent> {
    let deadline = Instant::now() + Duration::from_secs(3);
    let mut events = Vec::new();
    while Instant::now() < deadline {
        events.extend(handle.try_recv());
        let _ = handle.poll_exit();
        events.extend(handle.try_recv());
        if handle.is_finished() {
            return events;
        }
        thread_sleep();
    }
    panic!("worker did not produce a terminal event; received {events:?}");
}

fn thread_sleep() {
    std::thread::sleep(Duration::from_millis(5));
}

fn outcome(events: &[WorkerEvent]) -> Option<JobOutcome> {
    events.iter().rev().find_map(|event| match event {
        WorkerEvent::Completed { outcome, .. } => Some(*outcome),
        _ => None,
    })
}

#[test]
fn worker_events_do_not_block_ui() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(request("nonblocking", "delayed"), temp.path().to_path_buf())
        .expect("start fake worker");

    let started = Instant::now();
    let _ = handle.try_recv();
    assert!(started.elapsed() < Duration::from_millis(100));

    let started = Instant::now();
    let _ = handle.poll_exit();
    assert!(started.elapsed() < Duration::from_millis(100));

    assert_eq!(
        outcome(&terminal_events(&mut handle)),
        Some(JobOutcome::Success)
    );
}

#[test]
fn no_results_remains_distinct_from_success_and_failure() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(
            request("no-results", "no-results"),
            temp.path().to_path_buf(),
        )
        .expect("start fake worker");

    assert_eq!(
        outcome(&terminal_events(&mut handle)),
        Some(JobOutcome::NoResults)
    );
}

#[test]
fn wrong_version_and_job_id_fail() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    for (job_id, mode) in [("bad-version", "wrong-version"), ("bad-id", "wrong-job-id")] {
        let mut handle = launcher()
            .start(request(job_id, mode), temp.path().to_path_buf())
            .expect("start fake worker");
        let events = terminal_events(&mut handle);
        assert_eq!(outcome(&events), Some(JobOutcome::Failed), "mode {mode}");
        assert!(
            events
                .iter()
                .any(|event| matches!(event, WorkerEvent::Error { .. }))
        );
    }
}

#[test]
fn crash_before_completed_fails() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(request("crash", "crash"), temp.path().to_path_buf())
        .expect("start fake worker");
    let events = terminal_events(&mut handle);
    assert_eq!(outcome(&events), Some(JobOutcome::Failed));
    assert!(
        events
            .iter()
            .any(|event| matches!(event, WorkerEvent::Started))
    );
    assert!(
        events
            .iter()
            .any(|event| matches!(event, WorkerEvent::Error { .. }))
    );
}

#[test]
fn nonzero_exit_after_success_event_is_failed() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(
            request("completed-nonzero", "completed-nonzero"),
            temp.path().to_path_buf(),
        )
        .expect("start fake worker");
    let events = terminal_events(&mut handle);

    assert_eq!(outcome(&events), Some(JobOutcome::Failed));
    assert!(
        events
            .iter()
            .any(|event| matches!(event, WorkerEvent::Error { .. }))
    );
}

#[test]
fn malformed_record_after_success_event_is_failed() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(
            request("completed-trailing-invalid", "completed-trailing-invalid"),
            temp.path().to_path_buf(),
        )
        .expect("start fake worker");
    let events = terminal_events(&mut handle);

    assert_eq!(outcome(&events), Some(JobOutcome::Failed));
    assert!(
        events
            .iter()
            .any(|event| matches!(event, WorkerEvent::Error { .. }))
    );
}

#[test]
fn cancel_sends_v1_command() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut handle = launcher()
        .start(request("cancel", "cancel"), temp.path().to_path_buf())
        .expect("start fake worker");
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline && !handle.try_recv().contains(&WorkerEvent::Started) {
        thread_sleep();
    }

    handle.request_cancel().expect("send cancellation request");
    let events = terminal_events(&mut handle);
    assert_eq!(outcome(&events), Some(JobOutcome::Cancelled));
}

#[test]
fn cookie_value_is_never_forwarded() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let cookie_file = temp.path().join("session_cookies.json");
    std::fs::write(&cookie_file, "COOKIE_SENTINEL_SECRET").expect("write isolated sentinel");
    let request = WorkerRequest {
        job_id: "cookie-check".to_owned(),
        job_kind: JobKind::Magazines,
        options: serde_json::json!({"fake_mode": "cookie", "cookies_path": cookie_file}),
    };
    let mut handle = launcher()
        .start(request, PathBuf::from(temp.path()))
        .expect("start fake worker");
    let events = terminal_events(&mut handle);
    let summary = events.iter().find_map(|event| match event {
        WorkerEvent::Completed { summary, .. } => summary.as_ref(),
        _ => None,
    });
    assert_eq!(
        summary,
        Some(&serde_json::json!({"cookie_value_forwarded": false}))
    );
    assert!(events.iter().all(|event| match event {
        WorkerEvent::Log { message, .. } | WorkerEvent::Error { message } => {
            !message.contains("COOKIE_SENTINEL_SECRET")
        }
        _ => true,
    }));
}
