"""Keep ChromeDriver out of the embedded-frame attachment crash path."""

from types import SimpleNamespace

import pytest
from selenium import webdriver

from trains_app import MagazineDownloader


class StartupDriver:
    def __init__(self, configuration_error=None):
        self.auto_attach = True
        self.configuration_error = configuration_error
        self.command_executor = SimpleNamespace(
            _client_config=SimpleNamespace(timeout=120)
        )
        self.closed = False
        self.visited = []
        self.cookies = []

    def execute_cdp_cmd(self, command, params):
        # This is the Chrome protocol boundary; frames still render normally.
        assert command == "Target.setAutoAttach"
        assert params["waitForDebuggerOnStart"] is False
        assert params["flatten"] is True
        assert self.command_executor._client_config.timeout <= 60
        if self.configuration_error:
            raise self.configuration_error
        self.auto_attach = params["autoAttach"]

    def get(self, url):
        # An attachment burst must not reach an unconfigured driver, including
        # the first navigation used to restore cookies in a replacement session.
        assert not self.auto_attach
        self.visited.append(url)

    def add_cookie(self, cookie):
        self.cookies.append(dict(cookie))

    def quit(self):
        self.closed = True


@pytest.mark.parametrize("headless", [False, True])
def test_initial_and_replacement_browsers_are_ready_before_navigation(
    monkeypatch, tmp_path, headless
):
    initial, replacement = StartupDriver(), StartupDriver()
    drivers = iter([initial, replacement])
    monkeypatch.setattr(webdriver, "Chrome", lambda **_kwargs: next(drivers))
    monkeypatch.setattr("trains_app.time.sleep", lambda _seconds: None)
    downloader = MagazineDownloader(str(tmp_path), headless=headless)

    downloader._navigate("https://www.trains.com/")
    downloader._session_cookies = [{"name": "session", "value": "synthetic"}]
    assert downloader._restart_browser()
    assert initial.closed
    assert replacement.visited == ["https://www.trains.com/"]
    assert replacement.cookies == downloader._session_cookies
    downloader.close()
    assert replacement.closed


def test_failed_browser_configuration_closes_the_new_session(monkeypatch, tmp_path):
    error = RuntimeError("Chrome protocol configuration failed")
    driver = StartupDriver(configuration_error=error)
    monkeypatch.setattr(webdriver, "Chrome", lambda **_kwargs: driver)

    with pytest.raises(RuntimeError, match="protocol configuration") as caught:
        MagazineDownloader(str(tmp_path))

    assert caught.value is error
    assert driver.closed
    assert not driver.visited
