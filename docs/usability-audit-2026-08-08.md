# Usability Audit — 2026-08-08

## Executive summary

Release-readiness verdict: **Hold / not ready for v1.6.x sign-off.** The current source identifies itself as v1.6.0, but the repository has no packaged executable and the README still presents v1.5.0. More importantly, an isolated exercise of the organizer engine demonstrated that a date-named, 34-byte corrupt PDF is moved into the organized collection and reported as moved rather than rejected. Mixed-magazine completeness reporting also collapses different publications into one year-level report, and duplicate issues are silently renamed with a `-1` suffix.

The real Windows application was built from the current source in an isolated temporary directory and launched successfully. The first-launch window was captured at 876×759 pixels; the app title displayed v1.6.0 and the primary Download UI was visible. Computer Use successfully enumerated the target window, but every state-capture and input call failed with `Error: node_repl exec context not found`, so the required mouse/keyboard journeys could not be completed. No credentials were entered, no cookie contents were opened or exposed, no live download was started, and no real user data was used.

The audit therefore provides strong evidence for organizer, visual, documentation, and release-process risks, but it is not a complete approval of download, authentication, tray, cancellation, restart, or Windows UI Automation behavior. Those scenarios are explicitly marked blocked below.

### Five highest-impact risks

1. **P2 — Corrupt PDFs can be accepted by Organize.** The organizer path moved a 34-byte date-named corrupt file into the output and only logged a metadata warning.
2. **P2 — Mixed publications produce a misleading completeness report.** The result is one aggregate year-level list, not a per-magazine inventory.
3. **P2 — Conflicts are silently duplicated.** Two files resolving to the same issue become canonical and `-1` variants without a conflict summary or confirmation.
4. **P2 — First-run authentication and headless behavior are under-explained.** The screen exposes a cookie path and two similarly named headless controls but no visible subscription/login/recovery guidance.
5. **P2 — Low-contrast section labels reduce scannability and accessibility.** The stylesheet’s section-label color against the panel background computes to approximately 1.80:1.

## Environment, method, assumptions, and limitations

| Item | Observed value |
|---|---|
| OS | Windows 11 Pro, build 26200, 64-bit |
| Displays | Primary 2560×1440; second 2560×1440 |
| System scaling | Not discoverable from the checked registry values; global DPI/theme/high-contrast settings were not changed |
| Python | Repository venv Python 3.14.6; global `py` Python 3.14.4 |
| Chrome | Google Chrome 151.0.7922.77 detected; existing browser processes were left untouched |
| App version | v1.6.0 in the window title and `APP_VERSION`; README says v1.5.0 |
| Launch path | Isolated one-file PyInstaller build from current `trains_app.py`; build completed successfully in 165.95 seconds |
| Packaged artifact in repo | None found; the repository `dist` executable was not available |
| Window observation | First-launch capture 876×759 pixels; initial visible state was Download mode |

Method followed the requested Windows-first approach:

- Inspected README, requirements, build script, authentication guide, tests, current UI source, and Git state. Future RailShelf planning documents were not treated as v1 requirements.
- Ran the documented test command first. The default environments could not collect tests because `pytest`/`pluggy` were absent or incomplete. An isolated temporary dependency directory then enabled the existing suite to run without changing the repository venv.
- Built and launched the current source as an isolated executable outside the repository. The executable created its settings/log area outside the repository as well.
- Attempted Computer Use window selection, state capture, accessibility inspection, keyboard input, and coordinate input. Window enumeration worked; state capture and input consistently failed with the runtime error noted above. A sanitized screenshot was retained as evidence: [01-first-launch-sanitized.png](usability-audit-evidence/2026-08-08/01-first-launch-sanitized.png).
- Exercised organizer behavior with synthetic valid PDFs, a corrupt/truncated PDF, duplicate issue names, mixed magazine prefixes, Unicode/spaced directories, source equal to destination, and 80 small PDFs. This was direct function corroboration in an isolated copy, not a substitute for the blocked UI journey.
- Never read the contents of the repository’s cookie file or any generated cookie file. No login, password, account, upload, purchase, or global network disruption was attempted.

## Persona and task success matrix

