[CmdletBinding()]
param(
    [switch]$PublishAfterSmokeTests
)

$ErrorActionPreference = "Stop"
$ExpectedVersion = "2.49.5"
$ExpectedExistingWorkflowCount = 31
$AgentFiles = @(
    "00-supervisor.json",
    "01-repository-auditor.json",
    "02-security-auditor.json",
    "03-rbac-reviewer.json",
    "04-database-backup-reviewer.json",
    "05-mikrotik-test-gate.json",
    "06-backend-health-monitor.json",
    "07-network-diagnosis-advisor.json",
    "08-payment-intake-guard.json",
    "09-financial-reconciliation.json",
    "10-human-approval-gate.json",
    "11-qa-smoke-test.json",
    "12-release-preflight.json"
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$WorkflowSource = Join-Path $RepoRoot "automation\n8n\workflows"
$Documents = [Environment]::GetFolderPath("MyDocuments")
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupRoot = Join-Path $Documents "SmartNet-n8n-backups\live-update-$Stamp"
$BackupWorkflows = Join-Path $BackupRoot "workflows"
$Staging = Join-Path $BackupRoot "staging"
$PostCheck = Join-Path $BackupRoot "postcheck"
$SmokeLogs = Join-Path $BackupRoot "smoke-tests"
$ReportDir = Join-Path $Documents "SmartNet-n8n-final-audit"
$ReportPath = Join-Path $ReportDir "SmartNet-n8n-live-update-$Stamp.json"
$CredentialTemp = Join-Path $env:TEMP ("smartnet-credential-metadata-" + [Guid]::NewGuid().ToString("N") + ".json")
$CredentialLog = Join-Path $env:TEMP ("smartnet-credential-export-" + [Guid]::NewGuid().ToString("N") + ".log")
$N8nCommand = (Get-Command n8n -ErrorAction Stop).Source

function Invoke-N8n {
    param([string[]]$Arguments)
    & $script:N8nCommand @Arguments
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        throw "n8n command failed (exit $code): $($Arguments -join ' ')"
    }
}

