# Trains.com Downloader — Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add settings persistence, download integrity checks, parallel Mode 1 downloads, stacked per-magazine progress bars, a smarter log panel, and system tray support.

**Architecture:** All changes live in `trains_app.py` (single-file app). Pass 1 extracts two class methods to module-level functions and adds a `ThreadPoolExecutor` to `DownloadWorker`. Pass 2 extends the PyQt5 UI. A new `tests/test_trains_app.py` covers all testable pure functions.

**Tech Stack:** Python 3.10+, PyQt5, selenium, requests, pypdf, `concurrent.futures` (stdlib), pytest

**Spec:** `docs/superpowers/specs/2026-04-16-trains-improvements-design.md`

---

## File Map

| File | Change |
|------|--------|
| `trains_app.py` | All logic and UI changes |
| `tests/__init__.py` | Create (empty) |
| `tests/test_trains_app.py` | Create — unit tests for all pure functions |

---

## PASS 1 — BACKEND

---

### Task 1: Settings Persistence

**Files:**
- Modify: `trains_app.py`
- Create: `tests/__init__.py`, `tests/test_trains_app.py`

- [ ] **Step 1: Create test file and write failing tests for settings functions**

Create `tests/__init__.py` (empty).

Create `tests/test_trains_app.py`:

```python
import json
import os
import sys
import pytest

# Add project root to path so we can import trains_app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import only the pure functions we can test without a display
from trains_app import load_settings, save_settings


def test_load_settings_returns_empty_dict_when_file_missing(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    result = load_settings(path=path)
    assert result == {}


def test_load_settings_returns_empty_dict_on_malformed_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    result = load_settings(path=str(f))
    assert result == {}


def test_save_and_load_settings_roundtrip(tmp_path):
    path = str(tmp_path / "settings.json")
    data = {"base_dir": "/some/path", "headless": True, "newest_first": False}
    save_settings(data, path=path)
    result = load_settings(path=path)
    assert result == data


def test_save_settings_writes_valid_json(tmp_path):
    path = str(tmp_path / "settings.json")
    save_settings({"key": "value"}, path=path)
    with open(path, encoding="utf-8") as f:
        parsed = json.load(f)
    assert parsed == {"key": "value"}
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_trains_app.py -v
```

Expected: `ImportError` or `TypeError` — `load_settings`/`save_settings` don't have `path` param yet.

- [ ] **Step 3: Add `SETTINGS_FILE` constant and `load_settings`/`save_settings` to `trains_app.py`**

After the `SPECIAL_ISSUES_FILE` line (~line 94), add:

```python
SETTINGS_FILE       = os.path.join(_BASE_DIR, "settings.json")
```

After `save_special_issues` (~line 173), add:

```python
def load_settings(path: str = SETTINGS_FILE) -> dict:
    """Load UI settings from JSON. Returns {} on any error."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict, path: str = SETTINGS_FILE) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
```

- [ ] **Step 4: Run tests — should pass**

```
pytest tests/test_trains_app.py -v
```

Expected: all 4 pass.

- [ ] **Step 5: Add `_load_settings` and `_save_settings` to `MainWindow`**

In `MainWindow.__init__`, after `self._build_ui()`, add:

```python
self._load_settings()
```

Add these two methods after `_browse_org_cookies`:

```python
def _load_settings(self):
    s = load_settings()
    if "base_dir" in s:
        self.dir_edit.setText(s["base_dir"])
    if "cookies_path" in s:
        self.cookie_edit.setText(s["cookies_path"])
    if "headless" in s:
        self.headless_cb.setChecked(s["headless"])
    if "test_mode" in s:
        self.test_cb.setChecked(s["test_mode"])
    if "newest_first" in s:
        self.sort_combo.setCurrentIndex(0 if s["newest_first"] else 1)
    if "include_specials" in s:
        self.specials_cb.setChecked(s["include_specials"])
    if "selected_magazines" in s:
        sel = set(s["selected_magazines"])
        for name, cb in self.mag_checks.items():
            cb.setChecked(name in sel)
    if "org_src" in s:
        self.src_edit.setText(s["org_src"])
    if "org_dst" in s:
        self.dst_edit.setText(s["org_dst"])
    if "org_prefix" in s:
        idx = self.prefix_combo.findText(s["org_prefix"])
        if idx >= 0:
            self.prefix_combo.setCurrentIndex(idx)
    if "org_cookies" in s:
        self.org_cookie_edit.setText(s["org_cookies"])
    if "org_headless" in s:
        self.org_headless_cb.setChecked(s["org_headless"])

def _save_settings(self):
    save_settings({
        "base_dir":           self.dir_edit.text(),
        "cookies_path":       self.cookie_edit.text(),
        "headless":           self.headless_cb.isChecked(),
        "test_mode":          self.test_cb.isChecked(),
        "newest_first":       self.sort_combo.currentText() == "Newest first",
        "include_specials":   self.specials_cb.isChecked(),
        "selected_magazines": [n for n, cb in self.mag_checks.items() if cb.isChecked()],
        "org_src":            self.src_edit.text(),
        "org_dst":            self.dst_edit.text(),
        "org_prefix":         self.prefix_combo.currentText(),
        "org_cookies":        self.org_cookie_edit.text(),
        "org_headless":       self.org_headless_cb.isChecked(),
    })
```

