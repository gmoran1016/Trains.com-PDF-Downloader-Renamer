import io
import json
import os
import sys
import pytest

# Add project root to path so we can import trains_app without a display
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trains_app import load_settings, save_settings

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_load_settings_returns_empty_dict_when_file_missing(tmp_path):
    path = str(tmp_path / "nonexistent.json")
    result = load_settings(path=path)
    assert result == {}


def test_load_settings_returns_empty_dict_on_malformed_json(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("not json", encoding="utf-8")
    result = load_settings(path=str(f))
    assert result == {}


def test_save_and_load_settings_roundtrip(tmp_path):
    path = str(tmp_path / "settings.json")
    data = {"base_dir": "/some/path", "headless": True, "newest_first": False}
    save_settings(data, path=path)
    result = load_settings(path=path)
    assert result == data


def test_save_settings_writes_valid_json(tmp_path):
    path = str(tmp_path / "settings.json")
    save_settings({"key": "value"}, path=path)
    with open(path, encoding="utf-8") as f:
        parsed = json.load(f)
    assert parsed == {"key": "value"}


# ---------------------------------------------------------------------------
# Integrity check + rename_and_move  (added in Task 2)
# ---------------------------------------------------------------------------

def _make_valid_pdf_bytes() -> bytes:
    import pypdf
    buf = io.BytesIO()
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    return buf.getvalue()


def test_verify_pdf_rejects_too_small(tmp_path):
    from trains_app import _verify_pdf
    f = tmp_path / "small.pdf"
    f.write_bytes(b"%PDF-1.4 tiny")
    assert _verify_pdf(str(f)) is False


def test_verify_pdf_rejects_invalid_content(tmp_path):
    from trains_app import _verify_pdf
    f = tmp_path / "fake.pdf"
    f.write_bytes(b"not a pdf at all" + b"x" * 10_240)
    assert _verify_pdf(str(f)) is False


def test_verify_pdf_accepts_valid_pdf(tmp_path):
    from trains_app import _verify_pdf
    f = tmp_path / "valid.pdf"
    f.write_bytes(_make_valid_pdf_bytes())
    assert _verify_pdf(str(f)) is True


def test_rename_and_move_returns_false_for_corrupt_file(tmp_path):
    from trains_app import rename_and_move
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    bad_pdf = src / "MRR-2024-01.pdf"
    bad_pdf.write_bytes(b"tiny")
    logs = []
    ok, result = rename_and_move(str(bad_pdf), str(dst), "MRR", False, logs.append)
    assert ok is False
    assert result == "corrupt"
    assert not any(dst.rglob("*.pdf"))


def test_rename_and_move_moves_and_renames_valid_pdf(tmp_path):
    from trains_app import rename_and_move
    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    pdf_path = src / "2024-01.pdf"
    pdf_path.write_bytes(_make_valid_pdf_bytes())
    logs = []
    ok, result = rename_and_move(str(pdf_path), str(dst), "MRR", False, logs.append)
    assert ok is True
    assert "MRR" in result
    assert os.path.exists(result)


# ---------------------------------------------------------------------------
# _handle_result  (added in Task 4)
# ---------------------------------------------------------------------------

def _make_progress():
    return {"completed": [], "failed": []}


def test_handle_result_marks_completed_on_success(tmp_path):
    from trains_app import _handle_result
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(True, "/some/path.pdf", "http://x.com/issue/",
                       progress, completed_set, logs.append)
        assert "http://x.com/issue/" in completed_set
        assert "http://x.com/issue/" in progress["completed"]
        assert progress["failed"] == []
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_marks_completed_for_readonly(tmp_path):
    from trains_app import _handle_result
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(False, "No PDF download available (read-only issue)",
                       "http://x.com/old/", progress, completed_set, logs.append)
        assert "http://x.com/old/" in completed_set
        assert "http://x.com/old/" in progress["completed"]
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_appends_failed_on_error(tmp_path):
    from trains_app import _handle_result
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        completed_set = set()
        logs = []
        _handle_result(False, "HTTP download failed: timeout",
                       "http://x.com/fail/", progress, completed_set, logs.append)
        assert "http://x.com/fail/" not in completed_set
        assert len(progress["failed"]) == 1
        assert progress["failed"][0]["url"] == "http://x.com/fail/"
    finally:
        trains_app.PROGRESS_FILE = original


def test_handle_result_does_not_duplicate_failed_entry(tmp_path):
    from trains_app import _handle_result
    import trains_app
    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        progress = _make_progress()
        progress["failed"].append({"url": "http://x.com/fail/", "reason": "old"})
        completed_set = set()
        logs = []
        _handle_result(False, "HTTP download failed: timeout",
                       "http://x.com/fail/", progress, completed_set, logs.append)
        assert len(progress["failed"]) == 1
    finally:
        trains_app.PROGRESS_FILE = original
