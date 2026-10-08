//! Versioned JSON-lines client for the isolated Python job worker.

use std::{
    collections::BTreeMap,
    error::Error,
    ffi::OsString,
    fmt, fs,
    io::{self, BufRead, BufReader, Read, Write},
    path::PathBuf,
    process::{Child, Command, ExitStatus, Stdio},
    sync::mpsc::{self, Receiver, Sender, TryRecvError},
    thread,
};

#[cfg(feature = "desktop-smoke")]
use std::time::Duration;

use serde::{
    Deserialize, Serialize,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Map, Number, Value};

use crate::model::{JobOutcome, LogLevel, MagazineProgress};
use crate::worker_bundle::{EMBEDDED_WORKER, ExtractedWorker, WorkerBundleError, extract_worker};

pub const PROTOCOL_VERSION: u64 = 1;
const MAX_PROTOCOL_LINE_BYTES: usize = 1024 * 1024;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum JobKind {
    Magazines,
    TrackPlans,
    Organize,
    DownloadMissing,
}

#[derive(Clone, Debug, PartialEq)]
pub struct WorkerRequest {
    pub job_id: String,
    pub job_kind: JobKind,
    pub options: Value,
}

#[derive(Clone, Debug, PartialEq)]
pub enum WorkerEvent {
    Started,
    Log {
        level: LogLevel,
        message: String,
    },
    Progress {
        done: Option<u64>,
        total: Option<u64>,
        message: Option<String>,
        per_magazine: Option<BTreeMap<String, MagazineProgress>>,
    },
    Error {
        message: String,
    },
    Completed {
        outcome: JobOutcome,
        summary: Option<Value>,
    },
}

pub trait WorkerLauncher: Send + Sync {
    fn start(
        &self,
        _request: WorkerRequest,
        _data_dir: PathBuf,
    ) -> Result<WorkerHandle, WorkerError> {
        Err(WorkerError::Unavailable)
    }
}

pub struct UnavailableWorker;

impl WorkerLauncher for UnavailableWorker {}

#[derive(Clone, Debug)]
pub struct CommandWorkerLauncher {
    program: PathBuf,
    args: Vec<OsString>,
}

