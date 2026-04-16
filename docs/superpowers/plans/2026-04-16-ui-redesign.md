# UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-tab PyQt5 UI with a cleaner single-window layout using a mode toggle, chip-style magazine selection, shared authentication row, and plain log area.

**Architecture:** All changes are confined to `MainWindow` and `_STYLESHEET` inside `trains_app.py`. No backend logic, workers, or non-UI functions are touched. The UI is restructured but all existing signal/slot wiring is preserved with updated widget references.

**Tech Stack:** Python 3.10+, PyQt5

---

## Widget Reference Map (old → new)

| Old | New | Notes |
|---|---|---|
| `self.mag_checks` (dict[str,QCheckBox]) | `self.mag_chips` (dict[str,QPushButton]) | Checkable buttons, styled as chips |
| `self.dl_log` + `self.org_log` | `self.log` | Single unified QTextEdit |
| `self._dl_log_lines`, `self._org_log_lines` | *(removed)* | Log buffer removed with filter |
| `self._dl_filter`, `self._org_filter` | *(removed)* | No log filter |
| `self._dl_error_badge`, `self._org_error_badge` | *(removed)* | No error badge |
| `self._dl_copy_errors_btn`, `self._org_copy_errors_btn` | *(removed)* | No copy-errors button |
| `self._progress_container` + `self._mag_bar_rows` | *(removed)* | Per-mag bars gone |
| `self._summary_label` | `self.status_label` | Combined into one status label |
| `self.status_label` | `self.status_label` | Same name, same purpose |
| `self.org_progress` | `self.progress_bar` | Single shared progress bar |
| `self.org_run_btn` | `self.org_btn` | Renamed |
| `self.org_cookie_edit` | *(removed)* | `self.cookie_edit` is now shared |
| `self.org_headless_cb` | `self.org_headless_cb` | Moves to shared auth row |

---

## Task 1: Version bump

**Files:**
- Modify: `trains_app.py` (line with `APP_VERSION`)

- [ ] **Step 1: Change version**

In `trains_app.py`, find and replace:
```python
APP_VERSION = "1.5.0"
```
with:
```python
APP_VERSION = "1.6.0"
```

- [ ] **Step 2: Verify**

```bash
grep "APP_VERSION" trains_app.py
```
Expected output: `APP_VERSION = "1.6.0"`

- [ ] **Step 3: Commit**

```bash
git add trains_app.py
git commit -m "chore: bump version to 1.6.0"
```

---

## Task 2: Update `_STYLESHEET`

Remove QGroupBox, QTabWidget, and log-cap styles. Add chip button and mode toggle styles.

**Files:**
- Modify: `trains_app.py` — replace `_STYLESHEET` constant entirely

- [ ] **Step 1: Replace `_STYLESHEET`**

Find the line `_STYLESHEET = """` through the closing `"""` (ends around line 1895) and replace the entire constant with:

