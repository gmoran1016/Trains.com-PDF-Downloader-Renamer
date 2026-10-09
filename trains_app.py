#!/usr/bin/env python3
"""
Trains.com Magazine Downloader & Organizer
All-in-one tool: download all trains.com magazines and organize/rename PDFs.
Requires: Python 3.10+, selenium>=4.6, PyQt5, requests, beautifulsoup4
"""

import sys
import os
import io
import json
import re
import shutil
import time
import logging
import random
import datetime
import threading
from calendar import month_name, month_abbr as _month_abbr
from pathlib import Path
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

try:
    import pypdf
    from pypdf.generic import DecodedStreamObject, NameObject
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QComboBox, QMessageBox, QMenu, QSystemTrayIcon,
    QButtonGroup, QFrame, QScrollArea, QSplitter,
    QStackedWidget, QToolButton,
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread, Qt

# ------------------------------------------------------------------------------
# Base directory — next to the .exe when frozen, next to the script otherwise
# ------------------------------------------------------------------------------
_DATA_DIR_OVERRIDE = os.environ.get("TRAINS_DATA_DIR")
if _DATA_DIR_OVERRIDE:
    _BASE_DIR = os.path.abspath(os.path.expanduser(_DATA_DIR_OVERRIDE))
    os.makedirs(_BASE_DIR, exist_ok=True)
elif getattr(sys, "frozen", False):
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
MAGAZINE_SCHEDULE = {
    "Model Railroader": "Monthly",
    "Trains Magazine": "Monthly",
    "Classic Toy Trains": "Monthly",
    "Classic Trains": "Quarterly",
    "Garden Railways": "Seasonal / archived",
}

# Path segments that are not individual issue pages
_NON_ISSUE_SLUGS = frozenset({
    "current-issue", "special-issues", "staff", "annual-index",
    "contributor-guidelines", "archive-access", "subscription-plans",
    "subscriptions", "page", "index",
})

DEFAULT_COOKIES_FILE = os.path.join(_BASE_DIR, "session_cookies.json")
PROGRESS_FILE       = os.path.join(_BASE_DIR, "download_progress.json")
SPECIAL_ISSUES_FILE = os.path.join(_BASE_DIR, "special_issues.json")
SETTINGS_FILE       = os.path.join(_BASE_DIR, "settings.json")
TRACK_PLAN_DATABASE_URL = (
    "https://www.trains.com/mrr/how-to/track-plan-database/"
)
DOWNLOAD_TIMEOUT = 120   # seconds to wait for a PDF download
LOGIN_TIMEOUT = 300      # seconds to wait for manual login (5 min)
TRACK_PLAN_REQUEST_DELAY = 0.35
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)

OUTCOME_IDLE = "idle"
OUTCOME_RUNNING = "running"
OUTCOME_SUCCESS = "success"
OUTCOME_FAILED = "failed"
OUTCOME_CANCELLED = "cancelled"
OUTCOME_NO_RESULTS = "no-results"


class ArchiveScanError(RuntimeError):
    """Raised when an archive page cannot be trusted as a usable archive."""

    def __init__(self, message: str, partial_links: list[str] | None = None):
        super().__init__(message)
        self.partial_links = list(partial_links or [])


class ArchiveRedirectError(ArchiveScanError):
    """Raised when an archive request lands on an unrelated URL."""


class TrackPlanAccessError(ArchiveScanError):
    """Raised when a track plan page redirects to an access or login screen."""


class _AnchorParser(HTMLParser):
    """Extract visible anchor text and hrefs without adding an HTML dependency."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def _extract_anchor_links(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(html or "")
    parser.close()
    return [
        (urljoin(base_url, href.strip()), text)
        for href, text in parser.links
        if href and href.strip()
    ]


def _extract_track_plan_listing(
    html: str,
    base_url: str = TRACK_PLAN_DATABASE_URL,
) -> tuple[list[str], int]:
    """Return unique track plan pages and the largest pagination number."""
    base_path = urlsplit(TRACK_PLAN_DATABASE_URL).path.rstrip("/") + "/"
    plan_urls: list[str] = []
    max_page = 1

    for href, _text in _extract_anchor_links(html, base_url):
        parts = urlsplit(href)
        if parts.netloc.lower() not in ("www.trains.com", "trains.com"):
            continue
        if not parts.path.startswith(base_path):
            continue

        suffix = parts.path[len(base_path):].strip("/")
        if not suffix:
            continue
        segments = suffix.split("/")
        if len(segments) == 2 and segments[0].lower() == "page" \
                and segments[1].isdigit():
            max_page = max(max_page, int(segments[1]))
        elif len(segments) == 1 and segments[0].lower() not in {
            "page", "tag", "category", "author",
        }:
            canonical = _canonical_url(href)
            if canonical not in plan_urls:
                plan_urls.append(canonical)

    return plan_urls, max_page


def _extract_track_plan_pdf_url(
    html: str,
    plan_url: str,
) -> str | None:
    """Find the PDF link belonging to an individual track plan page."""
    pdf_links: list[tuple[str, str]] = []
    for href, text in _extract_anchor_links(html, plan_url):
        parts = urlsplit(href)
        if parts.scheme.lower() != "https" \
                or parts.netloc.lower() not in ("www.trains.com", "trains.com") \
                or not parts.path.lower().endswith(".pdf"):
            continue
        candidate = (href, text.strip().lower())
        if candidate not in pdf_links:
            pdf_links.append(candidate)

    track_plan_links = [
        href for href, text in pdf_links
        if "track plan" in text and "pdf" in text
    ]
    if len(track_plan_links) == 1:
        return track_plan_links[0]
    if not track_plan_links and len(pdf_links) == 1:
        return pdf_links[0][0]
    return None


def _track_plan_pdf_filename(pdf_url: str) -> str:
    from urllib.parse import unquote

    filename = os.path.basename(unquote(urlsplit(pdf_url).path))
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).strip(" .")
    if not filename:
        filename = "track-plan.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return filename


def _download_track_plan_pdf(
    session,
    pdf_url: str,
    destination_dir: str,
    stop_requested,
) -> tuple[bool, str]:
    """Save a plan PDF under its original filename without magazine renaming."""
    import tempfile
    response = None
    temporary_path = None
    try:
        response = session.get(
            pdf_url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
        )
        response.raise_for_status()
        filename = _track_plan_pdf_filename(pdf_url)

        fd, temporary_path = tempfile.mkstemp(
            prefix=".track-plan-",
            suffix=".download",
            dir=destination_dir,
        )
        with os.fdopen(fd, "wb") as output:
            for chunk in response.iter_content(chunk_size=65536):
                if stop_requested():
                    return False, "cancelled"
                if chunk:
                    output.write(chunk)

        if not _verify_pdf(temporary_path):
            return False, f"Downloaded file is not a valid PDF: {filename}"

        destination = _unique_path(os.path.join(destination_dir, filename))
        os.replace(temporary_path, destination)
        temporary_path = None
        return True, destination
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in (401, 403):
            return False, f"Access denied (HTTP {status_code}) while downloading PDF"
        return False, f"PDF download failed: {exc}"
    finally:
        if response is not None:
            response.close()
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass


def _canonical_url(url: str) -> str:
    """Normalize a Trains.com URL without retaining filters or fragments."""
    parts = urlsplit((url or "").strip())
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/") + "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def cancel_pending_futures(pending: dict) -> int:
    """Cancel futures that have not started and return the number cancelled."""
    cancelled = 0
    for future in list(pending):
        try:
            if future.cancel():
                cancelled += 1
        except Exception:
            logger.debug("Unable to cancel pending future", exc_info=True)
    return cancelled

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


def load_cookies(path: str) -> list:
    """Load cookies from a JSON file. Pickle format is not supported (insecure deserialization)."""
    if path.endswith(".pkl") or path.endswith(".pickle"):
        logger.warning(
            f"Pickle cookie files are not supported for security reasons. "
            f"Export your cookies as JSON instead: {path}"
        )
        return []
    return load_cookies_json(path)


# ------------------------------------------------------------------------------
# Progress tracking
# ------------------------------------------------------------------------------

def load_progress() -> dict:
    empty = {"completed": [], "completed_scoped": [], "failed": []}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return empty
            # Ensure required keys and tolerate legacy progress files.
            for key in empty:
                if not isinstance(data.get(key), list):
                    data[key] = []
            return data
        except Exception:
            pass
    return empty


def progress_key(issue_url: str, destination_dir: str, flat: bool) -> str:
    """Return a stable completion key scoped to the output location."""
    destination = os.path.normcase(os.path.abspath(os.path.normpath(destination_dir)))
    return json.dumps(
        {
            "destination": destination,
            "flat": bool(flat),
            "url": _canonical_url(issue_url),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _is_progress_completed(progress: dict, issue_url: str,
                           destination_dir: str, flat: bool) -> bool:
    key = progress_key(issue_url, destination_dir, flat)
    return key in set(progress.get("completed_scoped", []))


def _record_progress_completion(progress: dict, issue_url: str,
                                scoped_key: str | None = None) -> None:
    progress.setdefault("completed", [])
    progress.setdefault("completed_scoped", [])
    if issue_url not in progress["completed"]:
        progress["completed"].append(issue_url)
    if scoped_key and scoped_key not in progress["completed_scoped"]:
        progress["completed_scoped"].append(scoped_key)


def save_progress(progress: dict) -> None:
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save progress: {e}")


def load_special_issues() -> set:
    """Return the set of special-issue URLs already downloaded (survives cache clears)."""
    if os.path.exists(SPECIAL_ISSUES_FILE):
        try:
            with open(SPECIAL_ISSUES_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_special_issues(urls: set) -> None:
    try:
        with open(SPECIAL_ISSUES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(urls), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save special issues: {e}")


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


def _verify_pdf(path: str) -> bool:
    """Return True if the PDF at path appears valid (size + parseable)."""
    try:
        if os.path.getsize(path) < 512:
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


def rename_and_move(src_path: str, dest_dir: str, hint_prefix: str | None,
                    flat: bool, log_fn) -> tuple[bool, str]:
    """
    Rename src_path per naming convention, move into dest_dir (or dest_dir/YYYY/),
    stamp metadata, verify integrity.
    Returns (True, dest_path) on success or (False, reason) on failure.
    """
    if not _verify_pdf(src_path):
        log_fn(f"  [corrupt] {os.path.basename(src_path)} — left in place")
        return False, "corrupt"

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
        log_fn(f"  [corrupt] {os.path.basename(dest)} — restoring source")
        try:
            shutil.move(dest, src_path)
        except OSError:
            pass
        return False, "corrupt"

    log_fn(f"  → {dest}")
    return True, dest


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
        "User-Agent": HTTP_USER_AGENT,
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


def detect_download_mode(driver) -> tuple[str, str | None]:
    """
    Inspect the currently-loaded page and return the download mode.
    Returns ('mode1', pdf_url), ('mode2', None), or ('mode3', detail).
    Mode 1 = direct <a> download link.
    Mode 2 = real3d flipbook reader.
    Mode 3 = read-only, no download.
    For mode 3, detail is ``"gated"`` when the page is an authenticated
    membership surface that the current account cannot access.
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

    if _is_membership_gated(driver):
        return "mode3", "gated"

    if _has_flipbook_trigger(driver):
        return "mode2", None

    return "mode3", None


def _has_flipbook_trigger(driver) -> bool:
    """Return whether the issue page exposes a reader/viewer entry point."""
    from selenium.webdriver.common.by import By

    # trains.com uses the same cover markup for open readers and locked
    # membership cards.  A cover by itself is not a reader trigger: some
    # special-issue pages expose only artwork and print instructions.
    if _is_membership_gated(driver):
        return False
    if driver.find_elements(By.CSS_SELECTOR, ".real3dflipbook"):
        return True
    for label in ("Read Magazine", "PDF Edition"):
        if driver.find_elements(
            By.XPATH, f"//button[contains(normalize-space(.), '{label}')]"
        ):
            return True
    return False


def _is_membership_gated(driver) -> bool:
    """Return whether the current issue surface is locked behind membership."""
    from selenium.webdriver.common.by import By

    for selector in (
        "div.ci-media.ci-media--gated",
        ".ci-media .ci-btn--locked",
        ".ci-media .ci-paywall",
    ):
        if driver.find_elements(By.CSS_SELECTOR, selector):
            return True
    return False


def _gated_issue_message(issue_url: str) -> str:
    return (
        "PDF access requires an eligible trains.com Unlimited Membership: "
        f"{issue_url}"
    )


def _handle_result(ok: bool, result: str, issue_url: str,
                   progress: dict, completed_set: set, log_fn,
                   progress_key_value: str | None = None) -> None:
    """Update progress tracking after a download attempt."""
    progress.setdefault("completed", [])
    progress.setdefault("completed_scoped", [])
    progress.setdefault("failed", [])
    if ok:
        completed_set.add(issue_url)
        _record_progress_completion(progress, issue_url, progress_key_value)
        save_progress(progress)
    elif "read-only" in result or "No PDF download available" in result:
        log_fn(f"  [no pdf] {result}")
        completed_set.add(issue_url)
        _record_progress_completion(progress, issue_url, progress_key_value)
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


def issue_already_on_disk(issue_url: str, dest_dir: str, prefix: str, flat: bool) -> bool:
    """
    Return True if the PDF for this issue URL already exists in dest_dir.
    Parses the URL slug to derive the expected filename without hitting the network.
    Checks both the canonical name (stem.pdf) and duplicate variants (stem-1.pdf,
    stem-2.pdf, …) created by _unique_path.
    Returns False if the slug can't be parsed (caller will attempt the download).
    """
    slug = issue_url.rstrip("/").split("/")[-1]
    parsed = parse_pdf_filename(slug + ".pdf", hint_prefix=prefix)
    if not parsed:
        return False
    new_stem, year, _ = parsed
    target_dir = Path(dest_dir) if flat else Path(dest_dir) / year
    # Check canonical name first (fast path), then any -N duplicate variants
    return (target_dir / (new_stem + ".pdf")).exists() or any(
        target_dir.glob(f"{new_stem}-[0-9]*.pdf")
    )


# ------------------------------------------------------------------------------
# File renamer / organizer
# ------------------------------------------------------------------------------
_abbr_list = [a for a in _month_abbr if a]
MONTH_FROM_ABBR = {a.upper(): month_name[i + 1] for i, a in enumerate(_abbr_list)}
MONTHNUM_FROM_ABBR = {a.upper(): f"{i + 1:02d}" for i, a in enumerate(_abbr_list)}
MONTH_NUM_FROM_NAME = {month_name[i]: i for i in range(1, 13)}
APP_VERSION = "1.10.0"
BROWSER_COMMAND_TIMEOUT = 45
BROWSER_COMMAND_ATTEMPTS = 2
ALL_MONTHS = list(month_name)[1:]
# Full magazine names keyed by the file prefix used throughout this tool
PREFIX_TO_TITLE: dict[str, str] = {
    "MRR": "Model Railroader",
    "TRN": "Trains",
    "CTT": "Classic Toy Trains",
    "CTR": "Classic Trains",
    "GRW": "Garden Railways",
}
# Expected issue months for non-monthly magazines.
# Prefixes not listed here are assumed monthly (ALL_MONTHS).
PREFIX_ISSUE_MONTHS: dict[str, list[str]] = {
    "CTR": ["March", "June", "September", "December"],  # quarterly
}
SEASONAL_PREFIXES = frozenset({"GRW"})

# Non-standard abbreviations not covered by the 3-letter calendar set
EXTRA_MONTH_ABBR: dict[str, tuple[str, int]] = {
    "SEPT": ("September", 9),
}
# Quarter number → (representative month name, month number)
QUARTER_TO_MONTH: dict[int, tuple[str, int]] = {
    1: ("January",  1),
    2: ("April",    4),
    3: ("July",     7),
    4: ("October", 10),
}
# Season name → (representative month name, month number)
# Used to parse URL slugs like "classic-trains-summer-2005"
SEASON_TO_MONTH: dict[str, tuple[str, int]] = {
    "SPRING": ("March",     3),
    "SUMMER": ("June",      6),
    "FALL":   ("September", 9),
    "AUTUMN": ("September", 9),
    "WINTER": ("December", 12),
}


def _guess_prefix(filename: str) -> str | None:
    low = filename.lower()
    if re.search(r"\btrn\b|trains\s+magazine", low):
        return "TRN"
    if re.search(r"\bctt\b|classic\s+toy", low):
        return "CTT"
    if re.search(r"\bctr\b|classic\s+trains", low):
        return "CTR"
    if re.search(r"\bgrw\b|garden\s+rail", low):
        return "GRW"
    if re.search(r"\bmrr\b|model\s+railroader", low):
        return "MRR"
    return None


def parse_pdf_filename(filepath: str, hint_prefix: str | None = None):
    """
    Parse a PDF filename and return (new_stem, year_str, month_name) or None.
    Tries multiple date-in-filename patterns.
    """
    name, ext = os.path.splitext(os.path.basename(filepath))
    if ext.lower() != ".pdf":
        return None

    prefix = hint_prefix or _guess_prefix(name)
    if not prefix:
        return None

    # Archive slugs use full month names, e.g. "october-2026".
    full_month_pattern = "|".join(re.escape(month) for month in ALL_MONTHS)
    m = re.search(
        rf"({full_month_pattern})[_\-](\d{{4}})(?:\D|$)",
        name,
        re.IGNORECASE,
    )
    if m:
        mname = m.group(1).capitalize()
        year = int(m.group(2))
        if 1800 <= year <= 2200:
            mnum = MONTH_NUM_FROM_NAME[mname]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Also accept the less common year-first spelling, e.g. "2026-october".
    m = re.search(
        rf"(\d{{4}})[_\-]({full_month_pattern})(?:\D|$)",
        name,
        re.IGNORECASE,
    )
    if m:
        year = int(m.group(1))
        mname = m.group(2).capitalize()
        if 1800 <= year <= 2200:
            mnum = MONTH_NUM_FROM_NAME[mname]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 0: MM-FullMonthName-YYYY (already-formatted files, e.g. MRR-01-January-1934)
    m = re.search(r"(\d{1,2})[_\-]([A-Za-z]+)[_\-](\d{4})(?:\D|$)", name)
    if m:
        mnum_raw, mname_raw, year_str = int(m.group(1)), m.group(2).capitalize(), m.group(3)
        if mname_raw in MONTH_NUM_FROM_NAME:
            mnum = MONTH_NUM_FROM_NAME[mname_raw]
            year = int(year_str)
            if 1800 <= year <= 2200:
                mname = month_name[mnum]
                return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 1: YYYY_MM or YYYY-MM
    m = re.search(r"(\d{4})[_\-](\d{1,2})(?:\D|$)", name)
    if m:
        year, mnum = int(m.group(1)), int(m.group(2))
        if 1800 <= year <= 2200 and 1 <= mnum <= 12:
            mname = month_name[mnum]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 2: YYYYMM (6 consecutive digits)
    m = re.search(r"(\d{4})(\d{2})(?:\D|$)", name)
    if m:
        year, mnum = int(m.group(1)), int(m.group(2))
        if 1800 <= year <= 2200 and 1 <= mnum <= 12:
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
            if 1800 <= year <= 2200:
                mname = MONTH_FROM_ABBR[abbr]
                mnum = MONTHNUM_FROM_ABBR[abbr]
                return f"{prefix}-{mnum}-{mname}-{year}", str(year), mname

    # Pattern 3b: Non-standard 4-letter abbreviations (e.g. SEPT17)
    m = re.search(r"([A-Za-z]{4})[_\-]?(\d{2,4})(?:\D|$)", name)
    if m:
        abbr = m.group(1).upper()
        if abbr in EXTRA_MONTH_ABBR:
            mname, mnum = EXTRA_MONTH_ABBR[abbr]
            year = int(m.group(2))
            if year < 100:
                year += 2000
            if 1800 <= year <= 2200:
                return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 3c: Quarter notation (e.g. 1988Q2, 1989Q1)
    m = re.search(r"(\d{4})[_\-]?[Qq]([1-4])(?:\D|$)", name)
    if m:
        year = int(m.group(1))
        quarter = int(m.group(2))
        if 1800 <= year <= 2200:
            mname, mnum = QUARTER_TO_MONTH[quarter]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 3d: Season name before year (e.g. summer-2005, spring2003)
    m = re.search(r"(spring|summer|fall|autumn|winter)[_\-]?(\d{4})(?:\D|$)", name, re.IGNORECASE)
    if m:
        season_key = m.group(1).upper()
        year = int(m.group(2))
        if 1800 <= year <= 2200 and season_key in SEASON_TO_MONTH:
            mname, mnum = SEASON_TO_MONTH[season_key]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 3d-alt: Year before season (e.g. 2023-fall, 2005summer)
    m = re.search(r"(\d{4})[_\-]?(spring|summer|fall|autumn|winter)(?:\W|$)", name, re.IGNORECASE)
    if m:
        year = int(m.group(1))
        season_key = m.group(2).upper()
        if 1800 <= year <= 2200 and season_key in SEASON_TO_MONTH:
            mname, mnum = SEASON_TO_MONTH[season_key]
            return f"{prefix}-{mnum:02d}-{mname}-{year}", str(year), mname

    # Pattern 3e: Year only — no month information (e.g. CTR-1999.pdf)
    m = re.search(r"(?:^|\D)(\d{4})(?:\D|$)", name)
    if m:
        year = int(m.group(1))
        if 1800 <= year <= 2200:
            return f"{prefix}-{year}", str(year), None

    # Pattern 4: Extract date from PDF first-page text (fallback for unrecognized filenames)
    result = _extract_date_from_pdf(filepath)
    if result:
        mnum, mname, year_str = result
        return f"{prefix}-{mnum:02d}-{mname}-{year_str}", year_str, mname

    return None


