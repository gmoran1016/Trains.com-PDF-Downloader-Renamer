# Trains.com Downloader UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Replace the cramped PyQt5 main window with a readable rail-archive workstation UI while preserving the downloader, trains.com archive integration, organizer, workers, settings, and system-tray behavior.

**Architecture:** Keep the single-file application boundary and all non-UI processing intact. Rebuild MainWindow around a header, navigation rail, stacked scrollable workflow pages, shared archive-access controls, and a resizable activity drawer. Keep existing widget attributes used by settings and worker slots, or provide explicit aliases while the new layout is introduced.

**Tech Stack:** Python 3.14 environment, PyQt5, pytest, Selenium downloader workers, pypdf organizer, PyInstaller.

**Spec:** docs/superpowers/specs/2026-09-12-ui-redesign-design.md

## Global Constraints

- Preserve MagazineDownloader, archive URL/link parsing, viewer download handling, cookie format, PDF parsing, organizer behavior, progress schema, and worker scheduling.
- Preserve the trains.com archive URLs, magazine identifiers, system tray semantics, close-while-running safety, existing settings keys, and default values.
- Support Model Railroader, Trains Magazine, Classic Toy Trains, Classic Trains, and Garden Railways.
- Keep the minimum supported window at 800×620 and prevent horizontal clipping at 800×620, 1040×760, and 1440×900.
- Use sentence-case labels, visible keyboard focus, accessible names, no emoji controls, no gradients, and no color-only state indicators.
- Run tests with .venv\Scripts\python.exe -m pytest.
- Create a fresh isolated worktree with the using-git-worktrees skill before implementation; do not edit the unrelated railshelf-v2 worktree.

---

### Task 1: Establish the new shell and UI contract

**Files:**
- Modify: trains_app.py imports, stylesheet, MainWindow.__init__, _build_ui, and UI helper methods.
- Modify: tests/test_ui_smoke.py shell tests.

**Interfaces:**
- Consumes: Existing MainWindow worker fields, settings fields, and logging/progress slots.
- Produces: _page_stack, _download_page, _organize_page, _download_nav_btn, _organize_nav_btn, _activity_nav_btn, _activity_splitter, _activity_panel, _header_status, _set_mode(mode: str), and _toggle_activity().

- [ ] Step 1: Write the failing shell tests.

~~~python
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
~~~

- [ ] Step 2: Run the focused tests and verify the expected failure.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -q
~~~

Expected failure: MainWindow does not yet expose the new page-stack and navigation attributes. Do not change production code until this failure is observed.

- [ ] Step 3: Replace the stylesheet and add the shell widgets.

Add the PyQt5 widgets required by the design: QCheckBox, QFrame, QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QToolButton, and QButtonGroup where used. Replace the dark stylesheet with a light token-based stylesheet using paper #F4F1EA, surface #FFFDF8, ink #182126, muted #53636A, line #C9C4B8, navy #203B4A, and amber #C7792B. Style focused, disabled, selected, success, warning, and failure states with text and borders in addition to color.

- [ ] Step 4: Implement the shell without changing worker behavior.

Replace _build_ui with a header, navigation rail, stacked pages, and activity splitter:

~~~python
self.setWindowTitle(f"Trains.com Magazine Downloader & Organizer v{APP_VERSION}")
self.resize(1040, 760)
self.setMinimumSize(800, 620)
self._page_stack = QStackedWidget()
self._download_page = self._make_download_page()
self._organize_page = self._make_organize_page()
self._page_stack.addWidget(self._download_page)
self._page_stack.addWidget(self._organize_page)
self._activity_panel = self._make_activity_panel()
self._activity_splitter = QSplitter(Qt.Vertical)
self._activity_splitter.addWidget(workspace)
self._activity_splitter.addWidget(self._activity_panel)
self._activity_splitter.setStretchFactor(0, 1)
self._activity_splitter.setStretchFactor(1, 0)
self._activity_splitter.setSizes([520, 190])
~~~

Use QScrollArea inside both pages. _set_mode changes the stack, selected navigation state, page title/description, and scroll position without destroying either page. _toggle_activity expands or contracts the drawer.

- [ ] Step 5: Run focused tests and compile.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -q
.\.venv\Scripts\python.exe -m compileall -q trains_app.py tests
~~~

Expected: the new shell tests pass; old tests that assert the chip/grid layout may still fail and are updated in Task 2.

- [ ] Step 6: Commit the shell slice.

~~~powershell
git add trains_app.py tests/test_ui_smoke.py
git commit -m "feat: replace main window shell with archive workstation layout"
~~~

### Task 2: Build the Download page and magazine selection flow

