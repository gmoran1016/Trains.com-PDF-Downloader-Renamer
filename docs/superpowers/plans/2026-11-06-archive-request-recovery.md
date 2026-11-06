# Archive Request Recovery Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this focused fix in the current session.

**Goal:** Reduce archive request load and recover from temporary access blocks while preserving discovered issues and responsive cancellation.

**Architecture:** Use the existing authenticated HTML parser before loading archive pages in Chrome. Keep browser recovery for HTTP failures, refresh cookies from the active browser, and replace short blind retries with status-aware, cancellable delays.

**Tech Stack:** Existing Python, requests, Selenium, and pytest; no new dependencies.

**Spec:** The user's November 6 failure log and explicit request to fix the downloader, plus PRODUCT.md's incomplete-discovery and collection-protection requirements.

## Global Constraints

- Preserve partial issue links, existing pagination and special-issue behavior, and honest failed outcomes.
- Keep browser fallback and browser transport recovery.
- Never expose session values or write to the user's PDF library during verification.
- The initial local repair used `fix/cloudfront-403-v2.0.1`. The user's follow-up authorizes version 2.0.2, update notes, committing and pushing the fix, and verifying the GitHub release build.

## Review Focus

- An HTTP success must extract and deduplicate the same issue URLs without browser navigation.
- An HTTP failure must retain the browser fallback; a denied browser must not immediately repeat the same HTTP request.
- A 403/429 must wait before retrying; numeric and date Retry-After headers must be respected.
- User cancellation during a retry must stop promptly and retain previous pages.
- Current browser cookies must supersede older saved cookies, with saved-cookie recovery if the driver is unavailable.

### Task 1: Implement and verify archive request recovery

**Files:** `trains_app.py`, `tests/test_downloader_integration.py`, `tests/test_trains_app.py`, `README.md`.

**Interfaces:** Preserve `get_page_issue_links` and `collect_all_issue_links` signatures. Add an optional `stop_requested` callback to `MagazineDownloader`, pass it from the magazine and missing-issue workers, and use `_wait_for_archive_delay(seconds) -> bool` for interruptible waits.

- [x] Add isolated HTTP/browser boundary regressions for the review cases; confirm the new cases fail against the existing implementation.
- [x] Prefer authenticated HTTP for archive HTML, using live browser cookies when available and the existing browser fallback on request failures.
- [x] Retry blocked requests after 60 and 120 seconds, honoring longer Retry-After values; retain short bounded retries for other transient failures and terminal 404 handling.
- [x] Allow cancellation during page pacing and cooldown, preserving partial links and skipping subsequent special-issue scans after cancellation.
- [x] Document the lighter discovery path and recovery behavior.
- [x] Run focused tests, the full Python test suite, compilation, and diff checks; review the final patch.
- [x] Build the local Windows portable app and installer; verify the packaged worker and isolated desktop startup.

## Execution Record

- Baseline: 33 downloader, login-recovery, and browser-startup tests passed.
- Live evidence: one authenticated HTTP request to the formerly failing Trains Magazine page 7 returned HTTP 200 and archive HTML. The precise server rule causing the earlier 403 is not observable from the client.
- Ruling: implement this bounded repair in place on the dedicated fix branch; no new worktree, dependency changes, or release publication are needed.
- Regression evidence: seven initial cases failed against the original implementation. Review added failing cases for browser-confirming empty HTTP responses, cooldown before Chrome requests, HTTP timeout classification, and cancellation with no matching missing issue; all pass after correction.
- Final verification: `python -m pytest tests/ -q --tb=short` passed all 145 tests; Python compilation, version consistency, and `git diff --check` passed. Focused downloader/login/browser coverage passed all 49 tests.
- Live sample: seven paced authenticated HTML requests found issue links on the formerly failing Trains page 7, the first page of all five magazines, and Model Railroader specials. No PDF downloads or library writes were performed; this was not a full archive scan.
- Review: an independent read-only reviewer confirmed the recovery, retry-timing, HTTP-empty, browser-transport, and cancellation fixes; no substantive findings remain.
- Local Windows build: `dist/desktop-20261106-083010-7d50ab6b/` contains the portable executable and installer, both version 2.0.1. The packaged worker completed an isolated organizer request, and the desktop app opened and closed cleanly using temporary application data. No release was published.
- Portable SHA-256: `9F26ECB1AFFF0335A0DA8FA154466A8910E74991CFE5B59B655F3FDDD2A72763`.
- Installer SHA-256: `776406579AA9D9C20AA13FF23C0B04AD0319075BD7355253C8BAC826481FC39F`.
- Release follow-up: synchronized all engine, desktop, bundle, and lockfile versions to 2.0.2; added `docs/releases/v2.0.2.md` and updated the README. All 145 Python tests, Python compilation, version consistency, diff checks, and the desktop frontend production build passed before committing for the existing four-platform GitHub release workflow.
