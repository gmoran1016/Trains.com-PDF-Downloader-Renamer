# Trains.com Downloader — Improvements Design
**Date:** 2026-04-16
**Scope:** Six improvements in two implementation passes

---

## Overview

Six improvements to the existing `trains_app.py` single-file PyQt5 application, delivered in two PRs:

- **Pass 1 (backend):** Settings persistence, download integrity checks, parallel Mode 1 downloads
- **Pass 2 (frontend):** Stacked per-magazine progress bars, smarter log panel, system tray

---

## Pass 1 — Backend

### 1. Settings Persistence

**What:** Save and restore all user-facing settings between sessions.

**Storage:** A `settings.json` file in `_BASE_DIR` (same directory as `session_cookies.json`, `download_progress.json`, etc.). Plain JSON — no new dependency.

**Keys saved:**

| Key | Widget | Default |
|-----|--------|---------|
| `base_dir` | Download tab save location | `~/Downloads/TrainsMagazines` |
| `cookies_path` | Download tab cookie field | `DEFAULT_COOKIES_FILE` |
| `headless` | Headless mode checkbox | `false` |
| `test_mode` | Test mode checkbox | `false` |
| `newest_first` | Sort combo | `true` |
| `include_specials` | Include special issues checkbox | `true` |
| `selected_magazines` | Magazine checkboxes | all selected |
| `org_src` | Organize source folder | `""` |
| `org_dst` | Organize destination folder | `""` |
| `org_prefix` | Organize prefix combo | `"Auto-detect"` |
| `org_cookies` | Organize cookie field | `""` |
| `org_headless` | Organize headless checkbox | `false` |

**Load:** Called once in `MainWindow.__init__` after `_build_ui()`. Silently skipped if the file is missing or malformed.

**Save:** A single `_save_settings()` method connected to `textChanged` / `stateChanged` / `currentIndexChanged` on every relevant widget. Writes the full settings dict each time.

**Implementation:**
```python
SETTINGS_FILE = os.path.join(_BASE_DIR, "settings.json")

def load_settings() -> dict: ...   # returns {} on any error
def save_settings(data: dict) -> None: ...
```

`MainWindow._load_settings()` reads the file and pushes values into widgets.
`MainWindow._save_settings()` reads values from widgets and writes the file.

---

### 2. Download Integrity Checks

**What:** Verify each PDF after it lands on disk; discard and re-queue corrupt files.

**Where:** End of `_rename_and_move()`, after `shutil.move` and metadata stamp succeed.

**Checks (in order):**
1. `os.path.getsize(dest) < 10_240` → file is suspiciously small (10 KB minimum)
2. If `pypdf` is available: open file, assert `len(reader.pages) > 0`

**On failure:**
- Log `[corrupt] <filename> — deleted, will retry`
- `os.unlink(dest)` to remove the bad file
- Return `(False, "corrupt")` so the caller does **not** add the URL to `completed`
- The URL stays pending and will be retried on the next run

**On success:** existing behavior unchanged.

**Note:** `_rename_and_move` currently returns a `str` (destination path). It will be changed to return `tuple[bool, str]` matching `download_issue`'s convention. All callers updated accordingly.

---

### 3. Parallel Mode 1 Downloads

**What:** While the browser sequentially visits each issue page, Mode 1 PDF fetches (pure HTTP via `requests`) run concurrently in a thread pool.

**Pool size:** 3 workers, hardcoded. Not user-configurable in this iteration.

**Architectural change — extract `_fetch_pdf` and `_rename_and_move`:**
Both `MagazineDownloader._fetch_pdf` and `MagazineDownloader._rename_and_move` are extracted to module-level functions. `_rename_and_move` uses only `os`, `shutil`, `parse_pdf_filename`, and a `log_fn` callback — no Selenium. `_fetch_pdf` only calls `_rename_and_move` and `requests` — no Selenium. Extracting both makes `fetch_pdf(url, dest_dir, hint_prefix, cookies, flat, download_dir, log_fn)` safely callable from threads. The class methods become thin wrappers calling the module-level functions.

