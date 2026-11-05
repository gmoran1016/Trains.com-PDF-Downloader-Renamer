param([string] $PythonPath, [switch] $SkipChecks)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $PythonPath) { $PythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe' }
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path
if (Test-Path -LiteralPath "$env:USERPROFILE/.cargo/bin/cargo.exe") { $env:PATH = "$env:USERPROFILE/.cargo/bin;" + $env:PATH }
if (Test-Path -LiteralPath 'C:/Program Files/nodejs/npm.cmd') { $env:PATH = 'C:/Program Files/nodejs;' + $env:PATH }
$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$cargo = (Get-Command cargo.exe -ErrorAction Stop).Source
$originalTarget = $env:CARGO_TARGET_DIR
$originalWorker = $env:TRAINSDOWNLOADER_WORKER
$drive = $null
$pushed = $false
function Run-Step([string] $Program, [string[]] $Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE." }
}
try {
    # A short checkout path avoids MSVC's resource-compiler path limit. Existing
    # build and distribution folders are preserved; artifacts get a fresh folder.
    foreach ($letter in 'R','S','T','U','V','W','X','Z','Q','P') {
        $candidate = $letter + ':'
        if (-not (Test-Path -LiteralPath ($candidate + '\'))) {
            Run-Step 'subst.exe' @($candidate, $projectRoot)
            $drive = $candidate
            break
        }
    }
    if (-not $drive) { throw 'No unused drive letter is available for the short build path.' }
    Push-Location ($drive + '\'); $pushed = $true
    $runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8)
    $buildRoot = Join-Path (Get-Location) ('build/desktop-' + $runId)
    $distRoot = Join-Path (Get-Location) ('dist/desktop-' + $runId)
    New-Item -ItemType Directory -Path $buildRoot, $distRoot | Out-Null
    if (-not $env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR = Join-Path (Get-Location) 'build/cargo-target' }
    $env:CARGO_TARGET_DIR = [IO.Path]::GetFullPath($env:CARGO_TARGET_DIR)
    Run-Step $PythonPath @('scripts/check_app_versions.py')
    Run-Step $npm @('--prefix','desktop-ui','ci')
    if (-not $SkipChecks) {
        Run-Step $PythonPath @('-m','pytest','tests/','-q')
        Run-Step $cargo @('fmt','--manifest-path','rust-ui/Cargo.toml','--','--check')
        Run-Step $cargo @('test','--manifest-path','rust-ui/Cargo.toml','--all-targets','--features','test-worker desktop-smoke')
        Run-Step $cargo @('clippy','--manifest-path','rust-ui/Cargo.toml','--all-targets','--features','test-worker desktop-smoke','--','-D','warnings')
        Run-Step $cargo @('fmt','--manifest-path','desktop-ui/src-tauri/Cargo.toml','--','--check')
        Run-Step $npm @('--prefix','desktop-ui','test')
        Run-Step $cargo @('test','--manifest-path','desktop-ui/src-tauri/Cargo.toml')
        Run-Step $cargo @('clippy','--manifest-path','desktop-ui/src-tauri/Cargo.toml','--all-targets','--features','ui-qa','--','-D','warnings')
    }
    Write-Host 'Building the bundled Python worker...'
    Run-Step $PythonPath @('-m','PyInstaller','--noconfirm','--onefile','--console','--name','TrainsDownloaderWorker','--distpath',(Join-Path $buildRoot 'worker-dist'),'--workpath',(Join-Path $buildRoot 'worker-work'),'--specpath',(Join-Path $buildRoot 'worker-spec'),'--collect-all','PyQt5','--collect-all','selenium','--collect-all','pypdf','--hidden-import','requests','--hidden-import','trains_app','worker_main.py')
    $env:TRAINSDOWNLOADER_WORKER = Join-Path $buildRoot 'worker-dist/TrainsDownloaderWorker.exe'
    Run-Step $PythonPath @('scripts/smoke_test_worker.py')
    Push-Location desktop-ui
    try { Run-Step $npm @('run','tauri','--','build','--bundles','nsis') } finally { Pop-Location }
    Copy-Item -LiteralPath (Join-Path $env:CARGO_TARGET_DIR 'release/trains-desktop.exe') -Destination (Join-Path $distRoot 'TrainsDownloader-windows.exe')
    $appVersion = (Get-Content -LiteralPath (Join-Path $projectRoot 'desktop-ui/package.json') -Raw | ConvertFrom-Json).version
    $installerPattern = '*_' + $appVersion + '_x64-setup.exe'
    $installers = @(Get-ChildItem -LiteralPath (Join-Path $env:CARGO_TARGET_DIR 'release/bundle/nsis') -Filter $installerPattern -File)
    if ($installers.Count -ne 1) { throw "Expected one Windows installer for version $appVersion." }
    Copy-Item -LiteralPath $installers[0].FullName -Destination (Join-Path $distRoot 'TrainsDownloader-windows-setup.exe')
    & (Join-Path $projectRoot 'scripts/verify-desktop-release.ps1') -ExecutablePath (Join-Path $distRoot 'TrainsDownloader-windows.exe')
    Write-Host ('Build complete: ' + (Join-Path $projectRoot ('dist/desktop-' + $runId)))
} finally {
    if ($pushed) { Pop-Location }
    if ($drive) { & subst.exe $drive /D }
    $env:CARGO_TARGET_DIR = $originalTarget
    $env:TRAINSDOWNLOADER_WORKER = $originalWorker
}
