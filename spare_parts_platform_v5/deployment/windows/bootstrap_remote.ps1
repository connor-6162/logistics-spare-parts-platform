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

Write-Host "Deployment completed successfully." -ForegroundColor Green
Write-Host "Open: https://lwqgraduationproject.cn" -ForegroundColor Green
