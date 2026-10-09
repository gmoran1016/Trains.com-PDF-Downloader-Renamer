use std::{
    fs,
    path::PathBuf,
    sync::{
        Arc,
        mpsc::{self, Receiver, TryRecvError},
    },
    thread,
    time::Duration,
};

use eframe::egui;

use crate::{
    model::{AppPage, JobOutcome, JobState, LogEntry, LogLevel},
    settings::{Settings, SettingsError},
    theme,
    tray::{DesktopTray, TrayAction, TrayController},
    worker::{WorkerError, WorkerEvent, WorkerHandle, WorkerRequest},
};

pub use crate::worker::{UnavailableWorker, WorkerLauncher};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum CloseChoice {
    MinimizeToTray,
    StopAndQuit,
    Cancel,
}

pub struct TrainsApp {
    data_dir: PathBuf,
    worker: Arc<dyn WorkerLauncher>,
    settings: Settings,
    settings_error: Option<String>,
    job: JobState,
    pending_request: Option<WorkerRequest>,
    queued_request: Option<WorkerRequest>,
    start_result: Option<Receiver<Result<WorkerHandle, WorkerError>>>,
    active_worker: Option<WorkerHandle>,
    next_job_sequence: u64,
    activity_filter: String,
    activity_projection: ActivityProjection,
    activity_resize_dirty: bool,
    account_open: bool,
    tray: Option<Box<dyn TrayController>>,
    close_dialog_open: bool,
    quit_after_worker: bool,
    clear_cache_confirmation: bool,
    notice: Option<String>,
    fonts_installed: bool,
}

#[derive(Default)]
struct ActivityProjection {
    filter: String,
    indexed_len: usize,
    matching_rows: Vec<usize>,
}

impl ActivityProjection {
    fn sync(&mut self, logs: &[LogEntry], filter: &str) {
        let filter = filter.trim().to_lowercase();
        if self.filter != filter || self.indexed_len > logs.len() {
            self.filter = filter;
            self.indexed_len = 0;
            self.matching_rows.clear();
        }

        for (offset, entry) in logs[self.indexed_len..].iter().enumerate() {
            if self.filter.is_empty() || entry.message.to_lowercase().contains(&self.filter) {
                self.matching_rows.push(self.indexed_len + offset);
            }
        }
        self.indexed_len = logs.len();
    }
}

impl TrainsApp {
    pub fn new(data_dir: PathBuf, worker: Box<dyn WorkerLauncher>) -> Self {
        let loaded = Settings::load(&data_dir);
        Self {
            data_dir,
            worker: Arc::from(worker),
            settings: loaded.settings,
            settings_error: loaded.parse_error,
            job: JobState::default(),
            pending_request: None,
            queued_request: None,
            start_result: None,
            active_worker: None,
            next_job_sequence: 1,
            activity_filter: String::new(),
            activity_projection: ActivityProjection::default(),
            activity_resize_dirty: false,
            account_open: false,
            tray: None,
            close_dialog_open: false,
            quit_after_worker: false,
            clear_cache_confirmation: false,
            notice: None,
            fonts_installed: false,
        }
    }

    pub const fn active_page(&self) -> AppPage {
        self.settings.selected_page
    }

    pub fn set_active_page(&mut self, page: AppPage) {
        if self.settings.selected_page != page {
            self.settings.selected_page = page;
            self.settings_error = self.save_settings().err().map(|error| error.to_string());
            if self.notice.as_deref() == Some("Settings saved.") {
                self.notice = None;
            }
        }
    }

    pub fn set_dark_mode(&mut self, dark_mode: bool) {
        if self.settings.dark_mode != dark_mode {
            self.settings.dark_mode = dark_mode;
            self.save_settings_notice();
        }
    }

    pub fn job_state(&self) -> &JobState {
        &self.job
    }

    pub fn settings(&self) -> &Settings {
        &self.settings
    }

    pub fn settings_mut(&mut self) -> &mut Settings {
        &mut self.settings
    }

