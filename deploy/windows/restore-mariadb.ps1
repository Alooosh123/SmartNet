[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Parameter(Mandatory=$true)][switch]$ConfirmRestore,
    [string]$MariaDbBin = "C:\Program Files\MariaDB 11.8\bin"
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmRestore) { throw "Pass -ConfirmRestore only after a verified backup and maintenance window." }
if (-not (Test-Path $BackupPath)) { throw "Backup file not found: $BackupPath" }
foreach ($name in @("MARIADB_DATABASE","MARIADB_RESTORE_USER","MARIADB_RESTORE_PASSWORD")) {
    if (-not [Environment]::GetEnvironmentVariable($name)) { throw "Set protected environment variable $name first." }
}
$hostName = if ($env:MARIADB_HOST) { $env:MARIADB_HOST } else { "127.0.0.1" }
$port = if ($env:MARIADB_PORT) { $env:MARIADB_PORT } else { "3306" }
$defaults = Join-Path $env:TEMP ("smartnet-mariadb-restore-" + [guid]::NewGuid().ToString("N") + ".cnf")
try {
    @("[client]","user=$env:MARIADB_RESTORE_USER","password=$env:MARIADB_RESTORE_PASSWORD","host=$hostName","port=$port","protocol=tcp","default-character-set=utf8mb4") | Set-Content -Encoding Ascii $defaults
    $acl = Get-Acl $defaults
    $acl.SetAccessRuleProtection($true,$false)
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME,"FullControl","Allow")
    $acl.SetAccessRule($rule)
    Set-Acl $defaults $acl
    if (Test-Path "$BackupPath.sha256") {
        $expected = ((Get-Content "$BackupPath.sha256" -Raw).Trim() -split '\s+')[0]
        $actual = (Get-FileHash -Algorithm SHA256 $BackupPath).Hash
        if ($actual -ne $expected) { throw "Backup SHA256 verification failed." }
    }
    $process = Start-Process -FilePath (Join-Path $MariaDbBin "mariadb.exe") -ArgumentList @("--defaults-extra-file=$defaults",$env:MARIADB_DATABASE) -RedirectStandardInput $BackupPath -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0) { throw "MariaDB restore failed with exit code $($process.ExitCode)" }
    Write-Host "Restore completed from: $BackupPath" -ForegroundColor Green
}
finally {
    Remove-Item $defaults -Force -ErrorAction SilentlyContinue
}
