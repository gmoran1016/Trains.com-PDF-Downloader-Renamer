# Python Worker Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run existing magazine, track-plan, and organizer jobs as a headless Python process with a strict versioned JSON-lines interface.

**Architecture:** Reuse the existing Python job logic and QThread workers behind a `QCoreApplication` worker entry point. Each process accepts one job, streams typed events on stdout, reads a cooperative cancel command on stdin, and exits after one terminal result.

**Tech Stack:** Python 3.13 in CI, existing PyQt5 QtCore workers, `json`, `threading`, and pytest.

**Spec:** [docs/rust-ui-design-spec.md](../../rust-ui-design-spec.md)

## Global Constraints

- Protocol envelope fields are `v`, `job_id`, `command` or `event`; `v` is exactly `1`.
- Supported `job_kind` values are `magazines`, `track-plans`, `organize`, and `download-missing`.
- A process accepts one `start` command, optional `cancel` commands for that `job_id`, and emits exactly one terminal `completed` event.
- Worker stdout contains protocol records only. Diagnostics go to the established log file or stderr.
- The worker receives cookie paths, never cookie contents.
- `TRAINS_DATA_DIR` overrides the frozen worker's default directory so settings, logs, cookie lookup, progress, and special-issue cache stay beside the Rust app.
- No live site access or user-library writes in tests.

## Review Focus

- A malformed line, unsupported version, invalid job kind, or mismatched job ID must fail cleanly and terminate the job rather than hang.
- An archive error with partial matches must serialize those matches while retaining `failed` as its outcome.
- Stop must reach each supported worker; organize cancellation must stop between file operations and report the partial summary.
- A cookie file containing a sentinel value must not cause that value to appear in stdout, stderr, or the log file.

---

### Task 1: Define protocol v1 and codecs

**Files:**
- Create: `docs/worker-protocol-v1.md`
- Create: `worker_protocol.py`
- Create: `tests/test_worker_protocol.py`

**Interfaces:**
- `decode_command(line: str) -> StartCommand | CancelCommand`
- `decode_event(line: str) -> WorkerEvent`
- `encode_event(job_id: str, event: str, payload: dict[str, object]) -> str`
- `ProtocolError` for malformed JSON, wrong version, invalid fields, or unknown command/event.
- A start record has `{ "v": 1, "job_id": str, "command": "start", "job_kind": str, "options": object }`.
- A cancel record has `{ "v": 1, "job_id": str, "command": "cancel" }`.
- Event records have `{ "v": 1, "job_id": str, "event": str, ... }`; event names are `started`, `log`, `progress`, `error`, and `completed`.
- `log` carries `level` and `message`; `progress` carries optional overall `done`/`total`, the existing human-readable status/ETA as `message`, and `per_magazine`, keyed by the existing publication name with `{ "done": u64, "total": u64 }` values. Do not invent or recalculate per-publication ETA. `error` carries a sanitized `message`; `completed` carries one terminal `outcome` and an optional JSON `summary`. An `error` event does not replace the required terminal `completed` event.

- [x] **Step 1: Write codec tests** named `test_decode_start_and_cancel_v1`, `test_decode_rejects_bad_version_unknown_job_and_malformed_json`, `test_decode_rejects_unknown_event_and_invalid_payload`, `test_decode_rejects_unhashable_enum_values`, `test_encode_rejects_non_json_payload`, and `test_event_round_trip_preserves_unicode_and_newlines`. Keep the cookie sentinel assertion in the worker integration test, where it covers actual adapter output.
- [x] **Step 2: Run `python -m pytest tests/test_worker_protocol.py -q` and confirm the new tests fail because the codec is absent.**
- [x] **Step 3: Implement the schema document, typed command/event records, strict command and event decoders, and JSON-line encoder.** Reject unknown versions, invalid event names, and event payloads that do not match the schema; JSON-escape messages so every event occupies exactly one physical line.
- [x] **Step 4: Run `python -m pytest tests/test_worker_protocol.py -q` and confirm all codec tests pass.**

### Task 2: Add the headless worker entry point

**Files:**
- Create: `worker_main.py`
- Modify: `trains_app.py` (`_BASE_DIR`, entry point, worker signal adapters)
- Create: `tests/test_worker_integration.py`

**Interfaces:**
- `run_worker_stdio(stdin: TextIO, stdout: TextIO, data_dir: Path) -> int` reads one start record, starts one current job worker, and emits its events.
- `run_job(command: StartCommand, emit: Callable[[dict[str, object]], None], cancel_event: threading.Event) -> WorkerResult` dispatches the four job kinds to the existing job classes.
- A `progress` event carries optional overall `done`/`total`, the existing human-readable status/ETA as `message`, and `per_magazine`, keyed by the existing publication name with `{ "done": u64, "total": u64 }` values. `completed` carries one terminal outcome and optional job summary.

- [x] **Step 1: Write fake-worker integration tests** named `test_worker_dispatches_all_job_kinds`, `test_worker_streams_log_progress_and_one_completed_event`, `test_worker_uses_temp_data_dir_with_spaces_and_unicode`, `test_worker_rejects_second_start_command`, `test_cookie_contents_never_reach_any_output_stream`, and `test_worker_cli_uses_script_directory_by_default`.
- [x] **Step 2: Run `python -m pytest tests/test_worker_integration.py -q` and confirm they fail before the entry point exists.**
- [x] **Step 3: Implement `worker_main.py --stdio` using `QCoreApplication`; connect existing worker signals to typed protocol events, and bridge stdin cancellation through a reader thread. Keep stdout free of logger output.
- [x] **Step 4: Make `_BASE_DIR` use `TRAINS_DATA_DIR` when set and otherwise retain its current frozen/script location.** Keep existing worker defaults and file formats.
- [x] **Step 5: Run `python -m pytest tests/test_worker_integration.py tests/test_worker_protocol.py -q` and confirm the protocol and fake-worker tests pass without network access.**

### Task 3: Preserve terminal outcomes and cooperative stop

**Files:**
- Modify: `trains_app.py` (`OrganizeWorker`, `organize_pdfs`, job outcome serialization)
- Modify: `tests/test_trains_app.py`
- Modify: `tests/test_worker_integration.py`

**Interfaces:**
- Add optional `cancel_event: threading.Event | None = None` to `organize_pdfs`; check it between file operations and return the partial `OrganizeSummary`.
- Add `OrganizeWorker.stop()` and serialize cancellation as `cancelled`, never `success`.
- Preserve the existing partial archive result and mark an incomplete scan `failed` in its terminal worker event.

- [x] **Step 1: Add `test_organize_stops_between_files_with_partial_summary`, `test_failed_scan_retains_partial_matches_and_failed_outcome`, and `test_no_results_is_not_failure` before changing worker behavior.**
- [x] **Step 2: Run `python -m pytest tests/test_trains_app.py tests/test_worker_integration.py -q` and confirm the new cases fail.**
- [x] **Step 3: Implement cooperative organizer cancellation and map every existing worker's final `outcome` into the protocol; do not discard partial summaries on failure or cancellation.**
- [x] **Step 4: Run `python -m pytest tests/test_trains_app.py tests/test_worker_protocol.py tests/test_worker_integration.py -q` and confirm all Python engine and worker tests pass.**