    pub fn settings_error(&self) -> Option<&str> {
        self.settings_error.as_deref()
    }

    pub fn save_settings(&self) -> Result<(), SettingsError> {
        self.settings.save(&self.data_dir)
    }

    pub fn data_dir(&self) -> &std::path::Path {
        &self.data_dir
    }

    pub fn set_tray(&mut self, tray: Box<dyn TrayController>) {
        self.tray = Some(tray);
    }

    pub fn install_desktop_tray(&mut self, ctx: egui::Context) {
        match DesktopTray::create(ctx) {
            Ok(tray) => self.set_tray(Box::new(tray)),
            Err(_) => {
                self.notice = Some(
                    "System tray controls are unavailable on this desktop; close choices remain available while a job runs.".to_owned(),
                );
            }
        }
    }

    pub fn tray_available(&self) -> bool {
        self.tray.as_ref().is_some_and(|tray| tray.available())
    }

    pub fn handle_window_close(&mut self) -> bool {
        let work_in_progress = self.job.outcome == JobOutcome::Running
            || self.queued_request.is_some()
            || self.start_result.is_some();
        if work_in_progress {
            self.close_dialog_open = true;
            false
        } else {
            true
        }
    }

    pub fn close_dialog_open(&self) -> bool {
        self.close_dialog_open
    }

    pub(crate) fn cancel_close_dialog(&mut self) {
        self.close_dialog_open = false;
    }

    pub(crate) fn choose_close_action(&mut self, choice: CloseChoice, ctx: &egui::Context) {
        match choice {
            CloseChoice::MinimizeToTray if self.tray_available() => {
                self.close_dialog_open = false;
                ctx.send_viewport_cmd(egui::ViewportCommand::Visible(false));
            }
            CloseChoice::MinimizeToTray => {
                self.notice =
                    Some("The system tray is unavailable, so the app stayed open.".to_owned());
            }
            CloseChoice::StopAndQuit => {
                self.close_dialog_open = false;
                self.quit_after_worker = true;
                self.request_stop();
                self.close_after_worker_if_ready(ctx);
            }
            CloseChoice::Cancel => self.close_dialog_open = false,
        }
    }

    pub fn pending_request(&self) -> Option<&WorkerRequest> {
        self.pending_request.as_ref()
    }

    pub fn take_pending_request(&mut self) -> Option<WorkerRequest> {
        self.pending_request.take()
    }

    pub fn apply_worker_event(&mut self, event: WorkerEvent) {
        match event {
            WorkerEvent::Started => {
                self.job.outcome = JobOutcome::Running;
                self.job.message = "Working…".to_owned();
            }
            WorkerEvent::Log { level, message } => {
                let entry = LogEntry { level, message };
                if entry.level == LogLevel::Error {
                    self.job.errors.push(entry.clone());
                }
                self.job.logs.push(entry);
            }
            WorkerEvent::Progress {
                done,
                total,
                message,
                per_magazine,
            } => {
                self.job.outcome = JobOutcome::Running;
                if let Some(message) = message {
                    self.job.message = message;
                }
                if let Some(done) = done {
                    self.job.done = Some(done);
                }
                if let Some(total) = total {
                    self.job.total = Some(total);
                }
                if let Some(per_magazine) = per_magazine {
                    self.job.per_magazine = per_magazine;
                }
            }
            WorkerEvent::Error { message } => {
                let entry = LogEntry {
                    level: LogLevel::Error,
                    message: message.clone(),
                };
                self.job.errors.push(entry.clone());
                self.job.logs.push(entry);
                self.job.message = message;
            }
            WorkerEvent::Completed { outcome, summary } => {
                self.job.outcome = outcome;
                self.job.summary = summary;
                self.job.stop_requested = false;
                self.job.message = match outcome {
                    JobOutcome::Success => "Job complete.".to_owned(),
                    JobOutcome::NoResults => "No matching results were found.".to_owned(),
                    JobOutcome::Failed => "The job failed.".to_owned(),
                    JobOutcome::Cancelled => "The job was cancelled.".to_owned(),
                    JobOutcome::Idle | JobOutcome::Running => outcome.label().to_owned(),
                };
            }
        }
    }

