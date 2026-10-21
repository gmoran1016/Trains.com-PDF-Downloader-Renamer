# Trains.com Magazine & Track Plan Downloader

**v1.10.0** — A Tauri desktop application for downloading trains.com magazine issues and Model Railroader track plan PDFs, with a built-in PDF organizer. The interface uses React and TypeScript; Rust retains desktop integration and the existing Python engine is bundled.

## Download

Pre-built executables are available on the [Releases](../../releases/latest) page — no Python installation required.

| Platform | File |
|----------|------|
| Windows  | `TrainsDownloader-windows.exe` portable, or `TrainsDownloader-windows-setup.exe` installer |
| Linux    | `TrainsDownloader-linux.AppImage` → mark executable → run |
| macOS    | `TrainsDownloader-macos.dmg` → copy the application to a writable folder → run |

> **Requirements:** Google Chrome for downloads. The Windows portable application also needs [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/); the per-user installer supplies its bootstrapper. Python is bundled. The matching ChromeDriver is downloaded automatically on first run.

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

- **Desktop interface** — equal Magazines, Track Plans, and Organize work areas, readable text, shared settings, independent scrolling, and pinned workflow actions
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
- **Per-magazine progress** — Activity shows the worker's actual issue counts and status; it starts compact and can be expanded or resized
- **System tray** — minimizes to the system tray; right-click the tray icon to show the window or quit. Closing the window while a download is running prompts to minimize to tray, stop and quit, or cancel
- **Built-in PDF organizer** — renames and sorts PDFs into `YYYY/` subfolders with consistent naming (`MRR-01-January-2024.pdf`)
- **PDF integrity verification** — downloaded files are validated with pypdf; corrupt or truncated organizer inputs stay in the source folder and are reported instead of being moved
- **Conflict-safe organization** — duplicate issue targets are preserved with an explicit conflict count and log entry
- **PDF metadata stamping** — writes correct Title, Subject, Keywords, and Creation Date into each PDF's info dictionary and XMP metadata
- **Smart completeness report** — after organizing, lists missing issues per magazine and year using known publication schedules; seasonal/variable archives are reported without inventing monthly gaps
- **Download missing issues** — after a single-magazine organization run, fetch only the missing issues using the same download engine
- **Activity history** — filter the full retained session, page through events, review error counts, copy failures, and explicitly clear history; status labels accompany colors
- **Sort order** — choose newest-first or oldest-first
- **Test mode** — scans only the first 3 archive pages for quick testing
- **Headless mode** — hide the browser window (requires valid saved cookies)

---

## Authentication

A trains.com subscription is required. On first use, open **Settings** and leave the cookie file path set to `session_cookies.json`. In **Magazines**, leave **Keep magazine browser hidden** unchecked, select the publications, and click **Download selected magazines**. Chrome opens for you to sign in manually. Credentials are never stored; only the JSON session cookie is saved for reuse. Treat that file as sensitive and do not share it.

The Track Plans workflow uses the same cookie file and sign-in process. If the saved session is no longer valid, its browser opens for sign-in and saves refreshed cookies for both download workflows.

The app avoids a ChromeDriver 154 crash on Windows by disabling automatic attachment to embedded frames. Frames still display normally and accept manual input; the downloader automates the main page. A driver crash can leave Chrome open even though the downloader has lost its connection.

If the browser connection drops during login, the app restarts Chrome once, restores any saved cookies, and reopens Trains.com. Continue signing in in the replacement window. Recovery uses the time remaining in the original five-minute login window; repeated disconnections produce a clear error with the log file location.

The application keeps local runtime state beside the portable executable, original AppImage, or macOS `.app` folder. This includes `session_cookies.json`, `settings.json`, `download_progress.json`, `special_issues.json`, and `trains_downloader.log`; these files are intentionally ignored by Git. To retain existing portable data, put the replacement in the same writable folder. Installing into a new location creates a separate data location; move the existing data files there intentionally if desired. On macOS, use a writable folder such as `~/Applications/TrainsArchive`, rather than running from the read-only DMG. The cookie file contains authenticated session data and must remain private. `--data-dir <folder>` explicitly selects another data root.

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