| Persona / task | Result | Time | Wrong turns / errors | Confidence |
|---|---|---:|---|---|
| A — launch from the isolated executable and inspect first state | Pass with friction | ~3 s to visible window | No app error; Computer Use capture failed afterward | High for launch state |
| A — choose only Model Railroader, temporary destination, Test mode | Blocked | Not measured | Computer Use input context unavailable | None for UI outcome |
| A — no magazine, invalid folder, browser authentication handoff | Blocked | Not measured | No credentials or browser handoff attempted | None for UI outcome |
| B — relaunch, settings persistence, visible/headless download | Blocked | Not measured | No UI input or restart journey possible | None for UI outcome |
| B — Start/Stop, completion, cache clear, tray, close/recovery | Blocked | Not measured | Worker/tray states were not safely reachable | None for UI outcome |
| C — organizer through direct isolated engine exercise | Pass with friction | 0.036 s for 9 inputs | Corrupt handling, report aggregation, and duplicate clarity failed | High for engine behavior; not a UI result |
| C — 80 small PDFs through direct isolated engine exercise | Pass with friction | 0.306 s | 80/80 progress callbacks and outputs; cancellation not exercised | High for throughput only |
| C — organizer through visible UI, including close during work | Blocked | Not measured | Computer Use input context unavailable | None for UI outcome |

## Prioritized findings

| ID | Severity | Category | Confidence | Affected task |
|---|---|---|---|---|
| UX-01 | P2 | Reliability / data integrity | High | C — corrupt collection |
| UX-02 | P2 | Feedback / collection completeness | High | C — mixed magazines |
| UX-03 | P2 | Conflict handling / trust | High | C — duplicates |
| UX-04 | P2 | Onboarding / authentication terminology | Medium | A — first run |
| A11Y-01 | P2 | Visual accessibility / contrast | High | A/B/C — all states |
| DOC-01 | P2 | Documentation / release readiness | High | A/B — install and recovery |
| VIS-01 | P3 | Visual density / small-window resilience | Medium | A — first state |
| QA-01 | P3 | Testability / baseline setup | High | Release process |

## Detailed findings

### UX-01 — Organize moves corrupt date-named PDFs instead of rejecting them

- **Severity:** P2
- **Category:** Reliability and data integrity
- **Confidence:** High; directly reproduced in an isolated copy of the current source
- **Affected persona/task:** Persona C, Organize with a corrupt/truncated PDF
- **Evidence:** A 34-byte file named `MRR-2024-07.pdf` was moved to `2024/MRR-07-July-2024.pdf`. The mixed run returned 8 moved, 0 already-correct, 1 unrecognized, and 7 metadata updates. The log contained a metadata warning, but the corrupt file remained in the organized output.
- **Reproduction:** Create a truncated PDF with a recognizable date in its filename; run Organize with Auto-detect or MRR selected; inspect the destination and completion summary.
- **Expected:** The file is rejected before mutation, counted as corrupt, and left in the source or placed in an explicit quarantine with a recovery action.
- **Actual:** Filename parsing succeeds; the file is moved; metadata stamping fails; the organizer does not perform `_verify_pdf` before reporting the move.
- **Impact/frequency:** Any corrupt or truncated issue whose filename contains a recognizable date. Users can believe the collection is organized and complete while retaining an unreadable issue. The separate lower-level `rename_and_move` helper did reject the same kind of file, making behavior inconsistent across paths.
- **Design direction:** Add a pre-move integrity gate to the organizer, reuse one transactional move/verify path, show a corrupt count and exact safe next action, and never report a corrupt file as moved successfully.

### UX-02 — Completeness reporting is misleading for mixed-magazine collections

- **Severity:** P2
- **Category:** Feedback and collection completeness
- **Confidence:** High; directly reproduced with mixed prefixes
- **Affected persona/task:** Persona C, a collection containing MRR, TRN, CTT, CTR, and GRW files
- **Evidence:** The synthetic mixed run produced one report line: `2024: missing ['August', 'September', 'October', 'November', 'December']`. It did not produce one completeness result per publication, even though the input contained five publication prefixes and CTR is quarterly.
- **Reproduction:** Put recognizable files for multiple supported magazines into one source folder; run Organize with Auto-detect; inspect the report in the log panel.
- **Expected:** Completeness is grouped by magazine, with each publication’s schedule applied independently.
- **Actual:** The engine aggregates months by year and falls back to a shared monthly expectation when multiple prefixes are observed.
- **Impact/frequency:** Any mixed collection, which the UI and supported-magazine list make plausible. The report can suggest missing issues for the wrong publication and cannot answer “what is missing from Model Railroader?”
- **Design direction:** Partition the inventory by prefix before calculating completeness; show publication, year, expected schedule, present issues, and missing issues in separate sections or a table.

### UX-03 — Duplicate/conflicting issues are silently renamed with `-1`