    pub fn request_stop(&mut self) {
        if self.job.outcome != JobOutcome::Running || self.job.stop_requested {
            return;
        }
        self.job.stop_requested = true;
        self.job.message = "Stop requested; waiting for the worker to finish safely.".to_owned();
        if let Some(worker) = self.active_worker.as_mut() {
            let _ = worker.request_cancel();
        }
    }

    pub(crate) fn clear_activity(&mut self) {
        self.job.logs.clear();
        self.job.errors.clear();
        self.activity_projection = ActivityProjection::default();
    }

    pub fn can_start_job(&self) -> bool {
        self.job.outcome != JobOutcome::Running
            && self.queued_request.is_none()
            && self.start_result.is_none()
            && self.active_worker.is_none()
    }

    pub(crate) fn activity_filter_mut(&mut self) -> &mut String {
        &mut self.activity_filter
    }

    pub(crate) fn activity_rows(&mut self) -> (&[LogEntry], &[usize]) {
        self.activity_projection
            .sync(&self.job.logs, &self.activity_filter);
        (&self.job.logs, &self.activity_projection.matching_rows)
    }

    pub(crate) fn record_activity_height(&mut self, height: f32) {
        if (self.settings.activity_height - height).abs() > 1.0 {
            self.settings.activity_height = height;
            self.activity_resize_dirty = true;
        }
    }

    pub(crate) fn save_activity_resize_if_released(&mut self, pointer_down: bool) {
        if self.activity_resize_dirty && !pointer_down {
            self.activity_resize_dirty = false;
            self.save_settings_notice();
        }
    }

    pub(crate) fn queue_request(&mut self, request: WorkerRequest) {
        if !self.can_start_job() {
            return;
        }
        if let Err(error) = self.save_settings() {
            self.settings_error = Some(error.to_string());
            self.notice = Some(
                "Settings could not be saved; the job is using the current values.".to_owned(),
            );
        } else {
            self.notice = Some("Job request prepared.".to_owned());
        }
        let logs = std::mem::take(&mut self.job.logs);
        let errors = std::mem::take(&mut self.job.errors);
        self.pending_request = Some(request);
        self.queued_request = self.pending_request.clone();
        self.job = JobState {
            outcome: JobOutcome::Running,
            message: "Starting the worker…".to_owned(),
            logs,
            errors,
            ..JobState::default()
        };
    }

    pub(crate) fn next_job_id(&mut self) -> String {
        let sequence = self.next_job_sequence;
        self.next_job_sequence += 1;
        format!("job-{}-{sequence}", std::process::id())
    }

    pub(crate) fn account_open(&self) -> bool {
        self.account_open
    }

    pub(crate) fn set_account_open(&mut self, open: bool) {
        self.account_open = open;
    }

    pub(crate) fn clear_cache_confirmation(&self) -> bool {
        self.clear_cache_confirmation
    }

    pub(crate) fn set_clear_cache_confirmation(&mut self, open: bool) {
        if open && !self.can_start_job() {
            self.clear_cache_confirmation = false;
            self.notice = Some("Cache files cannot be cleared while a job is running.".to_owned());
        } else {
            self.clear_cache_confirmation = open;
        }
    }

    pub(crate) fn confirm_clear_cache(&mut self) {
        if !self.can_start_job() {
            self.clear_cache_confirmation = false;
            self.notice = Some("Cache files cannot be cleared while a job is running.".to_owned());
            return;
        }
        let mut removed = Vec::new();
        let mut failures = Vec::new();
        for (label, name) in [
            ("download progress", "download_progress.json"),
            ("special issue index", "special_issues.json"),
        ] {
            match fs::remove_file(self.data_dir.join(name)) {
                Ok(()) => removed.push(label),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => failures.push(label),
            }
        }
        self.notice = if failures.is_empty() {
            if removed.is_empty() {
                Some("There were no cache files to clear.".to_owned())
            } else {
                Some("Cache cleared. Settings, cookies, and logs were kept.".to_owned())
            }
        } else {
            Some(format!("Could not clear: {}.", failures.join(" and ")))
        };
        self.clear_cache_confirmation = false;
    }

