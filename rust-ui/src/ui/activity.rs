use eframe::egui::{
    self, Align, Button, Frame, Layout, Rect, RichText, Sense, Stroke, UiBuilder, Vec2,
};

use crate::{
    app::TrainsApp,
    model::{JobOutcome, LogEntry, LogLevel},
    theme,
};

const MIN_EXPANDED_HEIGHT: f32 = 128.0;
const MAX_EXPANDED_HEIGHT: f32 = 340.0;
const MIN_WORK_AREA_HEIGHT: f32 = 144.0;
const FIXED_SHELL_HEIGHT: f32 = 128.0;

pub(crate) fn show(
    app: &mut TrainsApp,
    ui: &mut egui::Ui,
    ctx: &egui::Context,
    navigation_width: f32,
    show_action: impl FnOnce(&mut TrainsApp, &mut egui::Ui),
) {
    let collapsed = app.settings().activity_collapsed;
    let colors = theme::palette(app.settings().dark_mode);
    let available_height = ui.available_height();
    let max_expanded_height = (available_height - FIXED_SHELL_HEIGHT - MIN_WORK_AREA_HEIGHT)
        .clamp(MIN_EXPANDED_HEIGHT, MAX_EXPANDED_HEIGHT);
    let expanded_height = app
        .settings()
        .activity_height
        .clamp(MIN_EXPANDED_HEIGHT, max_expanded_height);
    let activity_height = if collapsed { 48.0 } else { expanded_height };
    let action_height = 64.0;
    let dock_height = action_height + activity_height;
    let action_frame = Frame::new()
        .fill(colors.surface)
        .stroke(Stroke::new(1.0, colors.line))
        .inner_margin(egui::Margin::symmetric(20, 9));
    let activity_frame = Frame::new()
        .fill(colors.surface)
        .stroke(Stroke::new(1.0, colors.line))
        .inner_margin(egui::Margin::symmetric(16, 8));
    let mut toggle_to = None;

    egui::Panel::bottom("workflow_activity_dock")
        .exact_size(dock_height)
        .frame(Frame::new().fill(colors.surface))
        .show(ui, |ui| {
            ui.spacing_mut().item_spacing.y = 0.0;
            let panel_rect = ui.available_rect_before_wrap();
            let action_row_rect =
                Rect::from_min_size(panel_rect.min, Vec2::new(panel_rect.width(), action_height));
            let rail_rect = Rect::from_min_max(
                action_row_rect.min,
                egui::pos2(
                    action_row_rect.min.x + navigation_width,
                    action_row_rect.max.y,
                ),
            );
            ui.painter().rect_filled(rail_rect, 0.0, colors.navy_dark);
            let action_rect = Rect::from_min_max(
                egui::pos2(rail_rect.max.x, action_row_rect.min.y),
                action_row_rect.max,
            );
            let mut action_ui = ui.new_child(
                UiBuilder::new()
                    .max_rect(action_rect)
                    .layout(Layout::top_down(Align::Min)),
            );
            action_ui.expand_to_include_rect(action_rect);
            action_ui.set_min_size(action_rect.size());
            action_ui.set_clip_rect(action_rect);
            action_frame.show(&mut action_ui, |ui| show_action(app, ui));
            ui.advance_cursor_after_rect(action_row_rect);

            let activity_rect = ui.available_rect_before_wrap();
            let mut activity_ui = ui.new_child(
                UiBuilder::new()
                    .max_rect(activity_rect)
                    .layout(Layout::top_down(Align::Min)),
            );
            activity_ui.expand_to_include_rect(activity_rect);
            activity_ui.set_min_size(activity_rect.size());
            activity_ui.set_clip_rect(activity_rect);
            activity_frame.show(&mut activity_ui, |ui| {
                if collapsed {
                    toggle_to = activity_header(app, ui, true, colors);
                } else {
                    let handle = ui
                        .add_sized(
                            Vec2::new(ui.available_width(), 22.0),
                            egui::Label::new(
                                RichText::new("Resize Activity").small().color(colors.muted),
                            )
                            .sense(Sense::drag()),
                        )
                        .on_hover_cursor(egui::CursorIcon::ResizeVertical);
                    if handle.dragged() {
                        let next_height = (app.settings().activity_height - handle.drag_delta().y)
                            .clamp(MIN_EXPANDED_HEIGHT, max_expanded_height);
                        app.record_activity_height(next_height);
                    }
                    toggle_to = activity_header(app, ui, false, colors);
                    ui.separator();
                    show_activity_body(app, ui, colors);
                }
            });
        });

    app.save_activity_resize_if_released(ctx.input(|input| input.pointer.primary_down()));
    if let Some(collapsed) = toggle_to {
        app.settings_mut().activity_collapsed = collapsed;
        app.save_settings_notice();
    }
}

