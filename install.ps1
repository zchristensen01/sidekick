# Sidekick installer for Windows. From the Sidekick folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File install.ps1
# It makes a private Python environment (.venv), installs Sidekick into it, puts Sidekick on the
# Desktop and in the Start menu, and opens it. Safe to run again: it updates what's there.
# Needs Python 3.11 or newer (python.org) and, for the app's Update button, Git (git-scm.com).

$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot

function Say($text) { Write-Host "==> $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host $text -ForegroundColor Red; exit 1 }

if (Get-Process sidekick -ErrorAction SilentlyContinue) {
    Fail "Sidekick is open. Close its window, then run this again."
}

# 1. Python 3.11 or newer
$pyExe = $null
$pyArgs = @()
$check = "import sys; print(int(sys.version_info >= (3, 11)))"
if (Get-Command py -ErrorAction SilentlyContinue) {
    $ok = & py -3 -c $check 2>$null
    if ($ok -eq "1") { $pyExe = "py"; $pyArgs = @("-3") }
}
if (-not $pyExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $ok = & python -c $check 2>$null
    if ($ok -eq "1") { $pyExe = "python" }
}
if (-not $pyExe) {
    Fail ("Python 3.11 or newer isn't installed. Get it from https://www.python.org/downloads/ " +
          "(tick 'Add python.exe to PATH'), or run: winget install -e --id Python.Python.3.13 " +
          "Then run this again.")
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Note: Git isn't installed, so the app's Update button won't work. Get it from https://git-scm.com/download/win" -ForegroundColor DarkYellow
}

# 2. The private environment and Sidekick in it
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Say "Making the Python environment (.venv)"
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Couldn't make .venv (see the message above)." }
}
Say "Installing Sidekick and what it needs (a minute or two the first time)"
& $venvPython -m pip install --quiet --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --quiet --disable-pip-version-check -e .
if ($LASTEXITCODE -ne 0) { Fail "Installing failed (see the message above)." }

# 3. Shortcuts, then open it (the app makes its settings files and downloads the data itself)
Say "Adding Desktop and Start menu shortcuts"
& (Join-Path $PSScriptRoot ".venv\Scripts\scout.exe") shortcut
Say "Opening Sidekick. Next time, use the Sidekick shortcut on your Desktop."
Start-Process (Join-Path $PSScriptRoot ".venv\Scripts\sidekick.exe")