```python
_STYLESHEET = """
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QDialog { background-color: #13131f; }
QWidget { color: #cdd6f4; font-family: "Segoe UI", system-ui, sans-serif; font-size: 10pt; background-color: transparent; }

/* ── Inputs ───────────────────────────────────────────────────────────── */
QLineEdit, QComboBox {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    min-height: 28px;
}
QLineEdit:focus, QComboBox:focus { border-color: #89b4fa; background: #2a2a42; }
QLineEdit:disabled, QComboBox:disabled { background: #181825; color: #45475a; }
QLineEdit::placeholder { color: #585b70; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { width: 10px; height: 10px; }
QComboBox QAbstractItemView {
    background: #252538;
    border: 1px solid #45475a;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
    outline: none;
    padding: 2px;
}

/* ── Buttons — base ───────────────────────────────────────────────────── */
QPushButton {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 6px;
    padding: 6px 16px;
    color: #a6adc8;
    font-weight: 500;
    min-height: 28px;
}
QPushButton:hover  { background: #2e2e48; border-color: #89b4fa; color: #cdd6f4; }
QPushButton:pressed { background: #383858; }
QPushButton:disabled { background: #181825; color: #45475a; border-color: #252535; }

/* ── Buttons — primary ────────────────────────────────────────────────── */
QPushButton[role="primary"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #97c0ff, stop:1 #7aa2f7);
    border: none;
    border-bottom: 2px solid #5a7fd0;
    border-radius: 6px;
    color: #11111b;
    font-weight: 700;
    letter-spacing: 0.02em;
    min-height: 34px;
}
QPushButton[role="primary"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #aaceff, stop:1 #89b4fa);
}
QPushButton[role="primary"]:pressed  { background: #7aa2f7; border-bottom-width: 1px; }
QPushButton[role="primary"]:disabled { background: #252538; color: #45475a; border: 1px solid #252535; }

/* ── Buttons — danger ─────────────────────────────────────────────────── */
QPushButton[role="danger"] {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f5a0b8, stop:1 #e8708e);
    border: none;
    border-bottom: 2px solid #b85070;
    border-radius: 6px;
    color: #11111b;
    font-weight: 700;
    min-height: 34px;
}
QPushButton[role="danger"]:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f7b0c5, stop:1 #f38ba8);
}
QPushButton[role="danger"]:pressed  { background: #f38ba8; border-bottom-width: 1px; }
QPushButton[role="danger"]:disabled { background: #252538; color: #45475a; border: 1px solid #252535; }

/* ── Mode toggle buttons ──────────────────────────────────────────────── */
QPushButton[role="mode"] {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 8px 28px;
    color: #585b70;
    font-weight: 600;
    font-size: 10pt;
    min-height: 0;
}
QPushButton[role="mode"]:checked {
    background: #1e1e2e;
    border-color: #353550;
    color: #cdd6f4;
}
QPushButton[role="mode"]:hover:!checked { color: #a6adc8; }

/* ── Magazine chip buttons ────────────────────────────────────────────── */
QPushButton[role="chip"] {
    background: #252538;
    border: 1px solid #353550;
    border-radius: 20px;
    padding: 4px 14px;
    color: #585b70;
    font-weight: 400;
    font-size: 9.5pt;
    min-height: 0;
}
QPushButton[role="chip"]:checked {
    background: #2a3f6f;
    border-color: #89b4fa;
    color: #89b4fa;
    font-weight: 600;
}
QPushButton[role="chip"]:hover:!checked { border-color: #45475a; color: #a6adc8; }
QPushButton[role="chip"]:hover:checked  { background: #324878; }

/* ── Section labels ───────────────────────────────────────────────────── */
QLabel[role="section"] {
    color: #45475a;
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 0.1em;
}
QLabel[role="status"]  { color: #a6adc8; font-size: 9pt; }
QLabel[role="muted"]   { color: #585b70; font-size: 9pt; }
QLabel[role="app-name"] { color: #cdd6f4; font-size: 15pt; font-weight: 700; letter-spacing: -0.02em; }

/* ── Checkboxes ───────────────────────────────────────────────────────── */
QCheckBox { color: #cdd6f4; spacing: 8px; }
QCheckBox::indicator {
    width: 17px; height: 17px;
    border: 2px solid #484860;
    border-radius: 4px;
    background: #1e1e2e;
}
QCheckBox::indicator:hover   { border-color: #89b4fa; background: #252538; }
QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
QCheckBox::indicator:checked:hover { background: #a6c8ff; border-color: #a6c8ff; }

/* ── Progress bar ─────────────────────────────────────────────────────── */
QProgressBar {
    background: #252538;
    border: none;
    border-radius: 5px;
    min-height: 6px;
    max-height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89b4fa, stop:1 #cba6f7);
    border-radius: 5px;
}

/* ── Log area ─────────────────────────────────────────────────────────── */
QTextEdit {
    background: #0d0d17;
    border: 1px solid #252538;
    border-radius: 8px;
    color: #a6adc8;
    selection-background-color: #313244;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 9pt;
}

/* ── Scrollbars ───────────────────────────────────────────────────────── */
QScrollBar:vertical   { background: transparent; width: 7px; margin: 0; }
QScrollBar:horizontal { background: transparent; height: 7px; margin: 0; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #353550; border-radius: 3px; min-height: 20px; min-width: 20px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #45475a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; width: 0; }

/* ── Tooltips ─────────────────────────────────────────────────────────── */
QToolTip {
    background: #252538; border: 1px solid #45475a;
    color: #cdd6f4; padding: 5px 10px; border-radius: 5px;
}

/* ── Message boxes ────────────────────────────────────────────────────── */
QMessageBox { background: #1e1e2e; }
QMessageBox QLabel { color: #cdd6f4; }

/* ── Mode panel container ─────────────────────────────────────────────── */
QWidget#mode_panel {
    background: #1e1e2e;
    border: 1px solid #353550;
    border-radius: 0 8px 8px 8px;
}

/* ── Auth row ─────────────────────────────────────────────────────────── */
QWidget#auth_row {
    background: #1a1a2e;
    border: 1px solid #2a2a3e;
    border-radius: 6px;
}

/* ── Thin separator ──────────────────────────────────────────────────── */
QFrame[frameShape="4"] { color: #2a2a3e; }
QFrame[frameShape="5"] { color: #2a2a3e; }
"""
```

- [ ] **Step 2: Verify app still starts (stylesheet is pure CSS — no logic change)**

```bash
cd "$(git rev-parse --show-toplevel)"
python -c "from PyQt5.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from trains_app import _STYLESHEET; print('Stylesheet OK, length:', len(_STYLESHEET))"
```
Expected: prints `Stylesheet OK, length: <number>`

