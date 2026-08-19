# Install the /daily-grace command on Windows.
#
#   .\install.ps1              # default language: Russian
#   .\install.ps1 -Language Spanish
#
# Safe to re-run; it overwrites the installed command with a fresh copy.

param([string]$Language = "Russian")

$ErrorActionPreference = "Stop"

$PkgDir      = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommandsDir = Join-Path $env:USERPROFILE ".claude\commands"
$Target      = Join-Path $CommandsDir "daily-grace.md"
$Template    = Join-Path $PkgDir "command-template.md"

if (-not (Test-Path $Template)) { throw "command-template.md not found next to this script." }

# --- Python ---------------------------------------------------------------
$Python = $null
foreach ($candidate in @("python", "python3", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        & $candidate -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $Python = $candidate; break }
    }
}
if (-not $Python) { throw "Python 3.9+ not found. Install from https://python.org" }
Write-Host "python:   $Python ($(& $Python --version))"

# --- Install the command --------------------------------------------------
if (-not (Test-Path $CommandsDir)) { New-Item -ItemType Directory -Force $CommandsDir | Out-Null }

# Forward slashes work fine in the quoted paths the command emits, and avoid
# backslash-escaping headaches in the generated markdown.
$PkgDirFwd = $PkgDir.Replace("\", "/")

(Get-Content $Template -Raw -Encoding utf8).
    Replace("{{PKG_DIR}}", $PkgDirFwd).
    Replace("{{PYTHON}}", $Python).
    Replace("{{LANGUAGE}}", $Language) |
    Out-File -FilePath $Target -Encoding utf8 -NoNewline

Write-Host "command:  $Target"
Write-Host "language: $Language"

# --- Credentials ----------------------------------------------------------
$EnvFile = Join-Path $PkgDir ".env"
if (-not (Test-Path $EnvFile)) {
    (Get-Content (Join-Path $PkgDir ".env.example") -Raw -Encoding utf8) -replace
        "(?m)^GMAIL_ADDRESS=.*$", "GMAIL_ADDRESS=" |
        Out-File -FilePath $EnvFile -Encoding utf8
    Write-Host ""
    Write-Host "Created $EnvFile - you still need to fill it in:"
    Write-Host "  1. Enable 2-Step Verification: https://myaccount.google.com/signinoptions/two-step-verification"
    Write-Host "  2. Create an App Password:     https://myaccount.google.com/apppasswords"
    Write-Host "  3. Put your address and that password into .env"
    Write-Host "  4. Gmail -> Settings -> Forwarding and POP/IMAP -> Enable IMAP"
} else {
    Write-Host "env:      $EnvFile (left as-is)"
}

Write-Host ""
Write-Host "Done. Once .env is filled in, start the app with:"
Write-Host "  $Python `"$PkgDir\app.py`"      (or double-click start.bat)"
Write-Host ""
Write-Host "No-UI alternatives:"
Write-Host "  $Python `"$PkgDir\daily_grace.py`"   # terminal, prints + copies"
Write-Host "  /daily-grace                          # inside Claude Code"
