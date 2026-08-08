# Collection Manager Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the v1.6 single-file downloader with a Windows-first visual magazine collection manager whose shared Python core also powers a CLI, Windows scheduler service, Docker scheduler, and deterministic test suite.

**Architecture:** Build a `src/railshelf` package around pure domain models and typed service interfaces. SQLite repositories and filesystem/browser adapters sit below application services; PySide6/QML, CLI, Windows service, and Docker are thin operating surfaces. Keep `trains_app.py` runnable until the final cutover so every vertical slice can be reviewed without losing the current release.

**Tech Stack:** Python 3.13+, PySide6/QML, SQLite, httpx, Playwright Chromium, pypdf, PyMuPDF, platformdirs, APScheduler, Typer, pytest, pytest-qt, pytest-asyncio, Ruff, mypy, PyInstaller, WiX Toolset, Docker.

## Global Constraints

- Start clean; do not migrate v1.x settings, cookies, progress files, or databases.
- Support multiple switchable managed libraries.
- Share authentication globally by default and permit a per-library override.
- Keep the core independent of PySide6/QML.
- Never write application state, credentials, caches, or logs beside the executable.
- Never expose an unverified PDF as an owned issue.
- Permit only one mutation owner per library across desktop, service, CLI, and Docker.
- Keep SQLite inventory rebuildable from managed PDFs and `.railshelf/library.json`.
- Use deterministic fake-site and sanitized-fixture tests for ordinary CI; live-site tests are opt-in.
- Run Docker processes as non-root with `/config` and `/libraries` volumes.
- Keep the current application runnable until Task 14 performs the release cutover.

---

## Planned File Structure

```text
pyproject.toml                         # package metadata, dependencies, tools, entry points
src/railshelf/
  __init__.py                          # version only
  paths.py                             # platform-specific application directories
  domain/
    enums.py                           # job, item, asset, auth, and issue states
    models.py                          # immutable domain dataclasses
    errors.py                          # diagnostic codes and actionable failures
  persistence/
    database.py                        # connection lifecycle and transactions
    migrations.py                      # ordered SQLite schema migrations
    repositories.py                    # typed repository implementations
  storage/
    layout.py                          # canonical paths and manifests
    locks.py                           # cross-process library mutation locks
    scanner.py                         # rebuild inventory from managed files
  catalog/
    ports.py                           # catalog adapter protocol
    trains.py                          # Trains.com fixture/live adapter
    completeness.py                    # catalog versus verified assets
  imports/
    planner.py                         # non-mutating import plan
    executor.py                        # copy/move, verify, and atomic commit
  sync/
    planner.py                         # deterministic sync plans
  jobs/
    state_machine.py                   # legal transitions
    runner.py                          # persistent execution and recovery
    leases.py                          # owner heartbeat and stale recovery
  acquisition/
    http.py                            # authenticated direct downloads
    browser.py                         # Playwright fallback
  documents/
    pdf.py                             # verification and metadata
    artwork.py                         # local thumbnails and remote cache
  auth/
    service.py                         # shared/override session selection
    windows_dpapi.py                   # Windows secret protection
    file_secrets.py                    # Docker secret-file provider
  scheduling/
    engine.py                          # recurrence and missed-run behavior
    host.py                            # long-running schedule evaluator
  application/
    services.py                        # use-case facade shared by all surfaces
    events.py                          # structured redacted event publishing
  desktop/
    main.py                            # QApplication bootstrap
    bridge.py                          # typed command/event bridge
    models.py                          # QAbstractItemModel adapters
    qml/
      Main.qml                         # application shell
      components/                     # reusable design-system components
      pages/                           # Library, Downloads, Schedule, Import, Problems, History, Settings
  service/
    windows.py                         # Windows service host
  cli.py                               # Typer commands
tests/
  unit/                               # pure domain/service tests
  integration/                        # SQLite and managed-library tests
  contract/fixtures/                  # sanitized remote response fixtures
  contract/                           # catalog adapter contracts
  fake_site/                          # local failure-mode server
  ui/                                 # QML model and smoke tests
  service/                            # scheduler/service integration tests
docker/
  Dockerfile                          # runtime image
  compose.test.yml                    # local/CI container tests
packaging/windows/                    # PyInstaller and WiX sources
```

---

### Task 1: Package Foundation and Quality Gates

**Files:**
- Create: `pyproject.toml`
- Create: `src/railshelf/__init__.py`
- Create: `src/railshelf/paths.py`
- Create: `tests/unit/test_paths.py`
- Create: `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `railshelf.__version__: str`
- Produces: `AppPaths.from_environment(app_name: str = "RailShelf") -> AppPaths`
- Produces: console entry points `railshelf`, `railshelf-desktop`, and `railshelf-scheduler`

- [ ] **Step 1: Write the failing application-path test**

```python
# tests/unit/test_paths.py
from pathlib import Path

from railshelf.paths import AppPaths


def test_paths_use_explicit_config_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RAILSHELF_CONFIG_DIR", str(tmp_path / "config"))
    paths = AppPaths.from_environment()
    assert paths.config_dir == tmp_path / "config"
    assert paths.database == tmp_path / "config" / "railshelf.sqlite3"
    assert paths.cache_dir != paths.config_dir
    assert paths.log_dir != paths.config_dir
```

- [ ] **Step 2: Run the test and verify the package does not exist**

Run: `python -m pytest tests/unit/test_paths.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'railshelf'`.

- [ ] **Step 3: Add package metadata and the minimal path implementation**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "railshelf"
version = "2.0.0a1"
requires-python = ">=3.13"
dependencies = [
  "APScheduler>=3.11,<4",
  "httpx>=0.28,<1",
  "platformdirs>=4.3,<5",
  "playwright>=1.52,<2",
  "pydantic>=2.11,<3",
  "pypdf>=5.6,<6",
  "PyMuPDF>=1.26,<2",
  "selectolax>=0.3.29,<1",
  "typer>=0.16,<1",
]

[project.optional-dependencies]
desktop = ["PySide6>=6.9,<7"]
dev = [
  "mypy>=1.16,<2",
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.0,<2",
  "pytest-qt>=4.4,<5",
  "PySide6>=6.9,<7",
  "respx>=0.22,<1",
  "ruff>=0.12,<1",
  "starlette>=0.47,<1",
  "uvicorn>=0.35,<1",
]
windows = ["pywin32>=310; platform_system == 'Windows'"]

[project.scripts]
railshelf = "railshelf.cli:app"
railshelf-desktop = "railshelf.desktop.main:main"
railshelf-scheduler = "railshelf.scheduling.host:main"

[tool.hatch.build.targets.wheel]
packages = ["src/railshelf"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
markers = ["live: requires maintainer credentials and the live service"]

[tool.ruff]
target-version = "py313"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.13"
strict = true
packages = ["railshelf"]
```

