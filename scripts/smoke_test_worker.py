"""Run one isolated organizer request through the packaged Python worker."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worker_protocol import decode_event


def main() -> int:
    executable = os.environ.get("TRAINSDOWNLOADER_WORKER")
    if not executable:
        raise SystemExit("TRAINSDOWNLOADER_WORKER is not set")
    worker = Path(executable)
    if not worker.is_file() or worker.stat().st_size == 0:
        raise SystemExit(f"Packaged worker does not exist or is empty: {worker}")

    job_id = f"package-smoke-{uuid.uuid4()}"
    with tempfile.TemporaryDirectory(prefix="trains-worker-smoke-") as data_root:
        root = Path(data_root)
        source = root / "incoming-東京"
        destination = root / "Archive – Édition"
        source.mkdir()
        request = {
            "v": 1,
            "job_id": job_id,
            "command": "start",
            "job_kind": "organize",
            "options": {
                "source_dir": str(source),
                "destination_dir": str(destination),
                "hint_prefix": None,
            },
        }
        environment = os.environ.copy()
        environment["TRAINS_DATA_DIR"] = str(root / "app-data")
        environment["PYTHONIOENCODING"] = "cp1252"
        environment.pop("PYTHONUTF8", None)
        result = subprocess.run(
            [str(worker), "--stdio"],
            input=json.dumps(request, ensure_ascii=False) + "\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            env=environment,
            check=False,
        )

    if result.returncode != 0:
        raise SystemExit(
            f"Packaged worker exited with {result.returncode}.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    events = []
    for line in result.stdout.splitlines():
        try:
            events.append(decode_event(line))
        except ValueError as error:
            raise SystemExit(f"Packaged worker returned invalid protocol output: {error}") from None
    if not any(event.event == "started" and event.job_id == job_id for event in events):
        raise SystemExit("Packaged worker did not report that the isolated job started")
    completed = [event for event in events if event.event == "completed" and event.job_id == job_id]
    if len(completed) != 1 or completed[0].payload.get("outcome") != "no-results":
        raise SystemExit(f"Packaged worker returned an unexpected terminal result: {completed}")
    print("Packaged Python worker completed an isolated organize request.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
