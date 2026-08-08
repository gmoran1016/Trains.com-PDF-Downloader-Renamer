import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QLabel

from trains_app import MainWindow, _STYLESHEET


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


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