- [ ] **Step 6: Wire all widgets to `_save_settings` in `_make_download_tab` and `_make_organize_tab`**

In `_make_download_tab`, after each widget is created, connect its change signal. Add these lines immediately before `return w`:

```python
# Persist settings on every change
self.dir_edit.textChanged.connect(self._save_settings)
self.cookie_edit.textChanged.connect(self._save_settings)
self.headless_cb.stateChanged.connect(self._save_settings)
self.test_cb.stateChanged.connect(self._save_settings)
self.specials_cb.stateChanged.connect(self._save_settings)
self.sort_combo.currentIndexChanged.connect(self._save_settings)
for cb in self.mag_checks.values():
    cb.stateChanged.connect(self._save_settings)
```

In `_make_organize_tab`, add these lines immediately before `return w`:

```python
self.src_edit.textChanged.connect(self._save_settings)
self.dst_edit.textChanged.connect(self._save_settings)
self.prefix_combo.currentIndexChanged.connect(self._save_settings)
self.org_cookie_edit.textChanged.connect(self._save_settings)
self.org_headless_cb.stateChanged.connect(self._save_settings)
```

- [ ] **Step 7: Smoke-test manually**

Run the app, change some settings, close, reopen — values should be restored. No automated test needed here.

- [ ] **Step 8: Commit**

```bash
git add trains_app.py tests/__init__.py tests/test_trains_app.py
git commit -m "feat: persist UI settings to settings.json between sessions"
```

---

### Task 2: Download Integrity Check + Extract `rename_and_move`

**Files:**
- Modify: `trains_app.py`
- Modify: `tests/test_trains_app.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_trains_app.py`:

```python
from trains_app import _verify_pdf, rename_and_move


def test_verify_pdf_rejects_too_small(tmp_path):
    f = tmp_path / "small.pdf"
    f.write_bytes(b"%PDF-1.4 tiny")
    assert _verify_pdf(str(f)) is False


def test_verify_pdf_rejects_invalid_content(tmp_path):
    f = tmp_path / "fake.pdf"
    # Large enough to pass size check, but not a real PDF
    f.write_bytes(b"not a pdf at all" + b"x" * 10_240)
    assert _verify_pdf(str(f)) is False


def test_verify_pdf_accepts_valid_pdf(tmp_path):
    import io
    import pypdf
    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    f = tmp_path / "valid.pdf"
    f.write_bytes(buf.getvalue())
    assert _verify_pdf(str(f)) is True


def test_rename_and_move_returns_false_for_corrupt_file(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    bad_pdf = src / "MRR-2024-01.pdf"
    bad_pdf.write_bytes(b"tiny")  # too small → corrupt
    logs = []
    ok, result = rename_and_move(str(bad_pdf), str(dst), "MRR", False, logs.append)
    assert ok is False
    assert result == "corrupt"
    # File should be deleted
    assert not any(dst.rglob("*.pdf"))


def test_rename_and_move_moves_and_renames_valid_pdf(tmp_path):
    import io, pypdf
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    # Build a real minimal PDF
    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    pdf_path = src / "2024-01.pdf"
    pdf_path.write_bytes(buf.getvalue())
    logs = []
    ok, result = rename_and_move(str(pdf_path), str(dst), "MRR", False, logs.append)
    assert ok is True
    assert "MRR" in result
    assert os.path.exists(result)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_trains_app.py::test_verify_pdf_rejects_too_small -v
```

Expected: `ImportError` — `_verify_pdf` and `rename_and_move` not defined yet.

- [ ] **Step 3: Add `_verify_pdf` to `trains_app.py`**

After `save_settings` (~line 200), add:

```python
def _verify_pdf(path: str) -> bool:
    """Return True if the PDF at path appears valid (size + parseable)."""
    try:
        if os.path.getsize(path) < 10_240:
            return False
    except OSError:
        return False
    if not _PYPDF_AVAILABLE:
        return True
    try:
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(io.BytesIO(f.read()))
            return len(reader.pages) > 0
    except Exception:
        return False
```

- [ ] **Step 4: Extract `_rename_and_move` to module-level `rename_and_move`**

Add the following module-level function after `_verify_pdf`:

```python
def rename_and_move(src_path: str, dest_dir: str, hint_prefix: str | None,
                    flat: bool, log_fn) -> tuple[bool, str]:
    """
    Rename src_path per naming convention, move into dest_dir (or dest_dir/YYYY/),
    stamp metadata, verify integrity.
    Returns (True, dest_path) on success or (False, reason) on failure.
    """
    parsed = parse_pdf_filename(src_path, hint_prefix)
    if parsed:
        new_stem, year, mname = parsed
        target_dir = dest_dir if flat else os.path.join(dest_dir, year)
        os.makedirs(target_dir, exist_ok=True)
        dest = _unique_path(os.path.join(target_dir, new_stem + ".pdf"))
    else:
        mname = year = None
        os.makedirs(dest_dir, exist_ok=True)
        dest = _unique_path(os.path.join(dest_dir, os.path.basename(src_path)))

    shutil.move(src_path, dest)
    if year:
        _stamp_pdf_metadata(dest, mname, year, warn_fn=log_fn)

    if not _verify_pdf(dest):
        log_fn(f"  [corrupt] {os.path.basename(dest)} — deleted, will retry")
        try:
            os.unlink(dest)
        except OSError:
            pass
        return False, "corrupt"

    log_fn(f"  → {dest}")
    return True, dest
```

