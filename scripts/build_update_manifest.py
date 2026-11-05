"""Build the static update feed consumed by the Tauri updater."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote


SUPPORTED_ARCHITECTURES = {"x86_64", "aarch64", "i686", "armv7"}
PLATFORM_ASSETS = (
    ("windows", "windows", "x86_64", "TrainsDownloader-windows-setup.exe"),
    ("linux", "linux", "x86_64", "TrainsDownloader-linux.AppImage"),
    (
        "macos",
        "darwin",
        "aarch64",
        "TrainsDownloader-macos-aarch64.app.tar.gz",
    ),
    (
        "macos",
        "darwin",
        "x86_64",
        "TrainsDownloader-macos-x86_64.app.tar.gz",
    ),
)
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def _required_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Required update {label} is missing or empty: {path}")
    return path


def _validate_architecture_metadata(
    release_dir: Path, platform: str, expected_architecture: str
) -> None:
    metadata_path = _required_file(
        release_dir
        / f"update-architecture-{platform}-{expected_architecture}.json",
        "architecture metadata",
    )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Invalid architecture metadata: {metadata_path}") from error
    architecture = metadata.get("architecture")
    if (
        metadata.get("platform") != platform
        or architecture not in SUPPORTED_ARCHITECTURES
        or architecture != expected_architecture
    ):
        raise ValueError(
            f"Invalid or unsupported architecture metadata for {platform}: {metadata_path}"
        )


def build_manifest(
    release_dir: Path,
    *,
    version: str,
    repository: str,
    notes: str = "",
) -> dict[str, object]:
    if not SEMVER.fullmatch(version):
        raise ValueError(f"Release version must be a semantic version: {version!r}")
    owner_repo = repository.strip("/")
    if owner_repo.count("/") != 1 or any(part in {"", ".", ".."} for part in owner_repo.split("/")):
        raise ValueError(f"Repository must use the owner/name form: {repository!r}")

    platforms: dict[str, dict[str, str]] = {}
    for artifact_platform, updater_os, architecture, asset_name in PLATFORM_ASSETS:
        _validate_architecture_metadata(release_dir, artifact_platform, architecture)
        target = f"{updater_os}-{architecture}"
        artifact = _required_file(release_dir / asset_name, "artifact")
        signature_path = _required_file(
            Path(f"{artifact}.sig"), "signature"
        )
        signature = signature_path.read_text(encoding="utf-8").strip()
        if not signature:
            raise ValueError(f"Required update signature is empty: {signature_path}")
        platforms[target] = {
            "url": (
                f"https://github.com/{owner_repo}/releases/download/v{version}/"
                f"{quote(asset_name, safe='-_.')}"
            ),
            "signature": signature,
        }

    return {
        "version": version,
        "notes": notes.rstrip(),
        "platforms": platforms,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--repository",
        default="gmoran1016/Trains.com-PDF-Downloader-Renamer",
    )
    parser.add_argument("--notes-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    notes = ""
    if args.notes_file:
        if not args.notes_file.is_file():
            raise SystemExit(f"Release notes file is missing: {args.notes_file}.")
        notes = args.notes_file.read_text(encoding="utf-8")
    try:
        manifest = build_manifest(
            args.release_dir,
            version=args.version,
            repository=args.repository,
            notes=notes,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    output_path = args.output or args.release_dir / "latest.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote signed update manifest to {output_path}.")


if __name__ == "__main__":
    main()
