# bash-wrapper.ps1 — Run shell scripts via Git Bash on Windows
# Usage: powershell -File bash-wrapper.ps1 <script.sh> [args...]
#
# Finds Git Bash automatically, converts Windows paths to Unix-style paths,
# and runs the script. Used by consolidar-estado and blog-publish on Windows.

param(
    [Parameter(Mandatory=$true, Position=0)]
    [string]$Script,

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

# Find Git Bash
$bashCandidates = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe",
    "${env:ProgramFiles}\Git\bin\bash.exe",
    "${env:ProgramW6432}\Git\bin\bash.exe"
)

$bashExe = $null
foreach ($candidate in $bashCandidates) {
    if (Test-Path $candidate) {
        $bashExe = $candidate
        break
    }
}

# Also check PATH
if (-not $bashExe) {
    $bashExe = Get-Command bash -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
}

if (-not $bashExe) {
    Write-Host "ERROR: Git Bash not found. Install Git for Windows: https://git-scm.com/download/win" -ForegroundColor Red
    Write-Host "Or use WSL: wsl bash $Script $($Arguments -join ' ')" -ForegroundColor Yellow
    exit 1
}

# Convert Windows path to Unix path for Git Bash
function ConvertTo-UnixPath($winPath) {
    if (-not $winPath) { return $winPath }
    $resolved = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($winPath)
    # C:\Users\foo -> /c/Users/foo
    if ($resolved -match '^([A-Za-z]):\\(.*)$') {
        $drive = $Matches[1].ToLower()
        $rest = $Matches[2].Replace('\', '/')
        return "/$drive/$rest"
    }
    return $resolved.Replace('\', '/')
}

$unixScript = ConvertTo-UnixPath $Script
$unixArgs = $Arguments | ForEach-Object { ConvertTo-UnixPath $_ }

# Set HOME for Git Bash (it may not be set correctly)
$env:HOME = $env:USERPROFILE

& $bashExe $unixScript @unixArgs
exit $LASTEXITCODE
