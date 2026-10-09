# Rust Desktop UI Design Spec

Historical specification for the egui implementation. The replacement desktop interface is described in [Tauri desktop design](superpowers/specs/2026-10-09-tauri-desktop-design.md); the workflow and data compatibility requirements remain binding.

**Status:** Approved; compatibility inventory clarified
**Scope:** Replace the user-facing PyQt interface with a Rust/eframe desktop app while retaining the Python download and organizer engine.

## Product promise

The app uses an authenticated Trains.com account to retrieve magazine issues and track plans, then validates and organizes those PDFs into the user's local library. Its first screen must make the three jobs—Magazines, Track Plans, and Organize—easy to find, while making the active job, its progress, and its final outcome unmistakable.

The UI is new work. It will not reuse the old PyQt layout, styling, or component structure. Existing behavior, settings, files, and release targets remain compatibility requirements.

## Direction contract

**THESIS:** A clear annual index is the visual language for a tool that retrieves and keeps a trustworthy local archive. The app keeps familiar desktop navigation and controls; it avoids both the generic metrics-and-log dashboard and a nostalgic paper replica.

**OWN-WORLD:** Use a cool, bright work surface, a broad deep-blue navigation rail and title band, and a warm yellow index mark for selection. Pair bundled Source Sans 3 Regular and Semibold with aligned issue counts, dates, and progress. Keep title rows compact and aligned; give status colors distinct, consistent meanings.

**STORY:** The user chooses one of three jobs, checks the correct source and destination, and starts it. Activity shows truthful progress, a stop action, and a distinct success, no-results, failure, or cancelled result. Organize retains useful partial findings after a failed scan without presenting them as a complete scan.

**FIRST VIEWPORT:** At 1440×900, a 208 px blue navigation rail lists Magazines, Track Plans, and Organize. A 64 px header identifies the selected work area, shows its current job state, and opens shared account settings. The remaining work area presents the task's controls and primary action. A shared Activity dock spans the bottom and can be resized. At 800×620, the rail narrows, task content scrolls vertically without horizontal overflow, and Activity can collapse to a one-line status strip.

**FORM:** The Model Railroader annual-index system ranked first of seven grounded cultural sources; it is Impeccable's pick. The direction seed is `ee530b99`. Its strongest signature is consistent year/issue indexing in organizer findings, where actual scan data supports it.

