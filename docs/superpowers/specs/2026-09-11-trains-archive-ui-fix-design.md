# Trains Archive and UI Remediation Design

**Date:** 2026-09-11  
**Repository:** `Trains.com-PDF-Downloader-Renamer`  
**Baseline:** `e0a7704`

## Goal

Restore reliable downloads across the current Trains.com archive for TRN,
MRR, CTT, CTR, and GRW while making progress, errors, cancellation, and the
PyQt UI truthful and usable.

## Scope

This repair covers the current single-file PyQt/Selenium application and its
existing tests and release workflow. It is intentionally a targeted repair,
not a full rewrite to Playwright or a database-backed collection manager.

The implementation will address:

1. Live archive collection reliability and redirect/zero-result validation.
2. Current direct-PDF and GRW `PDF Edition` viewer flows.
3. Authentication-state detection and cookie-file guidance.
4. Destination-aware progress and complete cache clearing.
5. Worker cancellation, failure, and completion state reporting.
6. Per-magazine progress and the documented log-panel capabilities.
7. Keyboard/accessibility metadata, focus visibility, layout density, and
   text-first controls.
8. Seasonal/ambiguous organizer behavior and current archive documentation.
9. Regression tests and CI test execution.

## Architecture

Keep `trains_app.py` as the application entry point, but isolate the risky
boundaries behind small helpers: archive-page extraction, page validation,
download-mode detection, viewer-download observation, progress-key creation,
and worker outcome state. Selenium page extraction will use explicit
conditions plus one browser-side href read per page; requests remains the
direct-PDF transport and pypdf remains the integrity check.

The UI will remain PyQt5 and use the existing dark visual language. It will
add lightweight widgets and state plumbing rather than introduce a new UI
framework. Existing organizer naming and output conventions remain stable for
recognized, prefixed files.

## Behavioral requirements

### Archive collection

- Wait for meaningful archive content instead of relying only on a fixed sleep.
- Extract candidate hrefs in one browser-side operation and canonicalize them.
- Reject pagination, query/filter links, known non-issue paths, unrelated
  redirects, and archive cards that cannot identify an issue.
- Treat an unexpected empty page, unrelated redirect, or page-load failure as a
  failed scan with a visible error; a legitimate empty special-issue archive
  must be explicitly reported as empty.
- Preserve the current `/page/N/` pagination scheme and test-mode page limit.

### Download modes

- Continue supporting direct `Download` anchors and current PDF URL patterns.
- Recognize the current `PDF Edition` viewer trigger in addition to legacy
  reader triggers.
- After opening a viewer, wait for the current PDF download control, observe a
  new completed PDF in the configured download directory, validate it, and
  report a bounded timeout with the issue URL.
- Never mark an issue completed merely because a read-only/no-PDF result was
  reached unless that behavior is explicitly represented in progress state.

### Authentication

- Accept only JSON cookies as the existing security boundary requires.
- Detect the current signed-in account surface using stable positive markers
  in addition to legacy logout text.
- Report invalid/unsupported cookie files directly in the UI and explain how
  to recover with a visible login.

### Progress and outcomes

- Scope completed entries by canonical issue URL, destination root, and the
  relevant special/regular destination so changing folders cannot suppress a
  needed download.
- Keep compatibility with existing progress files where practical; malformed
  or legacy entries must not cause silent skips.
- Clear all downloader caches through the Clear Cache action, with a clear
  confirmation/status message.
- Represent worker outcomes as success, failed, cancelled, or no-results.
- Stop must prevent new work and cancel pending direct-download futures where
  possible; the UI must not report `Done.` after a failure or cancellation.

### UI and usability

- Display one overall progress bar plus a compact per-magazine progress view.
- Add a log filter, visible error count, and Copy Errors action.
- Add explicit accessible names/associations and visible keyboard focus states.
- Keep the minimum window usable at 640×520, with the log remaining useful.
- Replace emoji-dependent action labels with plain text labels that remain
  clear in accessibility tools and restricted fonts.
- Keep the first-launch authentication guidance and headless warning visible.

### Organizer and documentation

- Do not silently infer MRR for ambiguous filenames in auto-detect mode;
  preserve the file as unrecognized or require an explicit prefix.
- Model GRW seasonal/quarterly archive history without claiming it is monthly.
- Update README claims to match the actual UI and archive behavior.
- Make CI run the test suite before building packages and remove the
  requirements/build mismatch for optional imports.

## Acceptance criteria

1. New regression tests fail on the baseline for each confirmed defect and
   pass after implementation.
2. The full test suite passes with no failures.
3. The organizer preserves corrupt files, duplicates, and recognized naming
   behavior while rejecting ambiguous auto-detect input safely.
4. A live browser smoke check confirms all five archive roots load, current
   issue links are collected, and the GRW viewer path is recognized.
5. Four currently direct-PDF issue samples download, rename, and validate;
   GRW produces a validated PDF through the viewer path when the browser
   session permits it, or a precise actionable error otherwise.
6. A failed/empty scan cannot finish as a successful zero-issue run.
7. Changing the output folder does not skip files that are absent there.
8. The UI exposes truthful completion/cancellation/error states and the
   documented progress/log controls.
9. `compileall`, `pip check`, PyInstaller, and the CI-equivalent test/build
   commands pass; the worktree contains only intended changes.

## Testing strategy

- Use TDD for each production behavior: write a focused regression test, run
  it red, implement the smallest fix, run it green, then run the broader suite.
- Use fake Selenium driver elements for deterministic mode/collector tests;
  keep live-site checks as bounded smoke tests so network variability does not
  make unit tests flaky.
- Use offscreen Qt tests for widget state, accessible metadata, minimum-size
  layout, filters, progress, and outcome presentation.
- Use a fresh packaged launch and live archive checks after unit/UI tests pass.
- Do not store credentials or cookies in the repository or test artifacts.

## Non-goals

- No rewrite to a new browser automation framework.
- No automatic cookie extraction from the user's browser profile.
- No changes to the user's existing archive or download folders during tests;
  live downloads use isolated temporary directories.
- No release push or merge until the repaired branch is reviewed and verified.
