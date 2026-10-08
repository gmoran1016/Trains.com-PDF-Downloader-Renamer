param(
    [Parameter(Mandatory = $true)]
    [string] $ExecutablePath
)

$resolvedExecutable = (Resolve-Path -LiteralPath $ExecutablePath).Path
$workingDirectory = Split-Path -Parent $resolvedExecutable
$process = Start-Process -FilePath $resolvedExecutable -WorkingDirectory $workingDirectory -PassThru

try {
    $deadline = [DateTime]::UtcNow.AddSeconds(30)
    do {
        $process.Refresh()
        if ($process.HasExited) {
            throw "The desktop application exited during startup (code $($process.ExitCode))."
        }
        if ($process.MainWindowHandle -ne 0 -and $process.MainWindowTitle -eq 'Trains.com Archive') {
            break
        }
        Start-Sleep -Milliseconds 200
    } while ([DateTime]::UtcNow -lt $deadline)

    $process.Refresh()
    if ($process.MainWindowHandle -eq 0 -or $process.MainWindowTitle -ne 'Trains.com Archive') {
        throw 'The desktop application did not create its main window within 30 seconds.'
    }
    if (-not $process.CloseMainWindow()) {
        throw 'The desktop application did not accept a normal window-close request.'
    }
    if (-not $process.WaitForExit(15000)) {
        throw 'The desktop application did not exit after its window-close request.'
    }
    if ($process.ExitCode -ne 0) {
        throw "The desktop application exited with code $($process.ExitCode)."
    }
    Write-Output 'Packaged desktop application opened and exited cleanly.'
}
finally {
    if (-not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit()
    }
    $process.Dispose()
}
