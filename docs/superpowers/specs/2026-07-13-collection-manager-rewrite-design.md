# Collection Manager Rewrite Design

**Date:** 2026-07-13  
**Working product name:** RailShelf  
**Status:** Approved design, pending written-spec review  
**Target:** Windows-first desktop application with portable headless and test environments

## Summary

Rewrite the current single-file Trains.com downloader and organizer as a visual magazine collection manager. The collection is the product's primary experience; downloading, importing, organization, scheduling, and recovery support that experience.

The rewrite starts clean. It does not migrate legacy settings, cookies, progress files, or application databases. Users may import existing PDFs into a new managed library.

The application supports multiple switchable libraries. Each library has its own managed root, inventory, sync rules, schedules, and history. Authentication is shared globally by default, with an optional per-library override.

## Goals

1. Make a user's collection understandable at a glance through cover artwork, completeness summaries, missing issues, and filters.
2. Make every acquisition and organization operation resumable, inspectable, and recoverable.
3. Separate presentation, domain logic, infrastructure, and external-site adapters into independently testable units.
4. Use one portable core from the Windows desktop app, CLI, Windows background service, Docker scheduler, and tests.
5. Support scheduled synchronization while the desktop window is closed.
6. Provide first-class Docker operation for both headless use and automated testing.
7. Keep library files recoverable independently of the application database.

## Non-Goals

- Migrating legacy v1.x configuration, sessions, progress, caches, or databases.
- Supporting arbitrary publications outside the five current Trains.com magazines in the first release.
- Building a browser-based or remotely hosted multi-user application.
- Synchronizing libraries between machines through a proprietary cloud service.
- Editing PDF page content beyond validation and metadata management.
- Hiding subscription requirements or bypassing Trains.com access controls.

## Supported Publications

The initial catalog supports:

- Model Railroader (`MRR`)
- Trains Magazine (`TRN`)
- Classic Toy Trains (`CTT`)
- Classic Trains (`CTR`)
- Garden Railways (`GRW`)

Publication cadence is catalog data, not hard-coded UI behavior. Completeness calculations use issue records discovered from the catalog and validated schedule rules, including quarterly and special issues.

## Technical Architecture

### Technology choices

- Python 3.13 or newer.
- PySide6 and QML for the Windows desktop interface.
- SQLite for persistent application state.
- Playwright-managed Chromium for browser-required acquisition and authentication flows, isolated behind an adapter.
- An HTTP client for direct authenticated catalog and PDF requests.
- `pypdf` for document validation and metadata.
- A PDF rendering library selected during implementation for first-page thumbnails.
- `platformdirs` for OS-appropriate application paths.
- `pytest` for unit, integration, adapter, service, and container tests.
- Docker for the headless scheduler, one-shot CLI operations, and reproducible test runs.

Implementation may change a named library only when a documented proof-of-concept shows it cannot satisfy the corresponding requirement. The module boundaries and behaviors in this spec remain fixed.

### Presentation boundary

QML renders immutable view state, submits typed commands, and receives typed events. It does not scrape pages, rename or move files, edit PDFs, or write SQLite records directly.

Qt-facing models adapt core entities for QML. The core has no dependency on PySide6 or QML.

### Operating surfaces

The shared core is used by three surfaces:

1. **Windows desktop:** visual library, setup, authentication, import previews, schedules, job controls, recovery, and settings.
2. **CLI:** one-shot commands for library scanning, catalog refresh, sync planning, sync execution, import, verification, repair, diagnostics, and schedule inspection.
3. **Scheduler host:** a Windows background service or long-running Docker process that evaluates and executes persisted schedules.

### Core modules

- `catalog`: publications, issue metadata, expected cadence, remote identifiers, and cover sources.
- `libraries`: profiles, managed roots, inventory scans, library switching, and completeness calculations.
- `imports`: copy/move previews, duplicate detection, normalization, transactional commits, and rollback records.
- `downloads`: sync planning, persistent queues, item state transitions, retry, resume, pause, and cancellation.
- `acquisition`: authenticated HTTP and isolated browser fallback.
- `documents`: PDF validation, metadata, canonical naming, thumbnail generation, and quarantine.
- `scheduling`: rules, triggers, next-run calculation, leases, job creation, and missed-run policy.
- `authentication`: shared session storage and optional library overrides.
- `history`: structured user-visible events, diagnostics, and redacted support bundles.