def _extract_date_from_pdf(filepath: str):
    """
    Read the first page of a PDF and search for a month+year date.
    Returns (mnum, mname, year_str) or None.
    Falls back silently if pypdf is not installed or the PDF has no text layer.
    """
    if not _PYPDF_AVAILABLE:
        return None
    try:
        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            if not reader.pages:
                return None
            text = reader.pages[0].extract_text() or ""
    except Exception:
        return None

    # Search for "FullMonthName YYYY" (month name before year)
    for mnum in range(1, 13):
        mname = month_name[mnum]
        m = re.search(rf"\b{mname}\b[\s,]+(\d{{4}})\b", text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1800 <= year <= 2200:
                return mnum, mname, str(year)

    # Search for "YYYY FullMonthName" (year before month name)
    for mnum in range(1, 13):
        mname = month_name[mnum]
        m = re.search(rf"\b(\d{{4}})\b[\s,]+{mname}\b", text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1800 <= year <= 2200:
                return mnum, mname, str(year)

    # Search for 3-letter abbreviation + year as a last resort
    for abbr, mname in MONTH_FROM_ABBR.items():
        mnum = int(MONTHNUM_FROM_ABBR[abbr])
        m = re.search(rf"\b{abbr}\.?\s+(\d{{4}})\b", text, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1800 <= year <= 2200:
                return mnum, mname, str(year)

    return None


def _xml_escape(text: str) -> str:
    """Escape the five predefined XML entities."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _build_xmp(title: str, mname: str | None, year: str, author: str = "") -> bytes:
    """Build a minimal XMP metadata packet for a magazine issue."""
    mnum = MONTH_NUM_FROM_NAME.get(mname, 1) if mname else 1
    date_str = f"{year}-{mnum:02d}-01"
    safe_title  = _xml_escape(title)
    safe_author = _xml_escape(author)
    creator_xml = (
        f'      <dc:creator><rdf:Seq><rdf:li>{safe_author}</rdf:li></rdf:Seq></dc:creator>\n'
        if author else ""
    )
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        '        xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
        '        xmlns:xmp="http://ns.adobe.com/xap/1.0/">\n'
        '      <dc:title><rdf:Alt>'
        f'<rdf:li xml:lang="x-default">{safe_title}</rdf:li>'
        '</rdf:Alt></dc:title>\n'
        f'{creator_xml}'
        f'      <xmp:CreateDate>{date_str}T00:00:00</xmp:CreateDate>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>\n'
        '<?xpacket end="w"?>'
    ).encode("utf-8")


def _stamp_pdf_metadata(path: str, mname: str | None, year: str, warn_fn=None) -> bool:
    """
    Write title, month/year into both the PDF info dictionary and XMP metadata.
    Returns True if metadata was written, False if already present or on any error.
    warn_fn, if provided, is called with a message string on failure.
    """
    if not _PYPDF_AVAILABLE:
        return False
    tmp = path + ".meta_tmp"
    try:
        file_size = os.path.getsize(path)
        if file_size > 50 * 1024 * 1024:  # warn for PDFs over 50 MB
            logger.warning(
                f"Large PDF ({file_size // (1024 * 1024)} MB): loading "
                f"{os.path.basename(path)} into memory for metadata update"
            )
        stem = os.path.splitext(os.path.basename(path))[0]
        prefix = stem.split("-")[0].upper()
        mag_name = PREFIX_TO_TITLE.get(prefix, prefix)
        if mname:
            mnum = MONTH_NUM_FROM_NAME.get(mname, 1)
            title = f"{mag_name} - {mname}, {year}"
            metadata = {
                "/Title":        title,
                "/Author":       mag_name,
                "/Subject":      f"{mname} {year}",
                "/Keywords":     f"{mname}, {year}",
                "/CreationDate": f"D:{year}{mnum:02d}01000000",
            }
        else:
            title = f"{mag_name} - {year}"
            metadata = {
                "/Title":        title,
                "/Author":       mag_name,
                "/Subject":      year,
                "/Keywords":     year,
                "/CreationDate": f"D:{year}0101000000",
            }
        # Read entire file into memory so pypdf never needs the file handle later
        with open(path, "rb") as f:
            data = f.read()
        reader = pypdf.PdfReader(io.BytesIO(data))
        existing = reader.metadata or {}
        if existing.get("/Title") == title and existing.get("/Author") == mag_name:
            return False  # already stamped with correct title and author — skip rewrite
        # clone_from (pypdf 3.1+) properly owns all objects so add_metadata
        # reliably overrides the existing /Info dict.  Fall back to page-by-page
        # copy on older builds; that also starts with a clean info object.
        try:
            writer = pypdf.PdfWriter(clone_from=reader)
        except TypeError:
            writer = pypdf.PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
        # Write PDF info dictionary (traditional metadata)
        writer.add_metadata(metadata)
        # Write XMP metadata (modern standard, read by Grimoire and similar apps)
        xmp_stream = DecodedStreamObject()
        xmp_stream.set_data(_build_xmp(title, mname, year, author=mag_name))
        xmp_stream[NameObject("/Type")] = NameObject("/Metadata")
        xmp_stream[NameObject("/Subtype")] = NameObject("/XML")
        writer._root_object[NameObject("/Metadata")] = writer._add_object(xmp_stream)
        with open(tmp, "wb") as f:
            writer.write(f)
        os.replace(tmp, path)
        return True
    except Exception as e:
        msg = f"  Warning: metadata update failed for {os.path.basename(path)}: {e}"
        logger.warning(msg)
        if warn_fn:
            warn_fn(msg)
        return False
    finally:
        # Always remove the temp file if it was left behind by any error path
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError as _oe:
                logger.warning(f"Could not remove temp metadata file {tmp}: {_oe}")


def _unique_path(base_path: str) -> str:
    if not os.path.exists(base_path):
        return base_path
    root, ext = os.path.splitext(base_path)
    i = 1
    while os.path.exists(f"{root}-{i}{ext}"):
        i += 1
    return f"{root}-{i}{ext}"


@dataclass
class OrganizeSummary:
    """Structured outcome from one organizer run."""

    moved: int = 0
    already_correct: int = 0
    unrecognized: int = 0
    corrupt: int = 0
    conflicts: int = 0
    metadata_stamped: int = 0
    report: list[str] = field(default_factory=list)
    missing_by_prefix_year: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    scan_complete: bool = True


def _missing_download_selection(summary: OrganizeSummary) -> tuple[str | None, dict[str, list[str]]]:
    """Return a safe missing-download target only for one observed publication."""
    if not summary.scan_complete:
        return None, {}
    if len(summary.missing_by_prefix_year) != 1:
        return None, {}
    prefix, by_year = next(iter(summary.missing_by_prefix_year.items()))
    missing = {year: months for year, months in by_year.items() if months}
    if not missing:
        return None, {}
    return prefix, missing


def _detect_issue_frequency(issues_by_year: dict) -> list | None:
    """
    Infer the expected issue months from the collected files.

    Strategy: find years that look "complete" (have the most issues of any year),
    then check whether those years all share the same set of months.  If yes, that
    consistent set is returned as the expected schedule.  Falls back to None so the
    caller can try a hardcoded table or ALL_MONTHS.

    A threshold of 9 is used so monthly magazines (12 issues) and near-monthly
    magazines (10-11) are never mis-classified as sub-monthly.
    """
    # Only consider years with at least 2 dated issues (ignore year-only entries)
    year_data = [months for months in issues_by_year.values() if len(months) >= 2]
    if len(year_data) < 2:
        return None

    max_count = max(len(m) for m in year_data)
    if max_count >= 9:          # monthly or near-monthly — don't override
        return None

    full_years = [m for m in year_data if len(m) == max_count]
    if len(full_years) < 2:     # need at least two "complete" years to be confident
        return None

    # All complete years must share exactly the same months
    common = set.intersection(*[set(m) for m in full_years])
    if len(common) != max_count:
        return None

    return sorted(common, key=lambda m: MONTH_NUM_FROM_NAME[m])


def organize_pdfs(
    source_dir: str,
    dest_dir: str,
    hint_prefix: str | None = None,
    log_fn=None,
    progress_fn=None,
    cancel_event: threading.Event | None = None,
):
    """
    Move and rename PDFs from source_dir into dest_dir/YYYY/ subfolders.
    Returns an OrganizeSummary describing moves, integrity checks, conflicts,
    metadata updates, and per-publication completeness.
    progress_fn, if provided, is called with (current, total) after each file is processed.
    """
    def _log(msg):
        logger.info(msg)
        if log_fn:
            log_fn(msg)

    summary = OrganizeSummary()

    def _walk_error(error: OSError) -> None:
        summary.scan_complete = False
        _log(f"  [error] Could not scan a source folder: {error}")

    # Pre-collect all PDF paths so we can report total progress. os.walk
    # reports inaccessible directories through onerror; keep files already
    # discovered, but mark the coverage incomplete for the final outcome.
    all_pdfs = []
    for root, _, files in os.walk(source_dir, onerror=_walk_error):
        if cancel_event is not None and cancel_event.is_set():
            summary.scan_complete = False
            break
        for fname in files:
            if fname.lower().endswith(".pdf"):
                all_pdfs.append((root, fname))
    total_pdfs = len(all_pdfs)

    issues_by_prefix_year: dict[str, dict[str, set[str]]] = {}

    def _record_issue(prefix: str, year: str, mname: str | None) -> None:
        months = issues_by_prefix_year.setdefault(prefix, {}).setdefault(year, set())
        if mname:
            months.add(mname)

    def _emit_progress(file_idx: int) -> None:
        if progress_fn:
            progress_fn(file_idx + 1, total_pdfs)

    for file_idx, (root, fname) in enumerate(all_pdfs):
        if cancel_event is not None and cancel_event.is_set():
            summary.scan_complete = False
            _log("  Organizer stopped; keeping the partial summary.")
            break
        fpath = os.path.join(root, fname)
        try:
            parsed = parse_pdf_filename(fpath, hint_prefix)
            if not parsed:
                _log(f"  Skipping (unrecognized, no date found in filename or PDF content): {fname}")
                summary.unrecognized += 1
                continue
            new_stem, year, mname = parsed
            prefix = new_stem.split("-", 1)[0].upper()

            if not _verify_pdf(fpath):
                _log(f"  [corrupt] {fname} — left in place")
                summary.corrupt += 1
                continue

            _record_issue(prefix, year, mname)

            year_dir = os.path.join(dest_dir, year)
            expected_path = os.path.join(year_dir, new_stem + ".pdf")
            fname_stem = os.path.splitext(fname)[0]
            actual_dir = os.path.normcase(os.path.abspath(root))
            expected_dir = os.path.normcase(os.path.abspath(year_dir))
            is_duplicate_variant = (
                actual_dir == expected_dir
                and re.fullmatch(
                    re.escape(new_stem) + r"-\d+", fname_stem, re.IGNORECASE
                )
            )
            if (
                is_duplicate_variant
                or os.path.normcase(os.path.abspath(fpath))
                == os.path.normcase(os.path.abspath(expected_path))
            ):
                if is_duplicate_variant and os.path.exists(expected_path):
                    summary.conflicts += 1
                    _log(
                        f"  [conflict] {fname} — duplicate preserved alongside "
                        f"{os.path.basename(expected_path)}"
                    )
                if _stamp_pdf_metadata(fpath, mname, year, warn_fn=_log):
                    _log(f"  Metadata updated: {fname}")
                    summary.metadata_stamped += 1
                summary.already_correct += 1
                continue
            os.makedirs(year_dir, exist_ok=True)
            has_conflict = os.path.exists(expected_path)
            dest_path = _unique_path(expected_path)
            if has_conflict:
                summary.conflicts += 1
                _log(
                    f"  [conflict] {fname} — canonical issue exists; preserving as "
                    f"{os.path.basename(dest_path)}"
                )
            shutil.move(fpath, dest_path)
            if _stamp_pdf_metadata(dest_path, mname, year, warn_fn=_log):
                summary.metadata_stamped += 1
            if not has_conflict:
                _log(f"  {fname}  →  {dest_path}")
            summary.moved += 1
        except Exception as error:
            summary.scan_complete = False
            _log(f"  [error] Could not process {fname}: {error}")
        finally:
            _emit_progress(file_idx)

    if cancel_event is not None and cancel_event.is_set():
        summary.scan_complete = False

    # Determine expected months independently for each observed publication.
    today = datetime.date.today()
    for prefix in sorted(issues_by_prefix_year):
        years = issues_by_prefix_year[prefix]
        expected_months = _detect_issue_frequency(years)
        if expected_months is None and prefix in PREFIX_ISSUE_MONTHS:
            expected_months = PREFIX_ISSUE_MONTHS[prefix]
        if expected_months is None and prefix in SEASONAL_PREFIXES:
            for year in sorted(years):
                summary.missing_by_prefix_year.setdefault(prefix, {})[year] = []
                summary.report.append(
                    f"{prefix} {year}: schedule unknown/seasonal; completeness not inferred"
                )
            continue
        if expected_months is None:
            expected_months = ALL_MONTHS
        for year in sorted(years):
            yr_int = int(year)
            missing = [
                m for m in expected_months
                if m not in years[year]
                and datetime.date(yr_int, MONTH_NUM_FROM_NAME[m], 1) <= today
            ]
            summary.missing_by_prefix_year.setdefault(prefix, {})[year] = missing
            state = "complete" if not missing else f"missing {missing}"
            summary.report.append(f"{prefix} {year}: {state}")
    return summary


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
                    if isinstance(e, ArchiveScanError):
                        raise
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
        self.download_dir = os.path.abspath(download_dir)
        os.makedirs(self.download_dir, exist_ok=True)
        self.log_fn = log_fn
        self.headless = headless
        self._session_cookies: list[dict] = []
        self._driver = None

        self._driver = self._create_driver()
        self._log("Browser started.")

    def _create_driver(self):
        """Create a configured Chrome session for the downloader."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

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
        if self.headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
            opts.add_argument("--disable-gpu")

        # Selenium 4.6+ selenium-manager auto-downloads the right chromedriver.
        # A fresh transport per command avoids stale keep-alive sockets being
        # reset while long trains.com pages are still loading.
        driver = webdriver.Chrome(options=opts, keep_alive=False)
        try:
            self._configure_browser_transport(driver)
            # ChromeDriver 154 on Windows can exhaust its stack while attaching
            # to a burst of embedded frames on Trains.com. We automate only the
            # top-level document; frames still render and accept manual input.
            # Configure this before navigation, including on session recovery.
            driver.execute_cdp_cmd("Target.setAutoAttach", {
                "autoAttach": False,
                "waitForDebuggerOnStart": False,
                "flatten": True,
            })
        except Exception:
            try:
                driver.quit()
            except Exception:
                pass
            raise
        return driver

    @staticmethod
    def _configure_browser_transport(driver) -> None:
        """Bound local WebDriver HTTP calls so a dead driver cannot stall a run."""
        command_executor = getattr(driver, "command_executor", None)
        client_config = getattr(command_executor, "_client_config", None)
        if client_config is not None:
            client_config.timeout = BROWSER_COMMAND_TIMEOUT
            return
        # Compatibility with older Selenium 4 releases that predate the
        # public ClientConfig path used by current Selenium.
        set_timeout = getattr(command_executor, "set_timeout", None)
        if set_timeout:
            set_timeout(BROWSER_COMMAND_TIMEOUT)

    def _log(self, msg: str):
        logger.info(msg)
        if self.log_fn:
            self.log_fn(msg)

    @staticmethod
    def _is_transient_browser_error(exc: Exception) -> bool:
        """Return whether a local browser transport failure is safe to retry."""
        if isinstance(exc, (ConnectionError, TimeoutError)):
            return True
        message = repr(exc).lower()
        return any(marker in message for marker in (
            "connection aborted",
            "connection reset",
            "connection refused",
            "remote disconnected",
            "chrome not reachable",
            "not connected to devtools",
            "invalid session id",
            "target window already closed",
            "httpconnectionpool(host='localhost'",
            "read timed out",
            "max retries exceeded",
            "newconnectionerror",
            "session deleted",
            "tab crashed",
            "10054",
        ))

    @staticmethod
    def _is_transient_navigation_error(exc: Exception) -> bool:
        """Backward-compatible alias for the browser transport classifier."""
        return MagazineDownloader._is_transient_browser_error(exc)

    def _run_browser_command(self, operation, *, attempts: int = BROWSER_COMMAND_ATTEMPTS,
                             description: str = "Browser command"):
        """Run a browser operation and recover once if ChromeDriver dies."""
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_transient_browser_error(exc):
                    raise
                self._log(
                    f"{description} lost the browser connection; "
                    f"restarting browser ({attempt}/{attempts - 1})…"
                )
                if not self._restart_browser():
                    raise
                time.sleep(0.5 + random.uniform(0, 0.5))
        if last_error:
            raise last_error
        raise RuntimeError(f"{description} did not run")

    def _restart_browser(self) -> bool:
        """Replace a dead ChromeDriver session and restore saved cookies."""
        old_driver = self._driver
        try:
            if old_driver:
                old_driver.quit()
        except Exception:
            pass

        try:
            self._driver = self._create_driver()
            if self._session_cookies:
                self._restore_cookies(self._session_cookies)
            self._log("Browser session restarted.")
            return True
        except Exception as exc:
            logger.exception("Browser restart failed")
            self._log(f"Browser restart failed: {exc}")
            return False

    def _navigate(self, url: str, attempts: int = 3) -> None:
        """Navigate with bounded retries for transient ChromeDriver resets."""
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self._driver.get(url)
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_transient_navigation_error(exc):
                    raise
                wait = 1.0 * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                self._log(
                    "Browser navigation was interrupted; "
                    f"retrying ({attempt}/{attempts - 1}) in {wait:.1f}s…"
                )
                time.sleep(wait)
        if last_error:
            raise last_error

    def close(self):
        try:
            if self._driver:
                self._driver.quit()
                self._log("Browser closed.")
        except Exception:
            pass

    # -- Cookies ------------------------------------------------------------
    def _restore_cookies(self, cookies: list[dict]) -> int:
        """Restore cookies into the active session; return the number added."""
        # Must be on the target domain first
        self._navigate("https://www.trains.com/")
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
        return added

    def add_cookies(self, cookies: list):
        """Add a list of cookies to the current browser session."""
        self._session_cookies = [
            dict(c) for c in cookies if isinstance(c, dict)
        ]
        added = self._restore_cookies(self._session_cookies)
        self._log(f"Added {added}/{len(cookies)} cookies.")

    def save_cookies(self, path: str):
        cookies = self._driver.get_cookies()
        self._session_cookies = [dict(c) for c in cookies]
        save_cookies_json(cookies, path)

    def _remember_current_cookies(self) -> None:
        """Snapshot cookies so a later browser restart can retain login state."""
        try:
            self._session_cookies = [
                dict(c) for c in self._driver.get_cookies()
            ]
        except Exception:
            pass

    def _cookie_dict(self) -> dict[str, str]:
        """Return the current session cookies in the shape requests expects."""
        cookies = list(getattr(self, "_session_cookies", []) or [])
        if not cookies:
            try:
                cookies = list(self._driver.get_cookies() or [])
            except Exception:
                cookies = []
        return {
            str(cookie["name"]): str(cookie["value"])
            for cookie in cookies
            if isinstance(cookie, dict)
            and cookie.get("name") is not None
            and cookie.get("value") is not None
        }

    @staticmethod
    def _is_browser_blocked_page(driver) -> bool:
        """Detect the small 403 page returned by the site's anti-bot layer."""
        try:
            title = str(getattr(driver, "title", "") or "").strip().lower()
        except Exception:
            title = ""
        if title in {"403 forbidden", "access denied", "forbidden"}:
            return True
        try:
            source = str(getattr(driver, "page_source", "") or "").lower()
        except Exception:
            source = ""
        return len(source) <= 20_000 and any(
            marker in source
            for marker in ("<title>403 forbidden", "<h1>403 forbidden", "error 403")
        )

    def _fetch_authenticated_html(
        self,
        url: str,
        *,
        expected_scope: str | None = None,
    ) -> tuple[str, str]:
        """Fetch a page with saved cookies when Selenium is blocked by 403."""
        import requests as _req

        response = _req.get(
            url,
            cookies=self._cookie_dict(),
            headers={
                "User-Agent": HTTP_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=BROWSER_COMMAND_TIMEOUT,
        )
        response.raise_for_status()
        final_url = str(getattr(response, "url", url) or url)
        if expected_scope and not _canonical_url(final_url).startswith(
            _canonical_url(expected_scope)
        ):
            raise ArchiveRedirectError(
                f"HTTP archive request redirected outside the requested route: "
                f"{url} → {final_url}"
            )
        return response.text, final_url

    @staticmethod
    def _detect_download_mode_from_html(
        html: str,
        base_url: str,
    ) -> tuple[str, str | None]:
        """Detect direct, viewer, gated, or read-only issues from HTML."""
        links = _extract_anchor_links(html, base_url)
        for href, text in links:
            path = urlsplit(href).path.lower()
            if text.strip().lower() == "download" and path.endswith(".pdf"):
                return "mode1", href

        lowered = (html or "").lower()
        if any(marker in lowered for marker in (
            "ci-media.ci-media--gated",
            "ci-media--gated",
            "ci-btn--locked",
            "ci-paywall",
        )):
            return "mode3", "gated"
        if any(marker in lowered for marker in (
            "real3dflipbook",
            "read magazine",
            "pdf edition",
        )):
            return "mode2", None
        return "mode3", None

    def _get_page_issue_links_via_http(
        self,
        url: str,
        archive_url: str,
        hint_prefix: str | None = None,
    ) -> list[str]:
        """Collect issue links from authenticated HTML when browser HTML is blocked."""
        self._log(
            "Browser returned 403 for the archive page; "
            "using authenticated HTTP fallback."
        )
        html, _ = self._fetch_authenticated_html(
            url,
            expected_scope=archive_url,
        )
        links: list[str] = []
        for raw_href, _text in _extract_anchor_links(html, url):
            href = self._canonical_url(raw_href)
            if self._is_issue_link(href, archive_url, hint_prefix=hint_prefix) \
                    and href not in links:
                links.append(href)
        return links

    def detect_issue_mode(
        self,
        issue_url: str,
        hint_prefix: str | None = None,
    ) -> tuple[str, str | None]:
        """Inspect an issue using Selenium, with an authenticated HTTP fallback."""
        self._navigate(issue_url)
        time.sleep(2 + random.uniform(0, 0.5))
        if self._is_browser_blocked_page(self._driver):
            html, final_url = self._fetch_authenticated_html(
                issue_url,
                expected_scope="https://www.trains.com/",
            )
            return self._detect_download_mode_from_html(html, final_url)
        return detect_download_mode(self._driver)

    # -- Login ---------------------------------------------------------------
    def is_logged_in(self, url: str = "https://www.trains.com/") -> bool:
        def check_login():
            self._navigate(url)
            time.sleep(2)
            if self._is_browser_blocked_page(self._driver):
                src, _ = self._fetch_authenticated_html(url)
            else:
                src = self._driver.page_source
            src = src.lower()
            return any(k in src for k in (
                "log out", "logout", "sign out", "my account",
                "hello,", "my benefits",
            ))

        try:
            return self._run_browser_command(
                check_login, description="Login check"
            )
        except Exception as e:
            logger.error(f"Login check error: {e}")
            return False

    def wait_for_manual_login(
        self,
        timeout: int = LOGIN_TIMEOUT,
        progress_fn=None,
        stop_requested=None,
    ) -> bool:
        """
        Open trains.com in the visible browser and poll until the user
        has successfully logged in (or timeout expires).
        """
        # Keep one deadline across recovery; a dead session must not grant
        # another full login timeout or cause an endless restart loop.
        deadline = time.monotonic() + timeout

        def wait_for_login():
            if time.monotonic() >= deadline:
                return False
            # A replacement browser starts on a blank page. Reopen the login
            # entry point once per attempt, never during normal polling.
            self._navigate("https://www.trains.com/")
            self._log("Please log in via the browser window. Waiting…")
            while time.monotonic() < deadline:
                if stop_requested and stop_requested():
                    return False
                src = self._driver.page_source.lower()
                if any(k in src for k in (
                    "log out", "logout", "sign out", "my account",
                    "hello,", "my benefits",
                )):
                    self._remember_current_cookies()
                    self._log("Login detected.")
                    return True
                remaining = max(0.0, deadline - time.monotonic())
                if progress_fn:
                    progress_fn(f"Waiting for login… ({int(remaining)}s remaining)")
                time.sleep(min(3, remaining))
            return False

        try:
            return self._run_browser_command(
                wait_for_login, description="Manual login"
            )
        except Exception as exc:
            if not self._is_transient_browser_error(exc):
                raise
            logger.exception("Browser connection failed during manual login")
            raise RuntimeError(
                "The browser's automation connection was lost during login "
                "and automatic recovery failed. Chrome may still be open. "
                "Start the download again; if it fails again, check "
                "trains_downloader.log for details."
            ) from exc

    # -- Issue link collection ------------------------------------------------
    @staticmethod
    def _canonical_url(url: str) -> str:
        """Normalize an archive URL without retaining filters or fragments."""
        return _canonical_url(url)

    def _is_issue_link(self, href: str, archive_url: str,
                       hint_prefix: str | None = None) -> bool:
        """
        Return True if href looks like an individual issue page under archive_url.
        Rejects year-filter URLs (?archive_year=…), pagination (/page/N/),
        and known non-issue slugs (current-issue, special-issues, etc.).
        """
        if not href:
            return False
        href = MagazineDownloader._canonical_url(href)
        archive_url = MagazineDownloader._canonical_url(archive_url)
        if not href.startswith(archive_url):
            return False
        suffix = href[len(archive_url):].strip("/")
        if not suffix:           # bare archive URL itself
            return False
        first_slug = suffix.split("/")[0]
        if first_slug in _NON_ISSUE_SLUGS:
            return False
        # Normal archives contain dated issue slugs.  Keep special-issue slugs
        # permissive because their titles are not necessarily date-shaped.
        if "/special-issues/" not in archive_url:
            if not parse_pdf_filename(first_slug + ".pdf", hint_prefix=hint_prefix):
                return False
        return True

    @retry(attempts=3, exceptions=(Exception,))
    def get_page_issue_links(self, url: str, archive_url: str,
                             hint_prefix: str | None = None) -> list[str]:
        return self._run_browser_command(
            lambda: self._get_page_issue_links_once(
                url, archive_url, hint_prefix=hint_prefix
            ),
            description="Archive page inspection",
        )

    def _get_page_issue_links_once(self, url: str, archive_url: str,
                                   hint_prefix: str | None = None) -> list[str]:
        from selenium.webdriver.support.ui import WebDriverWait

        self._navigate(url)

        expected_scope = self._canonical_url(archive_url)
        current_url = self._canonical_url(self._driver.current_url)
        if not current_url.startswith(expected_scope):
            raise ArchiveRedirectError(
                f"Archive redirected outside the requested route: {url} → "
                f"{self._driver.current_url}"
            )

        if self._is_browser_blocked_page(self._driver):
            return self._get_page_issue_links_via_http(
                url,
                archive_url,
                hint_prefix=hint_prefix,
            )

        try:
            WebDriverWait(self._driver, 15).until(
                lambda driver: driver.execute_script(
                    "return document.readyState"
                ) in ("interactive", "complete")
            )
        except Exception as exc:
            if self._is_transient_browser_error(exc):
                raise
            raise ArchiveScanError(f"Archive page did not finish loading: {url}") from exc

        raw_hrefs = self._driver.execute_script(
            "return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);"
        ) or []
        links: list[str] = []
        for raw_href in raw_hrefs:
            href = self._canonical_url(raw_href)
            if self._is_issue_link(href, archive_url, hint_prefix=hint_prefix) \
                    and href not in links:
                links.append(href)
        return links

    def collect_all_issue_links(self, archive_url: str, max_pages: int = 110,
                                hint_prefix: str | None = None,
                                allow_empty: bool = False) -> list[str]:
        """
        New trains.com pagination: page 1 = archive_url, page N = archive_url + 'page/N/'
        """
        all_links: list = []
        is_special_archive = "/special-issues/" in self._canonical_url(archive_url)
        for page_num in range(1, max_pages + 1):
            url = archive_url if page_num == 1 else f"{archive_url}page/{page_num}/"
            try:
                page_links = self.get_page_issue_links(
                    url, archive_url, hint_prefix=hint_prefix
                )
            except ArchiveRedirectError as exc:
                if allow_empty and is_special_archive and not all_links:
                    self._log(f"  Special-issue route unavailable: {exc}")
                    return []
                exc.partial_links = list(all_links)
                raise
            except ArchiveScanError as exc:
                exc.partial_links = list(dict.fromkeys(
                    [*all_links, *exc.partial_links]
                ))
                raise
            except Exception as e:
                status_code = getattr(getattr(e, "response", None), "status_code", None)
                if status_code == 404 and all_links:
                    self._log(f"  No more issues after page {page_num - 1} -- done.")
                    break
                if status_code == 404 and allow_empty and is_special_archive:
                    self._log("  No special issues found -- done.")
                    break
                if status_code == 404 and page_num == 1:
                    raise ArchiveScanError(
                        f"Archive returned no issue links on page 1: {archive_url}",
                        partial_links=all_links,
                    ) from e
                raise ArchiveScanError(
                    f"Error loading archive page {page_num} ({url}): {e}",
                    partial_links=all_links,
                ) from e

            new = [l for l in page_links if l not in all_links]
            if not new:
                if page_num == 1:
                    if allow_empty and is_special_archive:
                        self._log("  No special issues found -- done.")
                    else:
                        raise ArchiveScanError(
                            f"Archive returned no issue links on page 1: {archive_url}"
                        )
                else:
                    self._log(f"  No more issues after page {page_num - 1} -- done.")
                break
            all_links.extend(new)
            self._log(f"  Page {page_num}: {len(new)} issues ({len(all_links)} total)")
            time.sleep(1 + random.uniform(0, 0.5))

        return all_links

    # -- Single issue download ------------------------------------------------
    def download_issue(self, issue_url: str, dest_dir: str,
                       hint_prefix: str | None = None,
                       flat: bool = False) -> tuple[bool, str]:
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
        try:
            return self._run_browser_command(
                lambda: self._download_issue_once(
                    issue_url, dest_dir, hint_prefix, flat=flat
                ),
                description="Issue download",
            )

        except Exception as e:
            logger.exception(f"Error downloading {issue_url}")
            return False, str(e)

    def _download_issue_once(self, issue_url: str, dest_dir: str,
                             hint_prefix: str | None,
                             flat: bool = False) -> tuple[bool, str]:
        """Perform one issue attempt; the public method supplies recovery."""
        from selenium.webdriver.common.by import By

        self._navigate(issue_url)
        time.sleep(2 + random.uniform(0, 0.5))

        if self._is_browser_blocked_page(self._driver):
            html, final_url = self._fetch_authenticated_html(
                issue_url,
                expected_scope="https://www.trains.com/",
            )
            mode, detail = self._detect_download_mode_from_html(html, final_url)
            if mode == "mode1" and detail:
                return self._fetch_pdf(
                    detail,
                    dest_dir,
                    hint_prefix,
                    self._cookie_dict(),
                    flat=flat,
                )
            if detail == "gated":
                return False, _gated_issue_message(issue_url)
            if mode == "mode2":
                return False, (
                    "Flipbook download requires browser HTML access, but the "
                    f"site blocked the browser session: {issue_url}"
                )
            return False, f"No PDF download available for {issue_url} (read-only issue)"

        # ---- Mode 1: direct <a> download link -------------------------------
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
            return self._fetch_pdf(pdf_url, dest_dir, hint_prefix, cookies, flat=flat)

        # ---- Membership gate ------------------------------------------------
        # The public cover card is not an interactive reader when the issue is
        # locked.  Return immediately instead of spending 60 seconds clicking
        # a paywall while waiting for a toolbar that cannot appear.
        if _is_membership_gated(self._driver):
            return False, _gated_issue_message(issue_url)

        # ---- Mode 2: flipbook reader ----------------------------------------
        # The btnDownloadPdf span only exists AFTER the reader is opened.
        # Detect the flipbook cover div or "Read Magazine" button as the trigger.
        if _has_flipbook_trigger(self._driver):
            return self._flipbook_download(issue_url, dest_dir, hint_prefix, flat=flat)

        # ---- Mode 3: no download available (read-only) ----------------------
        return False, f"No PDF download available for {issue_url} (read-only issue)"

    def _flipbook_download(self, issue_url: str, dest_dir: str,
                           hint_prefix: str | None, flat: bool = False) -> tuple[bool, str]:
        """
        Open the real3d-flipbook reader, click its download button, and wait
        for the PDF to land in self.download_dir, then rename/move it.
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        if _is_membership_gated(self._driver):
            return False, _gated_issue_message(issue_url)

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
            # Fallback: an unlocked ci-media cover.  Do not click the cover of
            # a locked membership card; it is visually similar but has no
            # reader behind it.
            covers = self._driver.find_elements(
                By.CSS_SELECTOR,
                "div.ci-media:not(.ci-media--gated) div.ci-media__cover",
            )
            if covers:
                return covers[0]
            for label in ("PDF Edition", "Read Magazine"):
                buttons = self._driver.find_elements(
                    By.XPATH,
                    "//button[not(contains(@class, 'ci-btn--locked')) and "
                    f"contains(normalize-space(.), '{label}')]",
                )
                if buttons:
                    return buttons[0]
            return None

        def _find_download_control(driver):
            selectors = (
                "span[data-name='btnDownloadPdf']",
                "[data-name='btnDownloadPdf']",
                "a[href$='.pdf']",
            )
            for selector in selectors:
                controls = driver.find_elements(By.CSS_SELECTOR, selector)
                if controls:
                    return controls[0]
            return False

        # Step 1 & 2: click to open the reader, then wait for the download button.
        # Retry up to 5 times (some pages load the flipbook slowly or need a second click).
        btn_el = None
        for attempt in range(5):
            trigger = _find_reader_trigger()
            if trigger:
                _try_click(trigger)
            # Wait up to 12s per attempt for the download button to appear
            try:
                btn_el = WebDriverWait(self._driver, 12).until(_find_download_control)
                break  # found it
            except Exception:
                pass  # not yet — try clicking again

        if btn_el is None:
            return False, (
                "Flipbook download button never appeared after multiple attempts: "
                f"{issue_url}"
            )

        # Give the reader a brief moment after the button appears
        time.sleep(1)

        # Step 3: JS-click the download button — record handles first so we can
        # identify any newly opened tab by set-difference rather than index.
        handles_before = set(self._driver.window_handles)
        original_handle = self._driver.current_window_handle
        self._driver.execute_script("arguments[0].click();", btn_el)
        self._log(f"  Clicked flipbook download button")

        # Step 4: check if a new tab opened containing the PDF URL
        time.sleep(2)
        handles_after = set(self._driver.window_handles)
        new_handles = handles_after - handles_before
        if new_handles:
            new_handle = next(iter(new_handles))
            try:
                self._driver.switch_to.window(new_handle)
                new_url = self._driver.current_url
                if ".pdf" in new_url.lower():
                    cookies = {c["name"]: c["value"] for c in self._driver.get_cookies()}
                    self._driver.close()
                    self._driver.switch_to.window(original_handle)
                    return self._fetch_pdf(new_url, dest_dir, hint_prefix, cookies, flat=flat)
                self._driver.close()
            except Exception as _tab_err:
                self._log(f"  Warning: error handling new tab: {_tab_err}")
            finally:
                try:
                    self._driver.switch_to.window(original_handle)
                except Exception:
                    pass

        # Step 5: wait for a completed .pdf file in the download directory (90s)
        deadline = time.time() + 90
        while time.time() < deadline:
            after = pdf_files()
            new_files = after - before
            if new_files:
                new_path = os.path.join(self.download_dir, next(iter(new_files)))
                time.sleep(1)  # ensure file is fully written
                return self._rename_and_move(new_path, dest_dir, hint_prefix, flat=flat)
            time.sleep(1.5)

        return False, (
            "Flipbook download timed out (no file appeared within 90s): "
            f"{issue_url}"
        )

    def _fetch_pdf(self, url: str, dest_dir: str, hint_prefix: str | None,
                   cookies: dict, flat: bool = False) -> tuple[bool, str]:
        return fetch_pdf(url, dest_dir, hint_prefix, cookies, flat,
                         self.download_dir, self._log)

    def _rename_and_move(self, src_path: str, dest_dir: str, hint_prefix: str | None,
                         flat: bool = False) -> tuple[bool, str]:
        return rename_and_move(src_path, dest_dir, hint_prefix, flat, self._log)


# ------------------------------------------------------------------------------
# Reverse-lookup: prefix → archive URL
# ------------------------------------------------------------------------------
def _archive_url_for_prefix(prefix: str) -> str | None:
    for info in MAGAZINES.values():
        if info["prefix"] == prefix:
            return info["url"]
    return None


# ------------------------------------------------------------------------------
# Worker thread
# ------------------------------------------------------------------------------
class WorkerSignals(QObject):
    log               = pyqtSignal(str)
    progress          = pyqtSignal(int, int)        # (current, total)
    magazine_progress = pyqtSignal(str, int, int)   # (mag_name, done, total)
    status_msg        = pyqtSignal(str)
    finished          = pyqtSignal()
    error             = pyqtSignal(str)


class DownloadWorker(QThread):
    def __init__(self, magazines: list, base_dir: str, headless: bool,
                 test_mode: bool, cookies_path: str | None, newest_first: bool,
                 include_specials: bool = True):
        super().__init__()
        self.magazines       = magazines
        self.base_dir        = base_dir
        self.headless        = headless
        self.test_mode       = test_mode
        self.cookies_path    = cookies_path
        self.newest_first    = newest_first
        self.include_specials = include_specials
        self.signals         = WorkerSignals()
        self._stop           = False
        self._start_time: float = 0.0
        self.outcome         = OUTCOME_IDLE
        self._pending_futures: dict = {}
        self._had_failures   = False

    def stop(self):
        self._stop = True
        cancel_pending_futures(self._pending_futures)

    def _log(self, msg: str):
        logger.info(msg)
        self.signals.log.emit(msg)

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

    def run(self):
        downloader = None
        self.outcome = OUTCOME_RUNNING
        self._had_failures = False
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
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit(
                        "Not logged in and headless mode is ON.\n"
                        "Disable headless mode so you can log in via the browser window."
                    )
                    return
                self._log("Please log in via the browser window (you have 5 minutes)…")
                if not downloader.wait_for_manual_login(
                    timeout=LOGIN_TIMEOUT,
                    progress_fn=self.signals.status_msg.emit,
                    stop_requested=lambda: self._stop,
                ):
                    if self._stop:
                        self.outcome = OUTCOME_CANCELLED
                        self._log("Magazine login stopped by user.")
                        return
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit("Login timed out. Please try again.")
                    return
                # Save fresh cookies
                if self.cookies_path:
                    downloader.save_cookies(self.cookies_path)
                    self._log(f"Cookies saved to {self.cookies_path}")

            # -- Collect all issue links ------------------------------------
            progress = load_progress()
            completed_set = set(progress["completed"])  # legacy compatibility for result handling
            # each task: (url, dest_dir, prefix, flat, mag_name)
            all_tasks: list[tuple[str, str, str, bool, str]] = []

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
                try:
                    links = downloader.collect_all_issue_links(
                        archive_url, max_pages=max_pages, hint_prefix=prefix
                    )
                except ArchiveScanError as exc:
                    self._had_failures = True
                    links = exc.partial_links
                    self._log(
                        f"  Archive scan incomplete for {mag_name}: {exc}"
                    )
                if not self.newest_first:   # list is already newest-first from the archive
                    links = list(reversed(links))
                all_tasks.extend([(link, dest_dir, prefix, False, mag_name) for link in links])

                if self.include_specials:
                    specials_url = archive_url + "special-issues/"
                    special_dir  = os.path.join(dest_dir, "Special Issues")
                    self._log(f"  Checking special issues at {specials_url}…")
                    try:
                        special_links = downloader.collect_all_issue_links(
                            specials_url,
                            max_pages=max_pages,
                            hint_prefix=prefix,
                            allow_empty=True,
                        )
                    except ArchiveScanError as exc:
                        self._had_failures = True
                        special_links = exc.partial_links
                        self._log(
                            f"  Special-issue scan incomplete for {mag_name}: {exc}"
                        )
                    if not self.newest_first:
                        special_links = list(reversed(special_links))
                    if special_links:
                        self._log(f"  Found {len(special_links)} special issue(s).")
                    all_tasks.extend([(link, special_dir, prefix, True, mag_name) for link in special_links])

            total = len(all_tasks)
            self._log(f"\nTotal issues found: {total}")

            if total == 0:
                if self._stop:
                    self.outcome = OUTCOME_CANCELLED
                elif self._had_failures:
                    self.outcome = OUTCOME_FAILED
                    self._log(
                        "Archive discovery was incomplete; no issues were available to download."
                    )
                else:
                    self.outcome = OUTCOME_NO_RESULTS
                if self.outcome == OUTCOME_NO_RESULTS:
                    self._log("No issues found to download.")
                return

            mag_done: dict[str, int] = {}
            mag_total: dict[str, int] = {}
            for _, _, _, _, mn in all_tasks:
                if mn:
                    mag_total[mn] = mag_total.get(mn, 0) + 1

            # -- Download each issue (Mode 1 parallel, Mode 2/3 sequential) ----
            self._start_time = time.time()
            done = 0
            with ThreadPoolExecutor(max_workers=3) as pool:
                pending: dict = {}   # future → (issue_url, mag_name)
                self._pending_futures = pending

                try:
                    for issue_url, dest_dir, prefix, flat, mag_name in all_tasks:
                        if self._stop:
                            self._log("Stopped by user.")
                            cancel_pending_futures(pending)
                            break

                        scoped_key_value = progress_key(issue_url, dest_dir, flat)
                        if _is_progress_completed(progress, issue_url, dest_dir, flat):
                            self._log(f"[skip] {issue_url}")
                            done += 1
                            self._emit_progress(done, total, mag_name, mag_done, mag_total)
                            continue

                        if issue_already_on_disk(issue_url, dest_dir, prefix, flat):
                            self._log(f"[exists] {issue_url}")
                            completed_set.add(issue_url)
                            _record_progress_completion(progress, issue_url, scoped_key_value)
                            save_progress(progress)
                            done += 1
                            self._emit_progress(done, total, mag_name, mag_done, mag_total)
                            continue

                        self._log(f"[{done + 1}/{total}] {issue_url}")
                        try:
                            def inspect_issue():
                                return downloader.detect_issue_mode(
                                    issue_url,
                                    hint_prefix=prefix,
                                )

                            mode, mode_detail = downloader._run_browser_command(
                                inspect_issue,
                                description="Issue inspection",
                            )
                            pdf_url = mode_detail
                        except Exception as e:
                            self._had_failures = True
                            self._log(f"  Error loading page: {e}")
                            _handle_result(False, str(e), issue_url,
                                           progress, completed_set, self._log,
                                           progress_key_value=scoped_key_value)
                            done += 1
                            self._emit_progress(done, total, mag_name, mag_done, mag_total)
                            continue

                        if mode == "mode1":
                            try:
                                cookies = downloader._run_browser_command(
                                    lambda: {
                                        c["name"]: c["value"]
                                        for c in downloader._driver.get_cookies()
                                    },
                                    description="Read browser cookies",
                                )
                            except Exception as e:
                                self._had_failures = True
                                self._log(f"  Error reading browser cookies: {e}")
                                _handle_result(
                                    False, str(e), issue_url,
                                    progress, completed_set, self._log,
                                    progress_key_value=scoped_key_value,
                                )
                                done += 1
                                self._emit_progress(done, total, mag_name, mag_done, mag_total)
                                continue
                            fut = pool.submit(
                                fetch_pdf, pdf_url, dest_dir, prefix,
                                cookies, flat, downloader.download_dir, self._log
                            )
                            pending[fut] = (issue_url, mag_name, scoped_key_value)
                            # Don't increment done yet — wait for future to complete
                        elif mode == "mode2":
                            try:
                                def download_flipbook():
                                    # A retry after a dead session needs the
                                    # issue page loaded again before looking
                                    # for the reader trigger.
                                    downloader._navigate(issue_url)
                                    time.sleep(2 + random.uniform(0, 0.5))
                                    return downloader._flipbook_download(
                                        issue_url, dest_dir, prefix, flat=flat
                                    )

                                ok, result = downloader._run_browser_command(
                                    download_flipbook,
                                    description="Flipbook download",
                                )
                            except Exception as e:
                                ok, result = False, str(e)
                            if not ok and "read-only" not in result and "No PDF download available" not in result:
                                self._had_failures = True
                            _handle_result(ok, result, issue_url,
                                           progress, completed_set, self._log,
                                           progress_key_value=scoped_key_value)
                            done += 1
                            self._emit_progress(done, total, mag_name, mag_done, mag_total)
                            time.sleep(1 + random.uniform(0, 0.5))
                        else:  # mode3
                            if mode_detail == "gated":
                                self._had_failures = True
                                result = _gated_issue_message(issue_url)
                            else:
                                result = "No PDF download available (read-only issue)"
                            _handle_result(
                                False, result,
                                issue_url, progress, completed_set, self._log,
                                progress_key_value=scoped_key_value,
                            )
                            done += 1
                            self._emit_progress(done, total, mag_name, mag_done, mag_total)

                    # Stop requests cancel queued work; active requests are
                    # drained so the executor can shut down cleanly.
                    if self._stop:
                        cancel_pending_futures(pending)
                    for fut in as_completed(pending):
                        if fut.cancelled():
                            continue
                        issue_url, mag_name, scoped_key_value = pending[fut]
                        try:
                            ok, result = fut.result()
                        except Exception as e:
                            ok, result = False, str(e)
                        if not ok:
                            self._had_failures = True
                        _handle_result(ok, result, issue_url,
                                       progress, completed_set, self._log,
                                       progress_key_value=scoped_key_value)
                        done += 1
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)
                finally:
                    self._pending_futures = {}

            if self._stop:
                self.outcome = OUTCOME_CANCELLED
                self._log("\nSession cancelled.")
            elif self._had_failures:
                self.outcome = OUTCOME_FAILED
                self._log("\nSession finished with failures.")
            else:
                self.outcome = OUTCOME_SUCCESS
                self._log(f"\nSession complete. {len(progress['completed'])} total downloaded.")

            # Save cookies at the end of a successful run
            if self.cookies_path:
                downloader.save_cookies(self.cookies_path)

        except Exception as e:
            self.outcome = OUTCOME_FAILED
            logger.exception("Worker error")
            self.signals.error.emit(str(e))
        finally:
            if downloader:
                downloader.close()
            self.signals.finished.emit()


class TrackPlanWorker(QThread):
    """Downloads individual PDFs from the authenticated track plan database."""

    def __init__(self, destination_dir: str, cookies_path: str | None):
        super().__init__()
        self.destination_dir = os.path.abspath(destination_dir)
        self.cookies_path = cookies_path or DEFAULT_COOKIES_FILE
        self.signals = WorkerSignals()
        self._stop = False
        self._had_failures = False
        self.outcome = OUTCOME_IDLE

    def stop(self):
        self._stop = True

    def _log(self, message: str):
        logger.info(message)
        self.signals.log.emit(message)

    def _fetch_page(self, downloader, session, url: str) -> tuple[str, str]:
        """Fetch an authenticated page, falling back to the signed-in browser."""
        try:
            with session.get(url, timeout=BROWSER_COMMAND_TIMEOUT) as response:
                response.raise_for_status()
                html = response.text
                final_url = str(getattr(response, "url", url) or url)
        except Exception as http_error:
            self._log("Authenticated page request failed; retrying in the browser…")

            def read_browser_page():
                downloader._navigate(url)
                time.sleep(1)
                if downloader._is_browser_blocked_page(downloader._driver):
                    raise TrackPlanAccessError(
                        "Trains.com denied access to the track plan page. "
                        "Refresh the shared cookies or check this account's access."
                    )
                return downloader._driver.page_source, downloader._driver.current_url

            try:
                html, final_url = downloader._run_browser_command(
                    read_browser_page,
                    description="Track plan page request",
                )
            except TrackPlanAccessError:
                raise
            except Exception as browser_error:
                raise ArchiveScanError(
                    f"Could not load {url}. HTTP request: {http_error}; "
                    f"browser request: {browser_error}"
                ) from browser_error

        final_canonical = _canonical_url(final_url)
        route = _canonical_url(TRACK_PLAN_DATABASE_URL)
        if not final_canonical.startswith(route):
            raise TrackPlanAccessError(
                f"Trains.com redirected away from the track plan database: "
                f"{final_url}"
            )
        expected = _canonical_url(url)
        if final_canonical != expected:
            raise ArchiveRedirectError(
                f"Track plan request redirected to an unexpected page: "
                f"{url} → {final_url}"
            )
        return html, final_url

    def run(self):
        downloader = None
        session = None
        authenticated = False
        self.outcome = OUTCOME_RUNNING
        self._had_failures = False
        try:
            os.makedirs(self.destination_dir, exist_ok=True)
            self._log("Starting browser for the track plan database…")
            downloader = MagazineDownloader(
                download_dir=self.destination_dir,
                headless=False,
                log_fn=self.signals.log.emit,
            )

            logged_in = False
            if self.cookies_path and os.path.exists(self.cookies_path):
                cookies = load_cookies(self.cookies_path)
                if cookies:
                    downloader.add_cookies(cookies)
                    logged_in = downloader.is_logged_in()
                    if logged_in:
                        self._log("Authenticated via the shared saved cookies.")
                    else:
                        self._log(
                            "Saved cookies did not authenticate — need to log in manually."
                        )

            if not logged_in:
                self._log(
                    "Please log in via the browser window (you have 5 minutes)…"
                )
                if not downloader.wait_for_manual_login(
                    timeout=LOGIN_TIMEOUT,
                    progress_fn=self.signals.status_msg.emit,
                    stop_requested=lambda: self._stop,
                ):
                    if self._stop:
                        self.outcome = OUTCOME_CANCELLED
                        self._log("Track plan login stopped by user.")
                        return
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit("Login timed out. Please try again.")
                    return
                if self.cookies_path:
                    downloader.save_cookies(self.cookies_path)
                    self._log(f"Cookies saved to {self.cookies_path}")
            authenticated = True

            import requests

            session = requests.Session()
            session.headers.update({
                "User-Agent": HTTP_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
            })
            session.cookies.update(downloader._cookie_dict())

            plan_urls: list[str] = []
            page_number = 1
            max_page = 1
            scan_complete = False
            access_lost = False

            while page_number <= max_page:
                if self._stop:
                    self.outcome = OUTCOME_CANCELLED
                    self._log("Track plan scan stopped by user.")
                    return

                page_url = (
                    TRACK_PLAN_DATABASE_URL
                    if page_number == 1
                    else f"{TRACK_PLAN_DATABASE_URL}page/{page_number}/"
                )
                self.signals.status_msg.emit(
                    f"Scanning track plan page {page_number} of {max_page}…"
                )
                try:
                    time.sleep(TRACK_PLAN_REQUEST_DELAY)
                    html, _final_url = self._fetch_page(downloader, session, page_url)
                    page_plans, discovered_max = _extract_track_plan_listing(
                        html, page_url
                    )
                    if not page_plans:
                        raise ArchiveScanError(
                            f"Track plan database page {page_number} contained no plan links.",
                            partial_links=plan_urls,
                        )
                    new_plans = [url for url in page_plans if url not in plan_urls]
                    if not new_plans:
                        raise ArchiveScanError(
                            f"Track plan database page {page_number} repeated earlier links.",
                            partial_links=plan_urls,
                        )
                    plan_urls.extend(new_plans)
                    max_page = max(max_page, discovered_max)
                    if max_page > 500:
                        raise ArchiveScanError(
                            f"Track plan pagination reported an unexpected limit of {max_page} pages.",
                            partial_links=plan_urls,
                        )
                    self.signals.progress.emit(page_number, max_page)
                    self._log(
                        f"  Listing page {page_number}: {len(new_plans)} plans "
                        f"({len(plan_urls)} total)."
                    )
                except TrackPlanAccessError as exc:
                    self._had_failures = True
                    access_lost = True
                    self._log(f"Track plan access failed: {exc}")
                    break
                except Exception as exc:
                    self._had_failures = True
                    self._log(f"Track plan scan failed on page {page_number}: {exc}")
                    break

                page_number += 1
                scan_complete = page_number > max_page

            if self._stop:
                self.outcome = OUTCOME_CANCELLED
                self._log("Track plan scan stopped by user.")
                return
            if not plan_urls:
                self.outcome = OUTCOME_FAILED if self._had_failures else OUTCOME_NO_RESULTS
                if self.outcome == OUTCOME_NO_RESULTS:
                    self._log("No track plans were found.")
                return
            if access_lost:
                self._log(
                    "The authenticated session stopped working during discovery. "
                    "Refresh the shared cookies and start again."
                )
                self.outcome = OUTCOME_FAILED
                return

            self._log(
                f"Found {len(plan_urls)} track plans across "
                f"{page_number - 1} listing page(s)."
            )
            if not scan_complete:
                self._log(
                    "The database scan was incomplete; downloading plans already found."
                )

            progress = load_progress()
            total = len(plan_urls)
            done = 0
            downloaded = 0
            existing = 0

            for index, plan_url in enumerate(plan_urls, 1):
                if self._stop:
                    break
                slug = urlsplit(plan_url).path.rstrip("/").rsplit("/", 1)[-1]
                label = slug.replace("-", " ")
                self.signals.status_msg.emit(
                    f"Checking plan {index} of {total}: {label}"
                )
                stop_for_access = False

                try:
                    time.sleep(TRACK_PLAN_REQUEST_DELAY)
                    html, _final_url = self._fetch_page(
                        downloader, session, plan_url
                    )
                    pdf_url = _extract_track_plan_pdf_url(html, plan_url)
                    if not pdf_url:
                        self._had_failures = True
                        self._log(f"[error] No plan PDF link found: {plan_url}")
                    else:
                        scoped_key = progress_key(
                            pdf_url, self.destination_dir, flat=True
                        )
                        filename = _track_plan_pdf_filename(pdf_url)
                        expected_path = os.path.join(
                            self.destination_dir, filename
                        )
                        if _is_progress_completed(
                            progress, pdf_url, self.destination_dir, flat=True
                        ):
                            self._log(f"[skip] {filename}")
                            existing += 1
                        elif os.path.isfile(expected_path) and _verify_pdf(expected_path):
                            self._log(f"[exists] {filename}")
                            _record_progress_completion(
                                progress, pdf_url, scoped_key
                            )
                            save_progress(progress)
                            existing += 1
                        else:
                            time.sleep(TRACK_PLAN_REQUEST_DELAY)
                            ok, result = _download_track_plan_pdf(
                                session,
                                pdf_url,
                                self.destination_dir,
                                lambda: self._stop,
                            )
                            if ok:
                                self._log(f"  → {result}")
                                _record_progress_completion(
                                    progress, pdf_url, scoped_key
                                )
                                save_progress(progress)
                                downloaded += 1
                            elif result == "cancelled":
                                self._stop = True
                            else:
                                self._had_failures = True
                                self._log(f"[error] {filename}: {result}")
                                if result.startswith("Access denied"):
                                    stop_for_access = True
                except TrackPlanAccessError as exc:
                    self._had_failures = True
                    self._log(f"[error] Track plan access stopped: {exc}")
                    stop_for_access = True
                except Exception as exc:
                    self._had_failures = True
                    self._log(f"[error] Could not process {plan_url}: {exc}")

                if self._stop:
                    break
                done += 1
                self.signals.progress.emit(done, total)
                self.signals.status_msg.emit(f"Processed {done} of {total} plans")
                if stop_for_access:
                    self._log(
                        "Trains.com denied access. Refresh the shared cookies or "
                        "check this account's access before starting again."
                    )
                    break

            if authenticated and self.cookies_path:
                downloader.save_cookies(self.cookies_path)

            if self._stop:
                self.outcome = OUTCOME_CANCELLED
                self._log("Track plan download stopped by user.")
            elif self._had_failures or not scan_complete:
                self.outcome = OUTCOME_FAILED
                self._log(
                    f"Track plan run finished with failures: {downloaded} downloaded, "
                    f"{existing} already present or skipped."
                )
            else:
                self.outcome = OUTCOME_SUCCESS
                self._log(
                    f"Track plan run complete: {downloaded} downloaded, "
                    f"{existing} already present or skipped."
                )
        except Exception as exc:
            self.outcome = OUTCOME_FAILED
            logger.exception("Track plan worker error")
            self.signals.error.emit(str(exc))
        finally:
            if session is not None:
                session.close()
            if downloader is not None:
                downloader.close()
            self.signals.finished.emit()


class OrganizeWorker(QThread):
    """Runs organize_pdfs in a background thread."""
    def __init__(self, source_dir: str, dest_dir: str, hint_prefix: str | None):
        super().__init__()
        self.source_dir  = source_dir
        self.dest_dir    = dest_dir
        self.hint_prefix = hint_prefix
        self.signals     = WorkerSignals()
        self.result      = None   # filled in by run()
        self._cancel_event = threading.Event()
        self.outcome = OUTCOME_IDLE

    def stop(self):
        self._cancel_event.set()

    def run(self):
        self.outcome = OUTCOME_RUNNING
        try:
            self.result = organize_pdfs(
                self.source_dir,
                self.dest_dir,
                hint_prefix=self.hint_prefix,
                log_fn=self.signals.log.emit,
                progress_fn=self.signals.progress.emit,
                cancel_event=self._cancel_event,
            )
        except Exception as e:
            self.outcome = OUTCOME_FAILED
            logger.exception("Organizer worker error")
            self.signals.error.emit(str(e))
        finally:
            if self.result is not None and self.outcome == OUTCOME_RUNNING:
                if self._cancel_event.is_set():
                    self.result.scan_complete = False
                    self.outcome = OUTCOME_CANCELLED
                elif not self.result.scan_complete:
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit(
                        "Organizer scan was incomplete; partial results were retained."
                    )
                elif not any((
                    self.result.moved,
                    self.result.already_correct,
                    self.result.unrecognized,
                    self.result.corrupt,
                )):
                    self.outcome = OUTCOME_NO_RESULTS
                else:
                    self.outcome = OUTCOME_SUCCESS
            self.signals.finished.emit()


class MissingIssuesWorker(QThread):
    """
    Downloads only the issues identified as missing by the organizer.
    Crawls the archive for the given magazine, matches URLs against the
    missing (year, month) pairs by parsing each URL slug, and downloads
    only those that are needed.
    """

    def __init__(self, prefix: str, archive_url: str,
                 missing_by_year: dict[str, list[str]],
                 dest_dir: str, cookies_path: str | None, headless: bool):
        super().__init__()
        self.prefix          = prefix
        self.archive_url     = archive_url
        self.missing_by_year = missing_by_year   # {year: [month_names]}
        self.dest_dir        = dest_dir
        self.cookies_path    = cookies_path
        self.headless        = headless
        self.signals         = WorkerSignals()
        self._stop           = False
        self.outcome         = OUTCOME_IDLE
        self._had_failures   = False

    def stop(self):
        self._stop = True

    def _log(self, msg: str):
        logger.info(msg)
        self.signals.log.emit(msg)

    def run(self):
        downloader = None
        self.outcome = OUTCOME_RUNNING
        self._had_failures = False
        try:
            # Build set of (year, month) targets
            targets: set[tuple[str, str]] = {
                (year, month)
                for year, months in self.missing_by_year.items()
                for month in months
            }
            if not targets:
                self.outcome = OUTCOME_NO_RESULTS
                self._log("No missing issues to download.")
                return

            self._log(f"Searching for {len(targets)} missing issue(s) in the archive…")

            downloader = MagazineDownloader(
                download_dir=self.dest_dir,
                headless=self.headless,
                log_fn=self.signals.log.emit,
            )

            # Authentication
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
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit(
                        "Not logged in and headless mode is ON.\n"
                        "Disable headless mode so you can log in via the browser window."
                    )
                    return
                self._log("Please log in via the browser window (you have 5 minutes)…")
                if not downloader.wait_for_manual_login(
                    timeout=LOGIN_TIMEOUT,
                    progress_fn=self.signals.status_msg.emit,
                    stop_requested=lambda: self._stop,
                ):
                    if self._stop:
                        self.outcome = OUTCOME_CANCELLED
                        self._log("Missing-issue login stopped by user.")
                        return
                    self.outcome = OUTCOME_FAILED
                    self.signals.error.emit("Login timed out. Please try again.")
                    return
                if self.cookies_path:
                    downloader.save_cookies(self.cookies_path)
                    self._log(f"Cookies saved to {self.cookies_path}")

            # Collect all issue URLs from the archive
            self._log(f"Scanning archive: {self.archive_url}")
            try:
                links = downloader.collect_all_issue_links(
                    self.archive_url, max_pages=110, hint_prefix=self.prefix
                )
            except ArchiveScanError as exc:
                self._had_failures = True
                links = exc.partial_links
                self._log(
                    f"Archive scan incomplete for {self.prefix}: {exc}; "
                    f"continuing with {len(links)} issue(s) found so far."
                )
            self._log(f"Found {len(links)} issues in archive. Matching against missing list…")

            # Match each URL to a (year, month) by parsing its slug
            matched: list[tuple[str, str, str]] = []  # (url, year, month)
            special: list[str] = []                   # urls with no parseable date
            progress = load_progress()
            completed_set = set(progress["completed"])  # legacy compatibility for result handling
            # Special issues use a separate file so they survive a progress-cache clear
            downloaded_specials = load_special_issues()
            special_dir = os.path.join(self.dest_dir, "Special Issues")
            for url in links:
                slug = url.rstrip("/").split("/")[-1]
                parsed = parse_pdf_filename(slug + ".pdf", hint_prefix=self.prefix)
                if parsed:
                    _, year, month = parsed
                    if month and (year, month) in targets:
                        matched.append((url, year, month))
                else:
                    # Special issue — skip if already downloaded in a prior run
                    special_key_value = progress_key(url, special_dir, True)
                    if special_key_value in downloaded_specials:
                        continue
                    if issue_already_on_disk(url, special_dir, self.prefix, flat=True):
                        _record_progress_completion(progress, url, special_key_value)
                        downloaded_specials.add(special_key_value)
                        save_special_issues(downloaded_specials)
                        save_progress(progress)
                        continue
                    special.append(url)

            if not matched and not special:
                self.outcome = (
                    OUTCOME_FAILED if self._had_failures else OUTCOME_NO_RESULTS
                )
                if self._had_failures:
                    self._log(
                        "Archive discovery was incomplete; could not confirm whether "
                        "the requested missing issues are available."
                    )
                else:
                    self._log("Could not match any missing issues to archive URLs.")
                self._log("Targets: " + ", ".join(f"{y}/{m}" for y, m in sorted(targets)))
                sample_slugs = [url.rstrip("/").split("/")[-1] for url in links[:5]]
                self._log("Sample URL slugs: " + ", ".join(sample_slugs))
                return

            total = len(matched) + len(special)
            self._log(f"Matched {len(matched)} regular issue(s) and {len(special)} special issue(s) to download.")
            self.signals.progress.emit(0, total)

            if special:
                os.makedirs(special_dir, exist_ok=True)

            dl_count = 0
            for i, (url, year, month) in enumerate(matched, 1):
                if self._stop:
                    self._log("Stopped by user.")
                    break

                scoped_key_value = progress_key(url, self.dest_dir, False)
                if _is_progress_completed(progress, url, self.dest_dir, False):
                    self._log(f"[skip] {url}")
                    dl_count += 1
                    self.signals.progress.emit(dl_count, total)
                    continue

                if issue_already_on_disk(url, self.dest_dir, self.prefix, flat=False):
                    self._log(f"[exists] {month} {year}")
                    completed_set.add(url)
                    _record_progress_completion(progress, url, scoped_key_value)
                    save_progress(progress)
                    dl_count += 1
                    self.signals.progress.emit(dl_count, total)
                    continue

                self._log(f"[{i}/{total}] {month} {year}  —  {url}")
                os.makedirs(os.path.join(self.dest_dir, year), exist_ok=True)

                ok, result = downloader.download_issue(url, dest_dir=self.dest_dir,
                                                       hint_prefix=self.prefix)
                if not ok and "read-only" not in result and "No PDF download available" not in result:
                    self._had_failures = True
                _handle_result(
                    ok, result, url, progress, completed_set, self._log,
                    progress_key_value=scoped_key_value,
                )
                if ok:
                    self._log(f"  Downloaded: {result}")

                dl_count += 1
                self.signals.progress.emit(dl_count, total)
                if not self._stop:
                    time.sleep(1 + random.uniform(0, 0.5))

            for url in special:
                if self._stop:
                    self._log("Stopped by user.")
                    break

                slug = url.rstrip("/").split("/")[-1]
                self._log(f"[special] {slug}  —  {url}")
                scoped_key_value = progress_key(url, special_dir, True)

                ok, result = downloader.download_issue(url, dest_dir=special_dir,
                                                       hint_prefix=self.prefix, flat=True)
                if not ok and "read-only" not in result and "No PDF download available" not in result:
                    self._had_failures = True
                _handle_result(
                    ok, result, url, progress, completed_set, self._log,
                    progress_key_value=scoped_key_value,
                )
                if ok:
                    downloaded_specials.add(scoped_key_value)
                    save_special_issues(downloaded_specials)
                    self._log(f"  Downloaded: {result}")
                elif "read-only" in result or "No PDF download available" in result:
                    downloaded_specials.add(scoped_key_value)
                    save_special_issues(downloaded_specials)

                dl_count += 1
                self.signals.progress.emit(dl_count, total)
                if url != special[-1] and not self._stop:
                    time.sleep(1 + random.uniform(0, 0.5))

            if self._stop:
                self.outcome = OUTCOME_CANCELLED
                self._log("\nMissing-issue download cancelled.")
            elif self._had_failures:
                self.outcome = OUTCOME_FAILED
                self._log("\nMissing-issue download finished with failures.")
            else:
                self.outcome = OUTCOME_SUCCESS
                self._log("\nMissing-issue download complete.")

            if self.cookies_path:
                downloader.save_cookies(self.cookies_path)

        except Exception as e:
            self.outcome = OUTCOME_FAILED
            logger.exception("MissingIssuesWorker error")
            self.signals.error.emit(str(e))
        finally:
            if downloader:
                downloader.close()
            self.signals.finished.emit()


# ------------------------------------------------------------------------------
# GUI
# ------------------------------------------------------------------------------
_STYLESHEET = """
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QDialog { background-color: #13131f; }
QWidget { color: #cdd6f4; font-family: "Segoe UI", system-ui, sans-serif; font-size: 10pt; background-color: transparent; }

/* ── Mode toggle buttons ──────────────────────────────────────────────── */
QPushButton[role="mode"] {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 28px;
    color: #585b70;
    font-weight: 600;
    font-size: 10pt;
    min-height: 0;
}
QPushButton[role="mode"]:checked {
    background: #1e1e2e;
    border-color: #353550;
    color: #cdd6f4;
}
QPushButton[role="mode"]:hover:!checked { color: #a6adc8; }

/* ── Magazine chip buttons ────────────────────────────────────────────── */
QPushButton[role="chip"] {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 20px;
    padding: 4px 14px;
    color: #585b70;
    font-weight: 400;
    font-size: 9.5pt;
    min-height: 0;
}
QPushButton[role="chip"]:checked {
    background: #2a3f6f;
    border-color: #89b4fa;
    color: #89b4fa;
    font-weight: 600;
}
QPushButton[role="chip"]:hover:!checked { border-color: #45475a; color: #a6adc8; }
QPushButton[role="chip"]:hover:checked  { background: #324878; }

/* ── Section labels ───────────────────────────────────────────────────── */
QLabel[role="section"] {
    color: #a6adc8;
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.1em;
}

/* ── Mode panel / auth row containers ────────────────────────────────── */
QWidget#mode_panel {
    background: #1e1e2e;
    border: 1px solid #353550;
    border-radius: 0 8px 8px 8px;
}
QWidget#auth_row {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
}

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit, QComboBox {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    min-height: 28px;
}
QLineEdit:focus, QComboBox:focus { border-color: #89b4fa; background: #2a2a42; }
QLineEdit:disabled, QComboBox:disabled { background: #181825; color: #45475a; }
QLineEdit::placeholder { color: #585b70; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background: #252538;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    outline: none;
    padding: 2px;
}

/* ── Buttons — base ───────────────────────────────────────────────────── */
QPushButton {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 6px;
    padding: 6px 16px;
    color: #a6adc8;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover  { background: #2e2e48; border-color: #89b4fa; color: #cdd6f4; }
QPushButton:pressed { background: #383858; }
QPushButton:disabled { background: #181825; color: #45475a; border-color: #252535; }
QPushButton:focus, QCheckBox:focus { border: 2px solid #89b4fa; }

/* ── Buttons — primary ────────────────────────────────────────────────── */
QPushButton[role="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #97c0ff, stop:1 #7aa2f7);
    border: none;
    border-bottom: 2px solid #5a7fd0;
    border-radius: 6px;
    color: #11111b;
    font-weight: 700;
    letter-spacing: 0.02em;
    min-height: 34px;
}
QPushButton[role="primary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #aaceff, stop:1 #89b4fa);
}
QPushButton[role="primary"]:pressed  { background: #7aa2f7; border-bottom-width: 1px; }
QPushButton[role="primary"]:disabled { background: #252538; color: #45475a; border: 1px solid #252535; }

/* ── Buttons — danger ─────────────────────────────────────────────────── */
QPushButton[role="danger"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5a0b8, stop:1 #e8708e);
    border: none;
    border-bottom: 2px solid #b85070;
    border-radius: 6px;
    color: #11111b;
    font-weight: 700;
    min-height: 34px;
}
QPushButton[role="danger"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f7b0c5, stop:1 #f38ba8);
}
QPushButton[role="danger"]:pressed  { background: #f38ba8; border-bottom-width: 1px; }
QPushButton[role="danger"]:disabled { background: #252538; color: #45475a; border: 1px solid #252535; }

/* ── Checkboxes ───────────────────────────────────────────────────────── */
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 17px; height: 17px;
    border: 2px solid #484860;
    border-radius: 4px;
    background: #1e1e2e;
}
QCheckBox::indicator:hover   { border-color: #89b4fa; background: #252538; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QCheckBox::indicator:checked:hover { background: #a6c8ff; border-color: #a6c8ff; }

/* ── Progress bar ─────────────────────────────────────────────────────── */
QProgressBar {
    background: #252538;
    border: none;
    border-radius: 5px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89b4fa, stop:1 #cba6f7);
    border-radius: 5px;
}

/* ── Log areas ────────────────────────────────────────────────────────── */
QTextEdit {
    background: #0d0d17;
    border: 1px solid #252538;
    border-radius: 8px;
    color: #a6adc8;
    selection-background-color: #313244;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 9pt;
}

/* ── Labels ───────────────────────────────────────────────────────────── */
QLabel { color: #cdd6f4; background: transparent; }
QLabel[role="muted"]    { color: #585b70; font-size: 9pt; }
QLabel[role="app-name"] { color: #cdd6f4; font-size: 15pt; font-weight: 700; letter-spacing: -0.02em; }
QLabel[role="status"]   { color: #a6adc8; font-size: 9pt; }

/* ── Thin separator line ─────────────────────────────────────────────── */
QFrame[frameShape="4"] { color: #2a2a3e; }
QFrame[frameShape="5"] { color: #2a2a3e; }

/* ── Scrollbars ───────────────────────────────────────────────────────── */
QScrollBar:vertical   { background: transparent; width: 7px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #353550; border-radius: 3px; min-height: 20px; min-width: 20px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #45475a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; width: 0; }

/* ── Tooltips ─────────────────────────────────────────────────────────── */
QToolTip {
    background: #252538; border: 1px solid #45475a;
    color: #cdd6f4; padding: 5px 10px; border-radius: 5px;
}

/* ── Message boxes ────────────────────────────────────────────────────── */
QMessageBox { background: #1e1e2e; }
QMessageBox QLabel { color: #cdd6f4; }

/* ── Archive workstation redesign ───────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #F6F3EC;
    color: #17242B;
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}
QLabel { background-color: transparent; }
QWidget#app_header { background: transparent; }
QLabel#brand_mark {
    background: #183B49;
    color: #FFFCF7;
    border-radius: 10px;
    font-size: 14pt;
    font-weight: 800;
    padding: 8px;
}
QLabel[role="app-title"] { color: #17242B; font-size: 16pt; font-weight: 800; }
QLabel[role="app-subtitle"] { color: #5B6A70; font-size: 9pt; }
QLabel[role="page-title"] { color: #17242B; font-size: 20pt; font-weight: 800; }
QLabel[role="page-description"] { color: #5B6A70; font-size: 10pt; }
QLabel[role="eyebrow"] {
    color: #5B6A70;
    font-size: 8pt;
    font-weight: 800;
    letter-spacing: 0.08em;
}
QLabel[role="muted"] { color: #5B6A70; font-size: 9pt; }
QLabel[role="status"] { color: #183B49; font-size: 9pt; font-weight: 600; }
QLabel#header_status {
    background: #E5F0EA;
    border: 1px solid #AACAB8;
    border-radius: 14px;
    color: #2E765F;
    font-weight: 700;
    padding: 6px 12px;
}
QLabel#header_status[state="failed"] { background: #F8E8E4; border-color: #DDB2AA; color: #AD4D45; }
QLabel#header_status[state="cancelled"], QLabel#header_status[state="empty"] { background: #FAF0DE; border-color: #DFC285; color: #91631F; }
QFrame#nav_rail {
    background: #183B49;
    border: none;
    border-radius: 14px;
}
QLabel#nav_heading { color: #B6C9CE; font-size: 8pt; font-weight: 800; letter-spacing: 0.08em; }
QToolButton#nav_button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #DCE7E9;
    min-height: 42px;
    padding: 0 14px;
    text-align: left;
}
QToolButton#nav_button:hover { background: #285565; border-color: #78949C; }
QToolButton#nav_button:checked { background: #FFFCF7; color: #183B49; font-weight: 800; }
QFrame[role="card"] {
    background: #FFFCF7;
    border: 1px solid #CEC8BB;
    border-radius: 12px;
}
QFrame[role="card"] > QLabel[role="card-title"] { color: #17242B; font-size: 11pt; font-weight: 800; }
QFrame#magazine_row { background: #F7F3EB; }
QLabel#magazine_prefix { color: #183B49; font-size: 9pt; font-weight: 800; }
QLabel#summary_value { color: #183B49; font-size: 18pt; font-weight: 800; }
QLineEdit, QComboBox {
    background: #FFFCF7;
    border: 1px solid #B2ACA0;
    border-radius: 7px;
    color: #17242B;
    min-height: 32px;
    padding: 5px 10px;
    selection-background-color: #D8E5E8;
    selection-color: #17242B;
}
QLineEdit:focus, QComboBox:focus { background: #FFFFFF; border: 2px solid #A95530; }
QLineEdit:disabled, QComboBox:disabled { background: #E8E3D9; color: #56666D; }
QLineEdit::placeholder { color: #637177; }
QComboBox QAbstractItemView { background: #FFFCF7; color: #17242B; selection-background-color: #D8E5E8; }
QPushButton, QToolButton {
    background: #E8E3D9;
    border: 1px solid #B7B1A5;
    border-radius: 7px;
    color: #183B49;
    min-height: 34px;
    padding: 5px 14px;
    font-weight: 600;
}
QPushButton:hover, QToolButton:hover { background: #DED8CD; border-color: #A95530; }
QPushButton:pressed, QToolButton:pressed { background: #D2CBC0; }
QPushButton:disabled, QToolButton:disabled { background: #E8E4DB; color: #56666D; border-color: #D2CCC2; }
QPushButton:focus, QToolButton:focus, QCheckBox:focus { border: 2px solid #A95530; }
QPushButton[role="primary"] { background: #A95530; border-color: #874226; color: #FFFCF7; font-weight: 800; min-height: 42px; }
QPushButton[role="primary"]:hover { background: #914C2E; }
QPushButton[role="primary"]:disabled { background: #E8E4DB; border-color: #D2CCC2; color: #56666D; }
QPushButton[role="danger"] { background: #F8E8E4; border-color: #DDB2AA; color: #AD4D45; }
QPushButton[role="danger"]:disabled { background: #E8E4DB; border-color: #D2CCC2; color: #56666D; }
QCheckBox { color: #17242B; spacing: 8px; min-height: 36px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 2px solid #718087; border-radius: 4px; background: #FFFCF7; }
QCheckBox::indicator:hover { border-color: #A95530; }
QCheckBox::indicator:checked { background: #A95530; border-color: #874226; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QSplitter::handle { background: #CEC8BB; height: 5px; }
QProgressBar { background: #DDD8CE; border: 1px solid #CEC8BB; border-radius: 5px; min-height: 9px; max-height: 9px; text-align: center; color: transparent; }
QProgressBar::chunk { background: #A95530; border-radius: 4px; }
QTextEdit {
    background: #17242B;
    border: 1px solid #5B6A70;
    border-radius: 8px;
    color: #F6F3EC;
    selection-background-color: #365E6A;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 9pt;
}
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: #A9A398; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #183B49; border: 1px solid #78949C; color: #FFFCF7; padding: 5px 9px; }
QMessageBox { background: #FFFCF7; }
QMessageBox QLabel { color: #17242B; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Trains.com Downloader & Organizer v{APP_VERSION}")
        self.resize(1040, 760)
        self.setMinimumSize(800, 620)
        self.worker:           DownloadWorker | None      = None
        self._track_plan_worker: TrackPlanWorker | None    = None
        self._org_worker:      OrganizeWorker | None      = None
        self._missing_worker:  MissingIssuesWorker | None = None
        self._org_hint:        str | None                 = None
        self._org_dst:         str                        = ""
        self._org_prefix:      str | None                 = None
        self._missing_by_year: dict[str, list[str]]       = {}
        self._raw_log_lines: list[str]                    = []
        self._magazine_progress_rows: dict[str, tuple[QWidget, QProgressBar, QLabel]] = {}
        self._build_ui()
        self._load_settings()
        self._setup_tray()

    # -- UI construction ------------------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(_STYLESHEET)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(6)

        # ── Mode toggle ──────────────────────────────────────────────────────
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(2)
        toggle_row.setContentsMargins(0, 0, 0, 0)
        self._dl_mode_btn  = QPushButton("  Download  ")
        self._org_mode_btn = QPushButton("  Organize  ")
        for btn in (self._dl_mode_btn, self._org_mode_btn):
            btn.setProperty("role", "mode")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
        self._dl_mode_btn.setChecked(True)
        self._dl_mode_btn.setAccessibleName("Download mode")
        self._org_mode_btn.setAccessibleName("Organize mode")
        self._dl_mode_btn.clicked.connect(lambda: self._switch_mode("download"))
        self._org_mode_btn.clicked.connect(lambda: self._switch_mode("organize"))
        toggle_row.addWidget(self._dl_mode_btn)
        toggle_row.addWidget(self._org_mode_btn)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        # ── Stacked mode panels ──────────────────────────────────────────────
        self._dl_panel  = self._make_download_panel()
        self._org_panel = self._make_organize_panel()
        for panel in (self._dl_panel, self._org_panel):
            panel.setObjectName("mode_panel")
            layout.addWidget(panel)
        self._org_panel.setVisible(False)

        layout.addSpacing(8)

        # ── Shared auth row ──────────────────────────────────────────────────
        auth_row = QWidget()
        auth_row.setObjectName("auth_row")
        auth_layout = QVBoxLayout(auth_row)
        auth_layout.setContentsMargins(12, 8, 12, 8)
        auth_layout.setSpacing(8)
        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(8)
        cookie_lbl = QLabel("COOKIE FILE")
        cookie_lbl.setProperty("role", "section")
        self.cookie_edit = QLineEdit(DEFAULT_COOKIES_FILE)
        self.cookie_edit.setAccessibleName("Cookie file path")
        cookie_lbl.setBuddy(self.cookie_edit)
        cookie_browse = QPushButton("Browse…")
        cookie_browse.setFixedWidth(80)
        cookie_browse.setAccessibleName("Browse for cookie file")
        cookie_browse.clicked.connect(self._browse_cookies)
        cookie_row.addWidget(cookie_lbl)
        cookie_row.addWidget(self.cookie_edit)
        cookie_row.addWidget(cookie_browse)
        auth_layout.addLayout(cookie_row)
        auth_note = QLabel(
            "Requires an active trains.com subscription. Leave the browser visible "
            "for first-time login; the JSON cookie file stores your session and is "
            "sensitive. Enable headless mode only after login succeeds."
        )
        auth_note.setProperty("role", "status")
        auth_note.setWordWrap(True)
        auth_layout.addWidget(auth_note)
        self.org_headless_cb = QCheckBox("Hide browser for missing-issue downloads")
        self.org_headless_cb.setAccessibleName("Hide browser for missing-issue downloads")
        auth_layout.addWidget(self.org_headless_cb)
        layout.addWidget(auth_row)

        layout.addSpacing(8)

        # ── Progress ─────────────────────────────────────────────────────────
        prog_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("")
        self.status_label.setProperty("role", "status")
        prog_row.addWidget(self.progress_bar)
        prog_row.addWidget(self.status_label)
        layout.addLayout(prog_row)

        self.magazine_progress_panel = QWidget()
        self.magazine_progress_layout = QVBoxLayout(self.magazine_progress_panel)
        self.magazine_progress_layout.setContentsMargins(0, 0, 0, 0)
        self.magazine_progress_layout.setSpacing(3)
        self.magazine_progress_panel.setVisible(False)
        layout.addWidget(self.magazine_progress_panel)

        # ── Log ──────────────────────────────────────────────────────────────
        log_toolbar = QHBoxLayout()
        log_toolbar.setSpacing(6)
        self.log_filter = QLineEdit()
        self.log_filter.setPlaceholderText("Filter log…")
        self.log_filter.setAccessibleName("Log filter")
        self.log_filter.textChanged.connect(self._refresh_log)
        self.error_badge = QLabel("0 errors")
        self.error_badge.setProperty("role", "status")
        self.error_badge.setAccessibleName("Log error count")
        self.copy_errors_btn = QPushButton("Copy Errors")
        self.copy_errors_btn.setAccessibleName("Copy log errors")
        self.copy_errors_btn.clicked.connect(self._copy_errors)
        log_toolbar.addWidget(self.log_filter, 1)
        log_toolbar.addWidget(self.error_badge)
        log_toolbar.addWidget(self.copy_errors_btn)
        layout.addLayout(log_toolbar)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Activity log")
        self.log.setMinimumHeight(90)
        layout.addWidget(self.log)

        self.cookie_edit.textChanged.connect(self._save_settings)
        self.org_headless_cb.stateChanged.connect(self._save_settings)

    def _switch_mode(self, mode: str):
        self._dl_panel.setVisible(mode == "download")
        self._org_panel.setVisible(mode == "organize")

    def _make_download_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Magazines ────────────────────────────────────────────────────────
        mag_lbl = QLabel("MAGAZINES")
        mag_lbl.setProperty("role", "section")
        layout.addWidget(mag_lbl)
        self.magazine_grid = QGridLayout()
        self.magazine_grid.setHorizontalSpacing(6)
        self.magazine_grid.setVerticalSpacing(6)
        self.mag_chips: dict[str, QPushButton] = {}
        for index, name in enumerate(MAGAZINES):
            btn = QPushButton(name)
            btn.setProperty("role", "chip")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setAccessibleName(f"Select {name} magazine")
            btn.toggled.connect(self._save_settings)
            self.mag_chips[name] = btn
            row, column = divmod(index, 3)
            self.magazine_grid.addWidget(btn, row, column)
        for column in range(3):
            self.magazine_grid.setColumnStretch(column, 1)
        layout.addLayout(self.magazine_grid)

        # ── Save location ─────────────────────────────────────────────────────
        save_lbl = QLabel("SAVE LOCATION")
        save_lbl.setProperty("role", "section")
        layout.addWidget(save_lbl)
        save_row = QHBoxLayout()
        save_row.setSpacing(6)
        self.dir_edit = QLineEdit(str(Path.home() / "Downloads" / "TrainsMagazines"))
        self.dir_edit.setAccessibleName("Save location folder")
        save_lbl.setBuddy(self.dir_edit)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.setAccessibleName("Browse for save location")
        browse_btn.clicked.connect(self._browse_dir)
        save_row.addWidget(self.dir_edit)
        save_row.addWidget(browse_btn)
        layout.addLayout(save_row)

        # ── Options ───────────────────────────────────────────────────────────
        opts_lbl = QLabel("OPTIONS")
        opts_lbl.setProperty("role", "section")
        layout.addWidget(opts_lbl)
        opts_row = QHBoxLayout()
        opts_row.setSpacing(16)
        self.headless_cb = QCheckBox("Hide download browser")
        self.headless_cb.setAccessibleName("Hide download browser")
        self.headless_cb.setToolTip(
            "Run without a visible browser window.\nRequires a valid saved cookie file."
        )
        self.test_cb = QCheckBox("Test mode")
        self.test_cb.setAccessibleName("Test mode")
        self.specials_cb = QCheckBox("Special issues")
        self.specials_cb.setChecked(True)
        self.specials_cb.setAccessibleName("Include special issues")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Newest first", "Oldest first"])
        self.sort_combo.setFixedWidth(130)
        self.sort_combo.setAccessibleName("Issue order")
        for widget in (self.headless_cb, self.test_cb, self.specials_cb):
            opts_row.addWidget(widget)
        opts_row.addWidget(self.sort_combo)
        opts_row.addStretch()
        layout.addLayout(opts_row)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.start_btn = QPushButton("Start Download")
        self.start_btn.setProperty("role", "primary")
        self.start_btn.setAccessibleName("Start download")
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setProperty("role", "danger")
        self.stop_btn.setAccessibleName("Stop download")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        self._clear_btn = QPushButton("Clear Cache")
        self._clear_btn.setAccessibleName("Clear download cache")
        self._clear_btn.clicked.connect(self._clear_progress)
        btn_row.addWidget(self.start_btn, 2)
        btn_row.addWidget(self.stop_btn, 1)
        btn_row.addWidget(self._clear_btn, 1)
        layout.addLayout(btn_row)

        layout.addStretch()

        self.dir_edit.textChanged.connect(self._save_settings)
        self.headless_cb.stateChanged.connect(self._save_settings)
        self.test_cb.stateChanged.connect(self._save_settings)
        self.specials_cb.stateChanged.connect(self._save_settings)
        self.sort_combo.currentIndexChanged.connect(self._save_settings)

        return w

    def _make_track_plans_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(12)
        layout.addWidget(self._make_page_heading(
            "Download track plans",
            "Download the available Model Railroader Track Plan Database PDFs. "
            "A large collection can take a while; you can stop and resume later.",
        ))

        self.track_plans_folder_edit = QLineEdit(
            str(Path.home() / "Downloads" / "TrainsTrackPlans")
        )
        self.track_plans_folder_edit.setAccessibleName("Track plans save folder")
        folder_card = self._make_path_card(
            "Track plans folder",
            "PDFs are saved here with their original filenames, separate from magazines.",
            self.track_plans_folder_edit,
            lambda: self._pick_dir(self.track_plans_folder_edit),
        )
        self.track_plans_browse_btn = folder_card.findChild(QPushButton)
        layout.addWidget(folder_card)

        access_note = QLabel(
            "Uses the shared trains.com cookie file above. If it needs a fresh sign-in, "
            "the browser will open and save the updated cookies for both download tabs."
        )
        access_note.setProperty("role", "muted")
        access_note.setWordWrap(True)
        layout.addWidget(access_note)

        self.track_plans_validation = QLabel("")
        self.track_plans_validation.setProperty("role", "status")
        self.track_plans_validation.setWordWrap(True)
        layout.addWidget(self.track_plans_validation)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.track_plans_start_btn = QPushButton("Download all track plans")
        self.track_plans_start_btn.setProperty("role", "primary")
        self.track_plans_start_btn.setAccessibleName("Download all track plans")
        self.track_plans_start_btn.clicked.connect(self._start_track_plan_download)
        self.track_plans_stop_btn = QPushButton("Stop")
        self.track_plans_stop_btn.setProperty("role", "danger")
        self.track_plans_stop_btn.setAccessibleName("Stop track plan download")
        self.track_plans_stop_btn.setEnabled(False)
        self.track_plans_stop_btn.clicked.connect(self._stop_track_plan_download)
        actions.addWidget(self.track_plans_start_btn, 2)
        actions.addWidget(self.track_plans_stop_btn, 1)
        layout.addLayout(actions)
        layout.addStretch()

        self.track_plans_folder_edit.textChanged.connect(self._save_settings)
        self._track_plans_config_controls = [
            self.track_plans_folder_edit,
            self.track_plans_browse_btn,
            self.track_plans_start_btn,
        ]
        return content

    def _make_organize_panel(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # ── Source ───────────────────────────────────────────────────────────
        src_lbl = QLabel("SOURCE FOLDER")
        src_lbl.setProperty("role", "section")
        layout.addWidget(src_lbl)
        src_row = QHBoxLayout()
        src_row.setSpacing(6)
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Folder containing PDFs to organize…")
        self.src_edit.setAccessibleName("Source folder")
        src_lbl.setBuddy(self.src_edit)
        src_browse = QPushButton("Browse…")
        src_browse.setFixedWidth(80)
        src_browse.setAccessibleName("Browse for source folder")
        src_browse.clicked.connect(lambda: self._pick_dir(self.src_edit))
        src_row.addWidget(self.src_edit)
        src_row.addWidget(src_browse)
        layout.addLayout(src_row)

        # ── Destination ──────────────────────────────────────────────────────
        dst_lbl = QLabel("DESTINATION FOLDER")
        dst_lbl.setProperty("role", "section")
        layout.addWidget(dst_lbl)
        dst_row = QHBoxLayout()
        dst_row.setSpacing(6)
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText("Organized output folder (can be same as source)…")
        self.dst_edit.setAccessibleName("Destination folder")
        dst_lbl.setBuddy(self.dst_edit)
        dst_browse = QPushButton("Browse…")
        dst_browse.setFixedWidth(80)
        dst_browse.setAccessibleName("Browse for destination folder")
        dst_browse.clicked.connect(lambda: self._pick_dir(self.dst_edit))
        dst_row.addWidget(self.dst_edit)
        dst_row.addWidget(dst_browse)
        layout.addLayout(dst_row)

        # ── Prefix ───────────────────────────────────────────────────────────
        pfx_lbl = QLabel("MAGAZINE PREFIX")
        pfx_lbl.setProperty("role", "section")
        layout.addWidget(pfx_lbl)
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItem("Auto-detect")
        for info in MAGAZINES.values():
            self.prefix_combo.addItem(info["prefix"])
        self.prefix_combo.setFixedWidth(140)
        self.prefix_combo.setToolTip("Force a specific magazine prefix when auto-detect fails")
        self.prefix_combo.setAccessibleName("Magazine prefix")
        layout.addWidget(self.prefix_combo)

        # ── Actions ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.org_btn = QPushButton("Organize PDFs")
        self.org_btn.setProperty("role", "primary")
        self.org_btn.setAccessibleName("Organize PDFs")
        self.org_btn.clicked.connect(self._run_organize)
        self.dl_missing_btn = QPushButton("Download Missing")
        self.dl_missing_btn.setAccessibleName("Download missing issues")
        self.dl_missing_btn.setEnabled(False)
        self.dl_missing_btn.clicked.connect(self._start_missing_download)
        self.dl_missing_stop_btn = QPushButton("Stop")
        self.dl_missing_stop_btn.setProperty("role", "danger")
        self.dl_missing_stop_btn.setAccessibleName("Stop missing-issue download")
        self.dl_missing_stop_btn.setEnabled(False)
        self.dl_missing_stop_btn.clicked.connect(self._stop_missing_download)
        btn_row.addWidget(self.org_btn, 2)
        btn_row.addWidget(self.dl_missing_btn, 2)
        btn_row.addWidget(self.dl_missing_stop_btn, 1)
        layout.addLayout(btn_row)

        layout.addStretch()

        self.src_edit.textChanged.connect(self._save_settings)
        self.dst_edit.textChanged.connect(self._save_settings)
        self.prefix_combo.currentIndexChanged.connect(self._save_settings)

        return w

    # -- Archive workstation shell ------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(_STYLESHEET)
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)
        outer.addWidget(self._make_header())

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self._make_navigation(), 0)

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(12)
        workspace_layout.addWidget(self._make_archive_access(), 0)

        self._page_stack = QStackedWidget()
        self._download_page = self._make_download_page()
        self._track_plans_page = self._make_track_plans_page()
        self._organize_page = self._make_organize_page()
        self._page_stack.addWidget(self._download_page)
        self._page_stack.addWidget(self._track_plans_page)
        self._page_stack.addWidget(self._organize_page)
        workspace_layout.addWidget(self._page_stack, 1)
        body_widget = QWidget()
        body_widget.setLayout(body)
        body.addWidget(workspace, 1)

        self._activity_panel = self._make_activity_panel()
        self._activity_splitter = QSplitter(Qt.Vertical)
        self._activity_splitter.addWidget(body_widget)
        self._activity_splitter.addWidget(self._activity_panel)
        self._activity_splitter.setStretchFactor(0, 1)
        self._activity_splitter.setStretchFactor(1, 0)
        self._activity_splitter.setSizes([520, 190])
        outer.addWidget(self._activity_splitter, 1)

        self.cookie_edit.textChanged.connect(self._save_settings)
        self._set_mode("download")

    def _make_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("app_header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        mark = QLabel("TA")
        mark.setObjectName("brand_mark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(44, 44)
        layout.addWidget(mark)
        title_column = QVBoxLayout()
        title_column.setSpacing(1)
        title = QLabel("Trains.com Archive")
        title.setProperty("role", "app-title")
        subtitle = QLabel("Magazine and track plan downloader with PDF organizer")
        subtitle.setProperty("role", "app-subtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)
        layout.addLayout(title_column)
        layout.addStretch()
        self._header_status = QLabel("Ready")
        self._header_status.setObjectName("header_status")
        self._header_status.setAccessibleName("Job status: Ready")
        self._header_status.setProperty("state", "ready")
        layout.addWidget(self._header_status)
        version = QLabel(f"v{APP_VERSION}")
        version.setProperty("role", "muted")
        layout.addWidget(version)
        return header

    def _make_navigation(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("nav_rail")
        rail.setFixedWidth(176)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(8)
        heading = QLabel("WORKSPACE")
        heading.setObjectName("nav_heading")
        layout.addWidget(heading)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._download_nav_btn = QToolButton()
        self._track_plans_nav_btn = QToolButton()
        self._organize_nav_btn = QToolButton()
        for button, text, name in (
            (self._download_nav_btn, "Download", "Download workflow"),
            (self._track_plans_nav_btn, "Track Plans", "Track plan download workflow"),
            (self._organize_nav_btn, "Organize", "Organize workflow"),
        ):
            button.setObjectName("nav_button")
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setCheckable(True)
            button.setAccessibleName(name)
            self._nav_group.addButton(button)
            layout.addWidget(button)
        self._download_nav_btn.clicked.connect(lambda: self._set_mode("download"))
        self._track_plans_nav_btn.clicked.connect(
            lambda: self._set_mode("track_plans")
        )
        self._organize_nav_btn.clicked.connect(lambda: self._set_mode("organize"))
        # Compatibility aliases for integrations and older UI smoke checks.
        self._dl_mode_btn = self._download_nav_btn
        self._org_mode_btn = self._organize_nav_btn
        layout.addStretch()
        self._activity_nav_btn = QToolButton()
        self._activity_nav_btn.setObjectName("nav_button")
        self._activity_nav_btn.setText("Activity")
        self._activity_nav_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._activity_nav_btn.setCheckable(True)
        self._activity_nav_btn.setAccessibleName("Toggle activity panel")
        self._activity_nav_btn.clicked.connect(self._toggle_activity)
        layout.addWidget(self._activity_nav_btn)
        return rail

    def _make_archive_access(self) -> QWidget:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        title = QLabel("Archive access")
        title.setProperty("role", "card-title")
        layout.addWidget(title)
        note = QLabel(
            "An active trains.com subscription is required. Use a saved cookie file and leave the browser visible the first time you sign in."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.setSpacing(8)
        label = QLabel("Cookie file")
        label.setProperty("role", "eyebrow")
        self.cookie_edit = QLineEdit(DEFAULT_COOKIES_FILE)
        self.cookie_edit.setAccessibleName("Cookie file path")
        label.setBuddy(self.cookie_edit)
        browse = QPushButton("Browse…")
        browse.setAccessibleName("Browse for cookie file")
        browse.clicked.connect(self._browse_cookies)
        row.addWidget(label)
        row.addWidget(self.cookie_edit, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        return card

    @staticmethod
    def _wrap_page(content: QWidget, object_name: str) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName(object_name)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        return scroll

    def _make_download_page(self) -> QScrollArea:
        return self._wrap_page(self._make_download_panel(), "download_scroll")

    def _make_track_plans_page(self) -> QScrollArea:
        return self._wrap_page(
            self._make_track_plans_panel(), "track_plans_scroll"
        )

    def _make_organize_page(self) -> QScrollArea:
        return self._wrap_page(self._make_organize_panel(), "organize_scroll")

    def _make_activity_panel(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("role", "card")
        panel.setMinimumHeight(160)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(7)
        toolbar = QHBoxLayout()
        heading = QLabel("Activity")
        heading.setProperty("role", "card-title")
        toolbar.addWidget(heading)
        self.status_label = QLabel("Ready")
        self.status_label.setProperty("role", "status")
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()
        self.log_filter = QLineEdit()
        self.log_filter.setPlaceholderText("Filter activity…")
        self.log_filter.setAccessibleName("Activity filter")
        self.log_filter.textChanged.connect(self._refresh_log)
        self.error_badge = QLabel("0 errors")
        self.error_badge.setProperty("role", "status")
        self.error_badge.setAccessibleName("Activity error count")
        self.copy_errors_btn = QPushButton("Copy errors")
        self.copy_errors_btn.setAccessibleName("Copy activity errors")
        self.copy_errors_btn.clicked.connect(self._copy_errors)
        clear_btn = QPushButton("Clear")
        clear_btn.setAccessibleName("Clear activity log")
        clear_btn.clicked.connect(self._clear_log)
        toolbar.addWidget(self.log_filter, 1)
        toolbar.addWidget(self.error_badge)
        toolbar.addWidget(self.copy_errors_btn)
        toolbar.addWidget(clear_btn)
        layout.addLayout(toolbar)

        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label.setMinimumWidth(170)
        progress_row.addWidget(self.progress_bar, 1)
        self.magazine_progress_panel = QWidget()
        self.magazine_progress_layout = QVBoxLayout(self.magazine_progress_panel)
        self.magazine_progress_layout.setContentsMargins(0, 0, 0, 0)
        self.magazine_progress_layout.setSpacing(3)
        self.magazine_progress_panel.setVisible(False)
        progress_row.addWidget(self.magazine_progress_panel, 1)
        layout.addLayout(progress_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Activity log")
        self.log.setMinimumHeight(72)
        layout.addWidget(self.log, 1)
        return panel

    def _set_mode(self, mode: str):
        index = {"download": 0, "track_plans": 1, "organize": 2}.get(mode, 0)
        self._page_stack.setCurrentIndex(index)
        self._download_nav_btn.setChecked(index == 0)
        self._track_plans_nav_btn.setChecked(index == 1)
        self._organize_nav_btn.setChecked(index == 2)
        self._active_mode = mode
        scroll = self._page_stack.currentWidget()
        if isinstance(scroll, QScrollArea):
            scroll.verticalScrollBar().setValue(0)

    def _switch_mode(self, mode: str):
        self._set_mode(mode)

    def _toggle_activity(self):
        expanded = not getattr(self, "_activity_expanded", False)
        self._activity_expanded = expanded
        self._activity_nav_btn.setChecked(expanded)
        total = max(self.height() - 170, 420)
        self._activity_splitter.setSizes(
            [max(260, total - (330 if expanded else 190)), 330 if expanded else 190]
        )

    def _set_job_state(self, state: str, detail: str = "") -> None:
        labels = {
            "ready": "Ready",
            "running": "Running",
            "success": "Complete",
            "failed": "Failed",
            "cancelled": "Cancelled",
            "empty": "No results",
        }
        text = labels.get(state, "Ready")
        if detail:
            text = f"{text} · {detail}"
        self._header_status.setText(text)
        self._header_status.setAccessibleName(f"Job status: {state} — {text}")
        self.status_label.setText(text)
        self._header_status.setProperty("state", state)
        self._header_status.style().unpolish(self._header_status)
        self._header_status.style().polish(self._header_status)

    def _sync_busy_controls(self, busy: bool) -> None:
        for control in (
            *getattr(self, "_download_config_controls", []),
            *getattr(self, "_track_plans_config_controls", []),
            *getattr(self, "_org_config_controls", []),
        ):
            control.setEnabled(not busy)

    @staticmethod
    def _make_page_heading(title_text: str, description: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 2, 4, 6)
        layout.setSpacing(3)
        title = QLabel(title_text)
        title.setProperty("role", "page-title")
        subtitle = QLabel(description)
        subtitle.setProperty("role", "page-description")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return widget

    @staticmethod
    def _make_card_title(title_text: str, description: str = "") -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        title = QLabel(title_text)
        title.setProperty("role", "card-title")
        layout.addWidget(title)
        if description:
            subtitle = QLabel(description)
            subtitle.setProperty("role", "muted")
            subtitle.setWordWrap(True)
            layout.addWidget(subtitle)
        return widget

    def _make_path_card(
        self,
        label_text: str,
        helper_text: str,
        target: QLineEdit,
        browse_slot,
    ) -> QFrame:
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(7)
        layout.addWidget(self._make_card_title(label_text, helper_text))
        row = QHBoxLayout()
        row.setSpacing(8)
        browse = QPushButton("Browse…")
        browse.setAccessibleName(f"Browse for {label_text.lower()}")
        browse.clicked.connect(browse_slot)
        row.addWidget(target, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        return card

    def _make_magazine_row(self, name: str) -> QFrame:
        row = QFrame()
        row.setObjectName("magazine_row")
        row.setProperty("role", "card")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 7, 12, 7)
        row_layout.setSpacing(12)
        checkbox = QCheckBox(name)
        checkbox.setChecked(True)
        checkbox.setAccessibleName(f"Select {name} magazine")
        checkbox.setToolTip(f"Include {name} in the archive download")
        checkbox.toggled.connect(self._save_settings)
        self.mag_chips[name] = checkbox
        row_layout.addWidget(checkbox, 1)
        prefix = QLabel(MAGAZINES[name]["prefix"])
        prefix.setObjectName("magazine_prefix")
        prefix.setAlignment(Qt.AlignCenter)
        prefix.setMinimumWidth(42)
        schedule = QLabel(MAGAZINE_SCHEDULE[name])
        schedule.setProperty("role", "muted")
        schedule.setMinimumWidth(126)
        schedule.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row_layout.addWidget(prefix)
        row_layout.addWidget(schedule)
        return row

    def _select_all_magazines(self):
        for checkbox in self.mag_chips.values():
            checkbox.setChecked(True)

    def _clear_all_magazines(self):
        for checkbox in self.mag_chips.values():
            checkbox.setChecked(False)

    def _toggle_advanced_options(self, expanded: bool):
        self._advanced_options_body.setVisible(expanded)
        self._advanced_options_toggle.setText(
            "Advanced options  ▾" if expanded else "Advanced options  ▸"
        )

    def _make_download_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(12)
        layout.addWidget(self._make_page_heading(
            "Download magazines",
            "Choose the publications and archive options to save locally.",
        ))

        selection = QFrame()
        selection.setProperty("role", "card")
        selection_layout = QVBoxLayout(selection)
        selection_layout.setContentsMargins(16, 13, 16, 13)
        selection_layout.setSpacing(7)
        selection_header = QHBoxLayout()
        selection_header.addWidget(self._make_card_title(
            "Publications",
            "Select one or more magazines. Each archive is saved under its prefix.",
        ), 1)
        self.select_all_btn = QPushButton("Select all")
        self.select_all_btn.setAccessibleName("Select all magazines")
        self.select_all_btn.clicked.connect(self._select_all_magazines)
        self.clear_all_btn = QPushButton("Clear all")
        self.clear_all_btn.setAccessibleName("Clear all magazines")
        self.clear_all_btn.clicked.connect(self._clear_all_magazines)
        selection_header.addWidget(self.select_all_btn)
        selection_header.addWidget(self.clear_all_btn)
        selection_layout.addLayout(selection_header)
        self.mag_chips = {}
        self.magazine_rows = {}
        for name in MAGAZINES:
            row = self._make_magazine_row(name)
            self.magazine_rows[name] = row
            selection_layout.addWidget(row)
        layout.addWidget(selection)

        self.dir_edit = QLineEdit(str(Path.home() / "Downloads" / "TrainsMagazines"))
        self.dir_edit.setAccessibleName("Save location folder")
        self.dir_edit.setPlaceholderText("Choose a folder for downloaded magazines")
        layout.addWidget(self._make_path_card(
            "Save location",
            "PDFs are organized into magazine and year folders after download.",
            self.dir_edit,
            self._browse_dir,
        ))

        advanced = QFrame()
        advanced.setProperty("role", "card")
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(16, 10, 16, 12)
        advanced_layout.setSpacing(6)
        self._advanced_options_toggle = QToolButton()
        self._advanced_options_toggle.setText("Advanced options  ▾")
        self._advanced_options_toggle.setCheckable(True)
        self._advanced_options_toggle.setChecked(True)
        self._advanced_options_toggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._advanced_options_toggle.setAccessibleName("Toggle advanced download options")
        self._advanced_options_toggle.toggled.connect(self._toggle_advanced_options)
        advanced_layout.addWidget(self._advanced_options_toggle)
        self._advanced_options_body = QWidget()
        options_layout = QVBoxLayout(self._advanced_options_body)
        options_layout.setContentsMargins(0, 2, 0, 0)
        options_layout.setSpacing(2)
        self.specials_cb = QCheckBox("Include special issues")
        self.specials_cb.setChecked(True)
        self.specials_cb.setAccessibleName("Include special issues")
        self.test_cb = QCheckBox("Test mode: scan only the first few archive pages")
        self.test_cb.setAccessibleName("Test mode")
        self.headless_cb = QCheckBox("Hide download browser")
        self.headless_cb.setAccessibleName("Hide download browser")
        self.headless_cb.setToolTip("Requires a valid saved cookie file.")
        for checkbox in (self.specials_cb, self.test_cb, self.headless_cb):
            checkbox.stateChanged.connect(self._save_settings)
            options_layout.addWidget(checkbox)
        order_row = QHBoxLayout()
        order_label = QLabel("Issue order")
        order_label.setProperty("role", "muted")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Newest first", "Oldest first"])
        self.sort_combo.setAccessibleName("Issue order")
        self.sort_combo.setMinimumWidth(150)
        self.sort_combo.currentIndexChanged.connect(self._save_settings)
        order_row.addWidget(order_label)
        order_row.addWidget(self.sort_combo)
        order_row.addStretch()
        options_layout.addLayout(order_row)
        advanced_layout.addWidget(self._advanced_options_body)
        layout.addWidget(advanced)

        self.download_validation = QLabel("")
        self.download_validation.setProperty("role", "status")
        self.download_validation.setAccessibleName("Download validation message")
        self.download_validation.setWordWrap(True)
        layout.addWidget(self.download_validation)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.start_btn = QPushButton("Start download")
        self.start_btn.setProperty("role", "primary")
        self.start_btn.setAccessibleName("Start download")
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setProperty("role", "danger")
        self.stop_btn.setAccessibleName("Stop download")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        self._clear_btn = QPushButton("Clear cache")
        self._clear_btn.setAccessibleName("Clear download cache")
        self._clear_btn.clicked.connect(self._clear_progress)
        actions.addWidget(self.start_btn, 2)
        actions.addWidget(self.stop_btn, 1)
        actions.addWidget(self._clear_btn, 1)
        layout.addLayout(actions)
        self.dir_edit.textChanged.connect(self._save_settings)
        self._download_config_controls = [
            *self.mag_chips.values(),
            self.select_all_btn,
            self.clear_all_btn,
            self.dir_edit,
            self._advanced_options_toggle,
            self.specials_cb,
            self.test_cb,
            self.headless_cb,
            self.sort_combo,
            self._clear_btn,
        ]
        return content

    def _make_organize_panel(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(12)
        layout.addWidget(self._make_page_heading(
            "Organize your PDFs",
            "Rename, sort, validate, and report on an existing PDF folder.",
        ))

        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Folder containing PDFs to organize")
        self.src_edit.setAccessibleName("Source folder")
        layout.addWidget(self._make_path_card(
            "Source folder",
            "Choose the folder that contains the PDFs you want to inspect.",
            self.src_edit,
            lambda: self._pick_dir(self.src_edit),
        ))

        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText("Organized output folder")
        self.dst_edit.setAccessibleName("Destination folder")
        layout.addWidget(self._make_path_card(
            "Destination folder",
            "The destination may be the same as the source folder.",
            self.dst_edit,
            lambda: self._pick_dir(self.dst_edit),
        ))

        identification = QFrame()
        identification.setProperty("role", "card")
        identification_layout = QVBoxLayout(identification)
        identification_layout.setContentsMargins(16, 13, 16, 13)
        identification_layout.setSpacing(6)
        identification_layout.addWidget(self._make_card_title(
            "Magazine identification",
            "Use Auto-detect unless filenames do not identify the publication.",
        ))
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItem("Auto-detect")
        for info in MAGAZINES.values():
            self.prefix_combo.addItem(info["prefix"])
        self.prefix_combo.setAccessibleName("Magazine prefix")
        self.prefix_combo.setMinimumWidth(180)
        identification_layout.addWidget(self.prefix_combo)
        layout.addWidget(identification)

        browser_options = QFrame()
        browser_options.setProperty("role", "card")
        browser_options_layout = QVBoxLayout(browser_options)
        browser_options_layout.setContentsMargins(16, 12, 16, 12)
        browser_options_layout.setSpacing(5)
        browser_options_layout.addWidget(self._make_card_title(
            "Missing-issue browser",
            "Keep the browser visible while signing in; hide it only after the cookie file is saved.",
        ))
        self.org_headless_cb = QCheckBox("Hide browser for missing-issue downloads")
        self.org_headless_cb.setAccessibleName("Hide browser for missing-issue downloads")
        self.org_headless_cb.stateChanged.connect(self._save_settings)
        browser_options_layout.addWidget(self.org_headless_cb)
        layout.addWidget(browser_options)

        self._organize_summary = QFrame()
        self._organize_summary.setProperty("role", "card")
        self._organize_summary.setVisible(False)
        summary_layout = QVBoxLayout(self._organize_summary)
        summary_layout.setContentsMargins(16, 13, 16, 13)
        summary_layout.setSpacing(8)
        summary_layout.addWidget(self._make_card_title(
            "Organization results",
            "Review the counts before downloading any missing issues.",
        ))
        tile_grid = QGridLayout()
        tile_grid.setHorizontalSpacing(8)
        tile_grid.setVerticalSpacing(8)
        self._organize_summary_tiles = {}
        tile_labels = (
            "Moved", "Already correct", "Unrecognized",
            "Corrupt", "Conflicts", "Metadata updated",
        )
        for index, label_text in enumerate(tile_labels):
            tile = QFrame()
            tile.setProperty("role", "card")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(10, 8, 10, 8)
            value = QLabel("0")
            value.setObjectName("summary_value")
            value.setAlignment(Qt.AlignCenter)
            caption = QLabel(label_text)
            caption.setProperty("role", "muted")
            caption.setAlignment(Qt.AlignCenter)
            tile_layout.addWidget(value)
            tile_layout.addWidget(caption)
            self._organize_summary_tiles[label_text] = value
            tile_grid.addWidget(tile, index // 3, index % 3)
        summary_layout.addLayout(tile_grid)
        self._missing_summary = QLabel("No downloadable missing issues identified.")
        self._missing_summary.setProperty("role", "status")
        self._missing_summary.setWordWrap(True)
        summary_layout.addWidget(self._missing_summary)
        layout.addWidget(self._organize_summary)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.org_btn = QPushButton("Organize PDFs")
        self.org_btn.setProperty("role", "primary")
        self.org_btn.setAccessibleName("Organize PDFs")
        self.org_btn.clicked.connect(self._run_organize)
        self.dl_missing_btn = QPushButton("Download missing issues")
        self.dl_missing_btn.setAccessibleName("Download missing issues")
        self.dl_missing_btn.setEnabled(False)
        self.dl_missing_btn.clicked.connect(self._start_missing_download)
        self.dl_missing_stop_btn = QPushButton("Stop")
        self.dl_missing_stop_btn.setProperty("role", "danger")
        self.dl_missing_stop_btn.setAccessibleName("Stop missing-issue download")
        self.dl_missing_stop_btn.setEnabled(False)
        self.dl_missing_stop_btn.clicked.connect(self._stop_missing_download)
        actions.addWidget(self.org_btn, 2)
        actions.addWidget(self.dl_missing_btn, 2)
        actions.addWidget(self.dl_missing_stop_btn, 1)
        layout.addLayout(actions)

        self.src_edit.textChanged.connect(self._save_settings)
        self.dst_edit.textChanged.connect(self._save_settings)
        self.prefix_combo.currentIndexChanged.connect(self._save_settings)
        self._org_config_controls = [
            self.src_edit,
            self.dst_edit,
            self.prefix_combo,
            self.org_headless_cb,
        ]
        return content

    def _render_organize_summary(self, summary: OrganizeSummary) -> None:
        values = {
            "Moved": summary.moved,
            "Already correct": summary.already_correct,
            "Unrecognized": summary.unrecognized,
            "Corrupt": summary.corrupt,
            "Conflicts": summary.conflicts,
            "Metadata updated": summary.metadata_stamped,
        }
        for label, value in values.items():
            self._organize_summary_tiles[label].setText(str(value))
        self._organize_summary.show()
        self._org_prefix, self._missing_by_year = _missing_download_selection(summary)
        missing_count = sum(len(months) for months in self._missing_by_year.values())
        if missing_count and self._org_prefix:
            self._missing_summary.setText(
                f"{missing_count} missing issue(s) identified for {self._org_prefix}."
            )
            self.dl_missing_btn.setEnabled(True)
        else:
            self._missing_summary.setText("No downloadable missing issues identified.")
            self.dl_missing_btn.setEnabled(False)

    # -- Helpers --------------------------------------------------------------
    @staticmethod
    def _disconnect_worker(worker) -> None:
        """Disconnect all signals from a worker so stale callbacks never fire."""
        if worker is None:
            return
        for attr in ("log", "progress", "magazine_progress", "status_msg", "error", "finished"):
            sig = getattr(worker.signals, attr, None)
            if sig is not None:
                try:
                    sig.disconnect()
                except TypeError:
                    pass  # not connected — harmless

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
            "Cookie files (*.json);;All files (*)"
        )
        if path:
            self.cookie_edit.setText(path)

    def _clear_progress(self):
        removed = []
        for path in (PROGRESS_FILE, SPECIAL_ISSUES_FILE):
            if os.path.exists(path):
                os.remove(path)
                removed.append(os.path.basename(path))
        if removed:
            self._log("Cache cleared: " + ", ".join(removed))
        else:
            self._log("No download cache files found.")

    @staticmethod
    def _colorize(line: str) -> str:
        """Return an HTML-colored version of a log line."""
        esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if MainWindow._is_error_line(line):
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

    @staticmethod
    def _is_error_line(line: str) -> bool:
        upper = line.upper()
        return "FAILED" in upper or "ERROR:" in upper or upper.startswith("ERROR")

    def _update_error_badge(self) -> None:
        count = sum(1 for line in self._raw_log_lines if self._is_error_line(line))
        self.error_badge.setText(f"{count} error" if count == 1 else f"{count} errors")

    def _refresh_log(self) -> None:
        query = self.log_filter.text().strip().lower()
        lines = [
            line for line in self._raw_log_lines
            if not query or query in line.lower()
        ]
        self.log.setHtml("\n".join(self._colorize(line) for line in lines))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _copy_errors(self) -> None:
        errors = [line for line in self._raw_log_lines if self._is_error_line(line)]
        QApplication.clipboard().setText("\n".join(errors))

    def _clear_log(self) -> None:
        self._raw_log_lines.clear()
        self._update_error_badge()
        self._refresh_log()

    def _reset_magazine_progress(self) -> None:
        while self.magazine_progress_layout.count():
            item = self.magazine_progress_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._magazine_progress_rows.clear()
        self.magazine_progress_panel.setVisible(False)

    def _update_magazine_progress(self, name: str, done: int, total: int) -> None:
        row_data = self._magazine_progress_rows.get(name)
        if row_data is None:
            row = QWidget(self.magazine_progress_panel)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)
            label = QLabel(name)
            label.setProperty("role", "muted")
            bar = QProgressBar()
            bar.setAccessibleName(f"{name} download progress")
            count = QLabel("0 / 0")
            count.setProperty("role", "status")
            count.setMinimumWidth(48)
            row_layout.addWidget(label)
            row_layout.addWidget(bar, 1)
            row_layout.addWidget(count)
            self.magazine_progress_layout.addWidget(row)
            row_data = (row, bar, count)
            self._magazine_progress_rows[name] = row_data
        row, bar, count = row_data
        bar.setMaximum(max(1, total))
        bar.setValue(max(0, min(done, total)))
        count.setText(f"{done} / {total}")
        row.setVisible(True)
        self.magazine_progress_panel.setVisible(True)

    def _log(self, msg: str) -> None:
        self._raw_log_lines.append(msg)
        self._update_error_badge()
        self._refresh_log()

    def _start_track_plan_download(self):
        if self._track_plan_worker is not None and self._track_plan_worker.isRunning():
            return
        active_workers = (
            self.worker,
            self._missing_worker,
            self._org_worker,
        )
        if any(worker is not None and worker.isRunning() for worker in active_workers):
            QMessageBox.information(
                self,
                "Task in progress",
                "Wait for the current task to finish before starting a track plan download.",
            )
            return

        destination_dir = self.track_plans_folder_edit.text().strip()
        if not destination_dir:
            self.track_plans_validation.setText("Choose a folder to continue.")
            QMessageBox.warning(
                self, "No folder", "Please choose a track plans folder."
            )
            return
        self.track_plans_validation.clear()
        cookies_path = self.cookie_edit.text().strip() or DEFAULT_COOKIES_FILE

        self.track_plans_start_btn.setEnabled(False)
        self.track_plans_stop_btn.setEnabled(True)
        self.start_btn.setEnabled(False)
        self.org_btn.setEnabled(False)
        self.dl_missing_btn.setEnabled(False)
        self._sync_busy_controls(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setVisible(True)
        self._set_job_state("running", "Track plan database")
        self._tray.setToolTip("Trains Downloader — Track plans starting…")

        self._disconnect_worker(self._track_plan_worker)
        self._track_plan_worker = TrackPlanWorker(
            destination_dir=destination_dir,
            cookies_path=cookies_path,
        )
        self._track_plan_worker.signals.log.connect(self._log)
        self._track_plan_worker.signals.progress.connect(
            self._update_track_plan_progress
        )
        self._track_plan_worker.signals.status_msg.connect(self.status_label.setText)
        self._track_plan_worker.signals.error.connect(self._on_error)
        self._track_plan_worker.signals.finished.connect(
            self._on_track_plans_finished
        )
        self._track_plan_worker.start()

    def _stop_track_plan_download(self):
        if self._track_plan_worker is not None and self._track_plan_worker.isRunning():
            self._track_plan_worker.stop()
            self._log("Track plan stop requested — finishing the current request…")
            self._set_job_state("running", "Stop requested")
        self.track_plans_stop_btn.setEnabled(False)

    def _update_track_plan_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self._tray.setToolTip(
                f"Trains Downloader — {current} / {total} track plans…"
            )

    def _on_track_plans_finished(self):
        self.track_plans_start_btn.setEnabled(True)
        self.track_plans_stop_btn.setEnabled(False)
        self.start_btn.setEnabled(True)
        self.org_btn.setEnabled(True)
        has_missing = bool(self._missing_by_year) and self._org_prefix and \
                      _archive_url_for_prefix(self._org_prefix) is not None
        self.dl_missing_btn.setEnabled(has_missing)
        self._sync_busy_controls(False)
        self.progress_bar.setVisible(False)

        outcome = getattr(self._track_plan_worker, "outcome", OUTCOME_FAILED)
        label = {
            OUTCOME_SUCCESS: "Track plans complete",
            OUTCOME_CANCELLED: "Track plan download cancelled",
            OUTCOME_NO_RESULTS: "No track plans found",
            OUTCOME_FAILED: "Track plan download failed",
        }.get(outcome, "Track plan download failed")
        state = {
            OUTCOME_SUCCESS: "success",
            OUTCOME_CANCELLED: "cancelled",
            OUTCOME_NO_RESULTS: "empty",
            OUTCOME_FAILED: "failed",
        }.get(outcome, "failed")
        self._log(f"--- {label} ---")
        self._set_job_state(state, label)
        self._tray.setToolTip("Trains Downloader — Idle")

    def _start_download(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self._track_plan_worker is not None and self._track_plan_worker.isRunning():
            return

        magazines = [n for n, btn in self.mag_chips.items() if btn.isChecked()]
        if not magazines:
            self.download_validation.setText("Select at least one magazine to continue.")
            QMessageBox.warning(self, "Nothing selected", "Select at least one magazine.")
            return

        base_dir = self.dir_edit.text().strip()
        if not base_dir:
            self.download_validation.setText("Choose a save location to continue.")
            QMessageBox.warning(self, "No folder", "Please choose a save location.")
            return
        self.download_validation.clear()

        cookies  = self.cookie_edit.text().strip() or None
        headless = self.headless_cb.isChecked()
        test     = self.test_cb.isChecked()
        newest   = self.sort_combo.currentText() == "Newest first"
        specials = self.specials_cb.isChecked()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._sync_busy_controls(True)
        self._reset_magazine_progress()
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(1)
        self.progress_bar.setVisible(True)
        self._set_job_state("running", "Starting…")

        self._disconnect_worker(self.worker)
        self.worker = DownloadWorker(magazines, base_dir, headless, test, cookies, newest,
                                     include_specials=specials)
        self.worker.signals.log.connect(self._log)
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.magazine_progress.connect(self._update_magazine_progress)
        self.worker.signals.status_msg.connect(self.status_label.setText)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_download(self):
        if self.worker:
            self.worker.stop()
            self._log("Stop requested — waiting for current issue to finish…")
            self._set_job_state("running", "Stop requested")
        self.stop_btn.setEnabled(False)

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
            self._set_job_state("running", f"{current} / {total} issues")
            self._tray.setToolTip(f"Trains Downloader — {current} / {total} downloading…")

    def _on_error(self, msg: str):
        self._log(f"ERROR: {msg}")
        self._set_job_state("failed", msg)
        QMessageBox.critical(self, "Error", msg)

    def _on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._sync_busy_controls(False)
        self.progress_bar.setVisible(False)
        self.magazine_progress_panel.setVisible(False)
        outcome = getattr(self.worker, "outcome", OUTCOME_FAILED)
        label = {
            OUTCOME_SUCCESS: "Done",
            OUTCOME_CANCELLED: "Cancelled",
            OUTCOME_NO_RESULTS: "No issues found",
            OUTCOME_FAILED: "Failed",
        }.get(outcome, "Failed")
        self._log(f"--- {label} ---")
        state = {
            OUTCOME_SUCCESS: "success",
            OUTCOME_CANCELLED: "cancelled",
            OUTCOME_NO_RESULTS: "empty",
            OUTCOME_FAILED: "failed",
        }.get(outcome, "failed")
        self._set_job_state(state, label)
        self._tray.setToolTip("Trains Downloader — Idle")

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

    def closeEvent(self, event):
        running = (
            (self.worker is not None and self.worker.isRunning())
            or (self._track_plan_worker is not None and self._track_plan_worker.isRunning())
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
            for w in (self.worker, self._track_plan_worker, self._missing_worker):
                if w is not None and w.isRunning():
                    w.stop()
            QApplication.instance().quit()

    def _load_settings(self):
        s = load_settings()
        if "base_dir" in s:
            self.dir_edit.setText(s["base_dir"])
        if "track_plans_dir" in s:
            self.track_plans_folder_edit.setText(s["track_plans_dir"])
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
            for name, btn in self.mag_chips.items():
                btn.setChecked(name in sel)
        if "org_src" in s:
            self.src_edit.setText(s["org_src"])
        if "org_dst" in s:
            self.dst_edit.setText(s["org_dst"])
        if "org_prefix" in s:
            idx = self.prefix_combo.findText(s["org_prefix"])
            if idx >= 0:
                self.prefix_combo.setCurrentIndex(idx)
        if "org_headless" in s:
            self.org_headless_cb.setChecked(s["org_headless"])

    def _save_settings(self):
        save_settings({
            "base_dir":           self.dir_edit.text(),
            "track_plans_dir":    self.track_plans_folder_edit.text(),
            "cookies_path":       self.cookie_edit.text(),
            "headless":           self.headless_cb.isChecked(),
            "test_mode":          self.test_cb.isChecked(),
            "newest_first":       self.sort_combo.currentText() == "Newest first",
            "include_specials":   self.specials_cb.isChecked(),
            "selected_magazines": [n for n, btn in self.mag_chips.items() if btn.isChecked()],
            "org_src":            self.src_edit.text(),
            "org_dst":            self.dst_edit.text(),
            "org_prefix":         self.prefix_combo.currentText(),
            "org_headless":       self.org_headless_cb.isChecked(),
        })

    def _run_organize(self):
        if self._org_worker is not None and self._org_worker.isRunning():
            return
        if self._track_plan_worker is not None and self._track_plan_worker.isRunning():
            return

        src = self.src_edit.text().strip()
        dst = self.dst_edit.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "Missing folders", "Select both source and destination folders.")
            return
        pfx_text = self.prefix_combo.currentText()
        hint = None if pfx_text == "Auto-detect" else pfx_text

        self._clear_log()
        self._reset_magazine_progress()
        self._organize_summary.hide()
        self._missing_summary.setText("Results will appear here after organizing.")
        self._log(f"Organizing PDFs from: {src}")
        self._log(f"                  to: {dst}\n")

        self.org_btn.setEnabled(False)
        self.dl_missing_btn.setEnabled(False)
        self._sync_busy_controls(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._set_job_state("running", "Organizing PDFs")

        self._org_hint = hint
        self._org_dst  = dst
        self._disconnect_worker(self._org_worker)
        self._org_worker = OrganizeWorker(src, dst, hint)
        self._org_worker.signals.log.connect(self._log)
        self._org_worker.signals.progress.connect(self._update_org_progress)
        self._org_worker.signals.error.connect(
            lambda msg: QMessageBox.critical(self, "Organize error", msg)
        )
        self._org_worker.signals.finished.connect(self._on_organize_finished)
        self._org_worker.start()

    def _on_organize_finished(self):
        self.org_btn.setEnabled(True)
        self._sync_busy_controls(False)
        self.progress_bar.setVisible(False)

        if self._org_worker.result is None:
            self._set_job_state("failed", "Organizer did not return a result")
            return
        summary = self._org_worker.result

        self._log(
            f"\n-- {summary.moved} moved, {summary.already_correct} already correct, "
            f"{summary.unrecognized} unrecognized, {summary.corrupt} corrupt, "
            f"{summary.conflicts} conflicts, {summary.metadata_stamped} metadata updated --"
        )
        for line in summary.report:
            self._log(line)

        self._render_organize_summary(summary)
        self._set_job_state("success", "Organization complete")

        has_missing = bool(self._missing_by_year) and self._org_prefix and \
                      _archive_url_for_prefix(self._org_prefix) is not None
        self.dl_missing_btn.setEnabled(has_missing)
        if has_missing:
            total = sum(len(v) for v in self._missing_by_year.values())
            self._log(f"\n{total} missing issue(s) found — click 'Download Missing' to fetch them.")
        elif len(summary.missing_by_prefix_year) > 1 and any(
            any(months for months in by_year.values())
            for by_year in summary.missing_by_prefix_year.values()
        ):
            self._log(
                "\nMultiple publications found; review each report separately before "
                "using Download Missing for one magazine."
            )

    def _start_missing_download(self):
        if self._missing_worker is not None and self._missing_worker.isRunning():
            return
        if self._track_plan_worker is not None and self._track_plan_worker.isRunning():
            return

        dst = self.dst_edit.text().strip()
        if not dst or not self._org_prefix:
            return
        archive_url = _archive_url_for_prefix(self._org_prefix)
        if not archive_url:
            QMessageBox.warning(self, "Unknown magazine",
                                f"No archive URL found for prefix '{self._org_prefix}'.")
            return

        cookies  = self.cookie_edit.text().strip() or DEFAULT_COOKIES_FILE
        headless = self.org_headless_cb.isChecked()

        self.dl_missing_btn.setEnabled(False)
        self.dl_missing_stop_btn.setEnabled(True)
        self._sync_busy_controls(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self._set_job_state("running", "Searching for missing issues")

        self._disconnect_worker(self._missing_worker)
        self._missing_worker = MissingIssuesWorker(
            prefix=self._org_prefix,
            archive_url=archive_url,
            missing_by_year=self._missing_by_year,
            dest_dir=dst,
            cookies_path=cookies,
            headless=headless,
        )
        self._missing_worker.signals.log.connect(self._log)
        self._missing_worker.signals.progress.connect(self._update_org_progress)
        self._missing_worker.signals.error.connect(
            lambda msg: QMessageBox.critical(self, "Error", msg)
        )
        self._missing_worker.signals.finished.connect(self._on_missing_finished)
        self._missing_worker.start()

    def _stop_missing_download(self):
        if self._missing_worker is not None and self._missing_worker.isRunning():
            self._missing_worker.stop()
            self._log("Stop requested…")
            self._set_job_state("running", "Stop requested")
        self.dl_missing_stop_btn.setEnabled(False)

    def _update_org_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def _on_missing_finished(self):
        has_missing = bool(self._missing_by_year) and self._org_prefix and \
                      _archive_url_for_prefix(self._org_prefix) is not None
        self.dl_missing_btn.setEnabled(has_missing)
        self.dl_missing_stop_btn.setEnabled(False)
        self.progress_bar.setVisible(False)
        outcome = getattr(self._missing_worker, "outcome", OUTCOME_FAILED)
        label = {
            OUTCOME_SUCCESS: "Download complete",
            OUTCOME_CANCELLED: "Download cancelled",
            OUTCOME_NO_RESULTS: "No missing issues found",
            OUTCOME_FAILED: "Download failed",
        }.get(outcome, "Download failed")
        self._log(f"--- {label} ---")
        state = {
            OUTCOME_SUCCESS: "success",
            OUTCOME_CANCELLED: "cancelled",
            OUTCOME_NO_RESULTS: "empty",
            OUTCOME_FAILED: "failed",
        }.get(outcome, "failed")
        self._set_job_state(state, label)
        self._sync_busy_controls(False)


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
