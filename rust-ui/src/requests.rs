//! Workflow validation and protocol mapping, shared by every desktop surface.
use crate::{
    model::JobOutcome,
    settings::Settings,
    worker::{JobKind, WorkerRequest},
};
use serde_json::{Value, json};

pub const PUBLICATIONS: [&str; 5] = [
    "Model Railroader",
    "Trains Magazine",
    "Classic Toy Trains",
    "Classic Trains",
    "Garden Railways",
];
const PREFIXES: [(&str, &str); 5] = [
    ("MRR", "https://www.trains.com/mrr/magazine/"),
    ("TRN", "https://www.trains.com/trn/magazine/"),
    ("CTT", "https://www.trains.com/ctt/magazine/"),
    ("CTR", "https://www.trains.com/ctr/magazine/"),
    ("GRW", "https://www.trains.com/grw/magazine/"),
];

pub fn can_download_missing(summary: &Value, outcome: JobOutcome) -> bool {
    outcome == JobOutcome::Success
        && summary.get("scan_complete").and_then(Value::as_bool) == Some(true)
        && missing_target(summary).is_some()
}

fn missing_target(summary: &Value) -> Option<(&'static str, &'static str, Value)> {
    let map = summary.get("missing_by_prefix_year")?.as_object()?;
    if map.len() != 1 {
        return None;
    }
    let (prefix, years) = map.iter().next()?;
    let (prefix, url) = PREFIXES.iter().find(|(known, _)| *known == prefix)?;
    let missing = years
        .as_object()?
        .iter()
        .filter(|(_, months)| months.as_array().is_some_and(|months| !months.is_empty()))
        .map(|(year, months)| (year.clone(), months.clone()))
        .collect::<serde_json::Map<_, _>>();
    if missing.is_empty() {
        return None;
    }
    Some((*prefix, *url, Value::Object(missing)))
}

pub fn build_request(
    kind: JobKind,
    settings: &Settings,
    organizer: Option<(&Value, JobOutcome)>,
    job_id: String,
) -> Result<WorkerRequest, String> {
    let options = match kind {
        JobKind::Magazines => {
            if settings.base_dir.trim().is_empty() {
                return Err("Choose a magazine destination folder.".into());
            }
            if settings.selected_magazines.is_empty()
                || settings
                    .selected_magazines
                    .iter()
                    .any(|name| !PUBLICATIONS.contains(&name.as_str()))
            {
                return Err("Select at least one supported publication.".into());
            }
            json!({"base_dir":settings.base_dir,"magazines":settings.selected_magazines,"headless":settings.headless,"test_mode":settings.test_mode,"cookies_path":settings.cookies_path,"newest_first":settings.newest_first,"include_specials":settings.include_specials})
        }
        JobKind::TrackPlans => {
            if settings.track_plans_dir.trim().is_empty() {
                return Err("Choose a track-plan destination folder.".into());
            }
            json!({"destination_dir":settings.track_plans_dir,"cookies_path":settings.cookies_path})
        }
        JobKind::Organize => {
            if settings.org_src.trim().is_empty() {
                return Err("Choose the source folder containing PDFs.".into());
            }
            if settings.org_dst.trim().is_empty() {
                return Err("Choose an archive destination folder.".into());
            }
            let hint = settings.org_prefix.trim();
            if !hint.is_empty()
                && hint != "Auto-detect"
                && !PREFIXES.iter().any(|(prefix, _)| *prefix == hint)
            {
                return Err("Choose Auto-detect or a supported magazine prefix.".into());
            }
            json!({"source_dir":settings.org_src,"destination_dir":settings.org_dst,"hint_prefix":if hint.is_empty() || hint == "Auto-detect" { Value::Null } else { json!(hint) }})
        }
        JobKind::DownloadMissing => {
            let (summary, outcome) =
                organizer.ok_or("Run an organizer scan before downloading missing issues.")?;
            if !can_download_missing(summary, outcome) {
                return Err("Download Missing requires a complete, successful scan of one supported publication.".into());
            }
            if settings.org_dst.trim().is_empty() {
                return Err("Choose an archive destination folder.".into());
            }
            let (prefix, url, years) =
                missing_target(summary).ok_or("The missing-issue target is ambiguous.")?;
            json!({"prefix":prefix,"archive_url":url,"missing_by_year":years,"destination_dir":settings.org_dst,"cookies_path":settings.cookies_path,"headless":settings.org_headless})
        }
    };
    Ok(WorkerRequest {
        job_id,
        job_kind: kind,
        options,
    })
}
