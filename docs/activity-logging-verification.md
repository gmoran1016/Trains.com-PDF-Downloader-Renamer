# Activity logging verification

Date: 2026-10-09. Local changes following the 1.10.0 release; application versions remain 1.10.0.

## Implemented behavior

- Local timestamps and explicit file outcomes, with full paths and recovery advice under Details.
- Organize stages for scanning, file processing, and issue coverage. Every processed file produces one outcome row, including files already organized.
- Metadata warnings attached to the file outcome. Conflicting PDFs remain preserved, and unreadable or unrecognized files remain in place.
- All activity / Needs attention filtering with text search. Partial coverage and partial closing summaries appear under Needs attention.
- Copy log exports all matching events across every page in chronological order, including full details. Copy errors retains its separate scope.
- Closing totals for moved, already organized, skipped, conflicts, and updated metadata. Cancelled and incomplete runs explicitly identify partial findings.

Filename parsing, movement, conflict preservation, metadata updates, coverage inference, missing-download eligibility, settings, and protocol v1 retain their existing behavior. Progress and status come from worker events.

## Automated checks

| Check | Result |
|---|---|
| Python engine and worker tests | 109 passed |
| Rust core, settings, controller, worker, and bundle tests | 35 passed |
| Tauri shell test | 1 passed |
| Rendered layout and interaction checks | 29 passed |
| Rust formatting and Clippy, warnings denied | Passed for core and shell |
| TypeScript and Vite production build | Passed |
| Frontend formatting and patch whitespace | Passed |
| Shared version consistency | Passed |
| Fresh bundled Python worker smoke | Passed |
| Windows portable executable and installer build | Passed |
| Production startup and normal close | Passed with isolated data |

Regression checks cover all file outcomes, metadata warnings without losing the move outcome, cancellation between files, partial coverage, severity determined by outcomes rather than words in a path, paged filtering, whole-history copying, and clearing warning counts. Existing download and organizer tests remain in the suite.

Rendered checks cover both themes at 640×480, 800×620, 1120×760, and 1440×900. The confirming captures show readable filenames, timestamp and outcome columns, themed controls, and expandable details. At the minimum size, reading long details scrolls inside Activity; workflow actions and the Activity toolbar stay in place. Checks reject horizontal overflow and verify that the first filename fits before scrolling.

## Packaged Windows interaction check

The fresh production executable loaded embedded WebView2 assets and bundled Source Sans 3 with no development server or fake worker. A temporary archive contained one existing canonical issue, two incoming recognized issues including a conflict, one unreadable PDF, and one unrecognized PDF.

The real bundled worker returned 2 moved, 1 already organized, 2 skipped, and 1 conflict; the conflict overlaps the moved count. Native checks verified five individual outcome rows, real timestamps and IDs, 5/5 progress, stage messages, and the closing summary. Both conflicting files and both skipped files were present afterward.

Through the rendered desktop controls, Copy log placed the full chronological history and paths on the Windows clipboard. Needs attention showed exactly the three warning outcomes; copying that view omitted ordinary moves. Details, text search, and Clear activity worked, and clearing reset the warning count. No browser errors were recorded. The app closed normally after the checks.

The check used a fresh data directory and WebView2 profile, with synthetic PDFs only. No live login, subscription downloads, cookies, or user archive changes were involved. Diagnostic helpers and evidence remain in the ignored `build/` and `desktop-ui/test-results/` folders.

## Local packages

Build directory: `dist/desktop-20261009-135023-be5de6f6/`.

| File | Bytes | SHA-256 |
|---|---:|---|
| TrainsDownloader-windows.exe | 96,886,784 | `7eef35ca378ef228bd175ab8b0de96b253fe5e0c9356e34f67a9e8e0a53def75` |
| TrainsDownloader-windows-setup.exe | 89,000,649 | `ba37f2849363a5e437b786b279c37d3bdb99a643356283ec3c595ca6fb76f269` |

These are local Windows verification packages. Linux/macOS builds and runtime checks are outside this local verification record.
