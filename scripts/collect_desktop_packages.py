"""Collect platform bundles without relying on versioned Tauri filenames."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=("windows", "linux", "macos"), required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    release = args.target_dir / "release"
    bundle = release / "bundle"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.platform == "windows":
        shutil.copy2(release / "trains-desktop.exe", args.output_dir / "TrainsDownloader-windows.exe")
        pattern, name = "nsis/*.exe", "TrainsDownloader-windows-setup.exe"
    elif args.platform == "linux":
        pattern, name = "appimage/*.AppImage", "TrainsDownloader-linux.AppImage"
    else:
        pattern, name = "dmg/*.dmg", "TrainsDownloader-macos.dmg"
    files = list(bundle.glob(pattern))
    if len(files) != 1:
        raise SystemExit(f"Expected one {args.platform} package; found {len(files)}.")
    shutil.copy2(files[0], args.output_dir / name)
    print(f"Collected {args.platform} release in {args.output_dir}.")


if __name__ == "__main__":
    main()
