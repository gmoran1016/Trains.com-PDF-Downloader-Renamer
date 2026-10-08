# Rust UI Packaging and Desktop QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce standalone Rust desktop builds with the Python worker bundled, update Windows and CI build paths, and verify the approved desktop experience.

**Architecture:** Build a one-file Python worker with PyInstaller, embed that binary into the Rust executable at build time, and extract it lazily into a unique temporary directory when the first job starts. Keep the existing single-file release names and app data paths.

**Tech Stack:** PyInstaller, Rust stable/Cargo, eframe 0.36.2, `include_bytes!`, tempfile 3, GitHub Actions Windows/Linux/macOS matrix, PowerShell desktop screenshot/interaction harness.

**Spec:** [design spec](../../rust-ui-design-spec.md). The protocol contract is authored in Task 1 of the [Python worker plan](2026-10-08-rust-ui-python-worker.md).

## Verified local build prerequisites

- `cargo` and `rustc` are not currently on `PATH`; install the stable Rust toolchain under the user profile before the approved Windows build, then verify both commands.
- The existing project `.venv` is available with Python 3.14.7. Use `.venv\Scripts\python.exe` for local Python tests and worker packaging; confirm the selected PyInstaller release supports that interpreter before building. CI remains pinned to Python 3.13.
- The current `build.bat` deletes top-level `build/` and `dist/`; replace those cleanup steps with isolated work output and `dist/rust-ui/` as specified below.

## Global Constraints

- Existing release executable names remain `TrainsDownloader-windows.exe`, `TrainsDownloader-linux`, and `TrainsDownloader-macos`.
- The worker is built before Cargo and embedded in the Rust executable; users do not install Python or download a second worker file.
- Worker extraction is lazy, uses an app-owned unique temp directory, and never writes to the app data directory.
- Preserve the existing app data location beside the running executable; no tests or build cleanup may touch the user's settings, cookie, progress, special-issue, log, or library files.
- Do not delete `build/` or `dist/`; use isolated output/work directories so pre-existing artifacts remain intact.
- The existing top-level `dist/` contains `settings.json`, `session_cookies.json`, `download_progress.json`, `trains_downloader.log`, and `TrainsDownloader.exe`. Every local build uses fresh, collision-checked child directories under `build/` and `dist/`; configure PyInstaller `--workpath`, `--distpath`, and `--specpath`, and Cargo `--target-dir`. Fail if a selected child path already exists; never clean or overwrite it.
- No release is published or pushed during this work.

## Review Focus

- A missing/unreadable embedded worker must produce a clear failure before starting a job; test the empty-worker development build.
- Extracted workers need executable permission on Unix and no visible console window on Windows; verify the local packaged launch path.
- If an app process starts twice, temp extraction directories must not collide or delete each other's workers; test unique paths and owned cleanup.
- Linux builds need the eframe system headers and KSNI tray backend without adding an unapproved runtime appindicator requirement.
- CI must fail on Python tests, Rust tests, formatting, clippy, or package failure before publishing artifacts.

---

### Task 1: Embed and extract the worker safely

**Files:**
- Create: `rust-ui/build.rs`, `rust-ui/src/worker_bundle.rs`
- Modify: `rust-ui/src/worker.rs`, `.gitignore`
- Create: `rust-ui/tests/worker_bundle_tests.rs`

**Interfaces:**
- Build-time environment variable `TRAINSDOWNLOADER_WORKER` points to the platform PyInstaller output; `build.rs` copies it into `OUT_DIR/worker.bin` before compilation.
- `extract_worker(data: &[u8], temp_root: &Path, version: &str) -> Result<ExtractedWorker, WorkerBundleError>` uses a uniquely created, app-owned `tempfile::TempDir`; `ExtractedWorker` retains its guard until the child exits.
- On Unix, set executable permission on the extracted file; on Windows, launch without opening a console window.
- If the embedded bytes are empty, show a development/release packaging error and do not create a child process.

- [x] **Step 1: Write `extracts_worker_to_unique_temp_path`, `empty_worker_is_rejected`, `worker_temp_is_removed_only_when_owned`, and `unix_extracted_worker_is_executable` tests.**
- [x] **Step 2: Run `cargo test --manifest-path rust-ui/Cargo.toml worker_bundle_tests` and confirm failures before the bundle code exists.**
- [x] **Step 3: Implement build-time embedding and lazy, per-process extraction; use the existing `tempfile = 3` dependency and ensure the Rust UI event loop is not blocked during the first extraction.**
- [x] **Step 4: Run worker-bundle tests and `cargo test --manifest-path rust-ui/Cargo.toml`; confirm both pass.**

### Task 2: Update the local Windows build without cleaning user artifacts

**Files:**
- Modify: `build.bat`
- Modify: `rust-ui/build.rs`

- [ ] **Step 1: Add a build-script check that an absent `TRAINSDOWNLOADER_WORKER` is allowed only for tests/development, and a release build rejects it.**
- [ ] **Step 2: Run the focused Rust build-script tests and confirm the release-mode missing-worker case fails as expected.**
- [ ] **Step 3: Check for stable `rustc` and `cargo`; if absent, install Rust stable under the user profile as setup for the approved Windows build. Change `build.bat` to report a clear setup message if the toolchain is still missing. Use the existing `.venv\Scripts\python.exe` for Python engine/worker tests; build the console-mode PyInstaller worker with explicit `--workpath`, `--distpath`, and `--specpath` inside a new, collision-checked `build/rust-ui-<run-id>/` directory. Set `TRAINSDOWNLOADER_WORKER`, set Cargo's target directory inside that same fresh workspace, and copy the release binary to a fresh `dist/rust-ui-<run-id>/` directory. Remove the old `rmdir /s /q build` and `dist` commands; do not delete or overwrite any existing output.**
- [ ] **Step 4: Run `build.bat`; confirm the release executable in the printed run-specific output directory opens and exits using its isolated data directory. Exercise the fake worker separately through the `desktop-smoke` example.**

