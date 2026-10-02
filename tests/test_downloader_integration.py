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


def test_archive_page_falls_back_to_authenticated_http_when_browser_is_blocked(
    monkeypatch,
):
    archive = "https://www.trains.com/mrr/magazine/"
    driver = FakeDriver(current_url=archive)
    driver.page_source = "<html><title>403 Forbidden</title></html>"
    driver.title = "403 Forbidden"
    downloader = _downloader(driver)
    downloader._session_cookies = [
        {"name": "kserv-session", "value": "session-token"}
    ]

    class Response:
        status_code = 200
        text = f'<a href="{archive}october-2026/">October 2026</a>'

        def raise_for_status(self):
            return None

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["cookies"] = kwargs["cookies"]
        return Response()

    import requests

    monkeypatch.setattr(requests, "get", fake_get)

    assert downloader.get_page_issue_links(
        archive,
        archive,
        hint_prefix="MRR",
    ) == [f"{archive}october-2026/"]
    assert captured == {
        "url": archive,
        "cookies": {"kserv-session": "session-token"},
    }


def test_direct_issue_download_falls_back_to_authenticated_http_when_browser_is_blocked(
    monkeypatch,
    tmp_path,
):
    issue_url = "https://www.trains.com/mrr/magazine/october-2026/"
    driver = ModeDriver()
    driver.page_source = "<html><title>403 Forbidden</title></html>"
    driver.title = "403 Forbidden"
    downloader = _downloader(driver)
    downloader.download_dir = str(tmp_path / "raw")
    downloader._session_cookies = [
        {"name": "kserv-session", "value": "session-token"}
    ]
    downloader._fetch_pdf = lambda url, dest_dir, hint_prefix, cookies, flat: (
        True,
        f"{url}|{dest_dir}|{hint_prefix}|{cookies['kserv-session']}|{flat}",
    )

    class Response:
        status_code = 200
        text = '<a href="https://cdn.example/MAG-MRR-OCT26.pdf">Download</a>'

        def raise_for_status(self):
            return None

    import requests

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())

    assert downloader.download_issue(
        issue_url,
        str(tmp_path / "organized"),
        hint_prefix="MRR",
    ) == (
        True,
        "https://cdn.example/MAG-MRR-OCT26.pdf|"
        f"{tmp_path / 'organized'}|MRR|session-token|False",
    )


def test_issue_mode_uses_authenticated_http_when_browser_is_blocked(monkeypatch):
    issue_url = "https://www.trains.com/mrr/magazine/october-2026/"
    driver = ModeDriver()
    driver.page_source = "<html><title>403 Forbidden</title></html>"
    driver.title = "403 Forbidden"
    downloader = _downloader(driver)
    downloader._session_cookies = [
        {"name": "kserv-session", "value": "session-token"}
    ]

    class Response:
        status_code = 200
        text = '<a href="https://cdn.example/MAG-MRR-OCT26.pdf">Download</a>'

        def raise_for_status(self):
            return None

    import requests

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: Response())

    assert downloader.detect_issue_mode(issue_url, hint_prefix="MRR") == (
        "mode1",
        "https://cdn.example/MAG-MRR-OCT26.pdf",
    )


def test_authenticated_html_cover_without_reader_controls_is_read_only():
    html = """
    <div class="ci-media">
      <div class="ci-media__cover">
        <img class="ci-media__cover-img" src="cover.jpg">
      </div>
      <a class="ci-help__link" href="/print-help/">
        Download &amp; Print Instructions
      </a>
    </div>
    """

    assert MagazineDownloader._detect_download_mode_from_html(
        html,
        "https://www.trains.com/mrr/magazine/special-issues/example/",
    ) == ("mode3", None)


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


def test_later_archive_404_ends_pagination_without_error(monkeypatch):
    import requests

    archive = "https://www.trains.com/mrr/magazine/special-issues/"
    issue = f"{archive}great-model-railroads-2024/"
    downloader = _downloader(FakeDriver(current_url=archive))
    logs = []
    downloader.log_fn = logs.append

    response = requests.Response()
    response.status_code = 404
    response.url = f"{archive}page/2/"
    not_found = requests.HTTPError("404 Client Error: Not Found", response=response)

    def fake_get_page_issue_links(url, *_args, **_kwargs):
        if url.endswith("page/2/"):
            raise not_found
        return [issue]

    downloader.get_page_issue_links = fake_get_page_issue_links
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    assert downloader.collect_all_issue_links(
        archive,
        max_pages=3,
        hint_prefix="MRR",
        allow_empty=True,
    ) == [issue]
    assert not any("Error on page" in message for message in logs)
    assert any("No more issues after page 1" in message for message in logs)


def test_archive_page_403_is_a_scan_error_with_no_partial_links():
    import requests

    archive = "https://www.trains.com/mrr/magazine/"
    response = requests.Response()
    response.status_code = 403
    response.url = archive
    forbidden = requests.HTTPError("403 Client Error: Forbidden", response=response)
    downloader = _downloader(FakeDriver(current_url=archive))
    downloader.get_page_issue_links = lambda *_args, **_kwargs: (_ for _ in ()).throw(forbidden)

    with pytest.raises(ArchiveScanError, match="403") as exc_info:
        downloader.collect_all_issue_links(archive, max_pages=2, hint_prefix="MRR")

    assert exc_info.value.partial_links == []


def test_later_archive_403_preserves_links_from_successful_pages(monkeypatch):
    import requests

    archive = "https://www.trains.com/mrr/magazine/"
    issue = f"{archive}november-2026/"
    response = requests.Response()
    response.status_code = 403
    response.url = f"{archive}page/2/"
    forbidden = requests.HTTPError("403 Client Error: Forbidden", response=response)
    downloader = _downloader(FakeDriver(current_url=archive))

    def fake_get_page_issue_links(url, *_args, **_kwargs):
        if url.endswith("page/2/"):
            raise forbidden
        return [issue]

    downloader.get_page_issue_links = fake_get_page_issue_links
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    with pytest.raises(ArchiveScanError, match="403") as exc_info:
        downloader.collect_all_issue_links(archive, max_pages=3, hint_prefix="MRR")

    assert exc_info.value.partial_links == [issue]


def test_optional_special_archive_403_is_not_treated_as_empty():
    import requests

    archive = "https://www.trains.com/mrr/magazine/special-issues/"
    response = requests.Response()
    response.status_code = 403
    response.url = archive
    forbidden = requests.HTTPError("403 Client Error: Forbidden", response=response)
    downloader = _downloader(FakeDriver(current_url=archive))
    downloader.get_page_issue_links = lambda *_args, **_kwargs: (_ for _ in ()).throw(forbidden)

    with pytest.raises(ArchiveScanError, match="403"):
        downloader.collect_all_issue_links(
            archive, max_pages=1, hint_prefix="MRR", allow_empty=True
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


def test_detect_download_mode_does_not_treat_cover_only_as_flipbook():
    from trains_app import detect_download_mode

    class CoverOnlyDriver(ModeDriver):
        def find_elements(self, _by, selector):
            if selector == "div.ci-media__cover":
                return [FakeElement()]
            return super().find_elements(_by, selector)

    assert detect_download_mode(CoverOnlyDriver()) == ("mode3", None)


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