- **Severity:** P2
- **Category:** Conflict handling and user trust
- **Confidence:** High; directly reproduced with two files resolving to the same canonical issue
- **Affected persona/task:** Persona C, duplicate or conflicting names
- **Evidence:** Two valid files resolving to January 2024 produced both `MRR-01-January-2024.pdf` and `MRR-01-January-2024-1.pdf`. The operation summary counted both as moved; there was no duplicate/conflict count.
- **Reproduction:** Place two different PDFs whose filenames parse to the same issue; run Organize; inspect the destination and log.
- **Expected:** The app previews a conflict and explains whether it will skip, replace, compare, or preserve both files. The user should be able to identify which copy is canonical.
- **Actual:** `_unique_path` silently adds a numeric suffix and the log presents a normal move arrow.
- **Impact/frequency:** Any duplicate or conflicting download. A collection may contain two different files for one issue without the user knowing that a conflict occurred.
- **Design direction:** Add a preflight conflict summary, compare size/hash when useful, use an explicit “duplicate preserved” label, and expose a review list before mutation.

### UX-04 — First-run auth and headless behavior are not self-explanatory

- **Severity:** P2
- **Category:** Onboarding and terminology
- **Confidence:** Medium; first state was observed, but the auth handoff could not be exercised
- **Affected persona/task:** Persona A, first-time subscriber setup
- **Evidence:** The sanitized first-launch screenshot shows the Download panel, a `COOKIE FILE` row, a `Headless browser` checkbox, and a separate `Headless` checkbox in the Download options. There is no visible statement that a subscription is required, that Start opens Chrome for manual login, that cookies are sensitive, or that headless mode requires a valid saved session. The cookie row appears below the primary download controls, which makes it part of the setup flow but not part of the explanation.
- **Reproduction:** Launch with clean app data and read the visible UI without opening the README.
- **Expected:** A novice can identify the required account state, the safe authentication handoff, where the session is saved, and the difference between download headless mode and organizer headless mode.
- **Actual:** The UI exposes fields and duplicated terminology but leaves the core next action to documentation/source knowledge.
- **Impact/frequency:** Every first launch, especially when the default cookie file does not exist or has expired.
- **Design direction:** Add a concise “Requires an active subscription” explanation, an explicit “Start login in Chrome” state, a safe-cookie warning, and distinct labels such as “Hide download browser” and “Hide missing-issue browser.” Explain when headless is unavailable.

### A11Y-01 — Section labels are too low contrast for small all-caps text

- **Severity:** P2
- **Category:** Accessibility and visual hierarchy
- **Confidence:** High; visible in the captured UI and corroborated by the stylesheet colors
- **Affected persona/task:** All personas, all modes
- **Evidence:** The screenshot shows faint all-caps labels such as `MAGAZINES`, `SAVE LOCATION`, `OPTIONS`, and `COOKIE FILE`. The stylesheet uses `#45475a` for section labels against a `#1e1e2e` panel. The computed contrast ratio is approximately 1.80:1, well below the usual 4.5:1 target for small text.
- **Reproduction:** Launch the app at the default size and inspect the section labels at normal viewing distance.
- **Expected:** Group labels remain legible at the current font size and do not require color vision or zoom.
- **Actual:** Labels are visually subordinate to the point that they are easy to miss, particularly against the dark panel.
- **Impact/frequency:** Constant; increases scan time and makes the form hierarchy less accessible.
- **Design direction:** Increase label luminance, use a larger or less tightly tracked label style, and verify the whole palette with a contrast checker in normal and disabled states.

### DOC-01 — Version, build, and authentication documentation contradict the current app

- **Severity:** P2
- **Category:** Onboarding and release readiness
- **Confidence:** High; directly observed in repository documentation and build output
- **Affected persona/task:** Personas A/B, installation, upgrade, recovery, and local build
- **Evidence:** README heading says v1.5.0 while the app title and source say v1.6.0. The README says the local build output is `dist\TrainsDownloader.exe`; `build.bat` prints a single-folder path after invoking `--onefile`. `docs/AUTHENTICATION_GUIDE.md` still describes older CLI commands and flags not presented by the current GUI workflow. The current repository has no packaged executable to reconcile these instructions.
- **Reproduction:** Follow the README and build instructions from a clean checkout; compare the displayed app version and actual build artifact.
- **Expected:** One current version, one supported launch path, one authentication workflow, and a build instruction that matches the produced artifact.
- **Actual:** A novice must reconcile stale version and CLI material with the v1.6.0 GUI.
- **Impact/frequency:** Every new installation, support request, and upgrade. It also weakens confidence that the tested artifact is the intended release.
- **Design direction:** Update all docs from a single version source, separate legacy notes from supported v1.6.x instructions, and add a clean-install smoke test that verifies the documented output path.