- [ ] **Step 5: Replace `MagazineDownloader._rename_and_move` with a wrapper**

Find `_rename_and_move` in `MagazineDownloader` (~line 1081). Replace the entire method body:

```python
def _rename_and_move(self, src_path: str, dest_dir: str, hint_prefix: str | None,
                     flat: bool = False) -> tuple[bool, str]:
    return rename_and_move(src_path, dest_dir, hint_prefix, flat, self._log)
```

- [ ] **Step 6: Update callers of `_rename_and_move` inside `MagazineDownloader`**

In `_flipbook_download` (~line 1035), change:

```python
dest_path = self._rename_and_move(new_path, dest_dir, hint_prefix, flat=flat)
return True, dest_path
```

to:

```python
return self._rename_and_move(new_path, dest_dir, hint_prefix, flat=flat)
```

In `_fetch_pdf` (~line 1069), change:

```python
dest_path = self._rename_and_move(tmp_path, dest_dir, hint_prefix, flat=flat)
tmp_path = None  # successfully moved — nothing to clean up
return True, dest_path
```

to:

```python
ok, result = self._rename_and_move(tmp_path, dest_dir, hint_prefix, flat=flat)
if ok:
    tmp_path = None  # successfully moved — nothing to clean up
return ok, result
```

- [ ] **Step 7: Run tests**

```
pytest tests/test_trains_app.py -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add trains_app.py tests/test_trains_app.py
git commit -m "feat: add PDF integrity check and extract rename_and_move to module level"
```

---

### Task 3: Extract `fetch_pdf` to Module Level

**Files:**
- Modify: `trains_app.py`

- [ ] **Step 1: Add module-level `fetch_pdf` after `rename_and_move`**

```python
def fetch_pdf(url: str, dest_dir: str, hint_prefix: str | None,
              cookies: dict, flat: bool,
              download_dir: str, log_fn) -> tuple[bool, str]:
    """
    Stream-download a PDF from a direct URL, save to download_dir,
    then rename/move/verify into dest_dir.
    Includes a short rate-limiting delay before the request.
    """
    import requests as _req
    from urllib.parse import urlparse

    time.sleep(0.5 + random.uniform(0, 1.0))  # rate limiting

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    tmp_path = None
    try:
        r = _req.get(url, cookies=cookies, headers=headers,
                     stream=True, timeout=DOWNLOAD_TIMEOUT)
        r.raise_for_status()

        raw_name = os.path.basename(urlparse(url).path) or "download.pdf"
        if not raw_name.lower().endswith(".pdf"):
            raw_name += ".pdf"

        tmp_path = os.path.join(download_dir, raw_name)
        with open(tmp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)

        ok, result = rename_and_move(tmp_path, dest_dir, hint_prefix, flat, log_fn)
        if ok:
            tmp_path = None  # successfully moved
        return ok, result

    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False, f"HTTP download failed: {e}"
```

- [ ] **Step 2: Replace `MagazineDownloader._fetch_pdf` with a wrapper**

Find `_fetch_pdf` in `MagazineDownloader` (~line 1041). Replace the entire method body:

```python
def _fetch_pdf(self, url: str, dest_dir: str, hint_prefix: str | None,
               cookies: dict, flat: bool = False) -> tuple[bool, str]:
    return fetch_pdf(url, dest_dir, hint_prefix, cookies, flat,
                     self.download_dir, self._log)
```

- [ ] **Step 3: Verify tests still pass**

```
pytest tests/test_trains_app.py -v
```

Expected: all pass (no behaviour change — just extraction).

- [ ] **Step 4: Commit**

```bash
git add trains_app.py
git commit -m "refactor: extract fetch_pdf to module level for thread-pool use"
```

---

### Task 4: `detect_download_mode` and `_handle_result` Helpers

**Files:**
- Modify: `trains_app.py`
- Modify: `tests/test_trains_app.py`

- [ ] **Step 1: Write failing tests for `_handle_result`**

Append to `tests/test_trains_app.py`:

```python
from trains_app import _handle_result


def _make_progress():
    return {"completed": [], "failed": []}


def test_handle_result_marks_completed_on_success(tmp_path):
    # Use a tmp progress file so save_progress doesn't write to _BASE_DIR
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(True, "/some/path.pdf", "http://x.com/issue/",
                       progress, completed_set, logs.append)
        assert "http://x.com/issue/" in completed_set
        assert "http://x.com/issue/" in progress["completed"]
        assert progress["failed"] == []
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_marks_completed_for_readonly(tmp_path):
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(False, "No PDF download available (read-only issue)",
                       "http://x.com/old/", progress, completed_set, logs.append)
        assert "http://x.com/old/" in completed_set
        assert "http://x.com/old/" in progress["completed"]
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_appends_failed_on_error(tmp_path):
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(False, "HTTP download failed: timeout",
                       "http://x.com/fail/", progress, completed_set, logs.append)
        assert "http://x.com/fail/" not in completed_set
        assert len(progress["failed"]) == 1
        assert progress["failed"][0]["url"] == "http://x.com/fail/"
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_does_not_duplicate_failed_entry(tmp_path):
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        progress["failed"].append({"url": "http://x.com/fail/", "reason": "old"})
        completed_set = set()
        logs = []
        _handle_result(False, "HTTP download failed: timeout",
                       "http://x.com/fail/", progress, completed_set, logs.append)
        assert len(progress["failed"]) == 1  # not duplicated
    finally:
        trains_app.PROGRESS_FILE = original
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_trains_app.py::test_handle_result_marks_completed_on_success -v
```