**Worker loop change:**
```python
from concurrent.futures import ThreadPoolExecutor, Future

with ThreadPoolExecutor(max_workers=3) as pool:
    pending: dict[Future, tuple] = {}   # future → (issue_url, dest_dir, prefix, flat)

    for issue_url, dest_dir, prefix, flat in all_tasks:
        # ... skip/exists checks ...

        self._driver.get(issue_url)
        # detect_mode1_link: extracts the direct <a class="ci-btn--secondary"> or
        # "Download" anchor href from the already-loaded page — the first ~10 lines
        # of the existing download_issue() Mode 1 block, pulled into a helper.
        pdf_url = detect_mode1_link(self._driver)

        if pdf_url:
            cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
            fut = pool.submit(fetch_pdf, pdf_url, dest_dir, prefix, cookies, flat,
                              downloader.download_dir, self._log)
            pending[fut] = (issue_url, dest_dir, prefix, flat)
        else:
            # Mode 2 or mode 3 — synchronous (browser must stay on this page)
            ok, result = downloader.download_issue(issue_url, dest_dir, prefix, flat)
            # _handle_result: updates completed_set, progress dict, and calls
            # save_progress() — extracted from the existing per-issue if/elif/else block.
            _handle_result(ok, result, issue_url, progress, completed_set, self._log)
            done += 1
            self.signals.progress.emit(done, total)

    # Drain remaining Mode 1 futures
    for fut in as_completed(pending):
        issue_url = pending[fut][0]
        ok, result = fut.result()
        _handle_result(ok, result, issue_url, progress, completed_set, self._log)
        done += 1
        self.signals.progress.emit(done, total)
```

**Thread safety:** `progress` dict and `completed_set` are only written from the main worker thread (in `_handle_result`, called after `fut.result()`). No shared mutable state inside the thread pool tasks.

**Rate limiting:** Each `fetch_pdf` call includes a short random delay (`0.5–1.5s`) before the HTTP request to avoid hammering the CDN.

---

## Pass 2 — Frontend

### 4. Stacked Per-Magazine Progress Bars

**What:** Replace the single `dl_progress` QProgressBar with one labeled row per selected magazine, plus a summary line.

**New signal:**
```python
magazine_progress = pyqtSignal(str, int, int)  # (magazine_name, current, total)
```

**Widget structure** (replacing `self.dl_progress`):
```
QWidget (self._progress_container)
  QVBoxLayout
    [per magazine, repeated]
      QHBoxLayout
        QLabel (magazine name, left-aligned)
        QLabel (count "47 / 110", right-aligned)
      QProgressBar
    QLabel (self._summary_label)  ← "59 / 308 total · ~2h 14m remaining"
```

Container is hidden when no download is running; shown when one starts.

**ETA calculation** in `DownloadWorker`:
```python
elapsed = time.time() - self._start_time
rate = done / elapsed  # issues per second
eta_sec = (total - done) / rate if rate > 0 else 0
```
Emitted via `status_msg` signal as a formatted string. `_summary_label` displays it.

**`DownloadWorker` emits `magazine_progress`** after each issue completes, carrying the magazine name. `MainWindow` updates the corresponding row's bar and count label.

---

### 5. Smarter Log Panel

**What:** Filter field, error badge, "Copy Errors" button, and color-coded log lines. Applied to both Download and Organize log panels.

**Toolbar row** (inserted above each `QTextEdit`):
```
QHBoxLayout
  QLineEdit  (placeholder "Filter log…", self._dl_log_filter)
  QLabel     (self._dl_error_badge, hidden when 0 errors)
  QPushButton("Copy Errors", self._copy_errors_btn)
```

