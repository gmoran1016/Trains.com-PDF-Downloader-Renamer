use std::{
    path::PathBuf,
    sync::mpsc::{self, Receiver, TryRecvError},
};
#[cfg(feature = "desktop-smoke")]
use std::{
    thread,
    time::{Duration, Instant},
};

use eframe::egui::{self, Vec2};
use egui_kittest::{Harness, kittest::Queryable};
use trains_com_downloader::{
    app::{TrainsApp, UnavailableWorker},
    model::{AppPage, JobOutcome},
    tray::{TrayAction, TrayController},
    worker::WorkerEvent,
};

#[cfg(feature = "desktop-smoke")]
use trains_com_downloader::worker::FakeWorkerLauncher;

fn harness(data_dir: PathBuf, size: Vec2) -> Harness<'static, TrainsApp> {
    Harness::builder()
        .with_size(size)
        .build_eframe(move |_| TrainsApp::new(data_dir, Box::new(UnavailableWorker)))
}

fn has_command(
    harness: &Harness<'_, TrainsApp>,
    expected: fn(&egui::ViewportCommand) -> bool,
) -> bool {
    harness
        .output()
        .viewport_output
        .get(&egui::ViewportId::ROOT)
        .is_some_and(|viewport| viewport.commands.iter().any(expected))
}

struct FakeTray {
    receiver: Receiver<TrayAction>,
}

impl TrayController for FakeTray {
    fn available(&self) -> bool {
        true
    }

    fn drain_actions(&mut self) -> Vec<TrayAction> {
        let mut actions = Vec::new();
        loop {
            match self.receiver.try_recv() {
                Ok(action) => actions.push(action),
                Err(TryRecvError::Empty | TryRecvError::Disconnected) => return actions,
            }
        }
    }
}

fn harness_with_fake_tray(
    data_dir: PathBuf,
    size: Vec2,
) -> (Harness<'static, TrainsApp>, mpsc::Sender<TrayAction>) {
    let (sender, receiver) = mpsc::channel();
    let mut app = TrainsApp::new(data_dir, Box::new(UnavailableWorker));
    app.set_tray(Box::new(FakeTray { receiver }));
    let harness = Harness::builder()
        .with_size(size)
        .build_eframe(move |_| app);
    (harness, sender)
}

#[test]
fn close_idle_exits() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));

    assert!(harness.state_mut().handle_window_close());
}

#[test]
fn close_running_cancel_keeps_window() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));
    harness.state_mut().apply_worker_event(WorkerEvent::Started);
    harness.run();

    assert!(!harness.state_mut().handle_window_close());
    harness.run();
    harness.get_by_label("Cancel").click();
    harness.step();

    assert_eq!(harness.state().job_state().outcome, JobOutcome::Running);
    assert!(!harness.state().job_state().stop_requested);
    assert!(!harness.state().close_dialog_open());
}

#[test]
fn close_running_minimize_keeps_worker() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let (mut harness, _) =
        harness_with_fake_tray(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));
    harness.state_mut().apply_worker_event(WorkerEvent::Started);
    harness.run();

    assert!(!harness.state_mut().handle_window_close());
    harness.run();
    harness.get_by_label("Minimize to Tray").click();
    harness.step();

    assert_eq!(harness.state().job_state().outcome, JobOutcome::Running);
    assert!(!harness.state().job_state().stop_requested);
    assert!(has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Visible(false)
    )));
}

#[test]
fn close_running_stop_waits_for_worker() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));
    harness.state_mut().apply_worker_event(WorkerEvent::Started);
    harness.run();

    assert!(!harness.state_mut().handle_window_close());
    harness.run();
    harness.get_by_label("Stop & Quit").click();
    harness.step();
    assert_eq!(harness.state().job_state().outcome, JobOutcome::Running);
    assert!(harness.state().job_state().stop_requested);
    assert!(!has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Close
    )));

    harness
        .state_mut()
        .apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Cancelled,
            summary: None,
        });
    harness.step();
    assert!(has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Close
    )));
}

