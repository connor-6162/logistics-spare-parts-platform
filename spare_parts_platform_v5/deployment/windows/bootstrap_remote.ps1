# 远程一键部署引导脚本。
# 功能：申请管理员权限、下载 GitHub 主分支压缩包、兼容旧版 PowerShell 解压，
# 然后调用 install_application.ps1 完成正式安装。本脚本不保存业务数据或密钥。
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 固定使用系统自带 Windows PowerShell，避免 VNC 会话中的别名或 PATH 差异。
$PowerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$BootstrapUrl = "https://raw.githubusercontent.com/connor-6162/logistics-spare-parts-platform/main/spare_parts_platform_v5/deployment/windows/bootstrap_remote.ps1"
$CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$CurrentPrincipal = New-Object Security.Principal.WindowsPrincipal($CurrentIdentity)
$IsAdministrator = $CurrentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# 安装计划任务、Python 和防护目录需要管理员权限；普通会话自动触发 UAC。
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

# 下载内容放入系统临时目录，安装结束后不作为生产运行目录使用。
$WorkRoot = Join-Path $env:TEMP "spare-parts-platform-bootstrap"
$ArchivePath = Join-Path $WorkRoot "source.zip"
$ExtractRoot = Join-Path $WorkRoot "source"
$RepositoryArchive = "https://github.com/connor-6162/logistics-spare-parts-platform/archive/refs/heads/main.zip"

if (Test-Path -LiteralPath $WorkRoot) {
    Remove-Item -LiteralPath $WorkRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $ExtractRoot -Force | Out-Null

# GitHub archive 不依赖服务器预装 Git，适合最小化 Windows Server 环境。
Write-Host "Downloading application source..." -ForegroundColor Cyan
Invoke-WebRequest -Uri $RepositoryArchive -OutFile $ArchivePath -UseBasicParsing
if (Get-Command Expand-Archive -ErrorAction SilentlyContinue) {
    Expand-Archive -LiteralPath $ArchivePath -DestinationPath $ExtractRoot -Force
} else {
    # Windows Server 2012 R2 的 PowerShell 4.0 没有 Expand-Archive，改用 .NET ZIP。
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ArchivePath, $ExtractRoot)
}

# 校验正式安装脚本存在，防止仓库结构变化时误执行空目录。
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