### Task 3: Keep the cross-platform CI package matrix

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `README.md` after reviewing its existing uncommitted changes

- [x] **Step 1: Add CI checks for `python -m pytest tests/test_trains_app.py tests/test_worker_protocol.py tests/test_worker_integration.py -q`, `cargo fmt --check`, `cargo test`, and `cargo clippy --all-targets -- -D warnings`.**
- [x] **Step 2: Add Rust stable setup and Linux build dependencies required by eframe; keep the current Windows/Linux/macOS matrix.**
- [x] **Step 3: Build the PyInstaller worker first, set `TRAINSDOWNLOADER_WORKER`, then build each Rust release artifact under the existing names. Read the release version from Cargo.toml and assert it matches Python's `APP_VERSION`. Keep artifact publication behavior in the workflow unchanged; do not push or dispatch it here.**
- [x] **Step 4: Update the README launch instructions to explain the new Rust UI and that the Python worker is bundled; retain the Chrome requirement and first-sign-in behavior. Preserve all pre-existing README edits.**
- [x] **Step 5: Run the Python and Rust CI commands locally on Windows and inspect the workflow diff for all three platform entries.**

### Task 4: Capture real desktop screenshots and interactions

**Files:**
- Create: `scripts/desktop-smoke.ps1`
- Create: `.impeccable/review/desktop-wide-1440x900.png`, `.impeccable/review/desktop-compact-800x620.png`
- Modify: `rust-ui/tests/desktop_ui_tests.rs` only if a failing interaction reveals a defect

- [x] **Step 1: Configure the smoke harness to launch the actual eframe desktop-smoke example with a unique temporary data root and deterministic fake worker; keep magazine, track-plan, cookie, and organizer paths inside that root so it cannot use the real cookie path or write to user library folders.**
- [x] **Step 2: Exercise the native UI behavior with `egui_kittest` at 1440×900 and 800×620, covering Magazines, Track Plans, Organize, Account settings, Activity resize/collapse, success, no-results, failed, cancelled, and stop. Review the existing real eframe window captures at both sizes. Windows UI Automation was blocked by Defender; do not bypass it. This leaves the native accessibility tree, pointer interactions, and post-fix OS-window recapture unverified.**
- [x] **Step 3: Inspect both existing screenshots at original resolution. Fix clipping, overlap, unreadable contrast, unreachable primary actions, missing focus states, or misleading progress. Record any capture limitation; do not claim the existing screenshots were recaptured after the contrast fix.**
- [x] **Step 4: Run `python -m pytest tests/ -q`, `cargo fmt --check`, `cargo test`, `cargo clippy --all-targets -- -D warnings`, and the Windows release build one final time.**

### Task 5: Finish review and durable design documentation

**Files:**
- Create: `DESIGN.md`, `.impeccable/design.json`
- Use: `.impeccable/review/` screenshots and the approved direction contract

- [x] **Step 1: Run the Impeccable finish review from its polish guidance on the native app, using both screenshot paths, the approved spec/direction contract, and `docs/superpowers/plans/2026-10-08-rust-ui-rewrite-index.md`. The installed helper has no `polish` command; no web detector ran because the app has no HTML/CSS surface.**
- [x] **Step 2: Resolve reviewer findings in one scoped batch and re-review source, tests, and the retained views. The warning contrast defect was fixed and covered; a post-fix native screenshot could not be recaptured after Windows Defender blocked the UIA harness. Record the verification limit and disposition in the review note.**
- [x] **Step 3: Record the approved design tokens and Annual Index direction in both `DESIGN.md` and `.impeccable/design.json`; verify that both documents match the theme, layout, screenshots, and approved direction, and document the eframe font-family variation from the original spec.**
- [x] **Step 4: Re-run the final local Windows verification after documentation edits; report any cross-platform CI evidence that is unavailable without a remote workflow run.**

### Task 6: Resolve final whole-branch review findings

**Review:** `.superpowers/sdd/2026-10-08-rust-ui-packaging-and-qa/review-2.md`

- [x] **Step 1: Add regression tests for the real JSON-lines stdin UTF-8 boundary, the engine's multi-event progress sequence, engine log severity, magazine and missing-issue login cancellation, organizer secondary-action visibility at both approved sizes, seasonal coverage wording, busy cache protection, and large Activity logs. Add checks for the smoke worker lifecycle and worker-binary rebuild invalidation.**
- [x] **Step 2: Run focused tests and confirm the new tests fail for the reviewed defects before changing implementation.**
- [x] **Step 3: Fix worker boundary/event handling and retained-engine cancellation/error semantics without changing approved engine behavior.**
- [x] **Step 4: Fix organizer/action visibility, coverage claims, cache guards, test-mode labeling, and Activity rendering; retain all history while filtering and drawing only visible rows.**
- [x] **Step 5: Fix fake-worker completion and incremental bundle rebuild tracking; correct README prerequisites and project structure.**
- [x] **Step 6: Run the complete Python and Rust verification, Windows release build, packaged worker smoke, and packaged app launch/exit smoke; record the exact outcomes and remaining platform limits.**
- [x] **Step 7: Run a fresh read-only whole-branch review; fix any Critical/Important findings and ledger any deferred Minor findings.**
