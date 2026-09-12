# Trains.com Downloader UI Redesign

**Date:** 2026-09-12  
**Scope:** Replace the PyQt5 application shell and interaction layout while preserving downloader, archive, organizer, worker, settings, and tray behavior.  
**Status:** Design approved in chat; implementation awaits written-spec approval.

## Problem

The current window is a dense vertical form with a dark, low-contrast palette. Magazine controls, paths, options, authentication, progress, and logs compete for attention. At compact sizes, labels and controls become visually clipped, the log occupies too much space without explaining the current task, and the organizer's result state is represented almost entirely as text in the log.

The redesign must make the two core jobs obvious:

1. Download selected magazine archives into a known destination.
2. Organize local PDFs and, when appropriate, download the missing issues.

The user should always be able to answer: what task is selected, what will happen, where files will go, whether authentication is ready, what is running, and what happened when it finishes.

## Design direction

Use a light editorial “rail archive workstation” style:

- warm paper background for the window;
- ink/navy text with steel-blue navigation and borders;
- amber as the primary action color;
- green, red, and amber status colors used with text and icons, never color alone;
- flat surfaces with clear borders and restrained radius rather than nested dark cards;
- Segoe UI/system sans for interface text and a monospace face only for the activity log;
- no gradients, emoji controls, or decorative motion.

The visual hierarchy is action-first: page title and status, task-specific inputs, primary action, then supporting activity. Labels use normal sentence case and sufficient contrast; uppercase is reserved for small eyebrow metadata where it improves scanning.

## Window shell

