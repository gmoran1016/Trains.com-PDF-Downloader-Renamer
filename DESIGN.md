# Design system

## Direction

The UI follows the **Annual Index** direction (seed `ee530b99`): a modern, clear archive index with cool white surfaces, deep blue navigation, a bright yellow index mark, compact issue metadata, and crisp sans-serif text. The reference is Trains.com's Model Railroader annual index; the app uses its retrieval discipline without copying the publication page or inventing coverage data.

This is an **Operate** surface. Magazines, Track Plans, and Organize have equal standing in the left navigation. The shared header keeps account access and current job state visible. The bottom Activity dock stays available across work areas and can be resized or collapsed.

## Palette

| Token | Value | Use |
|---|---|---|
| Navy | `#1E385B` | Navigation rail and primary actions |
| Deep navy | `#172C48` | Strong text on pale selected navigation |
| Blue | `#2C5B8B` | Section labels and running state |
| Ink | `#1D2B3A` | Main text |
| Muted blue-gray | `#5C6D7E` | Supporting text |
| Canvas | `#EFF4F7` | Main work surface |
| Surface | `#FFFFFF` | Header, panels, and activity |
| Index yellow | `#FFCD40` | Selected index mark and key emphasis |
| Line | `#D5DEE5` | Panel and control boundaries |
| Success | `#28734F` | Completed jobs |
| Warning | `#9B5B10` | Warnings and cancellation |
| Warning surface | `#FFF6E1` | Warning message background |
| Failure | `#AF423F` | Failed jobs and errors |
| Primary action text | `#FFFFFF` | Text on navy primary actions |

Hover, active, selected-row, selected-navigation, and rail text treatments use pale blue or warm yellow tints from the shared theme and shell. Status labels and symbols accompany semantic color. The warning text token was darkened after the finish review found insufficient contrast; the Rust theme test checks it against the canvas, surface, and warning surface.

## Typography

The Rust UI uses egui's proportional sans-serif family. With the shipped epaint 0.36.2 defaults, this resolves to the bundled Ubuntu Light font across the supported desktop systems; the app does not load a different system font per OS. The title is 20 px and work-area headings are 28 px. Small labels support compact issue and publication metadata. Numeric values stay in aligned rows or grid columns; the current eframe theme does not request tabular numeral glyphs.

## Layout and spacing

- Minimum client size: 640 × 480 px.
- Navigation rail: 208 px wide at wider sizes and 156 px below 1000 px.
- Header and sticky workflow action area: 64 px each.
- Work-area content shares a 20 px horizontal inset with the sticky workflow actions, has a 980 px maximum width, and scrolls vertically in smaller windows.
- Activity: 190 px default height, 112–340 px expanded range, 48 px collapsed strip. In short windows, the expanded dock is capped to preserve at least 208 px for the work area after the header and workflow actions.
- Theme item spacing: 10 × 9 px; button padding: 13 × 8 px.

At 640 × 480, the navigation rail uses its compact width, the work-area heading remains visible above the pinned action, and longer forms scroll. Activity stays visible and yields height to preserve a useful work area. The layout avoids horizontal scrolling and keeps the primary action anchored above Activity.

## Interaction and state

Use the standard controls provided by egui/eframe, including buttons, checkboxes, text inputs, combo boxes, keyboard focus, native folder dialogs, and system-tray actions. Job state is always labeled: Ready, Running, Complete, No results, Failed, or Cancelled. Progress advances only from worker events. A partial scan remains Failed while its findings stay available; Download Missing requires a complete scan and one unambiguous magazine target.

## Review evidence

The saved native eframe captures are [wide](.impeccable/review/desktop-wide-1440x900.png) at 1440 × 900 and [compact](.impeccable/review/desktop-compact-800x620.png) at 800 × 620. They predate the 640 × 480 minimum-window adaptation, the shared work-area inset, and the final text-contrast adjustments. Geometry is covered by the desktop UI harness at 640 × 480, 800 × 620, and 1440 × 900; these checks do not replace a fresh native-window capture. No web detector ran because this is a native Rust UI with no HTML/CSS surface.