Expected: `ImportError` — `_handle_result` not defined.

- [ ] **Step 3: Add `detect_download_mode` and `_handle_result` to `trains_app.py`**

Add after `fetch_pdf` (before the `# Retry decorator` section):

```python
def detect_download_mode(driver) -> tuple[str, str | None]:
    """
    Inspect the currently-loaded page and return the download mode.
    Returns ('mode1', pdf_url), ('mode2', None), or ('mode3', None).
    Mode 1 = direct <a> download link.
    Mode 2 = real3d flipbook reader.
    Mode 3 = read-only, no download.
    """
    from selenium.webdriver.common.by import By

    for el in driver.find_elements(By.CSS_SELECTOR, "a.ci-btn--secondary[href]"):
        href = (el.get_attribute("href") or "").strip()
        if href:
            return "mode1", href
    for el in driver.find_elements(By.XPATH, "//a[normalize-space(.)='Download' and @href]"):
        href = (el.get_attribute("href") or "").strip()
        if href:
            return "mode1", href

    has_flipbook = bool(
        driver.find_elements(By.CSS_SELECTOR, "div.ci-media__cover")
        or driver.find_elements(
            By.XPATH, "//button[contains(normalize-space(.), 'Read Magazine')]"
        )
    )
    if has_flipbook:
        return "mode2", None

    return "mode3", None


def _handle_result(ok: bool, result: str, issue_url: str,
                   progress: dict, completed_set: set, log_fn) -> None:
    """Update progress tracking after a download attempt."""
    if ok:
        completed_set.add(issue_url)
        progress["completed"].append(issue_url)
        save_progress(progress)
    elif "read-only" in result or "No PDF download available" in result:
        log_fn(f"  [no pdf] {result}")
        completed_set.add(issue_url)
        progress["completed"].append(issue_url)
        save_progress(progress)
    else:
        log_fn(f"  FAILED: {result}")
        failed_urls = {
            e["url"] if isinstance(e, dict) else e
            for e in progress["failed"]
        }
        if issue_url not in failed_urls:
            progress["failed"].append({"url": issue_url, "reason": result})
        save_progress(progress)
```

- [ ] **Step 4: Run all tests**

```
pytest tests/test_trains_app.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add trains_app.py tests/test_trains_app.py
git commit -m "feat: add detect_download_mode and _handle_result helpers"
```

---

### Task 5: Parallel Mode 1 Downloads in `DownloadWorker`

**Files:**
- Modify: `trains_app.py`

- [ ] **Step 1: Add import at top of file**

Find the existing imports block. Add to the stdlib imports:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

- [ ] **Step 2: Update `all_tasks` to carry `mag_name`**

In `DownloadWorker.run()`, find:

```python
all_tasks: list[tuple[str, str, str, bool]] = []
```

Change to:

```python
all_tasks: list[tuple[str, str, str, bool, str]] = []  # (url, dest_dir, prefix, flat, mag_name)
```

Find where regular links are added:

```python
all_tasks.extend([(link, dest_dir, prefix, False) for link in links])
```

Change to:

```python
all_tasks.extend([(link, dest_dir, prefix, False, mag_name) for link in links])
```

Find where special links are added:

```python
all_tasks.extend([(link, special_dir, prefix, True) for link in special_links])
```

Change to:

```python
all_tasks.extend([(link, special_dir, prefix, True, mag_name) for link in special_links])
```

- [ ] **Step 3: Replace the sequential download loop with the parallel loop**

Find the comment `# -- Download each issue ---` and everything below it until the `self._log(f"\nSession complete...")` line. Replace that entire block with:

```python
            # -- Download each issue (Mode 1 parallel, Mode 2/3 sequential) ----
            self._start_time = time.time()
            done = 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                pending: dict = {}   # future → (issue_url, mag_name)

                for issue_url, dest_dir, prefix, flat, mag_name in all_tasks:
                    if self._stop:
                        self._log("Stopped by user.")
                        break

                    if issue_url in completed_set:
                        self._log(f"[skip] {issue_url}")
                        done += 1
                        self.signals.progress.emit(done, total)
                        continue

                    if issue_already_on_disk(issue_url, dest_dir, prefix, flat):
                        self._log(f"[exists] {issue_url}")
                        completed_set.add(issue_url)
                        progress["completed"].append(issue_url)
                        save_progress(progress)
                        done += 1
                        self.signals.progress.emit(done, total)
                        continue

                    self._log(f"[{done + 1}/{total}] {issue_url}")
                    try:
                        downloader._driver.get(issue_url)
                        time.sleep(2 + random.uniform(0, 0.5))
                        mode, pdf_url = detect_download_mode(downloader._driver)
                    except Exception as e:
                        self._log(f"  Error loading page: {e}")
                        _handle_result(False, str(e), issue_url,
                                       progress, completed_set, self._log)
                        done += 1
                        self.signals.progress.emit(done, total)
                        continue

                    if mode == "mode1":
                        cookies = {
                            c["name"]: c["value"]
                            for c in downloader._driver.get_cookies()
                        }
                        fut = pool.submit(
                            fetch_pdf, pdf_url, dest_dir, prefix,
                            cookies, flat, downloader.download_dir, self._log
                        )
                        pending[fut] = (issue_url, mag_name)
                        # Don't increment done yet — wait for future to complete
                    elif mode == "mode2":
                        try:
                            ok, result = downloader._flipbook_download(
                                issue_url, dest_dir, prefix, flat=flat
                            )
                        except Exception as e:
                            ok, result = False, str(e)
                        _handle_result(ok, result, issue_url,
                                       progress, completed_set, self._log)
                        done += 1
                        self.signals.progress.emit(done, total)
                        time.sleep(1 + random.uniform(0, 0.5))
                    else:  # mode3
                        _handle_result(
                            False, "No PDF download available (read-only issue)",
                            issue_url, progress, completed_set, self._log
                        )
                        done += 1
                        self.signals.progress.emit(done, total)

                # Drain completed Mode 1 futures
                for fut in as_completed(pending):
                    if self._stop:
                        break
                    issue_url, mag_name = pending[fut]
                    try:
                        ok, result = fut.result()
                    except Exception as e:
                        ok, result = False, str(e)
                    _handle_result(ok, result, issue_url,
                                   progress, completed_set, self._log)
                    done += 1
                    self.signals.progress.emit(done, total)

            self._log(f"\nSession complete. {len(progress['completed'])} total downloaded.")
```

- [ ] **Step 4: Add `_start_time` attribute to `DownloadWorker.__init__`**

In `DownloadWorker.__init__`, add after `self._stop = False`:

```python
self._start_time: float = 0.0
```

- [ ] **Step 5: Verify tests still pass**

```
pytest tests/test_trains_app.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add trains_app.py
git commit -m "feat: parallel Mode 1 downloads via ThreadPoolExecutor (3 workers)"
```

---

### Task 6: Pass 1 — Merge PR

- [ ] **Step 1: Push branch and open PR**

```bash
git push origin fix/bugs-and-version-bump
```

PR title: `feat: Pass 1 — settings persistence, integrity checks, parallel downloads`

- [ ] **Step 2: Verify CI passes, merge to main**

---

## PASS 2 — FRONTEND

---

### Task 7: Stacked Per-Magazine Progress Bars + ETA

**Files:**
- Modify: `trains_app.py`

- [ ] **Step 1: Add `magazine_progress` signal to `WorkerSignals`**

Find `WorkerSignals`:

```python
class WorkerSignals(QObject):
    log        = pyqtSignal(str)
    progress   = pyqtSignal(int, int)
    status_msg = pyqtSignal(str)
    finished   = pyqtSignal()
    error      = pyqtSignal(str)
```

Add the new signal:

```python
class WorkerSignals(QObject):
    log               = pyqtSignal(str)
    progress          = pyqtSignal(int, int)
    magazine_progress = pyqtSignal(str, int, int)   # (mag_name, done, total)
    status_msg        = pyqtSignal(str)
    finished          = pyqtSignal()
    error             = pyqtSignal(str)
```

- [ ] **Step 2: Emit ETA via `status_msg` and `magazine_progress` in `DownloadWorker`**

In `DownloadWorker`, add a helper method:

```python
def _emit_progress(self, done: int, total: int,
                   mag_name: str | None,
                   mag_done: dict, mag_total: dict) -> None:
    self.signals.progress.emit(done, total)
    if mag_name and mag_name in mag_total:
        mag_done[mag_name] = mag_done.get(mag_name, 0) + 1
        self.signals.magazine_progress.emit(
            mag_name, mag_done[mag_name], mag_total[mag_name]
        )
    elapsed = time.time() - self._start_time
    if elapsed > 0 and done > 0:
        rate = done / elapsed
        eta_sec = int((total - done) / rate) if rate > 0 else 0
        mins, secs = divmod(eta_sec, 60)
        eta_str = f"~{mins}m {secs:02d}s remaining" if eta_sec > 0 else "almost done"
    else:
        eta_str = "calculating..."
    self.signals.status_msg.emit(f"{done} / {total} issues · {eta_str}")
```

In `DownloadWorker.run()`, after building `all_tasks` and computing `total`, add:

```python
            mag_done: dict[str, int] = {}
            mag_total: dict[str, int] = {}
            for _, _, _, _, mn in all_tasks:
                if mn:
                    mag_total[mn] = mag_total.get(mn, 0) + 1
```

Replace every `self.signals.progress.emit(done, total)` in the download loop with:

```python
self._emit_progress(done, total, mag_name, mag_done, mag_total)
```

For the futures drain, `mag_name` comes from `pending[fut]`:

```python
                    issue_url, mag_name = pending[fut]
                    # ... after _handle_result ...
                    done += 1
                    self._emit_progress(done, total, mag_name, mag_done, mag_total)
```