- [ ] **Step 3: Commit**

```bash
git add trains_app.py
git commit -m "style: overhaul stylesheet for single-window redesign"
```

---

## Task 3: Rewrite `MainWindow.__init__` and `_build_ui`

Replace the tab-based structure with a single-window layout: mode toggle at top, stacked panels, shared auth row, progress, and log.

**Files:**
- Modify: `trains_app.py` — `__init__`, `_build_ui`

- [ ] **Step 1: Update `__init__`**

Replace the `__init__` body (keeping the method signature `def __init__(self):`):

```python
def __init__(self):
    super().__init__()
    self.setWindowTitle(f"Trains.com Magazine Downloader & Organizer v{APP_VERSION}")
    self.resize(860, 720)
    self.setMinimumSize(640, 520)
    self.worker:           DownloadWorker | None      = None
    self._org_worker:      OrganizeWorker | None      = None
    self._missing_worker:  MissingIssuesWorker | None = None
    self._org_hint:        str | None                 = None
    self._org_dst:         str                        = ""
    self._org_prefix:      str | None                 = None
    self._missing_by_year: dict[str, list[str]]       = {}
    self._build_ui()
    self._load_settings()
    self._setup_tray()
```

- [ ] **Step 2: Rewrite `_build_ui`**

Replace the entire `_build_ui` method:

```python
def _build_ui(self):
    self.setStyleSheet(_STYLESHEET)
    root = QWidget()
    self.setCentralWidget(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(20, 20, 20, 16)
    layout.setSpacing(0)

    # ── Mode toggle ──────────────────────────────────────────────────────
    toggle_row = QHBoxLayout()
    toggle_row.setSpacing(2)
    toggle_row.setContentsMargins(0, 0, 0, 0)
    self._dl_mode_btn  = QPushButton("  Download  ")
    self._org_mode_btn = QPushButton("  Organize  ")
    for btn in (self._dl_mode_btn, self._org_mode_btn):
        btn.setProperty("role", "mode")
        btn.setCheckable(True)
        btn.setAutoExclusive(True)
    self._dl_mode_btn.setChecked(True)
    self._dl_mode_btn.clicked.connect(lambda: self._switch_mode("download"))
    self._org_mode_btn.clicked.connect(lambda: self._switch_mode("organize"))
    toggle_row.addWidget(self._dl_mode_btn)
    toggle_row.addWidget(self._org_mode_btn)
    toggle_row.addStretch()
    layout.addLayout(toggle_row)

    # ── Stacked mode panels ──────────────────────────────────────────────
    self._dl_panel  = self._make_download_panel()
    self._org_panel = self._make_organize_panel()
    for panel in (self._dl_panel, self._org_panel):
        panel.setObjectName("mode_panel")
        layout.addWidget(panel)
    self._org_panel.setVisible(False)

    layout.addSpacing(8)

    # ── Shared auth row ──────────────────────────────────────────────────
    auth_row = QWidget()
    auth_row.setObjectName("auth_row")
    auth_layout = QHBoxLayout(auth_row)
    auth_layout.setContentsMargins(12, 8, 12, 8)
    auth_layout.setSpacing(8)
    cookie_lbl = QLabel("COOKIE FILE")
    cookie_lbl.setProperty("role", "section")
    self.cookie_edit = QLineEdit(DEFAULT_COOKIES_FILE)
    cookie_browse = QPushButton("Browse…")
    cookie_browse.setFixedWidth(80)
    cookie_browse.clicked.connect(self._browse_cookies)
    self.org_headless_cb = QCheckBox("Headless browser")
    auth_layout.addWidget(cookie_lbl)
    auth_layout.addWidget(self.cookie_edit)
    auth_layout.addWidget(cookie_browse)
    auth_layout.addWidget(self.org_headless_cb)
    layout.addWidget(auth_row)

    layout.addSpacing(8)

    # ── Progress ─────────────────────────────────────────────────────────
    prog_row = QHBoxLayout()
    self.progress_bar = QProgressBar()
    self.progress_bar.setVisible(False)
    self.status_label = QLabel("")
    self.status_label.setProperty("role", "status")
    prog_row.addWidget(self.progress_bar)
    prog_row.addWidget(self.status_label)
    layout.addLayout(prog_row)

    layout.addSpacing(4)

    # ── Log ──────────────────────────────────────────────────────────────
    self.log = QTextEdit()
    self.log.setReadOnly(True)
    layout.addWidget(self.log)

    # Persist settings on any change
    self.cookie_edit.textChanged.connect(self._save_settings)
    self.org_headless_cb.stateChanged.connect(self._save_settings)
```

- [ ] **Step 3: Add `_switch_mode` helper**

Add this method to `MainWindow` (place it near `_build_ui`):

```python
def _switch_mode(self, mode: str):
    self._dl_panel.setVisible(mode == "download")
    self._org_panel.setVisible(mode == "organize")
```

