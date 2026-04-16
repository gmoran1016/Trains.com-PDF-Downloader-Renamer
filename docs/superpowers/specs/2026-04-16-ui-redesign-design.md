# UI Redesign — Design Spec

**Date:** 2026-04-16  
**Version bump:** 1.5.0 → 1.6.0

---

## Summary

Redesign the PyQt5 UI from a two-tab layout to a cleaner single-window layout. The framework (PyQt5) stays the same; only the layout, widget choices, and stylesheet change.

---

## Layout

Single window. No tabs. The top section holds a **mode toggle** (segmented control) that switches between Download and Organize views. Only the active mode's controls are visible. Below the mode panel is a shared authentication row and a plain log area.

```
┌─────────────────────────────────────────┐
│  [Download]  [Organize]  (mode toggle)  │
├─────────────────────────────────────────┤
│  Mode-specific controls                 │
│  (only active mode visible)             │
├─────────────────────────────────────────┤
│  Cookie file  [path field]  [Browse]    │
│  □ Headless (org only)                  │
├─────────────────────────────────────────┤
│  Progress bar + status text (hidden     │
│  until a job is running)                │
├─────────────────────────────────────────┤
│  Log (plain scrollable text)            │
└─────────────────────────────────────────┘
```

---

## Mode Toggle

Implemented as two `QPushButton` widgets styled as a segmented control (or a `QTabBar` with custom styling). Switching modes shows/hides the two mode panels via `setVisible`. The log and authentication row are always visible regardless of mode.

---

## Download Mode Controls

1. **Magazines** — label + row of toggle chip buttons (`QPushButton`, checkable). Each chip is highlighted when selected, dim when not. All selected by default.
2. **Save Location** — section label + `QLineEdit` + `Browse…` button.
3. **Options** — section label + inline row:
   - `QCheckBox`: Headless
   - `QCheckBox`: Test mode
   - `QCheckBox`: Special issues (checked by default)
   - `QComboBox`: Newest first / Oldest first
4. **Actions** — row of buttons:
   - `▶ Start Download` (primary style, flex-2)
   - `■ Stop` (secondary, disabled until running, flex-1)
   - `Clear Cache` (secondary, flex-1)

---

## Organize Mode Controls

1. **Source Folder** — section label + `QLineEdit` + `Browse…` button.
2. **Destination Folder** — section label + `QLineEdit` + `Browse…` button.
3. **Magazine Prefix** — section label + `QComboBox` (Auto-detect, MRR, TRN, CTT, CTR, GRW).
4. **Actions** — row of buttons:
   - `▶ Organize PDFs` (primary, flex-2)
   - `⬇ Download Missing` (secondary, disabled until organizer runs, flex-2)
   - `■ Stop` (secondary, disabled until running, flex-1)

---

## Shared Authentication Row

Always visible below the mode panel. Contains:
- Small `COOKIE FILE` label
- `QLineEdit` for cookie file path (defaults to `session_cookies.json`)
- `Browse…` button
- `QCheckBox`: Headless browser (used when "Download Missing" runs)

This replaces the duplicated Authentication group boxes that appeared separately on each tab.

---

## Progress Area

Hidden until a job starts. Contains:
- Thin `QProgressBar` (no text, gradient fill, same style as current)
- `QLabel` status text: `"42 / 105 issues · ~8m remaining"`

For the download mode, per-magazine progress bars are removed. A single overall bar is sufficient.

---

## Log Area

Plain `QTextEdit`, read-only, monospace font, dark background. No filter input, no error badge, no copy button. Errors shown in red (`#f38ba8`), successes in green (`#a6e3a1`), normal lines in muted gray.

---

## Stylesheet

Keep the existing Catppuccin-inspired dark theme colors. Remove:
- `QGroupBox` styles (no more group boxes)
- `QLabel[role="log-cap"]` (log section label removed)
- Error badge styles

Add:
- Toggle chip button style (`QPushButton[role="chip"]`, `QPushButton[role="chip"][checked]`)
- Mode toggle button style (`QPushButton[role="mode"]`, `QPushButton[role="mode"][active]`)
- Section label style: small, uppercase, muted

---

## Version Bump

`APP_VERSION` changes from `"1.5.0"` to `"1.6.0"` in `trains_app.py`.

---

## What Is Removed

| Removed | Reason |
|---|---|
| `QTabWidget` + two tabs | Replaced by mode toggle |
| `QGroupBox` cards (×6) | Replaced by flat sections with small labels |
| Duplicate Authentication group on each tab | Replaced by single shared row |
| Log filter `QLineEdit` | Removed (plain log only) |
| Error badge `QLabel` | Removed |
| "Copy Errors" button | Removed |
| Per-magazine progress bars in download tab | Single overall bar is sufficient |
| `_dl_log_lines` / `_org_log_lines` / `_rebuild_log` machinery | No longer needed without filter |

---

## What Is Preserved

- All backend logic (`MagazineDownloader`, workers, `organize_pdfs`, etc.) — untouched
- System tray icon and minimize-to-tray behavior
- Settings persistence (`settings.json`)
- All existing signals/slots between workers and UI
- Window size and minimum size
