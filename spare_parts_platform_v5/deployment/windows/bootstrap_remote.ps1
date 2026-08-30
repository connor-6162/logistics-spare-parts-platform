$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PowerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$BootstrapUrl = "https://raw.githubusercontent.com/connor-6162/logistics-spare-parts-platform/main/spare_parts_platform_v5/deployment/windows/bootstrap_remote.ps1"
$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$CurrentPrincipal = New-Object Security.Principal.WindowsPrincipal($CurrentIdentity)
$IsAdministrator = $CurrentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $IsAdministrator) {
    $ElevatedBootstrap = Join-Path $env:TEMP "spare-parts-platform-bootstrap-elevated.ps1"
    Write-Host "Administrator permission is required. Preparing the elevated installer..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $BootstrapUrl -OutFile $ElevatedBootstrap -UseBasicParsing
    $ElevatedArguments = "-NoProfile -NoExit -ExecutionPolicy Bypass -File `"$ElevatedBootstrap`""
    try {
        Start-Process -FilePath $PowerShellExe -ArgumentList $ElevatedArguments -Verb RunAs | Out-Null
    } catch {
        throw "Administrator elevation was cancelled or failed. Run PowerShell as administrator and try again."
    }
    Write-Host "A Windows administrator confirmation should now be visible. Click Yes, then continue in the new PowerShell window." -ForegroundColor Cyan
    return
}

$WorkRoot = Join-Path $env:TEMP "spare-parts-platform-bootstrap"
$ArchivePath = Join-Path $WorkRoot "source.zip"
$ExtractRoot = Join-Path $WorkRoot "source"
$RepositoryArchive = "https://github.com/connor-6162/logistics-spare-parts-platform/archive/refs/heads/main.zip"

if (Test-Path -LiteralPath $WorkRoot) {
    Remove-Item -LiteralPath $WorkRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $ExtractRoot -Force | Out-Null

Write-Host "Downloading application source..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $RepositoryArchive -OutFile $ArchivePath -UseBasicParsing
Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractRoot -Force

$SourceRoot = Join-Path $ExtractRoot "logistics-spare-parts-platform-main\spare_parts_platform_v5"
$Installer = Join-Path $SourceRoot "deployment\windows\install_application.ps1"
if (-not (Test-Path -LiteralPath $Installer)) {
    throw "Deployment installer is missing from the downloaded repository."
}

Write-Host "Installing Python application and dependencies..." -ForegroundColor Cyan
& $PowerShellExe -NoProfile -ExecutionPolicy Bypass -File $Installer
if ($LASTEXITCODE -ne 0) {
    throw "Application installer failed with exit code $LASTEXITCODE."
}

$AppRoot = if (Test-Path -LiteralPath "D:\") { "D:\SparePartsPlatform" } else { "C:\SparePartsPlatform" }
$ConfigPath = Join-Path $AppRoot "deployment\windows\production.env.ps1"
$Config = Get-Content -LiteralPath $ConfigPath -Raw
$Config = $Config.Replace("`$env:SESSION_COOKIE_SECURE = 'True'", "`$env:SESSION_COOKIE_SECURE = 'False'")
$Config = $Config.Replace("`$env:PREFERRED_URL_SCHEME = 'https'", "`$env:PREFERRED_URL_SCHEME = 'http'")
$Config = $Config.Replace("`$env:PUBLIC_BASE_URL = 'https://lwqgraduationproject.cn'", "`$env:PUBLIC_BASE_URL = 'http://lwqgraduationproject.cn'")
$Config = $Config.Replace("`$env:HOST = '127.0.0.1'", "`$env:HOST = '0.0.0.0'")
$Config = $Config.Replace("`$env:PORT = '5055'", "`$env:PORT = '80'")
Set-Content -LiteralPath $ConfigPath -Value $Config -Encoding UTF8

Stop-ScheduledTask -TaskName "SparePartsPlatform" -ErrorAction SilentlyContinue
foreach ($Port in 5055, 80) {
    $Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($Listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($ProcessInfo -and ($ProcessInfo.CommandLine -like "*$AppRoot*" -or $ProcessInfo.CommandLine -like "*serve.py*")) {
            Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}
Start-Sleep -Seconds 2
try {
    New-NetFirewallRule -DisplayName "Spare Parts Platform HTTP" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 -ErrorAction Stop | Out-Null
} catch {
}
Start-ScheduledTask -TaskName "SparePartsPlatform"

$Ready = $false
for ($Attempt = 1; $Attempt -le 90; $Attempt++) {
    Start-Sleep -Seconds 1
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1/healthz" -TimeoutSec 2
        if ($Health.status -eq "ok") {
            $Ready = $true
            break
        }
    } catch {
    }
}

if (-not $Ready) {
    throw "The application did not become healthy. Check the application log under SparePartsData\logs."
}

Write-Host "Deployment completed successfully." -ForegroundColor Green
Write-Host "Open: http://lwqgraduationproject.cn" -ForegroundColor Green
