use std::{collections::BTreeMap, sync::Arc};

use eframe::egui::{self, Color32, FontData, FontDefinitions, FontFamily, FontId, TextStyle};

#[derive(Clone, Copy, Debug)]
pub struct Palette {
    pub canvas: Color32,
    pub surface: Color32,
    pub surface_hover: Color32,
    pub line: Color32,
    pub ink: Color32,
    pub muted: Color32,
    pub navy: Color32,
    pub navy_dark: Color32,
    pub blue: Color32,
    pub index_yellow: Color32,
    pub selected_fill: Color32,
    pub selected_ink: Color32,
    pub primary_action_text: Color32,
    pub success: Color32,
    pub warning: Color32,
    pub warning_surface: Color32,
    pub failure: Color32,
    pub rail_ink: Color32,
    pub rail_muted: Color32,
    pub rail_subtle: Color32,
}

pub const LIGHT: Palette = Palette {
    canvas: Color32::from_rgb(242, 246, 249),
    surface: Color32::WHITE,
    surface_hover: Color32::from_rgb(232, 239, 245),
    line: Color32::from_rgb(203, 215, 224),
    ink: Color32::from_rgb(25, 39, 53),
    muted: Color32::from_rgb(76, 94, 111),
    navy: Color32::from_rgb(30, 56, 91),
    navy_dark: Color32::from_rgb(23, 44, 72),
    blue: Color32::from_rgb(44, 91, 139),
    index_yellow: Color32::from_rgb(255, 205, 64),
    selected_fill: Color32::from_rgb(255, 248, 228),
    selected_ink: Color32::from_rgb(23, 44, 72),
    primary_action_text: Color32::WHITE,
    success: Color32::from_rgb(34, 105, 70),
    warning: Color32::from_rgb(125, 75, 10),
    warning_surface: Color32::from_rgb(255, 245, 218),
    failure: Color32::from_rgb(163, 52, 49),
    rail_ink: Color32::WHITE,
    rail_muted: Color32::from_rgb(223, 232, 240),
    rail_subtle: Color32::from_rgb(196, 211, 224),
};

pub const DARK: Palette = Palette {
    canvas: Color32::from_rgb(17, 27, 38),
    surface: Color32::from_rgb(27, 40, 53),
    surface_hover: Color32::from_rgb(40, 57, 73),
    line: Color32::from_rgb(59, 76, 91),
    ink: Color32::from_rgb(236, 242, 247),
    muted: Color32::from_rgb(189, 202, 213),
    navy: Color32::from_rgb(46, 83, 118),
    navy_dark: Color32::from_rgb(15, 25, 36),
    blue: Color32::from_rgb(135, 194, 236),
    index_yellow: Color32::from_rgb(255, 205, 64),
    selected_fill: Color32::from_rgb(46, 67, 85),
    selected_ink: Color32::from_rgb(246, 249, 251),
    primary_action_text: Color32::WHITE,
    success: Color32::from_rgb(133, 218, 173),
    warning: Color32::from_rgb(255, 211, 128),
    warning_surface: Color32::from_rgb(62, 49, 31),
    failure: Color32::from_rgb(255, 159, 151),
    rail_ink: Color32::from_rgb(240, 245, 249),
    rail_muted: Color32::from_rgb(211, 224, 235),
    rail_subtle: Color32::from_rgb(179, 197, 212),
};

const REGULAR_FONT: &str = "Source Sans 3 Regular";
const SEMIBOLD_FONT: &str = "Source Sans 3 Semibold";

pub const fn palette(dark_mode: bool) -> &'static Palette {
    if dark_mode { &DARK } else { &LIGHT }
}

pub fn install_fonts(ctx: &egui::Context) {
    let mut fonts = FontDefinitions::default();
    fonts.font_data.insert(
        REGULAR_FONT.to_owned(),
        Arc::new(FontData::from_static(include_bytes!(
            "../assets/SourceSans3-Regular.ttf"
        ))),
    );
    fonts.font_data.insert(
        SEMIBOLD_FONT.to_owned(),
        Arc::new(FontData::from_static(include_bytes!(
            "../assets/SourceSans3-Semibold.ttf"
        ))),
    );
    fonts.families.insert(
        FontFamily::Proportional,
        vec![REGULAR_FONT.to_owned(), "NotoEmoji-Regular".to_owned()],
    );
    fonts.families.insert(
        FontFamily::Name(Arc::from("Source Sans 3 Semibold")),
        vec![SEMIBOLD_FONT.to_owned(), REGULAR_FONT.to_owned()],
    );
    ctx.set_fonts(fonts);
}

