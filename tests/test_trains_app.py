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


def test_fetch_pdf_uses_issue_page_for_name_and_metadata(monkeypatch, tmp_path):
    import requests
    import trains_app

    issue_url = "https://www.trains.com/mrr/magazine/january-2024/"
    pdf_bytes = _make_valid_pdf_bytes()
    raw_dir = tmp_path / "raw"
    destination = tmp_path / "MRR"
    raw_dir.mkdir()

    class FakeResponse:
        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield pdf_bytes

        def close(self):
            pass

    monkeypatch.setattr(requests, "get", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    ok, result = trains_app.fetch_pdf(
        "https://cdn.example/files/opaque-id.pdf",
        str(destination),
        "MRR",
        {},
        False,
        str(raw_dir),
        lambda _message: None,
        issue_url=issue_url,
    )

    assert ok is True
    assert os.path.normcase(result) == os.path.normcase(
        str(destination / "2024" / "MRR-01-January-2024.pdf")
    )
    metadata = trains_app.pypdf.PdfReader(result).metadata
    assert metadata.get("/Title") == "Model Railroader - January, 2024"
    assert metadata.get("/Author") == "Model Railroader"
    assert metadata.get("/Subject") == "January 2024"


def test_issue_already_on_disk_finds_legacy_root_level_issue_file(tmp_path):
    from trains_app import issue_already_on_disk

    destination = tmp_path / "MRR"
    destination.mkdir()
    (destination / "MRR-01-January-2024.pdf").write_bytes(b"previous download")

    assert issue_already_on_disk(
        "https://www.trains.com/mrr/magazine/january-2024/",
        str(destination),
        "MRR",
        flat=False,
    ) is True


def test_undated_special_issue_uses_stable_name_and_is_detected_on_disk(tmp_path):
    import trains_app

    source = tmp_path / "raw"
    destination = tmp_path / "Special Issues"
    source.mkdir()
    (source / "opaque-id.pdf").write_bytes(_make_valid_pdf_bytes())
    issue_url = (
        "https://www.trains.com/mrr/magazine/special-issues/railroad-technology/"
    )

    ok, result = trains_app.rename_and_move(
        str(source / "opaque-id.pdf"),
        str(destination),
        "MRR",
        True,
        lambda _message: None,
        issue_url=issue_url,
    )

    assert ok is True
    assert os.path.basename(result) == "railroad-technology.pdf"
    assert trains_app.issue_already_on_disk(
        issue_url, str(destination), "MRR", flat=True
    ) is True


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


def test_organize_activity_reports_stages_and_each_file_outcome(tmp_path, monkeypatch):
    import trains_app

    archive = tmp_path / "archive"
    incoming = archive / "incoming"
    year = archive / "2024"
    incoming.mkdir(parents=True)
    year.mkdir()
    data = _make_valid_pdf_bytes()
    (year / "MRR-01-January-2024.pdf").write_bytes(data)
    (year / "MRR-02-February-2024.pdf").write_bytes(data)
    (incoming / "MRR-2024-01.pdf").write_bytes(data)
    (incoming / "MRR-2024-03.pdf").write_bytes(data)
    (incoming / "MRR-2024-04.pdf").write_bytes(b"%PDF-1.4 truncated")
    (incoming / "mystery.pdf").write_bytes(data)
    monkeypatch.setattr(trains_app, "_stamp_pdf_metadata", lambda *_args, **_kwargs: False)
    worker = trains_app.OrganizeWorker(str(archive), str(archive), "MRR")
    logs, statuses, progress = [], [], []
    worker.signals.log.connect(logs.append)
    worker.signals.status_msg.connect(statuses.append)
    worker.signals.progress.connect(lambda done, total: progress.append((done, total)))

    worker.run()

    assert logs[0].startswith("[stage] Scanning folders")
    assert any(line.startswith("[stage] Organizing 6 PDFs") for line in logs)
    assert any(line.startswith("[stage] Checking issue coverage") for line in logs)
    outcomes = [line for line in logs if line.startswith(
        ("[moved]", "[unchanged]", "[conflict]", "[corrupt]", "[unrecognized]")
    )]
    assert len(outcomes) == 6
    assert sum(line.startswith("[unchanged]") for line in outcomes) == 2
    moved = next(line for line in outcomes if line.startswith("[moved]"))
    assert "MRR-03-March-2024.pdf" in moved
    assert str(incoming / "MRR-2024-03.pdf") in moved
    assert str(year / "MRR-03-March-2024.pdf") in moved
    conflict = next(line for line in outcomes if line.startswith("[conflict]"))
    assert "both files preserved" in conflict.lower()
    assert (year / "MRR-01-January-2024-1.pdf").exists()
    assert (incoming / "MRR-2024-04.pdf").exists()
    assert (incoming / "mystery.pdf").exists()
    assert progress[0] == (0, 6) and progress[-1] == (6, 6)
    assert any("PDF 1 of 6" in message for message in statuses)
    assert any("Checking issue coverage" in message for message in statuses)
    assert logs[-1].startswith("[summary] Organization complete")
    assert "2 moved" in logs[-1] and "2 already organized" in logs[-1]
    assert "Unrecognized: 1" in logs[-1] and "Unreadable PDFs: 1" in logs[-1]
    assert "Conflicts: 1" in logs[-1] and "Metadata updated: 0" in logs[-1]
    assert any(line.startswith("[coverage]") and "January" not in line.split("missing", 1)[-1]
               for line in logs)


def test_organize_activity_keeps_metadata_failure_with_file_outcome(tmp_path, monkeypatch):
    import trains_app

    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    (source / "MRR-2024-01.pdf").write_bytes(_make_valid_pdf_bytes())

    def failed_metadata(_path, _month, _year, warn_fn):
        warn_fn("Warning: metadata update failed: access denied")
        return False

    monkeypatch.setattr(trains_app, "_stamp_pdf_metadata", failed_metadata)
    logs = []
    summary = trains_app.organize_pdfs(str(source), str(destination), "MRR", log_fn=logs.append)

    moved = [line for line in logs if line.startswith("[moved]")]
    assert len(moved) == 1
    assert "Metadata warning: Warning: metadata update failed: access denied" in moved[0]
    assert summary.moved == 1 and summary.metadata_stamped == 0
    assert summary.scan_complete is True


def test_organize_activity_identifies_cancelled_coverage_as_partial(tmp_path, monkeypatch):
    import trains_app

    source, destination = tmp_path / "source", tmp_path / "destination"
    source.mkdir()
    for month in ("01", "02"):
        (source / f"MRR-2024-{month}.pdf").write_bytes(_make_valid_pdf_bytes())
    monkeypatch.setattr(trains_app, "_stamp_pdf_metadata", lambda *_args, **_kwargs: False)
    worker = trains_app.OrganizeWorker(str(source), str(destination), "MRR")
    logs = []
    worker.signals.log.connect(logs.append)
    worker.signals.progress.connect(lambda done, _total: worker.stop() if done == 1 else None)

    worker.run()

    assert worker.outcome == trains_app.OUTCOME_CANCELLED
    assert worker.result.scan_complete is False
    assert len(list(source.glob("*.pdf"))) == 1
    assert "partial" in logs[-1].lower() and "cancelled" in logs[-1].lower()
    assert any(line.startswith("[coverage]") and "partial" in line.lower() for line in logs)


def test_organize_stops_between_files_with_partial_summary(tmp_path, monkeypatch):
    import threading
    import trains_app

    src = tmp_path / "incoming"
    dst = tmp_path / "library"
    src.mkdir()
    dst.mkdir()
    (src / "MRR-2024-01.pdf").write_bytes(b"first")
    (src / "MRR-2024-02.pdf").write_bytes(b"second")
    cancel_event = threading.Event()
    monkeypatch.setattr(trains_app, "_verify_pdf", lambda _path: True)
    monkeypatch.setattr(
        trains_app, "_stamp_pdf_metadata", lambda *_args, **_kwargs: False
    )

    def cancel_after_first(done, _total):
        if done == 1:
            cancel_event.set()

    summary = trains_app.organize_pdfs(
        str(src), str(dst),
        progress_fn=cancel_after_first,
        cancel_event=cancel_event,
    )

    assert summary.scan_complete is False
    assert summary.moved == 1
    assert len(list(dst.rglob("*.pdf"))) == 1
    assert len(list(src.glob("*.pdf"))) == 1
    assert trains_app._missing_download_selection(summary) == (None, {})


def test_organize_worker_stop_is_cancelled_with_partial_summary(tmp_path, monkeypatch):
    import trains_app

    src = tmp_path / "incoming"
    dst = tmp_path / "library"
    src.mkdir()
    dst.mkdir()
    (src / "MRR-2024-01.pdf").write_bytes(b"first")
    (src / "MRR-2024-02.pdf").write_bytes(b"second")
    monkeypatch.setattr(trains_app, "_verify_pdf", lambda _path: True)
    monkeypatch.setattr(
        trains_app, "_stamp_pdf_metadata", lambda *_args, **_kwargs: False
    )
    worker = trains_app.OrganizeWorker(str(src), str(dst), "MRR")

    def stop_after_first(done, _total):
        if done == 1:
            worker.stop()

    worker.signals.progress.connect(stop_after_first)
    worker.run()

    assert worker.outcome == trains_app.OUTCOME_CANCELLED
    assert worker.result.scan_complete is False
    assert worker.result.moved == 1


def test_failed_scan_retains_partial_matches_and_failed_outcome(tmp_path, monkeypatch):
    import trains_app

    src = tmp_path / "incoming"
    dst = tmp_path / "library"
    src.mkdir()
    dst.mkdir()
    (src / "MRR-2024-01.pdf").write_bytes(b"first")
    monkeypatch.setattr(trains_app, "_verify_pdf", lambda _path: True)
    monkeypatch.setattr(
        trains_app, "_stamp_pdf_metadata", lambda *_args, **_kwargs: False
    )

    def incomplete_walk(top, onerror=None):
        yield str(top), [], ["MRR-2024-01.pdf"]
        if onerror is not None:
            onerror(PermissionError("one subfolder could not be scanned"))

    monkeypatch.setattr(trains_app.os, "walk", incomplete_walk)
    worker = trains_app.OrganizeWorker(str(src), str(dst), "MRR")
    errors = []
    worker.signals.error.connect(errors.append)
    worker.run()

    assert worker.outcome == trains_app.OUTCOME_FAILED
    assert worker.result.scan_complete is False
    assert worker.result.moved == 1
    assert "MRR" in worker.result.missing_by_prefix_year
    assert trains_app._missing_download_selection(worker.result) == (None, {})
    assert errors == [
        "Organizer scan was incomplete; partial results were retained."
    ]


def test_no_results_is_not_failure(tmp_path):
    import trains_app

    src = tmp_path / "incoming"
    dst = tmp_path / "library"
    src.mkdir()
    dst.mkdir()
    worker = trains_app.OrganizeWorker(str(src), str(dst), None)

    worker.run()

    assert worker.outcome == trains_app.OUTCOME_NO_RESULTS
    assert worker.result is not None
    assert worker.result.moved == 0
    assert worker.result.scan_complete is True


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


def test_ambiguous_filename_does_not_default_to_mrr():
    from trains_app import _guess_prefix, parse_pdf_filename

    assert _guess_prefix("fall-2020.pdf") is None
    assert parse_pdf_filename("fall-2020.pdf") is None
    assert parse_pdf_filename("fall-2020.pdf", hint_prefix="GRW")[0].startswith("GRW-")


def test_grw_insufficient_schedule_evidence_is_not_monthly(tmp_path):
    from trains_app import organize_pdfs

    src = tmp_path / "src"
    dst = tmp_path / "dst"
    src.mkdir()
    dst.mkdir()
    (src / "fall-2020.pdf").write_bytes(_make_valid_pdf_bytes())

    summary = organize_pdfs(str(src), str(dst), hint_prefix="GRW")

    assert summary.missing_by_prefix_year["GRW"]["2020"] == []
    assert any("GRW 2020: schedule unknown/seasonal" in line for line in summary.report)


def test_parse_full_month_archive_slug():
    from trains_app import parse_pdf_filename

    assert parse_pdf_filename("october-2026.pdf", hint_prefix="MRR") == (
        "MRR-10-October-2026", "2026", "October"
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


def test_login_detection_does_not_accept_generic_account_link():
    from trains_app import MagazineDownloader

    class LoggedOutDriver:
        page_source = "<footer><a>Your Account</a></footer>"

        def get(self, _url):
            return None

    downloader = object.__new__(MagazineDownloader)
    downloader._driver = LoggedOutDriver()

    assert downloader.is_logged_in() is False


def test_browser_uses_non_persistent_webdriver_transport(monkeypatch, tmp_path):
    import selenium.webdriver
    from trains_app import MagazineDownloader

    captured = {}

    class FakeDriver:
        def execute_cdp_cmd(self, _command, _params):
            return {}

        def quit(self):
            pass

    def fake_chrome(**kwargs):
        captured.update(kwargs)
        return FakeDriver()

    monkeypatch.setattr(selenium.webdriver, "Chrome", fake_chrome)
    downloader = MagazineDownloader(str(tmp_path), headless=True)
    downloader.close()

    assert captured["keep_alive"] is False


def test_browser_navigation_retries_connection_reset(monkeypatch):
    from trains_app import MagazineDownloader

    class FlakyDriver:
        def __init__(self):
            self.calls = 0

        def get(self, _url):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError(
                    "ProtocolError: ('Connection aborted.', "
                    "ConnectionResetError(10054))"
                )

    logs = []
    downloader = object.__new__(MagazineDownloader)
    downloader._driver = FlakyDriver()
    downloader.log_fn = logs.append
    monkeypatch.setattr("trains_app.time.sleep", lambda _seconds: None)

    downloader._navigate("https://www.trains.com/", attempts=2)

    assert downloader._driver.calls == 2
    assert any("retrying" in message.lower() for message in logs)


def test_browser_transport_timeout_is_classified_as_transient():
    from trains_app import MagazineDownloader

    error = RuntimeError(
        "HTTPConnectionPool(host='localhost', port=65006): "
        "Read timed out. (read timeout=120)"
    )

    assert MagazineDownloader._is_transient_navigation_error(error) is True


def test_browser_command_retries_after_restarting_transient_session(monkeypatch):
    from trains_app import MagazineDownloader

    logs = []
    downloader = object.__new__(MagazineDownloader)
    downloader.log_fn = logs.append
    restarted = []
    downloader._restart_browser = lambda: restarted.append(True) or True
    calls = []

    def flaky_command():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError(
                "HTTPConnectionPool(host='localhost', port=65006): "
                "Read timed out. (read timeout=120)"
            )
        return "ok"

    assert downloader._run_browser_command(
        flaky_command,
        description="Issue inspection",
    ) == "ok"
    assert len(calls) == 2
    assert restarted == [True]
    assert any("restarting" in message.lower() for message in logs)


def test_browser_http_command_timeout_is_bounded(monkeypatch, tmp_path):
    import selenium.webdriver

    from trains_app import MagazineDownloader

    class ClientConfig:
        timeout = 120

    class FakeDriver:
        command_executor = type("Executor", (), {
            "_client_config": ClientConfig(),
        })()

        def execute_cdp_cmd(self, _command, _params):
            return {}

        def quit(self):
            pass

    captured = {}

    def fake_chrome(**kwargs):
        captured["kwargs"] = kwargs
        captured["driver"] = FakeDriver()
        return captured["driver"]

    monkeypatch.setattr(selenium.webdriver, "Chrome", fake_chrome)
    downloader = MagazineDownloader(str(tmp_path), headless=True)
    downloader.close()

    assert captured["driver"].command_executor._client_config.timeout <= 60


def test_cancel_pending_futures_only_cancels_not_started_work():
    from concurrent.futures import Future
    from trains_app import cancel_pending_futures

    pending = Future()
    running = Future()
    assert running.set_running_or_notify_cancel() is True

    assert cancel_pending_futures({pending: "pending", running: "running"}) == 1
    assert pending.cancelled()
    assert not running.cancelled()


def test_download_worker_classifies_empty_archive_as_no_results(monkeypatch, tmp_path):
    import trains_app

    class EmptyDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self._driver = None

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            return []

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", EmptyDownloader)
    worker = trains_app.DownloadWorker(
        ["Model Railroader"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )

    worker.run()

    assert worker.outcome == trains_app.OUTCOME_NO_RESULTS


def test_download_worker_marks_empty_failed_scan_as_failure(monkeypatch, tmp_path):
    import trains_app

    class BlockedDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self._driver = None

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            raise trains_app.ArchiveScanError("HTTP 403 while reading page 1")

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", BlockedDownloader)
    worker = trains_app.DownloadWorker(
        ["Model Railroader"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )

    worker.run()

    assert worker.outcome == trains_app.OUTCOME_FAILED
    assert worker._had_failures is True


def test_download_worker_downloads_partial_results_and_continues_after_scan_failure(
    monkeypatch, tmp_path
):
    import trains_app

    mrr_issue = "https://www.trains.com/mrr/magazine/november-2026/"
    trn_issue = "https://www.trains.com/trn/magazine/november-2026/"
    pdf_urls = {
        mrr_issue: "https://cdn.example/MAG-MRR-NOV26.pdf",
        trn_issue: "https://cdn.example/MAG-TRN-NOV26.pdf",
    }
    scanned = []
    downloaded = []

    class Driver:
        def get_cookies(self):
            return []

    class PartialFailureDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self.download_dir = download_dir
            self._driver = Driver()

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, archive_url, **_kwargs):
            scanned.append(archive_url)
            if archive_url == trains_app.MAGAZINES["Model Railroader"]["url"]:
                raise trains_app.ArchiveScanError(
                    "HTTP 403 while reading page 2", partial_links=[mrr_issue]
                )
            return [trn_issue]

        def detect_issue_mode(self, issue_url, **_kwargs):
            return "mode1", pdf_urls[issue_url]

        def _run_browser_command(self, operation, **_kwargs):
            return operation()

        def close(self):
            pass

    def fake_fetch_pdf(
        url, dest_dir, prefix, cookies, flat, download_dir, log_fn, issue_url=None
    ):
        downloaded.append(url)
        return True, url.rsplit("/", 1)[-1]

    monkeypatch.setattr(trains_app, "MagazineDownloader", PartialFailureDownloader)
    monkeypatch.setattr(trains_app, "fetch_pdf", fake_fetch_pdf)
    monkeypatch.setattr(trains_app, "PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    worker = trains_app.DownloadWorker(
        ["Model Railroader", "Trains Magazine"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )
    worker.run()

    assert scanned == [
        trains_app.MAGAZINES["Model Railroader"]["url"],
        trains_app.MAGAZINES["Trains Magazine"]["url"],
    ]
    assert set(downloaded) == set(pdf_urls.values())
    assert worker.outcome == trains_app.OUTCOME_FAILED


def test_missing_issues_worker_downloads_partial_matches_after_scan_failure(
    monkeypatch, tmp_path
):
    import trains_app

    issue_url = "https://www.trains.com/mrr/magazine/november-2026/"
    downloaded = []

    class PartialFailureDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self.download_dir = download_dir

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            raise trains_app.ArchiveScanError(
                "HTTP 403 while reading page 2", partial_links=[issue_url]
            )

        def download_issue(self, url, **_kwargs):
            downloaded.append(url)
            return True, "MRR-11-November-2026.pdf"

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", PartialFailureDownloader)
    monkeypatch.setattr(trains_app, "PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(
        trains_app, "SPECIAL_ISSUES_FILE", str(tmp_path / "special-issues.json")
    )
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    worker = trains_app.MissingIssuesWorker(
        "MRR",
        trains_app.MAGAZINES["Model Railroader"]["url"],
        {"2026": ["November"]},
        str(tmp_path),
        None,
        False,
    )
    worker.run()

    assert downloaded == [issue_url]
    assert worker.outcome == trains_app.OUTCOME_FAILED


def test_missing_issues_worker_does_not_report_no_results_for_incomplete_scan(
    monkeypatch, tmp_path
):
    import trains_app

    partial_issue = "https://www.trains.com/mrr/magazine/november-2026/"

    class PartialFailureDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self.download_dir = download_dir

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            raise trains_app.ArchiveScanError(
                "HTTP 403 while reading page 2", partial_links=[partial_issue]
            )

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", PartialFailureDownloader)
    monkeypatch.setattr(trains_app, "PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(
        trains_app, "SPECIAL_ISSUES_FILE", str(tmp_path / "special-issues.json")
    )

    worker = trains_app.MissingIssuesWorker(
        "MRR",
        trains_app.MAGAZINES["Model Railroader"]["url"],
        {"2026": ["December"]},
        str(tmp_path),
        None,
        False,
    )
    worker.run()

    assert worker.outcome == trains_app.OUTCOME_FAILED
    assert worker._had_failures is True


def test_download_worker_stop_is_cancelled_not_success(monkeypatch, tmp_path):
    import trains_app

    class EmptyDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self._driver = None

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            return []

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", EmptyDownloader)
    worker = trains_app.DownloadWorker(
        ["Model Railroader"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )
    worker.stop()

    worker.run()

    assert worker.outcome == trains_app.OUTCOME_CANCELLED


@pytest.mark.parametrize("job_kind", ["magazines", "download-missing"])
def test_manual_login_wait_honors_stop_for_magazines_and_missing_jobs(
    monkeypatch, tmp_path, job_kind
):
    import trains_app

    observed_stop = []

    class UnauthenticatedDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self._driver = None

        def wait_for_manual_login(self, **kwargs):
            stop_requested = kwargs.get("stop_requested")
            observed_stop.append(bool(stop_requested and stop_requested()))
            return False

        def close(self):
            pass

    monkeypatch.setattr(trains_app, "MagazineDownloader", UnauthenticatedDownloader)
    if job_kind == "magazines":
        worker = trains_app.DownloadWorker(
            ["Model Railroader"], str(tmp_path), False, False, None, True,
            include_specials=False,
        )
    else:
        worker = trains_app.MissingIssuesWorker(
            "MRR",
            trains_app.MAGAZINES["Model Railroader"]["url"],
            {"2024": ["March"]},
            str(tmp_path),
            None,
            False,
        )

    worker.stop()
    worker.run()

    assert observed_stop == [True]
    assert worker.outcome == trains_app.OUTCOME_CANCELLED


def test_download_worker_passes_direct_pdf_url_from_issue_mode(monkeypatch, tmp_path):
    import trains_app

    issue_url = "https://www.trains.com/mrr/magazine/october-2026/"
    pdf_url = "https://cdn.example/MAG-MRR-OCT26.pdf"
    captured = {}

    class Driver:
        def get_cookies(self):
            return [{"name": "auth", "value": "token"}]

    class DirectDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self.download_dir = download_dir
            self._driver = Driver()

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            return [issue_url]

        def detect_issue_mode(self, *_args, **_kwargs):
            return "mode1", pdf_url

        def _run_browser_command(self, operation, **_kwargs):
            return operation()

        def close(self):
            pass

    def fake_fetch_pdf(
        url, dest_dir, prefix, cookies, flat, download_dir, log_fn, issue_url=None
    ):
        captured.update(
            url=url,
            dest_dir=dest_dir,
            prefix=prefix,
            cookies=cookies,
            flat=flat,
            issue_url=issue_url,
        )
        return True, "downloaded.pdf"

    monkeypatch.setattr(trains_app, "MagazineDownloader", DirectDownloader)
    monkeypatch.setattr(trains_app, "fetch_pdf", fake_fetch_pdf)
    monkeypatch.setattr(trains_app, "PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(trains_app.time, "sleep", lambda *_args: None)

    worker = trains_app.DownloadWorker(
        ["Model Railroader"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )
    worker.run()

    assert worker.outcome == trains_app.OUTCOME_SUCCESS
    assert captured == {
        "url": pdf_url,
        "dest_dir": str(tmp_path / "MRR"),
        "prefix": "MRR",
        "cookies": {"auth": "token"},
        "flat": False,
        "issue_url": issue_url,
    }


def test_download_worker_skips_issue_in_legacy_folder_without_progress(
    monkeypatch, tmp_path
):
    import trains_app

    issue_url = "https://www.trains.com/mrr/magazine/january-2024/"
    destination = tmp_path / "MRR"
    destination.mkdir()
    (destination / "MRR-01-January-2024.pdf").write_bytes(b"existing issue")
    fetched = []

    class Driver:
        def get_cookies(self):
            return []

    class ExistingIssueDownloader:
        def __init__(self, download_dir, headless, log_fn):
            self._driver = Driver()

        def wait_for_manual_login(self, **_kwargs):
            return True

        def collect_all_issue_links(self, *_args, **_kwargs):
            return [issue_url]

        def close(self):
            pass

    def fake_fetch_pdf(*_args, **_kwargs):
        fetched.append(True)
        return True, "unexpected.pdf"

    monkeypatch.setattr(
        trains_app,
        "MAGAZINES",
        {"Model Railroader": {
            "url": "https://www.trains.com/mrr/magazine/",
            "prefix": "MRR",
        }},
    )
    monkeypatch.setattr(trains_app, "MagazineDownloader", ExistingIssueDownloader)
    monkeypatch.setattr(trains_app, "fetch_pdf", fake_fetch_pdf)
    monkeypatch.setattr(
        trains_app,
        "load_progress",
        lambda: {"completed": [], "completed_scoped": [], "failed": []},
    )
    monkeypatch.setattr(trains_app, "save_progress", lambda _progress: None)

    worker = trains_app.DownloadWorker(
        ["Model Railroader"], str(tmp_path), False, True, None, True,
        include_specials=False,
    )
    worker.run()

    assert worker.outcome == trains_app.OUTCOME_SUCCESS
    assert fetched == []