```python
# src/railshelf/__init__.py
__version__ = "2.0.0a1"
```

```python
# src/railshelf/paths.py
from dataclasses import dataclass
import os
from pathlib import Path

from platformdirs import user_cache_path, user_config_path, user_log_path


@dataclass(frozen=True, slots=True)
class AppPaths:
    config_dir: Path
    cache_dir: Path
    log_dir: Path
    database: Path

    @classmethod
    def from_environment(cls, app_name: str = "RailShelf") -> "AppPaths":
        config = Path(os.environ.get("RAILSHELF_CONFIG_DIR", user_config_path(app_name)))
        cache = Path(os.environ.get("RAILSHELF_CACHE_DIR", user_cache_path(app_name)))
        logs = Path(os.environ.get("RAILSHELF_LOG_DIR", user_log_path(app_name)))
        return cls(config, cache, logs, config / "railshelf.sqlite3")

    def create(self) -> None:
        for directory in (self.config_dir, self.cache_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Add CI and ignore generated visual/session data**

Configure `.github/workflows/ci.yml` with Python 3.13 jobs on `windows-latest` and `ubuntu-latest` that install `.[dev]` and run `ruff check .`, `mypy src`, and `pytest -m "not live"`. Add `.superpowers/`, `.coverage`, `htmlcov/`, `.mypy_cache/`, `.ruff_cache/`, and `*.sqlite3*` to `.gitignore`.

- [ ] **Step 5: Verify the foundation**

Run: `python -m pip install -e ".[desktop,dev,windows]"`

Run: `python -m pytest tests/unit/test_paths.py -q`

Run: `python -m ruff check src tests`

Run: `python -m mypy src`

Expected: one passing test and zero lint/type errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/railshelf tests/unit/test_paths.py .github/workflows/ci.yml .gitignore
git commit -m "build: establish RailShelf package and quality gates"
```

---

### Task 2: Domain Model and SQLite Schema

**Files:**
- Create: `src/railshelf/domain/enums.py`
- Create: `src/railshelf/domain/models.py`
- Create: `src/railshelf/domain/errors.py`
- Create: `src/railshelf/persistence/database.py`
- Create: `src/railshelf/persistence/migrations.py`
- Create: `src/railshelf/persistence/repositories.py`
- Create: `tests/integration/test_database.py`

**Interfaces:**
- Produces: immutable `Library`, `Publication`, `Issue`, `Asset`, `SyncRule`, `Schedule`, `Job`, `JobItem`, and `Event` dataclasses
- Produces: `Database.open(path: Path) -> Database`
- Produces: `LibraryRepository`, `IssueRepository`, `AssetRepository`, `JobRepository`, `ScheduleRepository`

- [ ] **Step 1: Write the failing migration and repository test**

```python
# tests/integration/test_database.py
from pathlib import Path
from uuid import uuid4

from railshelf.domain.models import Library
from railshelf.persistence.database import Database
from railshelf.persistence.repositories import LibraryRepository


def test_migration_and_library_roundtrip(tmp_path: Path) -> None:
    db = Database.open(tmp_path / "state.sqlite3")
    repo = LibraryRepository(db)
    library = Library(id=uuid4(), name="Main", root=tmp_path / "library")
    repo.add(library)
    assert repo.get(library.id) == library
    assert db.schema_version() == 1
```

- [ ] **Step 2: Verify the new modules are missing**

Run: `python -m pytest tests/integration/test_database.py -q`

Expected: FAIL importing `railshelf.domain.models`.

- [ ] **Step 3: Define states, models, and actionable errors**

Use `StrEnum` values from the specification. Define dataclasses as frozen and slotted. Store timestamps as timezone-aware UTC `datetime` values and identifiers as UUIDs.

```python
# src/railshelf/domain/enums.py
from enum import StrEnum


class JobState(StrEnum):
    PLANNED = "planned"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class ItemState(StrEnum):
    QUEUED = "queued"
    ACQUIRING = "acquiring"
    VERIFYING = "verifying"
    COMMITTING = "committing"
    COMPLETED = "completed"
    RETRY_WAIT = "retry_wait"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    QUARANTINED = "quarantined"
    FAILED = "failed"
```

```python
# src/railshelf/domain/models.py
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Library:
    id: UUID
    name: str
    root: Path
    auth_override_id: UUID | None = None
    enabled: bool = True
```

`domain/errors.py` must define these exact `DiagnosticCode` values: `AUTH_EXPIRED`, `DISK_FULL`, `PERMISSION_DENIED`, `EXACT_DUPLICATE`, `ISSUE_CONFLICT`, `MARKUP_CHANGED`, `NETWORK_TRANSIENT`, `PDF_INVALID`, `LOCKED`, `INVALID_CONFIG`, and `STORAGE_LIMIT`. `ActionableError` carries a safe message, diagnostic code, retryable flag, and tuple of action identifiers; it never embeds cookies or raw response bodies.

- [ ] **Step 4: Add versioned migrations and typed repositories**

Migration 1 creates normalized tables with foreign keys enabled, WAL mode, unique remote issue identities, unique `(library_id, issue_id)` assets, job/item indexes, and an `events` table. `Database.transaction()` must use `BEGIN IMMEDIATE` for write operations and roll back on every exception.

Repository methods accept and return domain types, not SQLite rows. Store paths as UTF-8 strings and convert them at the boundary. Store datetimes in RFC 3339 UTC form.

- [ ] **Step 5: Verify schema, foreign keys, rollback, and repository round trips**

Add tests for all repositories, a failed-transaction rollback, and migration idempotence.

