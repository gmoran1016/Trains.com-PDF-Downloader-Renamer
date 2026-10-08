# Rust Desktop Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete native Rust UI for magazine downloads, track plans, organizing, shared account settings, and Activity.

**Architecture:** An `eframe::App` owns presentation and state; focused modules own settings, protocol events, job execution, and each workflow page. The app can use a fake worker in tests and the real sibling worker in the packaged application.

**Tech Stack:** Rust stable, edition 2024, eframe 0.36.2 ([docs](https://docs.rs/eframe/0.36.2/eframe/)), serde/serde_json 1.x, rfd 0.17.2 ([docs](https://docs.rs/rfd/0.17.2/rfd/)), tray-icon 0.26.0 ([docs](https://docs.rs/tray-icon/0.26.0/tray_icon/)), egui_kittest 0.36.2 ([docs](https://docs.rs/egui_kittest/0.36.2/egui_kittest/)).

**Spec:** [design spec](../../rust-ui-design-spec.md). The protocol contract is authored in Task 1 of the [Python worker plan](2026-10-08-rust-ui-python-worker.md).

## Global Constraints

- `rust-ui/Cargo.toml` is version `1.8.6`, edition `2024`; commit `Cargo.lock` for reproducible Windows/Linux/macOS builds.
- Use eframe 0.36.2 with its default AccessKit support; use egui_kittest 0.36.2 with its `eframe` feature for deterministic UI interaction checks. Use `tempfile = 3` for app-owned worker extraction and isolated tests.
- Use the existing settings keys and app data directory; preserve unknown settings values when saving.
- Keep worker process I/O and folder traversal off the UI event loop.
- Use protocol v1 from `docs/worker-protocol-v1.md`; malformed or mismatched records become visible failures.
- Never serialize or log cookie contents; tests use temporary roots and a fake worker.
- Match the Annual Index direction and approved screen composition in `docs/rust-ui-design-spec.md`.

## Review Focus

- Invalid legacy JSON must not be overwritten; show defaults and a recovery notice while retaining the original bytes.
- A worker that exits, sends malformed JSON, or never sends `completed` must end in visible failure, not an infinite spinner.
- `failed`, `cancelled`, `no-results`, and `success` must remain distinct in model state and rendered labels.
- Long paths and labels at 800×620 must remain readable, reachable by keyboard, and free of horizontal overflow.
- Missing-issue action availability must require a completed, unambiguous result; partial failed summaries remain visible.

---

### Task 1: Create the eframe crate and state model

**Files:**
- Create: `rust-ui/Cargo.toml`, `rust-ui/Cargo.lock`, `rust-ui/src/main.rs`, `rust-ui/src/lib.rs`, `rust-ui/src/app.rs`, `rust-ui/src/model.rs`, `rust-ui/src/theme.rs`
- Create: `rust-ui/tests/state_tests.rs`
- Create: `rust-ui/examples/desktop_smoke.rs`

**Interfaces:**
- `AppPage::{Magazines, TrackPlans, Organize}`.
- `JobOutcome::{Idle, Running, Success, NoResults, Failed, Cancelled}`.
- `JobState { outcome: JobOutcome, message: String, done: Option<u64>, total: Option<u64>, per_magazine: BTreeMap<String, MagazineProgress>, summary: Option<serde_json::Value>, logs: Vec<LogEntry>, errors: Vec<LogEntry>, stop_requested: bool }`; `MagazineProgress` stores `done` and `total` only, while the existing ETA remains the worker's human-readable status message.
- `TrainsApp::new(data_dir: PathBuf, worker: Box<dyn WorkerLauncher>) -> TrainsApp`.

- [x] **Step 1: Create the minimal Cargo manifest and write `outcome_labels_distinguish_all_six_states` and `startup_selects_magazines` tests against the missing model API.**
- [x] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml` and confirm compilation fails because the state types and app are absent.**
- [x] **Step 3: Add the crate with `eframe = 0.36.2`, `serde = 1`, `serde_json = 1`, and `tempfile = 3`; add the six-state model and a minimal app that opens at 1120×760 with an 800×620 minimum. Add `egui_kittest = 0.36.2` with the `eframe` feature as a development dependency and a `desktop-smoke` feature for the fake-worker example.**
- [x] **Step 4: Run `cargo fmt --manifest-path rust-ui/Cargo.toml --check` and `cargo test --manifest-path rust-ui/Cargo.toml`; confirm state tests pass.**

### Task 2: Read and persist the existing settings

**Files:**
- Create: `rust-ui/src/settings.rs`
- Modify: `rust-ui/src/app.rs`
- Create: `rust-ui/tests/settings_tests.rs`

**Interfaces:**
- `Settings::load(data_dir: &Path) -> SettingsLoad`, where `SettingsLoad` includes the parsed settings and a nonfatal parse error if the file is invalid.
- `Settings::save(&self, data_dir: &Path) -> Result<(), SettingsError>`.
- `Settings` includes the existing 12 named keys, UI-only `selected_page`, `window_width`, `window_height`, `activity_height`, and `activity_collapsed` preferences, plus an `extra: BTreeMap<String, serde_json::Value>` for unknown keys. New preferences use defaults when absent; unknown values survive saves.

- [x] **Step 1: Write `loads_existing_settings_keys`, `preserves_unknown_keys_on_save`, `invalid_json_is_not_overwritten`, and `round_trips_unicode_paths` tests using `tempfile` data roots.**
- [x] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml settings_tests` and confirm the tests fail.**
- [x] **Step 3: Implement tolerant settings loading, safe defaults, preservation of unknown keys, and a save path that does not truncate the existing file on serialization or write failure.**
- [x] **Step 4: Run the settings tests and confirm they pass.**

### Task 3: Add the asynchronous worker client

**Files:**
- Create: `rust-ui/src/worker.rs`
- Modify: `rust-ui/src/app.rs`, `rust-ui/src/model.rs`
- Create: `rust-ui/tests/worker_tests.rs`

**Interfaces:**
- `WorkerLauncher::start(request: WorkerRequest, data_dir: PathBuf) -> Result<WorkerHandle, WorkerError>`.
- `WorkerHandle::try_recv() -> Vec<WorkerEvent>`, `request_cancel() -> Result<(), WorkerError>`, and `poll_exit() -> Option<ExitStatus>`.
- Worker request/event types match protocol v1. Read stdout and stderr on background threads; validate `v` and `job_id` before applying events.

- [x] **Step 1: Add a fake worker fixture and tests named `worker_events_do_not_block_ui`, `wrong_version_and_job_id_fail`, `crash_before_completed_fails`, `cancel_sends_v1_command`, and `cookie_value_is_never_forwarded`.**
- [x] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml worker_tests` and confirm the tests fail.**
- [x] **Step 3: Implement the process client and a `desktop-smoke`-only fake `WorkerLauncher`; do not pass cookie contents, and do not update `TrainsApp` from the reader threads directly.**
- [x] **Step 4: Run the worker tests and confirm event ordering, cancel delivery, and failure handling pass.**

### Task 4: Build the shell, Magazine page, and Track Plans page

**Files:**
- Create: `rust-ui/src/ui/mod.rs`, `rust-ui/src/ui/shell.rs`, `rust-ui/src/ui/magazines.rs`, `rust-ui/src/ui/track_plans.rs`
- Modify: `rust-ui/src/app.rs`, `rust-ui/src/theme.rs`
- Create: `rust-ui/tests/workflow_ui_tests.rs`

**Interfaces:**
- The shell provides the 208 px deep-blue rail, 64 px title band, shared Account control, three labeled work areas, and resizable/collapsible Activity slot from the spec.
- Magazine metadata mirrors Python's five current titles; job options retain `base_dir`, `selected_magazines`, `newest_first`, `include_specials`, `test_mode`, `headless`, and `cookies_path`.
- Track Plans uses `track_plans_dir` and `cookies_path` only; never reuses the magazine folder.

- [x] **Step 1: Write UI tests `navigation_switches_work_areas`, `magazine_options_map_to_protocol_v1`, `track_plans_uses_separate_destination`, and `clear_cache_removes_only_progress_and_special_files` with a temporary data root.**
- [x] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml workflow_ui_tests` and confirm the tests fail.**
- [x] **Step 3: Implement the shell and both workflow pages with standard egui controls, native folder selection through rfd 0.17.2, explicit labels, and the Annual Index palette/type/density. Make Clear Cache delete only `download_progress.json` and `special_issues.json` after activation.**
- [x] **Step 4: Run the workflow UI tests and confirm all folder, option, and cache boundaries pass.**

### Task 5: Build Organizer, Account settings, and Activity

**Files:**
- Create: `rust-ui/src/ui/organize.rs`, `rust-ui/src/ui/account.rs`, `rust-ui/src/ui/activity.rs`
- Modify: `rust-ui/src/ui/mod.rs`, `rust-ui/src/app.rs`, `rust-ui/src/settings.rs`
- Modify: `tests/test_ui_smoke.py` only after the Rust equivalents pass

**Interfaces:**
- Organizer state displays all `OrganizeSummary` fields from the Python result and retains partial summaries on `failed`/`cancelled`.
- `can_download_missing(summary, outcome) -> bool` returns true only for a complete successful scan with one supported magazine target.
- Account settings use `cookies_path`; current browser-visibility preferences remain in their existing keys.
- Activity owns filter text, full session log entries, error count, Copy errors, Clear, per-magazine progress and the worker's existing ETA/status message, dock height, collapse, and stop action. Stop is shown as a request until the worker acknowledges cancellation with its terminal event.

- [ ] **Step 1: Write `organizer_shows_complete_summary`, `missing_download_requires_single_complete_target`, `activity_filters_and_copies_errors`, `activity_resize_persists`, `stop_changes_only_after_worker_ack`, `account_settings_round_trip`, and `primary_controls_have_accessible_labels` interaction tests.**
- [ ] **Step 2: Run the named `egui_kittest` tests and confirm they fail before implementation.**
- [ ] **Step 3: Implement Organizer, Account, and Activity; keep keyboard focus, accessible labels, non-color state cues, complete logs, and nonblocking updates.**
- [ ] **Step 4: Run the UI tests. After their Rust coverage passes, replace obsolete PyQt-only assertions in `tests/test_ui_smoke.py` with the Rust interaction/screenshot suite; leave `tests/test_trains_app.py` intact.**
- [ ] **Step 5: Run `python -m pytest tests/test_trains_app.py -q` and `cargo test --manifest-path rust-ui/Cargo.toml`; confirm engine and Rust UI tests pass.**

### Task 6: Add tray, close choices, and viewport interaction checks

**Files:**
- Create: `rust-ui/src/tray.rs`, `rust-ui/tests/desktop_ui_tests.rs`
- Modify: `rust-ui/src/main.rs`, `rust-ui/src/app.rs`, `rust-ui/Cargo.toml`

**Interfaces:**
- Tray actions are `Show Window` and `Quit`; close while running offers `Minimize to Tray`, `Stop & Quit`, and `Cancel`.
- Use tray-icon 0.26.0; use its KSNI backend on Linux to avoid requiring GTK/AppIndicator runtime libraries.
- Use egui_kittest 0.36.2 to exercise the actual `TrainsApp` at 1440×900 and 800×620.

- [ ] **Step 1: Write `close_idle_exits`, `close_running_cancel_keeps_window`, `close_running_minimize_keeps_worker`, `close_running_stop_waits_for_worker`, `keyboard_reaches_primary_actions`, `desktop_layout_1440x900`, and `desktop_layout_800x620` checks.**
- [ ] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml desktop_ui_tests` and confirm the interactions/layout checks fail.**
- [ ] **Step 3: Implement the cross-platform tray and close state handling; maintain one job at a time and request a cooperative stop before quitting.**
- [ ] **Step 4: Run desktop UI tests at both sizes and confirm all primary actions, labels, and panels remain reachable without horizontal overflow.**
