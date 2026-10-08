use eframe::egui::{self, Button, Frame, RichText, Sense, Stroke, Vec2};

use crate::{
    app::TrainsApp,
    model::{JobOutcome, LogEntry, LogLevel},
    theme,
};

const MIN_EXPANDED_HEIGHT: f32 = 112.0;
const MAX_EXPANDED_HEIGHT: f32 = 340.0;
const MIN_WORK_AREA_HEIGHT: f32 = 208.0;
const FIXED_SHELL_HEIGHT: f32 = 128.0;

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui, ctx: &egui::Context) {
    let collapsed = app.settings().activity_collapsed;
    let max_expanded_height = (ui.available_height() - FIXED_SHELL_HEIGHT - MIN_WORK_AREA_HEIGHT)
        .clamp(MIN_EXPANDED_HEIGHT, MAX_EXPANDED_HEIGHT);
    let expanded_height = app
        .settings()
        .activity_height
        .clamp(MIN_EXPANDED_HEIGHT, max_expanded_height);
    let frame = Frame::new()
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::symmetric(16, 8));
    let mut toggle_to = None;

    if collapsed {
        egui::Panel::bottom("activity_dock")
            .exact_size(48.0)
            .frame(frame)
            .show(ui, |ui| {
                toggle_to = activity_header(app, ui, true);
            });
    } else {
        let response = egui::Panel::bottom("activity_dock")
            .exact_size(expanded_height)
            .frame(frame)
            .show(ui, |ui| {
                let handle = ui
                    .add_sized(
                        Vec2::new(ui.available_width(), 18.0),
                        egui::Label::new(
                            RichText::new("Resize Activity").small().color(theme::MUTED),
                        )
                        .sense(Sense::drag()),
                    )
                    .on_hover_cursor(egui::CursorIcon::ResizeVertical);
                if handle.dragged() {
                    let next_height = (app.settings().activity_height - handle.drag_delta().y)
                        .clamp(MIN_EXPANDED_HEIGHT, max_expanded_height);
                    app.record_activity_height(next_height);
                }
                let toggle = activity_header(app, ui, false);
                ui.separator();
                show_activity_body(app, ui);
                toggle
            });
        toggle_to = response.inner;
    }

    app.save_activity_resize_if_released(ctx.input(|input| input.pointer.primary_down()));
    if let Some(collapsed) = toggle_to {
        app.settings_mut().activity_collapsed = collapsed;
        app.save_settings_notice();
    }
}

fn activity_header(app: &mut TrainsApp, ui: &mut egui::Ui, collapsed: bool) -> Option<bool> {
    let mut next_state = None;
    ui.horizontal(|ui| {
        let label = if collapsed {
            "Expand Activity"
        } else {
            "Collapse Activity"
        };
        if ui.small_button(label).clicked() {
            next_state = Some(!collapsed);
        }
        ui.label(RichText::new("Activity").strong().color(theme::NAVY));
        state_marker(ui, app.job_state().outcome);
        ui.label(RichText::new(app.job_state().outcome.label()).strong());
        if app.job_state().outcome == JobOutcome::Running {
            let label = if app.job_state().stop_requested {
                "Stop requested"
            } else {
                "Stop job"
            };
            if ui
                .add_enabled(
                    !app.job_state().stop_requested,
                    Button::new(label).stroke(Stroke::new(1.0, theme::FAILURE)),
                )
                .clicked()
            {
                app.request_stop();
            }
        }
        if !collapsed {
            ui.separator();
            let message = app.job_state().message.clone();
            ui.add(egui::Label::new(RichText::new(&message).color(theme::MUTED)).truncate())
                .on_hover_text(message);
        }
    });
    next_state
}

fn show_activity_body(app: &mut TrainsApp, ui: &mut egui::Ui) {
    let state = app.job_state();
    if state.done.is_some() || state.total.is_some() {
        let done = state.done.unwrap_or_default();
        let total = state.total.unwrap_or_default();
        if total > 0 {
            ui.add(
                egui::ProgressBar::new((done as f32 / total as f32).clamp(0.0, 1.0))
                    .text(format!("{done} / {total}")),
            );
        }
    }
    if !state.per_magazine.is_empty() {
        ui.horizontal_wrapped(|ui| {
            for (name, progress) in &state.per_magazine {
                ui.label(format!("{name}: {} / {}", progress.done, progress.total));
            }
        });
    }

    let error_count = state.errors.len();
    let mut copy_errors = false;
    let mut clear_activity = false;
    ui.horizontal(|ui| {
        let label = ui.label("Filter activity");
        let filter = ui
            .add(
                egui::TextEdit::singleline(app.activity_filter_mut())
                    .hint_text("Type to filter")
                    .desired_width(220.0),
            )
            .labelled_by(label.id);
        filter.on_hover_text("Filter visible events; the full activity log is kept until cleared.");
        ui.label(format!("{error_count} errors"));
        copy_errors = ui
            .add_enabled(
                error_count > 0,
                Button::new("Copy errors").stroke(Stroke::new(1.0, theme::LINE)),
            )
            .clicked();
        clear_activity = ui.button("Clear activity").clicked();
    });

    if copy_errors {
        let text = app
            .job_state()
            .errors
            .iter()
            .map(|entry| entry.message.as_str())
            .collect::<Vec<_>>()
            .join("\n");
        ui.output_mut(|output| {
            output.commands.push(egui::OutputCommand::CopyText(text));
        });
    }
    if clear_activity {
        app.clear_activity();
    }

    let (logs, matching_rows) = app.activity_rows();
    if logs.is_empty() {
        ui.label(RichText::new("No activity yet.").color(theme::MUTED));
    } else if matching_rows.is_empty() {
        ui.label(RichText::new("No activity matches this filter.").color(theme::MUTED));
    } else {
        let row_height = ui.text_style_height(&egui::TextStyle::Body) + ui.spacing().item_spacing.y;
        egui::ScrollArea::vertical()
            .id_salt("activity_events")
            .auto_shrink([false, false])
            .stick_to_bottom(true)
            .show_rows(ui, row_height, matching_rows.len(), |ui, row_range| {
                for row in row_range {
                    if let Some(entry) = matching_rows.get(row).and_then(|index| logs.get(*index)) {
                        show_log_entry(ui, entry);
                    }
                }
            });
    }
}

fn show_log_entry(ui: &mut egui::Ui, entry: &LogEntry) {
    let (label, color) = match entry.level {
        LogLevel::Debug => ("Detail", theme::MUTED),
        LogLevel::Info => ("Info", theme::BLUE),
        LogLevel::Warning => ("Warning", theme::WARNING),
        LogLevel::Error => ("Error", theme::FAILURE),
    };
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).small().strong().color(color));
        ui.add(egui::Label::new(&entry.message).truncate())
            .on_hover_text(&entry.message);
    });
}

fn state_marker(ui: &mut egui::Ui, outcome: JobOutcome) {
    let (symbol, color) = match outcome {
        JobOutcome::Idle => ("○", theme::MUTED),
        JobOutcome::Running => ("●", theme::BLUE),
        JobOutcome::Success => ("✓", theme::SUCCESS),
        JobOutcome::NoResults => ("–", theme::MUTED),
        JobOutcome::Failed => ("!", theme::FAILURE),
        JobOutcome::Cancelled => ("Ⅱ", theme::WARNING),
    };
    ui.label(RichText::new(symbol).strong().color(color));
}
