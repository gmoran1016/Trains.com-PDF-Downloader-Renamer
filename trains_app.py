#!/usr/bin/env python3
"""
Trains.com Magazine Downloader & Organizer
All-in-one tool: download all trains.com magazines and organize/rename PDFs.
Requires: Python 3.10+, selenium>=4.6, PyQt5, requests, beautifulsoup4
"""

import sys
import os
import json
import re
import shutil
import time
import logging
import random
import pickle
from calendar import month_name, month_abbr as _month_abbr
from pathlib import Path
from functools import wraps

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QMessageBox,
    QTabWidget,
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread
from PyQt5.QtGui import QFont

# ------------------------------------------------------------------------------
# Base directory — next to the .exe when frozen, next to the script otherwise
# ------------------------------------------------------------------------------
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------
LOG_FILE = os.path.join(_BASE_DIR, "trains_downloader.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------------------
MAGAZINES = {
    "Model Railroader": {
        "url": "https://www.trains.com/mrr/magazine/",
        "prefix": "MRR",
    },
    "Trains Magazine": {
        "url": "https://www.trains.com/trn/magazine/",
        "prefix": "TRN",
    },
    "Classic Toy Trains": {
        "url": "https://www.trains.com/ctt/magazine/",
        "prefix": "CTT",
    },
    "Classic Trains": {
        "url": "https://www.trains.com/ctr/magazine/",
        "prefix": "CTR",
    },
    "Garden Railways": {
        "url": "https://www.trains.com/grw/magazine/",
        "prefix": "GRW",
    },
}

# Path segments that are not individual issue pages
_NON_ISSUE_SLUGS = frozenset({
    "current-issue", "special-issues", "staff", "annual-index",
    "contributor-guidelines", "archive-access", "subscription-plans",
    "subscriptions", "page",
})

DEFAULT_COOKIES_FILE = os.path.join(_BASE_DIR, "session_cookies.json")
PROGRESS_FILE = os.path.join(_BASE_DIR, "download_progress.json")
DOWNLOAD_TIMEOUT = 120   # seconds to wait for a PDF download
LOGIN_TIMEOUT = 300      # seconds to wait for manual login (5 min)

# ------------------------------------------------------------------------------
# Cookie utilities
# ------------------------------------------------------------------------------

def save_cookies_json(cookies: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    logger.info(f"Saved {len(cookies)} cookies to {path}")


def load_cookies_json(path: str) -> list:
    """Load cookies from a JSON file."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load JSON cookies from {path}: {e}")
        return []


def load_cookies_pickle(path: str) -> list:
    """Load cookies from the legacy pickle format."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"Could not load pickle cookies from {path}: {e}")
        return []


def load_cookies(path: str) -> list:
    """Auto-detect JSON or pickle format and load cookies."""
    if path.endswith(".pkl") or path.endswith(".pickle"):
        return load_cookies_pickle(path)
    # Try JSON first; fall back to pickle
    cookies = load_cookies_json(path)
    if not cookies:
        cookies = load_cookies_pickle(path)
    return cookies


# ------------------------------------------------------------------------------
# Progress tracking
# ------------------------------------------------------------------------------

def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r") as f:
                data = json.load(f)
            # ensure required keys
            data.setdefault("completed", [])
            data.setdefault("failed", [])
            return data
        except Exception:
            pass
    return {"completed": [], "failed": []}


def save_progress(progress: dict) -> None:
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")


# ------------------------------------------------------------------------------
# File renamer / organizer
# ------------------------------------------------------------------------------
_abbr_list = [a for a in _month_abbr if a]
MONTH_FROM_ABBR = {a.upper(): month_name[i + 1] for i, a in enumerate(_abbr_list)}
MONTHNUM_FROM_ABBR = {a.upper(): f"{i + 1:02d}" for i, a in enumerate(_abbr_list)}
ALL_MONTHS = list(month_name)[1:]


def _guess_prefix(filename: str) -> str:
    low = filename.lower()
    if re.search(r"\btrn\b|trains\s+magazine", low):
        return "TRN"
    if re.search(r"\bctt\b|classic\s+toy", low):
        return "CTT"
    if re.search(r"\bctr\b|classic\s+trains", low):
        return "CTR"
    if re.search(r"\bgrw\b|garden\s+rail", low):
        return "GRW"
    return "MRR"


def parse_pdf_filename(filepath: str, hint_prefix: str | None = None):
    """
    Parse a PDF filename and return (new_stem, year_str, month_name) or None.
    Tries multiple date-in-filename patterns.
    """
    name, ext = os.path.splitext(os.path.basename(filepath))
    if ext.lower() != ".pdf":
        return None

    prefix = hint_prefix or _guess_prefix(name)

    # Pattern 1: YYYY_MM or YYYY-MM
    m = re.search(r"(\d{4})[_\-](\d{1,2})(?:\D|$)", name)
    if m:
        year, mnum = int(m.group(1)), int(m.group(2))
        if 1900 <= year <= 2099 and 1 <= mnum <= 12:
            mname = month_name[mnum]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 2: YYYYMM (6 consecutive digits)
    m = re.search(r"(\d{4})(\d{2})(?:\D|$)", name)
    if m:
        year, mnum = int(m.group(1)), int(m.group(2))
        if 1900 <= year <= 2099 and 1 <= mnum <= 12:
            mname = month_name[mnum]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 3: 3-letter month abbreviation + 2-4 digit year (e.g. Jan2024, Jan-24)
    m = re.search(r"([A-Za-z]{3})[_\-]?(\d{2,4})(?:\D|$)", name)
    if m:
        abbr = m.group(1).upper()
        if abbr in MONTH_FROM_ABBR:
            year = int(m.group(2))
            if year < 100:
                year += 2000
            if 1900 <= year <= 2099:
                mname = MONTH_FROM_ABBR[abbr]
                mnum = MONTHNUM_FROM_ABBR[abbr]
                return f"{prefix}-{mnum}-{mname}-{year}", str(year), mname

    return None


def _unique_path(base_path: str) -> str:
    if not os.path.exists(base_path):
        return base_path
    root, ext = os.path.splitext(base_path)
    i = 1
    while os.path.exists(f"{root}-{i}{ext}"):
        i += 1
    return f"{root}-{i}{ext}"


def organize_pdfs(source_dir: str, dest_dir: str, hint_prefix: str | None = None, log_fn=None):
    """
    Move and rename PDFs from source_dir into dest_dir/YYYY/ subfolders.
    Returns (moved_count, skipped_count, missing_report_lines).
    """
    def _log(msg):
        logger.info(msg)
        if log_fn:
            log_fn(msg)

    issues_by_year: dict[str, set] = {}
    moved = skipped = 0

    for root, _, files in os.walk(source_dir):
        for fname in files:
            if not fname.lower().endswith(".pdf"):
                continue
            fpath = os.path.join(root, fname)
            parsed = parse_pdf_filename(fpath, hint_prefix)
            if not parsed:
                _log(f"  Skipping (unrecognized): {fname}")
                skipped += 1
                continue
            new_stem, year, mname = parsed
            year_dir = os.path.join(dest_dir, year)
            os.makedirs(year_dir, exist_ok=True)
            dest_path = _unique_path(os.path.join(year_dir, new_stem + ".pdf"))
            shutil.move(fpath, dest_path)
            _log(f"  {fname}  →  {dest_path}")
            issues_by_year.setdefault(year, set()).add(mname)
            moved += 1

    report = []
    for year in sorted(issues_by_year):
        missing = [m for m in ALL_MONTHS if m not in issues_by_year[year]]
        report.append(f"{year}: {'complete' if not missing else 'missing ' + str(missing)}")
    return moved, skipped, report


# ------------------------------------------------------------------------------
# Retry decorator
# ------------------------------------------------------------------------------
def retry(attempts=3, delay=2.0, exceptions=(Exception,)):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if i == attempts - 1:
                        raise
                    wait = delay * (2 ** i) + random.uniform(0, 0.5)
                    logger.warning(f"{fn.__name__} attempt {i+1} failed: {e}. Retrying in {wait:.1f}s…")
                    time.sleep(wait)
        return wrapper
    return decorator


# ------------------------------------------------------------------------------
# Selenium downloader
# ------------------------------------------------------------------------------
class MagazineDownloader:
    """
    Selenium-based downloader for trains.com magazines.
    Uses Selenium 4's built-in driver manager (no webdriver_manager needed).
    """

    def __init__(self, download_dir: str, headless: bool = False, log_fn=None):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        self.download_dir = os.path.abspath(download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        self.log_fn = log_fn
        self._driver = None

        opts = Options()
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option("prefs", {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-gpu")

        # Selenium 4.6+ selenium-manager auto-downloads the right chromedriver
        self._driver = webdriver.Chrome(options=opts)
        self._log("Browser started.")

    def _log(self, msg: str):
        logger.info(msg)
        if self.log_fn:
            self.log_fn(msg)

    def close(self):
        try:
            if self._driver:
                self._driver.quit()
                self._log("Browser closed.")
        except Exception:
            pass

    # -- Cookies ------------------------------------------------------------
    def add_cookies(self, cookies: list):
        """Add a list of cookies to the current browser session."""
        # Must be on the target domain first
        self._driver.get("https://www.trains.com/")
        time.sleep(1)
        added = 0
        for c in cookies:
            try:
                # Remove keys Selenium doesn't accept
                safe = {k: v for k, v in c.items()
                        if k in ("name", "value", "domain", "path", "secure", "expiry", "httpOnly")}
                self._driver.add_cookie(safe)
                added += 1
            except Exception as e:
                logger.debug(f"Skipping cookie {c.get('name', '?')}: {e}")
        self._log(f"Added {added}/{len(cookies)} cookies.")

    def save_cookies(self, path: str):
        cookies = self._driver.get_cookies()
        save_cookies_json(cookies, path)

    # -- Login ---------------------------------------------------------------
    def is_logged_in(self, url: str = "https://www.trains.com/") -> bool:
        try:
            self._driver.get(url)
            time.sleep(2)
            src = self._driver.page_source.lower()
            return any(k in src for k in ("log out", "logout", "sign out", "my account"))
        except Exception as e:
            logger.error(f"Login check error: {e}")
            return False

    def wait_for_manual_login(self, timeout: int = LOGIN_TIMEOUT, progress_fn=None) -> bool:
        """
        Open trains.com in the visible browser and poll until the user
        has successfully logged in (or timeout expires).
        """
        self._driver.get("https://www.trains.com/")
        self._log("Please log in via the browser window. Waiting…")
        deadline = time.time() + timeout
        while time.time() < deadline:
            src = self._driver.page_source.lower()
            if any(k in src for k in ("log out", "logout", "sign out", "my account")):
                self._log("Login detected.")
                return True
            remaining = int(deadline - time.time())
            if progress_fn:
                progress_fn(f"Waiting for login… ({remaining}s remaining)")
            time.sleep(3)
        return False

    # -- Issue link collection ------------------------------------------------
    def _is_issue_link(self, href: str, archive_url: str) -> bool:
        """
        Return True if href looks like an individual issue page under archive_url.
        Rejects year-filter URLs (?archive_year=…), pagination (/page/N/),
        and known non-issue slugs (current-issue, special-issues, etc.).
        """
        if not href or not href.startswith(archive_url):
            return False
        if "?" in href:          # year filter / query params
            return False
        if "#" in href:          # anchor/fragment links (e.g. #content, #top)
            return False
        suffix = href[len(archive_url):].strip("/")
        if not suffix:           # bare archive URL itself
            return False
        first_slug = suffix.split("/")[0]
        if first_slug in _NON_ISSUE_SLUGS:
            return False
        return True

    @retry(attempts=3, exceptions=(Exception,))
    def get_page_issue_links(self, url: str, archive_url: str) -> list:
        from selenium.webdriver.common.by import By
        self._driver.get(url)
        time.sleep(2)
        anchors = self._driver.find_elements(By.TAG_NAME, "a")
        links = []
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                if self._is_issue_link(href, archive_url) and href not in links:
                    links.append(href)
            except Exception:
                continue
        return links

    def collect_all_issue_links(self, archive_url: str, max_pages: int = 110) -> list:
        """
        New trains.com pagination: page 1 = archive_url, page N = archive_url + 'page/N/'
        """
        all_links: list = []
        for page_num in range(1, max_pages + 1):
            url = archive_url if page_num == 1 else f"{archive_url}page/{page_num}/"
            try:
                page_links = self.get_page_issue_links(url, archive_url)
            except Exception as e:
                self._log(f"  Error on page {page_num}: {e}")
                break

            new = [l for l in page_links if l not in all_links]
            if not new:
                self._log(f"  No more issues after page {page_num - 1} -- done.")
                break
            all_links.extend(new)
            self._log(f"  Page {page_num}: {len(new)} issues ({len(all_links)} total)")
            time.sleep(1 + random.uniform(0, 0.5))

        return all_links

    # -- Single issue download ------------------------------------------------
    def download_issue(self, issue_url: str, dest_dir: str,
                       hint_prefix: str | None = None) -> tuple[bool, str]:
        """
        Three download modes for trains.com issues:

        Mode 1 — Direct link: recent issues have
          <a class="ci-btn ci-btn--secondary" href="...pdf">Download</a>
          → fetched via requests with session cookies.

        Mode 2 — Flipbook reader: mid-era issues embed a real3d-flipbook
          whose toolbar contains <span data-name="btnDownloadPdf">.
          JS-clicking it triggers an immediate browser download.

        Mode 3 — Read-only: very old digitised-only issues have no
          download button at all → skipped gracefully.
        """
        from selenium.webdriver.common.by import By

        try:
            self._driver.get(issue_url)
            time.sleep(2 + random.uniform(0, 0.5))

            # ---- Mode 1: direct <a> download link ---------------------------
            pdf_url = None
            for el in self._driver.find_elements(By.CSS_SELECTOR, "a.ci-btn--secondary[href]"):
                href = (el.get_attribute("href") or "").strip()
                if href:
                    pdf_url = href
                    break
            if not pdf_url:
                for el in self._driver.find_elements(
                    By.XPATH, "//a[normalize-space(.)='Download' and @href]"
                ):
                    href = (el.get_attribute("href") or "").strip()
                    if href:
                        pdf_url = href
                        break
            if pdf_url:
                cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
                return self._fetch_pdf(pdf_url, dest_dir, hint_prefix, cookies)

            # ---- Mode 2: flipbook reader ----------------------------------------
            # The btnDownloadPdf span only exists AFTER the reader is opened.
            # Detect the flipbook cover div or "Read Magazine" button as the trigger.
            has_flipbook = bool(
                self._driver.find_elements(By.CSS_SELECTOR, "div.ci-media__cover")
                or self._driver.find_elements(
                    By.XPATH, "//button[contains(normalize-space(.), 'Read Magazine')]"
                )
            )
            if has_flipbook:
                return self._flipbook_download(issue_url, dest_dir, hint_prefix)

            # ---- Mode 3: no download available (read-only) ------------------
            return False, "No PDF download available (read-only issue)"

        except Exception as e:
            logger.exception(f"Error downloading {issue_url}")
            return False, str(e)

    def _flipbook_download(self, issue_url: str, dest_dir: str,
                           hint_prefix: str | None) -> tuple[bool, str]:
        """
        Open the real3d-flipbook reader, click its download button, and wait
        for the PDF to land in self.download_dir, then rename/move it.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        def pdf_files():
            return {
                f for f in os.listdir(self.download_dir)
                if f.lower().endswith(".pdf") and not f.endswith(".crdownload")
            }

        before = pdf_files()

        from selenium.webdriver.common.action_chains import ActionChains

        def _try_click(el):
            """Scroll into view and try ActionChains click, fall back to JS click."""
            self._driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", el
            )
            time.sleep(0.5)
            try:
                ActionChains(self._driver).move_to_element(el).click().perform()
            except Exception:
                try:
                    self._driver.execute_script("arguments[0].click();", el)
                except Exception:
                    pass

        def _find_reader_trigger():
            """Return the preview image (or its flipbook parent div) to click."""
            # The cover image has 'Magazine-Archives' in its src URL.
            # Its parent is the real3dflipbook div which holds the click handler.
            for img in self._driver.find_elements(By.TAG_NAME, "img"):
                try:
                    src = img.get_attribute("src") or ""
                    if "magazine-archives" in src.lower():
                        # Prefer the real3dflipbook parent div as click target
                        parent = self._driver.execute_script(
                            "return arguments[0].parentElement;", img
                        )
                        flipbook_div = self._driver.execute_script(
                            "return arguments[0].parentElement;", parent
                        )
                        if flipbook_div and "real3dflipbook" in (
                            flipbook_div.get_attribute("class") or ""
                        ):
                            return flipbook_div
                        return img
                except Exception:
                    continue
            # Fallback: the ci-media__cover div
            covers = self._driver.find_elements(By.CSS_SELECTOR, "div.ci-media__cover")
            return covers[0] if covers else None

        # Step 1 & 2: click to open the reader, then wait for the download button.
        # Retry up to 5 times (some pages load the flipbook slowly or need a second click).
        btn_el = None
        for attempt in range(5):
            trigger = _find_reader_trigger()
            if trigger:
                _try_click(trigger)
            # Wait up to 12s per attempt for the download button to appear
            try:
                btn_el = WebDriverWait(self._driver, 12).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "span[data-name='btnDownloadPdf']")
                    )
                )
                break  # found it
            except Exception:
                pass  # not yet — try clicking again

        if btn_el is None:
            return False, "Flipbook download button never appeared after multiple attempts"

        # Give the reader a brief moment after the button appears
        time.sleep(1)

        # Step 3: JS-click the download button
        self._driver.execute_script("arguments[0].click();", btn_el)
        self._log(f"  Clicked flipbook download button")

        # Step 4: check if a new tab opened containing the PDF URL
        time.sleep(2)
        handles = self._driver.window_handles
        if len(handles) > 1:
            self._driver.switch_to.window(handles[-1])
            new_url = self._driver.current_url
            if ".pdf" in new_url.lower():
                cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
                self._driver.close()
                self._driver.switch_to.window(handles[0])
                return self._fetch_pdf(new_url, dest_dir, hint_prefix, cookies)
            self._driver.close()
            self._driver.switch_to.window(handles[0])

        # Step 5: wait for a completed .pdf file in the download directory (90s)
        deadline = time.time() + 90
        while time.time() < deadline:
            after = pdf_files()
            new_files = after - before
            if new_files:
                new_path = os.path.join(self.download_dir, next(iter(new_files)))
                time.sleep(1)  # ensure file is fully written
                dest_path = self._rename_and_move(new_path, dest_dir, hint_prefix)
                return True, dest_path
            time.sleep(1.5)

        return False, "Flipbook download timed out (no file appeared within 90s)"

    def _fetch_pdf(self, url: str, dest_dir: str, hint_prefix: str | None,
                   cookies: dict) -> tuple[bool, str]:
        """Stream-download a PDF from a direct URL and save/rename into dest_dir."""
        import requests as _req
        from urllib.parse import urlparse

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            r = _req.get(url, cookies=cookies, headers=headers,
                         stream=True, timeout=120)
            r.raise_for_status()

            raw_name = os.path.basename(urlparse(url).path) or "download.pdf"
            if not raw_name.lower().endswith(".pdf"):
                raw_name += ".pdf"

            tmp_path = os.path.join(self.download_dir, raw_name)
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)

            dest_path = self._rename_and_move(tmp_path, dest_dir, hint_prefix)
            return True, dest_path

        except Exception as e:
            return False, f"HTTP download failed: {e}"

    def _rename_and_move(self, src_path: str, dest_dir: str, hint_prefix: str | None) -> str:
        """
        Rename src_path according to our naming convention and move it into
        dest_dir/YYYY/  (or dest_dir/ if the year can't be determined).
        """
        parsed = parse_pdf_filename(src_path, hint_prefix)
        if parsed:
            new_stem, year, _ = parsed
            year_dir = os.path.join(dest_dir, year)
            os.makedirs(year_dir, exist_ok=True)
            dest = _unique_path(os.path.join(year_dir, new_stem + ".pdf"))
        else:
            os.makedirs(dest_dir, exist_ok=True)
            dest = _unique_path(os.path.join(dest_dir, os.path.basename(src_path)))

        shutil.move(src_path, dest)
        self._log(f"  → {dest}")
        return dest


# ------------------------------------------------------------------------------
# Worker thread
# ------------------------------------------------------------------------------
class WorkerSignals(QObject):
    log        = pyqtSignal(str)
    progress   = pyqtSignal(int, int)   # (current, total)
    status_msg = pyqtSignal(str)
    finished   = pyqtSignal()
    error      = pyqtSignal(str)


class DownloadWorker(QThread):
    def __init__(self, magazines: list, base_dir: str, headless: bool,
                 test_mode: bool, cookies_path: str | None, newest_first: bool):
        super().__init__()
        self.magazines    = magazines
        self.base_dir     = base_dir
        self.headless     = headless
        self.test_mode    = test_mode
        self.cookies_path = cookies_path
        self.newest_first = newest_first
        self.signals      = WorkerSignals()
        self._stop        = False

    def stop(self):
        self._stop = True

    def _log(self, msg: str):
        logger.info(msg)
        self.signals.log.emit(msg)

    def run(self):
        downloader = None
        try:
            self._log("Starting browser…")
            downloader = MagazineDownloader(
                download_dir=self.base_dir,
                headless=self.headless,
                log_fn=self.signals.log.emit,
            )

            # -- Authentication ---------------------------------------------
            logged_in = False
            if self.cookies_path and os.path.exists(self.cookies_path):
                cookies = load_cookies(self.cookies_path)
                if cookies:
                    downloader.add_cookies(cookies)
                    logged_in = downloader.is_logged_in()
                    if logged_in:
                        self._log("Authenticated via saved cookies.")
                    else:
                        self._log("Saved cookies did not authenticate — need to log in manually.")

            if not logged_in:
                if self.headless:
                    self.signals.error.emit(
                        "Not logged in and headless mode is ON.\n"
                        "Disable headless mode so you can log in via the browser window."
                    )
                    return
                self._log("Please log in via the browser window (you have 5 minutes)…")
                if not downloader.wait_for_manual_login(
                    timeout=LOGIN_TIMEOUT,
                    progress_fn=self.signals.status_msg.emit,
                ):
                    self.signals.error.emit("Login timed out. Please try again.")
                    return
                # Save fresh cookies
                if self.cookies_path:
                    downloader.save_cookies(self.cookies_path)
                    self._log(f"Cookies saved to {self.cookies_path}")

            # -- Collect all issue links ------------------------------------
            progress = load_progress()
            # each task: (url, dest_dir, prefix)
            all_tasks: list[tuple[str, str, str]] = []

            for mag_name in self.magazines:
                if self._stop:
                    break
                info        = MAGAZINES[mag_name]
                archive_url = info["url"]
                prefix      = info["prefix"]
                # Final organized location for this magazine
                dest_dir = os.path.join(self.base_dir, prefix)
                os.makedirs(dest_dir, exist_ok=True)

                self._log(f"\n-- {mag_name} --")
                max_pages = 3 if self.test_mode else 110
                links = downloader.collect_all_issue_links(archive_url, max_pages=max_pages)
                if not self.newest_first:   # list is already newest-first from the archive
                    links = list(reversed(links))
                all_tasks.extend([(link, dest_dir, prefix) for link in links])

            total = len(all_tasks)
            self._log(f"\nTotal issues found: {total}")

            # -- Download each issue ----------------------------------------
            done = 0
            for issue_url, dest_dir, prefix in all_tasks:
                if self._stop:
                    self._log("Stopped by user.")
                    break

                if issue_url in progress["completed"]:
                    self._log(f"[skip] {issue_url}")
                    done += 1
                    self.signals.progress.emit(done, total)
                    continue

                self._log(f"[{done+1}/{total}] {issue_url}")
                ok, result = downloader.download_issue(issue_url, dest_dir=dest_dir, hint_prefix=prefix)
                if ok:
                    progress["completed"].append(issue_url)
                    save_progress(progress)
                elif "read-only" in result or "No PDF download available" in result:
                    # Old digitised-only issues — mark completed so they are never retried
                    self._log(f"  [no pdf] {result}")
                    progress["completed"].append(issue_url)
                    save_progress(progress)
                else:
                    self._log(f"  FAILED: {result}")
                    failed_urls = [
                        e["url"] if isinstance(e, dict) else e
                        for e in progress["failed"]
                    ]
                    if issue_url not in failed_urls:
                        progress["failed"].append({"url": issue_url, "reason": result})
                    save_progress(progress)

                done += 1
                self.signals.progress.emit(done, total)
                time.sleep(1 + random.uniform(0, 0.5))

            self._log(f"\nSession complete. {len(progress['completed'])} total downloaded.")

            # Save cookies at the end of a successful run
            if self.cookies_path:
                downloader.save_cookies(self.cookies_path)

        except Exception as e:
            logger.exception("Worker error")
            self.signals.error.emit(str(e))
        finally:
            if downloader:
                downloader.close()
            self.signals.finished.emit()


# ------------------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trains.com Magazine Downloader & Organizer")
        self.resize(920, 740)
        self.worker: DownloadWorker | None = None
        self._build_ui()

    # -- UI construction ------------------------------------------------------
    def _build_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        tabs.addTab(self._make_download_tab(), "Download")
        tabs.addTab(self._make_organize_tab(), "Organize")

    def _make_download_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # Magazine checkboxes
        mag_box = QGroupBox("Magazines to download")
        mag_grid = QGridLayout(mag_box)
        self.mag_checks: dict[str, QCheckBox] = {}
        for i, name in enumerate(MAGAZINES):
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.mag_checks[name] = cb
            mag_grid.addWidget(cb, i // 3, i % 3)
        layout.addWidget(mag_box)

        # Save location
        save_box = QGroupBox("Save location")
        save_row = QHBoxLayout(save_box)
        self.dir_edit = QLineEdit(
            str(Path.home() / "Downloads" / "TrainsMagazines")
        )
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_dir)
        save_row.addWidget(self.dir_edit)
        save_row.addWidget(browse_btn)
        layout.addWidget(save_box)

        # Cookie file
        cookie_box = QGroupBox("Authentication — session cookie file")
        cookie_row = QHBoxLayout(cookie_box)
        cookie_row.addWidget(QLabel("File:"))
        self.cookie_edit = QLineEdit(DEFAULT_COOKIES_FILE)
        cookie_browse = QPushButton("Browse…")
        cookie_browse.setFixedWidth(80)
        cookie_browse.clicked.connect(self._browse_cookies)
        cookie_row.addWidget(self.cookie_edit)
        cookie_row.addWidget(cookie_browse)
        cookie_hint = QLabel(
            "Tip: leave blank to log in manually each run, or select an existing .json or .pkl cookie file."
        )
        cookie_hint.setWordWrap(True)
        cookie_hint.setStyleSheet("color: gray; font-size: 10px;")
        cookie_col = QVBoxLayout()
        cookie_col.addLayout(cookie_row)
        cookie_col.addWidget(cookie_hint)
        cookie_box.setLayout(cookie_col)
        layout.addWidget(cookie_box)

        # Options
        opts_row = QHBoxLayout()
        self.headless_cb = QCheckBox("Headless (no browser window — requires valid cookies)")
        self.test_cb     = QCheckBox("Test mode (first 3 pages only)")
        self.sort_combo  = QComboBox()
        self.sort_combo.addItems(["Newest first", "Oldest first"])
        opts_row.addWidget(self.headless_cb)
        opts_row.addWidget(self.test_cb)
        opts_row.addWidget(QLabel("Sort:"))
        opts_row.addWidget(self.sort_combo)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        # Action buttons
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶  Start Download")
        self.start_btn.setFixedHeight(32)
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setFixedHeight(32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        clear_btn = QPushButton("Clear progress cache")
        clear_btn.setFixedHeight(32)
        clear_btn.clicked.connect(self._clear_progress)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Progress bar
        self.dl_progress = QProgressBar()
        self.dl_progress.setVisible(False)
        layout.addWidget(self.dl_progress)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        # Log output
        self.dl_log = QTextEdit()
        self.dl_log.setReadOnly(True)
        self.dl_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.dl_log)

        return w

    def _make_organize_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        src_box = QGroupBox("Source folder (PDFs to organize)")
        src_row = QHBoxLayout(src_box)
        self.src_edit = QLineEdit()
        src_browse = QPushButton("Browse…")
        src_browse.setFixedWidth(80)
        src_browse.clicked.connect(lambda: self._pick_dir(self.src_edit))
        src_row.addWidget(self.src_edit)
        src_row.addWidget(src_browse)
        layout.addWidget(src_box)

        dst_box = QGroupBox("Destination folder (organized output)")
        dst_row = QHBoxLayout(dst_box)
        self.dst_edit = QLineEdit()
        dst_browse = QPushButton("Browse…")
        dst_browse.setFixedWidth(80)
        dst_browse.clicked.connect(lambda: self._pick_dir(self.dst_edit))
        dst_row.addWidget(self.dst_edit)
        dst_row.addWidget(dst_browse)
        layout.addWidget(dst_box)

        prefix_row = QHBoxLayout()
        prefix_row.addWidget(QLabel("Magazine prefix override:"))
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItem("Auto-detect")
        for info in MAGAZINES.values():
            self.prefix_combo.addItem(info["prefix"])
        prefix_row.addWidget(self.prefix_combo)
        prefix_row.addStretch()
        layout.addLayout(prefix_row)

        run_btn = QPushButton("▶  Organize PDFs")
        run_btn.setFixedHeight(32)
        run_btn.clicked.connect(self._run_organize)
        layout.addWidget(run_btn)

        self.org_log = QTextEdit()
        self.org_log.setReadOnly(True)
        self.org_log.setFont(QFont("Consolas", 9))
        layout.addWidget(self.org_log)

        return w

    # -- Slots ----------------------------------------------------------------
    def _pick_dir(self, target: QLineEdit):
        d = QFileDialog.getExistingDirectory(self, "Select folder")
        if d:
            target.setText(d)

    def _browse_dir(self):
        self._pick_dir(self.dir_edit)

    def _browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cookie file", "",
            "Cookie files (*.json *.pkl *.pickle);;All files (*)"
        )
        if path:
            self.cookie_edit.setText(path)

    def _clear_progress(self):
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            self._dl_log("Progress cache cleared.")
        else:
            self._dl_log("No progress cache file found.")

    def _dl_log(self, msg: str):
        self.dl_log.append(msg)

    def _start_download(self):
        magazines = [n for n, cb in self.mag_checks.items() if cb.isChecked()]
        if not magazines:
            QMessageBox.warning(self, "Nothing selected", "Select at least one magazine.")
            return

        base_dir = self.dir_edit.text().strip()
        if not base_dir:
            QMessageBox.warning(self, "No folder", "Please choose a save location.")
            return

        cookies  = self.cookie_edit.text().strip() or None
        headless = self.headless_cb.isChecked()
        test     = self.test_cb.isChecked()
        newest   = self.sort_combo.currentText() == "Newest first"

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.dl_progress.setVisible(True)
        self.dl_progress.setValue(0)
        self.status_label.setText("")

        self.worker = DownloadWorker(magazines, base_dir, headless, test, cookies, newest)
        self.worker.signals.log.connect(self._dl_log)
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.status_msg.connect(self.status_label.setText)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_download(self):
        if self.worker:
            self.worker.stop()
            self._dl_log("Stop requested — waiting for current issue to finish…")
        self.stop_btn.setEnabled(False)

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.dl_progress.setMaximum(total)
            self.dl_progress.setValue(current)
            self.status_label.setText(f"{current} / {total} issues")

    def _on_error(self, msg: str):
        self._dl_log(f"ERROR: {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._dl_log("--- Done ---")
        self.status_label.setText("Done.")

    def _run_organize(self):
        src = self.src_edit.text().strip()
        dst = self.dst_edit.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "Missing folders", "Select both source and destination folders.")
            return
        pfx_text = self.prefix_combo.currentText()
        hint = None if pfx_text == "Auto-detect" else pfx_text

        self.org_log.clear()
        self.org_log.append(f"Organizing PDFs from: {src}")
        self.org_log.append(f"                  to: {dst}\n")
        moved, skipped, report = organize_pdfs(src, dst, hint_prefix=hint, log_fn=self.org_log.append)
        self.org_log.append(f"\n-- {moved} moved, {skipped} skipped --")
        for line in report:
            self.org_log.append(line)


# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------
def main():
    import traceback
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        win = MainWindow()
        win.show()
        sys.exit(app.exec_())
    except Exception:
        err = traceback.format_exc()
        # Write crash to file so it isn't lost when the window closes
        crash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
        with open(crash_path, "w") as f:
            f.write(err)
        print(err, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
