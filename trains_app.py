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
from calendar import month_name, month_abbr as _month_abbr
from pathlib import Path
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import pypdf
    from pypdf.generic import DecodedStreamObject, NameObject
    _PYPDF_AVAILABLE = True
except ImportError:
    _PYPDF_AVAILABLE = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QFileDialog, QTextEdit,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QMessageBox,
    QTabWidget, QFrame, QSizePolicy, QMenu, QSystemTrayIcon,
)
from PyQt5.QtCore import pyqtSignal, QObject, QThread
from PyQt5.QtGui import QTextCursor

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
    "subscriptions", "page", "index",
})

DEFAULT_COOKIES_FILE = os.path.join(_BASE_DIR, "session_cookies.json")
PROGRESS_FILE       = os.path.join(_BASE_DIR, "download_progress.json")
SPECIAL_ISSUES_FILE = os.path.join(_BASE_DIR, "special_issues.json")
SETTINGS_FILE       = os.path.join(_BASE_DIR, "settings.json")
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
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
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
APP_VERSION = "1.6.0"
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


def organize_pdfs(source_dir: str, dest_dir: str, hint_prefix: str | None = None, log_fn=None, progress_fn=None):
    """
    Move and rename PDFs from source_dir into dest_dir/YYYY/ subfolders.
    Returns (moved_count, already_correct_count, unrecognized_count, missing_report_lines).
    progress_fn, if provided, is called with (current, total) after each file is processed.
    """
    def _log(msg):
        logger.info(msg)
        if log_fn:
            log_fn(msg)

    # Pre-collect all PDF paths so we can report total progress
    all_pdfs = []
    for root, _, files in os.walk(source_dir):
        for fname in files:
            if fname.lower().endswith(".pdf"):
                all_pdfs.append((root, fname))
    total_pdfs = len(all_pdfs)

    issues_by_year: dict[str, set] = {}
    observed_prefixes: set[str] = set()
    moved = already_correct = unrecognized = metadata_stamped = 0

    for file_idx, (root, fname) in enumerate(all_pdfs):
        fpath = os.path.join(root, fname)
        parsed = parse_pdf_filename(fpath, hint_prefix)
        if not parsed:
            _log(f"  Skipping (unrecognized, no date found in filename or PDF content): {fname}")
            unrecognized += 1
            if progress_fn:
                progress_fn(file_idx + 1, total_pdfs)
            continue
        new_stem, year, mname = parsed
        observed_prefixes.add(new_stem.split("-")[0].upper())
        year_dir = os.path.join(dest_dir, year)
        expected_path = os.path.join(year_dir, new_stem + ".pdf")
        fname_stem = os.path.splitext(fname)[0]
        actual_dir  = os.path.normcase(os.path.abspath(root))
        expected_dir = os.path.normcase(os.path.abspath(year_dir))
        is_duplicate_variant = (
            actual_dir == expected_dir
            and re.fullmatch(re.escape(new_stem) + r"-\d+", fname_stem, re.IGNORECASE)
        )
        if is_duplicate_variant or os.path.normcase(os.path.abspath(fpath)) == os.path.normcase(os.path.abspath(expected_path)):
            if mname:
                issues_by_year.setdefault(year, set()).add(mname)
            else:
                issues_by_year.setdefault(year, set())
            if _stamp_pdf_metadata(fpath, mname, year, warn_fn=_log):
                _log(f"  Metadata updated: {fname}")
                metadata_stamped += 1
            already_correct += 1
            if progress_fn:
                progress_fn(file_idx + 1, total_pdfs)
            continue
        os.makedirs(year_dir, exist_ok=True)
        dest_path = _unique_path(expected_path)
        shutil.move(fpath, dest_path)
        if _stamp_pdf_metadata(dest_path, mname, year, warn_fn=_log):
            metadata_stamped += 1
        _log(f"  {fname}  →  {dest_path}")
        if mname:
            issues_by_year.setdefault(year, set()).add(mname)
        else:
            issues_by_year.setdefault(year, set())
        moved += 1
        if progress_fn:
            progress_fn(file_idx + 1, total_pdfs)

    # Determine expected months from hint_prefix, or from the single observed prefix
    _pfx = hint_prefix or (next(iter(observed_prefixes)) if len(observed_prefixes) == 1 else None)
    expected_months = _detect_issue_frequency(issues_by_year) \
        or (PREFIX_ISSUE_MONTHS.get(_pfx, ALL_MONTHS) if _pfx else ALL_MONTHS)
    today = datetime.date.today()
    report = []
    for year in sorted(issues_by_year):
        yr_int = int(year)
        missing = [
            m for m in expected_months
            if m not in issues_by_year[year]
            and datetime.date(yr_int, MONTH_NUM_FROM_NAME[m], 1) <= today
        ]
        report.append(f"{year}: {'complete' if not missing else 'missing ' + str(missing)}")
    return moved, already_correct, unrecognized, metadata_stamped, report


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
                if page_num == 1:
                    self._log("  No issues found on page 1 -- done.")
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
                return self._fetch_pdf(pdf_url, dest_dir, hint_prefix, cookies, flat=flat)

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
                return self._flipbook_download(issue_url, dest_dir, hint_prefix, flat=flat)

            # ---- Mode 3: no download available (read-only) ------------------
            return False, "No PDF download available (read-only issue)"

        except Exception as e:
            logger.exception(f"Error downloading {issue_url}")
            return False, str(e)

    def _flipbook_download(self, issue_url: str, dest_dir: str,
                           hint_prefix: str | None, flat: bool = False) -> tuple[bool, str]:
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

        return False, "Flipbook download timed out (no file appeared within 90s)"

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

    def stop(self):
        self._stop = True

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
            completed_set = set(progress["completed"])  # O(1) membership checks
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
                links = downloader.collect_all_issue_links(archive_url, max_pages=max_pages)
                if not self.newest_first:   # list is already newest-first from the archive
                    links = list(reversed(links))
                all_tasks.extend([(link, dest_dir, prefix, False, mag_name) for link in links])

                if self.include_specials:
                    specials_url = archive_url + "special-issues/"
                    special_dir  = os.path.join(dest_dir, "Special Issues")
                    self._log(f"  Checking special issues at {specials_url}…")
                    special_links = downloader.collect_all_issue_links(specials_url, max_pages=max_pages)
                    if not self.newest_first:
                        special_links = list(reversed(special_links))
                    if special_links:
                        self._log(f"  Found {len(special_links)} special issue(s).")
                    all_tasks.extend([(link, special_dir, prefix, True, mag_name) for link in special_links])

            total = len(all_tasks)
            self._log(f"\nTotal issues found: {total}")

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

                for issue_url, dest_dir, prefix, flat, mag_name in all_tasks:
                    if self._stop:
                        self._log("Stopped by user.")
                        break

                    if issue_url in completed_set:
                        self._log(f"[skip] {issue_url}")
                        done += 1
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)
                        continue

                    if issue_already_on_disk(issue_url, dest_dir, prefix, flat):
                        self._log(f"[exists] {issue_url}")
                        completed_set.add(issue_url)
                        progress["completed"].append(issue_url)
                        save_progress(progress)
                        done += 1
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)
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
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)
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
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)
                        time.sleep(1 + random.uniform(0, 0.5))
                    else:  # mode3
                        _handle_result(
                            False, "No PDF download available (read-only issue)",
                            issue_url, progress, completed_set, self._log
                        )
                        done += 1
                        self._emit_progress(done, total, mag_name, mag_done, mag_total)

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
                    self._emit_progress(done, total, mag_name, mag_done, mag_total)

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


