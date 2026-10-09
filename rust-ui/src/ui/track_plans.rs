use eframe::egui::{self, Button, Frame, RichText, Stroke};
use serde_json::json;

use crate::{
    app::TrainsApp,
    settings::Settings,
    theme,
    ui::magazines::folder_row,
    worker::{JobKind, WorkerRequest},
};

const TRACK_PLAN_DATABASE: &str = "https://www.trains.com/mrr/how-to/track-plan-database/";

pub fn build_request(settings: &Settings, job_id: String) -> WorkerRequest {
    WorkerRequest {
        job_id,
        job_kind: JobKind::TrackPlans,
        options: json!({
            "destination_dir": settings.track_plans_dir,
            "cookies_path": settings.cookies_path,
        }),
    }
}

pub(crate) fn show(app: &mut TrainsApp, ui: &mut egui::Ui) {
    let colors = theme::palette(app.settings().dark_mode);
    ui.add_space(20.0);
    ui.heading("Track Plan archive");
    ui.add(
        egui::Label::new(
            "Download the plans as PDFs while keeping their original filenames and skipping files already in your archive.",
        )
        .wrap(),
    );
    ui.add_space(14.0);

    Frame::group(ui.style())
        .fill(colors.surface)
        .stroke(Stroke::new(1.0, colors.line))
        .inner_margin(egui::Margin::same(18))
        .show(ui, |ui| {
            ui.label(
                RichText::new("Source")
                    .text_style(egui::TextStyle::Button)
                    .color(colors.blue),
            );
            ui.add_space(7.0);
            ui.label("Model Railroader Track Plan Database");
            ui.hyperlink_to("Open the database", TRACK_PLAN_DATABASE);
        });

    ui.add_space(12.0);
    Frame::group(ui.style())
        .fill(colors.surface)
        .stroke(Stroke::new(1.0, colors.line))
        .inner_margin(egui::Margin::same(18))
        .show(ui, |ui| {
            ui.label(
                RichText::new("Destination")
                    .text_style(egui::TextStyle::Button)
                    .color(colors.blue),
            );
            ui.add_space(7.0);
            folder_row(
                app,
                ui,
                "Track plans save folder",
                app.settings().track_plans_dir.clone(),
                false,
            );
        });
}

pub(crate) fn show_action(app: &mut TrainsApp, ui: &mut egui::Ui) {
    let colors = theme::palette(app.settings().dark_mode);
    if ui
        .add_enabled(
            app.can_start_job(),
            Button::new(
                RichText::new("Download all track plans")
                    .strong()
                    .color(colors.primary_action_text),
            )
            .fill(colors.navy)
            .stroke(Stroke::NONE)
            .min_size(egui::vec2(240.0, 42.0)),
        )
        .clicked()
    {
        app.queue_track_plans();
    }
}
