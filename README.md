# Trains.com Magazine & Track Plan Downloader

**v1.9.1** — A desktop application for downloading trains.com magazine issues and Model Railroader track plan PDFs, with a built-in PDF organizer.

## Download

Pre-built executables are available on the [Releases](../../releases/latest) page — no Python installation required.

| Platform | File |
|----------|------|
| Windows  | `TrainsDownloader-windows.exe` → run directly |
| Linux    | `TrainsDownloader-linux` → `chmod +x TrainsDownloader-linux` → run |
| macOS    | `TrainsDownloader-macos` → run directly |

> **Requirement:** Google Chrome must be installed. The matching ChromeDriver is downloaded automatically on first run.

> **macOS note:** Right-click the app and choose **Open** the first time to bypass Gatekeeper.

---

## Supported Magazines

| Magazine | Prefix | Schedule |
|----------|--------|----------|
| Model Railroader | MRR | Monthly |
| Trains Magazine | TRN | Monthly |
| Classic Toy Trains | CTT | Monthly |
| Classic Trains | CTR | Quarterly (Mar/Jun/Sep/Dec) |
| Garden Railways | GRW | Seasonal / archived (variable) |

---

## Features

- **Workstation UI** — separate Download, Track Plans, and Organize workflows with readable magazine rows, shared archive access, and a resizable activity drawer
- **Track Plan Database download** — a separate workflow scans the paginated [Model Railroader Track Plan Database](https://www.trains.com/mrr/how-to/track-plan-database/) and downloads each plan PDF under its original filename to an independent folder; existing downloads are skipped on later runs
- **Visible organizer results** — moved, existing, unrecognized, corrupt, conflict, metadata, and missing-issue counts are shown in the workspace
- **All three download modes** handled automatically:
  - Recent issues via direct PDF link (downloaded in parallel — up to 3 at once)
  - Mid-era issues via the embedded flipbook reader
  - Very old digitised-only issues skipped gracefully
- **Resumable downloads** — progress is saved; already-downloaded issues are skipped on subsequent runs
- **Cookie-based authentication** — log in once and reuse the shared session for magazine and track plan downloads
- **Authenticated HTTP fallback** — if ChromeDriver receives Trains.com's anti-bot 403 page, saved authenticated cookies are used for archive discovery and direct PDF downloads
- **Truthful archive discovery** — temporary request failures are retried; a blocked or interrupted archive scan is reported as a failure, preserves issues already found, and never appears as a complete or empty scan
- **Settings persistence** — magazine and track plan folders, cookie path, headless mode, sort order, and magazine selections are remembered between sessions
- **Per-magazine progress rows** — the resizable activity drawer shows each magazine's download progress with an ETA estimate
- **System tray** — minimizes to the system tray; right-click the tray icon to show the window or quit. Closing the window while a download is running prompts to minimize to tray, stop and quit, or cancel
- **Built-in PDF organizer** — renames and sorts PDFs into `YYYY/` subfolders with consistent naming (`MRR-01-January-2024.pdf`)
- **PDF integrity verification** — downloaded files are validated with pypdf; corrupt or truncated organizer inputs stay in the source folder and are reported instead of being moved
- **Conflict-safe organization** — duplicate issue targets are preserved with an explicit conflict count and log entry
- **PDF metadata stamping** — writes correct Title, Subject, Keywords, and Creation Date into each PDF's info dictionary and XMP metadata
- **Smart completeness report** — after organizing, lists missing issues per magazine and year using known publication schedules; seasonal/variable archives are reported without inventing monthly gaps
- **Download missing issues** — after a single-magazine organization run, fetch only the missing issues using the same download engine
- **Smarter activity drawer** — resize it without losing the workflow, filter live output, review the error badge, copy failures, and clear the log; lines remain color-coded (errors in red, successful moves in green, skipped issues dimmed)
- **Sort order** — choose newest-first or oldest-first
- **Test mode** — scans only the first 3 archive pages for quick testing
- **Headless mode** — hide the browser window (requires valid saved cookies)

---

## Authentication

A trains.com subscription is required. On first use, open **Account settings** and leave the cookie file path set to `session_cookies.json`. In **Magazines**, leave **Keep browser hidden** unchecked, select the publications, and click **Download selected magazines**. Chrome opens for you to sign in manually. Credentials are never stored; only the JSON session cookie is saved for reuse. Treat that file as sensitive and do not share it.

The Track Plans workflow uses the same cookie file and sign-in process. If the saved session is no longer valid, its browser opens for sign-in and saves refreshed cookies for both download workflows.

The app avoids a ChromeDriver 154 crash on Windows by disabling automatic attachment to embedded frames. Frames still display normally and accept manual input; the downloader automates the main page. A driver crash can leave Chrome open even though the downloader has lost its connection.

If the browser connection drops during login, the app restarts Chrome once, restores any saved cookies, and reopens Trains.com. Continue signing in in the replacement window. Recovery uses the time remaining in the original five-minute login window; repeated disconnections produce a clear error with the log file location.

The application keeps local runtime state beside the executable or source file. This includes `session_cookies.json`, `settings.json`, `download_progress.json`, `special_issues.json`, and `trains_downloader.log`; these files are intentionally ignored by Git. The cookie file contains authenticated session data and must remain private.

Recent issues normally expose a direct PDF link and can use the authenticated HTTP fallback. Older issues may use the embedded flipbook reader, which still requires browser HTML access. Read-only or membership-gated issues are reported without being treated as successful downloads.

Some archive pages intentionally expose only a cover or print instructions and do not contain a reader or PDF control. Those pages are read-only and are skipped quickly; they are not retried as if a flipbook were available. A valid subscription and the required issue access are still necessary for downloadable flipbooks. A public, unauthenticated HTTP request returning `403 Forbidden` is not evidence that the archive is empty — sign in through the visible Chrome session first.

---

## PDF Naming & Organization

Downloaded files are renamed and moved into year subfolders automatically:

```
TrainsMagazines/
├── MRR/
│   ├── 2024/
│   │   ├── MRR-01-January-2024.pdf
│   │   ├── MRR-02-February-2024.pdf
│   │   └── ...
│   └── 2025/
├── TRN/
├── CTT/
├── CTR/
└── GRW/
```

The **Organize** tab can also rename and sort any existing folder of PDFs independently of the downloader. After organizing, the app stamps each valid PDF with correct metadata (Title, Subject, Keywords, Creation Date), leaves corrupt inputs in place for recovery, reports destination conflicts, and lists missing issues separately for each detected magazine and year.

---

## Running from Source

The desktop interface is written in Rust and the existing Python engine runs as a bundled worker. Published applications do not require a Python installation. Building from source requires Rust stable, Python 3.11+, and Google Chrome for download jobs.

```bash
git clone https://github.com/gmoran1016/Trains.com-PDF-Downloader-Renamer.git
cd Trains.com-PDF-Downloader-Renamer
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt pyinstaller
```

On Windows, run `build.bat` to package the Rust desktop application with its Python worker. The builder uses fresh run-specific output folders and preserves existing `build/` and `dist/` contents. For Linux and macOS releases, use the cross-platform GitHub Actions workflow.

### Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

The development requirements include both the application dependencies and pytest. Pytest uses the repository-local `.pytest-tmp` and `.pytest-cache-local` directories, so the command does not depend on shared machine-wide paths.

### Building the exe locally (Windows)

```bat
build.bat
```

Output: a run-specific folder under `dist\rust-ui-*\TrainsDownloader-windows.exe`.

### GitHub Actions

Every push to `main` runs [`.github/workflows/build.yml`](.github/workflows/build.yml). The workflow runs the Python engine and worker tests, Rust UI tests, formatting, and lint checks on Windows, Linux, and macOS. It packages the Python worker into the Rust desktop executable and publishes all three platform assets to the release matching the shared app version:

| Platform | GitHub Release asset |
|----------|----------------------|
| Windows  | `TrainsDownloader-windows.exe` |
| Linux    | `TrainsDownloader-linux` |
| macOS    | `TrainsDownloader-macos` |

The workflow is also available through **Actions → Build Desktop Applications → Run workflow**. A successful run should show three completed matrix jobs and a release containing all three assets. The local `build/`, `dist/`, generated PyInstaller spec, runtime state, and downloaded files are intentionally excluded from Git; use the release assets for distribution rather than committing a workstation build.

---

## Project Structure

```
rust-ui/                       # Rust/egui desktop application and worker protocol
worker_main.py                 # bundled JSON-lines worker entry point
worker_protocol.py             # versioned worker request/response schema
trains_app.py                  # retained Python download, organizer, and PDF engine
requirements.txt               # runtime pip dependencies
requirements-dev.txt           # runtime dependencies plus pytest
build.bat                      # local Windows build script
pytest.ini                     # pytest config
tests/
  test_trains_app.py           # Python engine tests
  test_worker_protocol.py      # JSON-lines protocol validation
  test_worker_integration.py   # worker adapter and subprocess tests
rust-ui/tests/                 # Rust state, protocol, and desktop UI tests
.github/workflows/build.yml    # GitHub Actions — builds exe for all platforms on push to main
docs/superpowers/              # design specs and implementation plans
docs/usability-audit-2026-08-08.md  # QA findings and remediation evidence
```

---

## Disclaimer

This tool is intended for personal use only. You must have an active trains.com subscription to access magazine content. Please comply with trains.com's terms of service.