**Grounding reference:** [Trains.com's Model Railroader annual index](https://www.trains.com/mrr/magazine/annual-index/) demonstrates title-, author-, and subject-based retrieval, including a Track Plans subject category. This informs the index-first discipline; the UI will not reproduce the publication page or present invented issue data.

**FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Visual and interaction system

- **Color:** cool light canvas and white work surfaces; deep blue for the shell; yellow for selected index/navigation emphasis; dark ink for primary text; muted blue-gray for secondary text; green, amber, and red for success, warning, and failure. Never communicate state by color alone. Keep focus and selection visibly distinct from job outcome. Offer a persistent light/dark theme toggle with readable status colors in both modes.
- **Type:** bundle Source Sans 3 Regular and Semibold with the SIL Open Font License. Use 16-point body and button text, 14-point compact labels, and 26-point work-area headings. Avoid decorative display type and tiny all-caps labels.
- **Density:** clear section headings, aligned folder and option rows, compact publication selectors, and honest empty/loading/error states. No decorative charts, false data, paper texture, or oversized summary cards.
- **Controls:** use standard native buttons, checkboxes, text inputs, combo boxes, menus, folder pickers, focus behavior, and keyboard navigation. The annual-index world contributes type, palette, density, and the selected-index mark; it does not change navigation or turn controls into document props.
- **Motion:** keep window and panel interactions immediate. Use only brief state transitions that clarify a completed, running, or selected item; no looping ornament or progress animation unsupported by worker events.

## Information architecture

### Magazines

Show the existing magazine choices and selection state, the separate magazine destination folder, and the existing newest-first, include-specials, test-mode, and browser-visibility options. Keep the primary download action and stop action easy to reach. Retain **Clear Cache**: on explicit activation it removes only `download_progress.json` and `special_issues.json` from the established data directory and reports what it cleared. It never removes settings, cookies, or logs. Preserve current archive discovery, authenticated HTTP/browser fallback, issue filtering, resume/progress behavior, and incomplete-scan handling in the Python engine.

### Track Plans

Show the Track Plan Database source, its independent destination folder, and the scan/download action. Preserve authentication, original filenames, skip-existing behavior, progress, cancellation, and errors.

### Organize

Show source folder, destination folder, magazine-prefix choice, and the existing organizer browser option where applicable. After a run, show the full summary: moved, already-correct, unrecognized, corrupt, conflicts, metadata updates, report details, and missing issues by publication and year. Keep **Download Missing** disabled unless a completed scan identifies exactly one supported, unambiguous magazine target. An incomplete scan remains a failure; retain its partial findings for review, but do not offer a follow-up download based on incomplete coverage. The worker summary includes `scan_complete` so partial results cannot be mistaken for a complete index.

### Shared account settings

Provide one place to choose the cookie-file path and inspect whether that local file is present. Do not claim a session is authenticated until a worker confirms it. Preserve the existing headless preferences and cookie-path behavior. Never show cookie contents in the UI, worker protocol, Activity, or logs.

### Shared Activity

Provide a resizable bottom dock with current outcome, overall progress, per-magazine progress and ETA where available, searchable/filterable log lines, error count, Copy errors, Clear, and a stop action while a job is running. Keep all existing progress and errors available for the session until the user clears them. At 800×620, allow the dock to collapse while retaining the current status and an obvious way to reopen it.

## Job state and cancellation

Use the user-approved states: `idle`, `running`, `success`, `no-results`, `failed`, and `cancelled`. An incomplete archive or organizer scan is `failed`, even when the UI can display partial findings. `no-results` is a successful scan with no matching work, not a failure. Keep status text and iconography alongside semantic color.

The Rust UI remains responsive while Python work runs in its own process. Stop is cooperative: the worker stops at the next safe boundary, reports completed work and any partial organizer summary, then returns `cancelled`. Completed file operations are not rolled back. Closing the window during any active job keeps the existing choices: Minimize to Tray, Stop & Quit, or Cancel. The tray retains Show Window and Quit.

## Rust/Python boundary

- Build a Rust/eframe UI and a bundled Python worker. Start a fresh worker process for one job at a time; Python remains the source of truth for downloads, metadata, conflicts, missing-issue detection, PDF validation, and file organization.
- Use versioned JSON-lines on worker stdin/stdout. Each request carries a protocol version, job kind, and the settings required for that job. Events carry log, progress, status, and error updates. One final response carries the canonical outcome and job summary. Reserve stdout for protocol records; keep diagnostics off the protocol stream.
- Send the cookie-file path only. Cookie values must never be serialized or logged. Do not place credentials in process arguments, error details, Activity, or Rust logs.
- Read process output and cancellation input off the UI thread. Batch UI updates without dropping worker events. A worker crash, malformed protocol record, or unsupported version becomes a visible failure with a concise recovery message.
- Keep the current app data directory policy: settings, cookie file, download progress, special-issue data, and logs remain next to the running app as they do today. Do not silently move, reset, or overwrite those files. Preserve unrecognized settings keys when saving the shared settings file.
- Bundle the Python runtime/worker into each standalone Windows, Linux, and macOS release so the user does not install Python. Preserve the existing Chrome/ChromeDriver behavior required by the engine.

## Settings and compatibility

Read and write the existing settings keys without renaming or changing their meanings: `base_dir`, `track_plans_dir`, `cookies_path`, `headless`, `test_mode`, `newest_first`, `include_specials`, `selected_magazines`, `org_src`, `org_dst`, `org_prefix`, and `org_headless`. New UI-only preferences such as window size, selected work area, and Activity dock size may be added without relocating existing data.

The following files stay in their current data directory and retain their existing formats: `settings.json`, `session_cookies.json`, `download_progress.json`, and `special_issues.json`. Keep their existing readers/writers. The intentional Clear Cache action may remove only `download_progress.json` and `special_issues.json` after the user activates it. Do not read or expose the cookie file during UI development or tests.

## Accessibility and performance

- Support keyboard navigation, visible focus, useful accessible names and roles, and screen-reader-readable job outcomes. Do not rely on color alone.
- Keep the UI event loop free of file, network, and worker waits. Do not block a frame while launching or stopping a process. Read and render logs efficiently while retaining complete session output until Clear.
- Preserve a usable layout at 1440×900 and 800×620, and keep the 640×480 minimum window usable. Check idle and running states in both themes; avoid clipped primary actions, overlapping controls, and horizontal scrolling.

## Verification scope

- Keep the existing Python engine tests.
- Add Rust settings/state tests and JSON-lines worker protocol/integration checks using temporary folders and a fake worker.
- Replace the PyQt-only UI smoke checks with real Rust desktop screenshot and interaction checks at 1440×900 and 800×620, including the 640×480 minimum window in layout coverage. Cover all three work areas, account/settings persistence, Activity resizing/collapse, running progress/stop, and success, no-results, failed, and cancelled states.
- Build the Windows desktop package locally. Keep CI package builds for Windows, Linux, and macOS.
- No test may use a live Trains.com login or alter the user's library, settings, cookie file, progress file, special-issue file, or log. Use temporary data roots and a fake worker.

## Acceptance criteria

1. The Rust app opens as a responsive desktop UI with the approved Annual Index direction and all three work areas.
2. Every existing download, track-plan, organizer, metadata, conflict, missing-issue, cache-clearing, settings, progress, tray, and close-flow behavior remains available through the Python engine.
3. Existing data files remain at their current paths and retain their formats; cookie values never appear in logs or protocol messages.
4. Worker failures, incomplete scans, no-results, success, and cancellation are distinct and visible. Partial results survive failed scans without becoming success.
5. The approved local tests, screenshots, interactions, Windows package build, and cross-platform CI workflow provide evidence for release readiness.

## Working-tree preservation

The repository already contains uncommitted changes in `README.md`, `tests/test_ui_smoke.py`, and `trains_app.py`, plus the existing `.impeccable/` setup and `PRODUCT.md`. Treat all of that as pre-existing work: inspect before editing, retain its Track Plans and partial-scan behavior, and never discard or broadly stage unrelated files.
