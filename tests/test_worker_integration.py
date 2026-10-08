"""Offline integration tests for the JSON-lines Python worker."""

import importlib
import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from worker_protocol import decode_event


def _worker_main():
    try:
        return importlib.import_module("worker_main")
    except ModuleNotFoundError:
        pytest.fail("worker_main.py entry point is missing", pytrace=False)


def _start_line(job_id="job-1", job_kind="magazines", options=None):
    return json.dumps(
        {
            "v": 1,
            "job_id": job_id,
            "command": "start",
            "job_kind": job_kind,
            "options": options or {},
        },
        ensure_ascii=False,
    )


class _Signal:
    def __init__(self):
        self._slots = []

    def connect(self, slot, *_args, **_kwargs):
        self._slots.append(slot)

    def emit(self, *args):
        for slot in self._slots:
            slot(*args)


def _fake_worker_class(name, constructed):
    class FakeWorker:
        def __init__(self, *args, **kwargs):
            constructed.append((name, args, kwargs))
            self.signals = SimpleNamespace(
                log=_Signal(),
                progress=_Signal(),
                magazine_progress=_Signal(),
                status_msg=_Signal(),
                error=_Signal(),
                finished=_Signal(),
            )
            self.outcome = "success"
            self.result = None

        def start(self):
            self.signals.log.emit("fake worker log")
            self.signals.progress.emit(2, 4)
            self.signals.magazine_progress.emit("Model Railroader", 1, 2)
            self.signals.status_msg.emit("2 / 4 issues · almost done")

        def wait(self, _timeout=None):
            return True

        def stop(self):
            self.outcome = "cancelled"

    FakeWorker.__name__ = name
    return FakeWorker


def _fake_trains_app(constructed):
    module = ModuleType("trains_app")
    module.MAGAZINES = {
        "Model Railroader": {"url": "https://example.invalid/mrr/", "prefix": "MRR"},
        "Trains Magazine": {"url": "https://example.invalid/trn/", "prefix": "TRN"},
        "Classic Toy Trains": {"url": "https://example.invalid/ctt/", "prefix": "CTT"},
        "Classic Trains": {"url": "https://example.invalid/ctr/", "prefix": "CTR"},
        "Garden Railways": {"url": "https://example.invalid/grw/", "prefix": "GRW"},
    }
    module.DownloadWorker = _fake_worker_class("DownloadWorker", constructed)
    module.TrackPlanWorker = _fake_worker_class("TrackPlanWorker", constructed)
    module.OrganizeWorker = _fake_worker_class("OrganizeWorker", constructed)
    module.MissingIssuesWorker = _fake_worker_class("MissingIssuesWorker", constructed)
    module.OUTCOME_SUCCESS = "success"
    module.OUTCOME_FAILED = "failed"
    module.OUTCOME_CANCELLED = "cancelled"
    module.OUTCOME_NO_RESULTS = "no-results"
    return module


def test_worker_dispatches_all_job_kinds(monkeypatch):
    worker_main = _worker_main()
    constructed = []
    monkeypatch.setitem(sys.modules, "trains_app", _fake_trains_app(constructed))
    cases = [
        (
            "magazines",
            {
                "magazines": ["Model Railroader"],
                "base_dir": "D:/Magazine PDFs",
                "headless": True,
                "test_mode": False,
                "cookies_path": "D:/account.json",
                "newest_first": True,
                "include_specials": True,
                "newest_first": True,
                "include_specials": True,
            },
        ),
        (
            "track-plans",
            {"destination_dir": "D:/Track Plans", "cookies_path": "D:/account.json"},
        ),
        (
            "organize",
            {
                "source_dir": "D:/Incoming",
                "destination_dir": "D:/Library",
                "hint_prefix": "MRR",
            },
        ),
        (
            "download-missing",
            {
                "prefix": "MRR",
                "archive_url": "https://example.invalid/archive/",
                "missing_by_year": {"2024": ["March"]},
                "destination_dir": "D:/Library",
                "cookies_path": "D:/account.json",
                "headless": True,
            },
        ),
    ]

    results = []
    emitted_by_job = []
    for index, (kind, options) in enumerate(cases, start=1):
        emitted = []
        results.append(
            worker_main.run_job(
                worker_main.StartCommand(
                    job_id=f"job-{index}", job_kind=kind, options=options
                ),
                emitted.append,
                threading.Event(),
            )
        )
        emitted_by_job.append(emitted)

    assert [name for name, _args, _kwargs in constructed] == [
        "DownloadWorker",
        "TrackPlanWorker",
        "OrganizeWorker",
        "MissingIssuesWorker",
    ]
    assert all(result.outcome == "success" for result in results)
    assert constructed[0][1] == (
        ["Model Railroader"],
        "D:/Magazine PDFs",
        True,
        False,
        "D:/account.json",
        True,
    )
    assert constructed[0][2] == {"include_specials": True}
    assert constructed[1][1] == ("D:/Track Plans", "D:/account.json")
    assert constructed[2][1] == ("D:/Incoming", "D:/Library", "MRR")
    assert constructed[3][2] == {
        "prefix": "MRR",
        "archive_url": "https://example.invalid/archive/",
        "missing_by_year": {"2024": ["March"]},
        "dest_dir": "D:/Library",
        "cookies_path": "D:/account.json",
        "headless": True,
    }
    assert {
        "event": "log",
        "level": "info",
        "message": "fake worker log",
    } in emitted_by_job[0]
    assert {"event": "progress", "done": 2, "total": 4} in emitted_by_job[0]
    assert {
        "event": "progress",
        "per_magazine": {"Model Railroader": {"done": 1, "total": 2}},
    } in emitted_by_job[0]
    assert {
        "event": "progress",
        "message": "2 / 4 issues · almost done",
    } in emitted_by_job[0]
    assert {
        "event": "progress",
        "per_magazine": {"Model Railroader": {"done": 1, "total": 2}},
    } in emitted_by_job[0]
    assert {
        "event": "progress",
        "message": "2 / 4 issues · almost done",
    } in emitted_by_job[0]


