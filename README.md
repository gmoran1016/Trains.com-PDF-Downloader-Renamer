<div align="center">
  <img src="desktop-ui/src-tauri/icons/128x128.png" alt="PDF document icon" width="88" height="88">
  <h1>Trains.com Magazine &amp; Track Plan Downloader</h1>
  <p><strong>Download Trains.com magazines and track plans, then organize your PDFs in one desktop app.</strong></p>
  <p>
    <a href="../../releases/latest"><img alt="Latest GitHub release" src="https://img.shields.io/github/v/release/gmoran1016/Trains.com-PDF-Downloader-Renamer?display_name=tag&style=for-the-badge&label=Latest%20release"></a>
  </p>
  <p><a href="#download">Download for your platform</a> · <a href="#whats-new-in-v200">What’s new in v2.0.0</a> · <a href="#running-from-source">Build from source</a></p>
</div>

> **Upgrading from v1.x?** Install v2.0.0 once from the [latest GitHub release](../../releases/latest). Earlier versions do not include the updater; later signed releases can be installed from the app after you approve them.

## Contents

[Download](#download) · [What’s new](#whats-new-in-v200) · [Updating](#updating) · [Supported magazines](#supported-magazines) · [Features](#features) · [Authentication](#authentication) · [PDF naming](#pdf-naming--organization) · [Build and test](#running-from-source)

## Download

Choose the package for your computer. Python is bundled, so you do not need to install it separately.

| Platform | Download | First run |
|----------|----------|-----------|
| Windows portable | [Download `.exe`](../../releases/latest/download/TrainsDownloader-windows.exe) | Extract and run; keep the app beside its data files. |
| Windows installer | [Download setup](../../releases/latest/download/TrainsDownloader-windows-setup.exe) | Per-user install; includes the WebView2 bootstrapper. |
| Linux | [Download AppImage](../../releases/latest/download/TrainsDownloader-linux.AppImage) | Mark the file executable, then run it. |
| macOS · Apple Silicon | [Download `.dmg`](../../releases/latest/download/TrainsDownloader-macos.dmg) | Copy the app to a writable folder. |
| macOS · Intel | [Download `.dmg`](../../releases/latest/download/TrainsDownloader-macos-x86_64.dmg) | Copy the app to a writable folder. |

All files are also listed on the [Releases page](../../releases/latest). Downloads require Google Chrome; the matching ChromeDriver is downloaded automatically. The Windows portable app also needs [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/).

> **macOS:** On first launch, right-click the app and choose **Open** to bypass Gatekeeper.

## What’s new in v2.0.0

- **Built-in updater:** checks GitHub at startup or from Settings, shows release notes, and installs signed updates only after you approve them.
- **More reliable downloads:** filenames and PDF metadata use issue details, and existing issues are recognized across supported destination layouts to prevent duplicate downloads on later runs.
- **Safer install options:** Windows portable users get the portable executable and replacement instructions; existing v1.x users can install this version manually once.

See the [full v2.0.0 release notes](docs/releases/v2.0.0.md).

## Updating

The app checks GitHub for a newer stable release at startup and from **Settings → Check for updates**. It shows the release notes and waits for your approval before downloading or installing. Signed updates install and restart the app. If GitHub cannot be reached, the rest of the app remains available and Settings shows the check error.

Windows portable users receive a link to the portable executable. Close the app, replace the executable in its current folder, and keep the files beside it to retain settings and downloads.

Release signing and rollout instructions are in [docs/UPDATES.md](docs/UPDATES.md).

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

### Download

- Handle the three magazine download modes: direct PDF links for recent issues, embedded flipbook downloads for mid-era issues, and graceful skips for digitised-only issues.
- Download up to three recent issues in parallel; progress is saved so later runs can resume and skip completed issues.
- Scan the paginated [Model Railroader Track Plan Database](https://www.trains.com/mrr/how-to/track-plan-database/) and save plans under their original filenames in a separate folder. Existing downloads are skipped.
- Reuse one signed-in browser session for magazines and track plans. If ChromeDriver hits Trains.com’s anti-bot 403 page, authenticated cookies can be used for archive discovery and direct PDF downloads.
- Retry temporary archive failures and report blocked or interrupted scans as failures, preserving issues already found.
- Remember magazine and track plan folders, cookie path, headless mode, sort order, and magazine selections. Choose newest-first or oldest-first; use test mode to scan only the first three archive pages.

### Organize PDFs

- Rename and sort PDFs into `YYYY/` folders with consistent names such as `MRR-01-January-2024.pdf`.
- Stamp PDF info and XMP metadata with Title, Subject, Keywords, and Creation Date.
- Verify PDF integrity; keep corrupt or truncated inputs in place and report them for recovery.
- Preserve destination conflicts and report moved, existing, unrecognized, corrupt, metadata, and missing-issue counts.
- Report missing issues by magazine and year using known publication schedules; seasonal and variable archives do not receive invented monthly gaps. Fetch missing issues after organizing a single magazine.

### Desktop app

- Use separate Magazines, Track Plans, and Organize work areas with shared settings, readable text, independent scrolling, and pinned workflow actions.
- View per-magazine issue counts and status in Activity; expand or resize the progress area.
- Filter retained activity, page through events, review error counts, copy failures, and clear history explicitly. Status labels accompany colors.
- Minimize to the system tray. Closing during a download offers to minimize, stop and quit, or cancel.
- Install signed GitHub updates only after reviewing the release notes and approving the update.
- Sign in through visible Chrome when needed; headless mode requires valid saved cookies.

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

Pushes to `main` or `master` run [`.github/workflows/build.yml`](.github/workflows/build.yml). The four-platform matrix checks Python, Rust, rendered UI interactions, formatting, and lint; it embeds the Python worker and builds Windows, Linux, and macOS packages. A manual run stores build artifacts by default. When **publish** is enabled, the workflow waits for every platform to pass, generates the signed updater manifest, and publishes the versioned GitHub release.

| Platform | GitHub Release download |
|----------|-------------------------|
| Windows portable | `TrainsDownloader-windows.exe` |
| Windows installer | `TrainsDownloader-windows-setup.exe` |
| Linux | `TrainsDownloader-linux.AppImage` |
| macOS · Apple Silicon | `TrainsDownloader-macos.dmg` |
| macOS · Intel | `TrainsDownloader-macos-x86_64.dmg` |

The workflow is available through **Actions → Build Desktop Applications → Run workflow**. Linux builds use Ubuntu 22.04 as their baseline. macOS DMGs are unsigned unless Apple signing is configured; updater archives are signed with the Tauri key. Local Windows verification does not establish Linux/macOS runtime behavior; see [verification evidence](docs/tauri-ui-verification.md). Build outputs, dependencies, runtime state, and downloaded files are excluded from Git.

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
.github/workflows/build.yml    # GitHub Actions — cross-platform checks, builds, and release publishing
docs/superpowers/              # design specs and implementation plans
docs/usability-audit-2026-08-08.md  # QA findings and remediation evidence
```

---

## Disclaimer

This tool is intended for personal use only. You must have an active trains.com subscription to access magazine content. Please comply with trains.com's terms of service.