**Files:**
- Modify: trains_app.py with _make_download_page, _make_magazine_row, _make_path_card, _make_advanced_options, and action-bar helpers.
- Modify: trains_app.py settings signal connections for the new controls.
- Modify: tests/test_ui_smoke.py download-page tests.

**Interfaces:**
- Consumes: Task 1 shell, existing MAGAZINES, settings keys, and download slots.
- Produces: mag_chips as dict[str, QCheckBox], magazine_rows, select_all_btn, clear_all_btn, dir_edit, headless_cb, test_cb, specials_cb, sort_combo, start_btn, stop_btn, _clear_btn, and download_validation.

- [ ] Step 1: Write failing tests for magazine rows and download controls.

~~~python
def test_download_page_has_readable_magazine_rows_and_primary_controls(window):
    assert set(window.mag_chips) == set(MAGAZINES)
    assert len(window.magazine_rows) == 5
    assert window.select_all_btn.isVisible()
    assert window.clear_all_btn.isVisible()
    assert window.start_btn.text() == "Start download"
    assert window.dir_edit.isVisible()
    assert window.cookie_edit.isVisible()
    assert window.headless_cb.isVisible()
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
~~~

Import MAGAZINES from trains_app in the test module and remove assertions that require magazine_grid.

- [ ] Step 2: Run the focused tests and verify the expected failure.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -k "download_page or select_all" -q
~~~

Expected failure: the new row and action attributes do not yet exist.

- [ ] Step 3: Add display metadata and reusable builders.

Add this UI-only mapping without changing archive behavior:

~~~python
MAGAZINE_SCHEDULE = {
    "Model Railroader": "Monthly",
    "Trains Magazine": "Monthly",
    "Classic Toy Trains": "Monthly",
    "Classic Trains": "Quarterly",
    "Garden Railways": "Seasonal / archived",
}
~~~

Implement _make_section_heading, _make_card, _make_path_card, and _make_magazine_row. Each magazine row must contain a QCheckBox, full title, prefix, schedule, and an accessible name such as Select Model Railroader magazine.

- [ ] Step 4: Implement the Download page.

Build the scrollable page with a page header, selection card, Select all/Clear all actions, five rows, destination card, expandable Advanced options card, inline validation label, and action bar. Keep mag_chips as the settings mapping. Keep dir_edit, headless_cb, test_cb, specials_cb, sort_combo, start_btn, stop_btn, and _clear_btn as the existing handler-facing attributes.

- [ ] Step 5: Update validation and busy-state presentation.

Before the existing warning dialogs, set an inline validation message:

~~~python
if not magazines:
    self.download_validation.setText("Select at least one magazine to continue.")
    QMessageBox.warning(self, "Nothing selected", "Select at least one magazine.")
    return
if not base_dir:
    self.download_validation.setText("Choose a save location to continue.")
    QMessageBox.warning(self, "No folder", "Please choose a save location.")
    return
self.download_validation.clear()
~~~

When a worker starts, disable magazine selection, destination, and advanced options; re-enable them in _on_finished. Keep Start/Stop enablement aligned with worker state.

- [ ] Step 6: Run tests and commit.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -k "download_page or select_all or accessible" -q
git add trains_app.py tests/test_ui_smoke.py
git commit -m "feat: rebuild download workflow for clarity"
~~~

### Task 3: Build the Organize page and visible result summary

**Files:**
- Modify: trains_app.py with _make_organize_page, summary helpers, and organizer lifecycle UI updates.
- Modify: tests/test_ui_smoke.py organizer-page and summary tests.

**Interfaces:**
- Consumes: Task 1 shell, shared access controls, OrganizeSummary, and _missing_download_selection.
- Produces: src_edit, dst_edit, prefix_combo, org_btn, dl_missing_btn, dl_missing_stop_btn, _organize_summary, _organize_summary_tiles, _missing_summary, and _render_organize_summary(summary).

- [ ] Step 1: Write failing tests for organizer inputs and result tiles.

~~~python
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
    summary = OrganizeSummary(
        moved=4, already_correct=2, unrecognized=1, corrupt=1,
        conflicts=1, metadata_stamped=5,
        missing_by_prefix_year={"MRR": {"2025": ["March", "April"]}},
    )
    window._render_organize_summary(summary)
    qt_app.processEvents()
    assert window._organize_summary.isVisible()
    assert window._organize_summary_tiles["Moved"].text() == "4"
    assert "2 missing" in window._missing_summary.text()
    assert window.dl_missing_btn.isEnabled()
~~~

Import OrganizeSummary in the test module.

- [ ] Step 2: Run the focused tests and verify the expected failure.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -k "organize_page or organize_summary" -q
~~~