impl CommandWorkerLauncher {
    pub fn new<I, S>(program: impl Into<PathBuf>, args: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: Into<OsString>,
    {
        Self {
            program: program.into(),
            args: args.into_iter().map(Into::into).collect(),
        }
    }
}

impl WorkerLauncher for CommandWorkerLauncher {
    fn start(
        &self,
        request: WorkerRequest,
        data_dir: PathBuf,
    ) -> Result<WorkerHandle, WorkerError> {
        if request.job_id.trim().is_empty() {
            return Err(WorkerError::InvalidRequest);
        }
        if !request.options.is_object() {
            return Err(WorkerError::InvalidRequest);
        }

        let start_record = serde_json::to_vec(&StartCommand {
            v: PROTOCOL_VERSION,
            job_id: &request.job_id,
            command: "start",
            job_kind: request.job_kind,
            options: &request.options,
        })
        .map_err(WorkerError::Serialize)?;

        fs::create_dir_all(&data_dir).map_err(WorkerError::CreateDataDirectory)?;
        let mut command = Command::new(&self.program);
        command
            .args(&self.args)
            .env("TRAINS_DATA_DIR", data_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        configure_hidden_windows_process(&mut command);
        let mut child = command.spawn().map_err(WorkerError::Spawn)?;
        let stdin = child.stdin.take().ok_or(WorkerError::MissingPipe)?;
        let stdout = child.stdout.take().ok_or(WorkerError::MissingPipe)?;
        let stderr = child.stderr.take().ok_or(WorkerError::MissingPipe)?;

        let (output_tx, output_rx) = mpsc::channel();
        let (writer_tx, writer_rx) = mpsc::channel();
        let job_id = request.job_id.clone();

        let writer_output = output_tx.clone();
        thread::Builder::new()
            .name("trains-worker-stdin".to_owned())
            .spawn(move || write_worker_input(stdin, start_record, writer_rx, writer_output))
            .map_err(WorkerError::Thread)?;

        let reader_output = output_tx.clone();
        thread::Builder::new()
            .name("trains-worker-stdout".to_owned())
            .spawn(move || read_worker_output(stdout, job_id, reader_output))
            .map_err(WorkerError::Thread)?;

        thread::Builder::new()
            .name("trains-worker-stderr".to_owned())
            .spawn(move || drain_worker_stderr(stderr))
            .map_err(WorkerError::Thread)?;

        Ok(WorkerHandle {
            child: Some(child),
            _bundle_guard: None,
            job_id: request.job_id,
            output_rx,
            cancel: CancelControl::Process(Some(writer_tx)),
            cancel_requested: false,
            exit_status: None,
            completed_seen: false,
            failure_emitted: false,
            stdout_closed: false,
        })
    }
}

/// Launches the Python worker executable embedded in the Rust application.
#[derive(Clone, Debug)]
pub struct EmbeddedWorkerLauncher {
    temp_root: PathBuf,
}

impl Default for EmbeddedWorkerLauncher {
    fn default() -> Self {
        Self {
            temp_root: std::env::temp_dir(),
        }
    }
}

impl EmbeddedWorkerLauncher {
    pub fn with_temp_root(temp_root: impl Into<PathBuf>) -> Self {
        Self {
            temp_root: temp_root.into(),
        }
    }
}

impl WorkerLauncher for EmbeddedWorkerLauncher {
    fn start(
        &self,
        request: WorkerRequest,
        data_dir: PathBuf,
    ) -> Result<WorkerHandle, WorkerError> {
        let extracted = extract_worker(EMBEDDED_WORKER, &self.temp_root, env!("CARGO_PKG_VERSION"))
            .map_err(WorkerError::Bundle)?;
        let launcher = CommandWorkerLauncher::new(extracted.path(), [OsString::from("--stdio")]);
        let mut handle = launcher.start(request, data_dir)?;
        handle._bundle_guard = Some(extracted);
        Ok(handle)
    }
}

#[derive(Serialize)]
struct StartCommand<'a> {
    v: u64,
    job_id: &'a str,
    command: &'static str,
    job_kind: JobKind,
    options: &'a Value,
}

enum CancelControl {
    Process(Option<Sender<WriterCommand>>),
    #[cfg(feature = "desktop-smoke")]
    Fake(Option<Sender<()>>),
}

enum WriterCommand {
    Cancel(Vec<u8>),
}

enum ReaderMessage {
    Event(WorkerEvent),
    ProtocolFailure,
    OutputFailure,
    WriterFailure,
    StdoutClosed,
}

pub struct WorkerHandle {
    child: Option<Child>,
    _bundle_guard: Option<ExtractedWorker>,
    job_id: String,
    output_rx: Receiver<ReaderMessage>,
    cancel: CancelControl,
    cancel_requested: bool,
    exit_status: Option<ExitStatus>,
    completed_seen: bool,
    failure_emitted: bool,
    stdout_closed: bool,
}

impl WorkerHandle {
    /// Whether a terminal event has been observed and the process is safe to release.
    pub fn is_finished(&self) -> bool {
        self.completed_seen
            && self.stdout_closed
            && (self.child.is_none() || self.exit_status.is_some())
    }

    pub fn try_recv(&mut self) -> Vec<WorkerEvent> {
        let mut events = Vec::new();
        loop {
            match self.output_rx.try_recv() {
                Ok(ReaderMessage::Event(event)) => {
                    if matches!(event, WorkerEvent::Completed { .. }) {
                        self.completed_seen = true;
                    }
                    events.push(event);
                }
                Ok(ReaderMessage::ProtocolFailure) => {
                    self.stdout_closed = true;
                    self.fail(
                        &mut events,
                        "The worker returned an invalid response. Check the app version and try again.",
                    );
                }
                Ok(ReaderMessage::OutputFailure) => {
                    self.stdout_closed = true;
                    self.fail(&mut events, "The worker output could not be read.")
                }
                Ok(ReaderMessage::WriterFailure) => {
                    self.fail(&mut events, "The worker could not receive the job request.")
                }
                Ok(ReaderMessage::StdoutClosed) => {
                    self.stdout_closed = true;
                    if !self.completed_seen {
                        self.fail(
                            &mut events,
                            "The worker stopped before reporting completion.",
                        );
                    }
                }
                Err(TryRecvError::Empty) => break,
                Err(TryRecvError::Disconnected) => {
                    if !self.completed_seen && !self.stdout_closed {
                        self.fail(
                            &mut events,
                            "The worker stopped before reporting completion.",
                        );
                    }
                    break;
                }
            }
        }
        if self.exit_status.is_some_and(|status| !status.success()) {
            self.fail(&mut events, "The Python worker exited with an error.");
        }
        events
    }

