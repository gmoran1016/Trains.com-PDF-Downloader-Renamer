@echo off
setlocal EnableExtensions

echo ============================================================
echo  Trains.com Rust Desktop Builder
echo ============================================================

set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"
set "CARGO_BIN=%USERPROFILE%\.cargo\bin\cargo.exe"
set "ROOT_PUSHED=0"
set "DRIVE_PUSHED=0"
set "SHORTDRIVE_MAPPED=0"
set "EXIT_CODE=1"

pushd "%PROJECT_ROOT%"
if errorlevel 1 goto :finish
set "ROOT_PUSHED=1"

if not exist "%PYTHON%" (
    echo ERROR: Project Python environment not found at "%PYTHON%".
    echo Create the project .venv and install requirements-dev.txt first.
    goto :finish
)

if exist "%CARGO_BIN%" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
where cargo >nul 2>nul
if errorlevel 1 (
    echo ERROR: Rust stable with Cargo is required. Install it from https://rustup.rs/ and reopen this terminal.
    goto :finish
)

set "SHORTDRIVE="
for %%D in (R S T U V W X Y Z Q P O N M L K J I H G F E D) do if not defined SHORTDRIVE if not exist %%D:\ set "SHORTDRIVE=%%D:"
if not defined SHORTDRIVE (
    echo ERROR: No unused drive letter is available for the short build path.
    goto :finish
)

subst %SHORTDRIVE% "%PROJECT_ROOT%"
if errorlevel 1 (
    echo ERROR: Could not create a short path for Cargo.
    goto :finish
)
set "SHORTDRIVE_MAPPED=1"
pushd %SHORTDRIVE%\
if errorlevel 1 goto :finish
set "DRIVE_PUSHED=1"

set "RUN_ID=%RANDOM%-%RANDOM%-%RANDOM%"
set "BUILD_ROOT=build\rust-ui-%RUN_ID%"
set "DIST_ROOT=dist\rust-ui-%RUN_ID%"
if exist "%BUILD_ROOT%" (
    echo ERROR: Build output already exists: "%BUILD_ROOT%"
    goto :finish
)
if exist "%DIST_ROOT%" (
    echo ERROR: Release output already exists: "%DIST_ROOT%"
    goto :finish
)
mkdir "%BUILD_ROOT%"
if errorlevel 1 goto :finish
mkdir "%DIST_ROOT%"
if errorlevel 1 goto :finish

set "PYI_WORK=%BUILD_ROOT%\pyinstaller-work"
set "PYI_DIST=%BUILD_ROOT%\worker-dist"
set "PYI_SPEC=%BUILD_ROOT%\pyinstaller-spec"
set "CARGO_TARGET_DIR=%SHORTDRIVE%\%BUILD_ROOT%\cargo-target"
mkdir "%PYI_WORK%"
if errorlevel 1 goto :finish
mkdir "%PYI_DIST%"
if errorlevel 1 goto :finish
mkdir "%PYI_SPEC%"
if errorlevel 1 goto :finish

echo Checking Rust and Python app versions...
"%PYTHON%" scripts\check_app_versions.py
if errorlevel 1 goto :finish

echo Installing the project build dependencies...
"%PYTHON%" -m pip install --disable-pip-version-check -r requirements-dev.txt pyinstaller
if errorlevel 1 goto :finish

echo Running the Python and Rust regression suite...
"%PYTHON%" -m pytest tests/ -q
if errorlevel 1 goto :finish
cargo fmt --manifest-path rust-ui\Cargo.toml -- --check
if errorlevel 1 goto :finish
cargo test --manifest-path rust-ui\Cargo.toml --all-targets --features "test-worker desktop-smoke"
if errorlevel 1 goto :finish
cargo clippy --manifest-path rust-ui\Cargo.toml --all-targets --features "test-worker desktop-smoke" -- -D warnings
if errorlevel 1 goto :finish

echo Building the bundled Python worker...
"%PYTHON%" -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --console ^
    --name TrainsDownloaderWorker ^
    --distpath "%PYI_DIST%" ^
    --workpath "%PYI_WORK%" ^
    --specpath "%PYI_SPEC%" ^
    --collect-all PyQt5 ^
    --collect-all selenium ^
    --collect-all pypdf ^
    --hidden-import requests ^
    --hidden-import trains_app ^
    worker_main.py
if errorlevel 1 goto :finish

set "TRAINSDOWNLOADER_WORKER=%SHORTDRIVE%\%PYI_DIST%\TrainsDownloaderWorker.exe"
echo Verifying the packaged Python worker...
"%PYTHON%" scripts\smoke_test_worker.py
if errorlevel 1 goto :finish

echo Building the Rust desktop application...
cargo build --manifest-path rust-ui\Cargo.toml --release
if errorlevel 1 goto :finish

copy /b "%CARGO_TARGET_DIR%\release\trains-com-downloader.exe" "%DIST_ROOT%\TrainsDownloader-windows.exe" >nul
if errorlevel 1 goto :finish

echo Verifying the packaged desktop application opens and closes cleanly...
powershell.exe -NoProfile -File scripts\verify-rust-release.ps1 -ExecutablePath "%DIST_ROOT%\TrainsDownloader-windows.exe"
if errorlevel 1 goto :finish

set "EXIT_CODE=0"
echo.
echo ============================================================
echo  Build complete!
echo  Output: %PROJECT_ROOT%%DIST_ROOT%\TrainsDownloader-windows.exe
echo  The Python worker is bundled. Chrome is still required for downloads.
echo  Existing build and dist files were left in place.
echo ============================================================

:finish
if "%DRIVE_PUSHED%"=="1" popd
if "%SHORTDRIVE_MAPPED%"=="1" subst %SHORTDRIVE% /D >nul 2>nul
if "%ROOT_PUSHED%"=="1" popd
endlocal & exit /b %EXIT_CODE%