function Read-JsonFile {
    param([string]$Path)
    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function Write-JsonFile {
    param(
        [string]$Path,
        [object]$Value
    )
    $json = ConvertTo-Json -InputObject $Value -Depth 100
    $encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
    [System.IO.File]::WriteAllText($Path, $json, $encoding)
}

function Select-Credential {
    param(
        [object[]]$Candidates,
        [string]$Label,
        [switch]$ForceSelection
    )
    $list = @($Candidates)
    if ($list.Count -eq 0) {
        throw "No local $Label credential was found. Create it in n8n Credentials first; no workflows were updated."
    }
    if ($list.Count -eq 1 -and -not $ForceSelection) { return $list[0] }

    Write-Host ""
    Write-Host "Available $Label credentials (names and IDs only; secret values are never displayed):" -ForegroundColor Cyan
    for ($i = 0; $i -lt $list.Count; $i++) {
        Write-Host ("  [{0}] {1}  ({2})" -f ($i + 1), $list[$i].name, $list[$i].id)
    }
    $answer = Read-Host "Select the credential number to bind"
    $number = 0
    if (-not [int]::TryParse($answer, [ref]$number) -or $number -lt 1 -or $number -gt $list.Count) {
        throw "Invalid $Label credential selection. No workflows were updated."
    }
    return $list[$number - 1]
}

$Updated = @()
$SmokeResults = @()
$Published = @()
$Success = $false

try {
    Write-Host ""
    Write-Host "========== SmartNet n8n local update + smoke tests ==========" -ForegroundColor Cyan
    Write-Host "Repository: $RepoRoot"
    Write-Host "n8n executable: $N8nCommand"
    $VersionOutput = (& $N8nCommand --version | Out-String).Trim()
    Write-Host "n8n version: $VersionOutput"
    if ($VersionOutput -ne $ExpectedVersion) {
        throw "This bundle is validated for n8n $ExpectedVersion. Detected $VersionOutput. No workflows were updated."
    }

    foreach ($file in $AgentFiles) {
        $sourcePath = Join-Path $WorkflowSource $file
        if (-not (Test-Path -LiteralPath $sourcePath)) {
            throw "Missing source workflow: $sourcePath"
        }
        $source = Read-JsonFile $sourcePath
        if ($source.active -ne $false) {
            throw "$file must remain inactive in Git. No workflows were updated."
        }
        $nodes = @($source.nodes)
        if (@($nodes | Where-Object { $_.type -eq "@n8n/n8n-nodes-langchain.agent" }).Count -ne 1) {
            throw "$file does not contain exactly one AI Agent node."
        }
        if (@($nodes | Where-Object { $_.type -eq "@n8n/n8n-nodes-langchain.lmChatOpenAi" }).Count -ne 1) {
            throw "$file does not contain exactly one OpenAI Chat Model node."
        }
        $webhook = $nodes | Where-Object { $_.type -eq "n8n-nodes-base.webhook" } | Select-Object -First 1
        if (-not $webhook -or $webhook.parameters.authentication -ne "headerAuth") {
            throw "$file does not require Header Auth in the source bundle."
        }
    }

    New-Item -ItemType Directory -Force -Path $BackupWorkflows, $Staging, $PostCheck, $SmokeLogs, $ReportDir | Out-Null

    Write-Host ""
    Write-Host "[1/7] Backing up all existing workflow definitions..." -ForegroundColor Cyan
    Invoke-N8n @("export:workflow", "--all", "--separate", "--output=$BackupWorkflows")
    $BackupFiles = @(Get-ChildItem -LiteralPath $BackupWorkflows -Filter "*.json" -File)
    if ($BackupFiles.Count -ne $ExpectedExistingWorkflowCount) {
        throw "Expected $ExpectedExistingWorkflowCount local workflows from the latest audit, but exported $($BackupFiles.Count). This may be a different n8n database/account. No workflows were updated."
    }

    $LocalByName = @{}
    $HeaderRefs = @()
    foreach ($backupFile in $BackupFiles) {
        $local = Read-JsonFile $backupFile.FullName
        if ($local.name) {
            $LocalByName[[string]$local.name] = [pscustomobject]@{ workflow = $local; path = $backupFile.FullName }
        }
        foreach ($node in @($local.nodes)) {
            if ($node.type -eq "n8n-nodes-base.webhook" -and
                $node.parameters.authentication -eq "headerAuth" -and
                $node.credentials.httpHeaderAuth.id) {
                $HeaderRefs += [pscustomobject]@{
                    id = [string]$node.credentials.httpHeaderAuth.id
                    name = [string]$node.credentials.httpHeaderAuth.name
                }
            }
        }
    }

    Write-Host ""
    Write-Host "[2/7] Reading local credential metadata (encrypted export only)..." -ForegroundColor Cyan
    & $N8nCommand export:credentials --all "--output=$CredentialTemp" *> $CredentialLog
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $CredentialTemp)) {
        throw "Unable to inspect local credential metadata. No workflows were updated."
    }
    $credentialRoot = Read-JsonFile $CredentialTemp
    if ($credentialRoot -is [System.Array]) {
        $CredentialRecords = @($credentialRoot)
    } elseif ($credentialRoot.credentials) {
        $CredentialRecords = @($credentialRoot.credentials)
    } else {
        $CredentialRecords = @($credentialRoot)
    }

    $OpenAiCandidates = @($CredentialRecords | Where-Object { $_.type -eq "openAiApi" } | ForEach-Object {
        [pscustomobject]@{ id = [string]$_.id; name = [string]$_.name }
    })
    $OpenAiCredential = Select-Credential -Candidates $OpenAiCandidates -Label "OpenAI API"

    $HeaderCandidates = @($CredentialRecords | Where-Object {
        $_.type -eq "httpHeaderAuth" -and $_.name -eq "SmartNet Agents Header Auth"
    } | ForEach-Object {
        [pscustomobject]@{ id = [string]$_.id; name = [string]$_.name }
    })
    $HeaderCredential = Select-Credential -Candidates $HeaderCandidates -Label "dedicated SmartNet Agents Header Auth" -ForceSelection
    if (-not $OpenAiCredential.id -or -not $HeaderCredential.id) {
        throw "Local credential metadata is incomplete. No workflows were updated."
    }

    Write-Host "OpenAI credential selected: $($OpenAiCredential.name) (secret omitted)"
    Write-Host "Dedicated Webhook Header Auth selected: $($HeaderCredential.name) (secret omitted)"
    Write-Host "Credential secret values were not decrypted or displayed."

    Write-Host ""
    Write-Host "[3/7] Preparing 13 in-place workflow updates..." -ForegroundColor Cyan
    foreach ($file in $AgentFiles) {
        $sourcePath = Join-Path $WorkflowSource $file
        $source = Read-JsonFile $sourcePath
        $existingName = [string]$source.name
        if (-not $LocalByName.ContainsKey($existingName)) {
            throw "Could not find the already-imported local workflow '$existingName'. No updates were imported."
        }
        $localRecord = $LocalByName[$existingName]
        $local = $localRecord.workflow
        if ($local.active -eq $true) {
            throw "Workflow '$existingName' is currently active/published. This updater refuses to replace a published workflow."
        }

        $source.id = [string]$local.id
        $source.active = $false
        if ($local.settings) { $source.settings = $local.settings }
        if ($local.tags) { $source.tags = $local.tags }
        foreach ($propertyName in @("staticData", "pinData", "versionCounter", "createdAt", "updatedAt")) {
            if ($local.PSObject.Properties.Name -contains $propertyName) {
                $source | Add-Member -NotePropertyName $propertyName -NotePropertyValue $local.$propertyName -Force
            }
        }
        $mergedMeta = $local.meta
        if (-not $mergedMeta) { $mergedMeta = [pscustomobject]@{} }
        $mergedMeta | Add-Member -NotePropertyName "description" -NotePropertyValue $source.meta.description -Force
        $source.meta = $mergedMeta

        $webhookNode = $source.nodes | Where-Object { $_.type -eq "n8n-nodes-base.webhook" } | Select-Object -First 1
        $modelNode = $source.nodes | Where-Object { $_.type -eq "@n8n/n8n-nodes-langchain.lmChatOpenAi" } | Select-Object -First 1
        if (-not $webhookNode -or -not $modelNode) {
            throw "Missing Webhook or model node in $file."
        }
        $webhookNode | Add-Member -NotePropertyName "credentials" -NotePropertyValue ([pscustomobject]@{
            httpHeaderAuth = [pscustomobject]@{ id = $HeaderCredential.id; name = $HeaderCredential.name }
        }) -Force
        $modelNode | Add-Member -NotePropertyName "credentials" -NotePropertyValue ([pscustomobject]@{
            openAiApi = [pscustomobject]@{ id = $OpenAiCredential.id; name = $OpenAiCredential.name }
        }) -Force

        $stagedPath = Join-Path $Staging $file
        Write-JsonFile -Path $stagedPath -Value $source
    }

    Write-Host ""
    Write-Host "[4/7] Updating existing workflow IDs (no duplicates; all remain unpublished)..." -ForegroundColor Cyan
    foreach ($file in $AgentFiles) {
        $stagedPath = Join-Path $Staging $file
        $source = Read-JsonFile $stagedPath
        $originalPath = $LocalByName[[string]$source.name].path
        # Register the backup before import so rollback also covers a command that
        # reports failure after partially changing the current workflow record.
        $Updated += [pscustomobject]@{ name = $source.name; id = [string]$source.id; originalPath = $originalPath }
        Invoke-N8n @("import:workflow", "--input=$stagedPath")
    }

    Write-Host ""
    Write-Host "[5/7] Verifying imported node and credential bindings..." -ForegroundColor Cyan
    Invoke-N8n @("export:workflow", "--all", "--separate", "--output=$PostCheck")
    $PostFiles = @(Get-ChildItem -LiteralPath $PostCheck -Filter "*.json" -File)
    $PostByName = @{}
    foreach ($postFile in $PostFiles) {
        $wf = Read-JsonFile $postFile.FullName
        if ($wf.name) { $PostByName[[string]$wf.name] = $wf }
    }
    foreach ($file in $AgentFiles) {
        $source = Read-JsonFile (Join-Path $Staging $file)
        $post = $PostByName[[string]$source.name]
        if (-not $post) { throw "Post-import workflow missing: $($source.name)" }
        if ($post.active -eq $true) { throw "Safety check failed: $($source.name) is published." }
        $nodes = @($post.nodes)
        $agentNode = $nodes | Where-Object { $_.type -eq "@n8n/n8n-nodes-langchain.agent" } | Select-Object -First 1
        $modelNode = $nodes | Where-Object { $_.type -eq "@n8n/n8n-nodes-langchain.lmChatOpenAi" } | Select-Object -First 1
        $webhookNode = $nodes | Where-Object { $_.type -eq "n8n-nodes-base.webhook" } | Select-Object -First 1
        if (-not $agentNode -or -not $modelNode -or -not $webhookNode) { throw "Missing AI/Webhook node in $($source.name)." }
        if ($modelNode.credentials.openAiApi.id -ne $OpenAiCredential.id) { throw "OpenAI credential binding mismatch in $($source.name)." }
        if ($webhookNode.credentials.httpHeaderAuth.id -ne $HeaderCredential.id) { throw "Header Auth binding mismatch in $($source.name)." }
        $modelConnections = $post.connections[$modelNode.name].ai_languageModel
        $connected = $false
        foreach ($branch in $modelConnections) {
            foreach ($edge in $branch) {
                if ($edge.node -eq $agentNode.name) { $connected = $true }
            }
        }
        if (-not $connected) { throw "OpenAI Chat Model is not connected to AI Agent in $($source.name)." }
    }

    Write-Host ""
    Write-Host "[6/7] Executing 13 local read-only/model smoke tests..." -ForegroundColor Cyan
    foreach ($file in $AgentFiles) {
        $source = Read-JsonFile (Join-Path $Staging $file)
        $logPath = Join-Path $SmokeLogs ($file + ".log")
        $args = @("execute", "--id=$($source.id)", "--rawOutput")
        & $N8nCommand @args *> $logPath
        $exitCode = $LASTEXITCODE
        $markerFound = Select-String -LiteralPath $logPath -Pattern "SMARTNET_OPENAI_SMOKE_TEST_PASS" -SimpleMatch -Quiet
        $passed = ($exitCode -eq 0 -and $markerFound)
        $SmokeResults += [pscustomobject]@{
            workflow = $source.name
            workflow_id = [string]$source.id
            passed = $passed
            openai_response_marker_found = [bool]$markerFound
            exit_code = $exitCode
            log_file = $logPath
        }
        if ($passed) {
            Write-Host ("PASS  {0} (real OpenAI response marker found)" -f $source.name) -ForegroundColor Green
        } else {
            Write-Host ("FAIL  {0} (exit {1}, response marker {2})" -f $source.name, $exitCode, $markerFound) -ForegroundColor Red
        }
    }
    $allSmokePassed = (@($SmokeResults | Where-Object { -not $_.passed }).Count -eq 0)

    Write-Host ""
    Write-Host "[7/7] Publication decision..." -ForegroundColor Cyan
    if ($PublishAfterSmokeTests) {
        $httpsConfigured = (($env:WEBHOOK_URL -like "https://*") -or ($env:N8N_PROTOCOL -eq "https"))
        $localHost = $env:N8N_HOST
        $loopbackHost = ($localHost -in @("localhost", "127.0.0.1", "::1"))
        $localHttpApproved = ($env:SMARTNET_ALLOW_LOCAL_HTTP_PUBLISH -eq "YES") -and ($env:N8N_PROTOCOL -eq "http") -and $loopbackHost -and ($env:ENVIRONMENT -ne "production")
        $explicitPublishGate = ($env:SMARTNET_ALLOW_WEBHOOK_PUBLISH -eq "YES")
        if (-not $explicitPublishGate) {
            Write-Warning "Publication skipped: set SMARTNET_ALLOW_WEBHOOK_PUBLISH=YES only after manually verifying caller integration and the chosen secure local/private endpoint. Workflows remain unpublished."
        } elseif (-not ($httpsConfigured -or $localHttpApproved)) {
            Write-Warning "Publication skipped: use HTTPS, or explicitly allow HTTP only when N8N_HOST is localhost/127.0.0.1/::1, N8N_PROTOCOL=http, ENVIRONMENT is not production, and SMARTNET_ALLOW_LOCAL_HTTP_PUBLISH=YES."
        } elseif (-not $allSmokePassed) {
            Write-Warning "Publication skipped: one or more local smoke tests failed. Workflows remain unpublished."
        } else {
            try {
                foreach ($item in $Updated) {
                    Invoke-N8n @("publish:workflow", "--id=$($item.id)")
                    $Published += $item
                    Write-Host ("PUBLISHED  {0}" -f $item.name) -ForegroundColor Green
                }
            } catch {
                foreach ($item in $Published) {
                    & $N8nCommand unpublish:workflow "--id=$($item.id)" *> $null
                }
                throw "Publication failed. Any workflows published by this run were unpublished again. $($_.Exception.Message)"
            }
        }
    } else {
        Write-Host "Workflows remain unpublished. Use -PublishAfterSmokeTests only after verifying the local caller and Header Auth. Public endpoints require HTTPS; HTTP is allowed only with an explicit loopback-only development gate."
    }

    $Success = $true
    $Report = [pscustomobject]@{
        generated_at = (Get-Date).ToString("o")
        n8n_version = $VersionOutput
        workflow_count = 13
        workflows_updated_in_place = @($Updated | ForEach-Object { [pscustomobject]@{ name = $_.name; id = $_.id } })
        ai_agent_nodes = 13
        openai_chat_model_nodes = 13
        model_connections_verified = 13
        webhook_header_auth_bindings = 13
        credential_names = [pscustomobject]@{
            openai = $OpenAiCredential.name
            webhook_header_auth = $HeaderCredential.name
        }
        credential_secret_values_exported_or_displayed = $false
        smoke_tests = $SmokeResults
        all_smoke_tests_passed = $allSmokePassed
        published_count = $Published.Count
        publication_attempted_only_with_explicit_gate_https_or_loopback_dev_and_all_tests_passed = $true
        backup_directory = $BackupRoot
        smoke_log_directory = $SmokeLogs
        note = "Every smoke test must exit successfully and include SMARTNET_OPENAI_SMOKE_TEST_PASS, emitted only after non-empty OpenAI model output. AI Agent output is advisory only. Deterministic checks remain authoritative. No router, payment, ledger, customer account, or production database mutation tools are connected."
    }
    Write-JsonFile -Path $ReportPath -Value $Report

    Write-Host ""
    Write-Host "========== UPDATE RESULT ==========" -ForegroundColor Cyan
    Write-Host "Workflows updated: 13"
    Write-Host "AI Agent nodes: 13"
    Write-Host "OpenAI Chat Model nodes: 13"
    Write-Host "Header Auth bindings: 13"
    Write-Host "Smoke tests passed: $(@($SmokeResults | Where-Object { $_.passed }).Count)/13"
    Write-Host "Published: $($Published.Count)"
    Write-Host "Backup: $BackupRoot"
    Write-Host "Report: $ReportPath"
}
catch {
    Write-Error $_.Exception.Message
    if ($Updated.Count -gt 0) {
        Write-Warning "An update failed part-way through. Rolling back the workflows already updated from the local backup..."
        foreach ($item in $Updated) {
            try {
                Invoke-N8n @("import:workflow", "--input=$($item.originalPath)")
                Write-Host ("RESTORED  {0}" -f $item.name) -ForegroundColor Yellow
            } catch {
                Write-Warning "Rollback failed for $($item.name). Original backup remains at $BackupRoot."
            }
        }
    }
    throw
}
finally {
    if (Test-Path -LiteralPath $CredentialTemp) {
        Remove-Item -LiteralPath $CredentialTemp -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $CredentialLog) {
        Remove-Item -LiteralPath $CredentialLog -Force -ErrorAction SilentlyContinue
    }
}

if (-not $Success) {
    throw "SmartNet n8n updater did not complete."
}
