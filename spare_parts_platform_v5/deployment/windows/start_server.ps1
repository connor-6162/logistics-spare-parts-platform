$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ConfigPath = Join-Path $PSScriptRoot "production.env.ps1"
$DataRoot = if (Test-Path -LiteralPath "D:\") { "D:\SparePartsData" } else { "C:\SparePartsData" }
$LogRoot = Join-Path $DataRoot "logs"

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Missing production configuration: $ConfigPath"
}

. $ConfigPath
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

$PythonExe = Join-Path $AppRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

Set-Location -LiteralPath $AppRoot
& $PythonExe "serve.py" *>> (Join-Path $LogRoot "application.log")
