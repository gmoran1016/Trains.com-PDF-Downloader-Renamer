# Archive Scan Failure and Release Fix

**Goal:** Ensure a temporary archive access failure cannot silently skip newer downloadable issues or report a successful/empty run, while preserving already-discovered issues for download.

**Scope:** `trains_app.py`, focused regression tests, and release version/documentation. The failure from the October run was an HTTP 403 during pagination; the scan code logged and swallowed it.

**Spec:** No separate design spec. User request and confirmed October run evidence are authoritative.

**Constraints:** Keep existing retry behavior and normal end-of-pagination handling. Preserve partial results from pages already read. Continue scanning other selected magazines and attempt known issues. Report failure if any archive scan was incomplete, including when no issues were found. Do not expose cookies or modify the user's magazine library during verification. User explicitly authorized a GitHub push and release build.

### Task 1: Make archive scan failures visible and releasable

**Files:** `trains_app.py`, `tests/test_downloader_integration.py`, `tests/test_trains_app.py`, `tests/test_ui_smoke.py`, `README.md`

**Interfaces:**
- `ArchiveScanError` carries a `partial_links` list.
- `collect_all_issue_links` raises on a nonterminal scan failure, retaining links found before the failure; normal terminal 404 behavior remains intact.
- `DownloadWorker` records scan failures, continues with partial results and other selected archives, and reports a failed outcome if discovery was incomplete.

- [x] Add regression tests for a page-1 403, a page-2 403 retaining earlier links, optional-special 403, and worker failure/continuation behavior.
- [x] Run those tests and confirm they fail for the existing bug.
- [x] Implement the minimum collector and worker changes; retain the established per-request retry behavior.
- [x] Run focused tests and the full test suite; run syntax and diff checks.
- [x] Bump app and README version to 1.8.6 so GitHub produces a distinct release, and describe truthful incomplete-scan reporting.
- [ ] Commit, push `main` as authorized, wait for the GitHub release build, download the Windows EXE, and verify the asset's version/hash.
- [ ] Test the packaged EXE in isolation and perform authenticated, read-only checks of current magazine archive routes without writing to the user's library.

**Review Focus:** Verify a page-2 failure does not discard earlier issue URLs, a special archive's 403 is not mistaken for an empty archive, and a failed scan cannot produce a success or no-results outcome. Check that the release tag and executable both identify v1.8.6.
