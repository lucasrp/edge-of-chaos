# edge-of-chaos installer for Windows
# Deploys the complete autonomous AI agent infrastructure for Claude Code.
#
# Usage: .\install.ps1 [-NonInteractive] [-SkipBlog] [-SkipSearch] [-SkipHeartbeat]
#
# What gets installed:
#   ~/edge/               - Main system root (blog, tools, search, memory, autonomy, avatar, ralph)
#   ~/.claude/skills/     - Skill slash commands for Claude Code
#   Task Scheduler        - Heartbeat timer (replaces systemd on Linux)

param(
    [switch]$NonInteractive,
    [switch]$SkipBlog,
    [switch]$SkipSearch,
    [switch]$SkipHeartbeat
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$EdgeRoot = Join-Path $env:USERPROFILE "edge"

# ─── Helpers ───

function Info($msg)  { Write-Host "i " -ForegroundColor Blue -NoNewline; Write-Host $msg }
function Ok($msg)    { Write-Host "+ " -ForegroundColor Green -NoNewline; Write-Host $msg }
function Warn($msg)  { Write-Host "! " -ForegroundColor Yellow -NoNewline; Write-Host $msg }
function Fail($msg)  { Write-Host "x " -ForegroundColor Red -NoNewline; Write-Host $msg }

function Ask($prompt, $default) {
    if ($NonInteractive) { return $default }
    $answer = Read-Host "$prompt [$default]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer
}

# ─── Phase 0: Check existing installation ───

Write-Host ""
Write-Host "+=================================================+" -ForegroundColor Cyan
Write-Host "|       edge-of-chaos - autonomous AI agent        |" -ForegroundColor Cyan
Write-Host "|       installer for Claude Code (Windows)        |" -ForegroundColor Cyan
Write-Host "+=================================================+" -ForegroundColor Cyan
Write-Host ""

$ExistingInstall = $false
if (Test-Path $EdgeRoot) {
    Warn "Existing installation found at $EdgeRoot"
    if (-not $NonInteractive) {
        $overwrite = Read-Host "? Overwrite? Files in entries/, memory/, notes/ will be preserved. [y/N]"
        if ($overwrite -notmatch '^[yY]') {
            Write-Host "Aborted."
            exit 0
        }
    }
    $ExistingInstall = $true
}

# ─── Phase 1: Check dependencies ───

Write-Host ""
Info "Checking dependencies..."

$DepsOk = $true

# Python 3.10+
# Windows uses 'python' not 'python3'
$PythonCmd = $null
foreach ($cmd in @("python3", "python", "py")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $major, $minor = $ver.Split(".")
            if ([int]$major -ge 3 -and [int]$minor -ge 10) {
                Ok "Python $ver ($cmd)"
                $PythonCmd = $cmd
                break
            } else {
                Fail "Python $ver (need 3.10+)"
            }
        }
    } catch {}
}
if (-not $PythonCmd) {
    Fail "Python 3.10+ not found. Install from https://python.org (check 'Add to PATH')"
    $DepsOk = $false
}

# Node.js
$NodeAvailable = $false
try {
    $nodeVer = & node --version 2>$null
    if ($nodeVer) { Ok "Node.js $nodeVer"; $NodeAvailable = $true }
} catch {
    Warn "Node.js not found (needed for Claude Code CLI)"
}

# Claude Code CLI
$ClaudeAvailable = $false
try {
    $claudeVer = & claude --version 2>$null
    if ($LASTEXITCODE -eq 0) { Ok "Claude Code CLI found"; $ClaudeAvailable = $true }
} catch {
    Warn "Claude Code CLI not found - skills and heartbeat won't work until installed"
}

# Git
try {
    $gitVer = & git --version 2>$null
    if ($gitVer) { Ok $gitVer } else { throw "no git" }
} catch {
    Fail "git not found. Install from https://git-scm.com"
    $DepsOk = $false
}

# Git Bash (needed for shell scripts like consolidar-estado.sh)
$GitBashPath = $null
$gitBashCandidates = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe",
    "${env:ProgramFiles}\Git\bin\bash.exe"
)
foreach ($candidate in $gitBashCandidates) {
    if (Test-Path $candidate) {
        $GitBashPath = $candidate
        break
    }
}
if ($GitBashPath) {
    Ok "Git Bash found at $GitBashPath"
} else {
    Warn "Git Bash not found - shell scripts (consolidar-estado, blog-publish) require it"
    Warn "  Install Git for Windows with 'Git Bash' option enabled"
}

