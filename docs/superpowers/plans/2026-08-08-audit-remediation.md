# Audit Remediation Implementation Plan

> **Execution rule:** follow test-driven development for each behavioral change. Add or update a failing regression test, run it to confirm the failure, implement the smallest change, then rerun the focused and full suites.

## Scope

Implement the approved design in `docs/superpowers/specs/2026-08-08-audit-remediation-design.md` for all eight actionable audit findings. Preserve the blocked-flow boundary: do not alter the downloader’s browser/authentication logic, worker lifecycle, tray behavior, or close/cancel behavior.

## Worktree and baseline

1. Read the worktree instructions and create an isolated implementation worktree without disturbing the current branch’s untracked audit report, evidence, or `.superpowers/` files.
2. Record the initial status and run the existing test suite in the implementation environment. If pytest is unavailable, install the repository’s development requirements in the isolated environment as part of the test-setup work.
3. Confirm the baseline failure/pass state before adding tests.

## 1. Organizer integrity and result model

### Tests first

Update `tests/test_trains_app.py` with focused temporary-directory tests for:

- a recognized corrupt PDF remaining in its source directory, absent from the destination, and counted as corrupt;
- `rename_and_move` rejecting a corrupt source without moving or deleting it;
- a valid file still being renamed, moved, and verified;
- a canonical destination conflict preserving both files, incrementing a conflict count, and emitting an explicit conflict log entry;
- an already-canonical file continuing to count as already correct.

Run only the new organizer tests and confirm they fail against the current implementation.

### Implementation

In `trains_app.py`:

1. Add the required dataclass imports and define `OrganizeSummary` near the organizer code.
2. Add a shared pre-move verification helper or equivalent guard using `_verify_pdf`.
3. Change `rename_and_move` to verify the source before mutation and retain corrupt input in place.
4. Change `organize_pdfs` to use the same guard, increment `corrupt`, and always emit progress for rejected files.
5. Preserve `_unique_path` behavior for safety, but add a `conflicts` counter and explicit `[conflict]` log messages whenever the canonical destination is occupied by another source.
6. Return `OrganizeSummary` and update `OrganizeWorker`/`MainWindow` consumers without changing download worker behavior.

Run the focused organizer tests, then the existing full suite.

## 2. Per-publication completeness and missing-download state

### Tests first

Add tests for a synthetic mixed collection containing at least two supported prefixes and different issue schedules. Assert that:

- report lines are grouped by prefix and year;
- a missing month in one publication does not appear in another publication’s report;
- quarterly `CTR` uses its publication-specific schedule;
- `missing_by_prefix_year` contains structured values;
- a mixed result does not create an ambiguous missing-download action, while a single-prefix result retains the existing missing-download data.

Run these tests and confirm failure before changing the implementation.

### Implementation

1. Replace the aggregate year-only issue accumulator with `prefix → year → months`.
2. Apply schedule inference and fallback independently for each prefix.
3. Populate structured missing data and retain readable report lines for the log.
4. Update `_on_organize_finished` to consume the result object rather than parse report text.
5. Enable “Download Missing” only for one unambiguous prefix; preserve the existing prefix/archive URL flow for that case.
6. Log a clear explanation when a mixed run has missing issues but cannot safely select one download source.

Run the focused completeness tests and the full suite.

## 3. UI onboarding, accessibility, and narrow-window layout

### Tests first

Add a deterministic Qt smoke test module, using an offscreen Qt platform where supported, that checks:

- the download and organizer headless controls have distinct explanatory labels;
- the authentication guidance is present and mentions subscription/session-cookie prerequisites;
- the magazine selector has a wrapping layout rather than a single required horizontal row;
- the main window can construct at the minimum supported size without raising.

Run the UI smoke tests and confirm any expected failures before UI edits.

### Implementation

In `trains_app.py`:

1. Add wrapped authentication guidance adjacent to the cookie field without introducing a new browser action.
2. Rename visible headless labels while preserving the existing settings keys and signal wiring.
3. Increase the section-label color luminance to meet the selected contrast target against `#1e1e2e`.
4. Replace the magazine `QHBoxLayout` with a wrapping `QGridLayout` suitable for the five supported publications.
5. Keep all existing primary actions, controls, and download/organize modes intact.

Run the Qt smoke tests and full suite. Capture a source-built first-launch screenshot if the local runtime permits; do not treat blocked Computer Use flows as verified.

## 4. Documentation, build output, and development dependencies

1. Add `requirements-dev.txt` that includes `-r requirements.txt` and a pytest dependency.
2. Remove the fixed global `--basetemp` option from `pytest.ini` while retaining safe temporary-file retention settings.
3. Update README version, test-install instructions, test command, project structure, authentication wording, and build artifact path to match the actual app.
4. Rewrite `docs/AUTHENTICATION_GUIDE.md` for the current PyQt GUI, JSON cookie lifecycle, interactive-login prerequisite, headless prerequisite, recovery steps, and cookie security. Remove obsolete CLI entrypoints and flags.
5. Correct `build.bat` comments and success output to match the existing `--onefile` PyInstaller invocation.

Use `rg` to search for stale v1.5.0, `train-cli`, `train-gui`, `Magazine-Downloader.py`, and the old folder-style build path. Review each remaining match instead of blindly changing historical design documents.

## 5. Verification and handoff

Run, in order:

1. Focused organizer/completeness tests.
2. Focused Qt smoke tests.
3. Full `python -m pytest tests -v` using the documented development requirements.
4. `python -m compileall trains_app.py tests`.
5. `git diff --check`.
6. A clean source build with `build.bat` or the equivalent PyInstaller command if the local Windows environment supports it; verify the one-file output path.
7. A source-built or isolated executable launch smoke check at the default size and, where safe, the minimum size. Record any Computer Use limitation explicitly rather than inferring a pass.

Review the final diff for accidental changes to the audit report/evidence and for any modifications outside the approved scope. Report exact test/build results and identify any remaining blocked verification.
