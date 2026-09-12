# Trains.com Magazine Downloader & Organizer

**v1.6.0** — An all-in-one desktop application for downloading and organizing PDF issues of trains.com magazines. Supports all five publications, resumes interrupted downloads, and includes a built-in PDF organizer.

## Download

Pre-built executables are available on the [Releases](../../releases/latest) page — no Python installation required.

| Platform | File |
|----------|------|
| Windows  | `TrainsDownloader-windows.zip` → extract → run `TrainsDownloader.exe` |
| Linux    | `TrainsDownloader-linux.zip` → extract → `chmod +x TrainsDownloader` → run |
| macOS    | `TrainsDownloader-macos.zip` → extract → run `TrainsDownloader` |

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

- **GUI interface** — select magazines, set save location, and monitor progress
- **All three download modes** handled automatically:
  - Recent issues via direct PDF link (downloaded in parallel — up to 3 at once)
  - Mid-era issues via the embedded flipbook reader
  - Very old digitised-only issues skipped gracefully
- **Resumable downloads** — progress is saved; already-downloaded issues are skipped on subsequent runs
- **Cookie-based authentication** — log in once and sessions are reused across runs
- **Settings persistence** — save location, cookies path, headless mode, sort order, and magazine selections are remembered between sessions
- **Per-magazine progress bars** — stacked progress bars show each magazine's download progress with an ETA estimate
- **System tray** — minimizes to the system tray; right-click the tray icon to show the window or quit. Closing the window while a download is running prompts to minimize to tray, stop and quit, or cancel
- **Built-in PDF organizer** — renames and sorts PDFs into `YYYY/` subfolders with consistent naming (`MRR-01-January-2024.pdf`)
- **PDF integrity verification** — downloaded files are validated with pypdf; corrupt or truncated organizer inputs stay in the source folder and are reported instead of being moved
- **Conflict-safe organization** — duplicate issue targets are preserved with an explicit conflict count and log entry
- **PDF metadata stamping** — writes correct Title, Subject, Keywords, and Creation Date into each PDF's info dictionary and XMP metadata
- **Smart completeness report** — after organizing, lists missing issues per magazine and year using known publication schedules; seasonal/variable archives are reported without inventing monthly gaps
- **Download missing issues** — after a single-magazine organization run, fetch only the missing issues using the same download engine
- **Smarter log panel** — live filter field, error badge showing failure count, and a "Copy Errors" button; log lines are color-coded (errors in red, successful moves in green, skipped issues dimmed)
- **Sort order** — choose newest-first or oldest-first
- **Test mode** — scans only the first 3 archive pages for quick testing
- **Headless mode** — hide the browser window (requires valid saved cookies)

---

## Authentication

A trains.com subscription is required. On first run, leave the cookie file field set to `session_cookies.json`, leave **Hide download browser** unchecked, and click **Start Download**. Chrome will open for you to log in manually. Credentials are never stored; only the JSON session cookie is saved for reuse. Treat that file as sensitive and do not share it.

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

Requires Python 3.10+ and Google Chrome.

```bash
git clone https://github.com/gmoran1016/Trains.com-PDF-Downloader-Renamer.git
cd Trains.com-PDF-Downloader-Renamer
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python trains_app.py
```

### Running the tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

The development requirements include both the application dependencies and pytest. Pytest uses the repository-local `.pytest-tmp` and `.pytest-cache-local` directories, so the command does not depend on shared machine-wide paths.

### Building the exe locally (Windows)

```bash
build.bat
```

Output: `dist\TrainsDownloader.exe`

---

## Project Structure

```
trains_app.py                  # entire application (GUI + downloader + organizer)
requirements.txt               # runtime pip dependencies
requirements-dev.txt           # runtime dependencies plus pytest
build.bat                      # local Windows build script
pytest.ini                     # pytest config
tests/
  test_trains_app.py           # unit tests for settings, PDF and organizer behavior
  test_ui_smoke.py             # offscreen Qt construction/layout smoke tests
.github/workflows/build.yml    # GitHub Actions — builds exe for all platforms on push to main
docs/superpowers/              # design specs and implementation plans
docs/usability-audit-2026-08-08.md  # QA findings and remediation evidence
```

---

## Disclaimer

This tool is intended for personal use only. You must have an active trains.com subscription to access magazine content. Please comply with trains.com's terms of service.
