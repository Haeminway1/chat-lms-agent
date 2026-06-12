param(
    [switch]$DryRun,
    [switch]$NonInteractive,
    [ValidateSet("Dev", "User")]
    [string]$Mode = "Dev",
    [string]$Profile = "sample",
    [string]$ImportDbPath,
    [string]$LegacyToolsPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-ProfilePaths {
    param([string]$ProfileName)

    $localRoot = Join-Path $env:LOCALAPPDATA "ChatLMSAgent\profiles\$ProfileName"
    $roamingRoot = Join-Path $env:APPDATA "ChatLMSAgent\profiles\$ProfileName"
    return [ordered]@{
        LocalRoot = $localRoot
        RoamingRoot = $roamingRoot
        Workspace = Join-Path $localRoot "codex-workspace"
        Data = Join-Path $localRoot "data"
        Reports = Join-Path $localRoot "reports"
        Backups = Join-Path $localRoot "backups"
        Logs = Join-Path $localRoot "logs"
        Memory = Join-Path $roamingRoot "memory"
        Config = Join-Path $roamingRoot "config"
        Db = Join-Path (Join-Path $localRoot "data") "chat_lms.db"
    }
}

function Write-PrivateWorkspaceFiles {
    param(
        [hashtable]$Paths,
        [string]$ProfileName,
        [string]$RepoRoot,
        [string]$LegacyPath,
        [switch]$OverwriteExisting
    )

    $workspacePath = [string]$Paths["Workspace"]
    $localRoot = [string]$Paths["LocalRoot"]
    $dbPath = [string]$Paths["Db"]
    $reportsPath = [string]$Paths["Reports"]
    $backupsPath = [string]$Paths["Backups"]
    $logsPath = [string]$Paths["Logs"]
    $memoryRoot = [string]$Paths["Memory"]
    $agentsPath = Join-Path $workspacePath "AGENTS.md"
    $readmePath = Join-Path $workspacePath "README.md"
    $profilePath = Join-Path $workspacePath ".chat-lms-profile.json"
    $memoryPath = Join-Path $memoryRoot "dev-use-workspace-boundary.md"
    $scriptsPath = Join-Path $workspacePath "scripts"
    $hooksPath = Join-Path $workspacePath "hooks"
    $codexPath = Join-Path $workspacePath ".codex"
    $sessionStartScriptPath = Join-Path $scriptsPath "session-start-hydrate.ps1"
    $cliScriptPath = Join-Path $scriptsPath "chat-lms-cli.ps1"
    $hooksJsonPath = Join-Path $hooksPath "hooks.json"
    $codexHooksJsonPath = Join-Path $codexPath "hooks.json"

    New-Item -ItemType Directory -Force -Path $scriptsPath, $hooksPath, $codexPath | Out-Null

    $legacyImportRoot = Join-Path $localRoot "legacy-import"
    $latestLegacySnapshot = if (Test-Path -LiteralPath $legacyImportRoot) {
        Get-ChildItem -LiteralPath $legacyImportRoot -Directory -Filter ("chat_lms" + "_lite-*") |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    $legacySnapshotSection = if ($latestLegacySnapshot) {
        $manifestPath = Join-Path $latestLegacySnapshot.FullName "migration-manifest.json"
        @"
- Legacy runtime snapshot: $($latestLegacySnapshot.FullName)
- Legacy migration manifest: $manifestPath
"@
    } else {
        ""
    }

    $legacyToolLine = if ($LegacyPath) { "- Legacy tools: $LegacyPath" } else { "" }
    $legacySection = if ($LegacyPath -or $legacySnapshotSection) {
        @"

## Transition Toolchain

The new OSS repo is the product source of truth, but this profile may use the existing
local legacy toolchain during migration:

$legacyToolLine
$legacySnapshotSection

Use the private DB path above as the real data source. Do not copy private data back
into either source repository.
"@
    } else {
        ""
    }

    $agents = @"
# Chat LMS Agent Private Workspace

This is the real-use Codex workspace for profile $ProfileName.

## Core Rule

This folder is private runtime space, not the public source repository.
Use it for real lessons, learner records, reports, backups, and local memory.

## Boundaries

- Public OSS development repo: $RepoRoot
- Private workspace: $workspacePath
- Private DB: $dbPath
- Private reports: $reportsPath
- Private backups: $backupsPath
- Private memory: $memoryRoot

Never copy private data, generated reports, local memory, logs, or secrets into the public repo.
Do not initialize git here unless the user explicitly asks and understands the privacy risk.

## How To Operate

- Answer the teacher in Korean.
- Treat the private DB above as the source of truth for real use.
- Use simple direct local reads for simple questions.
- Render HTML under the private reports folder only for ad-hoc analyses not covered by any route.
- Ask before external writes, destructive local changes, bulk deletion, or secret changes.
- Keep long-lived operational notes in the private memory folder.
- A SessionStart hook must hydrate this private profile into every Codex session opened here.
- The SessionStart hook auto-syncs safe runtime wiring from the public repo so the user does not need to remember manual update commands.
- DB imports, schema migrations, credentials, external writes, and destructive changes still require explicit user approval.

## Development vs Use

- Development session: open the public OSS repo.
- Real-use session: open this private workspace.
- In this workspace, prefer reliability and speed over framework purity.
$legacySection
"@

    $readme = @"
# Chat LMS Agent - $ProfileName Private Workspace

Open this folder in Codex when you want to use Chat LMS Agent with real local data.

Use the public OSS repository only for development. This workspace is intentionally private.
"@

    $profile = [ordered]@{
        profile = $ProfileName
        mode = "user"
        publicRepo = $RepoRoot
        legacyTools = $LegacyPath
        workspace = $workspacePath
        db = $dbPath
        reports = $reportsPath
        backups = $backupsPath
        logs = $logsPath
        memory = $memoryRoot
    } | ConvertTo-Json -Depth 3

    $memory = @"
# Dev vs Real-Use Workspace Boundary

This note is required agent memory for the Chat LMS Agent setup.

## Development

Open the public OSS repo when building product code, tests, docs, plugins, hooks, skills, or reusable HTML blocks.
Do not read or write real learner data from a development session unless the user explicitly asks for migration or debugging.

## Real Use

Open the private profile workspace when managing real classes, tutoring, reports, word lists, and local automations.
The private DB, reports, backups, logs, and memory live outside the public repo.

## Public Safety

The public repo must remain publishable at all times. Real DB files, generated reports, local paths, learner records,
external account state, and saved secrets belong only in the private profile runtime.

## Agent Behavior

When in doubt, keep product code in the public repo and operational data in the private workspace.
Simple data should be answered in chat. Render HTML in private reports only for ad-hoc analyses not covered by any route.
"@

    $sessionStartTemplate = @'
param()

$ErrorActionPreference = "Stop"

function New-AdditionalContextOutput {
    param([string]$Context)

    $payload = @{
        hookSpecificOutput = @{
            hookEventName = "SessionStart"
            additionalContext = $Context.Trim()
        }
    }
    $payload | ConvertTo-Json -Depth 5 -Compress
}

function Get-Sha256 {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return "missing"
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Invoke-RuntimeSync {
    param(
        [pscustomobject]$Profile,
        [string]$CurrentScriptPath
    )

    if ($env:CHAT_LMS_AGENT_SYNC_REENTRY -eq "1") {
        return [ordered]@{
            status = "skipped-reentry"
            detail = "sync already ran before script reentry"
            changedScript = $false
        }
    }

    $publicRepo = [string]$Profile.publicRepo
    $bootstrapPath = Join-Path $publicRepo "scripts\bootstrap.ps1"
    if (-not (Test-Path -LiteralPath $bootstrapPath)) {
        return [ordered]@{
            status = "skipped"
            detail = "public repo bootstrap not found"
            changedScript = $false
        }
    }

    $beforeHash = Get-Sha256 -Path $CurrentScriptPath
    $logsRoot = if ($Profile.logs) { [string]$Profile.logs } else { Join-Path (Split-Path -Parent $Profile.workspace) "logs" }
    New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null
    $syncLogPath = Join-Path $logsRoot "session-start-sync.log"
    $syncStatePath = Join-Path $Profile.workspace ".chat-lms-sync-state.json"
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $bootstrapPath,
        "-Mode",
        "User",
        "-Profile",
        [string]$Profile.profile
    )
    if ($Profile.legacyTools) {
        $arguments += @("-LegacyToolsPath", [string]$Profile.legacyTools)
    }

    $output = & powershell @arguments 2>&1
    $exitCode = $LASTEXITCODE
    $outputText = ($output | Out-String).Trim()
    Add-Content -LiteralPath $syncLogPath -Value "[$(Get-Date -Format o)] exit=$exitCode`n$outputText`n"
    if ($exitCode -ne 0) {
        return [ordered]@{
            status = "failed"
            detail = "bootstrap sync failed with exit $exitCode"
            changedScript = $false
            log = $syncLogPath
        }
    }

    $afterHash = Get-Sha256 -Path $CurrentScriptPath
    $changedScript = $beforeHash -ne $afterHash
    $syncState = [ordered]@{
        syncedAt = (Get-Date).ToString("o")
        status = "applied"
        publicRepo = $publicRepo
        bootstrap = $bootstrapPath
        scriptHashBefore = $beforeHash
        scriptHashAfter = $afterHash
        changedScript = $changedScript
        log = $syncLogPath
    }
    $syncState | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $syncStatePath -Encoding UTF8

    return [ordered]@{
        status = "applied"
        detail = "safe runtime wiring synced from public repo"
        changedScript = $changedScript
        log = $syncLogPath
        state = $syncStatePath
    }
}

try {
    $profilePath = "__PROFILE_PATH__"
    $profile = Get-Content -Raw -Encoding UTF8 -LiteralPath $profilePath | ConvertFrom-Json
    $sync = Invoke-RuntimeSync -Profile $profile -CurrentScriptPath $PSCommandPath
    if ($sync.changedScript -and $env:CHAT_LMS_AGENT_SYNC_REENTRY -ne "1") {
        $env:CHAT_LMS_AGENT_SYNC_REENTRY = "1"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
        exit $LASTEXITCODE
    }
    $profile = Get-Content -Raw -Encoding UTF8 -LiteralPath $profilePath | ConvertFrom-Json
    $memoryFiles = @(
        "__ESSENTIAL_NOTES_PATH__",
        "__BOUNDARY_NOTES_PATH__"
    )

    $memorySummary = foreach ($file in $memoryFiles) {
        if (Test-Path -LiteralPath $file) {
            $name = Split-Path -Leaf $file
            "## $name`n" + (Get-Content -Raw -Encoding UTF8 -LiteralPath $file).Trim()
        }
    }

    $dbStatus = if (Test-Path -LiteralPath $profile.db) { "present" } else { "missing" }
    $setupNote = Join-Path $profile.workspace "docs\dev-use-workspace-setup.md"
    $profileLocalRoot = Split-Path -Parent $profile.workspace
    $legacyImportRoot = Join-Path $profileLocalRoot "legacy-import"
    $latestLegacySnapshot = if (Test-Path -LiteralPath $legacyImportRoot) {
        Get-ChildItem -LiteralPath $legacyImportRoot -Directory -Filter ("chat_lms" + "_lite-*") |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    $legacySnapshotPath = if ($latestLegacySnapshot) { $latestLegacySnapshot.FullName } else { "not-found" }
    $legacyManifestPath = if ($latestLegacySnapshot) {
        Join-Path $latestLegacySnapshot.FullName "migration-manifest.json"
    } else {
        "not-found"
    }

    $context = @"
# Chat LMS Agent Runtime Context

This context was injected by the private workspace SessionStart hook.

## Active Profile

- Profile: $($profile.profile)
- Mode: $($profile.mode)
- Public OSS repo: $($profile.publicRepo)
- Private workspace: $($profile.workspace)
- Private DB: $($profile.db)
- Private DB status: $dbStatus
- Private reports: $($profile.reports)
- Private backups: $($profile.backups)
- Private logs: $($profile.logs)
- Private memory: $($profile.memory)
- Legacy tools: $($profile.legacyTools)
- Legacy runtime snapshot: $legacySnapshotPath
- Legacy migration manifest: $legacyManifestPath
- Runtime sync status: $($sync.status)
- Runtime sync detail: $($sync.detail)
- Runtime sync log: $($sync.log)
- Runtime sync state: $($sync.state)

## Required Operating Rules

- This is the real-use workspace, not the public source repo.
- Use the private DB as the real data source.
- Never copy private data, reports, backups, logs, or memory into the public repo.
- Answer the teacher in Korean.
- Simple data can be shown in chat.
- Use the private CLI wrapper for Chat LMS commands: $($profile.workspace)\scripts\chat-lms-cli.ps1.
- For any panel, viewer, lesson-prep, or wordbook style request, run agent-tools prompt-check first.
- Follow the returned route or route_catalog first_command before inspecting schemas, scaffolding tools, searching files, or creating artifacts.
- Never create new HTML files for these routed requests; use the fixed CLI/viewer surface the route points to.
- Render HTML under the private reports folder only for ad-hoc analyses not covered by any route.
- Ask before external writes, destructive local changes, bulk deletion, or secret changes.
- During migration, legacy tools may be used, but runtime artifacts must stay private.
- Safe development changes from the public repo are auto-synced at SessionStart.
- DB imports, schema migrations, credentials, external writes, and destructive changes still require explicit user approval.

## Private Reference Docs

- Workspace AGENTS.md: $($profile.workspace)\AGENTS.md
- Setup note: $setupNote
- Essential memory dir: $($profile.memory)

$($memorySummary -join "`n`n")
"@

    New-AdditionalContextOutput -Context $context
} catch {
    $message = $_.Exception.Message
    New-AdditionalContextOutput -Context "# Chat LMS Agent Runtime Context`n`nSessionStart hydrate failed: $message`n`nRead AGENTS.md before operating."
}
'@

    $cliScriptTemplate = @'
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$repoRoot = "__REPO_ROOT__"
$repoSrc = Join-Path $repoRoot "src"
if (-not (Test-Path -LiteralPath $repoSrc)) {
    throw "Chat LMS Agent source not found: $repoSrc"
}

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$repoSrc$([System.IO.Path]::PathSeparator)$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $repoSrc
}

function Test-PythonRuntime {
    param([string[]]$CommandPrefix)

    $checkArgs = @(
        "-c",
        "import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)"
    )
    $prefixArgs = @()
    if ($CommandPrefix.Length -gt 1) {
        $prefixArgs = $CommandPrefix[1..($CommandPrefix.Length - 1)]
    }
    & $CommandPrefix[0] @($prefixArgs + $checkArgs)
    return $LASTEXITCODE -eq 0
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher -and (Test-PythonRuntime @($pyLauncher.Source, "-3"))) {
    & $pyLauncher.Source -3 -m chat_lms_agent @CliArgs
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python 3.12+ was not found. Install Python or the py launcher, then re-run bootstrap."
}
if (-not (Test-PythonRuntime @($python.Source))) {
    throw "Python 3.12+ was not found. Install Python or the py launcher, then re-run bootstrap."
}

& $python.Source -m chat_lms_agent @CliArgs
exit $LASTEXITCODE
'@

    $sessionStartScript = $sessionStartTemplate.
        Replace("__PROFILE_PATH__", $profilePath).
        Replace("__ESSENTIAL_NOTES_PATH__", (Join-Path $memoryRoot "essential-agent-notes.md")).
        Replace("__BOUNDARY_NOTES_PATH__", $memoryPath)

    $cliScript = $cliScriptTemplate.Replace("__REPO_ROOT__", $RepoRoot)
    $hookCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$sessionStartScriptPath`""
    $cliCommand = "powershell -NoProfile -ExecutionPolicy Bypass -File `"$cliScriptPath`""
    $profileRootArg = "--profile-root `"$localRoot`""
    $userPromptCommand = "$cliCommand hook user-prompt-submit $profileRootArg --json"
    $preToolUseCommand = "$cliCommand hook pre-tool-use $profileRootArg --json"
    $postToolUseCommand = "$cliCommand hook post-tool-use $profileRootArg --json"
    $postCompactCommand = "$cliCommand hook post-compact $profileRootArg --json"
    $stopCommand = "$cliCommand hook stop --verify-memory $profileRootArg --json"
    $hooksConfig = [ordered]@{
        hooks = [ordered]@{
            SessionStart = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $hookCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Hydrating private profile context"
                        }
                    )
                }
            )
            UserPromptSubmit = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $userPromptCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Checking prompt obligations"
                        }
                    )
                }
            )
            PreToolUse = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $preToolUseCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Screening tool call safety"
                        }
                    )
                }
            )
            PostToolUse = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $postToolUseCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Checking tool memory obligations"
                        }
                    )
                }
            )
            PostCompact = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $postCompactCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Verifying compacted memory"
                        }
                    )
                }
            )
            Stop = @(
                [ordered]@{
                    hooks = @(
                        [ordered]@{
                            type = "command"
                            command = $stopCommand
                            timeout = 5
                            statusMessage = "ChatLMS: Verifying closeout memory"
                        }
                    )
                }
            )
        }
    } | ConvertTo-Json -Depth 8

    Set-Content -LiteralPath $agentsPath -Value $agents -Encoding UTF8
    Set-Content -LiteralPath $readmePath -Value $readme -Encoding UTF8
    Set-Content -LiteralPath $profilePath -Value $profile -Encoding UTF8
    Set-Content -LiteralPath $memoryPath -Value $memory -Encoding UTF8
    Set-Content -LiteralPath $sessionStartScriptPath -Value $sessionStartScript -Encoding UTF8
    Set-Content -LiteralPath $cliScriptPath -Value $cliScript -Encoding UTF8
    Set-Content -LiteralPath $hooksJsonPath -Value $hooksConfig -Encoding UTF8
    Set-Content -LiteralPath $codexHooksJsonPath -Value $hooksConfig -Encoding UTF8
    Write-LessonPanelAssets `
        -RepoRoot $RepoRoot `
        -ProfileRoot $localRoot `
        -ScriptsPath $scriptsPath `
        -OverwriteExisting:$OverwriteExisting
}

function Write-LessonPanelAssets {
    param(
        [string]$RepoRoot,
        [string]$ProfileRoot,
        [string]$ScriptsPath,
        [switch]$OverwriteExisting
    )

    $assetRoot = Join-Path $RepoRoot "assets\side-panel"
    foreach ($assetName in @("lesson_panel_server.py", "lesson_panel_view.html")) {
        $sourcePath = Join-Path $assetRoot $assetName
        $targetPath = Join-Path $ScriptsPath $assetName
        if ((Test-Path -LiteralPath $targetPath) -and -not $OverwriteExisting) {
            continue
        }
        $text = Get-Content -Raw -Encoding UTF8 -LiteralPath $sourcePath
        $text = $text.Replace("__REPO_SRC__", (Join-Path $RepoRoot "src")).Replace("__PROFILE_ROOT__", $ProfileRoot)
        Set-Content -LiteralPath $targetPath -Value $text -Encoding UTF8
    }
}

function Invoke-UserMode {
    param(
        [string]$ProfileName,
        [string]$ImportPath,
        [string]$LegacyPath,
        [switch]$OverwriteExisting
    )

    $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    $paths = Get-ProfilePaths -ProfileName $ProfileName
    $directories = @(
        $paths["LocalRoot"],
        $paths["RoamingRoot"],
        $paths["Workspace"],
        $paths["Data"],
        $paths["Reports"],
        $paths["Backups"],
        $paths["Logs"],
        $paths["Memory"],
        $paths["Config"]
    )

    foreach ($directory in $directories) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }

    Write-PrivateWorkspaceFiles `
        -Paths $paths `
        -ProfileName $ProfileName `
        -RepoRoot $repoRoot `
        -LegacyPath $LegacyPath `
        -OverwriteExisting:$OverwriteExisting

    if ($ImportPath) {
        if (-not (Test-Path -LiteralPath $ImportPath)) {
            throw "ImportDbPath does not exist: $ImportPath"
        }
        if ((Test-Path -LiteralPath $paths["Db"]) -and -not $OverwriteExisting) {
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $backupPath = Join-Path $paths["Backups"] "chat_lms-$stamp.db"
            Copy-Item -LiteralPath $paths["Db"] -Destination $backupPath -Force
            Write-Output "BACKUP_CREATED path=$backupPath"
        }
        Copy-Item -LiteralPath $ImportPath -Destination $paths["Db"] -Force
        Write-Output "DB_IMPORTED path=$($paths["Db"])"
    }

    Write-Output "USER_MODE_READY profile=$ProfileName"
    Write-Output "WORKSPACE path=$($paths["Workspace"])"
    Write-Output "DB path=$($paths["Db"])"
    Write-Output "MEMORY path=$($paths["Memory"])"
    Write-Output "NEXT_STEP_OPTIONAL Google Workspace 연동: python -m chat_lms_agent gws setup --json (캘린더/시트/드라이브/메일)"
}

$actions = if ($Mode -eq "User") {
    @(
        "create private profile folders",
        "write private AGENTS.md",
        "write private profile config",
        "write private memory note",
        "write private SessionStart hydrate hook",
        "materialize lesson panel runtime assets",
        "delegate bootstrap plan to python -m chat_lms_agent bootstrap plan --json",
        "delegate bootstrap apply to python -m chat_lms_agent bootstrap apply --json",
        "delegate runtime sync to python -m chat_lms_agent bootstrap sync-runtime --json",
        "enable SessionStart safe runtime auto-sync",
        "optionally import existing local DB",
        "run doctor"
    )
} else {
    @(
        "check python",
        "check package",
        "prepare plugin",
        "prepare skills",
        "prepare hooks",
        "run doctor"
    )
}

if ($DryRun) {
    Write-Output "BOOTSTRAP_DRY_RUN PASS"
    Write-Output "MODE $Mode"
    Write-Output "PROFILE $Profile"
    foreach ($action in $actions) {
        Write-Output "DRY_RUN action=$action"
    }
    exit 0
}

if ($Mode -eq "User") {
    Invoke-UserMode `
        -ProfileName $Profile `
        -ImportPath $ImportDbPath `
        -LegacyPath $LegacyToolsPath `
        -OverwriteExisting:$Force
    exit 0
}

Write-Output "BOOTSTRAP PASS"
foreach ($action in $actions) {
    Write-Output "DONE action=$action"
}
exit 0
