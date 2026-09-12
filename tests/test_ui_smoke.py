import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
)

from trains_app import APP_VERSION, MAGAZINES, MainWindow, OrganizeSummary, _STYLESHEET


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


def test_release_version_is_bumped_and_visible_in_window_chrome(window):
    assert APP_VERSION == "1.8.1"
    assert "v1.8.1" in window.windowTitle()
    assert any(label.text() == "v1.8.1" for label in window.findChildren(QLabel))


def test_high_end_palette_uses_paper_ink_and_copper_tokens(qapp):
    window = MainWindow()
    try:
        assert "background-color: #F6F3EC;" in _STYLESHEET
        assert "background: #FFFCF7;" in _STYLESHEET
        assert 'QPushButton[role="primary"] { background: #A95530;' in _STYLESHEET
        assert "#183B49" in _STYLESHEET
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


def test_download_page_has_readable_magazine_rows_and_primary_controls(window):
    assert set(window.mag_chips) == set(MAGAZINES)
    assert len(window.magazine_rows) == 5
    assert window.select_all_btn.isVisible()
    assert window.clear_all_btn.isVisible()
    assert window.start_btn.text() == "Start download"
    assert window.dir_edit.isVisible()
    assert window.cookie_edit.isVisible()
    assert window.headless_cb.isVisible()
    assert not window.org_headless_cb.isVisible()
    assert window.test_cb.isVisible()
    assert window.specials_cb.isVisible()
    assert window.sort_combo.isVisible()


def test_select_all_and_clear_all_preserve_settings_mapping(window, qt_app):
    window.clear_all_btn.click()
    qt_app.processEvents()
    assert not any(button.isChecked() for button in window.mag_chips.values())
    window.select_all_btn.click()
    qt_app.processEvents()
    assert all(button.isChecked() for button in window.mag_chips.values())


def test_organize_page_exposes_contextual_inputs(window):
    window._organize_nav_btn.click()
    assert window.src_edit.isVisible()
    assert window.dst_edit.isVisible()
    assert window.prefix_combo.isVisible()
    assert window.prefix_combo.currentText() == "Auto-detect"
    assert window.org_btn.text() == "Organize PDFs"
    assert window.dl_missing_btn.text() == "Download missing issues"
    assert window.org_headless_cb.isVisible()


def test_organize_summary_renders_counts_and_missing_state(window, qt_app):
    window._organize_nav_btn.click()
    summary = OrganizeSummary(
        moved=4,
        already_correct=2,
        unrecognized=1,
        corrupt=1,
        conflicts=1,
        metadata_stamped=5,
        missing_by_prefix_year={"MRR": {"2025": ["March", "April"]}},
    )
    window._render_organize_summary(summary)
    qt_app.processEvents()
    assert window._organize_summary.isVisible()
    assert window._organize_summary_tiles["Moved"].text() == "4"
    assert "2 missing" in window._missing_summary.text()
    assert window.dl_missing_btn.isEnabled()


def test_archive_access_is_shared_and_activity_is_resizable(window, qt_app):
    assert window.cookie_edit.accessibleName() == "Cookie file path"
    assert window._activity_panel.isVisible()
    assert window.log_filter.isVisible()
    assert window.copy_errors_btn.isVisible()
    initial = window._activity_splitter.sizes()
    window._toggle_activity()
    qt_app.processEvents()
    assert window._activity_splitter.sizes()[1] > initial[1]


def test_status_state_is_textual_and_not_color_only(window):
    window._set_job_state("running", "Scanning 3 of 10")
    assert "Scanning 3 of 10" in window._header_status.text()
    assert "running" in window._header_status.accessibleName().lower()
    window._set_job_state("failed", "Login timed out")
    assert "Login timed out" in window._header_status.text()


def test_all_visible_interactive_controls_have_accessible_names(window):
    controls = window.findChildren(
        (QPushButton, QToolButton, QCheckBox, QComboBox, QLineEdit)
    )
    assert controls
    assert all(control.accessibleName() for control in controls if control.isVisible())


def test_compact_layout_keeps_workflows_and_activity_available(window, qt_app):
    window.resize(800, 620)
    window.show()
    qt_app.processEvents()
    assert window.width() >= 800
    assert window.height() >= 620
    assert window.findChild(type(window._download_page), "download_scroll") is not None
    assert window.findChild(type(window._organize_page), "organize_scroll") is not None
    assert window.start_btn.isVisible()
    assert window._activity_panel.isVisible()
    assert not window._page_stack.currentWidget().horizontalScrollBar().isVisible()
    assert all(row.width() > 0 for row in window.magazine_rows.values())


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


def test_magazine_selector_rows_and_section_cards_have_contrast_support(qapp):
    window = MainWindow()
    try:
        window.resize(800, 620)
        window.show()
        qapp.processEvents()
        assert window.width() >= 800
        assert window.height() >= 620
        assert all(button.isVisible() for button in window.mag_chips.values())
        assert len(window.magazine_rows) == 5
        assert all(row.isVisible() for row in window.magazine_rows.values())
        assert "QFrame[role=\"card\"]" in _STYLESHEET
        assert "#F6F3EC" in _STYLESHEET
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
    assert 'QPushButton[role="primary"]:disabled' in _STYLESHEET
    assert 'QPushButton[role="danger"]:disabled' in _STYLESHEET


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
