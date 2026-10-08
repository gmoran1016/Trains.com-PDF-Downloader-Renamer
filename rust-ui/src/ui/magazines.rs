use std::path::PathBuf;

use eframe::egui::{self, Button, Color32, Frame, RichText, Stroke};
use serde_json::json;

use crate::{
    app::TrainsApp,
    settings::Settings,
    theme,
    worker::{JobKind, WorkerRequest},
};

const MAGAZINES: [MagazineInfo; 5] = [
    MagazineInfo {
        name: "Model Railroader",
        prefix: "MRR",
        schedule: "Monthly",
    },
    MagazineInfo {
        name: "Trains Magazine",
        prefix: "TRN",
        schedule: "Monthly",
    },
    MagazineInfo {
        name: "Classic Toy Trains",
        prefix: "CTT",
        schedule: "Monthly",
    },
    MagazineInfo {
        name: "Classic Trains",
        prefix: "CTR",
        schedule: "Quarterly",
    },
    MagazineInfo {
        name: "Garden Railways",
        prefix: "GRW",
        schedule: "Seasonal / archived",
    },
];

struct MagazineInfo {
    name: &'static str,
    prefix: &'static str,
    schedule: &'static str,
}

pub fn build_request(settings: &Settings, job_id: String) -> WorkerRequest {
    WorkerRequest {
        job_id,
        job_kind: JobKind::Magazines,
        options: json!({
            "base_dir": settings.base_dir,
            "magazines": settings.selected_magazines,
            "headless": settings.headless,
            "test_mode": settings.test_mode,
            "cookies_path": settings.cookies_path,
            "newest_first": settings.newest_first,
            "include_specials": settings.include_specials,
        }),
    }
}

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui) {
    ui.add_space(20.0);
    ui.horizontal(|ui| {
        ui.label(
            RichText::new("MAGAZINE ARCHIVE")
                .small()
                .strong()
                .color(theme::BLUE),
        );
        ui.label(RichText::new("5 publications").small().color(theme::MUTED));
    });
    ui.heading(RichText::new("Magazine archive").size(28.0));
    ui.label("Choose the publications and issue range for your local archive.");
    ui.add_space(12.0);

    section(ui, "Publications", |ui| {
        ui.horizontal(|ui| {
            ui.label(RichText::new("Select the titles to include").color(theme::MUTED));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if ui.small_button("Clear all").clicked() {
                    app.settings_mut().selected_magazines.clear();
                    app.save_settings_notice();
                }
                if ui.small_button("Select all").clicked() {
                    app.settings_mut().selected_magazines = MAGAZINES
                        .iter()
                        .map(|magazine| magazine.name.to_owned())
                        .collect();
                    app.save_settings_notice();
                }
            });
        });
        ui.add_space(4.0);

        for magazine in MAGAZINES {
            let selected = app
                .settings()
                .selected_magazines
                .iter()
                .any(|name| name == magazine.name);
            let row_fill = if selected {
                Color32::from_rgb(255, 252, 241)
            } else {
                theme::SURFACE
            };
            Frame::new()
                .fill(row_fill)
                .stroke(Stroke::new(1.0, theme::LINE))
                .inner_margin(egui::Margin::symmetric(10, 5))
                .show(ui, |ui| {
                    ui.horizontal(|ui| {
                        ui.label(RichText::new("▌").color(if selected {
                            theme::INDEX_YELLOW
                        } else {
                            theme::SURFACE
                        }));
                        let mut checked = selected;
                        if ui.checkbox(&mut checked, magazine.name).changed() {
                            let titles = &mut app.settings_mut().selected_magazines;
                            if checked {
                                if !titles.iter().any(|name| name == magazine.name) {
                                    titles.push(magazine.name.to_owned());
                                }
                            } else {
                                titles.retain(|name| name != magazine.name);
                            }
                            app.save_settings_notice();
                        }
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            ui.label(RichText::new(magazine.schedule).small().color(theme::MUTED));
                            ui.add_space(12.0);
                            ui.label(
                                RichText::new(magazine.prefix)
                                    .monospace()
                                    .small()
                                    .strong()
                                    .color(theme::BLUE),
                            );
                        });
                    });
                });
        }
    });

    ui.add_space(12.0);
    section(ui, "Destination", |ui| {
        folder_row(
            app,
            ui,
            "Magazine save folder",
            app.settings().base_dir.clone(),
            true,
        );
        ui.label(
            RichText::new("Existing files are checked before downloads are resumed.")
                .small()
                .color(theme::MUTED),
        );
    });

    ui.add_space(12.0);
    section(ui, "Download options", |ui| {
        egui::Grid::new("magazine_options")
            .num_columns(2)
            .spacing([24.0, 7.0])
            .show(ui, |ui| {
                checkbox(app, ui, "Newest issues first", |settings| {
                    &mut settings.newest_first
                });
                checkbox(app, ui, "Include special issues", |settings| {
                    &mut settings.include_specials
                });
                ui.end_row();
                checkbox(app, ui, "Test mode (first 3 archive pages)", |settings| {
                    &mut settings.test_mode
                });
                checkbox(app, ui, "Keep browser hidden", |settings| {
                    &mut settings.headless
                });
                ui.end_row();
            });
    });

    ui.add_space(12.0);
    section(ui, "Local cache", |ui| {
        ui.horizontal_wrapped(|ui| {
            ui.label("Clear resume progress and the saved special-issue list.");
            if ui
                .add_enabled(app.can_start_job(), egui::Button::new("Clear cache"))
                .clicked()
            {
                app.set_clear_cache_confirmation(true);
            }
        });
    });
}