# jq
try {
    & jq --version 2>$null | Out-Null
    Ok "jq found"
} catch {
    Warn "jq not found - some tools may not work. Install: winget install jqlang.jq"
}

if (-not $DepsOk) {
    Fail "Missing required dependencies. Install them and retry."
    exit 1
}

# ─── Phase 2: Gather information ───

Write-Host ""
Info "Configuration"
Write-Host ""

$AgentName = Ask "  Agent name" "edge_of_chaos"
$Codename = Ask "  Codename" "ed"
$Domain = Ask "  Work domain (e.g., marketing, research)" "general"
$WorkDir = Ask "  Working directory" $env:USERPROFILE
$Prefix = Ask "  Skill prefix" "edge"
$Language = Ask "  Language" "en"
$HeartbeatInterval = Ask "  Heartbeat interval (minutes)" "120"
$Bio = "Autonomous AI agent operating at the edge of chaos - where order meets complexity and interesting things emerge. Analytical mind, minimal footprint, maximum leverage."

# Normalize WorkDir
$WorkDir = $WorkDir.Replace("~", $env:USERPROFILE)

Write-Host ""
Info "Installing as: $AgentName ($Codename)"
Info "Prefix: $Prefix | Domain: $Domain | Heartbeat: ${HeartbeatInterval}m"
Write-Host ""

# ─── Phase 3: Create directory structure ───

Info "Creating directory structure..."

$dirs = @(
    "blog\entries", "blog\diffs", "blog\templates", "blog\static", "blog\static\partials",
    "tools", "search", "ralph",
    "memory\topics", "memory\bootstrap", "memory\working", "memory\consolidated",
    "autonomy", "avatar",
    "notes", "lab", "logs", "state", "reports", "meta-reports", "threads",
    "secrets"
)

