"""Headless, one-job entry point for the bundled Python engine."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, is_dataclass
import importlib
import json
import os
from pathlib import Path
import queue
import sys
import threading
from typing import Any, Callable, TextIO

from worker_protocol import (
    CancelCommand,
    ProtocolError,
    StartCommand,
    decode_command,
    encode_event,
)


@dataclass(frozen=True)
class WorkerResult:
    outcome: str
    summary: dict[str, Any] | None = None


_QT_APP = None
_OUTPUT_LOCK = threading.Lock()


def _ensure_qcore_application():
    global _QT_APP
    from PyQt5.QtCore import QCoreApplication

    instance = QCoreApplication.instance()
    if instance is None:
        _QT_APP = QCoreApplication([])
    else:
        _QT_APP = instance
    return _QT_APP


def _job_worker(command: StartCommand, app):
    options = command.options

    if command.job_kind == "magazines":
        magazines = options["magazines"]
        if not magazines or any(name not in app.MAGAZINES for name in magazines):
            raise ValueError("Select at least one supported magazine")
        return app.DownloadWorker(
            magazines,
            options["base_dir"],
            options["headless"],
            options["test_mode"],
            options["cookies_path"],
            options["newest_first"],
            include_specials=options["include_specials"],
        )

    if command.job_kind == "track-plans":
        return app.TrackPlanWorker(
            options["destination_dir"], options["cookies_path"]
        )

    if command.job_kind == "organize":
        return app.OrganizeWorker(
            options["source_dir"],
            options["destination_dir"],
            options["hint_prefix"],
        )

    if command.job_kind == "download-missing":
        return app.MissingIssuesWorker(
            prefix=options["prefix"],
            archive_url=options["archive_url"],
            missing_by_year=options["missing_by_year"],
            dest_dir=options["destination_dir"],
            cookies_path=options["cookies_path"],
            headless=options["headless"],
        )

    raise ProtocolError("unsupported job kind")


def _require_options(
    options: dict[str, Any], *, required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    if set(options) - required - optional or required - set(options):
        raise ProtocolError("job options do not match the job schema")


def _validate_job_options(command: StartCommand) -> None:
    options = command.options
    schemas = {
        "magazines": {
            "required": {
                "magazines",
                "base_dir",
                "headless",
                "test_mode",
                "cookies_path",
                "newest_first",
                "include_specials",
            },
            "strings": {"base_dir"},
            "booleans": {"headless", "test_mode", "newest_first", "include_specials"},
        },
        "track-plans": {
            "required": {"destination_dir", "cookies_path"},
            "strings": {"destination_dir"},
            "booleans": set(),
        },
        "organize": {
            "required": {"source_dir", "destination_dir", "hint_prefix"},
            "strings": {"source_dir", "destination_dir"},
            "booleans": set(),
        },
        "download-missing": {
            "required": {
                "prefix",
                "archive_url",
                "missing_by_year",
                "destination_dir",
                "cookies_path",
                "headless",
            },
            "strings": {"prefix", "archive_url", "destination_dir"},
            "booleans": {"headless"},
        },
    }
    schema = schemas.get(command.job_kind)
    if schema is None:
        raise ProtocolError("unsupported job kind")
    _require_options(options, required=schema["required"])
    for key in schema["strings"]:
        if not isinstance(options[key], str) or not options[key]:
            raise ProtocolError(f"{key} must be a non-empty string")
    for key in schema["booleans"]:
        if type(options[key]) is not bool:
            raise ProtocolError(f"{key} must be a boolean")
    if "cookies_path" in options and options["cookies_path"] is not None:
        if not isinstance(options["cookies_path"], str):
            raise ProtocolError("cookies_path must be a string or null")
    if command.job_kind == "magazines":
        magazines = options["magazines"]
        if not isinstance(magazines, list) or any(
            not isinstance(name, str) or not name for name in magazines
        ):
            raise ProtocolError("magazines must be a list of publication names")
    if command.job_kind == "organize":
        hint_prefix = options["hint_prefix"]
        if hint_prefix is not None and not isinstance(hint_prefix, str):
            raise ProtocolError("hint_prefix must be a string or null")
    if command.job_kind == "download-missing":
        prefix, missing = options["prefix"], options["missing_by_year"]
        if not isinstance(prefix, str) or not prefix:
            raise ProtocolError("prefix must be a non-empty string")
        if not isinstance(missing, dict) or any(
            not isinstance(year, str)
            or not isinstance(months, list)
            or any(not isinstance(month, str) for month in months)
            for year, months in missing.items()
        ):
            raise ProtocolError("missing_by_year must map year strings to month arrays")


def _signal_connect(signal, callback, connection_type) -> None:
    try:
        signal.connect(callback, connection_type)
    except TypeError:
        # Small fake signals in integration tests have no Qt connection mode.
        signal.connect(callback)


def _worker_summary(worker) -> dict[str, Any] | None:
    summary = getattr(worker, "result", None)
    if summary is None:
        return None
    if is_dataclass(summary):
        summary = asdict(summary)
    if isinstance(summary, dict):
        return summary
    return None


def _engine_log_level(message: str) -> str:
    """Map legacy worker log text to the severity shown by the Rust UI."""

    normalized = message.strip().casefold()
    error_markers = (
        "failed:",
        "failure:",
        "failures:",
        "error:",
        "[error]",
        "archive discovery was incomplete",
        "archive scan incomplete",
        "finished with failures",
    )
    return "error" if any(marker in normalized for marker in error_markers) else "info"


def run_job(
    command: StartCommand,
    emit: Callable[[dict[str, object]], None],
    cancel_event: threading.Event,
) -> WorkerResult:
    """Dispatch one validated request to the existing Python worker classes."""

    _validate_job_options(command)
    _ensure_qcore_application()
    app = importlib.import_module("trains_app")
    if cancel_event.is_set():
        return WorkerResult(outcome=app.OUTCOME_CANCELLED)
    worker = _job_worker(command, app)
    from PyQt5.QtCore import Qt

    per_magazine: dict[str, dict[str, int]] = {}

    def emit_progress(**payload) -> None:
        emit({"event": "progress", **payload})

    _signal_connect(
        worker.signals.log,
        lambda message: emit({
            "event": "log",
            "level": _engine_log_level(str(message)),
            "message": str(message),
        }),
        Qt.DirectConnection,
    )
    _signal_connect(
        worker.signals.progress,
        lambda done, total: emit_progress(done=done, total=total),
        Qt.DirectConnection,
    )
    magazine_signal = getattr(worker.signals, "magazine_progress", None)
    if magazine_signal is not None:
        def magazine_progress(name, done, total):
            per_magazine[str(name)] = {"done": int(done), "total": int(total)}
            emit_progress(per_magazine=dict(per_magazine))

        _signal_connect(magazine_signal, magazine_progress, Qt.DirectConnection)
    status_signal = getattr(worker.signals, "status_msg", None)
    if status_signal is not None:
        _signal_connect(
            status_signal,
            lambda message: emit_progress(message=str(message)),
            Qt.DirectConnection,
        )
    error_signal = getattr(worker.signals, "error", None)
    if error_signal is not None:
        _signal_connect(
            error_signal,
            lambda message: emit(
                {"event": "error", "message": str(message)[:2000]}
            ),
            Qt.DirectConnection,
        )

    worker.start()
    stop_sent = False
    while True:
        if cancel_event.is_set() and not stop_sent:
            stop = getattr(worker, "stop", None)
            if callable(stop):
                stop()
            stop_sent = True
        finished = worker.wait(50)
        if cancel_event.is_set() and not stop_sent:
            stop = getattr(worker, "stop", None)
            if callable(stop):
                stop()
            stop_sent = True
        if finished:
            break

    outcome = getattr(worker, "outcome", None)
    if outcome is None:
        outcome = app.OUTCOME_SUCCESS if getattr(worker, "result", None) is not None else app.OUTCOME_FAILED
    return WorkerResult(outcome=outcome, summary=_worker_summary(worker))


def _emit_record(stdout: TextIO, job_id: str, record: dict[str, object]) -> None:
    if not isinstance(record, dict) or not isinstance(record.get("event"), str):
        raise ProtocolError("worker event is not a protocol record")
    event = record["event"]
    payload = {key: value for key, value in record.items() if key != "event"}
    line = encode_event(job_id, event, payload)
    with _OUTPUT_LOCK:
        stdout.write(line + "\n")
        stdout.flush()


def run_worker_stdio(stdin: TextIO, stdout: TextIO, data_dir: Path) -> int:
    """Run one JSON-lines job, with later input reserved for cancellation."""

    data_path = Path(data_dir).expanduser().resolve()
    data_path.mkdir(parents=True, exist_ok=True)
    previous_data_dir = os.environ.get("TRAINS_DATA_DIR")
    os.environ["TRAINS_DATA_DIR"] = str(data_path)
    try:
        first_line = stdin.readline()
        if not first_line:
            sys.stderr.write("worker input ended before a start command\n")
            return 2
        try:
            command = decode_command(first_line)
            if isinstance(command, CancelCommand):
                raise ProtocolError("worker must begin with a start command")
        except ProtocolError as error:
            sys.stderr.write(f"worker start command rejected: {error}\n")
            return 2

        cancel_event = threading.Event()
        control_errors: queue.Queue[str] = queue.Queue()

        def read_control_commands() -> None:
            while True:
                line = stdin.readline()
                if not line:
                    return
                try:
                    control = decode_command(line)
                except ProtocolError as error:
                    control_errors.put(str(error))
                    cancel_event.set()
                    return
                if not isinstance(control, CancelCommand):
                    control_errors.put("only one start command is allowed")
                    cancel_event.set()
                    return
                if control.job_id != command.job_id:
                    control_errors.put("cancel job_id does not match the active job")
                    cancel_event.set()
                    return
                cancel_event.set()

        reader = threading.Thread(
            target=read_control_commands,
            name="worker-command-reader",
            daemon=True,
        )
        reader.start()
        _emit_record(stdout, command.job_id, {"event": "started"})

        try:
            result = run_job(
                command,
                lambda record: _emit_record(stdout, command.job_id, record),
                cancel_event,
            )
            if not isinstance(result, WorkerResult):
                raise TypeError("worker returned an invalid result")
        except Exception as error:
            _emit_record(
                stdout,
                command.job_id,
                {"event": "error", "message": str(error)[:2000]},
            )
            result = WorkerResult(outcome="failed")

        try:
            control_error = control_errors.get_nowait()
        except queue.Empty:
            control_error = None
        if control_error is not None:
            _emit_record(
                stdout,
                command.job_id,
                {"event": "error", "message": control_error},
            )
            result = WorkerResult(outcome="failed", summary=result.summary)

        completed: dict[str, object] = {
            "event": "completed",
            "outcome": result.outcome,
        }
        if result.summary is not None:
            completed["summary"] = result.summary
        _emit_record(stdout, command.job_id, completed)
        return 1 if control_error is not None else 0
    finally:
        if previous_data_dir is None:
            os.environ.pop("TRAINS_DATA_DIR", None)
        else:
            os.environ["TRAINS_DATA_DIR"] = previous_data_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trains.com Python worker")
    parser.add_argument("--stdio", action="store_true")
    args = parser.parse_args(argv)
    if not args.stdio:
        parser.error("--stdio is required")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    data_dir = os.environ.get("TRAINS_DATA_DIR")
    if not data_dir:
        if getattr(sys, "frozen", False):
            data_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            data_dir = str(Path(__file__).resolve().parent)
    return run_worker_stdio(sys.stdin, sys.stdout, Path(data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
