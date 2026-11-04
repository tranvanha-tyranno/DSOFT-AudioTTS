# Mở dashboard Docker trên trình duyệt, không in khóa operator ra log.
$ErrorActionPreference = 'Continue'
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $rawAccess = & docker compose exec -T backend python -m backend.access --json
    if ($LASTEXITCODE -ne 0) { throw 'Backend is not ready. Run docker compose up -d --build first.' }
    $access = ($rawAccess -join "`n") | ConvertFrom-Json
    $publishedPort = & docker compose port backend 8088
    if ($LASTEXITCODE -ne 0) { throw 'Cannot determine the published Docker port.' }
    $portMatch = [regex]::Match(($publishedPort | Select-Object -First 1), ':(\d+)$')
    if (-not $portMatch.Success) { throw 'Docker did not return a valid published port.' }
    $localUrl = 'http://127.0.0.1:' + $portMatch.Groups[1].Value + '/'
    $loginUrl = $localUrl + '#key=' + [uri]::EscapeDataString($access.operator_key)
    Start-Process -FilePath $loginUrl
    Write-Output ('Dashboard: ' + $localUrl)
} finally {
    Pop-Location
}
