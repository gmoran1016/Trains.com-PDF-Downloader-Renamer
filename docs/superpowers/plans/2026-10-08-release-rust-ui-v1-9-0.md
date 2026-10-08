# Rust Desktop UI v1.9.0 Release Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the prepared native Rust desktop application and Track Plans workflow as v1.9.0, then verify the Windows, Linux, and macOS release builds.

**Architecture:** Keep the existing Python downloader and organizer as a bundled worker behind the Rust desktop app. Align the Python, Cargo, lockfile, and README versions, run the isolated local Windows package, then push the reviewed change set to `main` so the existing GitHub Actions matrix builds and publishes v1.9.0.

**Tech Stack:** Python 3.13 CI, PyInstaller, Rust stable, Cargo, eframe, pytest, GitHub Actions.

**Spec:** `docs/rust-ui-design-spec.md`; packaging details and artifact constraints in `docs/superpowers/plans/2026-10-08-rust-ui-packaging-and-qa.md`.

## Global Constraints

- The user explicitly authorized pushing this release to GitHub and asked for a new version build.
- Use v1.9.0 because v1.8.6 is the latest published version and this change adds the Rust desktop UI and a Track Plans workflow.
- Preserve the existing dirty Rust UI rewrite and stage its related source, tests, build workflow, and documentation; do not stage unrelated files.
- Preserve `session_cookies.json`, settings, progress, logs, downloaded files, and every existing file under `build/` and `dist/`.
- Keep Python `APP_VERSION`, Cargo package version and lockfile package version, README version, and release tag aligned.
- Keep the Windows, Linux, and macOS build matrix and existing release asset names.

## Review Focus

- Version drift between app metadata and the tag must fail before publication.
- Existing runtime state and build outputs must remain ignored and unmodified by local packaging.
- Worker packaging and app startup must be covered by the local Windows build and its smoke checks.
- The GitHub workflow must complete all three platform jobs and publish all three uniquely named assets to v1.9.0.
- The staged changes must include the prepared application and documentation but no cookies, settings, logs, or build output.

---

### Task 1: Finalize release metadata and documentation

**Files:**
- Modify: `trains_app.py`
- Modify: `rust-ui/Cargo.toml`
- Modify: `rust-ui/Cargo.lock`
- Modify: `README.md`
- Review: `.gitignore`, `.github/workflows/build.yml`, `build.bat`

- [x] **Step 1: Confirm the release candidate and artifact exclusions.** Verify the pending Rust UI files are within the release scope and the cookie, settings, logs, and current `build/` and `dist/` trees remain ignored.
- [x] **Step 2: Set the shared application version to 1.9.0** in Python, Cargo, Cargo.lock, and README.
- [x] **Step 3: Run the app-version check and `git diff --check`.** Expected: all app versions match and the whitespace check exits successfully.
- [x] **Step 4: Review the README and `.gitignore` against the current app and isolated build flow.** Keep or correct their existing prepared updates; document only behavior present in the release candidate.

### Task 2: Verify the local Windows release package

**Files:**
- Use: `build.bat`, `scripts/smoke_test_worker.py`, `scripts/verify-rust-release.ps1`

- [x] **Step 1: Run `build.bat`** using the project virtual environment and installed Rust toolchain. Expected: the complete Python and Rust checks pass, a fresh run-specific package is built, the worker smoke succeeds, and the packaged app opens and exits cleanly.
- [x] **Step 2: Confirm the printed executable exists in the fresh `dist/rust-ui-*` folder and the pre-existing output folders remain untouched.**

### Task 3: Review, commit, and push the release

**Files:**
- Stage only the release candidate files verified in Tasks 1 and 2.

- [x] **Step 1: Review the complete staged diff and verify no runtime or generated build data is included.**
- [ ] **Step 2: Commit the release candidate** with a message describing the Rust desktop UI and Track Plans workflow.
- [ ] **Step 3: Push the commit to `origin/main`**, as explicitly authorized by the user.

### Task 4: Verify GitHub Actions and release assets

**Files:**
- Verify: `.github/workflows/build.yml`

- [ ] **Step 1: Follow the Actions run for the pushed commit to a terminal result.** Expected: Windows, Linux, and macOS matrix jobs all succeed.
- [ ] **Step 2: Inspect GitHub release v1.9.0.** Expected: it contains `TrainsDownloader-windows.exe`, `TrainsDownloader-linux`, and `TrainsDownloader-macos`.
- [ ] **Step 3: Record local verification, commit SHA, workflow run, and asset results in this plan.**