Infrastructure adapters implement SQLite repositories, filesystem operations, clocks, HTTP, Chromium, Windows service integration, and container process hosting.

## Persistence and Managed Storage

### Application data

On Windows, application configuration, SQLite state, authentication data, logs, diagnostics, and cached remote artwork live under the appropriate per-user application-data directories. They are never stored beside the executable.

In Docker, equivalent state is mounted at `/config`. Library roots are mounted below `/libraries`. The container runs as a non-root user, and its UID/GID can be configured for host-volume compatibility.

Authentication secrets are encrypted using Windows DPAPI for the desktop/service installation. In Docker, secrets are supplied through mounted secret files or environment references and are never written into library roots or logs.

### Main entities

- `Library`: identity, display name, managed root, selected publications, authentication override, and status.
- `Publication`: prefix, title, catalog location, cadence, and active state.
- `Issue`: publication, remote identity, date/label, type, source URLs, cover metadata, and catalog state.
- `Asset`: issue association, canonical file path, hash, size, page count, verification state, and thumbnail state.
- `SyncRule`: library, publications, year bounds, special-issue policy, and storage limit.
- `Schedule`: library, recurrence, time zone, enabled state, next run, and missed-run policy.
- `Job`: operation type, owner, state, timestamps, progress, and summary.
- `JobItem`: issue or file target, state, attempt count, result, and actionable failure.
- `AuthSession`: scope, account label, protected secret reference, validation time, and state.
- `Event`: structured severity, category, user message, diagnostic code, job association, and redacted context.

### Recoverability

SQLite is authoritative during normal operation, but a library can be reconstructed by scanning its managed PDFs. Database-only information such as historical run detail and schedules is not inferred from files and must be restored from application-data backups.

Every library root contains a small, non-secret identity manifest recording the library UUID and format version. It contains no authentication data or machine-specific absolute paths.

### Canonical layout

```text
<library>/
  .railshelf/
    library.json
  MRR/
    2026/
      MRR-2026-01-January.pdf
  TRN/
  CTT/
  CTR/
  GRW/
  Quarantine/
```

Regular issues use `<PREFIX>-<YEAR>-<NUMBER>-<LABEL>.pdf`. Special issues use `<PREFIX>-<YEAR>-SPECIAL-<normalized-title>.pdf`. The naming parser and formatter are versioned so a future format change can be planned and previewed.

Temporary downloads are placed on the same filesystem as their final destination so final commits can use atomic replacement. They are hidden from the collection until verification succeeds.

## Library Experience

### Navigation

The primary navigation contains:

- Library
- Downloads
- Schedule
- Import & Organize
- Problems
- Run History
- Settings

A persistent library selector switches profiles. Switching libraries changes collection content, jobs, rules, schedules, and history without changing the global authentication default.

### Library home

The default screen is a cover grid with:

- Owned, completeness, missing, and queued summaries.
- Publication, year, ownership, missing-only, and special-issue filters.
- Search by publication, year, month, title, and issue label.
- Cover cards with owned, missing, queued, downloading, failed, or quarantined states.
- An activity rail showing active jobs, actionable problems, and the next scheduled run.
- A Sync Now action that generates and previews a plan before execution when the plan differs materially from the last approved rule set.

Selecting an issue opens details including metadata, source, local file, verification result, history, and applicable actions.

### Artwork

Owned issues use a locally generated thumbnail of the PDF's first page. Missing issues use remote Trains.com cover artwork when available. If neither source is available, the UI renders a polished placeholder using publication and issue metadata.

Remote artwork and generated thumbnails are cached locally. The library remains browsable offline. Missing artwork never blocks scanning, sync planning, or downloads.

### Visual system

The Windows-first design uses restrained graphite surfaces, a rail-blue accent, soft elevation, rounded panels, and cover art as the dominant color source. It uses Segoe UI Variable on Windows and suitable platform fallbacks elsewhere.

Light and dark themes follow the Windows setting by default and support a manual override. The activity rail collapses before primary library content becomes cramped.

