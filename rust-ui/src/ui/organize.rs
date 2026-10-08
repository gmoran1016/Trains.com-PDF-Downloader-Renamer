use std::path::PathBuf;

use eframe::egui::{self, Button, Frame, RichText, Stroke};
use serde_json::{Value, json};

use crate::{
    app::TrainsApp,
    model::JobOutcome,
    settings::Settings,
    theme,
    worker::{JobKind, WorkerRequest},
};

const PREFIXES: [(&str, &str); 5] = [
    ("MRR", "https://www.trains.com/mrr/magazine/"),
    ("TRN", "https://www.trains.com/trn/magazine/"),
    ("CTT", "https://www.trains.com/ctt/magazine/"),
    ("CTR", "https://www.trains.com/ctr/magazine/"),
    ("GRW", "https://www.trains.com/grw/magazine/"),
];

pub fn build_organize_request(settings: &Settings, job_id: String) -> WorkerRequest {
    let hint = settings.org_prefix.trim();
    WorkerRequest {
        job_id,
        job_kind: JobKind::Organize,
        options: json!({
            "source_dir": settings.org_src,
            "destination_dir": settings.org_dst,
            "hint_prefix": if hint.is_empty() || hint == "Auto-detect" { Value::Null } else { Value::String(hint.to_owned()) },
        }),
    }
}

pub fn can_download_missing(summary: &Value, outcome: JobOutcome) -> bool {
    if outcome != JobOutcome::Success
        || summary.get("scan_complete").and_then(Value::as_bool) != Some(true)
    {
        return false;
    }
    selected_missing_target(summary).is_some()
}

pub fn build_missing_request(
    summary: &Value,
    outcome: JobOutcome,
    settings: &Settings,
    job_id: String,
) -> Option<WorkerRequest> {
    if !can_download_missing(summary, outcome) || settings.org_dst.trim().is_empty() {
        return None;
    }
    let (prefix, archive_url, by_year) = selected_missing_target(summary)?;
    Some(WorkerRequest {
        job_id,
        job_kind: JobKind::DownloadMissing,
        options: json!({
            "prefix": prefix,
            "archive_url": archive_url,
            "missing_by_year": by_year,
            "destination_dir": settings.org_dst,
            "cookies_path": settings.cookies_path,
            "headless": settings.org_headless,
        }),
    })
}

fn selected_missing_target(summary: &Value) -> Option<(&'static str, &'static str, Value)> {
    let map = summary.get("missing_by_prefix_year")?.as_object()?;
    if map.len() != 1 {
        return None;
    }
    let (prefix, years) = map.iter().next()?;
    let (known_prefix, archive_url) = PREFIXES.iter().find(|(known, _)| *known == prefix)?;
    let years = years.as_object()?;
    let missing = years
        .iter()
        .filter(|(_, months)| months.as_array().is_some_and(|months| !months.is_empty()))
        .map(|(year, months)| (year.clone(), months.clone()))
        .collect::<serde_json::Map<_, _>>();
    if missing.is_empty() {
        return None;
    }
    Some((*known_prefix, *archive_url, Value::Object(missing)))
}

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui) {
    ui.add_space(20.0);
    ui.heading(RichText::new("PDF organizer").size(28.0));
    ui.label("Sort PDFs into the archive, review coverage, and find missing issues.");
    ui.add_space(14.0);

    Frame::group(ui.style())
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::same(16))
        .show(ui, |ui| {
            ui.label(RichText::new("Folders").strong().color(theme::NAVY));
            ui.add_space(8.0);
            folder_setting(app, ui, "Source folder", true);
            ui.add_space(6.0);
            folder_setting(app, ui, "Archive destination", false);
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                ui.label("Magazine prefix");
                egui::ComboBox::from_id_salt("organizer_prefix")
                    .selected_text(app.settings().org_prefix.as_str())
                    .show_ui(ui, |ui| {
                        for prefix in ["Auto-detect", "MRR", "TRN", "CTT", "CTR", "GRW"] {
                            if ui
                                .selectable_label(app.settings().org_prefix == prefix, prefix)
                                .clicked()
                            {
                                app.settings_mut().org_prefix = prefix.to_owned();
                                app.save_settings_notice();
                            }
                        }
                    });
                ui.label(
                    RichText::new("Use Auto-detect unless filenames need a hint.")
                        .small()
                        .color(theme::MUTED),
                );
            });
        });

    ui.add_space(12.0);
    show_summary(app, ui);
}

pub(crate) fn show_action(app: &mut TrainsApp, ui: &mut egui::Ui) {
    let ready = !app.settings().org_src.trim().is_empty()
        && !app.settings().org_dst.trim().is_empty()
        && app.can_start_job();
    let button = Button::new(
        RichText::new("Organize PDFs")
            .strong()
            .color(theme::PRIMARY_ACTION_TEXT),
    )
    .fill(theme::NAVY)
    .stroke(Stroke::NONE)
    .min_size(egui::vec2(190.0, 42.0));
    let missing_available = app
        .job_state()
        .summary
        .as_ref()
        .is_some_and(|summary| can_download_missing(summary, app.job_state().outcome));
    let mut start_organize = false;
    let mut download_missing = false;
    ui.horizontal(|ui| {
        start_organize = ui.add_enabled(ready, button).clicked();

        if missing_available {
            let button = Button::new(RichText::new("Download Missing").strong())
                .fill(theme::INDEX_YELLOW)
                .stroke(Stroke::NONE)
                .min_size(egui::vec2(178.0, 42.0));
            download_missing = ui.add_enabled(app.can_start_job(), button).clicked();
        }
    });
    if start_organize {
        app.queue_organize();
    } else if download_missing {
        app.queue_missing_download();
    }
    if let Some(notice) = app.notice() {
        ui.add_space(4.0);
        ui.label(RichText::new(notice).small().color(theme::MUTED));
    }
}

