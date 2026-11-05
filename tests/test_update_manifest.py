from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_update_manifest import build_manifest
from scripts.collect_desktop_packages import collect_packages


REPOSITORY = "gmoran1016/Trains.com-PDF-Downloader-Renamer"


def write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_collect_windows_keeps_portable_asset_and_copies_signed_installer(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    output = tmp_path / "release"
    write_file(target / "release" / "trains-desktop.exe", "portable binary")
    installer = write_file(
        target / "release" / "bundle" / "nsis" / "Trains setup.exe",
        "NSIS installer",
    )
    write_file(Path(f"{installer}.sig"), "installer signature")

    collect_packages("windows", target, output, machine="AMD64")

    assert (output / "TrainsDownloader-windows.exe").read_text("utf-8") == "portable binary"
    assert (output / "TrainsDownloader-windows-setup.exe").read_text("utf-8") == "NSIS installer"
    assert (output / "TrainsDownloader-windows-setup.exe.sig").read_text("utf-8") == "installer signature"
    assert json.loads((output / "update-architecture-windows-x86_64.json").read_text("utf-8")) == {
        "platform": "windows",
        "architecture": "x86_64",
    }


def test_collect_linux_appimage_for_public_download_and_update(tmp_path: Path) -> None:
    target = tmp_path / "target"
    output = tmp_path / "release"
    appimage = write_file(
        target / "release" / "bundle" / "appimage" / "trains.AppImage",
        "AppImage bytes",
    )
    write_file(Path(f"{appimage}.sig"), "AppImage signature")

    collect_packages("linux", target, output, machine="x86_64")

    assert (output / "TrainsDownloader-linux.AppImage").read_text("utf-8") == "AppImage bytes"
    assert (output / "TrainsDownloader-linux.AppImage.sig").read_text("utf-8") == "AppImage signature"
    assert json.loads((output / "update-architecture-linux-x86_64.json").read_text("utf-8")) == {
        "platform": "linux",
        "architecture": "x86_64",
    }


def test_collect_macos_dmg_and_signed_app_archive(tmp_path: Path) -> None:
    target = tmp_path / "target"
    output = tmp_path / "release"
    write_file(
        target / "release" / "bundle" / "dmg" / "Trains.dmg",
        "DMG bytes",
    )
    archive = write_file(
        target / "release" / "bundle" / "macos" / "Trains.app.tar.gz",
        "app archive",
    )
    write_file(Path(f"{archive}.sig"), "app signature")

    collect_packages("macos", target, output, machine="arm64")

    assert (output / "TrainsDownloader-macos.dmg").read_text("utf-8") == "DMG bytes"
    assert (output / "TrainsDownloader-macos-aarch64.app.tar.gz").read_text("utf-8") == "app archive"
    assert (output / "TrainsDownloader-macos-aarch64.app.tar.gz.sig").read_text("utf-8") == "app signature"
    assert json.loads((output / "update-architecture-macos-aarch64.json").read_text("utf-8")) == {
        "platform": "macos",
        "architecture": "aarch64",
    }


def test_collect_macos_intel_uses_architecture_specific_release_assets(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    output = tmp_path / "release"
    write_file(
        target / "release" / "bundle" / "dmg" / "Trains.dmg",
        "Intel DMG",
    )
    archive = write_file(
        target / "release" / "bundle" / "macos" / "Trains.app.tar.gz",
        "Intel app archive",
    )
    write_file(Path(f"{archive}.sig"), "Intel signature")

    collect_packages("macos", target, output, machine="x86_64")

    assert (output / "TrainsDownloader-macos-x86_64.dmg").read_text("utf-8") == "Intel DMG"
    assert (output / "TrainsDownloader-macos-x86_64.app.tar.gz").read_text("utf-8") == "Intel app archive"
    assert json.loads((output / "update-architecture-macos-x86_64.json").read_text("utf-8")) == {
        "platform": "macos",
        "architecture": "x86_64",
    }


def write_manifest_inputs(release: Path) -> None:
    assets = {
        "TrainsDownloader-windows-setup.exe": "Windows installer",
        "TrainsDownloader-windows-setup.exe.sig": "Windows signature",
        "TrainsDownloader-linux.AppImage": "Linux AppImage",
        "TrainsDownloader-linux.AppImage.sig": "Linux signature",
        "TrainsDownloader-macos-aarch64.app.tar.gz": "macOS ARM app archive",
        "TrainsDownloader-macos-aarch64.app.tar.gz.sig": "macOS ARM signature",
        "TrainsDownloader-macos-x86_64.app.tar.gz": "macOS Intel app archive",
        "TrainsDownloader-macos-x86_64.app.tar.gz.sig": "macOS Intel signature",
    }
    for name, contents in assets.items():
        write_file(release / name, contents)
    architectures = {
        "windows-x86_64": ("windows", "x86_64"),
        "linux-x86_64": ("linux", "x86_64"),
        "macos-aarch64": ("macos", "aarch64"),
        "macos-x86_64": ("macos", "x86_64"),
    }
    for suffix, (platform, architecture) in architectures.items():
        write_file(
            release / f"update-architecture-{suffix}.json",
            json.dumps({"platform": platform, "architecture": architecture}),
        )


def test_manifest_contains_versioned_asset_urls_and_signature_contents(
    tmp_path: Path,
) -> None:
    release = tmp_path / "release"
    write_manifest_inputs(release)

    manifest = build_manifest(
        release,
        version="2.0.0",
        repository=REPOSITORY,
        notes="Adds consent-based update checks.",
    )

    assert manifest["version"] == "2.0.0"
    assert manifest["notes"] == "Adds consent-based update checks."
    assert manifest["platforms"] == {
        "windows-x86_64": {
            "url": f"https://github.com/{REPOSITORY}/releases/download/v2.0.0/TrainsDownloader-windows-setup.exe",
            "signature": "Windows signature",
        },
        "linux-x86_64": {
            "url": f"https://github.com/{REPOSITORY}/releases/download/v2.0.0/TrainsDownloader-linux.AppImage",
            "signature": "Linux signature",
        },
        "darwin-aarch64": {
            "url": f"https://github.com/{REPOSITORY}/releases/download/v2.0.0/TrainsDownloader-macos-aarch64.app.tar.gz",
            "signature": "macOS ARM signature",
        },
        "darwin-x86_64": {
            "url": f"https://github.com/{REPOSITORY}/releases/download/v2.0.0/TrainsDownloader-macos-x86_64.app.tar.gz",
            "signature": "macOS Intel signature",
        },
    }


@pytest.mark.parametrize(
    ("missing_name", "message"),
    [
        ("TrainsDownloader-windows-setup.exe.sig", "signature"),
        ("TrainsDownloader-linux.AppImage", "artifact"),
        ("update-architecture-macos-x86_64.json", "architecture"),
    ],
)
def test_manifest_rejects_a_missing_required_update_file(
    tmp_path: Path, missing_name: str, message: str
) -> None:
    release = tmp_path / "release"
    write_manifest_inputs(release)
    (release / missing_name).unlink()

    with pytest.raises(ValueError, match=message):
        build_manifest(release, version="2.0.0", repository=REPOSITORY)


def test_manifest_rejects_an_unsupported_architecture(tmp_path: Path) -> None:
    release = tmp_path / "release"
    write_manifest_inputs(release)
    write_file(
        release / "update-architecture-macos-aarch64.json",
        json.dumps({"platform": "macos", "architecture": "riscv64"}),
    )

    with pytest.raises(ValueError, match="unsupported architecture"):
        build_manifest(release, version="2.0.0", repository=REPOSITORY)


@pytest.mark.parametrize("version", ["", "v2.0.0", "1.10", "latest"])
def test_manifest_requires_a_plain_semver_release_version(
    tmp_path: Path, version: str
) -> None:
    release = tmp_path / "release"
    write_manifest_inputs(release)

    with pytest.raises(ValueError, match="semantic version"):
        build_manifest(release, version=version, repository=REPOSITORY)


def test_collector_rejects_an_unsigned_updater_bundle(tmp_path: Path) -> None:
    target = tmp_path / "target"
    output = tmp_path / "release"
    write_file(
        target / "release" / "bundle" / "appimage" / "trains.AppImage",
        "unsigned AppImage",
    )

    with pytest.raises(SystemExit, match="signature"):
        collect_packages("linux", target, output, machine="x86_64")