Run: `python -m pytest tests/integration/test_database.py -q`

Expected: all database tests pass.

Run: `python -m ruff check src/railshelf/domain src/railshelf/persistence tests/integration/test_database.py && python -m mypy src`

Expected: zero errors.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/domain src/railshelf/persistence tests/integration/test_database.py
git commit -m "feat: add domain model and SQLite repositories"
```

---

### Task 3: Managed Libraries, Canonical Layout, and Rebuild Scanning

**Files:**
- Create: `src/railshelf/storage/layout.py`
- Create: `src/railshelf/storage/locks.py`
- Create: `src/railshelf/storage/scanner.py`
- Create: `src/railshelf/application/services.py`
- Create: `tests/unit/test_layout.py`
- Create: `tests/integration/test_library_scanner.py`

**Interfaces:**
- Produces: `canonical_issue_path(library_root: Path, issue: Issue) -> Path`
- Produces: `LibraryManifest.create(root: Path, library_id: UUID) -> LibraryManifest`
- Produces: `LibraryMutationLock.acquire(root: Path, owner: str) -> ContextManager[None]`
- Produces: `LibraryScanner.scan(library: Library) -> ScanResult`
- Produces: `ApplicationServices.create_library(name: str, root: Path) -> Library`

- [ ] **Step 1: Write failing canonical-path and rebuild tests**

```python
# tests/unit/test_layout.py
from datetime import date
from pathlib import Path
from uuid import uuid4

from railshelf.domain.models import Issue
from railshelf.storage.layout import canonical_issue_path


def test_regular_issue_uses_stable_canonical_name(tmp_path: Path) -> None:
    issue = Issue(
        id=uuid4(), publication_prefix="MRR", remote_id="mrr-2026-01",
        published_on=date(2026, 1, 1), number=1, label="January", special=False,
    )
    assert canonical_issue_path(tmp_path, issue) == (
        tmp_path / "MRR" / "2026" / "MRR-2026-01-January.pdf"
    )
```

```python
# tests/integration/test_library_scanner.py
def test_scan_rebuilds_verified_asset_from_managed_pdf(managed_library, valid_pdf) -> None:
    target = managed_library.root / "MRR/2026/MRR-2026-01-January.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(valid_pdf)
    result = managed_library.scanner.scan(managed_library.library)
    assert result.verified == 1
    assert result.unrecognized == ()
```

- [ ] **Step 2: Run both tests and verify failure**

Run: `python -m pytest tests/unit/test_layout.py tests/integration/test_library_scanner.py -q`

Expected: FAIL because storage modules do not exist.

- [ ] **Step 3: Implement safe layout and manifest behavior**

Normalize labels to ASCII-safe hyphenated components, reject reserved Windows names, reject path traversal, and keep the final path below the resolved library root. Write `.railshelf/library.json` atomically with exactly `library_id` and `format_version`.

Use `Quarantine/<timestamp>-<original-name>` for invalid files and a neighboring `.reason.json` containing only a diagnostic code, safe message, source name, and timestamp.

- [ ] **Step 4: Implement locks and scanning**

Use atomic lock-file creation at `.railshelf/mutation.lock`. The JSON lock record contains owner, PID, hostname, and heartbeat time. Do not reclaim a lock solely because it is old; call an injected `OwnerProbe` to determine whether the host owner is dead.

The scanner recognizes only canonical managed paths, hashes files in chunks, invokes the PDF verifier from Task 8 through a protocol, upserts verified assets, and reports unrecognized or invalid files without deleting them.

- [ ] **Step 5: Verify Windows-safe names, special issues, lock contention, stale recovery, and rebuilds**

Run: `python -m pytest tests/unit/test_layout.py tests/integration/test_library_scanner.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/storage src/railshelf/application/services.py tests/unit/test_layout.py tests/integration/test_library_scanner.py
git commit -m "feat: manage library layouts and rebuild inventory"
```

---

### Task 4: Catalog Adapter and Completeness Engine

**Files:**
- Create: `src/railshelf/catalog/ports.py`
- Create: `src/railshelf/catalog/trains.py`
- Create: `src/railshelf/catalog/completeness.py`
- Create: `tests/contract/fixtures/mrr_archive_page_1.html`
- Create: `tests/contract/fixtures/mrr_issue_january_2026.html`
- Create: `tests/contract/test_trains_catalog.py`
- Create: `tests/unit/test_completeness.py`

**Interfaces:**
- Produces: `CatalogPort.refresh(publications: frozenset[str]) -> CatalogRefresh`
- Produces: `TrainsCatalogClient(http: httpx.Client, base_url: str) -> TrainsCatalogClient`
- Produces: `calculate_completeness(issues: Iterable[Issue], assets: Iterable[Asset]) -> Completeness`

- [ ] **Step 1: Add sanitized fixtures and a failing contract test**

The fixtures must contain only the minimal DOM needed for pagination, issue identity, publication, date, special status, issue URL, cover URL, direct-PDF metadata, and flipbook marker. Remove analytics, account values, and unrelated copyrighted page text.

```python
# tests/contract/test_trains_catalog.py
def test_archive_fixture_produces_stable_issue_identity(fixture_http) -> None:
    refresh = fixture_http.catalog.refresh(frozenset({"MRR"}))
    issue = refresh.issues[0]
    assert issue.remote_id == "mrr-2026-01"
    assert issue.publication_prefix == "MRR"
    assert issue.number == 1
    assert issue.label == "January"
    assert issue.special is False
```

- [ ] **Step 2: Verify the contract fails**

Run: `python -m pytest tests/contract/test_trains_catalog.py tests/unit/test_completeness.py -q`

Expected: FAIL importing catalog modules.

- [ ] **Step 3: Implement the adapter protocol and fixture-backed parser**

The adapter returns domain `Issue` objects and adapter diagnostics. It follows bounded pagination, canonicalizes URLs, deduplicates by remote ID, and emits `MARKUP_CHANGED` when required selectors disappear instead of returning an empty successful catalog.

Keep selectors in one `TrainsSelectors` dataclass. Do not import Playwright here; catalog HTTP and browser acquisition are separate adapters.

- [ ] **Step 4: Implement deterministic completeness**

Completeness counts an issue as owned only when a verified asset exists for that library and issue. Return totals and grouped missing issue IDs by publication and year. Catalog absence is `unknown`, not `complete`.

- [ ] **Step 5: Test all five publications, quarterly cadence, specials, duplicate pages, and markup changes**

Run: `python -m pytest tests/contract tests/unit/test_completeness.py -q`

Expected: all tests pass without network access.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/catalog tests/contract tests/unit/test_completeness.py
git commit -m "feat: add fixture-tested catalog and completeness engine"
```