    pub(crate) fn notice(&self) -> Option<&str> {
        self.notice.as_deref()
    }

    pub(crate) fn save_settings_notice(&mut self) {
        self.settings_error = self.save_settings().err().map(|error| error.to_string());
        if self.settings_error.is_none() {
            self.notice = Some("Settings saved.".to_owned());
        } else {
            self.notice = Some("Settings could not be saved.".to_owned());
        }
    }

    pub(crate) fn queue_magazines(&mut self) {
        let job_id = self.next_job_id();
        let request = crate::ui::magazines::build_request(&self.settings, job_id);
        self.queue_request(request);
    }

    pub(crate) fn queue_track_plans(&mut self) {
        let job_id = self.next_job_id();
        let request = crate::ui::track_plans::build_request(&self.settings, job_id);
        self.queue_request(request);
    }

    pub(crate) fn queue_organize(&mut self) {
        let job_id = self.next_job_id();
        let request = crate::ui::organize::build_organize_request(&self.settings, job_id);
        self.queue_request(request);
    }

    pub(crate) fn queue_missing_download(&mut self) {
        let Some(summary) = self.job.summary.clone() else {
            return;
        };
        let outcome = self.job.outcome;
        let settings = self.settings.clone();
        let job_id = self.next_job_id();
        let Some(request) =
            crate::ui::organize::build_missing_request(&summary, outcome, &settings, job_id)
        else {
            return;
        };
        self.queue_request(request);
    }

    fn dispatch_queued_request(&mut self, ctx: &egui::Context) {
        let Some(request) = self.queued_request.take() else {
            return;
        };
        let (sender, receiver) = mpsc::channel();
        let launcher = Arc::clone(&self.worker);
        let data_dir = self.data_dir.clone();
        let repaint_context = ctx.clone();
        match thread::Builder::new()
            .name("trains-worker-launch".to_owned())
            .spawn(move || {
                let result =
                    launcher.start_with_repaint(request, data_dir, repaint_context.clone());
                let _ = sender.send(result);
                repaint_context.request_repaint();
            }) {
            Ok(_) => self.start_result = Some(receiver),
            Err(_) => self.fail_worker_start("The worker could not be scheduled to start."),
        }
    }

    fn fail_worker_start(&mut self, message: &str) {
        self.apply_worker_event(WorkerEvent::Error {
            message: message.to_owned(),
        });
        self.apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Failed,
            summary: None,
        });
    }

    fn poll_worker(&mut self) {
        if let Some(receiver) = &self.start_result {
            match receiver.try_recv() {
                Ok(Ok(worker)) => {
                    self.start_result = None;
                    self.active_worker = Some(worker);
                }
                Ok(Err(WorkerError::Bundle(error))) => {
                    self.start_result = None;
                    self.fail_worker_start(&error.to_string());
                }
                Ok(Err(_error)) => {
                    self.start_result = None;
                    self.fail_worker_start("The Python worker could not be started.");
                }
                Err(TryRecvError::Disconnected) => {
                    self.start_result = None;
                    self.fail_worker_start("The Python worker stopped during startup.");
                }
                Err(TryRecvError::Empty) => {}
            }
        }

        let stop_requested = self.job.stop_requested;
        let (events, finished) = if let Some(worker) = self.active_worker.as_mut() {
            if stop_requested {
                let _ = worker.request_cancel();
            }
            let mut events = worker.try_recv();
            let _ = worker.poll_exit();
            events.extend(worker.try_recv());
            (events, worker.is_finished())
        } else {
            (Vec::new(), false)
        };
        for event in events {
            self.apply_worker_event(event);
        }
        if finished {
            self.active_worker = None;
        }
    }

    fn poll_tray_actions(&mut self, ctx: &egui::Context) {
        let actions = self
            .tray
            .as_mut()
            .map_or_else(Vec::new, |tray| tray.drain_actions());
        for action in actions {
            match action {
                TrayAction::ShowWindow => {
                    ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                    ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                }
                TrayAction::Quit => {
                    if self.handle_window_close() {
                        ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                    } else {
                        ctx.send_viewport_cmd(egui::ViewportCommand::Visible(true));
                        ctx.send_viewport_cmd(egui::ViewportCommand::Focus);
                    }
                }
            }
        }
    }

    fn close_after_worker_if_ready(&mut self, ctx: &egui::Context) {
        if self.quit_after_worker
            && self.job.outcome != JobOutcome::Running
            && self.queued_request.is_none()
            && self.start_result.is_none()
            && self.active_worker.is_none()
        {
            self.quit_after_worker = false;
            ctx.send_viewport_cmd(egui::ViewportCommand::Close);
        }
    }
}