fn activity_header(
    app: &mut TrainsApp,
    ui: &mut egui::Ui,
    collapsed: bool,
    colors: &theme::Palette,
) -> Option<bool> {
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
        ui.label(RichText::new("Activity").strong().color(colors.blue));
        state_marker(ui, app.job_state().outcome, colors);
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
                    Button::new(label).stroke(Stroke::new(1.0, colors.failure)),
                )
                .clicked()
            {
                app.request_stop();
            }
        }
        if !collapsed {
            ui.separator();
            let message = app.job_state().message.clone();
            ui.add(egui::Label::new(RichText::new(&message).color(colors.muted)).truncate())
                .on_hover_text(message);
        }
    });
    next_state
}

fn show_activity_body(app: &mut TrainsApp, ui: &mut egui::Ui, colors: &theme::Palette) {
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
        let filter_width = (ui.available_width() * 0.25).clamp(140.0, 220.0);
        let filter = ui
            .add(
                egui::TextEdit::singleline(app.activity_filter_mut())
                    .hint_text("Type to filter")
                    .desired_width(filter_width),
            )
            .labelled_by(label.id);
        filter.on_hover_text("Filter visible events; the full activity log is kept until cleared.");
        ui.label(format!("{error_count} errors"));
        copy_errors = ui
            .add_enabled(
                error_count > 0,
                Button::new("Copy errors").stroke(Stroke::new(1.0, colors.line)),
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
        ui.label(RichText::new("No activity yet.").color(colors.muted));
    } else if matching_rows.is_empty() {
        ui.label(RichText::new("No activity matches this filter.").color(colors.muted));
    } else {
        let row_height = ui.text_style_height(&egui::TextStyle::Body) + ui.spacing().item_spacing.y;
        egui::ScrollArea::vertical()
            .id_salt("activity_events")
            .auto_shrink([false, false])
            .stick_to_bottom(true)
            .show_rows(ui, row_height, matching_rows.len(), |ui, row_range| {
                for row in row_range {
                    if let Some(entry) = matching_rows.get(row).and_then(|index| logs.get(*index)) {
                        show_log_entry(ui, entry, colors);
                    }
                }
            });
    }
}

fn show_log_entry(ui: &mut egui::Ui, entry: &LogEntry, colors: &theme::Palette) {
    let (label, color) = match entry.level {
        LogLevel::Debug => ("Detail", colors.muted),
        LogLevel::Info => ("Info", colors.blue),
        LogLevel::Warning => ("Warning", colors.warning),
        LogLevel::Error => ("Error", colors.failure),
    };
    ui.horizontal(|ui| {
        ui.label(RichText::new(label).small().strong().color(color));
        ui.add(egui::Label::new(&entry.message).truncate())
            .on_hover_text(&entry.message);
    });
}

fn state_marker(ui: &mut egui::Ui, outcome: JobOutcome, colors: &theme::Palette) {
    let (symbol, color) = match outcome {
        JobOutcome::Idle => ("○", colors.muted),
        JobOutcome::Running => ("●", colors.blue),
        JobOutcome::Success => ("✓", colors.success),
        JobOutcome::NoResults => ("–", colors.muted),
        JobOutcome::Failed => ("!", colors.failure),
        JobOutcome::Cancelled => ("Ⅱ", colors.warning),
    };
    ui.label(RichText::new(symbol).strong().color(color));
}
