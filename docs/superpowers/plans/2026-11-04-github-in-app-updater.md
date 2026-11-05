# GitHub In-App Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let desktop users check GitHub for a stable release, approve it, and install it in-app with signature verification and restart.

**Architecture:** Use Tauri's official signed updater plugin against a static manifest attached to the latest GitHub Release. React owns startup/manual check state, confirmation, and progress UI; Tauri performs platform installation and restart. Windows portable users receive a direct download link and replace the executable manually. GitHub Actions signs installer/update bundles and publishes the signatures and manifest.

**Tech Stack:** Tauri 2, Rust, React/TypeScript, npm, GitHub Actions, Python release scripts.

**Spec:** `docs/superpowers/specs/2026-11-04-github-in-app-updater-design.md`

## Global Constraints

- Support Windows NSIS, Linux AppImage, and the existing macOS app bundle distribution.
- For Windows portable builds, offer the portable executable download and explain how to replace the executable while retaining adjacent data files.
- The updater must verify signed artifacts; keep the private signing key only in GitHub Actions secrets and embed only its public key in app configuration.
- Check once at startup without blocking use, and provide a manual check in Settings.
- Never download or install before the user accepts the in-app offer.
- Update all release-version sources to v2.0.0. The release includes the v1.10.1 PDF-naming work and the signed updater.
- Existing v1.x installations require one manual v2.0.0 installation before in-app upgrades work.
- Preserve all unrelated local changes already present in the working tree.
- The user has requested completion verification; add focused regression tests and run the relevant project checks.

## Review Focus

- GitHub is unreachable at startup: the app remains usable and Settings can show the check failure.
- The latest stable version equals the installed version: report that the app is current and do not prompt.
- A release is missing a platform bundle or signature: fail closed and do not install it.
- The user chooses **Later**: do not start a download; leave manual checking available.
- The download or installation fails: show a readable error and do not report success or relaunch.
- The user runs the Windows portable build: provide the portable asset link and replacement instructions rather than launching the NSIS installer.

---

### Task 1: Configure the signed Tauri updater

**Files:**
- Modify: `desktop-ui/src-tauri/Cargo.toml`
- Modify: `desktop-ui/src-tauri/Cargo.lock`
- Modify: `desktop-ui/src-tauri/src/main.rs`
- Modify: `desktop-ui/src-tauri/tauri.conf.json`
- Modify: `desktop-ui/package.json`
- Modify: `desktop-ui/package-lock.json`

**Interfaces:**
- Register `tauri_plugin_updater`, `tauri_plugin_process`, and `tauri_plugin_opener` in the existing Tauri builder.
- Frontend uses `check`, `Update.downloadAndInstall`, `relaunch`, and the opener URL API from the official JS plugins.

- [ ] Add matching Tauri updater, process, and opener Rust/JavaScript plugin dependencies, updating lockfiles without changing unrelated dependency versions.
- [ ] Register the plugins and grant the main window only `updater:default`, `process:allow-restart`, and `opener:allow-open-url` scoped to the exact GitHub portable asset URL, in addition to its current permissions.
- [ ] Configure `createUpdaterArtifacts: true`, the stable `latest.json` GitHub Releases endpoint, and the public half of a newly generated persistent signing key. Keep the private key and passphrase out of the repository.

### Task 2: Add the consent-based update experience

**Files:**
- Modify: `desktop-ui/src/App.tsx`
- Modify: `desktop-ui/src/desktop.ts`
- Create: `desktop-ui/src/updater.ts`
- Modify: `desktop-ui/src/components/SettingsDialog.tsx`
- Create: `desktop-ui/src/components/UpdateDialog.tsx`
- Modify: `desktop-ui/src/styles.css`
- Modify: `desktop-ui/tests/fixtures.ts`
- Create: `desktop-ui/tests/updates.spec.ts`
- Modify: `desktop-ui/src-tauri/src/main.rs` and `desktop-ui/src-tauri/Cargo.toml` for deterministic portable-build detection.

**Interfaces:**
- `updater.ts` owns the Tauri `Update | null` and exposes typed check/install/open-portable-download functions, with a development QA bridge for rendered tests.
- App state owns the current version, check status, download progress, and user-facing error.
- `SettingsDialog` receives the installed version and a manual-check callback/status.
- `UpdateDialog` receives the available release, progress, install callback, and dismiss callback.

