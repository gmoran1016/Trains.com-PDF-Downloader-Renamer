"""Fail when any desktop or Python engine release version drifts."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def app_version() -> str:
    module = ast.parse((ROOT / "trains_app.py").read_text(encoding="utf-8"))
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == "APP_VERSION" for target in node.targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str):
                return value
    raise ValueError("APP_VERSION is missing or is not a string")


def locked_package_version(path: Path, package_name: str) -> str:
    lock = tomllib.loads(path.read_text(encoding="utf-8"))
    matches = [
        package["version"]
        for package in lock.get("package", [])
        if package.get("name") == package_name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {package_name} package in {path}, found {len(matches)}"
        )
    return matches[0]


def main() -> int:
    cargo = tomllib.loads((ROOT / "rust-ui" / "Cargo.toml").read_text(encoding="utf-8"))
    ui = ROOT / "desktop-ui"
    native = tomllib.loads((ui / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    controller_lock = ROOT / "rust-ui" / "Cargo.lock"
    desktop_lock = ui / "src-tauri/Cargo.lock"
    versions = {
        "Python engine": app_version(),
        "Rust controller": cargo["package"]["version"],
        "Rust controller lock": locked_package_version(
            controller_lock, "trains-com-downloader"
        ),
        "Rust desktop": native["package"]["version"],
        "Rust desktop lock": locked_package_version(desktop_lock, "trains-desktop"),
        "Desktop controller lock": locked_package_version(
            desktop_lock, "trains-com-downloader"
        ),
        "React UI": json.loads((ui / "package.json").read_text(encoding="utf-8"))["version"],
        "Tauri bundle": json.loads((ui / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))["version"],
        "npm lock": json.loads((ui / "package-lock.json").read_text(encoding="utf-8"))["packages"][""]["version"],
    }
    if len(set(versions.values())) != 1:
        print("Version mismatch: " + "; ".join(f"{name}: {value}" for name, value in versions.items()), file=sys.stderr)
        return 1
    print(f"All desktop and engine versions match: {versions['Python engine']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
