# Tauri desktop UI implementation plan

> Execute inline with superpowers:executing-plans. Use a final independent review.

Goal: replace the flawed egui UI with a cohesive desktop interface without changing engine behavior.

Architecture: a toolkit-independent Rust controller retains the strict worker client and settings compatibility. A Tauri shell exposes narrow commands and batched snapshots to React. Existing Python is embedded unchanged.

Tech stack: Tauri 2, React, TypeScript, Vite, Radix dialog primitives, shared shadcn-style controls, Playwright, Rust and Python.

Spec: docs/superpowers/specs/2026-10-09-tauri-desktop-design.md

## Global constraints

- Preserve worker protocol v1, existing settings keys and unknown settings fields.
- Preserve all three workflows, missing-issue safety, full session history, cooperative cancellation and running-close choices.
- Never read cookie contents in UI development or tests; all QA uses isolated roots.
- Minimum desktop client size 640x480; both themes, long strings, keyboard access, saved large Activity sizes must fit.
- Do not publish a new release until the replacement is verified.

## Review focus

- Startup/worker-exit races: one job only, stop during launch, terminal events do not release a still-running process.
- Partial organizer scans: useful report retained, follow-up downloads rejected.
- Settings errors/unknown keys: original files preserved, never silently reset.
- All window/panel sizes: content scrolls; action, navigation and Stop remain reachable.
- Platform packaging: embedded worker, WebView dependencies, data locations and tray failure paths.

### Task 1: Toolkit-independent controller

- [x] Add controller tests for protocol mapping, partial-scan gating, stop/start lifecycle, settings preservation and bounded activity access; observe failure before implementation.
- [x] Reuse worker parsing/bundling and settings; replace egui repaint with a toolkit-independent notification callback. Remove the egui entry point and its UI-only tests.
- [x] Implement controller with truthful outcomes, full logs and safe job requests; retain worker/state/settings tests. Expected: core tests and lint pass without eframe dependencies.

### Task 2: Tauri desktop shell

- [x] Add commands for snapshots/settings/jobs/activity/cache/file pickers and close choices.
- [x] Add tray, isolated data-root override and verification-only fake worker feature; bundle Python via the existing core embedding.
- [x] Expected: the Windows shell builds and starts with the real packaged worker available.

### Task 3: React interface

- [x] Implement shared controls, adaptive navigation, three workflow forms, organizer findings, settings, Activity and all job states.
- [x] Add rendered interaction checks for workflow/settings mapping, missing gating, cancel, errors, keyboard and layout sizes; inspect screenshots in one batch and fix findings together.
- [x] Expected: no overlap/clipping/horizontal overflow or console errors at supported sizes; inputs and actions are usable.

### Task 4: Packaging and completion

- [x] Replace build entry points/CI with Tauri packaging; keep existing Python tests and worker smoke checks.
- [x] Align version surfaces, update README/PRODUCT/DESIGN, build local Windows release and check isolated startup.
- [ ] Obtain independent review, fix material findings, record verification and provide the runnable result.