pub fn apply(ctx: &egui::Context, dark_mode: bool) {
    let colors = palette(dark_mode);
    let mut visuals = if dark_mode {
        egui::Visuals::dark()
    } else {
        egui::Visuals::light()
    };
    visuals.override_text_color = Some(colors.ink);
    visuals.window_fill = colors.surface;
    visuals.panel_fill = colors.canvas;
    visuals.faint_bg_color = colors.canvas;
    visuals.extreme_bg_color = colors.surface;
    visuals.code_bg_color = colors.surface_hover;
    visuals.hyperlink_color = colors.blue;
    visuals.warn_fg_color = colors.warning;
    visuals.error_fg_color = colors.failure;
    visuals.widgets.noninteractive.bg_fill = colors.surface;
    visuals.widgets.noninteractive.fg_stroke.color = colors.ink;
    visuals.widgets.inactive.bg_fill = colors.surface;
    visuals.widgets.inactive.fg_stroke.color = colors.ink;
    visuals.widgets.hovered.bg_fill = colors.surface_hover;
    visuals.widgets.hovered.fg_stroke.color = colors.ink;
    visuals.widgets.active.bg_fill = colors.selected_fill;
    visuals.widgets.active.fg_stroke.color = colors.ink;
    visuals.widgets.open.bg_fill = colors.surface_hover;
    visuals.widgets.open.fg_stroke.color = colors.ink;
    visuals.selection.bg_fill = colors.index_yellow;
    visuals.selection.stroke.color = colors.navy_dark;
    ctx.set_visuals(visuals);

    ctx.all_styles_mut(|style| {
        let regular = FontFamily::Proportional;
        let semibold = FontFamily::Name(Arc::from("Source Sans 3 Semibold"));
        let text_styles: BTreeMap<_, _> = [
            (TextStyle::Small, FontId::new(14.0, regular.clone())),
            (TextStyle::Body, FontId::new(16.0, regular.clone())),
            (TextStyle::Button, FontId::new(16.0, semibold.clone())),
            (TextStyle::Heading, FontId::new(26.0, semibold)),
            (
                TextStyle::Monospace,
                FontId::new(14.0, FontFamily::Monospace),
            ),
        ]
        .into();
        style.text_styles = text_styles;
        style.spacing.item_spacing = egui::vec2(12.0, 10.0);
        style.spacing.button_padding = egui::vec2(15.0, 10.0);
        style.spacing.interact_size = egui::vec2(40.0, 40.0);
        style.visuals.window_stroke.color = colors.line;
        style.visuals.widgets.noninteractive.bg_fill = colors.surface;
    });
}

#[cfg(test)]
mod tests {
    use super::{DARK, LIGHT, apply};
    use eframe::egui::{self, Color32, TextStyle};

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

    fn contrast(foreground: Color32, background: Color32) -> f64 {
        (luminance(foreground).max(luminance(background)) + 0.05)
            / (luminance(foreground).min(luminance(background)) + 0.05)
    }

    #[test]
    fn body_and_muted_text_meet_wcag_aa_in_both_themes() {
        for (name, palette) in [("light", LIGHT), ("dark", DARK)] {
            for (surface_name, surface) in
                [("canvas", palette.canvas), ("surface", palette.surface)]
            {
                assert!(
                    contrast(palette.ink, surface) >= 4.5,
                    "{name} body text on {surface_name} was {:.2}:1",
                    contrast(palette.ink, surface)
                );
                assert!(
                    contrast(palette.muted, surface) >= 4.5,
                    "{name} muted text on {surface_name} was {:.2}:1",
                    contrast(palette.muted, surface)
                );
            }
        }
    }

    #[test]
    fn status_text_meets_wcag_aa_in_both_themes() {
        for (name, palette) in [("light", LIGHT), ("dark", DARK)] {
            for (label, foreground, background) in [
                ("success", palette.success, palette.surface),
                ("warning", palette.warning, palette.warning_surface),
                ("failure", palette.failure, palette.surface),
                ("blue", palette.blue, palette.canvas),
                ("blue on surface", palette.blue, palette.surface),
                (
                    "selected navigation",
                    palette.selected_ink,
                    palette.selected_fill,
                ),
                ("navigation", palette.rail_ink, palette.navy_dark),
                (
                    "secondary navigation",
                    palette.rail_muted,
                    palette.navy_dark,
                ),
                ("subtle navigation", palette.rail_subtle, palette.navy_dark),
            ] {
                assert!(
                    contrast(foreground, background) >= 4.5,
                    "{name} {label} contrast was {:.2}:1",
                    contrast(foreground, background)
                );
            }
        }
    }

    #[test]
    fn primary_action_text_meets_wcag_aa_in_both_themes() {
        for palette in [LIGHT, DARK] {
            assert!(contrast(palette.primary_action_text, palette.navy) >= 4.5);
        }
    }

    #[test]
    fn theme_application_uses_readable_text_sizes_and_selected_mode() {
        let context = egui::Context::default();
        apply(&context, false);
        let light_style = context.global_style();
        assert!(!light_style.visuals.dark_mode);
        assert_eq!(light_style.text_styles[&TextStyle::Small].size, 14.0);
        assert_eq!(light_style.text_styles[&TextStyle::Body].size, 16.0);
        assert_eq!(light_style.text_styles[&TextStyle::Button].size, 16.0);

        apply(&context, true);
        let dark_style = context.global_style();
        assert!(dark_style.visuals.dark_mode);
        assert_eq!(dark_style.text_styles[&TextStyle::Small].size, 14.0);
        assert_eq!(dark_style.text_styles[&TextStyle::Body].size, 16.0);
    }
}
