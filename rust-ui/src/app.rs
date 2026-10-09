//! Desktop state without a dependency on a rendering toolkit.
pub use crate::worker::{UnavailableWorker, WorkerLauncher};
use crate::{
    model::{AppPage, JobOutcome, JobState, LogEntry, LogLevel},
    requests,
    settings::Settings,
    worker::{JobKind, WorkerEvent, WorkerHandle, WorkerNotifier},
};
use serde::Serialize;
use serde_json::Value;
use std::{
    fs,
    path::PathBuf,
    sync::{
        Arc,
        mpsc::{self, Receiver, TryRecvError},
    },
    thread,
};

#[derive(Clone, Serialize)]
pub struct Snapshot {
    pub settings: Settings,
    pub settings_error: Option<String>,
    pub job: JobState,
    pub busy: bool,
    pub log_count: usize,
    pub error_count: usize,
    pub cookie_file_exists: bool,
    pub organizer_summary: Option<Value>,
    pub organizer_outcome: JobOutcome,
    pub can_download_missing: bool,
    pub notice: Option<String>,
}

#[derive(Serialize)]
pub struct ActivityPage {
    pub entries: Vec<LogEntry>,
    pub total: usize,
}

pub struct TrainsApp {
    data_dir: PathBuf,
    launcher: Arc<dyn WorkerLauncher>,
    notifier: WorkerNotifier,
    settings: Settings,
    settings_error: Option<String>,
    job: JobState,
    launching: Option<Receiver<Result<WorkerHandle, crate::worker::WorkerError>>>,
    worker: Option<WorkerHandle>,
    job_kind: Option<JobKind>,
    sequence: u64,
    organizer_summary: Option<Value>,
    organizer_outcome: JobOutcome,
    organizer_destination: String,
    notice: Option<String>,
    current_error: Option<String>,
}