---

### Task 5: Import Preview and Atomic Managed Commit

**Files:**
- Create: `src/railshelf/imports/planner.py`
- Create: `src/railshelf/imports/executor.py`
- Create: `tests/unit/test_import_planner.py`
- Create: `tests/integration/test_import_executor.py`

**Interfaces:**
- Produces: `ImportPlanner.plan(source: Path, library: Library) -> ImportPlan`
- Produces: `ImportExecutor.execute(plan: ImportPlan, mode: ImportMode) -> ImportResult`
- Produces: `ImportMode.COPY` and `ImportMode.MOVE`

- [ ] **Step 1: Write failing duplicate/conflict preview tests**

```python
def test_plan_separates_exact_duplicate_from_issue_conflict(import_context) -> None:
    plan = import_context.plan(
        source_files={
            "same.pdf": import_context.owned_bytes,
            "different.pdf": import_context.different_pdf_for_owned_issue,
        }
    )
    assert [item.disposition for item in plan.items] == [
        ImportDisposition.EXACT_DUPLICATE,
        ImportDisposition.CONFLICT,
    ]
    assert plan.requires_confirmation
```

- [ ] **Step 2: Verify planning tests fail**

Run: `python -m pytest tests/unit/test_import_planner.py -q`

Expected: FAIL because `railshelf.imports` does not exist.

- [ ] **Step 3: Implement a non-mutating planner**

For each PDF, compute a chunked SHA-256, parse canonical and legacy-friendly filename candidates, inspect metadata/text through a `DocumentInspector` protocol, and return one of `READY`, `UNRECOGNIZED`, `EXACT_DUPLICATE`, `CONFLICT`, or `INVALID`. Every ready item includes its exact source, temporary destination, final destination, issue identity, and proposed metadata.

- [ ] **Step 4: Implement transactional copy and move execution**

For each ready item: copy bytes to a same-filesystem temporary path, verify, stamp metadata, render artwork, atomically replace the final path, and commit the asset record. In Move mode, delete the source only after the final asset and database record commit. On any failure, remove the temporary file, keep the source, and record an actionable item result.

- [ ] **Step 5: Test preview immutability, copy, move, rollback, conflicts, and disk errors**

Run: `python -m pytest tests/unit/test_import_planner.py tests/integration/test_import_executor.py -q`

Expected: all tests pass; tests assert no source mutation occurs during planning or failed execution.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/imports tests/unit/test_import_planner.py tests/integration/test_import_executor.py
git commit -m "feat: preview and execute managed PDF imports"
```

---

### Task 6: Sync Rules and Deterministic Planning

**Files:**
- Create: `src/railshelf/sync/planner.py`
- Create: `tests/unit/test_sync_planner.py`

**Interfaces:**
- Produces: `SyncPlanner.build(library: Library, rule: SyncRule, catalog: CatalogSnapshot, assets: Sequence[Asset]) -> SyncPlan`
- Produces: immutable `SyncPlan` containing ordered `SyncPlanItem` values and an approval fingerprint

- [ ] **Step 1: Write failing rule-boundary and fingerprint tests**

```python
def test_plan_filters_publication_year_and_specials(sync_fixture) -> None:
    plan = sync_fixture.plan(
        publications=frozenset({"MRR"}), start_year=2024,
        end_year=2026, include_specials=False,
    )
    assert all(item.issue.publication_prefix == "MRR" for item in plan.items)
    assert all(2024 <= item.issue.published_on.year <= 2026 for item in plan.items)
    assert all(not item.issue.special for item in plan.items)


def test_equivalent_inputs_produce_same_approval_fingerprint(sync_fixture) -> None:
    assert sync_fixture.plan().approval_fingerprint == sync_fixture.plan().approval_fingerprint
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/unit/test_sync_planner.py -q`

Expected: FAIL importing `SyncPlanner`.

- [ ] **Step 3: Implement stable planning**

Sort items by publication, date, issue number, then remote ID. Exclude verified owned issues and include quarantined/failed issues only when policy allows retry. Calculate known total bytes and unknown-size count. Generate the approval fingerprint from canonical JSON containing library ID, rule values, catalog revision, and ordered issue IDs.

- [ ] **Step 4: Enforce storage limits and approval semantics**

If known bytes exceed the configured maximum, return a blocked plan with `STORAGE_LIMIT`. If unknown sizes could cross the limit, mark the plan as requiring explicit approval. Editing a rule invalidates the prior fingerprint and disables its schedule until the new fingerprint is approved.

- [ ] **Step 5: Verify deterministic planning**

Run: `python -m pytest tests/unit/test_sync_planner.py -q`

Expected: all tests pass, including reordered-input property cases.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/sync tests/unit/test_sync_planner.py
git commit -m "feat: build deterministic sync plans"
```

---

### Task 7: Persistent Job State Machine, Leases, and Recovery

**Files:**
- Create: `src/railshelf/jobs/state_machine.py`
- Create: `src/railshelf/jobs/leases.py`
- Create: `src/railshelf/jobs/runner.py`
- Create: `tests/unit/test_job_state_machine.py`
- Create: `tests/integration/test_job_recovery.py`

**Interfaces:**
- Produces: `transition_job(current: JobState, target: JobState) -> JobState`
- Produces: `LeaseManager.acquire(library_id: UUID, owner: OwnerIdentity) -> Lease`
- Produces: `JobRunner.run(job_id: UUID, cancellation: CancellationToken) -> JobSummary`
- Consumes: an `ItemHandler` protocol implemented by import and acquisition pipelines

- [ ] **Step 1: Write failing legal/illegal transition tests**

