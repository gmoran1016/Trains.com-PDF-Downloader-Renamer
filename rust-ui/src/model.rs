use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AppPage {
    #[default]
    Magazines,
    TrackPlans,
    Organize,
}

impl AppPage {
    pub const ALL: [Self; 3] = [Self::Magazines, Self::TrackPlans, Self::Organize];

    pub const fn label(self) -> &'static str {
        match self {
            Self::Magazines => "Magazines",
            Self::TrackPlans => "Track Plans",
            Self::Organize => "Organize",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum JobOutcome {
    #[default]
    Idle,
    Running,
    Success,
    NoResults,
    Failed,
    Cancelled,
}

impl JobOutcome {
    pub const ALL: [Self; 6] = [
        Self::Idle,
        Self::Running,
        Self::Success,
        Self::NoResults,
        Self::Failed,
        Self::Cancelled,
    ];

    pub const fn label(self) -> &'static str {
        match self {
            Self::Idle => "Ready",
            Self::Running => "Running",
            Self::Success => "Complete",
            Self::NoResults => "No results",
            Self::Failed => "Failed",
            Self::Cancelled => "Cancelled",
        }
    }
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct MagazineProgress {
    pub done: u64,
    pub total: u64,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LogLevel {
    Debug,
    #[default]
    Info,
    Warning,
    Error,
}

#[derive(Clone, Debug, Default, Eq, PartialEq, Serialize, Deserialize)]
pub struct LogEntry {
    pub level: LogLevel,
    pub message: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct JobState {
    pub outcome: JobOutcome,
    pub message: String,
    pub done: Option<u64>,
    pub total: Option<u64>,
    pub per_magazine: BTreeMap<String, MagazineProgress>,
    pub summary: Option<serde_json::Value>,
    pub logs: Vec<LogEntry>,
    pub errors: Vec<LogEntry>,
    pub stop_requested: bool,
}

impl Default for JobState {
    fn default() -> Self {
        Self {
            outcome: JobOutcome::Idle,
            message: JobOutcome::Idle.label().to_owned(),
            done: None,
            total: None,
            per_magazine: BTreeMap::new(),
            summary: None,
            logs: Vec::new(),
            errors: Vec::new(),
            stop_requested: false,
        }
    }
}