    pub fn request_cancel(&mut self) -> Result<(), WorkerError> {
        if self.cancel_requested {
            return Ok(());
        }
        let result = match &self.cancel {
            CancelControl::Process(Some(sender)) => {
                let Some(child) = self.child.as_mut() else {
                    return Err(WorkerError::AlreadyExited);
                };
                if child.try_wait().map_err(WorkerError::Wait)?.is_some() {
                    return Err(WorkerError::AlreadyExited);
                }
                let record = serde_json::to_vec(&CancelCommand {
                    v: PROTOCOL_VERSION,
                    job_id: &self.job_id,
                    command: "cancel",
                })
                .map_err(WorkerError::Serialize)?;
                sender
                    .send(WriterCommand::Cancel(record))
                    .map_err(|_| WorkerError::InputClosed)
            }
            CancelControl::Process(None) => return Err(WorkerError::AlreadyExited),
            #[cfg(feature = "desktop-smoke")]
            CancelControl::Fake(Some(sender)) => {
                sender.send(()).map_err(|_| WorkerError::InputClosed)
            }
            #[cfg(feature = "desktop-smoke")]
            CancelControl::Fake(None) => return Err(WorkerError::AlreadyExited),
        };
        result?;
        self.cancel_requested = true;
        Ok(())
    }

    pub fn poll_exit(&mut self) -> Option<ExitStatus> {
        if let Some(status) = &self.exit_status {
            return Some(*status);
        }
        let status = self.child.as_mut()?.try_wait().ok().flatten()?;
        self.exit_status = Some(status);
        self.close_cancel_sender();
        Some(status)
    }

    fn close_cancel_sender(&mut self) {
        match &mut self.cancel {
            CancelControl::Process(sender) => *sender = None,
            #[cfg(feature = "desktop-smoke")]
            CancelControl::Fake(sender) => *sender = None,
        }
    }

