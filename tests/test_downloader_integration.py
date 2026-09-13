import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trains_app
from trains_app import MagazineDownloader


ArchiveScanError = getattr(trains_app, "ArchiveScanError", RuntimeError)


class FakeElement:
    def __init__(self, href="", text=""):
        self.href = href
        self.text = text

    def get_attribute(self, name):
        if name == "href":
            return self.href
        if name == "innerText":
            return self.text
        return ""


class FakeDriver:
    def __init__(self, hrefs=None, current_url=None):
        self.hrefs = list(hrefs or [])
        self.current_url = current_url or "https://www.trains.com/"
        self.execute_script_calls = 0
        self.href_script_calls = 0
        self.requested_url = None

    def get(self, url):
        self.requested_url = url

    def execute_script(self, script, *args):
        self.execute_script_calls += 1
        if "document.readyState" in script:
            return "complete"
        if "querySelectorAll" in script:
            self.href_script_calls += 1
            return self.hrefs
        return None

    def find_elements(self, *_args):
        return [FakeElement(href=href) for href in self.hrefs]


class ModeDriver(FakeDriver):
    def __init__(self, *, direct_href=None, pdf_edition=False, read_magazine=False):
        super().__init__()
        self.direct_href = direct_href
        self.pdf_edition = pdf_edition
        self.read_magazine = read_magazine

    def find_elements(self, _by, selector):
        if selector == "a.ci-btn--secondary[href]":
            return [FakeElement(href=self.direct_href)] if self.direct_href else []
        if "normalize-space(.)='Download'" in selector:
            return [FakeElement(href=self.direct_href)] if self.direct_href else []
        if selector == "div.ci-media__cover":
            return []
        if "Read Magazine" in selector:
            return [FakeElement(text="Read Magazine")] if self.read_magazine else []
        if "PDF Edition" in selector:
            return [FakeElement(text="PDF Edition")] if self.pdf_edition else []
        return []


class GatedModeDriver(ModeDriver):
    """Current trains.com issue surface when an eligible membership is absent."""

    def find_elements(self, _by, selector):
        if selector == "div.ci-media.ci-media--gated":
            return [FakeElement()]
        if selector == "div.ci-media__cover":
            return [FakeElement()]
        return super().find_elements(_by, selector)


def _downloader(driver):
    downloader = object.__new__(MagazineDownloader)
    downloader._driver = driver
    downloader.log_fn = None
    return downloader


def test_normal_archive_rejects_unparseable_article_link():
    assert not MagazineDownloader._is_issue_link(
        None,
        "https://www.trains.com/ctr/magazine/railroad-places/",
        "https://www.trains.com/ctr/magazine/",
        hint_prefix="CTR",
    )


def test_special_archive_accepts_unparseable_special_slug():
    assert MagazineDownloader._is_issue_link(
        None,
        "https://www.trains.com/trn/magazine/special-issues/railroad-technology/",
        "https://www.trains.com/trn/magazine/special-issues/",
        hint_prefix="TRN",
    )


def test_page_links_are_extracted_in_one_browser_script_call():
    archive = "https://www.trains.com/mrr/magazine/"
    driver = FakeDriver(
        hrefs=[
            archive,
            f"{archive}october-2026/",
            f"{archive}railroad-places/",
        ],
        current_url=archive,
    )
    downloader = _downloader(driver)

    links = downloader.get_page_issue_links(
        archive,
        archive,
        hint_prefix="MRR",
    )

    assert links == [f"{archive}october-2026/"]
    assert driver.href_script_calls == 1


def test_archive_page_recovers_when_chromedriver_dies_during_script(monkeypatch):
    archive = "https://www.trains.com/mrr/magazine/"
    hrefs = [f"{archive}october-2026/"]

    class DeadAfterFirstScriptDriver(FakeDriver):
        def __init__(self):
            super().__init__(hrefs=hrefs, current_url=archive)
            self.dead = False

        def execute_script(self, script, *args):
            if self.dead:
                raise RuntimeError(
                    "HTTPConnectionPool(host='localhost', port=65006): "
                    "Read timed out. (read timeout=120)"
                )
            if "document.readyState" in script:
                self.dead = True
                raise RuntimeError(
                    "HTTPConnectionPool(host='localhost', port=65006): "
                    "Read timed out. (read timeout=120)"
                )
            return super().execute_script(script, *args)

    downloader = _downloader(DeadAfterFirstScriptDriver())
    replacement = FakeDriver(hrefs=hrefs, current_url=archive)
    restarted = []

    def restart_browser():
        downloader._driver = replacement
        restarted.append(True)
        return True

    downloader._restart_browser = restart_browser
    downloader.log_fn = None
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    assert downloader.get_page_issue_links(
        archive,
        archive,
        hint_prefix="MRR",
    ) == hrefs
    assert restarted == [True]


def test_regular_empty_archive_is_an_error():
    archive = "https://www.trains.com/mrr/magazine/"
    downloader = _downloader(FakeDriver(current_url=archive))

    with pytest.raises(ArchiveScanError, match="no issue links"):
        downloader.collect_all_issue_links(
            archive,
            max_pages=1,
            hint_prefix="MRR",
        )


def test_special_redirect_can_be_reported_as_empty():
    archive = "https://www.trains.com/grw/magazine/special-issues/"
    driver = FakeDriver(
        current_url="https://www.trains.com/uncategorized/special-issues/"
    )
    downloader = _downloader(driver)

    assert downloader.collect_all_issue_links(
        archive,
        max_pages=1,
        hint_prefix="GRW",
        allow_empty=True,
    ) == []


def test_detect_download_mode_keeps_direct_downloads():
    from trains_app import detect_download_mode

    mode, href = detect_download_mode(
        ModeDriver(direct_href="https://cdn.example/MAG-MRR-OCT26.pdf")
    )

    assert mode == "mode1"
    assert href.endswith("MAG-MRR-OCT26.pdf")


def test_detect_download_mode_recognizes_pdf_edition_viewer():
    from trains_app import detect_download_mode

    mode, href = detect_download_mode(ModeDriver(pdf_edition=True))

    assert (mode, href) == ("mode2", None)


def test_detect_download_mode_skips_locked_issue_cover_as_gated():
    from trains_app import detect_download_mode

    mode, href = detect_download_mode(GatedModeDriver())

    assert (mode, href) == ("mode3", "gated")


def test_download_issue_reports_gated_access_without_opening_cover(monkeypatch, tmp_path):
    driver = GatedModeDriver()
    downloader = _downloader(driver)
    downloader.download_dir = str(tmp_path / "raw")
    flipbook_calls = []
    downloader._flipbook_download = lambda *args, **kwargs: (
        flipbook_calls.append((args, kwargs)) or (True, "unexpected.pdf")
    )
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    result = downloader.download_issue(
        "https://www.trains.com/mrr/magazine/great-model-railroads-2024/",
        str(tmp_path / "organized"),
        hint_prefix="MRR",
    )

    assert result[0] is False
    assert "unlimited membership" in result[1].lower()
    assert flipbook_calls == []


def test_download_issue_uses_current_pdf_edition_viewer(monkeypatch, tmp_path):
    driver = ModeDriver(pdf_edition=True)
    downloader = _downloader(driver)
    downloader.download_dir = str(tmp_path / "raw")
    downloader._flipbook_download = lambda *args, **kwargs: (True, "viewer.pdf")
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    result = downloader.download_issue(
        "https://www.trains.com/grw/magazine/fall-2020/",
        str(tmp_path / "organized"),
        hint_prefix="GRW",
    )

    assert result == (True, "viewer.pdf")