pub(crate) fn show_action(app: &mut TrainsApp, ui: &mut egui::Ui) {
    ui.horizontal(|ui| {
        let enabled = !app.settings().selected_magazines.is_empty() && app.can_start_job();
        let button = Button::new(
            RichText::new("Download selected magazines")
                .strong()
                .color(theme::PRIMARY_ACTION_TEXT),
        )
        .fill(theme::NAVY)
        .stroke(Stroke::NONE)
        .min_size(egui::vec2(252.0, 42.0));
        if ui.add_enabled(enabled, button).clicked() {
            app.queue_magazines();
        }
        if let Some(notice) = app.notice() {
            ui.label(RichText::new(notice).small().color(theme::MUTED));
        }
    });
}

fn section(ui: &mut egui::Ui, title: &str, content: impl FnOnce(&mut egui::Ui)) {
    Frame::group(ui.style())
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::same(14))
        .show(ui, |ui| {
            ui.label(RichText::new(title).strong().color(theme::NAVY));
            ui.add_space(5.0);
            content(ui);
        });
}

pub(crate) fn folder_row(
    app: &mut TrainsApp,
    ui: &mut egui::Ui,
    label: &str,
    initial_value: String,
    is_magazine: bool,
) {
    ui.horizontal(|ui| {
        let mut value = initial_value;
        let response = ui.add(
            egui::TextEdit::singleline(&mut value)
                .hint_text(label)
                .desired_width((ui.available_width() - 106.0).max(180.0)),
        );
        if response.changed() {
            if is_magazine {
                app.settings_mut().base_dir.clone_from(&value);
            } else {
                app.settings_mut().track_plans_dir.clone_from(&value);
            }
        }
        if response.lost_focus() {
            app.save_settings_notice();
        }

        if ui
            .button("Browse…")
            .on_hover_text(format!("Choose the {label}"))
            .clicked()
        {
            let start = PathBuf::from(&value);
            if let Some(folder) = rfd::FileDialog::new().set_directory(start).pick_folder() {
                let folder = folder.to_string_lossy().into_owned();
                if is_magazine {
                    app.settings_mut().base_dir = folder;
                } else {
                    app.settings_mut().track_plans_dir = folder;
                }
                app.save_settings_notice();
            }
        }
    });
}

type BoolSetting = for<'a> fn(&'a mut Settings) -> &'a mut bool;

fn checkbox(app: &mut TrainsApp, ui: &mut egui::Ui, label: &str, get_value: BoolSetting) {
    let changed = {
        let settings = app.settings_mut();
        ui.checkbox(get_value(settings), label).changed()
    };
    if changed {
        app.save_settings_notice();
    }
}
