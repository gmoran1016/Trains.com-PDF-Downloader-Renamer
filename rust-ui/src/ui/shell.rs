use eframe::egui::{self, Button, Frame, RichText, Stroke, Vec2};

use crate::{
    app::{CloseChoice, TrainsApp},
    model::{AppPage, JobOutcome},
    theme,
};

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui, ctx: &egui::Context) {
    let compact = ui.available_width() < 1000.0;
    let colors = theme::palette(app.settings().dark_mode);
    let navigation_width = if compact { 156.0 } else { 208.0 };
    crate::ui::activity::show(app, ui, ctx, navigation_width, |app, ui| {
        match app.active_page() {
            AppPage::Magazines => crate::ui::magazines::show_action(app, ui),
            AppPage::TrackPlans => crate::ui::track_plans::show_action(app, ui),
            AppPage::Organize => crate::ui::organize::show_action(app, ui),
        }
    });
    show_titlebar(app, ui, colors);
    show_navigation(app, ui, compact, colors);

    egui::CentralPanel::default()
        .frame(Frame::new().fill(colors.canvas))
        .show(ui, |ui| {
            if let Some(error) = app.settings_error() {
                Frame::new()
                    .fill(colors.warning_surface)
                    .stroke(Stroke::new(1.0, colors.warning))
                    .inner_margin(10.0)
                    .show(ui, |ui| {
                        ui.label(RichText::new(error).color(colors.warning));
                    });
                ui.add_space(8.0);
            }
            if let Some(notice) = app.notice() {
                ui.label(RichText::new(notice).small().color(colors.muted));
                ui.add_space(4.0);
            }

            Frame::new()
                .fill(colors.canvas)
                .inner_margin(egui::Margin::symmetric(20, 0))
                .show(ui, |ui| {
                    let page_width = (ui.available_width() - 12.0).min(980.0);
                    egui::ScrollArea::vertical()
                        .id_salt("work_area_scroll")
                        .max_width(page_width)
                        .auto_shrink([false, false])
                        .show(ui, |ui| {
                            ui.set_max_width(page_width);
                            match app.active_page() {
                                AppPage::Magazines => crate::ui::magazines::show(app, ui),
                                AppPage::TrackPlans => crate::ui::track_plans::show(app, ui),
                                AppPage::Organize => crate::ui::organize::show(app, ui),
                            }
                        });
                });
        });
    crate::ui::account::show(app, ctx);
    show_cache_confirmation_window(app, ctx, colors);
    show_close_confirmation_window(app, ctx, colors);
}

fn show_titlebar(app: &mut TrainsApp, ui: &mut egui::Ui, colors: &theme::Palette) {
    egui::Panel::top("titlebar")
        .exact_size(64.0)
        .frame(
            Frame::new()
                .fill(colors.surface)
                .stroke(Stroke::new(1.0, colors.line))
                .inner_margin(egui::Margin::symmetric(22, 10)),
        )
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.label(RichText::new("Trains.com Archive").size(20.0).strong());
                ui.add_space(12.0);
                state_marker(ui, app.job_state().outcome, colors);
                ui.label(RichText::new(app.job_state().outcome.label()).color(colors.muted));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui
                        .add(
                            Button::new(RichText::new("Account").strong())
                                .fill(colors.canvas)
                                .stroke(Stroke::new(1.0, colors.line)),
                        )
                        .clicked()
                    {
                        app.set_account_open(true);
                    }
                    let mut dark_mode = app.settings().dark_mode;
                    if ui.checkbox(&mut dark_mode, "Dark mode").changed() {
                        app.set_dark_mode(dark_mode);
                    }
                });
            });
        });
}

fn show_navigation(app: &mut TrainsApp, ui: &mut egui::Ui, compact: bool, colors: &theme::Palette) {
    let width = if compact { 156.0 } else { 208.0 };
    let mut selected = None;
    egui::Panel::left("primary_navigation")
        .exact_size(width)
        .resizable(false)
        .frame(
            Frame::new()
                .fill(colors.navy_dark)
                .inner_margin(egui::Margin::symmetric(
                    if compact { 10 } else { 16 },
                    if compact { 4 } else { 18 },
                )),
        )
        .show(ui, |ui| {
            if compact {
                ui.spacing_mut().item_spacing.y = 2.0;
                for (index, page) in AppPage::ALL.into_iter().enumerate() {
                    let is_selected = app.active_page() == page;
                    let fill = if is_selected {
                        colors.selected_fill
                    } else {
                        colors.navy_dark
                    };
                    let ink = if is_selected {
                        colors.selected_ink
                    } else {
                        colors.rail_ink
                    };
                    let response = ui.add_sized(
                        Vec2::new(ui.available_width(), 40.0),
                        Button::new(RichText::new(page.label()).strong().color(ink))
                            .fill(fill)
                            .stroke(if is_selected {
                                Stroke::new(1.0, colors.index_yellow)
                            } else {
                                Stroke::NONE
                            }),
                    );
                    if response.clicked() {
                        selected = Some(page);
                    }
                    if index + 1 < AppPage::ALL.len() {
                        ui.add_space(3.0);
                    }
                }
                return;
            }

            ui.horizontal(|ui| {
                Frame::new()
                    .fill(colors.index_yellow)
                    .inner_margin(egui::Margin::symmetric(7, 3))
                    .show(ui, |ui| {
                        ui.label(RichText::new("A").strong().color(colors.navy_dark));
                    });
                ui.vertical(|ui| {
                    ui.label(
                        RichText::new("TRAINS.COM")
                            .small()
                            .strong()
                            .color(colors.rail_ink),
                    );
                    ui.label(
                        RichText::new("Archive index")
                            .small()
                            .color(colors.rail_muted),
                    );
                });
            });
            ui.add_space(24.0);
            ui.label(
                RichText::new("WORK AREAS")
                    .small()
                    .strong()
                    .color(colors.rail_muted),
            );
            ui.add_space(8.0);

            for page in AppPage::ALL {
                let is_selected = app.active_page() == page;
                let fill = if is_selected {
                    colors.selected_fill
                } else {
                    colors.navy_dark
                };
                let ink = if is_selected {
                    colors.selected_ink
                } else {
                    colors.rail_ink
                };
                let response = ui.add_sized(
                    Vec2::new(ui.available_width(), 46.0),
                    Button::new(RichText::new(page.label()).strong().color(ink))
                        .fill(fill)
                        .stroke(if is_selected {
                            Stroke::new(1.0, colors.index_yellow)
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
                        .color(colors.rail_muted),
                );
                if !compact {
                    ui.label(
                        RichText::new("Windows · Linux · macOS")
                            .small()
                            .color(colors.rail_subtle),
                    );
                }
            });
        });
    if let Some(page) = selected {
        app.set_active_page(page);
    }
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

fn show_cache_confirmation_window(
    app: &mut TrainsApp,
    ctx: &egui::Context,
    colors: &theme::Palette,
) {
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
                            RichText::new("Remove cache files").color(colors.primary_action_text),
                        )
                        .fill(colors.navy)
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

fn show_close_confirmation_window(
    app: &mut TrainsApp,
    ctx: &egui::Context,
    colors: &theme::Palette,
) {
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
                    .color(colors.muted),
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
