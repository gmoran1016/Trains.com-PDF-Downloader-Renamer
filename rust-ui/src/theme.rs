use eframe::egui::{self, Color32};

pub const NAVY: Color32 = Color32::from_rgb(30, 56, 91);
pub const NAVY_DARK: Color32 = Color32::from_rgb(23, 44, 72);
pub const PRIMARY_ACTION_TEXT: Color32 = Color32::WHITE;
pub const BLUE: Color32 = Color32::from_rgb(44, 91, 139);
pub const INK: Color32 = Color32::from_rgb(29, 43, 58);
pub const MUTED: Color32 = Color32::from_rgb(92, 109, 126);
pub const CANVAS: Color32 = Color32::from_rgb(239, 244, 247);
pub const SURFACE: Color32 = Color32::WHITE;
pub const INDEX_YELLOW: Color32 = Color32::from_rgb(255, 205, 64);
pub const LINE: Color32 = Color32::from_rgb(213, 222, 229);
pub const SUCCESS: Color32 = Color32::from_rgb(45, 126, 88);
pub const WARNING: Color32 = Color32::from_rgb(155, 91, 16);
pub const WARNING_SURFACE: Color32 = Color32::from_rgb(255, 246, 225);
pub const FAILURE: Color32 = Color32::from_rgb(175, 66, 63);

pub fn apply(ctx: &egui::Context) {
    let mut visuals = egui::Visuals::light();
    visuals.override_text_color = Some(INK);
    visuals.window_fill = CANVAS;
    visuals.panel_fill = CANVAS;
    visuals.widgets.noninteractive.bg_fill = SURFACE;
    visuals.widgets.inactive.bg_fill = SURFACE;
    visuals.widgets.inactive.fg_stroke.color = INK;
    visuals.widgets.hovered.bg_fill = Color32::from_rgb(231, 239, 244);
    visuals.widgets.hovered.fg_stroke.color = NAVY;
    visuals.widgets.active.bg_fill = Color32::from_rgb(222, 233, 241);
    visuals.widgets.active.fg_stroke.color = NAVY_DARK;
    visuals.selection.bg_fill = INDEX_YELLOW;
    visuals.selection.stroke.color = NAVY;
    ctx.set_visuals(visuals);
    ctx.all_styles_mut(|style| {
        style.spacing.item_spacing = egui::vec2(10.0, 9.0);
        style.spacing.button_padding = egui::vec2(13.0, 8.0);
        style.visuals.window_stroke.color = LINE;
    });
}

#[cfg(test)]
mod tests {
    use super::{CANVAS, NAVY, PRIMARY_ACTION_TEXT, SURFACE, WARNING, WARNING_SURFACE};
    use eframe::egui::Color32;

    fn linear_channel(channel: u8) -> f64 {
        let channel = f64::from(channel) / 255.0;
        if channel <= 0.04045 {
            channel / 12.92
        } else {
            ((channel + 0.055) / 1.055).powf(2.4)
        }
    }

    fn luminance(color: Color32) -> f64 {
        0.2126 * linear_channel(color.r())
            + 0.7152 * linear_channel(color.g())
            + 0.0722 * linear_channel(color.b())
    }

    #[test]
    fn primary_action_text_meets_wcag_aa_contrast_on_navy() {
        let contrast = (luminance(NAVY).max(luminance(PRIMARY_ACTION_TEXT)) + 0.05)
            / (luminance(NAVY).min(luminance(PRIMARY_ACTION_TEXT)) + 0.05);

        assert!(
            contrast >= 4.5,
            "primary action text contrast was {contrast:.2}:1"
        );
    }

    #[test]
    fn warning_status_text_meets_wcag_aa_on_light_surfaces() {
        for (surface_name, background) in [
            ("canvas", CANVAS),
            ("surface", SURFACE),
            ("warning panel", WARNING_SURFACE),
        ] {
            let contrast = (luminance(WARNING).max(luminance(background)) + 0.05)
                / (luminance(WARNING).min(luminance(background)) + 0.05);
            assert!(
                contrast >= 4.5,
                "warning text contrast on {surface_name} was {contrast:.2}:1"
            );
        }
    }
}
