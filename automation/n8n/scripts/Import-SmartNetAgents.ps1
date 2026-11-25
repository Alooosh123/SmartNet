[CmdletBinding()]
param(
    [switch]$ConfirmImport
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-WithError([string]$Message) {
    Write-Error $Message
    exit 1
}

$command = Get-Command "n8n" -ErrorAction SilentlyContinue
if (-not $command) {
    Stop-WithError "n8n CLI was not found. Install/locate n8n, then reopen PowerShell."
}

$n8nPath = $command.Source
if ([string]::IsNullOrWhiteSpace($n8nPath)) {
    $n8nPath = $command.Name
}

$workflowDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\workflows"))
if (-not (Test-Path -LiteralPath $workflowDir -PathType Container)) {
    Stop-WithError "Workflow directory not found: $workflowDir"
}

$expected = @(
    "00-supervisor",
    "01-repository-auditor",
    "02-security-auditor",
    "03-rbac-reviewer",
    "04-database-backup-reviewer",
    "05-mikrotik-test-gate",
    "06-backend-health-monitor",
    "07-network-diagnosis-advisor",
    "08-payment-intake-guard",
    "09-financial-reconciliation",
    "10-human-approval-gate",
    "11-qa-smoke-test",
    "12-release-preflight"
)

$files = @(Get-ChildItem -LiteralPath $workflowDir -Filter "*.json" -File)
$actual = @($files | ForEach-Object { $_.BaseName })
$workflowNames = @()
$missing = @($expected | Where-Object { $_ -notin $actual })
$extra = @($actual | Where-Object { $_ -notin $expected })

if ($files.Count -ne 13 -or $missing.Count -gt 0 -or $extra.Count -gt 0) {
    Stop-WithError ("Workflow inventory is not the expected 13 files. Missing: {0}; Extra: {1}" -f ($missing -join ", "), ($extra -join ", "))
}

foreach ($file in $files) {
    try {
        $workflow = Get-Content -LiteralPath $file.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Stop-WithError "Invalid JSON in $($file.Name): $($_.Exception.Message)"
    }

    if ([string]::IsNullOrWhiteSpace([string]$workflow.name)) {
        Stop-WithError "$($file.Name) has no workflow name."
    }
    $workflowNames += [string]$workflow.name

    if ($workflow.active -ne $false) {
        Stop-WithError "$($file.Name) must have active=false before import."
    }

    $webhooks = @($workflow.nodes | Where-Object { $_.type -eq "n8n-nodes-base.webhook" })
    if ($webhooks.Count -ne 1) {
        Stop-WithError "$($file.Name) must contain exactly one Webhook Trigger."
    }
}

Write-Host ""
Write-Host "SmartNet n8n import preflight" -ForegroundColor Cyan
Write-Host "n8n executable: $n8nPath"
Write-Host "Workflow files: $($files.Count)"
Write-Host "Target: local n8n database used by the current Windows account"
Write-Host ""

& $n8nPath --version
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Could not read the installed n8n version."
}

$backupRoot = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "SmartNet-n8n-backups"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $backupRoot $stamp
$backupFile = $backupDir

New-Item -ItemType Directory -Path $backupDir -Force | Out-Null

Write-Host "Creating a backup of existing n8n workflows..."
& $n8nPath export:workflow --backup "--output=$backupFile"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupFile -PathType Container)) {
    Stop-WithError "Could not create a workflow backup. No import was attempted."
}

$existingNames = @()
$backupFiles = @(Get-ChildItem -LiteralPath $backupFile -Filter "*.json" -File -Recurse)
foreach ($backupWorkflowFile in $backupFiles) {
    try {
        $backupWorkflow = Get-Content -LiteralPath $backupWorkflowFile.FullName -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Stop-WithError "The workflow backup could not be parsed at $($backupWorkflowFile.FullName). No import was attempted."
    }
    if ($null -ne $backupWorkflow.name) {
        $existingNames += [string]$backupWorkflow.name
    }
}

$collisions = @($workflowNames | Where-Object { $_ -in $existingNames })
if ($collisions.Count -gt 0) {
    Stop-WithError ("SmartNet workflow names already exist in this n8n instance: {0}. Import stopped to prevent duplicate workflows. Review them in n8n before proceeding." -f ($collisions -join ", "))
}

Write-Host "Backup saved to: $backupFile" -ForegroundColor Green
Write-Host ""
Write-Warning "This imports all 13 workflows as INACTIVE / UNPUBLISHED. It does not connect an AI model, configure webhook authentication, or publish any workflow."
Write-Warning "The current workflow JSON files do not contain webhook authentication credentials. Do not publish them until authentication is configured on every Webhook Trigger."
Write-Warning "Run this script under the same Windows account and n8n environment that owns the target n8n database. A service running under another account may use a different n8n database."

if (-not $ConfirmImport) {
    $answer = Read-Host 'To continue, type exactly: IMPORT 13 SMARTNET AGENTS'
    if ($answer -cne "IMPORT 13 SMARTNET AGENTS") {
        Write-Host "Cancelled. No SmartNet workflows were imported."
        exit 0
    }
}

Write-Host ""
Write-Host "Importing 13 SmartNet workflows as inactive..."
& $n8nPath import:workflow --separate "--input=$workflowDir"
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "n8n import command failed. Existing workflows backup: $backupFile"
}

Write-Host ""
Write-Host "Import command completed." -ForegroundColor Green
Write-Host "All workflows are expected to remain inactive. Confirm their status in the n8n editor."
Write-Host "Backup directory: $backupFile"
Write-Host ""
Write-Host "Next: configure webhook authentication and test each read-only path before publishing anything."
