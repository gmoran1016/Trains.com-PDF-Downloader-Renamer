import os
import sys

# The offscreen Qt plugin on this host paints widget chrome but drops glyphs.
# Use the native Windows plugin for screenshot QA; unit tests remain headless.
os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtWidgets import QApplication

from trains_app import MainWindow


def main():
    output = Path(os.environ.get("UI_SCREENSHOT_DIR", "C:/tmp/trains-ui-screenshots"))
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    for width, height in ((800, 620), (1040, 760), (1440, 900)):
        window.resize(width, height)
        app.processEvents()
        window.grab().save(str(output / f"download-{width}x{height}.png"))
        window._organize_nav_btn.click()
        app.processEvents()
        window.grab().save(str(output / f"organize-{width}x{height}.png"))
        window._download_nav_btn.click()
    window.close()


if __name__ == "__main__":
    main()