- [ ] **Step 4: Add stub `_make_download_panel` and `_make_organize_panel`** so the app can launch

Add these two stub methods temporarily (they will be replaced in Tasks 4 and 5):

```python
def _make_download_panel(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(16, 16, 16, 16)
    # placeholders — replaced in Task 4
    self.mag_chips: dict[str, QPushButton] = {}
    self.dir_edit = QLineEdit(str(Path.home() / "Downloads" / "TrainsMagazines"))
    self.headless_cb = QCheckBox("Headless")
    self.test_cb = QCheckBox("Test mode")
    self.specials_cb = QCheckBox("Include special issues")
    self.specials_cb.setChecked(True)
    self.sort_combo = QComboBox()
    self.sort_combo.addItems(["Newest first", "Oldest first"])
    self.start_btn = QPushButton("▶  Start Download")
    self.start_btn.setProperty("role", "primary")
    self.start_btn.clicked.connect(self._start_download)
    self.stop_btn = QPushButton("■  Stop")
    self.stop_btn.setProperty("role", "danger")
    self.stop_btn.setEnabled(False)
    self.stop_btn.clicked.connect(self._stop_download)
    for w2 in (self.dir_edit, self.headless_cb, self.test_cb,
               self.specials_cb, self.sort_combo, self.start_btn, self.stop_btn):
        layout.addWidget(w2)
    return w

def _make_organize_panel(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(16, 16, 16, 16)
    # placeholders — replaced in Task 5
    self.src_edit = QLineEdit()
    self.dst_edit = QLineEdit()
    self.prefix_combo = QComboBox()
    self.prefix_combo.addItem("Auto-detect")
    for info in MAGAZINES.values():
        self.prefix_combo.addItem(info["prefix"])
    self.org_btn = QPushButton("▶  Organize PDFs")
    self.org_btn.setProperty("role", "primary")
    self.org_btn.clicked.connect(self._run_organize)
    self.dl_missing_btn = QPushButton("⬇  Download Missing Issues")
    self.dl_missing_btn.setEnabled(False)
    self.dl_missing_btn.clicked.connect(self._start_missing_download)
    self.dl_missing_stop_btn = QPushButton("■  Stop")
    self.dl_missing_stop_btn.setProperty("role", "danger")
    self.dl_missing_stop_btn.setEnabled(False)
    self.dl_missing_stop_btn.clicked.connect(self._stop_missing_download)
    for w2 in (self.src_edit, self.dst_edit, self.prefix_combo,
               self.org_btn, self.dl_missing_btn, self.dl_missing_stop_btn):
        layout.addWidget(w2)
    return w
```

- [ ] **Step 5: Launch the app and verify it opens without crashing**

```bash
python trains_app.py
```
Expected: window opens, shows Download/Organize toggle, no traceback.

- [ ] **Step 6: Commit**

```bash
git add trains_app.py
git commit -m "feat: replace tabs with single-window mode toggle (stub panels)"
```

---

## Task 4: Build the real Download panel

Replace the stub `_make_download_panel` with the full implementation using chips, section labels, and proper layout.

**Files:**
- Modify: `trains_app.py` — `_make_download_panel`

- [ ] **Step 1: Replace `_make_download_panel`**

