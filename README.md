# Trains.com Magazine Downloader

A comprehensive PyQt5-based GUI application for downloading and organizing train magazines from trains.com. Supports multiple magazines including Model Railroader, Trains Magazine, Classic Toy Trains, Classic Trains, and Garden Railways.

## Features

- **Multi-Magazine Support**: Download from multiple train magazines in a single session
- **Sequential Downloads**: Process multiple magazines one after another automatically
- **Trackplan Downloads**: Download trackplans from Model Railroader (when available)
- **File Organization**: Automatically rename and organize downloaded PDFs by year
- **Multithreaded Downloads**: Concurrent downloads for faster processing
- **Session Management**: Save and reuse login sessions
- **Headless Operation**: Run browser in background for unattended operation
- **Progress Tracking**: Real-time progress bars and detailed logging
- **Test Mode**: Limited downloads for testing purposes

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

Run the main GUI application:
```bash
python src/gui_downloader.py
```

1. Select one or more magazines to download
2. Enter your trains.com credentials (optional, can login manually)
3. Configure download settings
4. Click "Start Download"
5. Monitor progress in the log output

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