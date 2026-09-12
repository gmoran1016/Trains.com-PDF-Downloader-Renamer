import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QLabel

from trains_app import MainWindow, _STYLESHEET


def test_redesigned_shell_has_scrollable_pages_and_navigation(qapp):
    window = MainWindow()
    try:
        assert window.minimumWidth() >= 800
        assert window.minimumHeight() >= 620
        assert window._page_stack.count() == 2
        assert window._download_page is window._page_stack.widget(0)
        assert window._organize_page is window._page_stack.widget(1)
        assert window._download_nav_btn.isCheckable()
        assert window._organize_nav_btn.isCheckable()
        assert window._activity_nav_btn.isCheckable()
        assert window._download_nav_btn.isChecked()
        assert window._header_status.text()
    finally:
        window.close()
        window.deleteLater()


def test_navigation_switches_workflow_pages(qapp):
    window = MainWindow()
    try:
        assert window._page_stack.currentWidget() is window._download_page
        window._organize_nav_btn.click()
        qapp.processEvents()
        assert window._page_stack.currentWidget() is window._organize_page
        assert window._organize_nav_btn.isChecked()
        window._download_nav_btn.click()
        qapp.processEvents()
        assert window._page_stack.currentWidget() is window._download_page
    finally:
        window.close()
        window.deleteLater()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def qt_app(qapp):
    return qapp


@pytest.fixture
def window(qt_app):
    win = MainWindow()
    win.show()
    qt_app.processEvents()
    yield win
    win.close()
    qt_app.processEvents()


def test_first_launch_guidance_distinguishes_browser_modes(qapp):
    window = MainWindow()
    try:
        labels = [label.text().lower() for label in window.findChildren(QLabel)]
        assert window.headless_cb.text() == "Hide download browser"
        assert window.org_headless_cb.text() == (
            "Hide browser for missing-issue downloads"
        )
        assert any(
            "subscription" in label and "cookie" in label
            for label in labels
        )
    finally:
        window.close()
        window.deleteLater()


def test_magazine_selector_wraps_and_section_labels_have_contrast_support(qapp):
    window = MainWindow()
    try:
        window.resize(640, 520)
        window.show()
        qapp.processEvents()
        assert window.width() >= 640
        assert window.height() >= 520
        assert all(button.isVisible() for button in window.mag_chips.values())
        assert hasattr(window, "magazine_grid")
        rows = {
            window.magazine_grid.getItemPosition(index)[0]
            for index in range(window.magazine_grid.count())
        }
        assert len(rows) > 1
        assert "QLabel[role=\"section\"]" in _STYLESHEET
        assert "color: #a6adc8" in _STYLESHEET
    finally:
        window.close()
        window.deleteLater()


def test_action_controls_have_accessible_names_and_plain_text(window):
    controls = (
        window.start_btn,
        window.stop_btn,
        window._clear_btn,
        window._dl_mode_btn,
        window._org_mode_btn,
        window.cookie_edit,
        window.dir_edit,
        window.headless_cb,
        window.test_cb,
        window.specials_cb,
        window.sort_combo,
    )
    assert all(control.accessibleName() for control in controls)
    assert not any(icon in window.start_btn.text() for icon in ("▶", "■", "⬇"))
    assert not any(icon in window.stop_btn.text() for icon in ("▶", "■", "⬇"))


def test_log_filter_copy_errors_and_badge(window, qt_app):
    assert window.log_filter is not None
    assert window.copy_errors_btn is not None
    assert window.error_badge.text().startswith("0")

    window._log("Downloaded: good.pdf")
    window._log("FAILED: bad.pdf")
    qt_app.processEvents()

    assert window.error_badge.text().startswith("1")
    window.copy_errors_btn.click()
    assert "FAILED: bad.pdf" in QApplication.clipboard().text()

    window.log_filter.setText("good")
    qt_app.processEvents()
    assert "good.pdf" in window.log.toPlainText()
    assert "bad.pdf" not in window.log.toPlainText()


def test_magazine_progress_update_creates_visible_row(window, qt_app):
    window._update_magazine_progress("Model Railroader", 2, 5)
    qt_app.processEvents()

    row, bar, count = window._magazine_progress_rows["Model Railroader"]
    assert row.isVisible()
    assert bar.value() == 2
    assert bar.maximum() == 5
    assert count.text() == "2 / 5"


def test_minimum_window_keeps_log_toolbar_and_log_visible(window, qt_app):
    window.resize(640, 520)
    qt_app.processEvents()

    assert window.log_filter.isVisible()
    assert window.copy_errors_btn.isVisible()
    assert window.log.isVisible()
    assert window.log.height() > 0
