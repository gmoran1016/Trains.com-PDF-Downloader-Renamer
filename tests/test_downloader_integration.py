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