- [ ] **Step 3: Replace `dl_progress` single bar with stacked container in `_make_download_tab`**

Find the progress bar creation block (~line 1857):

```python
        self.dl_progress = QProgressBar()
        self.dl_progress.setVisible(False)
        layout.addWidget(self.dl_progress)
```

Replace with:

```python
        # Progress container — holds one bar per magazine + summary label
        self._progress_container = QWidget()
        self._progress_container.setVisible(False)
        prog_layout = QVBoxLayout(self._progress_container)
        prog_layout.setContentsMargins(0, 0, 0, 0)
        prog_layout.setSpacing(6)
        self._mag_bar_rows: dict[str, tuple] = {}  # mag_name → (count_label, QProgressBar)
        self._summary_label = QLabel("")
        self._summary_label.setProperty("role", "status")
        prog_layout.addWidget(self._summary_label)
        layout.addWidget(self._progress_container)
```

- [ ] **Step 4: Build per-magazine rows when download starts**

In `_start_download`, after `self.dl_progress.setValue(0)` is removed, add:

```python
        # Build per-magazine progress rows
        prog_layout = self._progress_container.layout()
        # Clear old rows (keep summary label at index 0)
        while prog_layout.count() > 1:
            item = prog_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self._mag_bar_rows = {}
        for mag_name in magazines:
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 2)
            row_layout.setSpacing(2)
            header = QHBoxLayout()
            name_lbl = QLabel(mag_name)
            count_lbl = QLabel("0 / ?")
            count_lbl.setProperty("role", "muted")
            header.addWidget(name_lbl)
            header.addStretch()
            header.addWidget(count_lbl)
            bar = QProgressBar()
            bar.setValue(0)
            bar.setMaximum(1)  # updated when total known
            row_layout.addLayout(header)
            row_layout.addWidget(bar)
            prog_layout.addWidget(row_widget)
            self._mag_bar_rows[mag_name] = (count_lbl, bar)
        self._progress_container.setVisible(True)
        self._summary_label.setText("Starting…")
```

Remove the old `self.dl_progress.setVisible(True)` and `self.dl_progress.setValue(0)` lines.

- [ ] **Step 5: Wire `magazine_progress` signal to update individual bars**

In `_start_download`, after the existing signal connections, add:

```python
        self.worker.signals.magazine_progress.connect(self._update_mag_progress)
        self.worker.signals.status_msg.connect(self._summary_label.setText)
```

Add the slot method to `MainWindow`:

```python
    def _update_mag_progress(self, mag_name: str, done: int, total: int):
        if mag_name not in self._mag_bar_rows:
            return
        count_lbl, bar = self._mag_bar_rows[mag_name]
        bar.setMaximum(total)
        bar.setValue(done)
        count_lbl.setText(f"{done} / {total}")
```

- [ ] **Step 6: Update `_on_finished` to hide container instead of old progress bar**

`_on_finished` already calls `self.dl_progress.setVisible(False)` (from the earlier bug fix). Change that to:

```python
        self._progress_container.setVisible(False)
```

Also remove `self.dl_progress` references in `_update_progress`:

```python
    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.status_label.setText(f"{current} / {total} issues")
```

(The ETA text is now set by `_update_mag_progress` via `status_msg`.)

- [ ] **Step 7: Manual smoke test**

Run the app in test mode (3 issues). Verify stacked bars appear per selected magazine and update as issues download.

- [ ] **Step 8: Commit**

```bash
git add trains_app.py
git commit -m "feat: stacked per-magazine progress bars with ETA"
```

---

### Task 8: Smarter Log Panel

**Files:**
- Modify: `trains_app.py`

- [ ] **Step 1: Add line buffers and color helper to `MainWindow`**

In `MainWindow.__init__`, after `self._build_ui()`, add:

```python
        self._dl_log_lines:  list[str] = []
        self._org_log_lines: list[str] = []
```

Add this static method to `MainWindow`:

```python
    @staticmethod
    def _colorize(line: str) -> str:
        """Return an HTML-colored version of a log line."""
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if "FAILED" in line or "ERROR:" in line:
            color = "#f38ba8"
        elif "[corrupt]" in line:
            color = "#fab387"
        elif line.startswith("  [skip]") or line.startswith("[skip]") \
                or line.startswith("  [exists]") or line.startswith("[exists]"):
            color = "#45475a"
        elif " → " in line or "Downloaded:" in line:
            color = "#a6e3a1"
        else:
            color = "#a6adc8"
        return f'<span style="color:{color}">{esc}</span>'
```

- [ ] **Step 2: Replace `_append_log` with a buffering + filtering version**

Replace the existing `_append_log` static method with:

```python
    def _append_log(self, log: QTextEdit, msg: str,
                    lines_buf: list, filter_edit: QLineEdit,
                    badge_label: QLabel, max_lines: int = 2000) -> None:
        lines_buf.append(msg)
        if len(lines_buf) > max_lines:
            lines_buf.pop(0)

        # Update error badge
        error_count = sum(
            1 for l in lines_buf if "FAILED" in l or "ERROR:" in l
        )
        if error_count > 0:
            badge_label.setText(f"{error_count} error{'s' if error_count != 1 else ''}")
            badge_label.setVisible(True)
        else:
            badge_label.setVisible(False)

        # Only append if line matches current filter
        filt = filter_edit.text().strip().lower()
        if filt and filt not in msg.lower():
            return
        log.append(self._colorize(msg))
        log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())
```

