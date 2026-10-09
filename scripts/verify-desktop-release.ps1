param([Parameter(Mandatory = $true)][string] $ExecutablePath)
$ErrorActionPreference = 'Stop'
$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
$dataRoot = Join-Path ([IO.Path]::GetTempPath()) ('trains-desktop-startup-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dataRoot | Out-Null
$process = Start-Process -FilePath $resolvedExecutable -ArgumentList @('--data-dir', ('"' + $dataRoot + '"')) -WorkingDirectory (Split-Path -Parent $resolvedExecutable) -WindowStyle Hidden -PassThru
try {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $process.Refresh()
        if ($process.HasExited) { throw "The desktop app exited during startup (code $($process.ExitCode))." }
        if ($process.MainWindowHandle -ne 0 -and $process.MainWindowTitle -eq 'Trains.com Archive') { break }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($process.MainWindowHandle -eq 0 -or $process.MainWindowTitle -ne 'Trains.com Archive') { throw 'The desktop app did not create its main window within 30 seconds.' }
    if (-not $process.CloseMainWindow()) { throw 'The desktop app did not accept a normal window-close request.' }
    if (-not $process.WaitForExit(15000)) { throw 'The desktop app did not exit after closing its window.' }
    if ($process.ExitCode -ne 0) { throw "The desktop app exited with code $($process.ExitCode)." }
    Write-Output "Packaged desktop app opened and exited cleanly. Isolated data: $dataRoot"
} finally {
    if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
    $process.Dispose()
}
