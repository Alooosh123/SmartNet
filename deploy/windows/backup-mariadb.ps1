[CmdletBinding()]
param(
    [string]$MariaDbBin = "C:\Program Files\MariaDB 11.8\bin",
    [string]$BackupDirectory = ".\backups"
)
$ErrorActionPreference = "Stop"
foreach ($name in @("MARIADB_DATABASE","MARIADB_USER","MARIADB_PASSWORD")) {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Set protected environment variable $name first." }
}
$hostName = if ($env:MARIADB_HOST) { $env:MARIADB_HOST } else { "127.0.0.1" }
$port = if ($env:MARIADB_PORT) { $env:MARIADB_PORT } else { "3306" }
New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$target = Join-Path $BackupDirectory "smartnet-$stamp.sql"
$defaults = Join-Path $env:TEMP ("smartnet-mariadb-" + [guid]::NewGuid().ToString("N") + ".cnf")
try {
    @("[client]","user=$env:MARIADB_USER","password=$env:MARIADB_PASSWORD","host=$hostName","port=$port","protocol=tcp","default-character-set=utf8mb4") | Set-Content -Encoding Ascii $defaults
    $acl = Get-Acl $defaults
    $acl.SetAccessRuleProtection($true,$false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME,"FullControl","Allow")
    $acl.SetAccessRule($rule)
    Set-Acl $defaults $acl
    & (Join-Path $MariaDbBin "mariadb-dump.exe") "--defaults-extra-file=$defaults" --single-transaction --quick --triggers --hex-blob --add-drop-table --result-file=$target $env:MARIADB_DATABASE
    if ($LASTEXITCODE -ne 0) { throw "mariadb-dump failed with exit code $LASTEXITCODE" }
    $hash = Get-FileHash -Algorithm SHA256 $target
    "$($hash.Hash)  $(Split-Path $target -Leaf)" | Set-Content -Encoding Ascii "$target.sha256"
    Write-Host "Backup created: $target" -ForegroundColor Green
}
finally {
    Remove-Item $defaults -Force -ErrorAction SilentlyContinue
}