```python
def _make_download_panel(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    # ── Magazines ────────────────────────────────────────────────────────
    mag_lbl = QLabel("MAGAZINES")
    mag_lbl.setProperty("role", "section")
    layout.addWidget(mag_lbl)
    chips_row = QHBoxLayout()
    chips_row.setSpacing(6)
    self.mag_chips: dict[str, QPushButton] = {}
    for name in MAGAZINES:
        btn = QPushButton(name)
        btn.setProperty("role", "chip")
        btn.setCheckable(True)
        btn.setChecked(True)
        btn.toggled.connect(self._save_settings)
        self.mag_chips[name] = btn
        chips_row.addWidget(btn)
    chips_row.addStretch()
    layout.addLayout(chips_row)

    # ── Save location ─────────────────────────────────────────────────────
    save_lbl = QLabel("SAVE LOCATION")
    save_lbl.setProperty("role", "section")
    layout.addWidget(save_lbl)
    save_row = QHBoxLayout()
    save_row.setSpacing(6)
    self.dir_edit = QLineEdit(str(Path.home() / "Downloads" / "TrainsMagazines"))
    browse_btn = QPushButton("Browse…")
    browse_btn.setFixedWidth(80)
    browse_btn.clicked.connect(self._browse_dir)
    save_row.addWidget(self.dir_edit)
    save_row.addWidget(browse_btn)
    layout.addLayout(save_row)

    # ── Options ───────────────────────────────────────────────────────────
    opts_lbl = QLabel("OPTIONS")
    opts_lbl.setProperty("role", "section")
    layout.addWidget(opts_lbl)
    opts_row = QHBoxLayout()
    opts_row.setSpacing(16)
    self.headless_cb = QCheckBox("Headless")
    self.headless_cb.setToolTip(
        "Run without a visible browser window.\nRequires a valid saved cookie file."
    )
    self.test_cb = QCheckBox("Test mode")
    self.specials_cb = QCheckBox("Special issues")
    self.specials_cb.setChecked(True)
    self.sort_combo = QComboBox()
    self.sort_combo.addItems(["Newest first", "Oldest first"])
    self.sort_combo.setFixedWidth(130)
    for widget in (self.headless_cb, self.test_cb, self.specials_cb):
        opts_row.addWidget(widget)
    opts_row.addWidget(self.sort_combo)
    opts_row.addStretch()
    layout.addLayout(opts_row)

    # ── Actions ───────────────────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    self.start_btn = QPushButton("▶  Start Download")
    self.start_btn.setProperty("role", "primary")
    self.start_btn.clicked.connect(self._start_download)
    self.stop_btn = QPushButton("■  Stop")
    self.stop_btn.setProperty("role", "danger")
    self.stop_btn.setEnabled(False)
    self.stop_btn.clicked.connect(self._stop_download)
    self._clear_btn = QPushButton("Clear Cache")
    self._clear_btn.clicked.connect(self._clear_progress)
    btn_row.addWidget(self.start_btn, 2)
    btn_row.addWidget(self.stop_btn, 1)
    btn_row.addWidget(self._clear_btn, 1)
    layout.addLayout(btn_row)

    layout.addStretch()

    # Persist settings on change
    self.dir_edit.textChanged.connect(self._save_settings)
    self.headless_cb.stateChanged.connect(self._save_settings)
    self.test_cb.stateChanged.connect(self._save_settings)
    self.specials_cb.stateChanged.connect(self._save_settings)
    self.sort_combo.currentIndexChanged.connect(self._save_settings)

    return w
```

- [ ] **Step 2: Launch and verify the Download panel looks correct**

```bash
python trains_app.py
```
Expected: Download mode shows chips for all 5 magazines, save location row, options row, and three action buttons. Chips toggle highlight on click.

- [ ] **Step 3: Commit**

```bash
git add trains_app.py
git commit -m "feat: implement download panel with chip magazine selection"
```

---

## Task 5: Build the real Organize panel

Replace the stub `_make_organize_panel`.

**Files:**
- Modify: `trains_app.py` — `_make_organize_panel`

- [ ] **Step 1: Replace `_make_organize_panel`**

```python
def _make_organize_panel(self) -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)

    # ── Source ───────────────────────────────────────────────────────────
    src_lbl = QLabel("SOURCE FOLDER")
    src_lbl.setProperty("role", "section")
    layout.addWidget(src_lbl)
    src_row = QHBoxLayout()
    src_row.setSpacing(6)
    self.src_edit = QLineEdit()
    self.src_edit.setPlaceholderText("Folder containing PDFs to organize…")
    src_browse = QPushButton("Browse…")
    src_browse.setFixedWidth(80)
    src_browse.clicked.connect(lambda: self._pick_dir(self.src_edit))
    src_row.addWidget(self.src_edit)
    src_row.addWidget(src_browse)
    layout.addLayout(src_row)

    # ── Destination ──────────────────────────────────────────────────────
    dst_lbl = QLabel("DESTINATION FOLDER")
    dst_lbl.setProperty("role", "section")
    layout.addWidget(dst_lbl)
    dst_row = QHBoxLayout()
    dst_row.setSpacing(6)
    self.dst_edit = QLineEdit()
    self.dst_edit.setPlaceholderText("Organized output folder (can be same as source)…")
    dst_browse = QPushButton("Browse…")
    dst_browse.setFixedWidth(80)
    dst_browse.clicked.connect(lambda: self._pick_dir(self.dst_edit))
    dst_row.addWidget(self.dst_edit)
    dst_row.addWidget(dst_browse)
    layout.addLayout(dst_row)

    # ── Prefix ───────────────────────────────────────────────────────────
    pfx_lbl = QLabel("MAGAZINE PREFIX")
    pfx_lbl.setProperty("role", "section")
    layout.addWidget(pfx_lbl)
    self.prefix_combo = QComboBox()
    self.prefix_combo.addItem("Auto-detect")
    for info in MAGAZINES.values():
        self.prefix_combo.addItem(info["prefix"])
    self.prefix_combo.setFixedWidth(140)
    self.prefix_combo.setToolTip("Force a specific magazine prefix when auto-detect fails")
    layout.addWidget(self.prefix_combo)

    # ── Actions ───────────────────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_row.setSpacing(8)
    self.org_btn = QPushButton("▶  Organize PDFs")
    self.org_btn.setProperty("role", "primary")
    self.org_btn.clicked.connect(self._run_organize)
    self.dl_missing_btn = QPushButton("⬇  Download Missing")
    self.dl_missing_btn.setEnabled(False)
    self.dl_missing_btn.clicked.connect(self._start_missing_download)
    self.dl_missing_stop_btn = QPushButton("■  Stop")
    self.dl_missing_stop_btn.setProperty("role", "danger")
    self.dl_missing_stop_btn.setEnabled(False)
    self.dl_missing_stop_btn.clicked.connect(self._stop_missing_download)
    btn_row.addWidget(self.org_btn, 2)
    btn_row.addWidget(self.dl_missing_btn, 2)
    btn_row.addWidget(self.dl_missing_stop_btn, 1)
    layout.addLayout(btn_row)

    layout.addStretch()

    # Persist settings on change
    self.src_edit.textChanged.connect(self._save_settings)
    self.dst_edit.textChanged.connect(self._save_settings)
    self.prefix_combo.currentIndexChanged.connect(self._save_settings)

    return w
```