impl eframe::App for TrainsApp {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        if !self.fonts_installed {
            theme::install_fonts(ui.ctx());
            self.fonts_installed = true;
        }
        theme::apply(ui.ctx(), self.settings.dark_mode);
        let ctx = ui.ctx().clone();
        self.poll_tray_actions(&ctx);
        if ctx.input(|input| input.viewport().close_requested()) && !self.handle_window_close() {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
        }
        self.dispatch_queued_request(&ctx);
        self.poll_worker();
        crate::ui::shell::show(self, ui, &ctx);
        self.close_after_worker_if_ready(&ctx);
        if self.active_worker.is_some() {
            ctx.request_repaint_after(Duration::from_secs(1));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{ActivityProjection, TrainsApp, UnavailableWorker};
    use crate::{
        model::{AppPage, LogEntry},
        settings::Settings,
        worker::WorkerEvent,
    };

    #[test]
    fn changing_work_area_persists_without_a_success_notice() {
        let data_dir = tempfile::tempdir().expect("temporary app data root");
        let mut app = TrainsApp::new(data_dir.path().to_path_buf(), Box::new(UnavailableWorker));

        app.set_active_page(AppPage::TrackPlans);

        assert_eq!(app.active_page(), AppPage::TrackPlans);
        assert_eq!(
            Settings::load(data_dir.path()).settings.selected_page,
            AppPage::TrackPlans
        );
        assert!(app.notice.is_none());
    }

    #[test]
    fn cache_confirmation_cannot_remove_worker_state_during_a_job() {
        let data_dir = tempfile::tempdir().expect("temporary app data root");
        let progress = data_dir.path().join("download_progress.json");
        let specials = data_dir.path().join("special_issues.json");
        std::fs::write(&progress, b"in-flight progress").expect("write progress fixture");
        std::fs::write(&specials, b"in-flight specials").expect("write specials fixture");
        let mut app = TrainsApp::new(data_dir.path().to_path_buf(), Box::new(UnavailableWorker));
        app.apply_worker_event(WorkerEvent::Started);
        app.set_clear_cache_confirmation(true);

        app.confirm_clear_cache();

        assert_eq!(
            std::fs::read(progress).expect("progress remains"),
            b"in-flight progress"
        );
        assert_eq!(
            std::fs::read(specials).expect("specials remain"),
            b"in-flight specials"
        );
        assert!(!app.clear_cache_confirmation());
    }

    #[test]
    fn activity_projection_indexes_only_new_rows_for_unchanged_filter() {
        let logs = vec![
            LogEntry {
                level: crate::model::LogLevel::Info,
                message: "first match".to_owned(),
            },
            LogEntry {
                level: crate::model::LogLevel::Info,
                message: "second".to_owned(),
            },
        ];
        let mut projection = ActivityProjection::default();
        projection.sync(&logs[..1], "match");
        assert_eq!(projection.matching_rows, vec![0]);
        projection.sync(&logs, "match");
        assert_eq!(projection.indexed_len, 2);
        assert_eq!(projection.matching_rows, vec![0]);
        projection.sync(&logs, "second");
        assert_eq!(projection.matching_rows, vec![1]);
    }
}