All screens support keyboard navigation, visible focus, screen-reader labels, scalable text, high-contrast compatibility, and reduced motion. Critical state is never communicated through color alone. Raw logs remain available under diagnostics, while normal screens show concise events and corrective actions.

## Import and Organization

Existing PDFs are imported into the managed structure. The import workflow:

1. Scans a selected source without modifying it.
2. Detects publication and issue identity from filenames, metadata, and PDF text where available.
3. Shows recognized files, unrecognized files, duplicates, conflicts, proposed canonical names, and destination paths.
4. Lets the user select Copy or Move for that import.
5. Requires confirmation of the preview before mutation.
6. Copies or moves to temporary destinations, verifies content, stamps metadata, generates thumbnails, then commits atomically.
7. Leaves unrecognized or failed files at the source and records an actionable result.

Duplicate detection uses issue identity and content hashes. Exact duplicates are skipped. Different PDFs that claim the same issue are presented as conflicts; the app never silently overwrites an owned issue.

## Catalog and Sync Planning

Each library has configurable sync rules:

- Selected publications.
- Inclusive start and end years; the end may be `current`.
- Include or exclude special issues.
- Optional maximum library storage.

Before a schedule is enabled, the app previews the issues the current rules would acquire and estimates known storage where source sizes are available. Rules never default to downloading every historical issue without explicit user approval.

The sync data flow is:

1. Refresh the remote catalog.
2. Compare catalog issues with verified local assets.
3. Build a deterministic plan.
4. Present the plan when interactive approval is required.
5. Persist a job and its items.
6. Acquire, verify, commit, index, and generate artwork.
7. Record a structured summary and leave failures actionable.

Scheduled runs execute the last approved rules without requiring the desktop window. A rule edit requires a new preview before its schedule becomes active again.

## Scheduling

Schedules are configured inside the desktop application and persisted centrally. The Windows service and Docker scheduler use the same recurrence engine and database semantics.

Each schedule records a named time zone and handles daylight-saving transitions explicitly. If a scheduled time is skipped by a clock change, it runs at the next valid local time. If the host was offline, the default missed-run policy executes one catch-up run at startup rather than replaying every missed occurrence.

Only one active mutation job may own a library. A new scheduled run coalesces with an equivalent queued run or waits behind a different active job. It never launches a competing writer.

The desktop can pause schedules globally or per library, run a schedule immediately, preview its current plan, and inspect its prior outcomes.

## Authentication

Authentication is global by default and may be overridden per library. The application stores browser session material, not account passwords.

Interactive sign-in opens an isolated Chromium window. Successful sessions are validated before being marked ready. Expired sessions pause affected jobs and produce a Sign In Again action. Other libraries using valid overrides continue operating.

Authentication values are excluded from logs, exceptions shown to users, diagnostic bundles, library manifests, and command histories.

## Job State and Concurrency

Jobs use explicit states: `planned`, `queued`, `running`, `pausing`, `paused`, `cancelling`, `cancelled`, `completed`, `completed_with_errors`, and `failed`.

Job items use explicit states: `queued`, `acquiring`, `verifying`, `committing`, `completed`, `retry_wait`, `paused`, `cancelled`, `quarantined`, and `failed`.

Desktop, service, CLI, and Docker processes coordinate through database leases and filesystem library locks. Leases have owner identities and heartbeats. Stale leases may be reclaimed only after verifying that the owning process is no longer active according to the host adapter.

Cancellation is cooperative. Pending items become cancelled immediately. Active items stop at a safe boundary, delete incomplete temporary files when safe, and never expose an unverified final PDF.

## Reliability and Error Handling

- Downloads stream to temporary files and enforce configured timeouts and size limits.
- Verification checks file signature, parseability, encryption state, and at least one readable page.
- Valid files commit atomically; invalid files move to `Quarantine/` with a sidecar reason record and never count as owned.
- Transient failures use bounded exponential backoff with jitter. Retry policy is recorded per job item.
- Authentication, disk-space, permission, duplicate, destination-conflict, markup-change, and verification failures use distinct diagnostic codes.
- User-facing errors provide specific actions such as Retry, Sign In, Choose New Folder, Free Space, Review Duplicate, Open Quarantine, or Export Diagnostics.
- A failed catalog or acquisition adapter cannot mutate existing verified assets.
- Run history supports retrying one failed item, all retryable failures, or a complete prior plan.
- Exported diagnostic bundles redact tokens, cookies, account identifiers, and user-specific path prefixes.