```python
import pytest


def test_running_job_can_pause_and_resume() -> None:
    assert transition_job(JobState.RUNNING, JobState.PAUSING) is JobState.PAUSING
    assert transition_job(JobState.PAUSED, JobState.QUEUED) is JobState.QUEUED


def test_completed_job_cannot_return_to_running() -> None:
    with pytest.raises(IllegalTransition):
        transition_job(JobState.COMPLETED, JobState.RUNNING)
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/unit/test_job_state_machine.py -q`

Expected: FAIL because the state machine is absent.

- [ ] **Step 3: Implement explicit transitions and lease heartbeats**

Represent legal transitions as exhaustive maps. Every state change occurs in a SQLite transaction with optimistic version checking. Lease acquisition uses `BEGIN IMMEDIATE`; duplicate owners coalesce equivalent queued sync jobs, while conflicting jobs wait. Heartbeats update both the database lease and filesystem lock.

- [ ] **Step 4: Implement restart and cancellation recovery**

At host startup, inspect jobs left in active states. If ownership is stale and no process is alive, convert `acquiring` items to `queued`, clean incomplete temporary downloads, convert `verifying` or `committing` items according to on-disk evidence, and requeue the job. Cancellation immediately cancels pending items and signals active handlers to stop at safe boundaries.

- [ ] **Step 5: Test crash points and competing owners**

Parametrize integration tests for crashes after temporary creation, after verification, before atomic replace, after replace, and before database commit. Test desktop/service contention with two database connections and two lock owners.

Run: `python -m pytest tests/unit/test_job_state_machine.py tests/integration/test_job_recovery.py -q`

Expected: all tests pass with no unverified final files.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/jobs tests/unit/test_job_state_machine.py tests/integration/test_job_recovery.py
git commit -m "feat: persist jobs and recover interrupted work"
```

---

### Task 8: PDF Pipeline, Artwork, and Acquisition Adapters

**Files:**
- Create: `src/railshelf/documents/pdf.py`
- Create: `src/railshelf/documents/artwork.py`
- Create: `src/railshelf/acquisition/http.py`
- Create: `src/railshelf/acquisition/browser.py`
- Create: `tests/unit/test_pdf_pipeline.py`
- Create: `tests/integration/test_artwork.py`
- Create: `tests/integration/test_acquisition.py`

**Interfaces:**
- Produces: `PdfProcessor.verify(path: Path) -> VerificationResult`
- Produces: `PdfProcessor.stamp(path: Path, issue: Issue) -> None`
- Produces: `ArtworkService.ensure(asset: Asset, issue: Issue) -> ArtworkResult`
- Produces: `HttpAcquirer.acquire(request: AcquisitionRequest, target: Path, cancellation: CancellationToken) -> AcquisitionResult`
- Produces: `BrowserAcquirer.acquire(...) -> AcquisitionResult`

- [ ] **Step 1: Write failing corrupt, encrypted, and thumbnail tests**

```python
def test_verifier_rejects_truncated_pdf(pdf_processor, tmp_path) -> None:
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF-1.7\ntruncated")
    result = pdf_processor.verify(path)
    assert not result.valid
    assert result.code is DiagnosticCode.PDF_INVALID


def test_first_page_thumbnail_is_cached(artwork_service, verified_asset) -> None:
    first = artwork_service.ensure(verified_asset.asset, verified_asset.issue)
    second = artwork_service.ensure(verified_asset.asset, verified_asset.issue)
    assert first.path == second.path
    assert second.generated is False
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/unit/test_pdf_pipeline.py tests/integration/test_artwork.py -q`

Expected: FAIL importing document modules.

- [ ] **Step 3: Implement verification, metadata, and artwork**

Verify `%PDF-`, minimum size, pypdf parseability, encryption state, positive page count, and first-page readability. Stamp title, subject, keywords, creation date, and XMP through a temporary same-directory output followed by atomic replacement. Render owned covers with PyMuPDF at a bounded size. Cache remote covers by content hash. Return a generated QML placeholder descriptor when neither source works.

- [ ] **Step 4: Implement streaming HTTP and isolated Playwright fallback**

HTTP acquisition streams chunks with connect/read/total timeouts, cancellation checks, maximum size, and bounded redirects. It never logs headers or cookies. Browser acquisition owns its context, loads session cookies through the auth port, detects the supported direct/flipbook modes, and returns a temporary file path without committing it to a library.

Browser selectors and scripts belong only in `acquisition/browser.py`; the job runner chooses HTTP first when the catalog exposes a direct source and uses browser fallback only for supported browser-required issues.

- [ ] **Step 5: Test interruption, timeout, redirect, size, corrupt content, and fallback choice**

Run: `python -m pytest tests/unit/test_pdf_pipeline.py tests/integration/test_artwork.py tests/integration/test_acquisition.py -q`

Expected: all tests pass without live network access.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/documents src/railshelf/acquisition tests/unit/test_pdf_pipeline.py tests/integration/test_artwork.py tests/integration/test_acquisition.py
git commit -m "feat: verify documents and acquire issue assets"
```

---

### Task 9: Authentication and Redacted Event History

**Files:**
- Create: `src/railshelf/auth/service.py`
- Create: `src/railshelf/auth/windows_dpapi.py`
- Create: `src/railshelf/auth/file_secrets.py`
- Create: `src/railshelf/application/events.py`
- Create: `tests/unit/test_auth_selection.py`
- Create: `tests/unit/test_redaction.py`
- Create: `tests/integration/test_windows_dpapi.py`

**Interfaces:**
- Produces: `AuthService.session_for(library: Library) -> AuthSession`
- Produces: `AuthService.validate(session_id: UUID) -> AuthState`
- Produces: `SecretStore.put(key: str, value: bytes) -> SecretReference`
- Produces: `EventPublisher.publish(event: Event) -> None`
- Produces: `DiagnosticExporter.export(destination: Path) -> Path`

- [ ] **Step 1: Write failing shared/override and redaction tests**

```python
def test_library_override_wins_over_global_session(auth_fixture) -> None:
    library = auth_fixture.library(auth_override_id=auth_fixture.override.id)
    assert auth_fixture.service.session_for(library).id == auth_fixture.override.id


def test_diagnostics_redact_secrets_and_user_root(redactor, tmp_path) -> None:
    text = f"cookie=secret; path={tmp_path / 'private/library'}"
    safe = redactor.clean(text)
    assert "secret" not in safe
    assert str(tmp_path) not in safe
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/unit/test_auth_selection.py tests/unit/test_redaction.py -q`