- [ ] **Step 3: Add log toolbar to Download tab**

In `_make_download_tab`, find:

```python
        log_cap = QLabel("DOWNLOAD LOG")
        log_cap.setProperty("role", "log-cap")
        layout.addWidget(log_cap)

        self.dl_log = QTextEdit()
        self.dl_log.setReadOnly(True)
        layout.addWidget(self.dl_log)
```

Replace with:

```python
        log_cap = QLabel("DOWNLOAD LOG")
        log_cap.setProperty("role", "log-cap")
        layout.addWidget(log_cap)

        log_toolbar = QHBoxLayout()
        self._dl_filter = QLineEdit()
        self._dl_filter.setPlaceholderText("Filter log…")
        self._dl_filter.setFixedHeight(28)
        self._dl_error_badge = QLabel("")
        self._dl_error_badge.setVisible(False)
        self._dl_error_badge.setStyleSheet("color:#f38ba8;font-weight:600;padding:0 6px")
        self._dl_copy_errors_btn = QPushButton("Copy Errors")
        self._dl_copy_errors_btn.setFixedHeight(28)
        self._dl_copy_errors_btn.clicked.connect(
            lambda: self._copy_errors(self._dl_log_lines)
        )
        log_toolbar.addWidget(self._dl_filter)
        log_toolbar.addWidget(self._dl_error_badge)
        log_toolbar.addWidget(self._dl_copy_errors_btn)
        layout.addLayout(log_toolbar)

        self.dl_log = QTextEdit()
        self.dl_log.setReadOnly(True)
        layout.addWidget(self.dl_log)

        # Rebuild display on filter change
        self._dl_filter.textChanged.connect(
            lambda: self._rebuild_log(self.dl_log, self._dl_log_lines, self._dl_filter)
        )
```

- [ ] **Step 4: Add log toolbar to Organize tab**

In `_make_organize_tab`, find:

```python
        log_cap = QLabel("ORGANIZE LOG")
        log_cap.setProperty("role", "log-cap")
        layout.addWidget(log_cap)

        self.org_log = QTextEdit()
        self.org_log.setReadOnly(True)
        layout.addWidget(self.org_log)
```

Replace with:

```python
        log_cap = QLabel("ORGANIZE LOG")
        log_cap.setProperty("role", "log-cap")
        layout.addWidget(log_cap)

        org_log_toolbar = QHBoxLayout()
        self._org_filter = QLineEdit()
        self._org_filter.setPlaceholderText("Filter log…")
        self._org_filter.setFixedHeight(28)
        self._org_error_badge = QLabel("")
        self._org_error_badge.setVisible(False)
        self._org_error_badge.setStyleSheet("color:#f38ba8;font-weight:600;padding:0 6px")
        self._org_copy_errors_btn = QPushButton("Copy Errors")
        self._org_copy_errors_btn.setFixedHeight(28)
        self._org_copy_errors_btn.clicked.connect(
            lambda: self._copy_errors(self._org_log_lines)
        )
        org_log_toolbar.addWidget(self._org_filter)
        org_log_toolbar.addWidget(self._org_error_badge)
        org_log_toolbar.addWidget(self._org_copy_errors_btn)
        layout.addLayout(org_log_toolbar)

        self.org_log = QTextEdit()
        self.org_log.setReadOnly(True)
        layout.addWidget(self.org_log)

        self._org_filter.textChanged.connect(
            lambda: self._rebuild_log(self.org_log, self._org_log_lines, self._org_filter)
        )
```

- [ ] **Step 5: Add `_rebuild_log` and `_copy_errors` helpers**

Add to `MainWindow`:

```python
    def _rebuild_log(self, log: QTextEdit, lines_buf: list, filter_edit: QLineEdit) -> None:
        filt = filter_edit.text().strip().lower()
        log.clear()
        for line in lines_buf:
            if filt and filt not in line.lower():
                continue
            log.append(self._colorize(line))
        log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())

    def _copy_errors(self, lines_buf: list) -> None:
        errors = [l for l in lines_buf if "FAILED" in l or "ERROR:" in l]
        if errors:
            QApplication.clipboard().setText("\n".join(errors))
```

- [ ] **Step 6: Update `_dl_log` and org log callers to use new signature**

Replace:

```python
    def _dl_log(self, msg: str):
        self._append_log(self.dl_log, msg)
```

With:

```python
    def _dl_log(self, msg: str):
        self._append_log(self.dl_log, msg,
                         self._dl_log_lines, self._dl_filter, self._dl_error_badge)
```

Update every `self._append_log(self.org_log, ...)` call. There are exactly 4 sites — update each one:

**In `_run_organize`** (2 calls):
```python
self._append_log(self.org_log, f"Organizing PDFs from: {src}",
                 self._org_log_lines, self._org_filter, self._org_error_badge)
self._append_log(self.org_log, f"                  to: {dst}\n",
                 self._org_log_lines, self._org_filter, self._org_error_badge)
```

