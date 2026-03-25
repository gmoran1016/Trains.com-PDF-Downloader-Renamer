# Authentication Guide

This document describes the simplified authentication workflow used by the
new `trains_downloader` package.  The CLI entrypoint is `train-cli`, and the
PySide6 GUI (`train-gui`) uses the same underlying logic.

## Overview

The scraper requires a logged‑in trains.com session in order to access
subscriber‑only archives.  Rather than storing credentials, the application
saves the browser session cookies to a JSON file which can be re‑used on
subsequent runs.  This method avoids exposing your username/password and is
compatible with headless operation.

### Default cookies file

By default the cookies are written to `session_cookies.json` in the current
working directory.  Specify a different path with the `--cookies` flag or the
corresponding GUI field.

## First‑time login

Run the CLI (no `--cookies` required) or launch the GUI, then sign in using
your trains.com subscription account.  For example:

```bash
train-cli --magazine "Model Railroader" --test
```

A browser window will open.  After you complete the login flow the scraper
automatically detects the authenticated session and saves the cookies file.

## Subsequent runs

Simply supply the cookies file and the scraper will reuse the session:

```bash
train-cli --magazine "Model Railroader" --cookies session_cookies.json
```

If the cookies have expired you will be prompted to log in again; the file
will then be updated.

## Headless / scheduled operation

Cookies allow the scraper to run headlessly without user interaction:

```bash
train-cli --magazine "Model Railroader" --cookies session_cookies.json --headless
```

Add `--test` when experimenting to limit the number of pages scanned.

## Using the GUI

Start the GUI with `train-gui` and use the **Load cookies…** button to pick an
existing JSON file.  Once logged in future sessions will automatically reuse
that file.

## Troubleshooting

* **Login not detected** – make sure you actually completed the login page and
  did not close the browser prematurely.  Run the command again without
  `--headless` to observe the process.
* **Cookies expire** – delete the JSON file and repeat the first‑time login
  procedure.
* **Multiple accounts** – maintain separate cookie files and specify the
  appropriate `--cookies` argument or load the correct file in the GUI.

Cookies contain your authenticated session and should be treated as
sensitive; do not commit them to version control or share them with others.


## Security Notes

1. **Cookie files contain your session** - keep them secure
2. **Don't share cookie files** - they give access to your account
3. **Use interactive login** instead of command-line password
4. **Cookies expire** - you'll need to re-login periodically
5. **Don't commit cookies to git** - they're in `.gitignore` by default

## Command Reference

| Flag | Description |
|------|-------------|
| `--login` | Perform login (prompts for credentials) |
| `--username USER` | Provide username/email |
| `--password PASS` | Provide password (not recommended) |
| `--use-cookies` | Load and use saved cookies |
| `--save-cookies` | Save cookies after login |
| `--cookies-file PATH` | Specify cookie file path |

## Examples by Use Case

### Download with subscription (first time)
```bash
python Magazine-Downloader.py --login --save-cookies
```

### Download with subscription (subsequent runs)
```bash
python Magazine-Downloader.py --use-cookies
```

### Automated/scheduled downloads
```bash
# Setup once with login
python Magazine-Downloader.py --login --save-cookies

# Use in cron/scheduled task
python Magazine-Downloader.py --use-cookies --headless
```

### Debug login issues
```bash
# Run without headless to see what's happening
python Magazine-Downloader.py --login --save-cookies
```

### Download specific range with authentication
```bash
python Magazine-Downloader.py --use-cookies --start-page 50 --end-page 60
```