- [ ] **Step 2: Launch and verify the Organize panel looks correct**

```bash
python trains_app.py
```
Expected: clicking Organize toggle shows source/dest folder rows, prefix combo, and three action buttons. Download toggle returns to chip view.

- [ ] **Step 3: Commit**

```bash
git add trains_app.py
git commit -m "feat: implement organize panel"
```

---

## Task 6: Simplify logging and update all slot methods

Replace the `_append_log`/`_rebuild_log`/`_copy_errors`/`_dl_log` machinery with a single `_log(msg)` method, and update all methods that call the old log infrastructure.

**Files:**
- Modify: `trains_app.py` — multiple methods in `MainWindow`

- [ ] **Step 1: Replace `_append_log`, `_rebuild_log`, `_copy_errors`, `_dl_log` with `_log`**

Remove these four methods entirely and add:

```python
def _log(self, msg: str, max_lines: int = 2000) -> None:
    self.log.append(self._colorize(msg))
    self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())
```

(`_colorize` is unchanged — keep it.)

- [ ] **Step 2: Update `_browse_cookies`**

Remove `_browse_org_cookies` entirely. The existing `_browse_cookies` method already sets `self.cookie_edit` — it's now shared, so nothing else needs to change there.

- [ ] **Step 3: Update `_clear_progress`**

```python
def _clear_progress(self):
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        self._log("Progress cache cleared.")
    else:
        self._log("No progress cache file found.")
```

- [ ] **Step 4: Update `_start_download`**

Replace the entire method:

```python
def _start_download(self):
    if self.worker is not None and self.worker.isRunning():
        return

    magazines = [n for n, btn in self.mag_chips.items() if btn.isChecked()]
    if not magazines:
        QMessageBox.warning(self, "Nothing selected", "Select at least one magazine.")
        return

    base_dir = self.dir_edit.text().strip()
    if not base_dir:
        QMessageBox.warning(self, "No folder", "Please choose a save location.")
        return

    cookies  = self.cookie_edit.text().strip() or None
    headless = self.headless_cb.isChecked()
    test     = self.test_cb.isChecked()
    newest   = self.sort_combo.currentText() == "Newest first"
    specials = self.specials_cb.isChecked()

    self.start_btn.setEnabled(False)
    self.stop_btn.setEnabled(True)
    self.progress_bar.setValue(0)
    self.progress_bar.setMaximum(1)
    self.progress_bar.setVisible(True)
    self.status_label.setText("Starting…")

    self._disconnect_worker(self.worker)
    self.worker = DownloadWorker(magazines, base_dir, headless, test, cookies, newest,
                                 include_specials=specials)
    self.worker.signals.log.connect(self._log)
    self.worker.signals.progress.connect(self._update_progress)
    self.worker.signals.status_msg.connect(self.status_label.setText)
    self.worker.signals.error.connect(self._on_error)
    self.worker.signals.finished.connect(self._on_finished)
    self.worker.start()
```

- [ ] **Step 5: Update `_stop_download`**

```python
def _stop_download(self):
    if self.worker:
        self.worker.stop()
        self._log("Stop requested — waiting for current issue to finish…")
    self.stop_btn.setEnabled(False)
```

- [ ] **Step 6: Replace `_update_progress` and remove `_update_mag_progress`**

Delete `_update_mag_progress` entirely. Replace `_update_progress`:

```python
def _update_progress(self, current: int, total: int):
    if total > 0:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"{current} / {total} issues")
        self._tray.setToolTip(f"Trains Downloader — {current} / {total} downloading…")
```

- [ ] **Step 7: Update `_on_error`**

```python
def _on_error(self, msg: str):
    self._log(f"ERROR: {msg}")
    QMessageBox.critical(self, "Error", msg)
```

- [ ] **Step 8: Update `_on_finished`**