### VIS-01 — The default form is dense and long labels have little room

- **Severity:** P3
- **Category:** Visual design and responsive layout
- **Confidence:** Medium; direct default-size screenshot; minimum/intermediate sizes were blocked
- **Affected persona/task:** Persona A, first-run Download setup
- **Evidence:** The 876×759 capture shows five magazine chips, long Browse controls, long path fields, two headless controls, and a large empty log surface competing for attention. The long chip and Browse labels are visually crowded in the capture, and the source sets a minimum size of 640×520 without a demonstrated wrap/overflow strategy for the five-chip row.
- **Reproduction:** Launch at the default window size; inspect the magazine row and file-picker controls. The required 640×520 and intermediate-size checks remain untested.
- **Expected:** All labels remain unambiguous at default and minimum supported sizes, with a clear responsive fallback.
- **Actual:** The default layout is workable but dense; the smallest-size behavior is unknown and the chip row has no visible wrap or scroll affordance.
- **Impact/frequency:** Every setup session on smaller displays or with larger system text.
- **Design direction:** Test the minimum size with UI automation, allow chips to wrap or move to a scrollable selection area, reduce duplicate controls, and reserve more space for status/progress only when work is active.

### QA-01 — The documented automated baseline is not runnable in the checked-in environment

- **Severity:** P3
- **Category:** Release process and testability
- **Confidence:** High
- **Affected task:** Maintenance and release verification
- **Evidence:** The first documented test attempt failed before collection because global pytest could not import `pluggy`; the repository venv contained project runtime dependencies but no pytest. Installing pytest into a temporary dependency directory allowed the existing suite to run: **13 passed, 1 warning**. The warning was a pytest cache-path conflict. The suite covers settings, PDF verification/rename helper behavior, and progress bookkeeping, but has no GUI, organizer, UIA, tray, or cancellation tests.
- **Reproduction:** Use the README test command with the provided venv; then repeat with isolated pytest dependencies.
- **Expected:** A fresh developer or CI environment can install the documented test dependencies and run the baseline without cache/path surprises.
- **Actual:** Test setup requires an extra dependency step and the most important organizer/UI journeys are outside the suite.
- **Impact/frequency:** Every clean checkout and release verification run; increases the chance that regressions like UX-01 remain undetected.
- **Design direction:** Add pytest to a documented dev/test dependency set, isolate cache and basetemp paths, and add organizer, GUI smoke, UIA, cancellation, and clean-start tests.

## Accessibility audit

Directly observed:

- Section labels are visually low contrast (A11Y-01).
- Controls have visible text labels, a clear primary action, and distinguishable selected chip backgrounds in the initial state.
- Disabled Stop is visually differentiated at idle, although disabled-state contrast was not treated as normal text contrast.

Not verifiable because the Computer Use state call failed:

- Windows UI Automation names, roles, values, and states.
- Tab and Shift+Tab order, visible focus, Space/Enter activation, Escape behavior, and keyboard traps.
- Screen-reader association between all-caps labels and the adjacent line edits.
- Tray menu accessibility and modal button order.
- Behavior at 640×520, an intermediate size, maximized, or altered text scaling.

The audit did not change DPI, theme, high contrast, or other global accessibility settings.

## Visual-design audit

The visual system is coherent: dark panel surfaces, blue selected states, a bright primary action, a distinct danger style, and a large log surface. The main visual risks are the 1.80:1 section-label contrast, duplicated headless terminology, and a dense horizontal chip row. The screenshot is representative of the idle Download state only; progress, error, stopped, completed, Organize, modal, and tray states were not reachable through the blocked UI input path.

## Onboarding and documentation

The app title communicates the product purpose and the Download/Organize mode toggle is discoverable. The first screen still assumes too much prior knowledge: it does not state the subscription requirement or explain the Chrome/cookie lifecycle, and it uses two headless controls with overlapping wording. Documentation is not a reliable fallback until the version and launch/authentication contradictions in DOC-01 are corrected.

## Reliability and recovery

