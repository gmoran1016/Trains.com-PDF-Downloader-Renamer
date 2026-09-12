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
    # Add enough pages to exceed the 512-byte minimum size check
    for _ in range(10):
        writer.add_blank_page(width=612, height=792)
    writer.write(buf)
    data = buf.getvalue()
    assert len(data) >= 512, f"Test PDF too small: {len(data)} bytes"
    return data


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
    assert bad_pdf.exists(), "a corrupt input must remain recoverable in the source directory"
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


def test_organize_pdfs_rejects_corrupt_input_without_moving(tmp_path):
    from trains_app import organize_pdfs

    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    bad_pdf = src / "MRR-2024-07.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4 truncated")
    logs = []

    summary = organize_pdfs(str(src), str(dst), "MRR", log_fn=logs.append)

    assert summary.corrupt == 1
    assert summary.moved == 0
    assert bad_pdf.exists()
    assert not any(dst.rglob("*.pdf"))
    assert any("[corrupt]" in line for line in logs)
    assert "MRR" not in summary.missing_by_prefix_year


def test_organize_pdfs_reports_and_preserves_destination_conflicts(tmp_path):
    from trains_app import organize_pdfs

    src = tmp_path / "src"; src.mkdir()
    first = src / "first"; first.mkdir()
    second = src / "second"; second.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    data = _make_valid_pdf_bytes()
    (first / "2024-01.pdf").write_bytes(data)
    (second / "MRR-2024-01.pdf").write_bytes(data)
    logs = []

    summary = organize_pdfs(str(src), str(dst), "MRR", log_fn=logs.append)

    outputs = sorted(path.name for path in (dst / "2024").glob("*.pdf"))
    assert summary.moved == 2
    assert summary.conflicts == 1
    assert outputs == [
        "MRR-01-January-2024-1.pdf",
        "MRR-01-January-2024.pdf",
    ]
    assert any("[conflict]" in line for line in logs)


def test_organize_pdfs_reports_completeness_per_publication(tmp_path):
    from trains_app import organize_pdfs

    src = tmp_path / "src"; src.mkdir()
    dst = tmp_path / "dst"; dst.mkdir()
    data = _make_valid_pdf_bytes()
    (src / "MRR-2024-01.pdf").write_bytes(data)
    (src / "MRR-2024-02.pdf").write_bytes(data)
    (src / "CTR-2024-03.pdf").write_bytes(data)
    (src / "TRN-2024-01.pdf").write_bytes(data)

    summary = organize_pdfs(str(src), str(dst), log_fn=lambda _line: None)

    assert "MRR 2024: " in "\n".join(summary.report)
    assert "CTR 2024: " in "\n".join(summary.report)
    assert "TRN 2024: " in "\n".join(summary.report)
    assert not any(line.startswith("2024:") for line in summary.report)
    assert summary.missing_by_prefix_year["CTR"]["2024"] == [
        "June", "September", "December"
    ]


def test_missing_download_selection_requires_one_publication():
    from trains_app import OrganizeSummary, _missing_download_selection

    mixed = OrganizeSummary(
        missing_by_prefix_year={
            "MRR": {"2024": ["March"]},
            "CTR": {"2024": ["June"]},
        }
    )
    single = OrganizeSummary(
        missing_by_prefix_year={"MRR": {"2024": ["March"]}}
    )

    assert _missing_download_selection(mixed) == (None, {})
    assert _missing_download_selection(single) == (
        "MRR", {"2024": ["March"]}
    )


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


def test_completed_progress_is_scoped_to_destination():
    from trains_app import _is_progress_completed, progress_key

    url = "https://www.trains.com/mrr/magazine/october-2026/"
    progress = {
        "completed_scoped": [progress_key(url, "C:/one/MRR", False)]
    }
    assert _is_progress_completed(progress, url, "C:/one/MRR", False)
    assert not _is_progress_completed(progress, url, "C:/two/MRR", False)
    assert progress_key(url, "C:/one/MRR", False) != progress_key(
        url, "C:/two/MRR", False
    )
    assert progress_key(url, "C:/one/MRR", False) != progress_key(
        url, "C:/one/MRR/Special Issues", True
    )


def test_handle_result_records_scoped_completion(tmp_path):
    from trains_app import _handle_result, progress_key
    import trains_app

    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "progress.json")
    try:
        url = "https://www.trains.com/mrr/magazine/october-2026/"
        progress = {"completed": [], "completed_scoped": [], "failed": []}
        _handle_result(
            True,
            "saved.pdf",
            url,
            progress,
            set(),
            lambda _line: None,
            progress_key_value=progress_key(url, str(tmp_path), False),
        )
        assert url in progress["completed"]
        assert progress["completed_scoped"]
    finally:
        trains_app.PROGRESS_FILE = original


def test_progress_loader_initializes_scoped_entries(tmp_path):
    import trains_app

    original = trains_app.PROGRESS_FILE
    trains_app.PROGRESS_FILE = str(tmp_path / "missing-progress.json")
    try:
        assert trains_app.load_progress()["completed_scoped"] == []
    finally:
        trains_app.PROGRESS_FILE = original


def test_login_detection_accepts_current_account_surface():
    from trains_app import MagazineDownloader

    class LoggedInDriver:
        page_source = "<header>Hello, Griffin</header><a>Your Account</a>"

        def get(self, _url):
            return None

    downloader = object.__new__(MagazineDownloader)
    downloader._driver = LoggedInDriver()

    assert downloader.is_logged_in() is True