- [ ] Add the QA bridge methods and typed updater wrapper around Tauri's `check`, `downloadAndInstall`, `relaunch`, `openUrl`, `getVersion`, and the native portable-build flag.
- [ ] Add a single non-blocking startup check after the desktop snapshot loads; avoid concurrent checks and retain startup failures for display in Settings.
- [ ] Add a Settings section with the installed version and **Check for updates**, showing checking/current/available/error states.
- [ ] Show a confirmation with the version and release notes. **Later** dismisses without downloading; acceptance calls the updater download-and-install API, updates progress, then calls `relaunch` after success.
- [ ] Include a Windows portable download link to `TrainsDownloader-windows.exe` and explain how to replace the executable after closing the app while retaining files beside it.
- [ ] Keep the UI responsive and report network/download/install errors without closing the app or claiming the update succeeded.
- [ ] Add Playwright coverage for the startup offer, deferring without installation, an accepted update with progress/relaunch, the current-version state, manual check failure, and the portable download path; run the focused UI tests.

### Task 3: Publish signed update assets and the GitHub manifest

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `scripts/collect_desktop_packages.py`
- Modify: `scripts/build-desktop.ps1`
- Create: `scripts/build_update_manifest.py`
- Create: `tests/test_update_manifest.py`

**Interfaces:**
- Each platform package job emits its existing public download plus the installer updater artifact, `.sig`, and target architecture metadata. Keep the Windows portable executable as a separate public asset.
- The manifest builder consumes the merged release directory and release version, and writes `dist/release/latest.json` with exact `OS-ARCH` keys and signature contents.
- GitHub Actions supplies `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` only to the bundle-signing step.

- [ ] Extend package collection for the signed NSIS installer, AppImage updater artifact, and macOS `.app.tar.gz` updater artifact while preserving the existing public asset names.
- [ ] Record the architecture produced by each platform job so the manifest contains a matching platform entry for every published updater bundle.
- [ ] Build both Apple Silicon and Intel macOS packages; use architecture-specific updater archives and keep `TrainsDownloader-macos.dmg` for the Apple Silicon download.
- [ ] Build the Windows portable executable with the dedicated `portable` feature while retaining the regular NSIS installer build.
- [ ] Generate `latest.json` using versioned release download URLs and the contents of each signature file; fail manifest generation when a required platform artifact/signature is absent.
- [ ] Pass signing secrets only to the Tauri bundle step and include `latest.json` with the assets uploaded to the GitHub Release.
- [ ] Add isolated tests for package collection, target architecture metadata, manifest platform URLs/signatures, and missing-artifact rejection; run those Python tests.

### Task 4: Version and document the rollout

**Files:**
- Modify: `trains_app.py`
- Modify: `rust-ui/Cargo.toml`
- Modify: `desktop-ui/src-tauri/Cargo.toml`
- Modify: `desktop-ui/src-tauri/Cargo.lock`
- Modify: `desktop-ui/package.json`
- Modify: `desktop-ui/package-lock.json`
- Modify: `desktop-ui/src-tauri/tauri.conf.json`
- Modify: `README.md`
- Create: `docs/UPDATES.md`
- Create: `docs/releases/v2.0.0.md`

- [ ] Align every version source checked by `scripts/check_app_versions.py`, including lockfile package entries, at `2.0.0`, preserving the v1.10.1 PDF-naming release note in the README.
- [ ] Update the README version and document the startup/manual check, consent, and first-update experience.
- [ ] Document how to generate the Tauri signing key, keep a private backup, and add the private key and password to GitHub Actions secrets without placing either in the repository.
- [ ] Document that users on v1.x need one manual installation of v2.0.0; subsequent signed releases can install from the app.
- [ ] Run the release-version consistency check and the relevant Python, Rust, and frontend suites; record any platform-packaging checks that cannot run on this host.

## Coverage Review

- GitHub unavailable: Task 2 retains the startup error for Settings and keeps the app usable.
- Current release: Task 2 reports the no-update result.
- Missing/invalid platform metadata or signature: Task 3 fails manifest generation, and the signed updater rejects invalid signatures.
- User deferral: Task 2 keeps installation behind explicit consent.
- Download/install failure: Task 2 preserves an actionable error state and does not relaunch.

The completion audit requires running focused regression tests and the relevant existing suites after the feature is implemented.
