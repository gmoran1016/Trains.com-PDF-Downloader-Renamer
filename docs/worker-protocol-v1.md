# Worker Protocol v1

The Rust desktop app and Python worker communicate through UTF-8 JSON-lines. Each physical line is one complete JSON object. Protocol version 1 is strict: unknown versions, commands, job kinds, events, fields, duplicate object keys, malformed JSON, and invalid field types are errors. A protocol error is surfaced by the Rust app as a failed job; raw input is not echoed into diagnostics.

## Process lifecycle

Each worker process handles one job. Rust starts the process with the data directory in `TRAINS_DATA_DIR`; it does not pass credentials in process arguments. The first input record must be `start`. Rust may later send `cancel` for the same `job_id`. The worker emits zero or more status, log, progress, or error events, then exactly one `completed` event and exits. An error event describes a problem but does not replace the terminal event.

Worker stdout is reserved for protocol records. Diagnostics go to the existing application log or stderr. The cookie-file path may appear in job options; cookie values must never appear in a command, event, Activity entry, log, or diagnostic.

## Commands

### Start

```json
{"v":1,"job_id":"job-123","command":"start","job_kind":"magazines","options":{}}
```

`job_id` is a non-empty string. `options` is a JSON object whose job-specific keys are:

| `job_kind` | Options |
|---|---|
| `magazines` | `magazines` (string array), `base_dir` (string), `headless` (boolean), `test_mode` (boolean), `cookies_path` (string or null), `newest_first` (boolean), `include_specials` (boolean) |
| `track-plans` | `destination_dir` (string), `cookies_path` (string or null) |
| `organize` | `source_dir` (string), `destination_dir` (string), `hint_prefix` (string or null) |
| `download-missing` | `prefix` (string), `archive_url` (string), `missing_by_year` (object from year strings to month-name arrays), `destination_dir` (string), `cookies_path` (string or null), `headless` (boolean) |

### Cancel

```json
{"v":1,"job_id":"job-123","command":"cancel"}
```

The worker stops at its next safe boundary. Completed file operations are not rolled back. It reports completed work and any partial organizer summary, and the terminal outcome is `cancelled`.

## Events

Every event has `v: 1`, the matching `job_id`, and an `event` name.

| Event | Payload |
|---|---|
| `started` | No additional fields. |
| `log` | `level` (`debug`, `info`, `warning`, or `error`) and `message` (string). |
| `progress` | Optional overall `done` and `total` (both non-negative integers), `message` (the existing status and ETA text), and `per_magazine` (map from publication name to `{ "done": integer, "total": integer }`). Per-publication ETA is not synthesized. |
| `error` | `message` (sanitized string). A later `completed` event is still required. |
| `completed` | `outcome` (`success`, `no-results`, `failed`, or `cancelled`) and optional job-specific `summary` object. |

Example progress event:

```json
{"v":1,"job_id":"job-123","event":"progress","done":3,"total":12,"message":"3 / 12 issues · calculating...","per_magazine":{"Model Railroader":{"done":3,"total":8}}}
```

For Organize, `summary` contains `moved`, `already_correct`, `unrecognized`, `corrupt`, `conflicts`, `metadata_stamped`, `report` (string array), `missing_by_prefix_year` (map from publication prefix to year to month-name arrays), and `scan_complete` (boolean). Partial values remain present when the outcome is `failed` or `cancelled`. An incomplete scan is `failed` even if it found partial results; `no-results` means a completed scan found no matching work. Rust must not offer Download Missing when `scan_complete` is false.
