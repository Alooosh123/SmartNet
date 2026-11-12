$ErrorActionPreference = "Stop"
$serviceDir = Join-Path $PSScriptRoot ""
$required = @(
    (Join-Path $serviceDir "smartnet-backend.exe"),
    (Join-Path $serviceDir "smartnet-backend.xml"),
    (Join-Path $serviceDir "smartnet-caddy.exe"),
    (Join-Path $serviceDir "caddy-service.xml")
)
foreach ($file in $required) {
    if (-not (Test-Path $file)) { throw "Missing service wrapper/config: $file" }
}
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not (Test-Path (Join-Path $projectRoot "backend\.env"))) {
    throw "Create and protect backend\.env before installing the services."
}
& (Join-Path $serviceDir "smartnet-backend.exe") install
if ($LASTEXITCODE -ne 0) { throw "Backend service install failed." }
& (Join-Path $serviceDir "smartnet-caddy.exe") install
if ($LASTEXITCODE -ne 0) { throw "Caddy service install failed." }
Write-Host "Services installed. Start MariaDB, then SmartNet Backend, then SmartNet HTTPS Gateway." -ForegroundColor Green
