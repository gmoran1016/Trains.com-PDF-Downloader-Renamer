"""Run the Rust desktop's native egui interaction smoke suite from pytest."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _cargo_executable() -> Path:
    discovered = shutil.which("cargo")
    if discovered:
        return Path(discovered)

    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo"))
    for name in ("cargo.exe", "cargo"):
        candidate = cargo_home / "bin" / name
        if candidate.is_file():
            return candidate
    raise AssertionError("Rust UI smoke checks require the Rust Cargo toolchain.")


def _windows_build_environment(environment: dict[str, str]) -> None:
    if os.name != "nt":
        return

    program_files_x86 = Path(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    )
    vswhere = program_files_x86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return
    installation = subprocess.run(
        [
            str(vswhere),
            "-latest",
            "-products",
            "*",
            "-property",
            "installationPath",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not installation:
        return

    vc_root = Path(installation) / "VC" / "Tools" / "MSVC"
    vc_versions = [path for path in vc_root.iterdir() if path.is_dir()]
    if not vc_versions:
        return
    vc = max(vc_versions, key=lambda path: tuple(int(part) for part in path.name.split(".")))

    sdk = program_files_x86 / "Windows Kits" / "10"
    sdk_include = sdk / "Include"
    sdk_versions = [
        path
        for path in sdk_include.iterdir()
        if path.is_dir() and path.name.startswith("10.")
    ]
    if not sdk_versions:
        return
    version = max(
        sdk_versions, key=lambda path: tuple(int(part) for part in path.name.split("."))
    ).name

    include_dirs = [
        vc / "include",
        *(
            sdk_include / version / name
            for name in ("ucrt", "shared", "um", "winrt", "cppwinrt")
        ),
    ]
    lib_dirs = [
        vc / "lib" / "x64",
        sdk / "Lib" / version / "ucrt" / "x64",
        sdk / "Lib" / version / "um" / "x64",
    ]
    environment["VCToolsInstallDir"] = str(vc) + os.sep
    environment["WindowsSdkDir"] = str(sdk) + os.sep
    environment["WindowsSDKVersion"] = version + os.sep
    environment["INCLUDE"] = os.pathsep.join(map(str, include_dirs))
    environment["LIB"] = os.pathsep.join(map(str, lib_dirs))
    environment["PATH"] = os.pathsep.join(
        [
            str(vc / "bin" / "Hostx64" / "x64"),
            str(sdk / "bin" / version / "x64"),
            environment["PATH"],
        ]
    )


def _short_target_path(target: Path) -> tuple[str, str | None]:
    if os.name != "nt":
        return str(target), None

    for letter in "RSTUVWXYZ":
        drive = f"{letter}:"
        if Path(drive + "\\").exists():
            continue
        subprocess.run(["subst", drive, str(target)], check=True, capture_output=True)
        return drive + "\\", drive
    return str(target), None


def test_rust_desktop_interaction_smoke() -> None:
    cargo = _cargo_executable()
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        [str(cargo.parent), environment.get("PATH", "")]
    )
    _windows_build_environment(environment)

    configured_target = environment.get("CARGO_TARGET_DIR")
    if configured_target:
        output = subprocess.run(
            [
                str(cargo),
                "test",
                "--manifest-path",
                str(ROOT / "rust-ui" / "Cargo.toml"),
                "--target-dir",
                configured_target,
                "--test",
                "workflow_ui_tests",
                "--test",
                "desktop_ui_tests",
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
        assert output.returncode == 0, output.stdout + output.stderr
        return

    with tempfile.TemporaryDirectory(prefix="trains-rust-ui-") as target_dir:
        target, mapped_drive = _short_target_path(Path(target_dir))
        try:
            output = subprocess.run(
                [
                    str(cargo),
                    "test",
                    "--manifest-path",
                    str(ROOT / "rust-ui" / "Cargo.toml"),
                    "--target-dir",
                    target,
                    "--test",
                    "workflow_ui_tests",
                    "--test",
                    "desktop_ui_tests",
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=900,
                check=False,
            )
        finally:
            if mapped_drive:
                subprocess.run(
                    ["subst", mapped_drive, "/d"], check=True, capture_output=True
                )
    assert output.returncode == 0, output.stdout + output.stderr
