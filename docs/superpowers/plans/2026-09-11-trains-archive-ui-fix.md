# Trains Archive and UI Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current PyQt5 downloader truthful and reliable against the live TRN, MRR, CTT, CTR, and GRW Trains.com archives.

**Architecture:** Preserve the single-entry-point PyQt5/Selenium design while extracting small, testable helpers for archive scanning, download-mode detection, progress scoping, and worker outcomes. Use Selenium only for page/session interaction, one browser-side href extraction per archive page, requests for direct PDFs, and pypdf for validation.

**Tech Stack:** Python 3.10+, PyQt5, Selenium 4.6+, requests, pypdf, pytest, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-09-11-trains-archive-ui-fix-design.md`

## Global Constraints

- Do not read, commit, or transmit credentials or cookie contents.
- JSON cookies remain the only supported cookie format; pickle deserialization remains disabled.
- Live downloads use isolated `C:/tmp` directories and never the user's archive folders.
- Preserve recognized output names such as `MRR-10-October-2026.pdf`.
- Every production behavior change gets a failing regression test first.
- Do not push or merge from the repair branch.

---

### Task 1: Harden archive-page extraction and issue-link filtering

**Files:**
- Modify: `trains_app.py:1003-1063`
- Test: `tests/test_downloader_integration.py`

**Interfaces:**
- Add `ArchiveScanError(RuntimeError)` and `ArchiveRedirectError(ArchiveScanError)`.
- Extend `MagazineDownloader.collect_all_issue_links(archive_url, max_pages=110, hint_prefix=None, allow_empty=False) -> list[str]`.
- Keep `_is_issue_link(href, archive_url, hint_prefix=None) -> bool` callable by existing tests.

- [ ] **Step 1: Write failing tests for live-shaped links.**

  Add deterministic fake Selenium driver/element classes and tests that assert:

  ```python
  def test_normal_archive_rejects_unparseable_article_link():
      assert not MagazineDownloader._is_issue_link(
          None,
          "https://www.trains.com/ctr/magazine/railroad-places/",
          "https://www.trains.com/ctr/magazine/",
          hint_prefix="CTR",
      )

  def test_special_archive_accepts_unparseable_special_slug():
      assert MagazineDownloader._is_issue_link(
          None,
          "https://www.trains.com/trn/magazine/special-issues/railroad-technology/",
          "https://www.trains.com/trn/magazine/special-issues/",
          hint_prefix="TRN",
      )

  def test_page_links_are_extracted_in_one_browser_script_call():
      links = downloader.get_page_issue_links(
          "https://www.trains.com/mrr/magazine/",
          "https://www.trains.com/mrr/magazine/",
          hint_prefix="MRR",
      )
      assert links == ["https://www.trains.com/mrr/magazine/october-2026/"]
      assert driver.execute_script_calls == 1

  def test_regular_empty_archive_is_an_error():
      with pytest.raises(ArchiveScanError, match="no issue links"):
          downloader.collect_all_issue_links(regular_url, max_pages=1, hint_prefix="MRR")

  def test_special_redirect_can_be_reported_as_empty():
      assert downloader.collect_all_issue_links(
          special_url, max_pages=1, hint_prefix="GRW", allow_empty=True
      ) == []
  ```

- [ ] **Step 2: Run the focused tests and verify they fail for the expected reasons.**

  Run:

  ```powershell
  & "$repoRoot\.venv\Scripts\python.exe" -m pytest tests/test_downloader_integration.py -q
  ```

  Expected: failures for the missing batched extraction, unparseable-link filtering, and empty-scan behavior.

- [ ] **Step 3: Implement the smallest archive-scan fix.**

  Add URL canonicalization that removes query strings/fragments and normalizes trailing slashes. Use `WebDriverWait` for `document.readyState == 'complete'`, verify the final URL remains under the requested archive scope, then call one `execute_script` returning all `a[href]` values. Filter links through the archive scope, known non-issue slugs, and `parse_pdf_filename(slug + '.pdf', hint_prefix)` for regular archives. Allow unparseable slugs only when the requested archive path contains `/special-issues/`.

  Raise `ArchiveRedirectError` for an unrelated final URL and `ArchiveScanError` for an unexpected empty regular archive. Let `allow_empty=True` convert an empty/redirected special archive into a logged empty result so GRW does not look like a successful regular scan.

- [ ] **Step 4: Run focused tests, then the existing suite.**

  Run the focused test file and then:

  ```powershell
  & "$repoRoot\.venv\Scripts\python.exe" -m pytest tests/ -q --basetemp=C:/tmp/pytest-trains-task1
  ```

- [ ] **Step 5: Commit the archive-scan task.**

  ```powershell
  git add trains_app.py tests/test_downloader_integration.py
  git commit -m "fix: harden archive link collection"
  ```

### Task 2: Support the current PDF Edition viewer and robust download-mode detection

**Files:**
- Modify: `trains_app.py:309-328,1066-1253`
- Test: `tests/test_downloader_integration.py`

**Interfaces:**
- Add `_has_flipbook_trigger(driver) -> bool`.
- Add `_find_flipbook_download_control(driver)` or an equivalent selector helper used by `_flipbook_download`.
- Preserve `detect_download_mode(driver) -> tuple[str, str | None]`.

- [ ] **Step 1: Write failing tests for the current GRW presentation.**

  Add fake-driver tests asserting that a `PDF Edition` button selects `mode2`, that the legacy `Read Magazine` trigger still selects `mode2`, and that a direct `Download` anchor still selects `mode1`.

- [ ] **Step 2: Run the focused tests and verify RED.**

  ```powershell
  & "$repoRoot\.venv\Scripts\python.exe" -m pytest tests/test_downloader_integration.py -q
  ```

- [ ] **Step 3: Implement current viewer support.**

  Expand viewer-trigger detection to include case-insensitive `PDF Edition` buttons and current cover/viewer containers. Expand the post-open download-control lookup to support the current `data-name="btnDownloadPdf"` element and equivalent PDF-download button/link attributes. Use explicit waits for the trigger/control and keep the existing new-tab and completed-file detection paths.

  Ensure a failed viewer path returns a precise message containing the issue URL and does not mark the issue completed as read-only.

- [ ] **Step 4: Run focused tests and the existing suite.**

- [ ] **Step 5: Commit the viewer task.**

  ```powershell
  git add trains_app.py tests/test_downloader_integration.py
  git commit -m "fix: support current trains viewer downloads"
  ```

### Task 3: Make authentication and progress state truthful

**Files:**
- Modify: `trains_app.py:93-180,973-1000,332-375,2254-2260,1410-1505,1620-1718`
- Test: `tests/test_trains_app.py`

**Interfaces:**
- Add `progress_key(issue_url, destination_dir, flat) -> str`.
- Extend progress data with `completed_scoped` while retaining legacy `completed`/`failed` fields for compatibility.
- Extend `_handle_result(..., progress_key_value=None)` without breaking existing callers.

- [ ] **Step 1: Write failing tests.**

  Add tests asserting that:

  ```python
  def test_completed_progress_is_scoped_to_destination():
      assert progress_key(url, "C:/one/MRR", False) != progress_key(url, "C:/two/MRR", False)

  def test_handle_result_records_scoped_completion(tmp_path):
      progress = {"completed": [], "completed_scoped": [], "failed": []}
      _handle_result(True, "saved.pdf", url, progress, set(), logs.append,
                     progress_key_value=progress_key(url, str(tmp_path), False))
      assert progress["completed_scoped"]

  def test_progress_loader_initializes_scoped_entries(tmp_path):
      assert load_progress()["completed_scoped"] == []
  ```

  Add a fake page-source test proving `Hello, Griffin`/`Your Account` is accepted as authenticated.

- [ ] **Step 2: Run the focused tests and verify RED.**

- [ ] **Step 3: Implement progress and authentication changes.**

  Normalize destination paths in scoped keys. Use scoped entries for skip decisions and check `issue_already_on_disk` before any legacy URL-only entry. Continue writing legacy URLs for compatibility, but never let a legacy URL suppress a missing file in a different destination. Add `completed_scoped` defaults and safe malformed-data handling.

  Expand login markers to include current account text and make unsupported cookie paths produce a visible actionable log/error rather than silently falling through. Keep pickle rejection.

  Make Clear Cache remove both `download_progress.json` and `special_issues.json`, reporting exactly what was cleared.

- [ ] **Step 4: Run focused tests and the full suite.**

- [ ] **Step 5: Commit the state/auth task.**

  ```powershell
  git add trains_app.py tests/test_trains_app.py
  git commit -m "fix: scope progress and improve auth detection"
  ```

### Task 4: Add explicit worker outcomes and reliable cancellation

**Files:**
- Modify: `trains_app.py:1277-1508,1510-1735,2300-2345`
- Test: `tests/test_trains_app.py`

**Interfaces:**
- Add worker outcome constants: `idle`, `running`, `success`, `failed`, `cancelled`, `no-results`.
- Add `cancel_pending_futures(pending: dict) -> int`.
- Preserve the no-argument `finished` signal for existing Qt wiring.

- [ ] **Step 1: Write failing tests for outcome helpers and no-results behavior.**

  Test that pending futures not yet running are cancelled, a zero-task download run is classified as `no-results`, and a stop request is classified as `cancelled` rather than `success`.

- [ ] **Step 2: Run focused tests and verify RED.**

- [ ] **Step 3: Implement worker outcome state.**

  Set the worker outcome at start and update it on successful completion, explicit stop, scan error, authentication failure, and zero-result scan. Wrap regular-archive scan errors with the magazine name. Special-archive redirects/empty results remain nonfatal and are logged as unavailable/empty. Cancel pending futures on stop and drain only active work needed for a clean shutdown.

  Update `MainWindow._on_finished` to show `Done`, `Cancelled`, `Failed`, or `No issues found` according to the worker outcome. Do not show a successful completion banner after an error.

- [ ] **Step 4: Run focused tests and the full suite.**

- [ ] **Step 5: Commit the worker task.**

  ```powershell
  git add trains_app.py tests/test_trains_app.py
  git commit -m "fix: report worker outcomes and cancel pending work"
  ```

### Task 5: Bring the PyQt UI in line with the documented behavior

**Files:**
- Modify: `trains_app.py:1810-2055,2100-2345`
- Test: `tests/test_ui_smoke.py`

**Interfaces:**
- Add `MainWindow._refresh_log()`, `_copy_errors()`, `_update_error_badge()`, and `_update_magazine_progress(name, done, total)`.
- Keep existing `MainWindow._log`, `_update_progress`, and worker signal names.

- [ ] **Step 1: Write failing offscreen UI tests.**

  Assert that action controls have explicit accessible names, action text does not depend on emoji icons, the log filter and Copy Errors controls exist, error count increments, per-magazine progress updates create a visible row, and the 640×520 layout keeps the log toolbar and log widget visible.

- [ ] **Step 2: Run UI tests and verify RED.**

- [ ] **Step 3: Implement UI state and controls.**

  Add a compact log toolbar with filter, error badge, and Copy Errors. Store raw log lines separately from rendered HTML so filtering and clipboard output remain accurate. Add compact per-magazine progress rows driven by `magazine_progress`.

  Set accessible names and label buddies for cookie, folder, checkbox, combo, action, and magazine controls. Add visible keyboard focus styling for buttons and checkboxes. Replace `▶`, `■`, and `⬇` action prefixes with plain text labels. Keep the dark palette and tighten spacing/margins so the minimum window remains usable.

- [ ] **Step 4: Run UI tests, full tests, and generate an offscreen screenshot for 640×520 and the default size.**

- [ ] **Step 5: Commit the UI task.**

  ```powershell
  git add trains_app.py tests/test_ui_smoke.py
  git commit -m "fix: improve downloader UI feedback and accessibility"
  ```

### Task 6: Correct organizer inference, documentation, and CI

**Files:**
- Modify: `trains_app.py:383-430,741-865`
- Modify: `README.md:1-65`
- Modify: `requirements.txt`, `.github/workflows/build.yml`, `build.bat`
- Test: `tests/test_trains_app.py`

- [ ] **Step 1: Write failing organizer/documentation tests.**

  Add tests asserting that an ambiguous `fall-2020.pdf` without a prefix is not silently renamed to MRR, and that GRW with insufficient schedule evidence reports an unknown/seasonal schedule rather than all twelve monthly issues missing.

- [ ] **Step 2: Run focused tests and verify RED.**

- [ ] **Step 3: Implement safe inference.**

  Make `_guess_prefix` return `None` when no publication marker is present. Make `parse_pdf_filename` return `None` for date-only filenames without an explicit hint. Keep downloaded files safe by passing the known magazine prefix from download tasks. Treat GRW as seasonal/variable when frequency inference is insufficient; do not fabricate monthly missing issues.

- [ ] **Step 4: Update documentation and build automation.**

  Change README feature claims to match the repaired UI and describe GRW as seasonal/archived rather than monthly. Remove the unused `beautifulsoup4`/`bs4` mismatch or add the dependency only if code needs it. Install pytest in CI/build setup and run the tests before PyInstaller. Keep the existing PyInstaller collection options that are actually used.

- [ ] **Step 5: Run focused tests and the full suite.**

- [ ] **Step 6: Commit organizer/docs/CI changes.**

  ```powershell
  git add trains_app.py README.md requirements.txt .github/workflows/build.yml build.bat tests/test_trains_app.py
  git commit -m "fix: align organizer docs and release checks"
  ```

### Task 7: Final verification and live smoke checks

**Files:**
- Modify: none unless verification exposes a regression.

- [ ] **Step 1: Run the complete test, compile, dependency, and whitespace checks.**

  ```powershell
  & "$repoRoot\.venv\Scripts\python.exe" -m pytest tests/ -v --basetemp=C:/tmp/pytest-trains-final
  & "$repoRoot\.venv\Scripts\python.exe" -m compileall -q trains_app.py tests
  & "$repoRoot\.venv\Scripts\python.exe" -m pip check
  git diff --check
  ```

- [ ] **Step 2: Build a fresh one-file executable in `C:/tmp` and launch it long enough to verify a responsive window process.**

- [ ] **Step 3: Run live archive smoke checks for all five roots and confirm that current issue links are nonzero, special-route redirects are explicit, four direct PDFs validate, and the GRW viewer trigger is recognized.**

- [ ] **Step 4: Review the final diff against the spec and confirm the worktree contains no cookies, generated binaries, or unrelated changes.**

- [ ] **Step 5: Commit any verification-only fixes, then prepare the branch for review without pushing or merging.**