def test_run_job_does_not_start_when_cancelled_before_worker_start(monkeypatch):
    worker_main = _worker_main()
    constructed = []
    module = _fake_trains_app(constructed)
    started = []
    base_worker = module.DownloadWorker

    class TrackingWorker(base_worker):
        def start(self):
            started.append(True)

    module.DownloadWorker = TrackingWorker
    monkeypatch.setitem(sys.modules, "trains_app", module)
    cancel_event = threading.Event()
    cancel_event.set()

    result = worker_main.run_job(
        worker_main.StartCommand(
            job_id="pre-cancelled",
            job_kind="magazines",
            options={
                "magazines": ["Model Railroader"],
                "base_dir": "D:/Magazine PDFs",
                "headless": True,
                "test_mode": False,
                "cookies_path": "D:/account.json",
                "newest_first": True,
                "include_specials": True,
            },
        ),
        lambda _event: None,
        cancel_event,
    )

    assert result.outcome == module.OUTCOME_CANCELLED
    assert started == []


def test_run_job_stops_worker_immediately_if_cancelled_during_start(monkeypatch):
    worker_main = _worker_main()
    constructed = []
    module = _fake_trains_app(constructed)
    cancel_event = threading.Event()
    calls = []
    base_worker = module.DownloadWorker

    class StartupCancellationWorker(base_worker):
        def start(self):
            super().start()
            cancel_event.set()

        def stop(self):
            calls.append("stop")
            super().stop()

        def wait(self, _timeout=None):
            calls.append("wait")
            return True

    module.DownloadWorker = StartupCancellationWorker
    monkeypatch.setitem(sys.modules, "trains_app", module)

    result = worker_main.run_job(
        worker_main.StartCommand(
            job_id="startup-cancelled",
            job_kind="magazines",
            options={
                "magazines": ["Model Railroader"],
                "base_dir": "D:/Magazine PDFs",
                "headless": True,
                "test_mode": False,
                "cookies_path": "D:/account.json",
                "newest_first": True,
                "include_specials": True,
            },
        ),
        lambda _event: None,
        cancel_event,
    )

    assert result.outcome == module.OUTCOME_CANCELLED
    assert calls == ["stop", "wait"]


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_worker_preserves_partial_organize_summary_and_terminal_outcome(
    monkeypatch, tmp_path, outcome
):
    worker_main = _worker_main()
    constructed = []
    module = _fake_trains_app(constructed)
    partial_summary = {
        "moved": 1,
        "scan_complete": False,
        "missing_by_prefix_year": {"MRR": {"2024": ["February"]}},
    }
    base_worker = _fake_worker_class("OrganizeWorker", constructed)

    class FailedOrganizeWorker(base_worker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.outcome = outcome
            self.result = partial_summary

    module.OrganizeWorker = FailedOrganizeWorker
    monkeypatch.setitem(sys.modules, "trains_app", module)
    stdout = io.StringIO()
    exit_code = worker_main.run_worker_stdio(
        io.StringIO(
            _start_line(
                job_id="organize-failed",
                job_kind="organize",
                options={
                    "source_dir": "D:/Incoming",
                    "destination_dir": "D:/Library",
                    "hint_prefix": "MRR",
                },
            )
            + "\n"
        ),
        stdout,
        tmp_path / "worker-data",
    )
    events = [decode_event(line) for line in stdout.getvalue().splitlines()]

    assert exit_code == 0
    assert events[-1].event == "completed"
    assert events[-1].payload == {
        "outcome": outcome,
        "summary": partial_summary,
    }


def test_worker_emits_no_results_for_completed_empty_organize(monkeypatch, tmp_path):
    worker_main = _worker_main()
    constructed = []
    module = _fake_trains_app(constructed)
    empty_summary = {
        "moved": 0,
        "already_correct": 0,
        "unrecognized": 0,
        "corrupt": 0,
        "conflicts": 0,
        "metadata_stamped": 0,
        "report": [],
        "missing_by_prefix_year": {},
        "scan_complete": True,
    }
    base_worker = _fake_worker_class("OrganizeWorker", constructed)

    class EmptyOrganizeWorker(base_worker):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.outcome = "no-results"
            self.result = empty_summary

    module.OrganizeWorker = EmptyOrganizeWorker
    monkeypatch.setitem(sys.modules, "trains_app", module)
    stdout = io.StringIO()
    exit_code = worker_main.run_worker_stdio(
        io.StringIO(
            _start_line(
                job_id="organize-empty",
                job_kind="organize",
                options={
                    "source_dir": "D:/Incoming",
                    "destination_dir": "D:/Library",
                    "hint_prefix": None,
                },
            )
            + "\n"
        ),
        stdout,
        tmp_path / "worker-data",
    )
    events = [decode_event(line) for line in stdout.getvalue().splitlines()]

    assert exit_code == 0
    assert events[-1].payload == {
        "outcome": "no-results",
        "summary": empty_summary,
    }


def test_worker_streams_log_progress_and_one_completed_event(monkeypatch, tmp_path):
    worker_main = _worker_main()

    def fake_run_job(command, emit, cancel_event):
        assert command.job_id == "job-2"
        assert not cancel_event.is_set()
        emit({"event": "log", "level": "info", "message": "scan started"})
        emit(
            {
                "event": "progress",
                "done": 3,
                "total": 12,
                "message": "3 / 12 issues · calculating...",
                "per_magazine": {"Model Railroader": {"done": 3, "total": 8}},
            }
        )
        return worker_main.WorkerResult(outcome="success", summary={"downloaded": 3})

    monkeypatch.setattr(worker_main, "run_job", fake_run_job)
    stdout = io.StringIO()
    result = worker_main.run_worker_stdio(
        io.StringIO(_start_line(job_id="job-2") + "\n"), stdout, tmp_path
    )
    events = [decode_event(line) for line in stdout.getvalue().splitlines()]

    assert result == 0
    assert [event.event for event in events] == [
        "started",
        "log",
        "progress",
        "completed",
    ]
    assert events[-1].payload == {
        "outcome": "success",
        "summary": {"downloaded": 3},
    }


def test_worker_adapts_engine_failure_log_lines_as_errors(monkeypatch):
    worker_main = _worker_main()
    constructed = []
    module = _fake_trains_app(constructed)
    base_worker = _fake_worker_class("DownloadWorker", constructed)

    class EngineFailureWorker(base_worker):
        def start(self):
            self.signals.log.emit("  FAILED: PDF download failed: timeout")
            self.signals.log.emit(
                "Track plan run finished with failures: 0 downloaded, 0 skipped."
            )
            self.signals.log.emit(
                "Archive discovery was incomplete; could not confirm whether issues exist."
            )
            self.signals.log.emit("Starting the next archive page.")

    module.DownloadWorker = EngineFailureWorker
    monkeypatch.setitem(sys.modules, "trains_app", module)
    emitted = []
    options = {
        "magazines": ["Model Railroader"],
        "base_dir": "D:/Magazine PDFs",
        "headless": True,
        "test_mode": False,
        "cookies_path": None,
        "newest_first": True,
        "include_specials": False,
    }

    worker_main.run_job(
        worker_main.StartCommand("job-errors", "magazines", options),
        emitted.append,
        threading.Event(),
    )

    logs = [record for record in emitted if record["event"] == "log"]
    assert [(record["level"], record["message"]) for record in logs] == [
        ("error", "  FAILED: PDF download failed: timeout"),
        (
            "error",
            "Track plan run finished with failures: 0 downloaded, 0 skipped.",
        ),
        (
            "error",
            "Archive discovery was incomplete; could not confirm whether issues exist.",
        ),
        ("info", "Starting the next archive page."),
    ]


def test_worker_stdio_reads_utf8_paths_when_windows_locale_is_legacy(
    tmp_path,
):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "Bibliothèque 東京"
    destination = tmp_path / "Archive – Édition"
    source.mkdir()
    request = {
        "v": 1,
        "job_id": "unicode-paths",
        "command": "start",
        "job_kind": "organize",
        "options": {
            "source_dir": str(source),
            "destination_dir": str(destination),
            "hint_prefix": None,
        },
    }
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    environment.pop("PYTHONUTF8", None)
    environment["TRAINS_DATA_DIR"] = str(tmp_path / "worker-data")
    result = subprocess.run(
        [sys.executable, str(root / "worker_main.py"), "--stdio"],
        cwd=root,
        env=environment,
        input=json.dumps(request, ensure_ascii=False) + "\n",
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    events = [decode_event(line) for line in result.stdout.splitlines()]
    completed = [event for event in events if event.event == "completed"]
    assert len(completed) == 1
    assert completed[0].job_id == "unicode-paths"
    assert completed[0].payload["outcome"] == "no-results"
    assert completed[0].payload["summary"]["scan_complete"] is True


def test_worker_uses_temp_data_dir_with_spaces_and_unicode(tmp_path):
    worker_main = _worker_main()
    data_dir = tmp_path / "Rail Library 東京"
    script = r'''
import io, json, sys
import worker_main
observed = {}
def fake_run_job(command, emit, cancel_event):
    import trains_app
    observed["base_dir"] = trains_app._BASE_DIR
    return worker_main.WorkerResult(outcome="no-results")
worker_main.run_job = fake_run_job
request = {"v": 1, "job_id": "job-path", "command": "start", "job_kind": "organize", "options": {}}
worker_main.run_worker_stdio(io.StringIO(json.dumps(request) + "\n"), io.StringIO(), sys.argv[1])
print(observed["base_dir"])
'''
    env = os.environ.copy()
    env.pop("TRAINS_DATA_DIR", None)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-c", script, str(data_dir)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(data_dir)
    assert data_dir.is_dir()
    assert (data_dir / "trains_downloader.log").is_file()


def test_worker_rejects_second_start_command(monkeypatch, tmp_path):
    worker_main = _worker_main()

    def waiting_run_job(_command, _emit, cancel_event):
        assert cancel_event.wait(timeout=2)
        return worker_main.WorkerResult(outcome="cancelled")

    monkeypatch.setattr(worker_main, "run_job", waiting_run_job)
    lines = _start_line(job_id="job-3") + "\n" + _start_line(job_id="job-4") + "\n"
    stdout = io.StringIO()
    result = worker_main.run_worker_stdio(io.StringIO(lines), stdout, tmp_path)
    events = [decode_event(line) for line in stdout.getvalue().splitlines()]

    assert result != 0
    assert [event.event for event in events].count("completed") == 1
    assert events[-1].payload["outcome"] == "failed"
    assert any(event.event == "error" for event in events)


def test_cookie_contents_never_reach_any_output_stream(monkeypatch, tmp_path, capsys):
    worker_main = _worker_main()
    cookie_path = tmp_path / "session_cookies.json"
    sentinel = "COOKIE-VALUE-MUST-STAY-PRIVATE"
    cookie_path.write_text('{"session":"' + sentinel + '"}', encoding="utf-8")
    seen_options = []

    def fake_run_job(command, _emit, _cancel_event):
        seen_options.append(command.options)
        return worker_main.WorkerResult(outcome="success")

    monkeypatch.setattr(worker_main, "run_job", fake_run_job)
    options = {"cookies_path": str(cookie_path)}
    stdout = io.StringIO()
    worker_main.run_worker_stdio(
        io.StringIO(_start_line(options=options) + "\n"), stdout, tmp_path
    )
    stderr = capsys.readouterr().err

    assert seen_options == [options]
    assert sentinel not in stdout.getvalue()
    assert sentinel not in stderr


def test_worker_cli_uses_script_directory_by_default(monkeypatch, tmp_path):
    worker_main = _worker_main()
    observed = []
    output = io.StringIO()

    def capture_data_dir(_stdin, _stdout, data_dir):
        observed.append(Path(data_dir))
        return 0

    monkeypatch.delenv("TRAINS_DATA_DIR", raising=False)
    monkeypatch.setattr(worker_main.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(worker_main.sys, "frozen", False, raising=False)
    monkeypatch.setattr(worker_main.sys, "stdout", output)
    monkeypatch.setattr(worker_main, "run_worker_stdio", capture_data_dir)

    assert worker_main.main(["--stdio"]) == 0
    assert observed == [Path(worker_main.__file__).resolve().parent]
