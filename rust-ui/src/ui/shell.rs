use eframe::egui::{self, Button, Color32, Frame, RichText, Stroke, Vec2};

use crate::{
    app::{CloseChoice, TrainsApp},
    model::{AppPage, JobOutcome},
    theme,
};

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui, ctx: &egui::Context) {
    let compact = ui.available_width() < 1000.0;
    crate::ui::activity::show(app, ui, ctx);
    show_titlebar(app, ui);
    show_navigation(app, ui, compact);
    egui::CentralPanel::default()
        .frame(Frame::new().fill(theme::CANVAS))
        .show(ui, |ui| {
            if let Some(error) = app.settings_error() {
                Frame::new()
                    .fill(theme::WARNING_SURFACE)
                    .stroke(Stroke::new(1.0, theme::WARNING))
                    .inner_margin(10.0)
                    .show(ui, |ui| {
                        ui.label(RichText::new(error).color(theme::WARNING));
                    });
                ui.add_space(8.0);
            }

            egui::Panel::bottom("workflow_actions")
                .exact_size(64.0)
                .frame(
                    Frame::new()
                        .fill(theme::SURFACE)
                        .stroke(Stroke::new(1.0, theme::LINE))
                        .inner_margin(egui::Margin::symmetric(20, 9)),
                )
                .show(ui, |ui| match app.active_page() {
                    AppPage::Magazines => crate::ui::magazines::show_action(app, ui),
                    AppPage::TrackPlans => crate::ui::track_plans::show_action(app, ui),
                    AppPage::Organize => crate::ui::organize::show_action(app, ui),
                });

            egui::ScrollArea::vertical()
                .id_salt("work_area_scroll")
                .auto_shrink([false, false])
                .show(ui, |ui| {
                    ui.set_max_width(980.0);
                    match app.active_page() {
                        AppPage::Magazines => crate::ui::magazines::show(app, ui),
                        AppPage::TrackPlans => crate::ui::track_plans::show(app, ui),
                        AppPage::Organize => crate::ui::organize::show(app, ui),
                    }
                });
        });
    crate::ui::account::show(app, ctx);
    show_cache_confirmation_window(app, ctx);
    show_close_confirmation_window(app, ctx);
}

fn show_titlebar(app: &mut TrainsApp, ui: &mut egui::Ui) {
    egui::Panel::top("titlebar")
        .exact_size(64.0)
        .frame(
            Frame::new()
                .fill(theme::SURFACE)
                .stroke(Stroke::new(1.0, theme::LINE))
                .inner_margin(egui::Margin::symmetric(22, 10)),
        )
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Trains.com Archive").size(20.0).strong());
                ui.add_space(12.0);
                state_marker(ui, app.job_state().outcome);
                ui.label(RichText::new(app.job_state().outcome.label()).color(theme::MUTED));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui
                        .add(
                            Button::new(RichText::new("Account").strong())
                                .fill(theme::CANVAS)
                                .stroke(Stroke::new(1.0, theme::LINE)),
                        )
                        .clicked()
                    {
                        app.set_account_open(true);
                    }
                    ui.label(RichText::new("Shared settings").small().color(theme::MUTED));
                });
            });
        });
}