**Line buffer:** Each log panel maintains a `list[str]` of plain-text lines (`self._dl_log_lines`). `_append_log` appends to both the buffer and the display. When the filter changes, `_rebuild_log` clears the `QTextEdit` and re-appends only matching lines with HTML color formatting.

**Color rules (applied as HTML):**
| Pattern | Color |
|---------|-------|
| `FAILED` or `ERROR:` | `#f38ba8` (red) |
| `[corrupt]` | `#fab387` (orange) |
| `[skip]` or `[exists]` | `#45475a` (muted) |
| `→` (successful move/download) | `#a6e3a1` (green) |
| everything else | `#a6adc8` (default) |

**Error badge:** Count of lines containing `FAILED` or `ERROR:` in the buffer. Recalculated in `_append_log`. Hidden via `setVisible(False)` when count is 0.

**Copy Errors:** Joins all error/failed lines with newline and puts them on `QApplication.clipboard()`.

---

### 6. System Tray

**What:** Tray icon with tooltip, close-event dialog, and show/quit menu.

**Setup** (in `MainWindow.__init__`, after `_build_ui`):
```python
QApplication.instance().setQuitOnLastWindowClosed(False)  # REQUIRED — prevents quit on hide()
self._tray = QSystemTrayIcon(self.windowIcon(), self)
menu = QMenu()
menu.addAction("Show Window", self.show)
menu.addAction("Quit", QApplication.instance().quit)
self._tray.setContextMenu(menu)
self._tray.activated.connect(self._on_tray_activated)  # double-click → show
self._tray.show()
```

**`closeEvent` override:**
```python
def closeEvent(self, event):
    running = (self.worker and self.worker.isRunning()) or \
              (self._missing_worker and self._missing_worker.isRunning())
    if not running:
        event.accept()
        return
    event.ignore()
    dlg = QMessageBox(self)
    dlg.setWindowTitle("Download in progress")
    dlg.setText("A download is running.")
    minimize_btn = dlg.addButton("Minimize to Tray", QMessageBox.AcceptRole)
    stop_btn     = dlg.addButton("Stop & Quit",      QMessageBox.DestructiveRole)
    dlg.addButton("Cancel",                          QMessageBox.RejectRole)
    dlg.exec_()
    clicked = dlg.clickedButton()
    if clicked is minimize_btn:
        self.hide()
    elif clicked is stop_btn:
        for w in (self.worker, self._missing_worker):
            if w and w.isRunning():
                w.stop()
        QApplication.instance().quit()
```

**Tooltip:** Updated in `_update_progress` and `_on_finished`:
```python
self._tray.setToolTip(f"Downloading {current} / {total}…")   # while running
self._tray.setToolTip("Trains Downloader — Idle")             # when done
```

**Icon:** Uses `self.windowIcon()`. If no icon is set, falls back to `QStyle.SP_DriveNetIcon` from the current style.

---

## What Is Not In Scope

- Multi-browser parallel flipbook downloads
- User-configurable thread pool size
- Notification (toast/bubble) on download complete — tray tooltip is sufficient
- Per-issue retry count UI

---

## File Changes

**Pass 1 — all in `trains_app.py`:**
- Add `SETTINGS_FILE`, `load_settings()`, `save_settings()`
- Add `MainWindow._load_settings()`, `_save_settings()`, wire to widgets
- Modify `_rename_and_move()` → returns `tuple[bool, str]`, adds integrity check
- Extract `MagazineDownloader._fetch_pdf` → module-level `fetch_pdf()`
- Modify `DownloadWorker.run()` → `ThreadPoolExecutor` loop

**Pass 2 — all in `trains_app.py`:**
- Add `magazine_progress` signal to `WorkerSignals`
- Replace `dl_progress` with `_progress_container` widget tree
- Add ETA tracking to `DownloadWorker`
- Add log toolbar (filter, badge, copy errors) to both tabs
- Add color formatting to `_append_log`
- Add `QSystemTrayIcon` setup and `closeEvent` override to `MainWindow`
