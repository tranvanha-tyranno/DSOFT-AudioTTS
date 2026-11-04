param(
    [ValidateSet('build','menuconfig','size','flash','monitor')]
    [string]$Action = 'build',
    [string]$Port = '',
    [string]$IdfPath = 'C:\Espressif\frameworks\esp-idf-v5.5.5'
)
# ESP-IDF activation writes informational messages to native stderr on Windows PowerShell.
# Check native exit codes explicitly instead of treating those messages as terminating errors.
$ErrorActionPreference = 'Continue'
if (-not (Test-Path -LiteralPath (Join-Path $IdfPath 'export.ps1'))) {
    throw "ESP-IDF not found at $IdfPath. Pass -IdfPath with your installation path."
}
if ($Action -in @('flash','monitor') -and -not $Port) {
    throw 'Specify -Port COMx for flash/monitor.'
}
$env:IDF_PATH = $IdfPath
. (Join-Path $IdfPath 'export.ps1')
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $idfArguments = @('-DIDF_TARGET=esp32s3', '-DSDKCONFIG=sdkconfig')
    if ($Port) { $idfArguments += @('-p', $Port) }
    $idfArguments += $Action
    & python (Join-Path $IdfPath 'tools\idf.py') @idfArguments
    if ($LASTEXITCODE -ne 0) { throw "idf.py failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
