"""Behavior tests for the versioned JSON-lines worker protocol."""

import importlib

import pytest


def _codec():
    try:
        return importlib.import_module("worker_protocol")
    except ModuleNotFoundError:
        pytest.fail("worker_protocol.py codec is missing", pytrace=False)


def test_decode_start_and_cancel_v1():
    codec = _codec()

    start = codec.decode_command(
        '{"v":1,"job_id":"job-7","command":"start",'
        '"job_kind":"magazines","options":{"base_dir":"D:/Rail PDFs"}}'
    )
    cancel = codec.decode_command(
        '{"v":1,"job_id":"job-7","command":"cancel"}'
    )

    assert start == codec.StartCommand(
        job_id="job-7",
        job_kind="magazines",
        options={"base_dir": "D:/Rail PDFs"},
    )
    assert cancel == codec.CancelCommand(job_id="job-7")


@pytest.mark.parametrize(
    "line",
    [
        '{"v":2,"job_id":"job-1","command":"cancel"}',
        '{"v":1,"job_id":"job-1","command":"launch"}',
        '{"v":1,"job_id":"job-1","command":"start",'
        '"job_kind":"unknown","options":{}}',
        '{"v":1,"job_id":"job-1","command":"start",'
        '"job_kind":"magazines","options":}',
    ],
)
def test_decode_rejects_bad_version_unknown_job_and_malformed_json(line):
    codec = _codec()

    with pytest.raises(codec.ProtocolError):
        codec.decode_command(line)


def test_decode_rejects_unknown_event_and_invalid_payload():
    codec = _codec()

    with pytest.raises(codec.ProtocolError):
        codec.decode_event(
            '{"v":1,"job_id":"job-1","event":"surprise"}'
        )
    with pytest.raises(codec.ProtocolError):
        codec.decode_event(
            '{"v":1,"job_id":"job-1","event":"progress",'
            '"done":"four","total":4}'
        )


def test_decode_rejects_unhashable_enum_values():
    codec = _codec()

    with pytest.raises(codec.ProtocolError):
        codec.decode_event(
            '{"v":1,"job_id":"job-1","event":"log",'
            '"level":["info"],"message":"hello"}'
        )
    with pytest.raises(codec.ProtocolError):
        codec.decode_event(
            '{"v":1,"job_id":"job-1","event":"completed",'
            '"outcome":{"state":"success"}}'
        )


def test_encode_rejects_non_json_payload():
    codec = _codec()

    with pytest.raises(codec.ProtocolError):
        codec.encode_event(
            job_id="job-1",
            event="log",
            payload={"level": "info", "message": object()},
        )


def test_event_round_trip_preserves_unicode_and_newlines():
    codec = _codec()
    message = "Édition spéciale — 東京\nNext line"

    line = codec.encode_event(
        job_id="job-42",
        event="log",
        payload={"level": "info", "message": message},
    )
    decoded = codec.decode_event(line)

    assert "\n" not in line
    assert decoded.job_id == "job-42"
    assert decoded.event == "log"
    assert decoded.payload == {"level": "info", "message": message}