fn show_navigation(app: &mut TrainsApp, ui: &mut egui::Ui, compact: bool) {
    let width = if compact { 156.0 } else { 208.0 };
    let mut selected = None;
    egui::Panel::left("primary_navigation")
        .exact_size(width)
        .resizable(false)
        .frame(
            Frame::new()
                .fill(theme::NAVY)
                .inner_margin(egui::Margin::symmetric(if compact { 10 } else { 16 }, 18)),
        )
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                Frame::new()
                    .fill(theme::INDEX_YELLOW)
                    .inner_margin(egui::Margin::symmetric(7, 3))
                    .show(ui, |ui| {
                        ui.label(RichText::new("A").strong().color(theme::NAVY_DARK));
                    });
                ui.vertical(|ui| {
                    ui.label(
                        RichText::new("TRAINS.COM")
                            .small()
                            .strong()
                            .color(Color32::WHITE),
                    );
                    ui.label(
                        RichText::new("Archive index")
                            .small()
                            .color(Color32::from_rgb(205, 217, 228)),
                    );
                });
            });
            ui.add_space(24.0);
            ui.label(
                RichText::new("WORK AREAS")
                    .small()
                    .strong()
                    .color(Color32::from_rgb(190, 207, 221)),
            );
            ui.add_space(8.0);

            for page in AppPage::ALL {
                let is_selected = app.active_page() == page;
                let fill = if is_selected {
                    Color32::from_rgb(255, 250, 230)
                } else {
                    theme::NAVY
                };
                let ink = if is_selected {
                    theme::NAVY_DARK
                } else {
                    Color32::WHITE
                };
                let response = ui.add_sized(
                    Vec2::new(ui.available_width(), 46.0),
                    Button::new(RichText::new(page.label()).strong().color(ink))
                        .fill(fill)
                        .stroke(if is_selected {
                            Stroke::new(1.0, theme::INDEX_YELLOW)
                        } else {
                            Stroke::NONE
                        }),
                );
                if response.clicked() {
                    selected = Some(page);
                }
                ui.add_space(5.0);
            }

            ui.with_layout(egui::Layout::bottom_up(egui::Align::Min), |ui| {
                ui.label(
                    RichText::new("Local PDF archive")
                        .small()
                        .color(Color32::from_rgb(205, 217, 228)),
                );
                ui.label(
                    RichText::new("Windows · Linux · macOS")
                        .small()
                        .color(Color32::from_rgb(157, 178, 197)),
                );
            });
        });
    if let Some(page) = selected {
        app.set_active_page(page);
    }
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

fn show_cache_confirmation_window(app: &mut TrainsApp, ctx: &egui::Context) {
    if !app.clear_cache_confirmation() {
        return;
    }
    if !app.can_start_job() {
        app.set_clear_cache_confirmation(false);
        return;
    }
    let mut open = true;
    egui::Window::new("Clear local cache?")
        .open(&mut open)
        .collapsible(false)
        .resizable(false)
        .default_width(420.0)
        .show(ctx, |ui| {
            ui.label("This removes only download_progress.json and special_issues.json.");
            ui.label("Settings, cookies, logs, and downloaded PDFs are kept.");
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("Cancel").clicked() {
                    app.set_clear_cache_confirmation(false);
                }
                if ui
                    .add(
                        Button::new(
                            RichText::new("Remove cache files").color(theme::PRIMARY_ACTION_TEXT),
                        )
                        .fill(theme::NAVY)
                        .stroke(Stroke::NONE)
                        .min_size(egui::vec2(150.0, 36.0)),
                    )
                    .clicked()
                {
                    app.confirm_clear_cache();
                }
            });
        });
    if !open {
        app.set_clear_cache_confirmation(false);
    }
}

fn show_close_confirmation_window(app: &mut TrainsApp, ctx: &egui::Context) {
    if !app.close_dialog_open() {
        return;
    }

    let mut is_open = true;
    let mut choice = None;
    let tray_available = app.tray_available();
    egui::Window::new("A job is still running")
        .open(&mut is_open)
        .collapsible(false)
        .resizable(false)
        .default_width(430.0)
        .show(ctx, |ui| {
            ui.label("Choose how to handle the current job before closing.");
            ui.add_space(10.0);
            ui.horizontal_wrapped(|ui| {
                if ui
                    .add_enabled(tray_available, Button::new("Minimize to Tray"))
                    .clicked()
                {
                    choice = Some(CloseChoice::MinimizeToTray);
                }
                if ui.button("Stop & Quit").clicked() {
                    choice = Some(CloseChoice::StopAndQuit);
                }
                if ui.button("Cancel").clicked() {
                    choice = Some(CloseChoice::Cancel);
                }
            });
            if !tray_available {
                ui.add_space(8.0);
                ui.label(
                    RichText::new(
                        "The system tray is unavailable; Stop & Quit or Cancel remains available.",
                    )
                    .small()
                    .color(theme::MUTED),
                );
            }
        });

    if !is_open {
        app.cancel_close_dialog();
    }
    if let Some(choice) = choice {
        app.choose_close_action(choice, ctx);
    }
}