class OrganizeWorker(QThread):
    """Runs organize_pdfs in a background thread."""
    def __init__(self, source_dir: str, dest_dir: str, hint_prefix: str | None):
        super().__init__()
        self.source_dir  = source_dir
        self.dest_dir    = dest_dir
        self.hint_prefix = hint_prefix
        self.signals     = WorkerSignals()
        self.result      = None   # filled in by run()

    def run(self):
        try:
            self.result = organize_pdfs(
                self.source_dir,
                self.dest_dir,
                hint_prefix=self.hint_prefix,
                log_fn=self.signals.log.emit,
                progress_fn=self.signals.progress.emit,
            )
        except Exception as e:
            self.signals.error.emit(str(e))
        finally:
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

    def stop(self):
        self._stop = True

    def _log(self, msg: str):
        logger.info(msg)
        self.signals.log.emit(msg)

    def run(self):
        downloader = None
        try:
            # Build set of (year, month) targets
            targets: set[tuple[str, str]] = {
                (year, month)
                for year, months in self.missing_by_year.items()
                for month in months
            }
            if not targets:
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
                if self.cookies_path:
                    downloader.save_cookies(self.cookies_path)
                    self._log(f"Cookies saved to {self.cookies_path}")

            # Collect all issue URLs from the archive
            self._log(f"Scanning archive: {self.archive_url}")
            links = downloader.collect_all_issue_links(self.archive_url, max_pages=110)
            self._log(f"Found {len(links)} issues in archive. Matching against missing list…")

            # Match each URL to a (year, month) by parsing its slug
            matched: list[tuple[str, str, str]] = []  # (url, year, month)
            special: list[str] = []                   # urls with no parseable date
            progress = load_progress()
            completed_set = set(progress["completed"])  # O(1) membership checks
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
                    if url not in downloaded_specials and not issue_already_on_disk(
                        url, special_dir, self.prefix, flat=True
                    ):
                        special.append(url)

            if not matched and not special:
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

                if url in completed_set:
                    self._log(f"[skip] {url}")
                    dl_count += 1
                    self.signals.progress.emit(dl_count, total)
                    continue

                if issue_already_on_disk(url, self.dest_dir, self.prefix, flat=False):
                    self._log(f"[exists] {month} {year}")
                    completed_set.add(url)
                    progress["completed"].append(url)
                    save_progress(progress)
                    dl_count += 1
                    self.signals.progress.emit(dl_count, total)
                    continue

                self._log(f"[{i}/{total}] {month} {year}  —  {url}")
                os.makedirs(os.path.join(self.dest_dir, year), exist_ok=True)

                ok, result = downloader.download_issue(url, dest_dir=self.dest_dir,
                                                       hint_prefix=self.prefix)
                if ok:
                    completed_set.add(url)
                    progress["completed"].append(url)
                    save_progress(progress)
                    self._log(f"  Downloaded: {result}")
                elif "read-only" in result or "No PDF download available" in result:
                    self._log(f"  [no pdf] {result}")
                    completed_set.add(url)
                    progress["completed"].append(url)
                    save_progress(progress)
                else:
                    self._log(f"  FAILED: {result}")

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

                ok, result = downloader.download_issue(url, dest_dir=special_dir,
                                                       hint_prefix=self.prefix, flat=True)
                if ok:
                    downloaded_specials.add(url)
                    save_special_issues(downloaded_specials)
                    self._log(f"  Downloaded: {result}")
                elif "read-only" in result or "No PDF download available" in result:
                    self._log(f"  [no pdf] {result}")
                    downloaded_specials.add(url)
                    save_special_issues(downloaded_specials)
                else:
                    self._log(f"  FAILED: {result}")

                dl_count += 1
                self.signals.progress.emit(dl_count, total)
                if url != special[-1] and not self._stop:
                    time.sleep(1 + random.uniform(0, 0.5))

            if self.cookies_path:
                downloader.save_cookies(self.cookies_path)

        except Exception as e:
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