impl TrainsApp {
    pub fn new(data_dir: PathBuf, launcher: Box<dyn WorkerLauncher>) -> Self {
        let loaded = Settings::load(&data_dir);
        Self {
            data_dir,
            launcher: Arc::from(launcher),
            notifier: WorkerNotifier::new(|| {}),
            settings: loaded.settings,
            settings_error: loaded.parse_error,
            job: JobState::default(),
            launching: None,
            worker: None,
            job_kind: None,
            sequence: 0,
            organizer_summary: None,
            organizer_outcome: JobOutcome::Idle,
            organizer_destination: String::new(),
            notice: None,
            current_error: None,
        }
    }
    pub fn set_notifier(&mut self, notifier: WorkerNotifier) {
        self.notifier = notifier;
    }
    pub fn settings(&self) -> &Settings {
        &self.settings
    }
    pub fn active_page(&self) -> AppPage {
        self.settings.selected_page
    }
    pub fn job_state(&self) -> &JobState {
        &self.job
    }
    pub fn can_start_job(&self) -> bool {
        self.job.outcome != JobOutcome::Running && self.launching.is_none() && self.worker.is_none()
    }
    pub fn snapshot(&self) -> Snapshot {
        let mut settings = self.settings.clone();
        settings.extra.clear();
        let job = JobState {
            outcome: self.job.outcome,
            message: self.job.message.clone(),
            done: self.job.done,
            total: self.job.total,
            per_magazine: self.job.per_magazine.clone(),
            summary: self.job.summary.clone(),
            stop_requested: self.job.stop_requested,
            logs: Vec::new(),
            errors: Vec::new(),
        };
        Snapshot {
            settings,
            settings_error: self.settings_error.clone(),
            job,
            busy: !self.can_start_job(),
            log_count: self.job.logs.len(),
            error_count: self.job.errors.len(),
            cookie_file_exists: std::path::Path::new(&self.settings.cookies_path).is_file(),
            organizer_summary: self.organizer_summary.clone(),
            organizer_outcome: self.organizer_outcome,
            can_download_missing: self.can_start_job()
                && self.organizer_destination == self.settings.org_dst
                && self
                    .organizer_summary
                    .as_ref()
                    .is_some_and(|s| requests::can_download_missing(s, self.organizer_outcome)),
            notice: self.notice.clone(),
        }
    }
    pub fn update_settings(&mut self, changes: Value) -> Result<(), String> {
        let changes = changes
            .as_object()
            .ok_or("Settings changes must be an object.")?;
        let allowed = [
            "base_dir",
            "track_plans_dir",
            "cookies_path",
            "headless",
            "test_mode",
            "newest_first",
            "include_specials",
            "selected_magazines",
            "org_src",
            "org_dst",
            "org_prefix",
            "org_headless",
            "selected_page",
            "window_width",
            "window_height",
            "activity_height",
            "activity_collapsed",
            "dark_mode",
        ];
        if changes.keys().any(|key| !allowed.contains(&key.as_str())) {
            return Err("Unknown settings field.".into());
        }
        let mut value =
            serde_json::to_value(&self.settings).map_err(|_| "Settings could not be prepared.")?;
        for (key, value_change) in changes {
            value[key] = value_change.clone();
        }
        let updated: Settings =
            serde_json::from_value(value).map_err(|_| "Settings contain an invalid value.")?;
        if !updated.activity_height.is_finite()
            || !(48.0..=1_000.0).contains(&updated.activity_height)
            || !updated.window_width.is_finite()
            || !updated.window_height.is_finite()
        {
            return Err("Window and Activity sizes must be valid numbers.".into());
        }
        // Preserve the original file and current values if a save fails.
        updated.save(&self.data_dir).map_err(|error| {
            let error = error.to_string();
            self.settings_error = Some(error.clone());
            error
        })?;
        self.settings = updated;
        self.settings_error = None;
        self.notice = None;
        Ok(())
    }
    pub fn start_job(&mut self, kind: JobKind) -> Result<(), String> {
        if !self.can_start_job() {
            return Err("A job is already running. Stop it or wait for it to finish.".into());
        }
        if kind == JobKind::DownloadMissing && self.organizer_destination != self.settings.org_dst {
            return Err(
                "The archive destination changed. Scan it again before downloading missing issues."
                    .into(),
            );
        }
        self.sequence += 1;
        let request = requests::build_request(
            kind,
            &self.settings,
            self.organizer_summary
                .as_ref()
                .map(|s| (s, self.organizer_outcome)),
            format!("job-{}-{}", std::process::id(), self.sequence),
        )?;
        let logs = std::mem::take(&mut self.job.logs);
        let errors = std::mem::take(&mut self.job.errors);
        self.job = JobState {
            outcome: JobOutcome::Running,
            message: "Starting the worker…".into(),
            logs,
            errors,
            ..JobState::default()
        };
        self.job_kind = Some(kind);
        self.notice = None;
        self.current_error = None;
        if kind == JobKind::Organize {
            self.organizer_destination = self.settings.org_dst.clone();
            self.organizer_summary = None;
            self.organizer_outcome = JobOutcome::Running;
        }
        let (sender, receiver) = mpsc::channel();
        let launcher = Arc::clone(&self.launcher);
        let data_dir = self.data_dir.clone();
        let notifier = self.notifier.clone();
        match thread::Builder::new()
            .name("trains-worker-launch".into())
            .spawn(move || {
                let result = launcher.start_with_notify(request, data_dir, notifier.clone());
                let _ = sender.send(result);
                notifier.notify();
            }) {
            Ok(_) => self.launching = Some(receiver),
            Err(_) => self.fail("The worker could not be scheduled to start."),
        }
        Ok(())
    }
    fn fail(&mut self, message: &str) {
        self.apply_worker_event(WorkerEvent::Error {
            message: message.into(),
        });
        self.apply_worker_event(WorkerEvent::Completed {
            outcome: JobOutcome::Failed,
            summary: None,
        });
    }
    pub fn poll_worker(&mut self) -> bool {
        let mut changed = false;
        if let Some(receiver) = self.launching.take() {
            match receiver.try_recv() {
                Ok(Ok(worker)) => {
                    self.worker = Some(worker);
                    changed = true;
                }
                Ok(Err(error)) => {
                    self.fail(&error.to_string());
                    changed = true;
                }
                Err(TryRecvError::Disconnected) => {
                    self.fail("The worker stopped during startup.");
                    changed = true;
                }
                Err(TryRecvError::Empty) => self.launching = Some(receiver),
            }
        }
        let (events, finished) = if let Some(worker) = &mut self.worker {
            if self.job.stop_requested {
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
            changed = true;
        }
        if finished {
            self.worker = None;
            changed = true;
        }
        changed
    }
    pub fn apply_worker_event(&mut self, event: WorkerEvent) {
        match event {
            WorkerEvent::Started => {
                self.job.outcome = JobOutcome::Running;
                if !self.job.stop_requested {
                    self.job.message = "Working…".into();
                }
            }
            WorkerEvent::Log { level, message } => self.add_log(LogEntry { level, message }),
            WorkerEvent::Error { message } => {
                self.job.message.clone_from(&message);
                self.add_log(LogEntry {
                    level: LogLevel::Error,
                    message,
                });
            }
            WorkerEvent::Progress {
                done,
                total,
                message,
                per_magazine,
            } => {
                self.job.outcome = JobOutcome::Running;
                if let Some(done) = done {
                    self.job.done = Some(done);
                }
                if let Some(total) = total {
                    self.job.total = Some(total);
                }
                if let Some(progress) = per_magazine {
                    self.job.per_magazine = progress;
                }
                if let Some(message) = message
                    && !self.job.stop_requested
                {
                    self.job.message = message;
                }
            }
            WorkerEvent::Completed {
                mut outcome,
                summary,
            } => {
                // Exit/protocol failures can follow a terminal message. Retain the findings.
                let summary = summary.or_else(|| self.job.summary.clone());
                if summary
                    .as_ref()
                    .and_then(|s| s.get("scan_complete"))
                    .and_then(Value::as_bool)
                    == Some(false)
                    && outcome == JobOutcome::Success
                {
                    outcome = JobOutcome::Failed;
                }
                if self.job_kind == Some(JobKind::Organize) {
                    self.organizer_summary = summary.clone();
                    self.organizer_outcome = outcome;
                }
                self.job.outcome = outcome;
                self.job.summary = summary;
                self.job.stop_requested = false;
                self.job.message = match outcome {
                    JobOutcome::Success => "Job complete.".into(),
                    JobOutcome::NoResults => "No matching results were found.".into(),
                    JobOutcome::Failed => self.current_error.clone().unwrap_or_else(|| {
                        "The scan did not finish. Review Activity before trying again.".into()
                    }),
                    JobOutcome::Cancelled => {
                        "Stopped safely. Completed files have been kept.".into()
                    }
                    _ => outcome.label().into(),
                };
            }
        }
    }
    fn add_log(&mut self, entry: LogEntry) {
        if entry.level == LogLevel::Error {
            self.current_error = Some(entry.message.clone());
            self.job.errors.push(entry.clone());
        }
        self.job.logs.push(entry);
    }
    pub fn request_stop(&mut self) {
        if self.can_start_job() || self.job.stop_requested {
            return;
        }
        self.job.stop_requested = true;
        self.job.message = "Stopping at the next safe point…".into();
        if let Some(worker) = &mut self.worker {
            let _ = worker.request_cancel();
        }
    }
    pub fn activity(&self, query: &str, offset: usize, limit: usize) -> ActivityPage {
        let query = query.trim().to_lowercase();
        let limit = limit.clamp(1, 200);
        let matching = self
            .job
            .logs
            .iter()
            .rev()
            .filter(|entry| query.is_empty() || entry.message.to_lowercase().contains(&query));
        ActivityPage {
            total: matching.clone().count(),
            entries: matching.skip(offset).take(limit).cloned().collect(),
        }
    }
    pub fn clear_activity(&mut self) {
        self.job.logs.clear();
        self.job.errors.clear();
    }
    pub fn error_text(&self) -> String {
        self.job
            .errors
            .iter()
            .map(|e| e.message.as_str())
            .collect::<Vec<_>>()
            .join("\n")
    }
    pub fn clear_cache(&mut self) -> Result<String, String> {
        if !self.can_start_job() {
            return Err("Wait for the current job to finish before clearing the cache.".into());
        }
        let mut count = 0;
        for name in ["download_progress.json", "special_issues.json"] {
            match fs::remove_file(self.data_dir.join(name)) {
                Ok(()) => count += 1,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return Err(
                    "A cache file could not be removed. Check folder permissions and try again."
                        .into(),
                ),
            }
        }
        let message = if count == 0 {
            "There were no cache files to clear."
        } else {
            "Download cache cleared."
        }
        .to_owned();
        self.notice = Some(message.clone());
        Ok(message)
    }
}
