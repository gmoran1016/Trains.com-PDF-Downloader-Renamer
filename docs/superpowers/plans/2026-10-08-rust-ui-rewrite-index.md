# Rust UI Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the user-facing PyQt UI with a fast Rust/eframe desktop app while preserving the Python engine and current user workflows.

**Architecture:** A headless, one-job Python worker speaks versioned JSON-lines to a Rust desktop app. The Rust app owns settings presentation, workflows, activity, tray behavior, and user-visible states; the Python engine remains the source of truth for download and organizer behavior.

**Tech Stack:** Python 3.13 in CI, PyQt5 QtCore worker threads, PyInstaller, Rust stable/edition 2024, eframe 0.36.2, serde/serde_json 1.x, rfd 0.17.2, tray-icon 0.26.0, egui_kittest 0.36.2.

**Spec:** [docs/rust-ui-design-spec.md](../../rust-ui-design-spec.md)

## Global Constraints

- The UI uses the Annual Index direction and the three approved work areas: Magazines, Track Plans, and Organize.
- Worker messages use JSON-lines protocol version 1; one worker process handles one job at a time.
- Outcomes are `idle`, `running`, `success`, `no-results`, `failed`, and `cancelled`; incomplete scans remain failures even with partial results.
- Existing settings and data files stay next to the running app and keep their existing formats.
- Cookie contents never enter worker messages, logs, Activity, process arguments, or test output; send the cookie-file path only.
- Tests use temporary data roots and fake workers; no live Trains.com login or user-library writes.
- Preserve the existing Windows/Linux/macOS package matrix and verify the Windows package locally.
- Preserve the existing uncommitted changes in README.md, tests/test_ui_smoke.py, trains_app.py, PRODUCT.md, and .impeccable/; inspect each before editing.
- Do not delete or broadly clean the existing `build/` or `dist/` directories.
- Existing top-level `dist/` contains user settings, cookies, progress, logs, and the current executable. Every local build must use fresh, collision-checked child directories under `build/` and `dist/`; set PyInstaller `--workpath`, `--distpath`, and `--specpath`, plus Cargo `--target-dir`. Never use defaults that write into top-level `dist/`.

## Review Focus

- Legacy settings with unknown keys or invalid JSON: retain unknown values and never overwrite the source file when parsing fails; pin in the Rust settings tests.
- Malformed, truncated, wrong-version, or wrong-job worker output: show a bounded failure and never leave the UI stuck; pin in Python and Rust protocol tests.
- Incomplete scans with partial matches: preserve the findings, show `failed`, and keep Download Missing disabled; pin in Python engine and Rust organizer tests.
- Cancellation during a download or organize pass: stop at a safe boundary, report completed work, and finish as `cancelled`; pin in Python worker tests.
- Paths containing spaces and non-ASCII characters, plus an extracted worker: keep all paths correct and data under the app's existing data directory; pin in worker and packaging tests.

---

## Sequenced Subplans

The subsystem plans are separate because their outputs can be reviewed independently; the protocol contract is the handoff between them.

1. [Python worker protocol and adapter](2026-10-08-rust-ui-python-worker.md) — establishes the JSON-lines contract and headless Python worker.
2. [Rust desktop application](2026-10-08-rust-ui-native-app.md) — builds the eframe UI against that contract, with a fake worker for deterministic interaction checks.
3. [Packaging and desktop QA](2026-10-08-rust-ui-packaging-and-qa.md) — bundles the worker, updates local and CI builds, and captures the required desktop evidence.

Execute the subplans in order. Do not start the Rust UI integration until the worker protocol and adapter tests pass. Update and inspect the release workflow, but do not execute it against GitHub or publish artifacts; build locally only.
