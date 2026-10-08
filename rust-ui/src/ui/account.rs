use std::path::Path;

use eframe::egui::{self, Button, RichText, Stroke};

use crate::{app::TrainsApp, theme};

pub(crate) fn show(app: &mut TrainsApp, ctx: &egui::Context) {
    if !app.account_open() {
        return;
    }
    let mut open = true;
    egui::Window::new("Account settings")
        .open(&mut open)
        .collapsible(false)
        .resizable(false)
        .default_width(470.0)
        .show(ctx, |ui| {
            ui.label(
                RichText::new("Shared access settings")
                    .strong()
                    .color(theme::NAVY),
            );
            ui.label("Choose the local cookie file used to access Trains.com.");
            ui.add_space(8.0);

            let mut cookie_path = app.settings().cookies_path.clone();
            ui.horizontal(|ui| {
                let label = ui.label("Cookie file path");
                let response = ui
                    .add(
                        egui::TextEdit::singleline(&mut cookie_path)
                            .hint_text("Path to session cookie file")
                            .desired_width(320.0),
                    )
                    .labelled_by(label.id);
                if response.changed() {
                    app.settings_mut().cookies_path.clone_from(&cookie_path);
                }
                if ui.button("Browse…").clicked() {
                    let mut dialog = rfd::FileDialog::new().set_file_name("session_cookies.json");
                    if !cookie_path.trim().is_empty()
                        && let Some(parent) = Path::new(&cookie_path).parent()
                    {
                        dialog = dialog.set_directory(parent);
                    }
                    if let Some(file) = dialog.pick_file() {
                        app.settings_mut().cookies_path = file.to_string_lossy().into_owned();
                    }
                }
            });

            let exists = Path::new(&app.settings().cookies_path).is_file();
            ui.label(
                RichText::new(if exists {
                    "Cookie file found. Its contents are never shown."
                } else {
                    "Cookie file not found. Its contents are never shown."
                })
                .small()
                .color(if exists { theme::SUCCESS } else { theme::MUTED }),
            );
            ui.add_space(10.0);

            let mut headless = app.settings().headless;
            if ui
                .checkbox(&mut headless, "Keep magazine browser hidden")
                .changed()
            {
                app.settings_mut().headless = headless;
            }
            let mut org_headless = app.settings().org_headless;
            if ui
                .checkbox(
                    &mut org_headless,
                    "Hide browser for missing-issue downloads",
                )
                .changed()
            {
                app.settings_mut().org_headless = org_headless;
            }
            ui.label(
                RichText::new("These choices are shared with their matching work areas.")
                    .small()
                    .color(theme::MUTED),
            );
            ui.add_space(12.0);
            ui.horizontal(|ui| {
                if ui
                    .add(
                        Button::new(
                            RichText::new("Save settings")
                                .strong()
                                .color(theme::PRIMARY_ACTION_TEXT),
                        )
                        .fill(theme::NAVY)
                        .stroke(Stroke::NONE),
                    )
                    .clicked()
                {
                    app.save_settings_notice();
                    app.set_account_open(false);
                }
                if ui.button("Close").clicked() {
                    app.set_account_open(false);
                }
            });
        });
    if !open {
        app.set_account_open(false);
    }
}