#[test]
fn tray_actions_show_and_quit() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let (mut harness, sender) =
        harness_with_fake_tray(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));

    sender
        .send(TrayAction::ShowWindow)
        .expect("send tray action");
    harness.step();
    assert!(has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Visible(true)
    )));
    assert!(has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Focus
    )));

    sender.send(TrayAction::Quit).expect("send tray quit");
    harness.step();
    assert!(has_command(&harness, |command| matches!(
        command,
        egui::ViewportCommand::Close
    )));
}

#[test]
fn keyboard_reaches_primary_actions() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));
    let mut focused = false;
    for _ in 0..64 {
        harness.key_press(egui::Key::Tab);
        harness.step();
        if harness
            .get_by_label("Download selected magazines")
            .is_focused()
        {
            focused = true;
            break;
        }
    }
    assert!(focused, "Tab should reach the primary magazine action");

    harness.key_press(egui::Key::Enter);
    harness.step();
    assert!(harness.state().pending_request().is_some());
}

fn assert_layout(harness: &mut Harness<'static, TrainsApp>, width: f32, height: f32) {
    for label in ["Magazines", "Track Plans", "Organize", "Account"] {
        let bounds = harness.get_by_label(label).rect();
        assert!(
            bounds.min.x >= 0.0 && bounds.max.x <= width,
            "{label}: {bounds:?}"
        );
        assert!(
            bounds.min.y >= 0.0 && bounds.max.y <= height,
            "{label}: {bounds:?}"
        );
    }

    let magazine_action = harness.get_by_label("Download selected magazines").rect();
    assert!(magazine_action.max.x <= width && magazine_action.max.y <= height);
    let activity_filter = harness.get_by_label("Filter activity").rect();
    assert!(activity_filter.max.x <= width && activity_filter.max.y <= height);
    let activity_resize = harness.get_by_label("Resize Activity").rect();
    assert!(activity_resize.max.x <= width && activity_resize.max.y <= height);

    harness.get_by_label("Track Plans").click();
    harness.run();
    let track_action = harness.get_by_label("Download all track plans").rect();
    assert!(track_action.max.x <= width && track_action.max.y <= height);

    harness.get_by_label("Organize").click();
    harness.run();
    let organize_action = harness.get_by_label("Organize PDFs").rect();
    assert!(organize_action.max.x <= width && organize_action.max.y <= height);
}

#[test]
fn desktop_layout_1440x900() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(1440.0, 900.0));

    assert_eq!(harness.state().active_page(), AppPage::Magazines);
    assert_layout(&mut harness, 1440.0, 900.0);
}

#[test]
fn desktop_layout_800x620() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut harness = harness(temp.path().to_path_buf(), Vec2::new(800.0, 620.0));

    assert_eq!(harness.state().active_page(), AppPage::Magazines);
    assert_layout(&mut harness, 800.0, 620.0);
}

#[test]
#[cfg(feature = "desktop-smoke")]
fn smoke_worker_releases_the_job_slot_for_consecutive_jobs() {
    let temp = tempfile::tempdir().expect("temporary app data root");
    let mut app = TrainsApp::new(temp.path().to_path_buf(), Box::new(FakeWorkerLauncher));
    app.settings_mut().selected_magazines = vec!["Model Railroader".to_owned()];
    let mut harness = Harness::builder()
        .with_size(Vec2::new(1440.0, 900.0))
        .build_eframe(move |_| app);

    for attempt in 1..=2 {
        harness.get_by_label("Download selected magazines").click();
        harness.step();
        let deadline = Instant::now() + Duration::from_secs(8);
        while !harness.state().can_start_job() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(30));
            harness.step();
        }
        assert!(
            harness.state().can_start_job(),
            "smoke job {attempt} should finish and release its worker slot"
        );
        assert_eq!(harness.state().job_state().outcome, JobOutcome::Success);
    }
}