    fn fail(&mut self, events: &mut Vec<WorkerEvent>, message: &str) {
        if self.failure_emitted {
            return;
        }
        self.failure_emitted = true;
        self.completed_seen = true;
        events.push(WorkerEvent::Error {
            message: message.to_owned(),
        });
        events.push(WorkerEvent::Completed {
            outcome: JobOutcome::Failed,
            summary: None,
        });
        if let Some(child) = self.child.as_mut()
            && child.try_wait().ok().flatten().is_none()
        {
            let _ = child.kill();
        }
        self.close_cancel_sender();
    }
}

impl Drop for WorkerHandle {
    fn drop(&mut self) {
        if let Some(child) = self.child.as_mut()
            && child.try_wait().ok().flatten().is_none()
        {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn write_worker_input(
    mut stdin: impl Write,
    start_record: Vec<u8>,
    commands: Receiver<WriterCommand>,
    output: Sender<ReaderMessage>,
) {
    if write_record(&mut stdin, &start_record).is_err() {
        let _ = output.send(ReaderMessage::WriterFailure);
        return;
    }
    while let Ok(WriterCommand::Cancel(record)) = commands.recv() {
        if write_record(&mut stdin, &record).is_err() {
            let _ = output.send(ReaderMessage::WriterFailure);
            return;
        }
    }
}

fn write_record(writer: &mut impl Write, record: &[u8]) -> io::Result<()> {
    writer.write_all(record)?;
    writer.write_all(b"\n")?;
    writer.flush()
}

fn read_worker_output(stdout: impl Read, expected_job_id: String, output: Sender<ReaderMessage>) {
    let mut reader = BufReader::new(stdout);
    let mut completed_seen = false;
    loop {
        let line = match read_bounded_line(&mut reader) {
            Ok(Some(line)) => line,
            Ok(None) => {
                let _ = output.send(ReaderMessage::StdoutClosed);
                return;
            }
            Err(_) => {
                let _ = output.send(ReaderMessage::OutputFailure);
                return;
            }
        };
        if completed_seen {
            let _ = output.send(ReaderMessage::ProtocolFailure);
            return;
        }
        let line = match std::str::from_utf8(&line) {
            Ok(line) => line,
            Err(_) => {
                let _ = output.send(ReaderMessage::ProtocolFailure);
                return;
            }
        };
        match decode_event(line, &expected_job_id) {
            Ok(event) => {
                if matches!(event, WorkerEvent::Completed { .. }) {
                    completed_seen = true;
                }
                if output.send(ReaderMessage::Event(event)).is_err() {
                    return;
                }
            }
            Err(()) => {
                let _ = output.send(ReaderMessage::ProtocolFailure);
                return;
            }
        }
    }
}

fn read_bounded_line(reader: &mut impl BufRead) -> io::Result<Option<Vec<u8>>> {
    let mut line = Vec::new();
    loop {
        let available = reader.fill_buf()?;
        if available.is_empty() {
            return if line.is_empty() {
                Ok(None)
            } else {
                Ok(Some(line))
            };
        }
        let newline = available.iter().position(|byte| *byte == b'\n');
        let amount = newline.map_or(available.len(), |index| index + 1);
        if line.len() + amount > MAX_PROTOCOL_LINE_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "worker protocol line exceeds size limit",
            ));
        }
        line.extend_from_slice(&available[..amount]);
        reader.consume(amount);
        if newline.is_some() {
            if line.last() == Some(&b'\n') {
                line.pop();
            }
            if line.last() == Some(&b'\r') {
                line.pop();
            }
            return Ok(Some(line));
        }
    }
}

fn drain_worker_stderr(stderr: impl Read) {
    let mut reader = BufReader::new(stderr);
    let mut buffer = [0_u8; 8192];
    loop {
        match reader.read(&mut buffer) {
            Ok(0) | Err(_) => return,
            Ok(_) => {}
        }
    }
}

fn decode_event(line: &str, expected_job_id: &str) -> Result<WorkerEvent, ()> {
    let mut deserializer = serde_json::Deserializer::from_str(line);
    let StrictValue(value) = StrictValue::deserialize(&mut deserializer).map_err(|_| ())?;
    deserializer.end().map_err(|_| ())?;
    let record = value.as_object().ok_or(())?;
    let version = record.get("v").and_then(Value::as_u64).ok_or(())?;
    if version != PROTOCOL_VERSION {
        return Err(());
    }
    let job_id = record.get("job_id").and_then(Value::as_str).ok_or(())?;
    if job_id.trim().is_empty() || job_id != expected_job_id {
        return Err(());
    }
    let event = record.get("event").and_then(Value::as_str).ok_or(())?;
    let mut payload = record.clone();
    for key in ["v", "job_id", "event"] {
        payload.remove(key);
    }

    match event {
        "started" if payload.is_empty() => Ok(WorkerEvent::Started),
        "log" if has_exact_keys(&payload, &["level", "message"]) => {
            let level = match payload.get("level").and_then(Value::as_str).ok_or(())? {
                "debug" => LogLevel::Debug,
                "info" => LogLevel::Info,
                "warning" => LogLevel::Warning,
                "error" => LogLevel::Error,
                _ => return Err(()),
            };
            let message = payload.get("message").and_then(Value::as_str).ok_or(())?;
            Ok(WorkerEvent::Log {
                level,
                message: message.to_owned(),
            })
        }
        "progress" => decode_progress(&payload),
        "error" if has_exact_keys(&payload, &["message"]) => {
            let message = payload.get("message").and_then(Value::as_str).ok_or(())?;
            Ok(WorkerEvent::Error {
                message: message.to_owned(),
            })
        }
        "completed" if has_required_and_optional_keys(&payload, &["outcome"], &["summary"]) => {
            let outcome = match payload.get("outcome").and_then(Value::as_str).ok_or(())? {
                "success" => JobOutcome::Success,
                "no-results" => JobOutcome::NoResults,
                "failed" => JobOutcome::Failed,
                "cancelled" => JobOutcome::Cancelled,
                _ => return Err(()),
            };
            let summary = payload.get("summary").cloned();
            if summary.as_ref().is_some_and(|value| !value.is_object()) {
                return Err(());
            }
            Ok(WorkerEvent::Completed { outcome, summary })
        }
        _ => Err(()),
    }
}

fn decode_progress(payload: &Map<String, Value>) -> Result<WorkerEvent, ()> {
    if payload.is_empty()
        || !has_required_and_optional_keys(
            payload,
            &[],
            &["done", "total", "message", "per_magazine"],
        )
    {
        return Err(());
    }
    let has_done = payload.contains_key("done");
    let has_total = payload.contains_key("total");
    if has_done != has_total {
        return Err(());
    }
    let done = payload
        .get("done")
        .map(as_nonnegative_integer)
        .transpose()?;
    let total = payload
        .get("total")
        .map(as_nonnegative_integer)
        .transpose()?;
    let message = payload
        .get("message")
        .map(|value| value.as_str().map(str::to_owned).ok_or(()))
        .transpose()?;
    let per_magazine = if let Some(progress) = payload.get("per_magazine") {
        let entries = progress.as_object().ok_or(())?;
        let mut decoded = BTreeMap::new();
        for (name, values) in entries {
            if name.trim().is_empty() {
                return Err(());
            }
            let values = values.as_object().ok_or(())?;
            if !has_exact_keys(values, &["done", "total"]) {
                return Err(());
            }
            decoded.insert(
                name.clone(),
                MagazineProgress {
                    done: as_nonnegative_integer(values.get("done").ok_or(())?)?,
                    total: as_nonnegative_integer(values.get("total").ok_or(())?)?,
                },
            );
        }
        Some(decoded)
    } else {
        None
    };
    Ok(WorkerEvent::Progress {
        done,
        total,
        message,
        per_magazine,
    })
}

fn as_nonnegative_integer(value: &Value) -> Result<u64, ()> {
    value.as_u64().ok_or(())
}

fn has_exact_keys(map: &Map<String, Value>, keys: &[&str]) -> bool {
    map.len() == keys.len() && keys.iter().all(|key| map.contains_key(*key))
}

fn has_required_and_optional_keys(
    map: &Map<String, Value>,
    required: &[&str],
    optional: &[&str],
) -> bool {
    required.iter().all(|key| map.contains_key(*key))
        && map
            .keys()
            .all(|key| required.contains(&key.as_str()) || optional.contains(&key.as_str()))
}

struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: serde::Deserializer<'de>,
    {
        struct StrictValueVisitor;

        impl<'de> Visitor<'de> for StrictValueVisitor {
            type Value = StrictValue;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a JSON value without duplicate object keys")
            }

            fn visit_bool<E>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Bool(value)))
            }

            fn visit_i64<E>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Number(Number::from(value))))
            }

            fn visit_u64<E>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Number(Number::from(value))))
            }

            fn visit_f64<E>(self, value: f64) -> Result<Self::Value, E>
            where
                E: de::Error,
            {
                Number::from_f64(value)
                    .map(Value::Number)
                    .map(StrictValue)
                    .ok_or_else(|| E::custom("invalid JSON number"))
            }

            fn visit_str<E>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value.to_owned())))
            }

            fn visit_string<E>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value)))
            }

            fn visit_none<E>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }

            fn visit_unit<E>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }

            fn visit_seq<A>(self, mut sequence: A) -> Result<Self::Value, A::Error>
            where
                A: SeqAccess<'de>,
            {
                let mut values = Vec::new();
                while let Some(value) = sequence.next_element::<StrictValue>()? {
                    values.push(value.0);
                }
                Ok(StrictValue(Value::Array(values)))
            }

            fn visit_map<A>(self, mut object: A) -> Result<Self::Value, A::Error>
            where
                A: MapAccess<'de>,
            {
                let mut values = Map::new();
                while let Some((key, value)) = object.next_entry::<String, StrictValue>()? {
                    if values.contains_key(&key) {
                        return Err(de::Error::custom("duplicate JSON object key"));
                    }
                    values.insert(key, value.0);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }

        deserializer.deserialize_any(StrictValueVisitor)
    }
}

