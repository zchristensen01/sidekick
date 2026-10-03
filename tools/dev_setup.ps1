# Developer setup for Sidekick (not for players: they use SidekickSetup.exe, see README).
# From the repo folder, in PowerShell:
#   powershell -ExecutionPolicy Bypass -File tools\dev_setup.ps1
# Makes a private Python environment (.venv) and installs Sidekick into it with the test tools,
# so `scout`, `pytest` and `ruff` work. Safe to run again. Needs Python 3.11 or newer and Git.
# A developer copy keeps its settings and data in %LOCALAPPDATA%\Sidekick, like the installed
# app (scout/paths.py), so nothing personal lands in the repo folder.

$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repo

function Say($text) { Write-Host "==> $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host $text -ForegroundColor Red; exit 1 }

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
    Fail "Python 3.11 or newer isn't installed (winget install -e --id Python.Python.3.13)."
}

# 2. The private environment, with Sidekick and the test tools in it
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Say "Making the Python environment (.venv)"
    & $pyExe @pyArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Couldn't make .venv (see the message above)." }
}
Say "Installing Sidekick and the test tools"
& $venvPython -m pip install --quiet --disable-pip-version-check --upgrade pip
& $venvPython -m pip install --quiet --disable-pip-version-check -e ".[dev]"
if ($LASTEXITCODE -ne 0) { Fail "Installing failed (see the message above)." }
Say "Done. Activate with .venv\Scripts\Activate.ps1, then: scout doctor, pytest, ruff check ."
