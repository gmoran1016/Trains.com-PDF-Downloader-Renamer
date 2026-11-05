# Design system

## Direction

**Annual Index** remains the approved direction: a clear contemporary archive index with cool surfaces, blue ink, a restrained yellow selection mark, and readable sans text. It is an Operate surface: complete a task, review its outcome, then continue. Publication coverage comes only from the Python scan.

The Tauri replacement uses one set of controls across Magazines, Track Plans, and Organize. The header contains account and appearance settings. Navigation has no decorative brand panel or footer. Workflow actions stay below the independently scrolling form. Activity occupies a compact strip while collapsed; new installations start collapsed.

## Tokens

| Role | Light | Dark |
|---|---|---|
| Canvas | `#f5f7f9` | `#111d28` |
| Surface | `#ffffff` | `#182633` |
| Main text | `#182b3a` | `#edf3f7` |
| Supporting text | `#526575` | `#b7c7d6` |
| Blue ink | `#23486e` | `#aacdeb` |
| Selection | `#fff4ce` | `#413c22` |
| Boundary | `#d7e0e7` | `#344859` |
| Failure | `#a72f36` | `#ffb2b5` |
| Success | `#226946` | `#9bd7b8` |
| Warning | `#80510e` | `#f1ca86` |
| Focus | `#2874b0` | `#79b9ef` |

Primary actions use white on `#23486e` in both themes. Status always has a label and icon. Inputs, selection, caret, focus rings, progress, and scrollbars share the palette. Native folder/file pickers and the title bar follow the operating system.

## Typography and assets

Source Sans 3 Regular and Semibold are bundled locally, with the original SIL Open Font License in `desktop-ui/src/assets/SourceSans3-OFL.txt`. Body and regular controls are 16 CSS px, secondary labels 14 px, headings 28 px (25 px in compact windows), and the brand 20 px. Text remains selectable; long paths can be edited and scroll inside their input.

The book/bookmark application icon was authored in `desktop-ui/assets/app-icon.svg`. Tauri's icon generator produces the desktop PNG, ICO, and ICNS files. Interface icons come from Lucide. No invented cover art or stock imagery is used.

## Layout

- Minimum client size: 640 × 480.
- Header: 64 px; 56 px in compact windows.
- Navigation: 194 px; 156 px below 1000 px. Below 720 px, three equal tabs occupy a 48 px row above the workspace.
- Form: independently scrollable, with a 1020 px maximum content width and 20–34 px horizontal inset. Sections use headings and spacing, without nested cards.
- Workflow actions: pinned outside the scroll area. Disabled actions retain clear labels; the form explains missing inputs where space permits.
- Activity: collapsed strip at least 54 px; expanded saved height is capped at 38% of client height (34% in compact tall windows). In short compact windows, a denser toolbar leaves at least one readable event row. Per-publication progress scrolls with the event area.
- Dialogs: constrained to client height, with a scrollable body and a fixed action area. Escape closes; focus returns to the invoking control.

The form may scroll in small windows. Navigation, primary actions, Activity toggle, and Stop remain within the client area. Expanding Activity never moves the workflow action over the form.

## Behavior

Job labels: Ready, Running, Complete, No results, Failed, Cancelled. Progress comes only from worker events. Stop remains available until the worker process has finished. Settings shown in the form must save before the next job starts. Failed saves remain visible and cannot silently use older options.

Organizer results retain every count, missing-issue row, and full report. Failed or cancelled scans keep their findings and do not offer Download Missing. That action requires a successful complete scan, one known publication, missing issues, and the same destination.

Activity shows local timestamps and renders 100 filtered events per page while Rust retains the full session. All activity and Needs attention share the same text search. Needs attention includes errors, conflicts, unreadable or unrecognized files, metadata warnings, and partial results. Copy log copies every matching event in chronological order, including full paths and details; Copy errors retains its separate error-only action. Both use the native clipboard.

Organize reports scanning, file processing, and issue coverage as distinct stages. Every processed file has one outcome row with its filename and an explicit action: Moved, Already organized, Conflict, Unreadable PDF, or Skipped. Paths and recovery advice are available under Details. Metadata warnings stay with the file outcome. Coverage and the closing count summary label cancelled or incomplete scans as partial; no missing-issue inference changes.

## Verification

Playwright covers both themes at 640×480, 800×620, 1120×760, and 1440×900, the loaded font, all job outcomes, workflow option mapping, keyboard dismissal/focus, cancellation, close choices, partial findings, and Activity controls. Rust checks preserve protocol, data, worker-exit, and settings behavior. Native Windows verification and platform packaging results are recorded separately in `docs/tauri-ui-verification.md`; browser fixtures alone are not evidence that a native package works.