Expected: FAIL importing auth/event modules.

- [ ] **Step 3: Implement session selection and secret providers**

The Windows store encrypts/decrypts bytes with current-user DPAPI and stores only encrypted blobs below the config directory. The Docker store accepts references such as `/run/secrets/trains_session` and rejects world-readable files when the platform reports permissions. The database stores references and status, never raw cookies.

Interactive login is an application command that launches an isolated persistent Playwright context, waits for a validated authenticated response, persists cookies through `SecretStore`, and closes the context. Store no password fields.

- [ ] **Step 4: Implement structured event publishing and diagnostic export**

Persist safe event messages and codes. Send raw exception traces to protected rotating diagnostic logs after redacting cookie/header patterns, account labels, home paths, and configured library roots. Export a ZIP containing version, schema version, redacted logs, job summaries, and environment facts; exclude databases, PDFs, thumbnails, cookies, and tokens.

- [ ] **Step 5: Verify auth expiry and platform behavior**

Run Windows DPAPI tests only on Windows and file-secret permission tests on Linux. Test that auth expiry pauses only jobs using the expired session.

Run: `python -m pytest tests/unit/test_auth_selection.py tests/unit/test_redaction.py tests/integration/test_windows_dpapi.py -q`

Expected: all applicable tests pass; platform-inapplicable tests skip with an explicit reason.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/auth src/railshelf/application/events.py tests/unit/test_auth_selection.py tests/unit/test_redaction.py tests/integration/test_windows_dpapi.py
git commit -m "feat: protect sessions and publish redacted events"
```

---

### Task 10: CLI and Deterministic Fake Site

**Files:**
- Create: `src/railshelf/cli.py`
- Create: `tests/fake_site/app.py`
- Create: `tests/fake_site/test_failure_modes.py`
- Create: `tests/integration/test_cli.py`

**Interfaces:**
- Produces CLI commands: `library create|list|scan`, `catalog refresh`, `sync plan|run`, `import preview|run`, `jobs list|retry`, `schedule list|run`, `diagnostics export`
- Produces fake-site routes for archives, issues, login/session, PDFs, flipbooks, redirects, failures, delays, and truncation

- [ ] **Step 1: Write failing CLI plan test**

```python
import json

from typer.testing import CliRunner
from railshelf.cli import app