**In `_run_organize` signal connection** (1 lambda):
```python
self._org_worker.signals.log.connect(
    lambda m: self._append_log(self.org_log, m,
                               self._org_log_lines, self._org_filter, self._org_error_badge)
)
```

**In `_on_organize_finished`** (multiple calls — update all of them the same way):
```python
self._append_log(self.org_log, f"\n-- {moved} moved ...",
                 self._org_log_lines, self._org_filter, self._org_error_badge)
# ...and every other self._append_log(self.org_log, ...) in this method
```

**In `_start_missing_download` signal connection** (1 lambda):
```python
self._missing_worker.signals.log.connect(
    lambda m: self._append_log(self.org_log, m,
                               self._org_log_lines, self._org_filter, self._org_error_badge)
)
```

**In `_on_missing_finished`**:
```python
self._append_log(self.org_log, "--- Download complete ---",
                 self._org_log_lines, self._org_filter, self._org_error_badge)
```

- [ ] **Step 7: Also initialize `_dl_log_lines` and `_org_log_lines` before `_build_ui` is called**

In `MainWindow.__init__`, add before `self._build_ui()`:

```python
        self._dl_log_lines:  list[str] = []
        self._org_log_lines: list[str] = []
```

Remove the duplicate lines added in Step 1.

- [ ] **Step 8: Manual smoke test**

Run app. Type in filter box — log should filter live. Trigger an error — badge should appear. Click "Copy Errors" — paste somewhere to confirm.

- [ ] **Step 9: Commit**

```bash
git add trains_app.py
git commit -m "feat: smarter log panel with filter, error badge, and copy errors"
```

---

### Task 9: System Tray

**Files:**
- Modify: `trains_app.py`

- [ ] **Step 1: Add `QMenu` to imports**

Find the PyQt5 imports block. Add `QMenu` to the `QWidgets` import:

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QMessageBox,
    QTabWidget, QFrame, QSizePolicy, QMenu,
)
```

Add `QSystemTrayIcon` to the `QtWidgets` import (it lives there in PyQt5):

```python
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QMessageBox,
    QTabWidget, QFrame, QSizePolicy, QMenu, QSystemTrayIcon,
)
```

- [ ] **Step 2: Set up tray in `MainWindow.__init__`**

After `self._load_settings()`, add:

```python
        self._setup_tray()
```

Add the method to `MainWindow`:

```python
    def _setup_tray(self):
        QApplication.instance().setQuitOnLastWindowClosed(False)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(
                __import__("PyQt5.QtWidgets", fromlist=["QStyle"]).QStyle.SP_DriveNetIcon
            )
        self._tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction("Show Window", self.show)
        menu.addAction("Quit", QApplication.instance().quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.setToolTip("Trains Downloader — Idle")
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.activateWindow()
```

- [ ] **Step 3: Override `closeEvent`**

Add to `MainWindow`:

```python
    def closeEvent(self, event):
        running = (
            (self.worker is not None and self.worker.isRunning())
            or (self._missing_worker is not None and self._missing_worker.isRunning())
        )
        if not running:
            event.accept()
            return
        event.ignore()
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Download in progress")
        dlg.setText("A download is running. What would you like to do?")
        minimize_btn = dlg.addButton("Minimize to Tray", QMessageBox.AcceptRole)
        stop_btn     = dlg.addButton("Stop & Quit",      QMessageBox.DestructiveRole)
        dlg.addButton("Cancel",                          QMessageBox.RejectRole)
        dlg.exec_()
        clicked = dlg.clickedButton()
        if clicked is minimize_btn:
            self.hide()
        elif clicked is stop_btn:
            for w in (self.worker, self._missing_worker):
                if w is not None and w.isRunning():
                    w.stop()
            QApplication.instance().quit()
```

- [ ] **Step 4: Update tray tooltip on progress and finish**

In `_update_progress`, add at the end:

```python
        self._tray.setToolTip(f"Trains Downloader — {current} / {total} downloading…")
```

In `_on_finished`, add after the existing lines:

```python
        self._tray.setToolTip("Trains Downloader — Idle")
```

- [ ] **Step 5: Manual smoke test**

Run app, start a download, click X — dialog should appear with three options. Choose "Minimize to Tray" — app disappears from taskbar but tray icon visible. Double-click tray icon — window reappears. Right-click tray icon → Quit works.

- [ ] **Step 6: Commit**

```bash
git add trains_app.py
git commit -m "feat: system tray icon with minimize-to-tray on close during download"
```

---

### Task 10: Bump Version + Pass 2 PR

- [ ] **Step 1: Bump version**

In `trains_app.py`, change:

```python
APP_VERSION = "1.4.0"
```

to:

```python
APP_VERSION = "1.5.0"
```

- [ ] **Step 2: Run full test suite one final time**

```
pytest tests/test_trains_app.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit and push**

```bash
git add trains_app.py
git commit -m "chore: bump version to 1.5.0"
git push origin fix/bugs-and-version-bump
```

- [ ] **Step 4: Open PR**

PR title: `feat: Pass 2 — stacked progress bars, smarter log, system tray (v1.5.0)`

- [ ] **Step 5: Merge to main to trigger CI build + release**