Expected failure: the new summary helper and attributes do not exist.

- [ ] Step 3: Implement the Organize page.

Use source and destination path cards, a magazine identification card with Auto-detect plus the five prefixes, an initially hidden result summary card, and an action bar with Organize PDFs, Download missing issues, and Stop. Place org_headless_cb in the organization page access context with helper text saying it applies to missing-issue downloads.

- [ ] Step 4: Implement result tiles and missing-issue presentation.

Create six result tiles keyed exactly as Moved, Already correct, Unrecognized, Corrupt, Conflicts, and Metadata updated. Add:

~~~python
def _render_organize_summary(self, summary: OrganizeSummary) -> None:
    values = {
        "Moved": summary.moved,
        "Already correct": summary.already_correct,
        "Unrecognized": summary.unrecognized,
        "Corrupt": summary.corrupt,
        "Conflicts": summary.conflicts,
        "Metadata updated": summary.metadata_stamped,
    }
    for label, value in values.items():
        self._organize_summary_tiles[label].setText(str(value))
    self._organize_summary.show()
    self._org_prefix, self._missing_by_year = _missing_download_selection(summary)
    missing_count = sum(len(months) for months in self._missing_by_year.values())
    if missing_count and self._org_prefix:
        self._missing_summary.setText(
            f"{missing_count} missing issue(s) identified for {self._org_prefix}."
        )
        self.dl_missing_btn.setEnabled(True)
    else:
        self._missing_summary.setText("No downloadable missing issues identified.")
        self.dl_missing_btn.setEnabled(False)
~~~

For multiple detected publications, preserve the existing safety log message and keep missing download disabled.

- [ ] Step 5: Wire organizer lifecycle and commit.

At the beginning of _run_organize, hide/reset the result summary, disable organizer inputs, and reset progress. In _on_organize_finished, re-enable inputs, call _render_organize_summary, and retain the complete report in the activity log.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -k "organize_page or organize_summary" -q
git add trains_app.py tests/test_ui_smoke.py
git commit -m "feat: surface organizer results and missing issues"
~~~

### Task 4: Add shared Archive access, activity drawer, and state synchronization

**Files:**
- Modify: trains_app.py with _make_archive_access, _make_activity_panel, status helpers, and worker lifecycle slots.
- Modify: tests/test_ui_smoke.py activity, status, progress, and accessibility tests.

**Interfaces:**
- Consumes: Tasks 1–3 and existing worker signals.
- Produces: _make_archive_access(), _make_activity_panel(), _set_job_state(state: str, detail: str = ""), _sync_busy_controls(busy: bool), and the existing log/progress attributes in their new locations.

- [ ] Step 1: Write failing tests for access and activity behavior.

~~~python
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
~~~

Import the listed Qt widget classes in the test module.

- [ ] Step 2: Run the focused tests and verify the expected failure.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -k "archive_access or status_state or accessible_names" -q
~~~

Expected failure: the new builders and state helper do not exist.

- [ ] Step 3: Implement the shared Archive access card.

Create _make_archive_access() with the shared cookie_edit, cookie browse button, subscription guidance, and contextual headless_cb/org_headless_cb controls. Keep DEFAULT_COOKIES_FILE, cookies_path, headless, and org_headless settings keys unchanged.

- [ ] Step 4: Implement the activity drawer.

Move the existing log toolbar and QTextEdit into _make_activity_panel(). Keep _raw_log_lines, _refresh_log, _copy_errors, _clear_log, _colorize, and error counting behavior. Add the compact header, progress bar, status label, dynamic per-magazine rows, filter, copy errors, clear, and log controls. Use a default height around 190 and a maximum around 360.

- [ ] Step 5: Implement job-state synchronization.

Use the states ready, running, success, failed, cancelled, and empty. Implement:

~~~python
def _set_job_state(self, state: str, detail: str = "") -> None:
    labels = {
        "ready": "Ready",
        "running": "Running",
        "success": "Complete",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "empty": "No results",
    }
    text = labels.get(state, "Ready")
    if detail:
        text = f"{text} · {detail}"
    self._header_status.setText(text)
    self._header_status.setAccessibleName(f"Job status: {text}")
    self.status_label.setText(text)
    self._header_status.setProperty("state", state)
    self._header_status.style().unpolish(self._header_status)
    self._header_status.style().polish(self._header_status)
~~~

Call it from download, organize, and missing-issue starts and finished slots. _sync_busy_controls must disable only inputs that would invalidate the active job and must never disable the active Stop button.

- [ ] Step 6: Update lifecycle methods and run tests.