```python
def _on_finished(self):
    self.start_btn.setEnabled(True)
    self.stop_btn.setEnabled(False)
    self.progress_bar.setVisible(False)
    self._log("--- Done ---")
    self.status_label.setText("Done.")
    self._tray.setToolTip("Trains Downloader — Idle")
```

- [ ] **Step 9: Update `_run_organize`**

```python
def _run_organize(self):
    if self._org_worker is not None and self._org_worker.isRunning():
        return

    src = self.src_edit.text().strip()
    dst = self.dst_edit.text().strip()
    if not src or not dst:
        QMessageBox.warning(self, "Missing folders", "Select both source and destination folders.")
        return
    pfx_text = self.prefix_combo.currentText()
    hint = None if pfx_text == "Auto-detect" else pfx_text

    self.log.clear()
    self._log(f"Organizing PDFs from: {src}")
    self._log(f"                  to: {dst}\n")

    self.org_btn.setEnabled(False)
    self.dl_missing_btn.setEnabled(False)
    self.progress_bar.setValue(0)
    self.progress_bar.setVisible(True)

    self._org_hint = hint
    self._org_dst  = dst
    self._disconnect_worker(self._org_worker)
    self._org_worker = OrganizeWorker(src, dst, hint)
    self._org_worker.signals.log.connect(self._log)
    self._org_worker.signals.progress.connect(self._update_org_progress)
    self._org_worker.signals.error.connect(
        lambda msg: QMessageBox.critical(self, "Organize error", msg)
    )
    self._org_worker.signals.finished.connect(self._on_organize_finished)
    self._org_worker.start()
```

- [ ] **Step 10: Update `_on_organize_finished`**

```python
def _on_organize_finished(self):
    self.org_btn.setEnabled(True)
    self.progress_bar.setVisible(False)

    if self._org_worker.result is None:
        return
    moved, already_correct, unrecognized, metadata_stamped, report = self._org_worker.result

    self._log(f"\n-- {moved} moved, {already_correct} already correct, "
              f"{unrecognized} unrecognized, {metadata_stamped} metadata updated --")
    for line in report:
        self._log(line)

    hint = self._org_hint
    dst  = self._org_dst

    self._missing_by_year: dict[str, list[str]] = {}
    for line in report:
        m = re.match(r"(\d{4}): missing (\[.*\])", line)
        if m:
            try:
                import ast
                self._missing_by_year[m.group(1)] = ast.literal_eval(m.group(2))
            except Exception:
                pass

    self._org_prefix: str | None = hint
    if not self._org_prefix:
        candidate = os.path.basename(os.path.normpath(dst)).upper()
        if candidate in PREFIX_TO_TITLE:
            self._org_prefix = candidate

    has_missing = bool(self._missing_by_year) and self._org_prefix and \
                  _archive_url_for_prefix(self._org_prefix) is not None
    self.dl_missing_btn.setEnabled(has_missing)
    if has_missing:
        total = sum(len(v) for v in self._missing_by_year.values())
        self._log(f"\n{total} missing issue(s) found — click 'Download Missing' to fetch them.")
```

- [ ] **Step 11: Update `_start_missing_download`**

```python
def _start_missing_download(self):
    if self._missing_worker is not None and self._missing_worker.isRunning():
        return

    dst = self.dst_edit.text().strip()
    if not dst or not self._org_prefix:
        return
    archive_url = _archive_url_for_prefix(self._org_prefix)
    if not archive_url:
        QMessageBox.warning(self, "Unknown magazine",
                            f"No archive URL found for prefix '{self._org_prefix}'.")
        return

    cookies  = self.cookie_edit.text().strip() or DEFAULT_COOKIES_FILE
    headless = self.org_headless_cb.isChecked()

    self.dl_missing_btn.setEnabled(False)
    self.dl_missing_stop_btn.setEnabled(True)
    self.progress_bar.setVisible(True)
    self.progress_bar.setValue(0)

    self._disconnect_worker(self._missing_worker)
    self._missing_worker = MissingIssuesWorker(
        prefix=self._org_prefix,
        archive_url=archive_url,
        missing_by_year=self._missing_by_year,
        dest_dir=dst,
        cookies_path=cookies,
        headless=headless,
    )
    self._missing_worker.signals.log.connect(self._log)
    self._missing_worker.signals.progress.connect(self._update_org_progress)
    self._missing_worker.signals.error.connect(
        lambda msg: QMessageBox.critical(self, "Error", msg)
    )
    self._missing_worker.signals.finished.connect(self._on_missing_finished)
    self._missing_worker.start()
```

- [ ] **Step 12: Update `_stop_missing_download`**

```python
def _stop_missing_download(self):
    if self._missing_worker is not None and self._missing_worker.isRunning():
        self._missing_worker.stop()
        self._log("Stop requested…")
    self.dl_missing_stop_btn.setEnabled(False)
```

