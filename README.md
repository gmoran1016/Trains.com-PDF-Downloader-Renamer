# Trains.com Magazine Downloader & Organizer

**v1.1.0** — An all-in-one desktop application for downloading and organizing PDF issues of trains.com magazines. Supports all five publications, resumes interrupted downloads, and includes a built-in PDF organizer.

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
| Garden Railways | GRW | Monthly |

---

## Features

- **GUI interface** — select magazines, set save location, and monitor progress
- **All three download modes** handled automatically:
  - Recent issues via direct PDF link
  - Mid-era issues via the embedded flipbook reader
  - Very old digitised-only issues skipped gracefully
- **Resumable downloads** — progress is saved; already-downloaded issues are skipped on subsequent runs
- **Cookie-based authentication** — log in once and sessions are reused across runs
- **Built-in PDF organizer** — renames and sorts PDFs into `YYYY/` subfolders with consistent naming (`MRR-01-January-2024.pdf`)
- **PDF metadata stamping** — writes correct Title, Subject, Keywords, and Creation Date into each PDF's info dictionary and XMP metadata
- **Smart completeness report** — after organizing, lists missing issues per year using each magazine's actual publication schedule (monthly, quarterly, etc.)
- **Sort order** — choose newest-first or oldest-first
- **Test mode** — scans only the first 3 archive pages for quick testing
- **Headless mode** — hide the browser window (requires valid saved cookies)

---

## Authentication

A trains.com subscription is required. On first run, leave the cookie file field set to `session_cookies.json` and click **Start** — a Chrome window will open for you to log in manually. Credentials are never stored; only the session cookie is saved for reuse.

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

The **Organize** tab can also rename and sort any existing folder of PDFs independently of the downloader. After organizing, the app stamps each PDF with correct metadata (Title, Subject, Keywords, Creation Date) and reports which issues are missing for each year based on the magazine's publication schedule.

---

## Running from Source

Requires Python 3.10+ and Google Chrome.

```bash
git clone https://github.com/yourusername/trains-magazine-downloader.git
cd trains-magazine-downloader
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python trains_app.py
```

### Building the exe locally (Windows)

```bash
build.bat
```

Output: `dist\TrainsDownloader.exe`

---

## Project Structure

```
trains_app.py                  # entire application (GUI + downloader + organizer)
requirements.txt               # pip dependencies
build.bat                      # local Windows build script
.github/workflows/build.yml    # GitHub Actions — builds exe for all platforms on push
```

---

## Disclaimer

This tool is intended for personal use only. You must have an active trains.com subscription to access magazine content. Please comply with trains.com's terms of service.
