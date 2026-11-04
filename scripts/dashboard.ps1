param([int]$Port = 8088, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$localPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pythonCommand = if (Test-Path -LiteralPath $localPython) { $localPython } else { 'python' }
Push-Location $projectRoot
try {
    $dashboardArguments = @('-m', 'backend.demo', '--port', "$Port")
    if ($NoBrowser) { $dashboardArguments += '--no-browser' }
    & $pythonCommand @dashboardArguments
    if ($LASTEXITCODE -ne 0) { throw "Dashboard stopped with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