/* ── Header banner ────────────────────────────────────────────────────── */
QWidget#header {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1a1a2e, stop:0.6 #1e1e2e, stop:1 #1a1a2e);
    border-bottom: 1px solid #2d2d45;
}

/* ── Tab widget ───────────────────────────────────────────────────────── */
QTabWidget::pane { border: none; background: #1a1a2a; top: 0; }
QTabBar { background: #13131f; }
QTabBar::tab {
    background: #13131f;
    color: #585b70;
    padding: 12px 32px;
    font-weight: 600;
    border-bottom: 3px solid transparent;
    margin-right: 0;
}
QTabBar::tab:selected   { color: #cdd6f4; background: #1a1a2a; border-bottom-color: #89b4fa; }
QTabBar::tab:hover:!selected { color: #a6adc8; background: #181826; border-bottom-color: #45475a; }

/* ── Scroll area / content pane ──────────────────────────────────────── */
QWidget#tab_content { background: #1a1a2a; }

/* ── Cards (group boxes) ─────────────────────────────────────────────── */
QGroupBox {
    background: #1e1e2e;
    border: 1px solid #2a2a3e;
    border-left: 3px solid #89b4fa;
    border-radius: 8px;
    margin-top: 16px;
    padding: 12px 14px 10px 14px;
    font-weight: 700;
    font-size: 8.5pt;
    color: #7287b8;
    letter-spacing: 0.08em;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 1px 6px;
    background: #1e1e2e;
    text-transform: uppercase;
}
QGroupBox[accent="purple"] { border-left-color: #cba6f7; }
QGroupBox[accent="purple"]::title { color: #9a7fc7; }
QGroupBox[accent="green"]  { border-left-color: #a6e3a1; }
QGroupBox[accent="green"]::title  { color: #6faf6a; }
QGroupBox[accent="teal"]   { border-left-color: #94e2d5; }
QGroupBox[accent="teal"]::title   { color: #5fa89e; }

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
QLabel[role="app-sub"]  { color: #585b70; font-size: 9pt; }
QLabel[role="log-cap"]  { color: #45475a; font-size: 8.5pt; font-weight: 600; letter-spacing: 0.08em; }
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
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Trains.com Magazine Downloader & Organizer v{APP_VERSION}")
        self.resize(960, 780)
        self.setMinimumSize(720, 560)
        # Workers — initialised here so slots never raise AttributeError
        self.worker:           DownloadWorker | None      = None
        self._org_worker:      OrganizeWorker | None      = None
        self._missing_worker:  MissingIssuesWorker | None = None
        # Organizer state
        self._org_hint:        str | None                 = None
        self._org_dst:         str                        = ""
        self._org_prefix:      str | None                 = None
        self._missing_by_year: dict[str, list[str]]       = {}
        self._dl_log_lines:  list[str] = []
        self._org_log_lines: list[str] = []
        self._build_ui()
        self._load_settings()
        self._setup_tray()

    # -- UI construction ------------------------------------------------------
    def _build_ui(self):
        self.setStyleSheet(_STYLESHEET)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        self.setCentralWidget(tabs)
        tabs.addTab(self._make_download_tab(), "  Download  ")
        tabs.addTab(self._make_organize_tab(), "  Organize  ")

    def _make_download_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("tab_content")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── Magazines ─────────────────────────────────────────────────────────
        mag_box = QGroupBox("Magazines")
        mag_grid = QGridLayout(mag_box)
        mag_grid.setHorizontalSpacing(20)
        self.mag_checks: dict[str, QCheckBox] = {}
        for i, name in enumerate(MAGAZINES):
            cb = QCheckBox(name)
            cb.setChecked(True)
            self.mag_checks[name] = cb
            mag_grid.addWidget(cb, i // 3, i % 3)
        layout.addWidget(mag_box)

        # ── Save location ──────────────────────────────────────────────────────
        save_box = QGroupBox("Save Location")
        save_box.setProperty("accent", "teal")
        save_layout = QVBoxLayout(save_box)
        save_row = QHBoxLayout()
        self.dir_edit = QLineEdit(
            str(Path.home() / "Downloads" / "TrainsMagazines")
        )
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_dir)
        save_row.addWidget(self.dir_edit)
        save_row.addWidget(browse_btn)
        save_layout.addLayout(save_row)
        layout.addWidget(save_box)

        # ── Authentication ─────────────────────────────────────────────────────
        cookie_box = QGroupBox("Authentication")
        cookie_box.setProperty("accent", "purple")
        cookie_col = QVBoxLayout(cookie_box)
        cookie_row = QHBoxLayout()
        self.cookie_edit = QLineEdit(DEFAULT_COOKIES_FILE)
        cookie_browse = QPushButton("Browse…")
        cookie_browse.setFixedWidth(90)
        cookie_browse.clicked.connect(self._browse_cookies)
        cookie_row.addWidget(self.cookie_edit)
        cookie_row.addWidget(cookie_browse)
        cookie_col.addLayout(cookie_row)
        cookie_hint = QLabel(
            "Leave blank to log in manually each run, or select an existing .json cookie file."
        )
        cookie_hint.setWordWrap(True)
        cookie_hint.setProperty("role", "muted")
        cookie_col.addWidget(cookie_hint)
        layout.addWidget(cookie_box)

        # ── Options ────────────────────────────────────────────────────────────
        opts_box = QGroupBox("Options")
        opts_box.setProperty("accent", "green")
        opts_layout = QVBoxLayout(opts_box)
        opts_layout.setSpacing(8)

        check_row = QHBoxLayout()
        self.headless_cb = QCheckBox("Headless mode")
        self.headless_cb.setToolTip(
            "Run without a visible browser window.\nRequires a valid saved cookie file."
        )
        self.test_cb     = QCheckBox("Test mode (3 issues only)")
        self.specials_cb = QCheckBox("Include special issues")
        self.specials_cb.setChecked(True)
        check_row.addWidget(self.headless_cb)
        check_row.addWidget(self.test_cb)
        check_row.addWidget(self.specials_cb)
        check_row.addStretch()
        opts_layout.addLayout(check_row)

        sort_row = QHBoxLayout()
        sort_lbl = QLabel("Download order:")
        sort_lbl.setFixedWidth(110)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Newest first", "Oldest first"])
        self.sort_combo.setFixedWidth(140)
        sort_row.addWidget(sort_lbl)
        sort_row.addWidget(self.sort_combo)
        sort_row.addStretch()
        opts_layout.addLayout(sort_row)

        layout.addWidget(opts_box)

        # ── Action bar ─────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.start_btn = QPushButton("▶  Start Download")
        self.start_btn.setProperty("role", "primary")
        self.start_btn.clicked.connect(self._start_download)
        self.stop_btn = QPushButton("■  Stop")
        self.stop_btn.setProperty("role", "danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_download)
        clear_btn = QPushButton("Clear Progress Cache")
        clear_btn.clicked.connect(self._clear_progress)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # ── Progress / status ──────────────────────────────────────────────────
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

        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setProperty("role", "status")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        # ── Log ────────────────────────────────────────────────────────────────
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

        self._dl_filter.textChanged.connect(
            lambda: self._rebuild_log(self.dl_log, self._dl_log_lines, self._dl_filter)
        )

        # Persist settings on every change
        self.dir_edit.textChanged.connect(self._save_settings)
        self.cookie_edit.textChanged.connect(self._save_settings)
        self.headless_cb.stateChanged.connect(self._save_settings)
        self.test_cb.stateChanged.connect(self._save_settings)
        self.specials_cb.stateChanged.connect(self._save_settings)
        self.sort_combo.currentIndexChanged.connect(self._save_settings)
        for cb in self.mag_checks.values():
            cb.stateChanged.connect(self._save_settings)

        return w

    def _make_organize_tab(self) -> QWidget:
        w = QWidget()
        w.setObjectName("tab_content")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── Folders ────────────────────────────────────────────────────────────
        folders_box = QGroupBox("Folders")
        folders_box.setProperty("accent", "teal")
        folders_layout = QVBoxLayout(folders_box)
        folders_layout.setSpacing(8)

        src_row = QHBoxLayout()
        src_lbl = QLabel("Source:")
        src_lbl.setFixedWidth(72)
        self.src_edit = QLineEdit()
        self.src_edit.setPlaceholderText("Folder containing PDFs to organize…")
        src_browse = QPushButton("Browse…")
        src_browse.setFixedWidth(90)
        src_browse.clicked.connect(lambda: self._pick_dir(self.src_edit))
        src_row.addWidget(src_lbl)
        src_row.addWidget(self.src_edit)
        src_row.addWidget(src_browse)
        folders_layout.addLayout(src_row)

        dst_row = QHBoxLayout()
        dst_lbl = QLabel("Destination:")
        dst_lbl.setFixedWidth(72)
        self.dst_edit = QLineEdit()
        self.dst_edit.setPlaceholderText("Folder for organized output (can be same as source)…")
        dst_browse = QPushButton("Browse…")
        dst_browse.setFixedWidth(90)
        dst_browse.clicked.connect(lambda: self._pick_dir(self.dst_edit))
        dst_row.addWidget(dst_lbl)
        dst_row.addWidget(self.dst_edit)
        dst_row.addWidget(dst_browse)
        folders_layout.addLayout(dst_row)

        prefix_row = QHBoxLayout()
        prefix_lbl = QLabel("Prefix:")
        prefix_lbl.setFixedWidth(72)
        self.prefix_combo = QComboBox()
        self.prefix_combo.addItem("Auto-detect")
        for info in MAGAZINES.values():
            self.prefix_combo.addItem(info["prefix"])
        self.prefix_combo.setFixedWidth(140)
        self.prefix_combo.setToolTip("Force a specific magazine prefix when auto-detect fails")
        prefix_row.addWidget(prefix_lbl)
        prefix_row.addWidget(self.prefix_combo)
        prefix_row.addStretch()
        folders_layout.addLayout(prefix_row)

        layout.addWidget(folders_box)

        # ── Organize action ────────────────────────────────────────────────────
        org_btn_row = QHBoxLayout()
        self.org_run_btn = QPushButton("▶  Organize PDFs")
        self.org_run_btn.setProperty("role", "primary")
        self.org_run_btn.clicked.connect(self._run_organize)
        org_btn_row.addWidget(self.org_run_btn)
        org_btn_row.addStretch()
        layout.addLayout(org_btn_row)

        # ── Authentication (for missing-issues download) ───────────────────────
        cookie_box = QGroupBox("Authentication")
        cookie_box.setProperty("accent", "purple")
        cookie_col = QVBoxLayout(cookie_box)
        cookie_row = QHBoxLayout()
        self.org_cookie_edit = QLineEdit()
        self.org_cookie_edit.setPlaceholderText("session_cookies.json (required to download missing issues)")
        org_cookie_browse = QPushButton("Browse…")
        org_cookie_browse.setFixedWidth(90)
        org_cookie_browse.clicked.connect(self._browse_org_cookies)
        self.org_headless_cb = QCheckBox("Headless browser")
        cookie_row.addWidget(self.org_cookie_edit)
        cookie_row.addWidget(org_cookie_browse)
        cookie_row.addWidget(self.org_headless_cb)
        cookie_col.addLayout(cookie_row)
        layout.addWidget(cookie_box)

        # ── Download missing ───────────────────────────────────────────────────
        missing_btn_row = QHBoxLayout()
        missing_btn_row.setSpacing(8)
        self.dl_missing_btn = QPushButton("⬇  Download Missing Issues")
        self.dl_missing_btn.setProperty("role", "primary")
        self.dl_missing_btn.setEnabled(False)
        self.dl_missing_btn.clicked.connect(self._start_missing_download)
        self.dl_missing_stop_btn = QPushButton("■  Stop")
        self.dl_missing_stop_btn.setProperty("role", "danger")
        self.dl_missing_stop_btn.setEnabled(False)
        self.dl_missing_stop_btn.clicked.connect(self._stop_missing_download)
        missing_btn_row.addWidget(self.dl_missing_btn)
        missing_btn_row.addWidget(self.dl_missing_stop_btn)
        missing_btn_row.addStretch()
        layout.addLayout(missing_btn_row)

        # ── Progress / log ─────────────────────────────────────────────────────
        self.org_progress = QProgressBar()
        self.org_progress.setVisible(False)
        layout.addWidget(self.org_progress)

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

        # Persist settings on every change
        self.src_edit.textChanged.connect(self._save_settings)
        self.dst_edit.textChanged.connect(self._save_settings)
        self.prefix_combo.currentIndexChanged.connect(self._save_settings)
        self.org_cookie_edit.textChanged.connect(self._save_settings)
        self.org_headless_cb.stateChanged.connect(self._save_settings)

        return w

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
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
            self._dl_log("Progress cache cleared.")
        else:
            self._dl_log("No progress cache file found.")

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

    def _append_log(self, log: QTextEdit, msg: str,
                    lines_buf: list, filter_edit: QLineEdit,
                    badge_label: QLabel, max_lines: int = 2000) -> None:
        lines_buf.append(msg)
        if len(lines_buf) > max_lines:
            lines_buf.pop(0)

        error_count = sum(1 for l in lines_buf if "FAILED" in l or "ERROR:" in l)
        if error_count > 0:
            badge_label.setText(f"{error_count} error{'s' if error_count != 1 else ''}")
            badge_label.setVisible(True)
        else:
            badge_label.setVisible(False)

        filt = filter_edit.text().strip().lower()
        if filt and filt not in msg.lower():
            return
        log.append(self._colorize(msg))
        log.verticalScrollBar().setValue(log.verticalScrollBar().maximum())

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

    def _dl_log(self, msg: str):
        self._append_log(self.dl_log, msg,
                         self._dl_log_lines, self._dl_filter, self._dl_error_badge)

    def _start_download(self):
        if self.worker is not None and self.worker.isRunning():
            return  # already running — button should be disabled, but be safe

        magazines = [n for n, cb in self.mag_checks.items() if cb.isChecked()]
        if not magazines:
            QMessageBox.warning(self, "Nothing selected", "Select at least one magazine.")
            return

        base_dir = self.dir_edit.text().strip()
        if not base_dir:
            QMessageBox.warning(self, "No folder", "Please choose a save location.")
            return

        cookies   = self.cookie_edit.text().strip() or None
        headless  = self.headless_cb.isChecked()
        test      = self.test_cb.isChecked()
        newest    = self.sort_combo.currentText() == "Newest first"
        specials  = self.specials_cb.isChecked()

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("")

        # Build per-magazine progress rows
        prog_layout = self._progress_container.layout()
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
            bar.setMaximum(1)
            row_layout.addLayout(header)
            row_layout.addWidget(bar)
            prog_layout.addWidget(row_widget)
            self._mag_bar_rows[mag_name] = (count_lbl, bar)
        self._summary_label.setText("Starting…")
        self._progress_container.setVisible(True)

        self._disconnect_worker(self.worker)
        self.worker = DownloadWorker(magazines, base_dir, headless, test, cookies, newest,
                                     include_specials=specials)
        self.worker.signals.log.connect(self._dl_log)
        self.worker.signals.progress.connect(self._update_progress)
        self.worker.signals.magazine_progress.connect(self._update_mag_progress)
        self.worker.signals.status_msg.connect(self._summary_label.setText)
        self.worker.signals.error.connect(self._on_error)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.start()

    def _stop_download(self):
        if self.worker:
            self.worker.stop()
            self._dl_log("Stop requested — waiting for current issue to finish…")
        self.stop_btn.setEnabled(False)

    def _update_mag_progress(self, mag_name: str, done: int, total: int):
        if mag_name not in self._mag_bar_rows:
            return
        count_lbl, bar = self._mag_bar_rows[mag_name]
        bar.setMaximum(total)
        bar.setValue(done)
        count_lbl.setText(f"{done} / {total}")

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.status_label.setText(f"{current} / {total} issues")
            self._tray.setToolTip(f"Trains Downloader — {current} / {total} downloading…")

    def _on_error(self, msg: str):
        self._dl_log(f"ERROR: {msg}")
        QMessageBox.critical(self, "Error", msg)

    def _on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._progress_container.setVisible(False)
        self._dl_log("--- Done ---")
        self.status_label.setText("Done.")
        self._tray.setToolTip("Trains Downloader — Idle")

    def _browse_org_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cookie file", "",
            "Cookie files (*.json);;All files (*)"
        )
        if path:
            self.org_cookie_edit.setText(path)

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

    def _run_organize(self):
        if self._org_worker is not None and self._org_worker.isRunning():
            return

        src = self.src_edit.text().strip()
        dst = self.dst_edit.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "Missing folders", "Select both source and destination folders.")
            return
        pfx_text = self.prefix_combo.currentText()
        hint = None if pfx_text == "Auto-detect" else pfx_text

        self.org_log.clear()
        self._org_log_lines.clear()
        self._append_log(self.org_log, f"Organizing PDFs from: {src}",
                         self._org_log_lines, self._org_filter, self._org_error_badge)
        self._append_log(self.org_log, f"                  to: {dst}\n",
                         self._org_log_lines, self._org_filter, self._org_error_badge)

        self.org_run_btn.setEnabled(False)
        self.dl_missing_btn.setEnabled(False)
        self.org_progress.setValue(0)
        self.org_progress.setVisible(True)

        self._org_hint = hint
        self._org_dst  = dst
        self._disconnect_worker(self._org_worker)
        self._org_worker = OrganizeWorker(src, dst, hint)
        self._org_worker.signals.log.connect(
            lambda m: self._append_log(self.org_log, m,
                                       self._org_log_lines, self._org_filter, self._org_error_badge)
        )
        self._org_worker.signals.progress.connect(self._update_org_progress)
        self._org_worker.signals.error.connect(
            lambda msg: QMessageBox.critical(self, "Organize error", msg)
        )
        self._org_worker.signals.finished.connect(self._on_organize_finished)
        self._org_worker.start()

    def _on_organize_finished(self):
        self.org_run_btn.setEnabled(True)
        self.org_progress.setVisible(False)

        if self._org_worker.result is None:
            return  # an error was emitted; nothing to summarize
        moved, already_correct, unrecognized, metadata_stamped, report = self._org_worker.result

        self._append_log(self.org_log, f"\n-- {moved} moved, {already_correct} already correct, {unrecognized} unrecognized, {metadata_stamped} metadata updated --",
                         self._org_log_lines, self._org_filter, self._org_error_badge)
        for line in report:
            self._append_log(self.org_log, line,
                             self._org_log_lines, self._org_filter, self._org_error_badge)

        hint = self._org_hint
        dst  = self._org_dst

        # Parse missing issues from the report so the download button can use them
        self._missing_by_year: dict[str, list[str]] = {}
        for line in report:
            m = re.match(r"(\d{4}): missing (\[.*\])", line)
            if m:
                try:
                    import ast
                    self._missing_by_year[m.group(1)] = ast.literal_eval(m.group(2))
                except Exception:
                    pass

        # Determine the magazine prefix for the destination folder
        self._org_prefix: str | None = hint
        if not self._org_prefix:
            # Try the last component of the dest path (e.g. .../CTR → CTR)
            candidate = os.path.basename(os.path.normpath(dst)).upper()
            if candidate in PREFIX_TO_TITLE:
                self._org_prefix = candidate

        has_missing = bool(self._missing_by_year) and self._org_prefix and \
                      _archive_url_for_prefix(self._org_prefix) is not None
        self.dl_missing_btn.setEnabled(has_missing)
        if has_missing:
            total = sum(len(v) for v in self._missing_by_year.values())
            self._append_log(
                self.org_log,
                f"\n{total} missing issue(s) found — click 'Download Missing Issues' to fetch them.",
                self._org_log_lines, self._org_filter, self._org_error_badge
            )

    def _start_missing_download(self):
        if self._missing_worker is not None and self._missing_worker.isRunning():
            return

        dst = self.dst_edit.text().strip()
        if not dst or not self._org_prefix:
            return
        archive_url = _archive_url_for_prefix(self._org_prefix)
        if not archive_url:
            QMessageBox.warning(self, "Unknown magazine",
                                f"No archive URL found for prefix '{self._org_prefix}'.")
            return

        cookies  = self.org_cookie_edit.text().strip() or DEFAULT_COOKIES_FILE
        headless = self.org_headless_cb.isChecked()

        self.dl_missing_btn.setEnabled(False)
        self.dl_missing_stop_btn.setEnabled(True)
        self.org_progress.setVisible(True)
        self.org_progress.setValue(0)

        self._disconnect_worker(self._missing_worker)
        self._missing_worker = MissingIssuesWorker(
            prefix=self._org_prefix,
            archive_url=archive_url,
            missing_by_year=self._missing_by_year,
            dest_dir=dst,
            cookies_path=cookies,
            headless=headless,
        )
        self._missing_worker.signals.log.connect(
            lambda m: self._append_log(self.org_log, m,
                                       self._org_log_lines, self._org_filter, self._org_error_badge)
        )
        self._missing_worker.signals.progress.connect(self._update_org_progress)
        self._missing_worker.signals.error.connect(
            lambda msg: QMessageBox.critical(self, "Error", msg)
        )
        self._missing_worker.signals.finished.connect(self._on_missing_finished)
        self._missing_worker.start()

    def _stop_missing_download(self):
        if self._missing_worker is not None and self._missing_worker.isRunning():
            self._missing_worker.stop()
            self._append_log(self.org_log, "Stop requested…",
                             self._org_log_lines, self._org_filter, self._org_error_badge)
        self.dl_missing_stop_btn.setEnabled(False)

    def _update_org_progress(self, current: int, total: int):
        if total > 0:
            self.org_progress.setMaximum(total)
            self.org_progress.setValue(current)

    def _on_missing_finished(self):
        has_missing = bool(self._missing_by_year) and self._org_prefix and \
                      _archive_url_for_prefix(self._org_prefix) is not None
        self.dl_missing_btn.setEnabled(has_missing)
        self.dl_missing_stop_btn.setEnabled(False)
        self.org_progress.setVisible(False)
        self._append_log(self.org_log, "--- Download complete ---",
                         self._org_log_lines, self._org_filter, self._org_error_badge)


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