#[derive(Serialize)]
struct CancelCommand<'a> {
    v: u64,
    job_id: &'a str,
    command: &'static str,
}

#[derive(Debug)]
pub enum WorkerError {
    Unavailable,
    InvalidRequest,
    Bundle(WorkerBundleError),
    Serialize(serde_json::Error),
    CreateDataDirectory(io::Error),
    Spawn(io::Error),
    MissingPipe,
    Thread(io::Error),
    Wait(io::Error),
    AlreadyExited,
    InputClosed,
}

impl fmt::Display for WorkerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Unavailable => formatter.write_str("the Python worker is not configured"),
            Self::InvalidRequest => formatter.write_str("the job request is invalid"),
            Self::Bundle(error) => error.fmt(formatter),
            Self::Serialize(_) => formatter.write_str("the job request could not be encoded"),
            Self::CreateDataDirectory(_) => {
                formatter.write_str("the app data folder could not be prepared")
            }
            Self::Spawn(_) => formatter.write_str("the Python worker could not be started"),
            Self::MissingPipe => formatter.write_str("the Python worker pipes could not be opened"),
            Self::Thread(_) => formatter.write_str("the Python worker I/O could not be started"),
            Self::Wait(_) => formatter.write_str("the Python worker status could not be read"),
            Self::AlreadyExited => formatter.write_str("the Python worker has already exited"),
            Self::InputClosed => formatter.write_str("the Python worker input is closed"),
        }
    }
}

