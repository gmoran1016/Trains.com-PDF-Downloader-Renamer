"""Collect public downloads and signed Tauri updater artifacts."""
from __future__ import annotations

import argparse
import json
import platform
import shutil
from pathlib import Path


SUPPORTED_ARCHITECTURES = {"x86_64", "aarch64", "i686", "armv7"}
ARCHITECTURE_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
    "i386": "i686",
    "i686": "i686",
    "armv7l": "armv7",
    "armv7": "armv7",
}


def _one_file(directory: Path, pattern: str, description: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(
            f"Expected one {description}; found {len(matches)} in {directory}."
        )
    return matches[0]


def _architecture(machine: str | None = None) -> str:
    value = (machine or platform.machine()).lower()
    architecture = ARCHITECTURE_ALIASES.get(value)
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise SystemExit(f"Unsupported build architecture: {value}.")
    return architecture


def _copy_signed(source: Path, destination: Path) -> None:
    signature = Path(f"{source}.sig")
    if not source.is_file():
        raise SystemExit(f"Updater artifact is missing: {source}.")
    if not signature.is_file() or not signature.read_text(encoding="utf-8").strip():
        raise SystemExit(f"Updater signature is missing or empty: {signature}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    shutil.copy2(signature, Path(f"{destination}.sig"))


def collect_packages(
    platform_name: str,
    target_dir: Path,
    output_dir: Path,
    *,
    machine: str | None = None,
    expected_architecture: str | None = None,
) -> None:
    release = target_dir / "release"
    bundle = release / "bundle"
    output_dir.mkdir(parents=True, exist_ok=True)
    architecture = _architecture(machine)
    if expected_architecture and architecture != expected_architecture:
        raise SystemExit(
            f"Build architecture mismatch: expected {expected_architecture}, got {architecture}."
        )

    if platform_name == "windows":
        portable = release / "trains-desktop.exe"
        if not portable.is_file():
            raise SystemExit(f"Windows portable executable is missing: {portable}.")
        shutil.copy2(portable, output_dir / "TrainsDownloader-windows.exe")
        installer = _one_file(bundle / "nsis", "*.exe", "NSIS installer")
        _copy_signed(
            installer,
            output_dir / "TrainsDownloader-windows-setup.exe",
        )
    elif platform_name == "linux":
        appimage = _one_file(bundle / "appimage", "*.AppImage", "AppImage")
        _copy_signed(appimage, output_dir / "TrainsDownloader-linux.AppImage")
    elif platform_name == "macos":
        dmg = _one_file(bundle / "dmg", "*.dmg", "DMG")
        dmg_name = (
            "TrainsDownloader-macos.dmg"
            if architecture == "aarch64"
            else f"TrainsDownloader-macos-{architecture}.dmg"
        )
        shutil.copy2(dmg, output_dir / dmg_name)
        archive = _one_file(
            bundle / "macos", "*.app.tar.gz", "macOS updater archive"
        )
        archive_name = f"TrainsDownloader-macos-{architecture}.app.tar.gz"
        _copy_signed(archive, output_dir / archive_name)
    else:
        raise SystemExit(f"Unsupported platform: {platform_name}.")

    metadata = {
        "platform": platform_name,
        "architecture": architecture,
    }
    (output_dir / f"update-architecture-{platform_name}-{architecture}.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--platform", choices=("windows", "linux", "macos"), required=True
    )
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--architecture", choices=sorted(SUPPORTED_ARCHITECTURES))
    args = parser.parse_args()
    collect_packages(
        args.platform,
        args.target_dir,
        args.output_dir,
        expected_architecture=args.architecture,
    )
    print(f"Collected {args.platform} release packages in {args.output_dir}.")


if __name__ == "__main__":
    main()
