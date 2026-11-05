# Download Naming, Metadata, and Duplicate Prevention Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure magazine downloads use issue-page identity for canonical names and PDF metadata, and skip issues already represented by PDFs in the destination tree.

**Architecture:** Carry the issue URL from the download worker through direct and flipbook download paths into the existing rename-and-metadata stage. Make existing-file checks compare parsed issue identity across the destination tree, including older folder layouts, and use a stable URL-derived name for issues without a parseable date. Keep the worker protocol unchanged.

**Tech Stack:** Python 3.13, pytest, PyQt5 worker, pypdf, Rust/Tauri/React release packaging.

**Spec:** User request in this task: investigate broken metadata/naming during downloads and repeated downloads despite an existing file; fix, fully test, build a new version, and push to GitHub.

## Global Constraints

- Apply issue-page identity to direct PDF and flipbook downloads.
- Existing PDFs for an issue must prevent a repeated download across legacy destination layouts.
- Metadata stamping remains best-effort and must not invalidate an otherwise successful download.
- Preserve unrelated uncommitted work in the current checkout.
- All version declarations must agree before packaging.
- Run the full project checks and a versioned desktop build before pushing the fix branch.

## Review Focus

- Generic or opaque CDN filenames: the issue URL still determines canonical naming and date metadata.
- Existing canonical files in the expected year folder, a magazine root, or a legacy nested folder: all cause a skip.
- Dated special issue slugs: preserve existing naming behavior while detecting the existing output.
- Undated special issue slugs: use a stable slug-derived filename so later runs can identify the output.
- Progress state missing or cleared: an existing PDF still prevents a second download.

---

### Task 1: Carry Issue Identity Through Download Naming and Metadata

**Files:**
- Modify: `trains_app.py`
- Test: `tests/test_trains_app.py`
- Test: `tests/test_downloader_integration.py`

**Interfaces:**
- `rename_and_move` and `fetch_pdf` accept an optional `issue_url` without breaking existing callers.
- `MagazineDownloader` and `DownloadWorker` pass the URL of the issue page through every download mode.

- [ ] **Step 1: Add failing integration tests** for a generic CDN PDF filename downloaded from a dated issue URL; assert the canonical filename and PDF info metadata derive from the URL.
- [ ] **Step 2: Run the focused tests and confirm they fail** because the current download pipeline omits the issue URL.
- [ ] **Step 3: Thread the issue URL** through direct HTTP, browser-fallback, flipbook, and parallel worker paths; prefer a parseable issue URL when deriving date-based output names and metadata, then use a stable URL slug when neither filename nor URL has a date.
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 2: Detect Existing and Repeated Issue Downloads

**Files:**
- Modify: `trains_app.py`
- Test: `tests/test_trains_app.py`
- Test: `tests/test_downloader_integration.py`

**Interfaces:**
- Add an issue-identity key derived from the issue URL or an existing PDF's parsed name/content.
- Allow worker loops to reuse one existing-file index per destination instead of rescanning for every issue.

- [ ] **Step 1: Add failing tests** for a previously downloaded canonical PDF in a legacy folder, an existing file without progress state, and a stable undated special-issue filename.
- [ ] **Step 2: Run the focused tests and confirm they fail** on the legacy-path or undated-issue cases.
- [ ] **Step 3: Index existing issue PDFs by normalized issue identity** and search the destination tree once per job.
- [ ] **Step 4: Run the focused tests and confirm they pass.**

### Task 3: Version the Fix and Verify the Release

**Files:**
- Modify: `trains_app.py`
- Modify: `README.md`
- Modify: `desktop-ui/package.json` and `desktop-ui/package-lock.json`
- Modify: `desktop-ui/src-tauri/Cargo.toml` and `desktop-ui/src-tauri/Cargo.lock`
- Modify: `rust-ui/Cargo.toml` and `rust-ui/Cargo.lock`
- Modify: `desktop-ui/src-tauri/tauri.conf.json`

**Interfaces:**
- Set every app/engine package version to `1.10.1` and update the README release heading.

- [ ] **Step 1: Bump all release versions** to `1.10.1` and document the download fix.
- [ ] **Step 2: Run the complete Python, Rust, and rendered UI suites**, version consistency check, formatting, and lint checks.
- [ ] **Step 3: Build and smoke-test the Windows desktop package** using the repository build script.
- [ ] **Step 4: Commit and push a fix branch**, then trigger the GitHub Actions release workflow without publishing and verify the new version builds across the matrix.