Building requires Rust stable, Node.js 22.12+ (CI uses 24), Python 3.11+, and the [Tauri desktop prerequisites](https://v2.tauri.app/start/prerequisites/). Windows needs Visual Studio C++ build tools and WebView2. Google Chrome is required for download jobs.

```bash
git clone https://github.com/gmoran1016/Trains.com-PDF-Downloader-Renamer.git
cd Trains.com-PDF-Downloader-Renamer
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements-dev.txt
```

On Windows, run `build.bat` to check and package the Tauri app and Python worker. Outputs use a fresh folder under `dist/desktop-*`; existing build and distribution artifacts are preserved. For Linux and macOS, use the GitHub Actions matrix. Development: install dependencies with `npm ci` inside `desktop-ui`, then run `npm run tauri -- dev`. A debug build without an embedded worker displays a useful job-start failure; build the Python worker and set `TRAINSDOWNLOADER_WORKER` for real download jobs. Never use live account/library data for UI checks.

### Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
cargo test --manifest-path rust-ui/Cargo.toml --all-targets --features "test-worker desktop-smoke"
cargo test --manifest-path desktop-ui/src-tauri/Cargo.toml
cd desktop-ui
npm ci
npm run build
npm test
```

The development requirements include both the application dependencies and pytest. Pytest uses the repository-local `.pytest-tmp` and `.pytest-cache-local` directories, so the command does not depend on shared machine-wide paths.

### Building the exe locally (Windows)

```bat
build.bat
```

Output: portable and installer applications in a run-specific `dist\desktop-*` folder. The script expects the project's Python environment to contain `requirements-dev.txt` and PyInstaller; `-PythonPath <python.exe>` can select another environment. `-SkipChecks` skips regression checks for an already verified rebuild.

### GitHub Actions

Every push to `main` runs [`.github/workflows/build.yml`](.github/workflows/build.yml). The matrix checks Python, Rust, rendered UI interactions, formatting, and lint; it embeds the Python worker and creates desktop packages. Publication waits for every platform to succeed:

| Platform | GitHub Release asset |
|----------|----------------------|
| Windows  | `TrainsDownloader-windows.exe` |
| Windows installer | `TrainsDownloader-windows-setup.exe` |
| Linux    | `TrainsDownloader-linux.AppImage` |
| macOS    | `TrainsDownloader-macos.dmg` |

The workflow is also available through **Actions → Build Desktop Applications → Run workflow**. Manual runs save artifacts; enable **publish** to release them after all checks pass. Linux builds use Ubuntu 22.04 as their baseline. macOS packages are unsigned unless signing is configured. Local Windows verification does not establish Linux/macOS runtime behavior; see [verification evidence](docs/tauri-ui-verification.md). Build outputs, dependencies, runtime state, and downloaded files are excluded from Git.

---

## Project Structure

```
desktop-ui/src/                # React/TypeScript desktop interface
desktop-ui/src-tauri/          # Tauri shell, tray, dialogs, narrow native commands
desktop-ui/tests/              # rendered workflow, keyboard, theme and layout checks
rust-ui/                       # toolkit-independent Rust controller and worker protocol
worker_main.py                 # bundled JSON-lines worker entry point
worker_protocol.py             # versioned worker request/response schema
trains_app.py                  # retained Python download, organizer, and PDF engine
requirements.txt               # runtime pip dependencies
requirements-dev.txt           # runtime, test, and packaging dependencies
build.bat                      # local Windows build script
pytest.ini                     # pytest config
tests/
  test_trains_app.py           # Python engine tests
  test_worker_protocol.py      # JSON-lines protocol validation
  test_worker_integration.py   # worker adapter and subprocess tests
rust-ui/tests/                 # Rust controller, state, settings and protocol tests
.github/workflows/build.yml    # GitHub Actions — builds exe for all platforms on push to main
docs/superpowers/              # design specs and implementation plans
docs/usability-audit-2026-08-08.md  # QA findings and remediation evidence
```

---

## Disclaimer

This tool is intended for personal use only. You must have an active trains.com subscription to access magazine content. Please comply with trains.com's terms of service.
