param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Event
)

# Chat LMS Agent Codex plugin hook dispatcher.
#
# This plugin is registered globally, but it ACTS ONLY inside a Chat LMS
# teaching workspace -- a directory tree that contains a .chat-lms-profile.json
# marker. In any other Codex session it emits an empty no-op so unrelated
# projects are never touched. The teaching workspace is discovered by walking
# up from the session working directory (Codex runs hooks with cwd = session
# cwd), and the profile root is its parent directory.

$ErrorActionPreference = "Stop"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
try {
    [Console]::InputEncoding = $utf8NoBom
    [Console]::OutputEncoding = $utf8NoBom
} catch {
    # Some hosts hand us a non-redirectable console; encoding stays default.
}
$OutputEncoding = $utf8NoBom

function Write-NoOp {
    Write-Output "{}"
    exit 0
}

try {
    # The hook payload arrives on stdin; capture it so we can forward it verbatim.
    $raw = [Console]::In.ReadToEnd()
    if ($null -eq $raw) { $raw = "" }

    # Locate the teaching workspace by walking up from the session cwd.
    $dir = (Get-Location).Path
    $workspace = $null
    while ($dir) {
        if (Test-Path -LiteralPath (Join-Path $dir ".chat-lms-profile.json")) {
            $workspace = $dir
            break
        }
        $parent = Split-Path -Parent $dir
        if (-not $parent -or $parent -eq $dir) { break }
        $dir = $parent
    }
    if (-not $workspace) { Write-NoOp }

    # SessionStart is served by the workspace's own hydrate/sync script.
    if ($Event -eq "session-start") {
        $hydrate = Join-Path $workspace "scripts\session-start-hydrate.ps1"
        if (Test-Path -LiteralPath $hydrate) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $hydrate
            exit $LASTEXITCODE
        }
        Write-NoOp
    }

    # All other events go through the tested CLI wrapper in the workspace, which
    # resolves the Python runtime (py -3 first, avoiding the Store alias) and the
    # public-repo PYTHONPATH before invoking the harness hook handler.
    $cli = Join-Path $workspace "scripts\chat-lms-cli.ps1"
    if (-not (Test-Path -LiteralPath $cli)) { Write-NoOp }
    $profileRoot = Split-Path -Parent $workspace

    $cliArgs = @("hook", $Event)
    if ($Event -eq "stop") { $cliArgs += "--verify-memory" }
    $cliArgs += @("--profile-root", $profileRoot, "--json")

    $raw | & powershell -NoProfile -ExecutionPolicy Bypass -File $cli @cliArgs
    exit $LASTEXITCODE
} catch {
    # Never break a Codex session because of a hook failure.
    Write-Output "{}"
    exit 0
}
