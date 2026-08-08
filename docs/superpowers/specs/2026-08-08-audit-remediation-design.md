# Audit Remediation Design — 2026-08-08

## Purpose

Remediate the eight actionable findings in `docs/usability-audit-2026-08-08.md` while preserving the current application architecture and avoiding unverified changes to download, authentication, tray, and Windows UI Automation behavior.

The repository currently contains a single-file PyQt5 application. The change should improve organizer data safety and reporting first, then make the visible setup experience clearer, and finally align release documentation and test setup with the shipped source.

## Goals

- Never move a corrupt or truncated source PDF into the organized collection.
- Make destination conflicts visible and countable without deleting either file.
- Produce completeness results independently for each detected magazine and year.
- Keep the missing-issue download action safe when an organize run contains multiple publications.
- Explain subscription, JSON cookie handling, and the two headless settings at the point of use.
- Improve section-label contrast and make the magazine selector resilient at the minimum window size.
- Align version, build, and authentication documentation with the current v1.6.0 GUI.
- Make the documented test setup installable in a clean environment without a fixed global pytest temp directory.
- Add regression coverage for the organizer failures reproduced by the audit.

## Non-goals

- Do not change the network scraper, browser login detection, cookie serialization, download worker lifecycle, system-tray behavior, or close/cancel behavior.
- Do not claim UI Automation, keyboard, tray, live authentication, or live download verification that the current Computer Use runtime cannot perform.
- Do not add a full interactive organizer preview or a separate application package in this remediation pass.
- Do not delete existing user files as part of conflict or integrity handling.

## Considered approaches

### Narrow compatibility patch

Keep the current positional organizer return value and add counters and report strings around it. This has the smallest code diff, but it leaves the result contract difficult to extend and requires the UI to continue parsing human-readable log lines.

### Structured targeted patch (selected)

Introduce a small `OrganizeSummary` data object and pure organizer helpers inside `trains_app.py`. Keep the existing worker and UI flow, but have the UI consume structured counts and missing-issue data. This gives the data-integrity and mixed-publication fixes a stable boundary without refactoring the downloader or splitting the application into modules.

### Full inventory/preview redesign

Separate organizer planning from mutation, show a preflight table, and provide interactive conflict resolution. This would provide the strongest long-term UX, but it is larger than the evidence-backed remediation, would require a new UI state, and would increase regression risk in an already unverified desktop flow.

## Selected design

### Organizer result model

Add an `OrganizeSummary` dataclass with at least these fields:

- `moved`
- `already_correct`
- `unrecognized`
- `corrupt`
- `conflicts`
- `metadata_stamped`
- `report` — human-readable lines for the log
- `missing_by_prefix_year` — structured mapping of prefix to year to missing month names

`OrganizeWorker` will store this object as its result, and `MainWindow` will read fields instead of reconstructing state by parsing summary text. The human-readable report remains so users can copy and understand the result from the log.

### Integrity and mutation rules

1. Enumerate PDFs and parse the filename/content as today.
2. For a recognized source, call `_verify_pdf` before creating a destination mutation.
3. If verification fails, leave the source at its original path, log a `[corrupt]` entry with an actionable explanation, increment `corrupt`, and emit progress.
4. For valid files, determine the canonical destination.
5. If the source is already at the canonical path, count it as `already_correct` and allow metadata stamping.
6. If the canonical destination exists for a different source, allocate the existing suffix path so neither file is lost, increment `conflicts`, and log an explicit `[conflict]` entry identifying the preserved destination.
7. Move only after these checks. Metadata stamping remains best-effort, but a metadata warning must not be presented as a move failure or integrity success.

`rename_and_move` will use the same pre-move verification rule. A corrupt input will remain in the download/source directory rather than being moved and deleted. Downloaded temporary files can still be cleaned up by the download error path after the helper returns failure.

### Per-publication completeness

Replace the aggregate `issues_by_year` accumulator with a nested mapping keyed by the normalized publication prefix. For each prefix:

- infer a schedule from that publication’s own years when the existing inference rules have enough evidence;
- otherwise use `PREFIX_ISSUE_MONTHS` or the monthly fallback for that publication;
- compare only that publication’s present months to its expected schedule and today’s date;
- append report lines such as `MRR 2024: complete` or `CTR 2024: missing ['September']`.

The structured `missing_by_prefix_year` mapping will contain only missing months and will be used by the GUI. When more than one prefix is present, the GUI will show all publication-specific reports but will not enable a single-publication “Download Missing” action. When exactly one prefix is present, the existing action remains available with that prefix’s missing mapping.

### Onboarding and accessibility

- Add a compact, wrapped authentication note near the cookie field stating that an active trains.com subscription is required, interactive Chrome login should be used before headless mode, and JSON cookies are sensitive session data.
- Rename the download checkbox to `Hide download browser`.
- Rename the organizer authentication checkbox to `Hide browser for missing-issue downloads`.
- Preserve existing setting keys for compatibility.
- Change the section-label foreground to a high-contrast color that remains legible on the existing dark panel.
- Replace the single horizontal magazine-chip row with a grid that wraps the five chips at narrow widths. Keep each chip keyboard-focusable and checkable.

No new authentication action or browser behavior is introduced; these are explanatory and visual changes only.

### Documentation and test setup

- Keep `APP_VERSION` at `1.6.0` and update README references to match.
- Correct `build.bat` comments and completion output to describe the actual `--onefile` artifact at `dist\TrainsDownloader.exe`.
- Rewrite `docs/AUTHENTICATION_GUIDE.md` around the current GUI, JSON cookie workflow, headless prerequisites, recovery, and cookie security. Remove unsupported legacy CLI commands and flags.
- Add `requirements-dev.txt` that includes the runtime requirements plus pytest.
- Update README test instructions and project structure for the development requirements file.
- Remove the fixed `--basetemp=C:/tmp/pytest-trains` pytest option so parallel or clean environments do not share a global cache path.

## Test strategy

Before production changes, add failing tests for:

- corrupt organizer inputs remaining in the source and being counted as corrupt;
- `rename_and_move` preserving corrupt inputs;
- valid organizer moves and already-correct detection;
- explicit conflict counts and conflict log entries;
- independent completeness reports for mixed MRR/TRN/CTT/CTR/GRW inputs;
- structured missing data and the single-prefix missing-download gating decision;
- existing settings, PDF verification, and progress behavior remaining green.

Where practical, keep tests on pure functions and temporary directories. GUI assertions should be limited to deterministic construction, labels, and layout properties; live browser and UI Automation journeys remain manual/blocked verification items.

## Acceptance criteria

- A recognized corrupt PDF is never moved by either organizer path and is visible in the final summary.
- A duplicate canonical target produces an explicit conflict log/count and preserves both files.
- Mixed-publication completeness output has no cross-publication aggregate months.
- Missing-download state is not enabled for an ambiguous mixed-publication result.
- First-launch labels explain the required subscription/session setup and distinguish the two headless controls.
- Section labels meet the project’s chosen contrast target against the panel background, and the magazine controls wrap at the minimum supported width.
- README, authentication guide, build output, and source version agree on the current v1.6.0 GUI.
- A clean development environment can install `requirements-dev.txt` and run the test suite without a repository-global pytest temp path.
- All existing and newly added automated tests pass.

