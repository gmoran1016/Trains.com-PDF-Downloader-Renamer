# Trains.com Magazine Downloader

A rewritten, modern version of the downloader with a clean package architecture.

This repository now contains a rewritten, modern Python package for downloading train magazines from trains.com.

Key improvements in the new version:

* **Playwright** replaces Selenium for more reliable, self‑contained browser automation
* **PySide6** provides a lightweight, cross‑platform GUI front end
* The code is organised as a proper package (`trains_downloader`) with both CLI and GUI entry points
* Build and distribution managed with `pyproject.toml`; tests added via `pytest`

Legacy single‑file scripts are still present under `src/` for historical reference but they simply delegate to the new implementation and are deprecated.

## Features

- Download issues from all trains.com magazines (Model Railroader, Trains Magazine, Classic Toy Trains, Classic Trains, Garden Railways)
- Simple GUI or command‑line interface
- Manual login with cookie persistence for reuse
- Optional headless mode for unattended runs
- Test mode limits page scanning for quick experimentation

## Supported Magazines

- Model Railroader (MRR)
- Trains Magazine (TRN)
- Classic Toy Trains (CTT)
- Classic Trains (CTR)
- Garden Railways (GRW)

## Requirements

- Python 3.8+
- Google Chrome browser
- Internet connection

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/trains-magazine-downloader.git
cd trains-magazine-downloader
```

2. Create a virtual environment:
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### GUI Application (Recommended)

After installing dependencies (and running `playwright install` once to obtain browsers), start the modern GUI via the entrypoint:

```bash
train-gui
```

A simple window lets you pick a magazine, set a download folder, optionally load a cookies file, and toggle headless or test mode.  Click **Start** to begin and watch progress in the log area.

### Command Line

The package provides a CLI wrapper:

```bash
train-cli --magazine "Model Railroader" --download-dir downloads-MRR --cookies session_cookies.json
```

Use `--help` for full options.  A `--test` flag limits pages for quick runs.

### Legacy Scripts

Old single-file scripts remain under `src/` (e.g. `Magazine-Downloader.py`) for reference but are no longer maintained.  New development should use the packaged `trains_downloader` modules instead.

### Command Line Scripts

Legacy command-line scripts are available in the `src/` directory:

- `Magazine-Downloader.py`: Download magazines from command line
- `Magazine-rename.py`: Organize and rename downloaded files

## Configuration

### Download Directories

The application automatically creates organized download folders:

- `downloads-MRR/`: Model Railroader magazines
- `downloads-TRN/`: Trains Magazine
- `downloads-CTT/`: Classic Toy Trains
- `downloads-CTR/`: Classic Trains
- `downloads-GRW/`: Garden Railways

Each magazine folder contains:
- `Organized/YYYY/`: Organized PDFs by year
- `Trackplans/`: Trackplan downloads (Model Railroader only)

### Authentication

The application supports multiple authentication methods:

1. **Automatic Login**: Enter username/password in the GUI
2. **Manual Login**: Login manually in the browser window
3. **Saved Sessions**: Reuse previous login sessions

See `docs/AUTHENTICATION_GUIDE.md` for detailed authentication instructions.

## File Organization

Downloaded PDFs are automatically organized with consistent naming:

- Format: `Magazine_YYYY_Month.pdf` (e.g., `MRR_2023_November.pdf`)
- Organized by year in `Organized/YYYY/` folders
- Duplicate handling with automatic numbering

## Troubleshooting

### Common Issues

1. **Login Problems**: Ensure you have an active trains.com subscription
2. **Download Failures**: Check internet connection and browser compatibility
3. **File Organization**: Ensure write permissions in download directories

### Logs

- Application logs: `scraper.log`
- GUI logs: Available in the application interface
- Debug information: Check console output when running scripts

## Development

### Project Structure

```
trains-magazine-downloader/
├── src/
│   ├── gui_downloader.py      # Main GUI application
│   ├── Magazine-Downloader.py # CLI magazine downloader
│   ├── Magazine-rename.py     # File organization script
│   └── Trackplan-Downloader   # Trackplan downloader script
├── docs/
│   └── AUTHENTICATION_GUIDE.md
├── requirements.txt           # Python dependencies
├── .gitignore                # Git ignore rules
└── README.md                 # This file
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for personal use only. Ensure you comply with trains.com terms of service and have appropriate subscriptions for accessing magazine content. The authors are not responsible for misuse of this software.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review existing GitHub issues
3. Create a new issue with detailed information