Update only the UI state calls in _start_download, _stop_download, _on_error, _on_finished, _run_organize, _on_organize_finished, _start_missing_download, _stop_missing_download, and _on_missing_finished. Do not alter worker construction arguments or signal names.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -q
git add trains_app.py tests/test_ui_smoke.py
git commit -m "feat: add shared archive access and activity state UI"
~~~

### Task 5: Visual regression harness, documentation, and accessibility polish

**Files:**
- Create: tests/render_ui.py screenshot harness writing only to UI_SCREENSHOT_DIR.
- Modify: tests/test_ui_smoke.py compact-layout, focus, and visible-control assertions.
- Modify: README.md UI feature descriptions.
- Modify: trains_app.py only for issues found by focused tests or screenshot inspection.

**Interfaces:**
- Consumes: Completed shell and workflow pages from Tasks 1–4.
- Produces: repeatable screenshots for 800×620, 1040×760, and 1440×900 and matching documentation.

- [ ] Step 1: Add the render harness.

Create tests/render_ui.py:

~~~python
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
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
~~~

- [ ] Step 2: Add compact-layout and documentation assertions.

Assert that both page scroll areas exist, all five magazine title labels fit within their rows, the activity drawer remains visible, and all primary buttons remain visible at 800×620. Keep the existing log filter/error badge/copy test and update button-label assertions to sentence case.

- [ ] Step 3: Render and inspect screenshots.

~~~powershell
$env:UI_SCREENSHOT_DIR = "C:/tmp/trains-ui-redesign"
Remove-Item -LiteralPath $env:UI_SCREENSHOT_DIR -Recurse -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe tests/render_ui.py
~~~

Use the image viewer on all six screenshots. Check for clipped text, horizontal scrollbars, unreadable muted text, action hierarchy, excessive empty space, and a log drawer that overwhelms the page. If a problem is found, add a focused test first, then change the smallest UI surface and rerender.

- [ ] Step 4: Update README UI documentation.

Replace the old UI bullet with:

~~~markdown
- **Workstation UI** — separate Download and Organize workflows with readable magazine rows, shared archive access, and a resizable activity drawer
- **Visible organizer results** — moved, existing, unrecognized, corrupt, conflict, metadata, and missing-issue counts are shown in the workspace
~~~

Retain the existing authentication, archive, organizer, and supported-magazine documentation.

- [ ] Step 5: Run focused tests and commit.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_smoke.py -q
git diff --check
git add trains_app.py tests/test_ui_smoke.py tests/render_ui.py README.md
git commit -m "test: add rendered UI checks and update usage documentation"
~~~

### Task 6: Full regression, package build, and release verification

**Files:**
- Verify: trains_app.py, tests/, README.md, build.bat, and .github/workflows/build.yml.
- Generated outside the repository: C:/tmp/trains-ui-redesign/ screenshots and PyInstaller work/spec directories.
- Generated in the repository: ignored dist/ and build/ outputs.

**Interfaces:**
- Consumes: All redesigned UI slices and updated tests.
- Produces: a verified source tree and packaged dist/TrainsDownloader.exe built from the redesigned code.

- [ ] Step 1: Run complete test and static verification.

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
.\.venv\Scripts\python.exe -m compileall -q trains_app.py tests
.\.venv\Scripts\python.exe -m pip check
git diff --check
~~~

Expected: zero test failures, no compile errors, no broken requirements, and no whitespace errors.

- [ ] Step 2: Confirm backend/archive code was not unintentionally modified.

Review the diff around MagazineDownloader, DownloadWorker, MissingIssuesWorker, organize_pdfs, and archive constants. Changes in those regions must be limited to UI-facing calls or existing attribute references required to synchronize state. Run:

~~~powershell
.\.venv\Scripts\python.exe -m pytest tests/test_downloader_integration.py tests/test_trains_app.py -q
~~~

- [ ] Step 3: Build the Windows executable.

Run:

~~~powershell
cmd /c build.bat
~~~

If the final pause is unsuitable for automation, run the equivalent PyInstaller command without pause, using the same collection arguments in build.bat, and write dist\TrainsDownloader.exe.

- [ ] Step 4: Run packaged startup smoke test.

Launch the exact dist\TrainsDownloader.exe with Start-Process -WindowStyle Hidden -PassThru, wait five seconds, verify it remains alive, then stop the parent and any child whose executable path is that exact artifact. Record artifact size and SHA-256.

- [ ] Step 5: Final verification and commit.

~~~powershell
git status --short --branch
git log -5 --oneline
git worktree list
git diff HEAD~5 --stat
~~~

Confirm the source tree is clean apart from ignored build output, the unrelated worktree is untouched, the packaged smoke passed, and all six screenshots were manually inspected before reporting the redesign complete.
