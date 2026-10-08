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
    ui.add_space(20.0);
    ui.label(
        RichText::new("MODEL RAILROADER DATABASE")
            .small()
            .strong()
            .color(theme::BLUE),
    );
    ui.heading(RichText::new("Track Plan archive").size(28.0));
    ui.label(
        "Download the plans as PDFs while keeping their original filenames and skipping files already in your archive.",
    );
    ui.add_space(14.0);

    Frame::group(ui.style())
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::same(16))
        .show(ui, |ui| {
            ui.label(RichText::new("Source").strong().color(theme::NAVY));
            ui.add_space(5.0);
            ui.label("Model Railroader Track Plan Database");
            ui.hyperlink_to("Open the database", TRACK_PLAN_DATABASE);
        });

    ui.add_space(12.0);
    Frame::group(ui.style())
        .fill(theme::SURFACE)
        .stroke(Stroke::new(1.0, theme::LINE))
        .inner_margin(egui::Margin::same(16))
        .show(ui, |ui| {
            ui.label(RichText::new("Destination").strong().color(theme::NAVY));
            ui.add_space(5.0);
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
    if ui
        .add_enabled(
            app.can_start_job(),
            Button::new(
                RichText::new("Download all track plans")
                    .strong()
                    .color(theme::PRIMARY_ACTION_TEXT),
            )
            .fill(theme::NAVY)
            .stroke(Stroke::NONE)
            .min_size(egui::vec2(240.0, 42.0)),
        )
        .clicked()
    {
        app.queue_track_plans();
    }
    if let Some(notice) = app.notice() {
        ui.add_space(4.0);
        ui.label(RichText::new(notice).small().color(theme::MUTED));
    }
}