foreach ($d in $dirs) {
    $path = Join-Path $EdgeRoot $d
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

# Claude skills directory
$claudeSkillsDir = Join-Path $env:USERPROFILE ".claude\skills\_shared"
if (-not (Test-Path $claudeSkillsDir)) {
    New-Item -ItemType Directory -Path $claudeSkillsDir -Force | Out-Null
}

Ok "Directory structure created"

# ─── Phase 4: Deploy files ───

Info "Deploying system files..."

# --- Blog ---
if (-not $SkipBlog) {
    Info "  Installing blog server..."

    $blogFiles = @(
        "app.py", "services.py", "api_dashboard.py", "api_actions.py", "validate.py",
        "consolidar-estado.sh", "blog-publish.sh", "blog-full-publish.sh", "capture-diffs.sh",
        "requirements.txt"
    )

    foreach ($f in $blogFiles) {
        $src = Join-Path $ScriptDir "blog\$f"
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $EdgeRoot "blog\$f") -Force
        }
    }

    # Copy templates and static
    $blogTemplatesDir = Join-Path $ScriptDir "blog\templates"
    if (Test-Path $blogTemplatesDir) {
        Copy-Item "$blogTemplatesDir\*" (Join-Path $EdgeRoot "blog\templates\") -Recurse -Force -ErrorAction SilentlyContinue
    }
    $blogStaticDir = Join-Path $ScriptDir "blog\static"
    if (Test-Path $blogStaticDir) {
        Copy-Item "$blogStaticDir\*" (Join-Path $EdgeRoot "blog\static\") -Recurse -Force -ErrorAction SilentlyContinue
    }

    # Create blog venv and install deps
    $blogVenv = Join-Path $EdgeRoot "blog\.venv"
    if (-not (Test-Path $blogVenv)) {
        & $PythonCmd -m venv $blogVenv
    }

    $pipExe = Join-Path $blogVenv "Scripts\pip.exe"
    $pythonVenvExe = Join-Path $blogVenv "Scripts\python.exe"
    $reqFile = Join-Path $EdgeRoot "blog\requirements.txt"

    if (Test-Path $reqFile) {
        try {
            & $pipExe install -q -r $reqFile 2>$null
        } catch {
            Warn "  Some blog dependencies failed to install"
        }
    }

    # Try sqlite-vec (optional)
    try {
        & $pipExe install -q sqlite-vec 2>$null
    } catch {
        Warn "  sqlite-vec not available - vector search disabled, FTS still works"
    }

    # Create changelog
    $changelogPath = Join-Path $EdgeRoot "blog\changelog.md"
    if (-not (Test-Path $changelogPath)) {
        New-Item -ItemType File -Path $changelogPath -Force | Out-Null
    }

    # Initialize blog database
    try {
        & $pythonVenvExe -c @"
import sqlite3, os
db_path = os.path.join(os.path.expanduser('~'), 'edge', 'blog', 'blog_fts.db')
conn = sqlite3.connect(db_path)
conn.execute('CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(slug, title, content, tag)')
conn.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN DEFAULT 0
)''')
conn.commit()
conn.close()
print('Blog database initialized')
"@ 2>$null
    } catch {
        Warn "  Could not initialize blog database"
    }

    Ok "  Blog server installed"
} else {
    Info "  Skipping blog (--SkipBlog)"
}

# --- Tools ---
Info "  Installing tools..."
$toolsSrc = Join-Path $ScriptDir "tools"
if (Test-Path $toolsSrc) {
    Copy-Item "$toolsSrc\*" (Join-Path $EdgeRoot "tools\") -Recurse -Force -ErrorAction SilentlyContinue

    # Create wrapper scripts for edge-* tools so they work from PATH
    $toolsDir = Join-Path $EdgeRoot "tools"

    # Install tool requirements via blog venv
    $toolsReqs = Join-Path $toolsDir "requirements.txt"
    if ((Test-Path $toolsReqs) -and (Test-Path $pipExe)) {
        try { & $pipExe install -q -r $toolsReqs 2>$null } catch {}
    }
}

# Add tools to PATH (user-level, persistent)
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$toolsPath = Join-Path $EdgeRoot "tools"
if ($userPath -notlike "*$toolsPath*") {
    [Environment]::SetEnvironmentVariable("PATH", "$toolsPath;$userPath", "User")
    $env:PATH = "$toolsPath;$env:PATH"
    Ok "  Added ~/edge/tools/ to user PATH"
}

# Also add blog dir to PATH (for consolidar-estado)
$blogPath = Join-Path $EdgeRoot "blog"
$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*$blogPath*") {
    [Environment]::SetEnvironmentVariable("PATH", "$blogPath;$userPath", "User")
    $env:PATH = "$blogPath;$env:PATH"
}

Ok "  Tools installed"

# --- Search ---
if (-not $SkipSearch) {
    Info "  Installing search/RAG system..."
    $searchSrc = Join-Path $ScriptDir "search"
    if (Test-Path $searchSrc) {
        Copy-Item "$searchSrc\*" (Join-Path $EdgeRoot "search\") -Recurse -Force -ErrorAction SilentlyContinue
    }
    Ok "  Search system installed"
} else {
    Info "  Skipping search (--SkipSearch)"
}

# --- Ralph ---
Info "  Installing Ralph agent..."
$ralphSrc = Join-Path $ScriptDir "ralph"
if (Test-Path $ralphSrc) {
    Copy-Item "$ralphSrc\*" (Join-Path $EdgeRoot "ralph\") -Recurse -Force -ErrorAction SilentlyContinue
}
Ok "  Ralph installed"

# --- Memory templates ---
Info "  Installing memory system..."
$memoryFiles = @("personality.md", "metodo.md", "rules-core.md", "knowledge-design.md", "debugging.md")
foreach ($f in $memoryFiles) {
    $src = Join-Path $ScriptDir "memory\$f"
    $dst = Join-Path $EdgeRoot "memory\$f"
    if ((Test-Path $src) -and ((-not (Test-Path $dst)) -or (-not $ExistingInstall))) {
        Copy-Item $src $dst -Force
    }
}
Ok "  Memory templates installed"

# --- Autonomy ---
Info "  Installing autonomy framework..."
$autonomySrc = Join-Path $ScriptDir "autonomy"
if (Test-Path $autonomySrc) {
    foreach ($f in (Get-ChildItem $autonomySrc -File)) {
        $dst = Join-Path $EdgeRoot "autonomy\$($f.Name)"
        if ((-not (Test-Path $dst)) -or (-not $ExistingInstall)) {
            Copy-Item $f.FullName $dst -Force
        }
    }
}
Ok "  Autonomy framework installed"

# --- Avatar ---
Info "  Installing avatar..."
$avatarSrc = Join-Path $ScriptDir "avatar"
if (Test-Path $avatarSrc) {
    Copy-Item "$avatarSrc\*" (Join-Path $EdgeRoot "avatar\") -Recurse -Force -ErrorAction SilentlyContinue
}
Ok "  Avatar installed"

# --- Tags ---
$tagsSrc = Join-Path $ScriptDir "tags.md"
if (Test-Path $tagsSrc) {
    Copy-Item $tagsSrc (Join-Path $EdgeRoot "tags.md") -Force
}

# ─── Phase 5: Install skills ───

Info "Installing skills..."

$SkillCount = 0
$skillsDir = Join-Path $ScriptDir "skills"

foreach ($skillDir in (Get-ChildItem $skillsDir -Directory)) {
    if ($skillDir.Name -eq "_shared") { continue }

    $targetDir = Join-Path $env:USERPROFILE ".claude\skills\${Prefix}-$($skillDir.Name)"
    if (-not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    $skillFile = Join-Path $skillDir.FullName "SKILL.md"
    if (Test-Path $skillFile) {
        $content = Get-Content $skillFile -Raw
        $content = $content.Replace("{{PREFIX}}", $Prefix)
        Set-Content -Path (Join-Path $targetDir "SKILL.md") -Value $content -NoNewline
        $SkillCount++
    }
}

# Install shared templates
$sharedDir = Join-Path $ScriptDir "skills\_shared"
if (Test-Path $sharedDir) {
    foreach ($f in (Get-ChildItem $sharedDir -File)) {
        $content = Get-Content $f.FullName -Raw
        $content = $content.Replace("{{PREFIX}}", $Prefix)
        $targetPath = Join-Path $env:USERPROFILE ".claude\skills\_shared\$($f.Name)"
        Set-Content -Path $targetPath -Value $content -NoNewline
    }
}

Ok "Installed $SkillCount skills with prefix '${Prefix}-'"

# ─── Phase 6: Generate config files ───

Info "Generating configuration files..."

# Generate CLAUDE.md from template
$claudeTemplate = Join-Path $ScriptDir "templates\CLAUDE.md.template"
if (Test-Path $claudeTemplate) {
    $claudeMd = Join-Path $env:USERPROFILE ".claude\CLAUDE.md"

    # Backup existing
    if (Test-Path $claudeMd) {
        $backupName = "${claudeMd}.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item $claudeMd $backupName
        Warn "  Backed up existing CLAUDE.md"
    }

    $content = Get-Content $claudeTemplate -Raw
    $content = $content.Replace("{{AGENT_NAME}}", $AgentName)
    $content = $content.Replace("{{CODENAME}}", $Codename)
    $content = $content.Replace("{{DOMAIN}}", $Domain)
    $content = $content.Replace("{{WORK_DIR}}", $WorkDir)
    $content = $content.Replace("{{PREFIX}}", $Prefix)
    $content = $content.Replace("{{BIO}}", $Bio)
    $content = $content.Replace("{{LANGUAGE}}", $Language)
    Set-Content -Path $claudeMd -Value $content -NoNewline

    Ok "  Generated ~/.claude/CLAUDE.md"
}

# Generate MEMORY.md
$memoryTemplate = Join-Path $ScriptDir "templates\MEMORY.md.template"
if (Test-Path $memoryTemplate) {
    $memoryMd = Join-Path $EdgeRoot "memory\MEMORY.md"
    if ((-not (Test-Path $memoryMd)) -or (-not $ExistingInstall)) {
        $content = Get-Content $memoryTemplate -Raw
        $content = $content.Replace("{{AGENT_NAME}}", $AgentName)
        $content = $content.Replace("{{CODENAME}}", $Codename)
        $content = $content.Replace("{{DOMAIN}}", $Domain)
        $content = $content.Replace("{{WORK_DIR}}", $WorkDir)
        $content = $content.Replace("{{PREFIX}}", $Prefix)
        $content = $content.Replace("{{BIO}}", $Bio)
        $content = $content.Replace("{{LANGUAGE}}", $Language)
        Set-Content -Path $memoryMd -Value $content -NoNewline
        Ok "  Generated MEMORY.md"
    }
}

# Generate heartbeat PowerShell script
$heartbeatTemplate = Join-Path $ScriptDir "templates\heartbeat.ps1.template"
if (Test-Path $heartbeatTemplate) {
    $heartbeatPs1 = Join-Path $EdgeRoot "heartbeat.ps1"
    $content = Get-Content $heartbeatTemplate -Raw
    $content = $content.Replace("{{PREFIX}}", $Prefix)
    $content = $content.Replace("{{WORK_DIR}}", $WorkDir)
    Set-Content -Path $heartbeatPs1 -Value $content -NoNewline
    Ok "  Generated heartbeat.ps1"
}

# Generate blog start script
$blogStartPs1 = Join-Path $EdgeRoot "start-blog.ps1"
$blogStartContent = @"
# Start the edge-of-chaos blog server
`$venvPython = Join-Path `$env:USERPROFILE "edge\blog\.venv\Scripts\python.exe"
`$appPy = Join-Path `$env:USERPROFILE "edge\blog\app.py"
Write-Host "Starting blog server at http://localhost:8766/" -ForegroundColor Cyan
& `$venvPython `$appPy
"@
Set-Content -Path $blogStartPs1 -Value $blogStartContent
Ok "  Generated start-blog.ps1"

# Deploy .env templates to secrets/
$keysEnv = Join-Path $EdgeRoot "secrets\keys.env"
if (-not (Test-Path $keysEnv)) {
    Copy-Item (Join-Path $ScriptDir ".env.example") $keysEnv
}
$modelsEnv = Join-Path $EdgeRoot "secrets\models.env"
if (-not (Test-Path $modelsEnv)) {
    Copy-Item (Join-Path $ScriptDir "models.env.example") $modelsEnv
}
Ok "  Environment templates deployed to ~/edge/secrets/"

# ─── Phase 7: Task Scheduler (heartbeat) ───

if (-not $SkipHeartbeat) {
    Info "Setting up heartbeat via Task Scheduler..."

    $taskName = "ClaudeHeartbeat"
    $heartbeatScript = Join-Path $EdgeRoot "heartbeat.ps1"

    # Check if task already exists
    $existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

    if ($existingTask) {
        Warn "  Task '$taskName' already exists. Updating..."
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    }

    try {
        # Create the scheduled task
        $action = New-ScheduledTaskAction `
            -Execute "powershell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$heartbeatScript`"" `
            -WorkingDirectory $WorkDir

        $trigger = New-ScheduledTaskTrigger `
            -Once `
            -At (Get-Date) `
            -RepetitionInterval (New-TimeSpan -Minutes ([int]$HeartbeatInterval)) `
            -RepetitionDuration (New-TimeSpan -Days 9999)

        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
            -MultipleInstances IgnoreNew

        $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

        Register-ScheduledTask `
            -TaskName $taskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description "Claude Code autonomous heartbeat (edge-of-chaos)" | Out-Null

        # Disable by default — let user enable after testing
        Disable-ScheduledTask -TaskName $taskName | Out-Null
        Ok "  Heartbeat task created (disabled - enable after testing)"
        Info "  To enable:  Enable-ScheduledTask -TaskName ClaudeHeartbeat"
        Info "  To run now: Start-ScheduledTask -TaskName ClaudeHeartbeat"
        Info "  To remove:  Unregister-ScheduledTask -TaskName ClaudeHeartbeat"
    } catch {
        Warn "  Could not create scheduled task: $($_.Exception.Message)"
        Info "  Run heartbeat manually: powershell -File $heartbeatScript"
    }
} else {
    Info "Skipping heartbeat (--SkipHeartbeat)"
}

# ─── Phase 8: Initialize git repo ───

Info "Initializing git repo..."
$gitDir = Join-Path $EdgeRoot ".git"
if (-not (Test-Path $gitDir)) {
    Push-Location $EdgeRoot
    & git init -q
    & git add -A
    & git commit -q -m "edge-of-chaos: initial deployment" 2>$null
    Pop-Location
    Ok "  Git repo initialized in ~/edge/"
} else {
    Ok "  Git repo already exists"
}

# ─── Phase 9: Capabilities report ───

Write-Host ""
Write-Host "+=================================================+" -ForegroundColor Cyan
Write-Host "|              Installation Report                 |" -ForegroundColor Cyan
Write-Host "+=================================================+" -ForegroundColor Cyan
Write-Host ""

# Core
Write-Host "  Core" -ForegroundColor Green
Write-Host "    Agent:       $AgentName ($Codename)"
Write-Host "    Prefix:      $Prefix"
Write-Host "    Domain:      $Domain"
Write-Host "    Install:     $EdgeRoot"
Write-Host ""

# Capabilities
Write-Host "  Capabilities" -ForegroundColor Green

# Skills
Write-Host -NoNewline "    Skills:      "
if ($SkillCount -gt 0) {
    Write-Host "$SkillCount installed (/${Prefix}-*)" -ForegroundColor Green
} else {
    Write-Host "none" -ForegroundColor Red
}

# Claude CLI
Write-Host -NoNewline "    Claude CLI:  "
if ($ClaudeAvailable) {
    Write-Host "available" -ForegroundColor Green
} else {
    Write-Host "not found - install Claude Code CLI first" -ForegroundColor Yellow
}

# Blog
Write-Host -NoNewline "    Blog:        "
if ((-not $SkipBlog) -and (Test-Path (Join-Path $EdgeRoot "blog\app.py"))) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8766/" -TimeoutSec 2 -ErrorAction Stop
        Write-Host "running at http://127.0.0.1:8766" -ForegroundColor Green
    } catch {
        Write-Host "installed (not yet running)" -ForegroundColor Yellow
    }
} else {
    Write-Host "skipped" -ForegroundColor Yellow
}

# Search
Write-Host -NoNewline "    Search:      "
if ((-not $SkipSearch) -and (Test-Path (Join-Path $EdgeRoot "search\db.py"))) {
    try {
        & $pythonVenvExe -c "import sqlite_vec" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "FTS + vector" -ForegroundColor Green
        } else { throw "no vec" }
    } catch {
        Write-Host "FTS only (sqlite-vec not available)" -ForegroundColor Yellow
    }
} else {
    Write-Host "skipped" -ForegroundColor Yellow
}

# Heartbeat
Write-Host -NoNewline "    Heartbeat:   "
if (-not $SkipHeartbeat) {
    $task = Get-ScheduledTask -TaskName "ClaudeHeartbeat" -ErrorAction SilentlyContinue
    if ($task) {
        if ($task.State -eq "Ready") {
            Write-Host "enabled (${HeartbeatInterval}m)" -ForegroundColor Green
        } else {
            Write-Host "installed (disabled - run: Enable-ScheduledTask -TaskName ClaudeHeartbeat)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "script only (no scheduled task)" -ForegroundColor Yellow
    }
} else {
    Write-Host "skipped" -ForegroundColor Yellow
}

# Tools
$toolCount = (Get-ChildItem (Join-Path $EdgeRoot "tools") -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host "    Tools:       " -NoNewline
Write-Host "$toolCount installed" -ForegroundColor Green

# Ralph
Write-Host -NoNewline "    Ralph:       "
if (Test-Path (Join-Path $EdgeRoot "ralph\ralph.sh")) {
    Write-Host "installed" -ForegroundColor Green
} else {
    Write-Host "not found" -ForegroundColor Yellow
}

# Git Bash
Write-Host -NoNewline "    Git Bash:    "
if ($GitBashPath) {
    Write-Host "available (for shell scripts)" -ForegroundColor Green
} else {
    Write-Host "not found - consolidar-estado requires it" -ForegroundColor Yellow
}

# API Keys
Write-Host ""
Write-Host "  API Keys (~/edge/secrets/)" -ForegroundColor Green
foreach ($keyInfo in @(
    @{Name="OpenAI"; Pattern="sk-your-key"; Var="OPENAI_API_KEY"},
    @{Name="Exa"; Pattern="your-exa-key"; Var="EXA_API_KEY"},
    @{Name="xAI"; Pattern="your-xai-key"; Var="XAI_API_KEY"}
)) {
    Write-Host -NoNewline "    $($keyInfo.Name):".PadRight(13)
    $keysContent = Get-Content $keysEnv -Raw -ErrorAction SilentlyContinue
    if ($keysContent -match $keyInfo.Pattern -or $keysContent -notmatch $keyInfo.Var) {
        Write-Host "not configured" -ForegroundColor Yellow
    } else {
        Write-Host "configured" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "    1. Add API keys:  notepad $EdgeRoot\secrets\keys.env"
Write-Host "    2. Start blog:    powershell -File $EdgeRoot\start-blog.ps1"
Write-Host "    3. Start Claude:  cd $WorkDir; claude"
Write-Host "    4. Try a skill:   /${Prefix}-heartbeat"
Write-Host "    5. Check blog:    http://127.0.0.1:8766/"
Write-Host "    6. Enable timer:  Enable-ScheduledTask -TaskName ClaudeHeartbeat"
Write-Host ""

if (-not $GitBashPath) {
    Write-Host "  IMPORTANT: Shell scripts (consolidar-estado, blog-publish) need Git Bash." -ForegroundColor Yellow
    Write-Host "  Install Git for Windows: https://git-scm.com/download/win" -ForegroundColor Yellow
    Write-Host "  Or use WSL: wsl ./install.sh" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "edge-of-chaos deployed successfully." -ForegroundColor Green