impl Error for WorkerError {}

fn configure_hidden_windows_process(command: &mut Command) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = command;
}

#[cfg(feature = "desktop-smoke")]
pub struct FakeWorkerLauncher;

#[cfg(feature = "desktop-smoke")]
impl WorkerLauncher for FakeWorkerLauncher {
    fn start(
        &self,
        request: WorkerRequest,
        _data_dir: PathBuf,
    ) -> Result<WorkerHandle, WorkerError> {
        let (output_tx, output_rx) = mpsc::channel();
        let (cancel_tx, cancel_rx) = mpsc::channel();
        let job_kind = request.job_kind;
        let desired_outcome = match std::env::var("TRAINS_UI_SMOKE_OUTCOME").as_deref() {
            Ok("no-results") => JobOutcome::NoResults,
            Ok("failed") => JobOutcome::Failed,
            Ok("cancelled") => JobOutcome::Cancelled,
            _ => JobOutcome::Success,
        };
        thread::Builder::new()
            .name("trains-smoke-worker".to_owned())
            .spawn(move || {
                let _ = output_tx.send(ReaderMessage::Event(WorkerEvent::Started));
                for done in 1..=4 {
                    if cancel_rx.recv_timeout(Duration::from_millis(350)).is_ok() {
                        let _ = output_tx.send(ReaderMessage::Event(WorkerEvent::Completed {
                            outcome: JobOutcome::Cancelled,
                            summary: organize_summary(job_kind, false),
                        }));
                        let _ = output_tx.send(ReaderMessage::StdoutClosed);
                        return;
                    }
                    let _ = output_tx.send(ReaderMessage::Event(WorkerEvent::Progress {
                        done: Some(done),
                        total: Some(4),
                        message: Some(format!("Preparing sample issue {done} of 4 · about 1 sec")),
                        per_magazine: None,
                    }));
                }
                if desired_outcome == JobOutcome::Failed {
                    let _ = output_tx.send(ReaderMessage::Event(WorkerEvent::Error {
                        message: "Sample worker failure for desktop verification.".to_owned(),
                    }));
                }
                let _ = output_tx.send(ReaderMessage::Event(WorkerEvent::Completed {
                    outcome: desired_outcome,
                    summary: organize_summary(job_kind, desired_outcome == JobOutcome::Success),
                }));
                let _ = output_tx.send(ReaderMessage::StdoutClosed);
            })
            .map_err(WorkerError::Thread)?;
        Ok(WorkerHandle {
            child: None,
            _bundle_guard: None,
            job_id: "desktop-smoke".to_owned(),
            output_rx,
            cancel: CancelControl::Fake(Some(cancel_tx)),
            cancel_requested: false,
            exit_status: None,
            completed_seen: false,
            failure_emitted: false,
            stdout_closed: false,
        })
    }
}