The organizer engine correctly handled spaced/Unicode temporary directories, same-source/destination organization, and unrecognized filenames in the isolated exercise. It did not safely handle corrupt date-named PDFs or explain duplicate conflicts. Start/Stop, cancellation, window-close choices, tray restoration, restart persistence, failed network recovery, and browser cleanup were not tested because Computer Use input was unavailable. Source inspection shows a close-in-progress dialog with Minimize to Tray, Stop & Quit, and Cancel, but this is source corroboration, not a behavioral pass.

## Performance

The isolated organizer processed 80 small PDFs in approximately 0.306 seconds, produced 80 output files, and delivered a final progress callback of 80/80. This is a positive engine-throughput signal, not a UI responsiveness result. No long-running visible operation, cancellation, worker shutdown, network timeout, Selenium startup, or progress rendering was safely exercised. Download performance and browser handoff remain untested.

## Positive patterns worth preserving

- Clear Download versus Organize mode separation.
- Magazine selection is explicit and supports all five listed publications.
- Test mode provides a low-risk concept for first-run verification.
- Auto-detect plus explicit magazine prefix is a useful recovery path.
- Primary actions are visually prominent and idle Stop is disabled.
- The log area is large enough to expose operation history, and the engine emits per-file progress.
- Same-source/destination organization worked for the tested synthetic set.
- JSON cookie loading rejects legacy pickle files rather than deserializing them.
- The application was able to launch from the isolated build and displayed a clear v1.6.0 title.

## Findings count by severity

| Severity | Count | IDs |
|---|---:|---|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 6 | UX-01, UX-02, UX-03, UX-04, A11Y-01, DOC-01 |
| P3 | 2 | VIS-01, QA-01 |

## Prioritized remediation roadmap

### Quick wins

- Reject or quarantine corrupt PDFs before Organize moves them; make the corrupt count visible.
- Show duplicate/conflict counts and rename variants explicitly instead of presenting every move as normal.
- Raise section-label contrast and remove ambiguous duplicate Headless wording.
- Add a first-run auth panel explaining subscription, Chrome login, JSON cookies, expiry, and headless prerequisites.
- Synchronize README, authentication guide, build output text, and app version from one source.
- Add pytest to documented test dependencies and fix the cache/basetemp setup.

### Medium changes

- Build completeness reports per magazine and publication schedule, not only per year.
- Add an Organize preview with file classification, integrity status, proposed destination, duplicate conflicts, and an explicit commit action.
- Add accessible names/descriptions and label associations, then verify them with Windows UI Automation.
- Add GUI smoke tests for validation, mode switching, keyboard order, progress, error dialogs, and persistence.
- Add cancellation and close/tray tests around the worker lifecycle.

### Deeper redesigns

- Use a single job/inventory model for download and organization with transactional file moves, integrity verification, conflict records, and resumable recovery.
- Separate per-publication collection state and completeness views.
- Add a release pipeline that builds a versioned artifact, launches it in a clean temporary profile, verifies the documented path, and runs a UIA smoke matrix before release.

## Blocked and untested scenarios

The following were not claimed as passes:

- Mouse or keyboard completion of Download and Organize flows.
- No-magazine and missing/invalid-folder validation dialogs.
- Chrome authentication handoff, cookie expiry, headless operation, or live Test-mode download.
- Start, Stop, completion, cancellation, resumption, cache clearing, and network failure recovery through the UI.
- Close while work is active, Minimize to Tray, restore, Stop & Quit, tray menu, and process cleanup after a real worker run.
- UI Automation tree, screen-reader names, roles, states, Tab order, focus visibility, and keyboard traps.
- 640×520, intermediate, maximized, and text-scaling visual checks.

Exact reason: the Computer Use runtime could list the target window but state capture and every attempted input returned `Error: node_repl exec context not found`. No safe authorized session was available for authentication, so credentials were not requested or entered. These limitations are tooling/authentication constraints, not evidence that the blocked app behaviors pass or fail.

## Automated baseline and final cleanup status

- Initial default-environment test command: blocked before collection by missing/incomplete `pytest`/`pluggy`.
- Isolated test-dependency rerun: **13 passed, 1 warning in 0.28 s**.
- Product code was not modified.
- The only pre-existing Git worktree item observed before the audit was an untracked `.superpowers/` directory. After the audit, the only new repository artifacts are this report and the sanitized evidence directory.
- The temporary PyInstaller build, synthetic PDFs, isolated test dependencies, raw screenshot, and pytest temp directories were removed from the system temp area.
- Both temporary `TrainsDownloader` processes were stopped. No audit app child browser or worker remained, and existing Chrome/Helium processes were not changed.
- No cookie contents, credentials, account identity, real downloads, or user settings were exposed or modified.