- [ ] **Step 13: Update `_update_org_progress`**

```python
def _update_org_progress(self, current: int, total: int):
    if total > 0:
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
```

- [ ] **Step 14: Update `_on_missing_finished`**

```python
def _on_missing_finished(self):
    has_missing = bool(self._missing_by_year) and self._org_prefix and \
                  _archive_url_for_prefix(self._org_prefix) is not None
    self.dl_missing_btn.setEnabled(has_missing)
    self.dl_missing_stop_btn.setEnabled(False)
    self.progress_bar.setVisible(False)
    self._log("--- Download complete ---")
```

- [ ] **Step 15: Launch and verify no crashes**

```bash
python trains_app.py
```
Expected: app opens, both modes switch cleanly, no `AttributeError` in the console.

- [ ] **Step 16: Run existing tests**

```bash
pytest tests/ -v
```
Expected: all tests pass (they test backend logic only, no UI).

- [ ] **Step 17: Commit**

```bash
git add trains_app.py
git commit -m "refactor: simplify logging and rewire all slots to new widget names"
```

---

## Task 7: Update settings load/save

Update `_load_settings` and `_save_settings` to use the new widget names (`mag_chips`, merged `cookie_edit`, removed `org_cookie_edit`).

**Files:**
- Modify: `trains_app.py` — `_load_settings`, `_save_settings`

- [ ] **Step 1: Replace `_load_settings`**

```python
def _load_settings(self):
    s = load_settings()
    if "base_dir" in s:
        self.dir_edit.setText(s["base_dir"])
    if "cookies_path" in s:
        self.cookie_edit.setText(s["cookies_path"])
    if "headless" in s:
        self.headless_cb.setChecked(s["headless"])
    if "test_mode" in s:
        self.test_cb.setChecked(s["test_mode"])
    if "newest_first" in s:
        self.sort_combo.setCurrentIndex(0 if s["newest_first"] else 1)
    if "include_specials" in s:
        self.specials_cb.setChecked(s["include_specials"])
    if "selected_magazines" in s:
        sel = set(s["selected_magazines"])
        for name, btn in self.mag_chips.items():
            btn.setChecked(name in sel)
    if "org_src" in s:
        self.src_edit.setText(s["org_src"])
    if "org_dst" in s:
        self.dst_edit.setText(s["org_dst"])
    if "org_prefix" in s:
        idx = self.prefix_combo.findText(s["org_prefix"])
        if idx >= 0:
            self.prefix_combo.setCurrentIndex(idx)
    if "org_headless" in s:
        self.org_headless_cb.setChecked(s["org_headless"])
```

- [ ] **Step 2: Replace `_save_settings`**

```python
def _save_settings(self):
    save_settings({
        "base_dir":           self.dir_edit.text(),
        "cookies_path":       self.cookie_edit.text(),
        "headless":           self.headless_cb.isChecked(),
        "test_mode":          self.test_cb.isChecked(),
        "newest_first":       self.sort_combo.currentText() == "Newest first",
        "include_specials":   self.specials_cb.isChecked(),
        "selected_magazines": [n for n, btn in self.mag_chips.items() if btn.isChecked()],
        "org_src":            self.src_edit.text(),
        "org_dst":            self.dst_edit.text(),
        "org_prefix":         self.prefix_combo.currentText(),
        "org_headless":       self.org_headless_cb.isChecked(),
    })
```

- [ ] **Step 3: Launch, change settings, close and reopen — verify they persist**

```bash
python trains_app.py
```
Expected: deselect a magazine chip, set a save path, close the app, reopen — chip state and path should be restored.

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -v
```
Expected: all pass.

- [ ] **Step 5: Final commit**

```bash
git add trains_app.py
git commit -m "feat: update settings persistence for redesigned UI"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Single window (no tabs) — Tasks 3–5
- ✅ Mode toggle (Download/Organize) — Task 3
- ✅ Magazine chip buttons — Task 4
- ✅ Shared cookie file row — Task 3 (`_build_ui`)
- ✅ Single progress bar — Task 3 (`_build_ui`) + Task 6 slots
- ✅ Plain log (no filter/badge/copy) — Task 3 + Task 6
- ✅ Per-magazine progress bars removed — Task 6 (`_start_download`)
- ✅ Auth duplication removed — single `cookie_edit` in shared row
- ✅ Version bump 1.5.0 → 1.6.0 — Task 1
- ✅ All backend logic untouched
- ✅ System tray preserved (not mentioned in any task — `_setup_tray` is unchanged)

**Placeholder scan:** No TBDs, all code blocks are complete.

**Type consistency:** `self.mag_chips` used consistently in Tasks 4, 6, 7. `self.progress_bar` used consistently in Tasks 3, 6. `self.org_btn` used consistently in Tasks 5, 6.
