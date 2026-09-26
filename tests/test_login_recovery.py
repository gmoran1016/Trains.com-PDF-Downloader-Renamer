"""Login must survive a lost ChromeDriver session without resetting its timeout."""

from types import SimpleNamespace

import pytest
from urllib3 import HTTPConnectionPool
from urllib3.connection import HTTPConnection
from urllib3.exceptions import MaxRetryError, NewConnectionError

import trains_app


LOGIN_URL = "https://www.trains.com/"
SIGNED_IN = "<header>Hello, reader</header><a>Log out</a>"


def refused_connection():
    return MaxRetryError(
        HTTPConnectionPool("localhost", 59921),
        "/session/expired/source",
        NewConnectionError(
            HTTPConnection("localhost", port=59921),
            "[WinError 10061] No connection could be made because the "
            "target machine actively refused it",
        ),
    )


class LoginDriver:
    """Script the external browser boundary; use the real login/restart code."""

    title = ""

    def __init__(self, pages=(), navigation_error=None):
        self.pages = iter(pages)
        self.navigation_error = navigation_error
        self.current_url = "data:,"
        self.visited = []
        self.cookies = []
        self.closed = False

    def get(self, url):
        self.visited.append(url)
        if self.navigation_error:
            raise self.navigation_error
        self.current_url = url

    @property
    def page_source(self):
        if self.current_url != LOGIN_URL:
            return "<html></html>"
        page = next(self.pages, "<a>Sign in</a>")
        if isinstance(page, Exception):
            raise page
        return page

    def add_cookie(self, cookie):
        assert self.current_url == LOGIN_URL
        self.cookies.append(dict(cookie))

    def get_cookies(self):
        return list(self.cookies)

    def quit(self):
        self.closed = True


@pytest.fixture
def login_clock(monkeypatch):
    clock = SimpleNamespace(now=0.0)

    def sleep(seconds):
        clock.now += seconds

    monkeypatch.setattr(trains_app, "time", SimpleNamespace(
        time=lambda: clock.now,
        monotonic=lambda: clock.now,
        sleep=sleep,
    ))
    monkeypatch.setattr(trains_app.random, "uniform", lambda *_args: 0.0)
    return clock


def make_downloader(monkeypatch, tmp_path, *drivers):
    available = iter(drivers)
    monkeypatch.setattr(
        trains_app.MagazineDownloader, "_create_driver", lambda _self: next(available)
    )
    return trains_app.MagazineDownloader(str(tmp_path))


@pytest.mark.parametrize("stage", ["navigation", "page_source"])
def test_manual_login_reopens_page_after_connection_refused(
    monkeypatch, tmp_path, login_clock, stage
):
    error = refused_connection()
    dead = LoginDriver(
        [error], navigation_error=error if stage == "navigation" else None
    )
    recovered = LoginDriver([SIGNED_IN])
    downloader = make_downloader(monkeypatch, tmp_path, dead, recovered)

    assert downloader.wait_for_manual_login(timeout=30) is True
    assert dead.closed
    assert recovered.visited == [LOGIN_URL]
    assert downloader._driver is recovered


def test_manual_login_preserves_saved_cookies_after_restart(
    monkeypatch, tmp_path, login_clock
):
    dead = LoginDriver([refused_connection()])
    recovered = LoginDriver([SIGNED_IN])
    downloader = make_downloader(monkeypatch, tmp_path, dead, recovered)
    downloader._session_cookies = [{
        "name": "test-session", "value": "synthetic", "domain": ".trains.com",
        "path": "/", "secure": True,
    }]

    assert downloader.wait_for_manual_login(timeout=30) is True
    assert recovered.cookies == downloader._session_cookies
    assert recovered.cookies[0]["value"] == "synthetic"


def test_manual_login_restart_keeps_original_deadline(
    monkeypatch, tmp_path, login_clock
):
    dead = LoginDriver(["<a>Sign in</a>", refused_connection()])
    recovered = LoginDriver()
    downloader = make_downloader(monkeypatch, tmp_path, dead, recovered)
    updates = []

    assert downloader.wait_for_manual_login(timeout=5, progress_fn=updates.append) is False
    assert dead.closed
    # One normal poll takes 3s and recovery takes 0.5s. A fresh 5s deadline
    # would incorrectly let the second browser keep waiting past 8 seconds.
    assert login_clock.now == 5
    assert updates


def test_manual_login_reports_persistent_disconnect_after_one_restart(
    monkeypatch, tmp_path, login_clock
):
    error = refused_connection()
    dead = LoginDriver([error])
    also_dead = LoginDriver([error])
    downloader = make_downloader(monkeypatch, tmp_path, dead, also_dead)

    with pytest.raises(RuntimeError, match="(?i)browser.*login") as caught:
        downloader.wait_for_manual_login(timeout=30)

    assert caught.value.__cause__ is error
    assert dead.closed
    assert downloader._driver is also_dead
    assert not also_dead.closed  # No unbounded restart loop.


def test_manual_login_does_not_restart_for_unrelated_error(
    monkeypatch, tmp_path, login_clock
):
    driver = LoginDriver([ValueError("unexpected login data")])
    downloader = make_downloader(monkeypatch, tmp_path, driver)

    with pytest.raises(ValueError, match="unexpected login data"):
        downloader.wait_for_manual_login(timeout=30)

    assert not driver.closed


def test_manual_login_detects_login_without_reloading_between_polls(
    monkeypatch, tmp_path, login_clock
):
    driver = LoginDriver(["<a>Sign in</a>", SIGNED_IN])
    downloader = make_downloader(monkeypatch, tmp_path, driver)

    assert downloader.wait_for_manual_login(timeout=30) is True
    assert driver.visited == [LOGIN_URL]
    assert not driver.closed


def test_saved_login_check_recovers_instead_of_reporting_signed_out(
    monkeypatch, tmp_path, login_clock
):
    error = refused_connection()
    # Both the 403 check and the account-marker read use page_source.
    dead = LoginDriver([error, error])
    recovered = LoginDriver([SIGNED_IN, SIGNED_IN])
    downloader = make_downloader(monkeypatch, tmp_path, dead, recovered)

    assert downloader.is_logged_in() is True
    assert dead.closed
    assert recovered.visited == [LOGIN_URL]
