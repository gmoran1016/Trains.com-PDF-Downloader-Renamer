"""Strict JSON-lines protocol shared by the Rust UI and Python worker."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any


PROTOCOL_VERSION = 1
JOB_KINDS = frozenset(
    {"magazines", "track-plans", "organize", "download-missing"}
)
EVENT_NAMES = frozenset({"started", "log", "progress", "error", "completed"})
TERMINAL_OUTCOMES = frozenset({"success", "no-results", "failed", "cancelled"})
LOG_LEVELS = frozenset({"debug", "info", "warning", "error"})


class ProtocolError(ValueError):
    """A malformed or unsupported protocol record, without echoing its input."""


@dataclass(frozen=True)
class StartCommand:
    job_id: str
    job_kind: str
    options: dict[str, Any]


@dataclass(frozen=True)
class CancelCommand:
    job_id: str


@dataclass(frozen=True)
class WorkerEvent:
    job_id: str
    event: str
    payload: dict[str, Any]


def _reject_constant(_value: str) -> None:
    raise ProtocolError("non-standard JSON number")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON object key")
        result[key] = value
    return result


def _parse_record(line: str) -> dict[str, Any]:
    if not isinstance(line, str):
        raise ProtocolError("protocol record must be text")
    try:
        record = json.loads(
            line,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except ProtocolError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError, RecursionError):
        raise ProtocolError("malformed JSON record") from None
    if not isinstance(record, dict):
        raise ProtocolError("protocol record must be a JSON object")
    return record


def _check_envelope(record: dict[str, Any]) -> str:
    version = record.get("v")
    if type(version) is not int or version != PROTOCOL_VERSION:
        raise ProtocolError("unsupported protocol version")
    job_id = record.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise ProtocolError("job_id must be a non-empty string")
    return job_id


def _require_fields(
    record: dict[str, Any], *, required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    keys = set(record)
    missing = required - keys
    unknown = keys - required - optional
    if missing:
        raise ProtocolError("protocol record is missing required fields")
    if unknown:
        raise ProtocolError("protocol record contains unsupported fields")


def decode_command(line: str) -> StartCommand | CancelCommand:
    """Decode one v1 start or cancel command."""

    record = _parse_record(line)
    job_id = _check_envelope(record)
    command = record.get("command")

    if command == "start":
        _require_fields(
            record,
            required={"v", "job_id", "command", "job_kind", "options"},
        )
        job_kind = record["job_kind"]
        options = record["options"]
        if not isinstance(job_kind, str) or job_kind not in JOB_KINDS:
            raise ProtocolError("unsupported job kind")
        if not isinstance(options, dict):
            raise ProtocolError("start options must be a JSON object")
        return StartCommand(job_id=job_id, job_kind=job_kind, options=options)

    if command == "cancel":
        _require_fields(record, required={"v", "job_id", "command"})
        return CancelCommand(job_id=job_id)

    raise ProtocolError("unsupported worker command")


def _nonnegative_integer(value: Any) -> bool:
    return type(value) is int and value >= 0


def _validate_event_payload(event: str, payload: dict[str, Any]) -> None:
    if event == "started":
        _require_fields(payload, required=set())
        return

    if event == "log":
        _require_fields(payload, required={"level", "message"})
        if not isinstance(payload["level"], str) or payload["level"] not in LOG_LEVELS:
            raise ProtocolError("log level is invalid")
        if not isinstance(payload["message"], str):
            raise ProtocolError("log message must be text")
        return

    if event == "progress":
        _require_fields(
            payload,
            required=set(),
            optional={"done", "total", "message", "per_magazine"},
        )
        has_done = "done" in payload
        has_total = "total" in payload
        if has_done != has_total:
            raise ProtocolError("overall progress requires both done and total")
        if has_done and (
            not _nonnegative_integer(payload["done"])
            or not _nonnegative_integer(payload["total"])
        ):
            raise ProtocolError("progress counts must be non-negative integers")
        if "message" in payload and not isinstance(payload["message"], str):
            raise ProtocolError("progress message must be text")
        if "per_magazine" in payload:
            per_magazine = payload["per_magazine"]
            if not isinstance(per_magazine, dict):
                raise ProtocolError("per_magazine must be a JSON object")
            for name, progress in per_magazine.items():
                if not name.strip() or not isinstance(progress, dict):
                    raise ProtocolError("per-magazine progress is invalid")
                _require_fields(progress, required={"done", "total"})
                if not _nonnegative_integer(progress["done"]) or not _nonnegative_integer(
                    progress["total"]
                ):
                    raise ProtocolError("per-magazine counts must be non-negative integers")
        if not payload:
            raise ProtocolError("progress event must contain progress data")
        return

    if event == "error":
        _require_fields(payload, required={"message"})
        if not isinstance(payload["message"], str):
            raise ProtocolError("error message must be text")
        return

    if event == "completed":
        _require_fields(payload, required={"outcome"}, optional={"summary"})
        if (
            not isinstance(payload["outcome"], str)
            or payload["outcome"] not in TERMINAL_OUTCOMES
        ):
            raise ProtocolError("terminal outcome is invalid")
        if "summary" in payload and not isinstance(payload["summary"], dict):
            raise ProtocolError("completed summary must be a JSON object")
        return

    raise ProtocolError("unsupported worker event")


def decode_event(line: str) -> WorkerEvent:
    """Decode and validate one v1 worker event."""

    record = _parse_record(line)
    job_id = _check_envelope(record)
    event = record.get("event")
    if not isinstance(event, str) or event not in EVENT_NAMES:
        raise ProtocolError("unsupported worker event")
    _require_fields(
        record,
        required={"v", "job_id", "event"},
        optional={"level", "message", "done", "total", "per_magazine", "outcome", "summary"},
    )
    payload = {key: value for key, value in record.items() if key not in {"v", "job_id", "event"}}
    _validate_event_payload(event, payload)
    return WorkerEvent(job_id=job_id, event=event, payload=payload)


def encode_event(job_id: str, event: str, payload: dict[str, object]) -> str:
    """Encode one validated event as a single JSON record without a line ending."""

    if not isinstance(payload, dict):
        raise ProtocolError("event payload must be a JSON object")
    if {"v", "job_id", "event"} & set(payload):
        raise ProtocolError("event payload cannot replace envelope fields")
    record = {
        "v": PROTOCOL_VERSION,
        "job_id": job_id,
        "event": event,
        **payload,
    }
    try:
        line = json.dumps(
            record,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError):
        raise ProtocolError("event payload is not JSON serializable") from None
    # Validate the complete record after JSON serialization has normalized
    # custom mapping subclasses and all values to the wire representation.
    decode_event(line)
    return line