fn folder_setting(app: &mut TrainsApp, ui: &mut egui::Ui, label: &str, source: bool) {
    ui.horizontal(|ui| {
        let initial = if source {
            app.settings().org_src.clone()
        } else {
            app.settings().org_dst.clone()
        };
        let mut value = initial;
        let label_response = ui.label(label);
        let response = ui
            .add(
                egui::TextEdit::singleline(&mut value)
                    .hint_text("Choose a folder")
                    .desired_width((ui.available_width() - 100.0).max(180.0)),
            )
            .labelled_by(label_response.id);
        if response.changed() {
            if source {
                app.settings_mut().org_src = value.clone();
            } else {
                app.settings_mut().org_dst = value.clone();
            }
        }
        if response.lost_focus() {
            app.save_settings_notice();
        }
        if ui.button("Browse…").clicked() {
            let mut dialog = rfd::FileDialog::new();
            if !value.trim().is_empty() {
                dialog = dialog.set_directory(PathBuf::from(&value));
            }
            if let Some(folder) = dialog.pick_folder() {
                let folder = folder.to_string_lossy().into_owned();
                if source {
                    app.settings_mut().org_src = folder;
                } else {
                    app.settings_mut().org_dst = folder;
                }
                app.save_settings_notice();
            }
        }
    });
}

fn show_summary(app: &TrainsApp, ui: &mut egui::Ui) {
    let Some(summary) = app.job_state().summary.as_ref() else {
        Frame::group(ui.style())
            .fill(theme::SURFACE)
            .stroke(Stroke::new(1.0, theme::LINE))
            .inner_margin(egui::Margin::same(16))
            .show(ui, |ui| {
                ui.label(RichText::new("Scan summary").strong().color(theme::NAVY));
                ui.add_space(4.0);
                ui.label("A full count and coverage report will appear here after the scan.");
            });
        return;
    };

    Frame::group(ui.style())
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::same(16))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Scan summary").strong().color(theme::NAVY));
                if summary.get("scan_complete").and_then(Value::as_bool) == Some(true) {
                    ui.label(
                        RichText::new("Complete scan")
                            .strong()
                            .color(theme::SUCCESS),
                    );
                } else {
                    ui.label(
                        RichText::new("Incomplete scan")
                            .strong()
                            .color(theme::FAILURE),
                    );
                }
                ui.label(RichText::new(app.job_state().outcome.label()).color(theme::MUTED));
            });
            ui.add_space(8.0);
            egui::Grid::new("organizer_counts")
                .num_columns(3)
                .spacing([22.0, 8.0])
                .show(ui, |ui| {
                    for (index, (key, label)) in [
                        ("moved", "Moved"),
                        ("already_correct", "Already correct"),
                        ("unrecognized", "Unrecognized"),
                        ("corrupt", "Corrupt"),
                        ("conflicts", "Conflicts"),
                        ("metadata_stamped", "Metadata updated"),
                    ]
                    .iter()
                    .enumerate()
                    {
                        ui.label(format!("{label}: {}", count(summary, key)));
                        if index % 3 == 2 {
                            ui.end_row();
                        }
                    }
                });

            let report = summary.get("report").and_then(Value::as_array);
            if let Some(report) = report.filter(|report| !report.is_empty()) {
                ui.add_space(8.0);
                ui.label(RichText::new("Coverage report").strong().color(theme::NAVY));
                for line in report.iter().filter_map(Value::as_str) {
                    ui.label(line);
                }
            }

            if let Some(by_prefix) = summary
                .get("missing_by_prefix_year")
                .and_then(Value::as_object)
            {
                for (prefix, years) in by_prefix {
                    if let Some(years) = years.as_object() {
                        for (year, months) in years {
                            let months = months
                                .as_array()
                                .map(|months| {
                                    months.iter().filter_map(Value::as_str).collect::<Vec<_>>()
                                })
                                .unwrap_or_default();
                            if months.is_empty() {
                                continue;
                            }
                            let state = format!("missing {}", months.join(", "));
                            let coverage = format!("{prefix} {year}: {state}");
                            let report_contains_coverage = summary
                                .get("report")
                                .and_then(Value::as_array)
                                .is_some_and(|report| {
                                    report.iter().any(|line| line.as_str() == Some(&coverage))
                                });
                            if !report_contains_coverage {
                                ui.label(coverage);
                            }
                        }
                    }
                }
            }
        });
}

fn count(summary: &Value, key: &str) -> u64 {
    summary.get(key).and_then(Value::as_u64).unwrap_or_default()
}