Raw exception text is retained only in protected diagnostics. Broad exceptions are not silently ignored.

## Testing Strategy

### Unit tests

Cover naming, catalog matching, completeness, sync planning, schedule calculation, duplicate policy, retry policy, state transitions, redaction, and path normalization.

### Integration tests

Temporary managed libraries, real SQLite repositories, generated PDFs, import copy/move behavior, verification, quarantine, atomic commit, crash recovery, leases, and database rebuild scans.

### Adapter contract tests

Saved and sanitized HTML/JSON fixtures cover catalog pagination, issue parsing, direct PDFs, flipbooks, missing artwork, and known site variants.

### Fake-site tests

A local fake site simulates authentication expiry, redirects, pagination, HTTP failures, timeouts, corrupt and truncated PDFs, interrupted transfers, rate limiting, and changed markup. These tests do not require a Trains.com subscription.

### UI tests

QML model and smoke tests cover navigation, library switching, search, filters, sync preview, job controls, schedule editing, import preview, and recovery actions. Accessibility metadata and keyboard traversal are verified.

### Service and container tests

Windows tests cover service installation boundaries, scheduled job creation, desktop/service coordination, locking, stop/start, and restart recovery. Docker tests use temporary `/config` and `/libraries` volumes and exercise CLI commands plus the long-running scheduler.

### Live-site tests

A small opt-in smoke suite may run against the live service using maintainer-provided authentication. It is excluded from ordinary CI and never runs for untrusted contributions.

## Packaging and Delivery

The Windows release uses a versioned installer with Start Menu integration, clean upgrade and uninstall behavior, and optional background-service registration. The installer does not require Docker.

Docker publishes versioned images for `linux/amd64` and `linux/arm64`, runs as non-root, exposes a health check, and documents `/config`, `/libraries`, time-zone, and secret inputs.

Continuous integration runs unit and integration tests on every change, Windows UI and service tests on Windows runners, and container tests on Linux. Release artifacts are produced only after required checks pass.

Docker Desktop may be installed locally during implementation if no working Docker-compatible runtime is available and container verification requires it.

## Implementation Boundaries

The rewrite is delivered as vertical slices rather than a big-bang replacement:

1. Core entities, SQLite repositories, library profiles, and managed scanning.
2. Catalog fixtures, sync planning, and deterministic completeness.
3. Import preview and managed commit pipeline.
4. Acquisition adapters, verification, queue persistence, and recovery.
5. QML application shell and visual library.
6. Authentication and issue acquisition workflows.
7. Scheduling, Windows service host, and Docker scheduler.
8. Diagnostics, accessibility, packaging, and release automation.

Each slice must produce independently testable behavior. No slice may restore direct QML-to-filesystem, QML-to-SQLite, or presentation-to-scraper coupling.

## Acceptance Criteria

The rewrite is ready for its first stable release when:

1. A user can create, switch, scan, and remove library profiles without deleting library files.
2. A user can import PDFs through a complete preview using Copy or Move and obtain canonical, verified managed files.
3. The library home accurately distinguishes owned, missing, queued, failed, and quarantined issues and remains useful offline.
4. A user can configure per-library sync rules and preview their results before enabling a schedule.
5. Downloads resume safely after desktop, service, Windows, or container restart.
6. The Windows service runs schedules while the desktop window is closed.
7. The Docker scheduler performs the same approved sync semantics using mounted volumes.
8. Authentication expiry pauses affected work without corrupting jobs or blocking libraries with valid overrides.
9. Invalid PDFs never count as owned and are recoverable through the Problems and Quarantine workflows.
10. Desktop, service, CLI, and Docker cannot concurrently mutate the same library.
11. The database can rebuild collection inventory from managed files.
12. Automated tests cover the core state machine, import pipeline, acquisition failure modes, scheduler, Docker host, and primary QML workflows.
13. The Windows installer supports clean installation, upgrade, optional service setup, and uninstall.
14. Diagnostic exports contain no session secrets or unredacted user-specific paths.

