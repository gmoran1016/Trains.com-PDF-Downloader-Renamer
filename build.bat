@echo off
setlocal

echo ============================================================
echo  Trains.com Magazine Downloader -- EXE Builder
echo ============================================================

:: Use the project venv
set PYTHON=.venv\Scripts\python.exe
set PIP=.venv\Scripts\pip.exe

:: Install / upgrade PyInstaller and all project dependencies inside the venv
echo Installing dependencies...
%PIP% install --quiet --upgrade pyinstaller
%PIP% install --quiet -r requirements.txt

:: Clean previous build artifacts
if exist build  rmdir /s /q build
if exist dist   rmdir /s /q dist

:: Build a single-folder distribution (faster startup than --onefile with PyQt5)
echo Building executable...
%PYTHON% -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "TrainsDownloader" ^
    --icon NONE ^
    --collect-all PyQt5 ^
    --collect-all selenium ^
    --hidden-import requests ^
    --hidden-import bs4 ^
    --collect-all pypdf ^
    trains_app.py

if errorlevel 1 (
    echo.
    echo BUILD FAILED -- see output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Output folder: dist\TrainsDownloader\
echo  Run:           dist\TrainsDownloader\TrainsDownloader.exe
echo.
echo  NOTE: Chrome must be installed on the target machine.
echo        The first run will auto-download the matching ChromeDriver.
echo ============================================================
pause