def test_sync_plan_json_is_machine_readable(cli_environment) -> None:
    result = CliRunner().invoke(
        app, ["sync", "plan", "--library", str(cli_environment.library_id), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["library_id"] == str(cli_environment.library_id)
    assert isinstance(payload["items"], list)
```

- [ ] **Step 2: Verify the CLI test fails**

Run: `python -m pytest tests/integration/test_cli.py -q`

Expected: FAIL because `railshelf.cli` is absent.

- [ ] **Step 3: Implement the thin CLI**

Create one `ApplicationServices` instance from `AppPaths`, repositories, and adapters. Commands call the same service methods as the desktop and scheduler. Human output goes to stdout, machine JSON uses stable keys, progress goes to stderr, and actionable failures return documented nonzero exit codes. Do not expose secret values in `--help`, output, or tracebacks.

- [ ] **Step 4: Build the fake site and failure matrix**

Use a test-only ASGI app served on an ephemeral localhost port. Parameterize response behavior using server-side fixture configuration, not query-string secrets. Cover successful direct PDF, browser-required issue, expired session, login redirect, 429 with `Retry-After`, 500, slow body, redirect loop, oversized body, corrupt PDF, truncated stream, and changed selectors.

- [ ] **Step 5: Run CLI and fake-site tests**

Run: `python -m pytest tests/integration/test_cli.py tests/fake_site -q`

Expected: all tests pass and no request reaches the public Internet.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/cli.py tests/integration/test_cli.py tests/fake_site
git commit -m "feat: expose core workflows through the CLI"
```

---

### Task 11: QML Shell, Library Grid, and Theme System

**Files:**
- Create: `src/railshelf/desktop/main.py`
- Create: `src/railshelf/desktop/bridge.py`
- Create: `src/railshelf/desktop/models.py`
- Create: `src/railshelf/desktop/qml/Main.qml`
- Create: `src/railshelf/desktop/qml/Theme.qml`
- Create: `src/railshelf/desktop/qml/components/AppSidebar.qml`
- Create: `src/railshelf/desktop/qml/components/IssueCard.qml`
- Create: `src/railshelf/desktop/qml/components/MetricCard.qml`
- Create: `src/railshelf/desktop/qml/pages/LibraryPage.qml`
- Create: `tests/ui/test_library_model.py`
- Create: `tests/ui/test_qml_smoke.py`

**Interfaces:**
- Produces: `DesktopBridge` slots for library selection, refresh, filtering, search, sync preview, and issue details
- Produces: `LibraryListModel`, `IssueGridModel`, `ActivityModel`
- Consumes: `ApplicationServices` only; QML receives no repository or filesystem object

- [ ] **Step 1: Write failing issue-model role test**

```python
def test_issue_grid_exposes_accessible_status_roles(qtbot, issue_grid_model) -> None:
    index = issue_grid_model.index(0, 0)
    assert issue_grid_model.data(index, issue_grid_model.TitleRole) == "January 2026"
    assert issue_grid_model.data(index, issue_grid_model.StatusRole) == "owned"
    assert issue_grid_model.data(index, issue_grid_model.AccessibleLabelRole) == (
        "Model Railroader, January 2026, owned"
    )
```

- [ ] **Step 2: Verify the UI model test fails**

Run: `python -m pytest tests/ui/test_library_model.py -q`

Expected: FAIL importing desktop models.

- [ ] **Step 3: Implement Qt adapters and asynchronous command dispatch**

Use `QAbstractListModel` with explicit roles for title, publication, year, status, cover URL, progress, and accessible label. The bridge submits commands to a worker executor and marshals immutable result DTOs back to the UI thread through signals. No UI call blocks on network, PDF, hashing, or SQLite work.

- [ ] **Step 4: Implement the approved visual-library shell**

Build a three-region desktop layout: switchable-library sidebar, responsive cover-grid content, and collapsible activity rail. Include owned/completeness/missing/queued metrics, publication/year/status filters, search, Sync Now, loading/empty/error states, and issue details. Use a reusable 8-pixel spacing scale, rail-blue accent, graphite surfaces, Segoe UI Variable, rounded panels, and restrained motion.

`Theme.qml` follows system light/dark by default and exposes manual light, dark, high-contrast, and reduced-motion preferences. `IssueCard.qml` communicates status with text/icon plus color.

- [ ] **Step 5: Verify QML loading, keyboard traversal, scaling, and model updates**

Run headlessly: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui/test_library_model.py tests/ui/test_qml_smoke.py -q`

Expected: all UI tests pass at 100%, 150%, and 200% scale fixtures.

Manually run: `railshelf-desktop`

Expected: the shell opens, switches fixture libraries, filters issues, and never freezes while a fixture refresh runs.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/desktop tests/ui
git commit -m "feat: add visual library desktop experience"
```

---

### Task 12: Operational Desktop Pages and Recovery Actions

**Files:**
- Create: `src/railshelf/desktop/qml/pages/DownloadsPage.qml`
- Create: `src/railshelf/desktop/qml/pages/SchedulePage.qml`
- Create: `src/railshelf/desktop/qml/pages/ImportPage.qml`
- Create: `src/railshelf/desktop/qml/pages/ProblemsPage.qml`
- Create: `src/railshelf/desktop/qml/pages/HistoryPage.qml`
- Create: `src/railshelf/desktop/qml/pages/SettingsPage.qml`
- Create: `src/railshelf/desktop/qml/components/ActionableProblem.qml`
- Create: `tests/ui/test_operational_models.py`
- Create: `tests/ui/test_workflow_smoke.py`

**Interfaces:**
- Extends `DesktopBridge` with pause, resume, cancel, retry, sign-in, import-preview, import-run, schedule-save, schedule-pause, open-quarantine, and export-diagnostics commands

- [ ] **Step 1: Write failing actionable-problem tests**

```python
def test_expired_auth_problem_offers_only_safe_actions(problem_model) -> None:
    problem = problem_model.for_code(DiagnosticCode.AUTH_EXPIRED)
    assert problem.actions == ("sign_in", "cancel_item")
    assert "cookie" not in problem.detail.lower()
```

- [ ] **Step 2: Verify tests fail**

Run: `python -m pytest tests/ui/test_operational_models.py -q`

Expected: FAIL because operational view models are absent.

- [ ] **Step 3: Implement jobs, problems, and history pages**

Downloads shows persistent jobs and item states with pause/resume/cancel/retry. Problems groups actionable failures by code and offers only actions declared by `ActionableError`. History shows structured summaries and drill-down events; raw logs are reachable only through diagnostics.

- [ ] **Step 4: Implement import, schedule, authentication, and settings workflows**

Import shows recognized, unrecognized, duplicate, conflict, and invalid rows plus exact source/final paths, Copy/Move selection, and a confirmation step. Schedule edits require a sync preview and approved fingerprint before enabling. Settings includes theme, motion, cache controls, global authentication, library override, and diagnostic export.

- [ ] **Step 5: Run complete fixture workflows**

Test keyboard-only create-library, import-preview/copy, sync-preview/run, auth-expired/sign-in, failed-item/retry, schedule-edit/approval, and quarantine-open flows.

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui -q`

Expected: all UI tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/railshelf/desktop/qml tests/ui
git commit -m "feat: add desktop operations and recovery workflows"
```

---

### Task 13: Scheduler Engine, Windows Service, and Docker Host

**Files:**
- Create: `src/railshelf/scheduling/engine.py`
- Create: `src/railshelf/scheduling/host.py`
- Create: `src/railshelf/service/windows.py`
- Create: `tests/unit/test_scheduling.py`
- Create: `tests/service/test_scheduler_host.py`
- Create: `tests/service/test_windows_service.py`
- Create: `docker/Dockerfile`
- Create: `docker/compose.test.yml`
- Create: `.dockerignore`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `ScheduleEngine.next_run(schedule: Schedule, after: datetime) -> datetime`
- Produces: `SchedulerHost.tick(now: datetime) -> tuple[UUID, ...]`
- Produces: `railshelf-service install|remove|start|stop|debug` on Windows
- Produces: container command `railshelf-scheduler --foreground`

- [ ] **Step 1: Write failing DST and missed-run tests**

```python
def test_spring_forward_uses_next_valid_local_time(schedule_engine) -> None:
    schedule = daily_schedule("02:30", zone="America/New_York")
    assert schedule_engine.next_run(schedule, utc("2026-03-08T06:00:00Z")) == utc(
        "2026-03-08T07:00:00Z"
    )


def test_offline_host_creates_one_catch_up_job(scheduler_host) -> None:
    created = scheduler_host.tick(utc("2026-07-13T12:00:00Z"))
    assert len(created) == 1
```

- [ ] **Step 2: Verify schedule tests fail**

Run: `python -m pytest tests/unit/test_scheduling.py -q`

Expected: FAIL importing the scheduling engine.

- [ ] **Step 3: Implement recurrence, coalescing, and the long-running host**

Use named IANA zones. For nonexistent local times, run at the next valid instant; for repeated times, run once at the first occurrence. Persist `next_run` after job creation in the same transaction. At startup create at most one catch-up run. Coalesce an equivalent queued sync job; otherwise wait behind the active library lease.

- [ ] **Step 4: Implement Windows service commands**

Wrap `SchedulerHost` with pywin32 `ServiceFramework`. Service stop signals cooperative cancellation and waits for a bounded shutdown. Install stores only the config directory argument, runs under the current user unless the installer explicitly configures another account, and never writes session material to service arguments or the registry.

- [ ] **Step 5: Build and test the non-root Docker image**

```dockerfile
# docker/Dockerfile
FROM python:3.13-slim AS runtime
RUN useradd --create-home --uid 10001 railshelf
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && playwright install --with-deps chromium
RUN mkdir -p /config /libraries && chown -R railshelf:railshelf /config /libraries
USER railshelf
ENV RAILSHELF_CONFIG_DIR=/config
HEALTHCHECK --interval=30s --timeout=5s CMD railshelf schedule list --json >/dev/null || exit 1
ENTRYPOINT ["railshelf-scheduler", "--foreground"]
```

Run: `docker build -f docker/Dockerfile -t railshelf:test .`

Run: `docker compose -f docker/compose.test.yml up --build --abort-on-container-exit --exit-code-from tests`

Expected: image runs as UID 10001, writes only to mounted volumes, passes health check, executes a fixture schedule, and exits cleanly.

If `docker version` is unavailable, install Docker Desktop using the user's prior authorization, then repeat these exact commands.

- [ ] **Step 6: Run Windows service debug tests and full scheduler tests**

Run: `python -m pytest tests/unit/test_scheduling.py tests/service -q`

Expected: all tests pass; service-manager mutation tests remain marked for an elevated CI job, while debug-host tests run normally.

- [ ] **Step 7: Commit**

```bash
git add src/railshelf/scheduling src/railshelf/service tests/unit/test_scheduling.py tests/service docker .dockerignore .github/workflows/ci.yml
git commit -m "feat: schedule syncs on Windows and Docker"
```

---

### Task 14: Windows Packaging, Cutover, and Release Verification

**Files:**
- Create: `packaging/windows/railshelf.spec`
- Create: `packaging/windows/Product.wxs`
- Create: `packaging/windows/build.ps1`
- Create: `docs/USER_GUIDE.md`
- Create: `docs/HEADLESS_DOCKER.md`
- Create: `docs/ARCHITECTURE.md`
- Modify: `README.md`
- Modify: `.github/workflows/build.yml`
- Delete: `trains_app.py`
- Delete: `requirements.txt`
- Delete: `build.bat`
- Delete: `tests/test_trains_app.py`
- Delete: `pytest.ini`

**Interfaces:**
- Produces: signed-capable `RailShelf-<version>-x64.msi`
- Produces: versioned `ghcr.io/<owner>/railshelf:<version>` images for `linux/amd64` and `linux/arm64`
- Produces: documented upgrade/uninstall, service, CLI, Docker, backup, rebuild, and diagnostics workflows

- [ ] **Step 1: Add a failing packaged-application smoke test**

Create a CI script that launches the unpacked PyInstaller build with `QT_QPA_PLATFORM=offscreen` and `RAILSHELF_SMOKE_EXIT=1`. The application must initialize paths, migrate a temporary database, load `Main.qml`, then exit zero without opening a browser or contacting the network.

Run: `powershell -File packaging/windows/build.ps1 -SmokeOnly`

Expected: FAIL because packaging files do not exist.

- [ ] **Step 2: Implement PyInstaller and WiX packaging**

Collect QML modules, Qt plugins, Playwright runtime location, schema resources, and application icons explicitly. The MSI installs per-user by default, adds Start Menu shortcuts, registers an optional Windows service feature, and removes the service before uninstall. Upgrades preserve the config directory and managed libraries.

The build script accepts `-Version`, `-Configuration`, `-SmokeOnly`, and optional signing-certificate parameters. It must not embed developer paths, cookies, test databases, or Chromium user profiles.

- [ ] **Step 3: Update release automation**

Run all required CI jobs before building artifacts. Build the MSI on Windows, build multi-architecture Docker images with Buildx, generate checksums, create a draft release, and publish only after artifact smoke tests pass. Keep signing optional in forks but required in the protected production release environment.

- [ ] **Step 4: Write operator and architecture documentation**

Document first-run library creation, managed import, authentication, sync rules, schedule approval, Problems/Quarantine, library rebuild, multiple libraries, global and override sessions, service lifecycle, Docker volumes/secrets/time zones, backups, diagnostic export, and uninstall behavior. Include the architecture boundaries and a statement that the tool requires an authorized subscription and does not bypass access controls.

- [ ] **Step 5: Perform the legacy cutover**

Delete the v1 single-file app and its obsolete build/test configuration only after the replacement passes the complete verification matrix. Preserve its Git history; do not copy it into the new package. Update README project structure and commands to reference only RailShelf.

- [ ] **Step 6: Run the release verification matrix**

Run:

```powershell
python -m ruff check .
python -m mypy src
python -m pytest -m "not live" -q
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests/ui -q
docker compose -f docker/compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
powershell -File packaging/windows/build.ps1 -Configuration Release
```

Expected:

- Zero lint or type errors.
- All non-live tests pass.
- Docker scheduler is healthy and fixture sync succeeds as non-root.
- MSI installs, launches, registers the optional service, upgrades over the prior alpha, uninstalls cleanly, and leaves user config/libraries intact.
- Packaged smoke test performs no public network request.

- [ ] **Step 7: Run the acceptance checklist from the design spec**

Create two switchable libraries; import through Copy and Move; rebuild one database inventory; preview and execute a sync; interrupt and resume it; expire authentication; quarantine an invalid PDF; retry a failed item; approve and run a schedule with the desktop closed; repeat the scheduled fixture sync in Docker; export and inspect a redacted diagnostic bundle.

Expected: all fourteen acceptance criteria in `docs/superpowers/specs/2026-07-13-collection-manager-rewrite-design.md` are demonstrably satisfied.

- [ ] **Step 8: Commit the release cutover**

```bash
git add -A
git commit -m "feat: release RailShelf collection manager v2"
```

---

## Cross-Task Review Checkpoints

After Tasks 3, 7, 11, and 13, pause for a focused review before continuing:

1. **Task 3:** domain boundaries, schema evolvability, path safety, and rebuild guarantees.
2. **Task 7:** job transitions, lease correctness, crash recovery, and atomicity.
3. **Task 11:** visual fidelity to the approved mockup, responsiveness, and accessibility.
4. **Task 13:** Windows service behavior, Docker parity, time-zone correctness, and secret handling.

At every checkpoint, run the complete test suite accumulated so far and record the exact command/output in the implementation task notes.

## Final Definition of Done

The rewrite is complete only when Task 14's verification matrix passes, every acceptance criterion has evidence, the legacy application is removed, the Windows installer and Docker image are reproducible, and no required work remains hidden behind a placeholder or manual-only test without documented evidence.