#[cfg(feature = "desktop-smoke")]
fn organize_summary(job_kind: JobKind, scan_complete: bool) -> Option<Value> {
    (job_kind == JobKind::Organize).then(|| {
        serde_json::json!({
            "moved": 7,
            "already_correct": 2,
            "unrecognized": 1,
            "corrupt": 0,
            "conflicts": 1,
            "metadata_stamped": 4,
            "report": ["MRR 2024: missing March", "TRN 2025: complete"],
            "missing_by_prefix_year": {"MRR": {"2024": ["March"]}},
            "scan_complete": scan_complete
        })
    })
}

#[cfg(test)]
mod tests {
    use super::{CancelControl, WorkerEvent, WorkerHandle, decode_event};
    use crate::model::MagazineProgress;
    use std::collections::BTreeMap;

    #[test]
    fn completed_worker_is_not_finished_until_stdout_closes() {
        let (_sender, output_rx) = std::sync::mpsc::channel();
        let mut handle = WorkerHandle {
            child: None,
            _bundle_guard: None,
            job_id: "stdout-close-check".to_owned(),
            output_rx,
            cancel: CancelControl::Process(None),
            cancel_requested: false,
            exit_status: None,
            completed_seen: true,
            failure_emitted: false,
            stdout_closed: false,
        };

        assert!(!handle.is_finished());

        handle.stdout_closed = true;
        assert!(handle.is_finished());
    }

    #[test]
    fn protocol_rejects_duplicate_keys_and_unknown_fields() {
        assert!(
            decode_event(
                r#"{"v":1,"v":1,"job_id":"job-1","event":"started"}"#,
                "job-1"
            )
            .is_err()
        );
        assert!(
            decode_event(
                r#"{"v":1,"job_id":"job-1","event":"started","extra":true}"#,
                "job-1"
            )
            .is_err()
        );
    }

    #[test]
    fn protocol_decodes_progress_without_synthesizing_eta() {
        let event = decode_event(
            r#"{"v":1,"job_id":"job-1","event":"progress","done":2,"total":5,"message":"2 / 5 issues · 00:12","per_magazine":{"Model Railroader":{"done":2,"total":4}}}"#,
            "job-1",
        )
        .expect("valid progress event");
        let mut per_magazine = BTreeMap::new();
        per_magazine.insert(
            "Model Railroader".to_owned(),
            MagazineProgress { done: 2, total: 4 },
        );
        assert_eq!(
            event,
            WorkerEvent::Progress {
                done: Some(2),
                total: Some(5),
                message: Some("2 / 5 issues · 00:12".to_owned()),
                per_magazine: Some(per_magazine),
            }
        );
    }

    #[test]
    fn protocol_distinguishes_missing_and_empty_magazine_progress() {
        let absent = decode_event(
            r#"{"v":1,"job_id":"job-1","event":"progress","message":"Searching"}"#,
            "job-1",
        )
        .expect("status-only progress");
        let empty = decode_event(
            r#"{"v":1,"job_id":"job-1","event":"progress","per_magazine":{}}"#,
            "job-1",
        )
        .expect("explicit empty magazine progress");
        assert!(matches!(
            absent,
            WorkerEvent::Progress {
                per_magazine: None,
                ..
            }
        ));
        assert!(
            matches!(empty, WorkerEvent::Progress { per_magazine: Some(map), .. } if map.is_empty())
        );
    }
}