`MainWindow` remains the application owner and keeps its current worker and settings attributes. Replace the current single-column layout with:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ monogram  Trains.com Archive             Ready / access status  v1.7 │
├───────────────┬──────────────────────────────────────────────────────┤
│ DOWNLOAD      │ Page title + short explanation                       │
│ ORGANIZE      │ task controls in a scrollable workspace              │
│ ACTIVITY      │                                                        │
│               │                                                        │
├───────────────┴──────────────────────────────────────────────────────┤
│ Activity drawer: filter, error count, copy errors, compact log        │
└──────────────────────────────────────────────────────────────────────┘
```

Implementation details:

- Default size: approximately 1040×760; minimum size: 800×620.
- A fixed-width navigation rail is paired with a `QStackedWidget` in the main workspace.
- Each page is inside a vertical `QScrollArea`; the content must remain usable when the window is reduced.
- A vertical `QSplitter` separates the page workspace and a compact activity drawer. The drawer is visible but short by default and can be expanded by dragging or by selecting Activity in the navigation rail.
- The header contains app identity, current version, a text status indicator, and an `Activity` toggle. It does not contain operational inputs.
- The existing system tray behavior and close-while-running decision dialog remain intact.

## Download page

### Header

Title: `Download magazines`  
Description: `Choose the publications and archive range to save locally.`

The header includes a compact state line such as `Ready to scan archive`, `Downloading 12 of 84`, `Complete`, or `Download failed`.

### Magazine selection

Replace cramped chip buttons with five full-width selectable rows. Each row contains:

- a 44px-or-larger check target;
- the full magazine title;
- its prefix (`MRR`, `TRN`, `CTT`, `CTR`, or `GRW`);
- schedule text (`Monthly`, `Quarterly`, or `Seasonal / archived`);
- a selected-state border and check mark that remain understandable without color.

Provide `Select all` and `Clear all` secondary actions above the list. Keep the existing `self.mag_chips` mapping for settings compatibility, but use checkboxes inside the new rows rather than the current text-only grid buttons.

### Destination

Use a labeled path card with a full-width editable path, a `Browse…` action, and a small helper line explaining the resulting folder structure. The path stays readable and does not get squeezed by adjacent controls.

### Advanced options

Put secondary settings inside a clearly labeled, expandable `Advanced options` panel:

- Include special issues (checked by default);
- Issue order: Newest first / Oldest first;
- Test mode;
- Hide download browser, with a note that saved cookies are required.

The panel is expanded on first launch only when it contains a non-default setting; otherwise it is collapsed to keep the primary flow short. All current setting keys remain persisted.

### Actions

Use a distinct action bar at the bottom of the download page:

- primary `Start download` button;
- secondary `Stop` button disabled until a worker is active;
- secondary `Clear cache` button;
- an inline validation/status area above the buttons for missing magazine selection or destination.

Buttons use verbs and sentence case. No icon is required for the action to be understood; if an icon is used, it comes from a consistent Qt/SVG line set and is paired with text.

## Organize page

Title: `Organize your PDFs`  
Description: `Rename, sort, validate, and report on an existing PDF folder.`

### Locations

Present source and destination as two clearly separated path cards. Each card has a visible label, helper text, editable field, and browse action. The destination card explicitly says that it may be the same as the source.

### Identification

Use a magazine identification card with:

- `Auto-detect` as the default;
- all five known prefixes as readable options;
- helper text explaining that a prefix is only needed when filenames do not identify the publication.

Keep the current prefix values and settings persistence unchanged.

### Actions and results

Use a primary `Organize PDFs` action and a disabled-until-valid `Download missing issues` action. Keep a contextual `Stop` action for the missing-issue worker.

After organizing, show a results summary panel above the activity drawer with visible count tiles for moved, already correct, unrecognized, corrupt, conflicts, and metadata updated. If missing issues are available for one identified magazine, show the missing count and the `Download missing issues` action there. If multiple publications are detected, show the existing safety message and do not offer an ambiguous download action.

The full report remains available in the activity drawer for inspection and copying.

## Archive access

Place one shared `Archive access` strip beneath the page header or at the top of each page's scrollable content, not in a visually detached footer. It contains:

- cookie file label and editable path;
- `Browse…` button;
- short subscription/login guidance;
- contextual browser visibility setting: download mode uses `headless_cb`, missing-issue organization uses `org_headless_cb`.

The cookie field remains the same setting and remains sensitive. Do not add credential storage or a new login protocol.

## Activity and status

The activity drawer keeps the current useful capabilities but gives them hierarchy:

- header: `Activity`, current job state, and error count;
- filter field;
- `Copy errors` and `Clear` actions;
- compact read-only monospace log;
- overall progress bar and status text above the log when a worker is active;
- per-magazine progress rows shown only during a multi-magazine download and hidden after completion.

The main page header and action bar must reflect the same worker state as the drawer. Completion states must distinguish success, cancellation, no results, and failure using both text and status styling.

## Interaction and accessibility requirements

- No horizontal clipping at 800×620, 1040×760, or 1440×900.
- All labels and helper text remain readable at the minimum size; long paths elide visually but remain editable and copyable.
- Keyboard order follows the visual order: navigation, page inputs, advanced options, access, action bar, activity controls.
- Every interactive control has an accessible name and visible focus state.
- Primary controls and check targets are at least 44 logical pixels high where practical.
- Selected state, error state, and progress state are not conveyed by color alone.
- Minimum body text is readable against the paper surface; muted text must still meet contrast requirements.
- Busy workers disable inputs that would invalidate the running task and expose a clear stop action.
- No layout-shifting hover transforms; transitions are limited to short color/opacity changes and respect reduced-motion preferences where Qt supports them.

## Implementation boundaries

### Change

- Replace `_STYLESHEET` with the new light workstation theme.
- Replace `_build_ui`, `_make_download_panel`, and `_make_organize_panel` with the shell, navigation, scrollable pages, access strip, activity drawer, and results summary.
- Add small UI-only helpers for path cards, magazine rows, section headings, status badges, and result tiles.
- Update UI slots only where widget visibility/state must be reflected in the new layout.
- Preserve existing public widget attributes used by worker slots and settings (`cookie_edit`, `dir_edit`, `mag_chips`, `headless_cb`, `org_headless_cb`, `sort_combo`, action buttons, progress/log fields) or provide explicit compatibility aliases.
- Update UI smoke tests to assert the new interaction model and render screenshots for manual visual inspection.

### Do not change

- `MagazineDownloader`, archive URL/link parsing, viewer download handling, cookie format, PDF parsing, organizer behavior, progress schema, or worker scheduling.
- The trains.com archive URLs or magazine identifiers.
- System tray semantics or close-while-running safety behavior.
- Existing settings keys and default values.

## Verification plan

1. Add/update UI tests before implementation for shell construction, navigation, magazine selection, scrollability, activity drawer behavior, progress state, organizer summary state, and accessible names.
2. Run the new focused UI tests and existing backend tests after each UI slice.
3. Launch the UI offscreen at 800×620, 1040×760, and 1440×900; capture screenshots outside the repository and inspect them for clipping, contrast, spacing, and hierarchy.
4. Exercise download and organize state transitions with deterministic workers/test doubles; verify no stale worker callbacks update the wrong page.
5. Run the full test suite, compile check, dependency check, and `git diff --check`.
6. Build the PyInstaller executable from the redesigned tree and run a packaged startup smoke test.

## Acceptance criteria

- A first-time user can identify the two workflows within two seconds and reach the primary action without scanning a dense form.
- All five magazines are fully readable and selectable at the minimum supported window size.
- The download flow makes destination, authentication expectations, options, and current status explicit.
- The organize flow presents its result counts and missing-issue decision without requiring the user to decode the log.
- Activity remains available without dominating the workspace.
- Existing archive/download/organizer tests remain green and the packaged executable starts successfully.
