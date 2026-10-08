"""Fail when the Python engine and Rust desktop release versions drift."""

from __future__ import annotations

import ast
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


def main() -> int:
    cargo = tomllib.loads((ROOT / "rust-ui" / "Cargo.toml").read_text(encoding="utf-8"))
    rust_version = cargo["package"]["version"]
    python_version = app_version()
    if rust_version != python_version:
        print(
            f"Version mismatch: Rust package is {rust_version}; Python engine is {python_version}.",
            file=sys.stderr,
        )
        return 1
    print(f"Rust UI and Python engine versions match: {rust_version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
