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
| Ink | `#192735` | Main text |
| Muted blue-gray | `#4C5E6F` | Supporting text |
| Canvas | `#F2F6F9` | Main work surface |
| Surface | `#FFFFFF` | Header, panels, and activity |
| Index yellow | `#FFCD40` | Selected index mark and key emphasis |
| Line | `#CBD7E0` | Panel and control boundaries |
| Success | `#226946` | Completed jobs |
| Warning | `#7D4B0A` | Warnings and cancellation |
| Warning surface | `#FFF5DA` | Warning message background |
| Failure | `#A33431` | Failed jobs and errors |
| Primary action text | `#FFFFFF` | Text on navy primary actions |

Hover, active, selected-row, selected-navigation, and rail text treatments use pale blue or warm yellow tints from the shared theme and shell. Status labels and symbols accompany semantic color. Theme tests check body, muted, status, navigation, and primary-action contrast against the surfaces where each appears.

Dark mode keeps the index yellow and navy identity while replacing the cool white work surface with a deep blue-gray canvas. It uses `#111B26` canvas, `#1B2835` panels, `#ECF2F7` main text, and `#BDCAD5` secondary text. Status colors lighten for dark surfaces and are tested separately. The header's Dark mode checkbox switches immediately and saves the preference in `settings.json`; older settings default to light mode.

## Typography

The UI bundles Source Sans 3 Regular and Semibold under its SIL Open Font License. Body and button text are 16 pt, compact labels are 14 pt, work-area headings are 26 pt, and the app title is 20 pt. Buttons and headings use the Semibold face; issue metadata remains Regular. No control, status, or navigation label uses text below 14 pt. Numeric values stay in aligned rows or grid columns.

## Layout and spacing

- Minimum client size: 640 × 480 px.
- Navigation rail: 208 px wide at 1000 px and wider; 156 px below 1000 px. The compact rail hides its brand and footer so all three work areas remain visible above Activity.
- Header and sticky workflow action area: 64 px each.
- Work-area content shares a 20 px horizontal inset with the sticky workflow actions, has a 980 px maximum width, and scrolls vertically in smaller windows.
- Activity: 220 px default height, 128–340 px expanded range, 48 px collapsed strip. In short windows, the expanded dock is capped to preserve at least 144 px for the scrollable work area after the header and workflow actions.
- Theme item spacing: 12 × 10 px; button padding: 15 × 10 px; interactive controls target at least 40 px.

At 640 × 480, the compact navigation keeps all three work areas visible, the page heading remains above its pinned action, and the work area scrolls vertically. Activity yields height to the main task view and keeps its status, filter, and stop controls within the window. The layout avoids horizontal scrolling and keeps the primary action anchored above Activity.

## Interaction and state

Use the standard controls provided by egui/eframe, including buttons, checkboxes, text inputs, combo boxes, keyboard focus, native folder dialogs, and system-tray actions. Job state is always labeled: Ready, Running, Complete, No results, Failed, or Cancelled. Progress advances only from worker events. A partial scan remains Failed while its findings stay available; Download Missing requires a complete scan and one unambiguous magazine target.

## Review evidence

The desktop UI harness checks idle and running layouts at 640 × 480, 800 × 620, and 1440 × 900 in both themes, including account controls, navigation, Activity actions, workflow action bounds, and compact-width controls. Fresh native-window captures are kept with the UI review evidence. No web detector runs because this is a native Rust UI with no HTML/CSS surface.
