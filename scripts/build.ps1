param(
    [ValidateSet('build','menuconfig','size','flash','monitor')]
    [string]$Action = 'build',
    [string]$Port = '',
    [string]$IdfPath = 'C:\Espressif\frameworks\esp-idf-v5.5.5',
    [ValidateRange(9600,2000000)]
    [int]$Baud = 115200,
    [ValidateSet('default_reset','usb_reset')]
    [string]$ResetMode = 'default_reset'
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
    if ($Action -eq 'flash') {
        # Build first, then explicitly control the reset mode for this upload.
        $idfArguments += 'build'
    } else {
        $idfArguments += $Action
    }
    & python (Join-Path $IdfPath 'tools\idf.py') @idfArguments
    if ($LASTEXITCODE -ne 0) { throw "idf.py failed with exit code $LASTEXITCODE" }
    if ($Action -eq 'flash') {
        # CH340/CP210x: DTR/RTS enter the ROM loader; RTS starts the app after upload.
        # usb_reset is available for the ESP32-S3 native USB Serial/JTAG port.
        Write-Host "Auto flash: port=$Port baud=$Baud before=$ResetMode after=hard_reset"
        Push-Location (Join-Path (Split-Path $PSScriptRoot -Parent) 'build')
        try {
            & python -m esptool --chip esp32s3 --port $Port --baud $Baud --before $ResetMode --after hard_reset write_flash '@flash_args'
            if ($LASTEXITCODE -ne 0) {
                throw "Auto flash failed (esptool exit $LASTEXITCODE). Check the serial port, USB-UART auto-reset circuit (DTR/RTS to GPIO0/EN), and board power."
            }
        } finally {
            Pop-Location
        }
    }
} finally {
    Pop-Location
}
