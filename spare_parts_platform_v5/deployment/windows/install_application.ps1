#Requires -RunAsAdministrator
# Windows 正式安装/更新脚本。
# 主要步骤：选择磁盘→复制应用→安装 Python/虚拟环境→创建或保留生产配置→
# 注册开机计划任务→启动应用→轮询 /healthz 验证部署成功。
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 源目录来自下载仓库；应用与数据分离，更新代码时不会覆盖数据库。
$SourceRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$AppRoot = "D:\SparePartsPlatform"
$DataRoot = "D:\SparePartsData"

# 优先使用数据盘 D:；没有数据盘的服务器自动回退到系统盘 C:。
if (-not (Test-Path -LiteralPath "D:\")) {
    $AppRoot = "C:\SparePartsPlatform"
    $DataRoot = "C:\SparePartsData"
}

New-Item -ItemType Directory -Path $AppRoot -Force | Out-Null
New-Item -ItemType Directory -Path $DataRoot -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $DataRoot "logs") -Force | Out-Null

# robocopy 只同步程序，明确排除数据库、生产密钥和虚拟环境。
$RoboCopyArgs = @(
    $SourceRoot,
    $AppRoot,
    "/E",
    "/R:2",
    "/W:2",
    "/XF", "spare_parts.db", "production.env.ps1",
    "/XD", ".venv", "__pycache__", ".pytest_cache"
)
& robocopy @RoboCopyArgs | Out-Host
if ($LASTEXITCODE -ge 8) {
    throw "Copying the application failed with robocopy exit code $LASTEXITCODE."
}

# 先复用已安装的 Python；找不到时静默安装经过固定版本的 Python 3.11。
$PythonExe = $null
$PythonCandidates = @(
    "C:\Python311\python.exe",
    "C:\Program Files\Python311\python.exe",
    "C:\Program Files\Python312\python.exe"
)
foreach ($Candidate in $PythonCandidates) {
    if (Test-Path -LiteralPath $Candidate) {
        $PythonExe = $Candidate
        break
    }
}

if (-not $PythonExe) {
    $Installer = Join-Path $env:TEMP "python-3.11.9-amd64.exe"
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" -OutFile $Installer
    $Process = Start-Process -FilePath $Installer -ArgumentList "/quiet InstallAllUsers=1 TargetDir=C:\Python311 Include_launcher=1 Include_pip=1 PrependPath=1" -Wait -PassThru
    if ($Process.ExitCode -ne 0) {
        throw "Python installation failed with exit code $($Process.ExitCode)."
    }
    $PythonExe = "C:\Python311\python.exe"
}

# 独立虚拟环境隔离系统 Python，requirements.txt 固定应用依赖。
$VenvPython = Join-Path $AppRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) {
    & $PythonExe -m venv (Join-Path $AppRoot ".venv")
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r (Join-Path $AppRoot "requirements.txt")

# 首次安装生成随机 SECRET_KEY；更新时绝不覆盖现有数据库地址、令牌和密钥。
$ConfigPath = Join-Path $AppRoot "deployment\windows\production.env.ps1"
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    $SecretBytes = New-Object byte[] 48
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($SecretBytes)
    $SecretKey = [Convert]::ToBase64String($SecretBytes)
    $DatabasePath = (Join-Path $DataRoot "spare_parts.db").Replace("\", "/")
    $Config = @"
`$env:SECRET_KEY = '$SecretKey'
`$env:DATABASE_URL = 'sqlite:///$DatabasePath'
`$env:DEMO_MODE = 'True'
`$env:SESSION_COOKIE_SECURE = 'True'
`$env:PREFERRED_URL_SCHEME = 'https'
`$env:PUBLIC_BASE_URL = 'https://lwqgraduationproject.cn'
`$env:HOST = '127.0.0.1'
`$env:PORT = '5055'
`$env:WAITRESS_THREADS = '8'
`$env:TRUSTED_PROXY = '127.0.0.1'
`$env:AI_PROVIDER = 'cloudflare'
`$env:CLOUDFLARE_ACCOUNT_ID = ''
`$env:CLOUDFLARE_API_TOKEN = ''
`$env:CLOUDFLARE_AI_MODEL = '@cf/meta/llama-3.1-8b-instruct-fast'
`$env:AI_TIMEOUT_SECONDS = '12'
"@
    Set-Content -LiteralPath $ConfigPath -Value $Config -Encoding UTF8
} else {
    # 更新只迁移已停用的模型名称，保留生产 API 令牌和会话密钥。
    $ExistingConfig = Get-Content -LiteralPath $ConfigPath -Raw
    $ExistingConfig = $ExistingConfig.Replace(
        '@cf/meta/llama-3.1-8b-instruct''',
        '@cf/meta/llama-3.1-8b-instruct-fast'''
    )
    Set-Content -LiteralPath $ConfigPath -Value $ExistingConfig -Encoding UTF8
    Write-Host "Existing production configuration and secrets were preserved." -ForegroundColor Cyan
}

# 停止旧计划任务和属于本应用的残留监听进程，避免端口 5055/80 冲突。
$StartScript = Join-Path $AppRoot "deployment\windows\start_server.ps1"
$PowerShellExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$ExistingTask = Get-ScheduledTask -TaskName "SparePartsPlatform" -ErrorAction SilentlyContinue
if ($ExistingTask) {
    Stop-ScheduledTask -TaskName "SparePartsPlatform" -ErrorAction SilentlyContinue
}

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

# SYSTEM 计划任务随 Windows 启动，并在异常退出后最多自动重试五次。
$Action = New-ScheduledTaskAction -Execute $PowerShellExe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$StartScript`""
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "SparePartsPlatform" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName "SparePartsPlatform"

# 最长等待 90 秒；只有本机健康接口明确返回 status=ok 才判定安装成功。
$Ready = $false
for ($Attempt = 1; $Attempt -le 90; $Attempt++) {
    Start-Sleep -Seconds 1
    try {
        $Health = Invoke-RestMethod -Uri "http://127.0.0.1:5055/healthz" -TimeoutSec 2
        if ($Health.status -eq "ok") {
            $Ready = $true
            break
        }
    } catch {
    }
}

if (-not $Ready) {
    Get-ScheduledTaskInfo -TaskName "SparePartsPlatform" -ErrorAction SilentlyContinue |
        Format-List LastRunTime, LastTaskResult | Out-Host
    throw "The application did not become healthy. Check $DataRoot\logs\application.log"
}

Write-Host "Application installed successfully." -ForegroundColor Green
Write-Host "Local health check: http://127.0.0.1:5055/healthz"
Write-Host "Application root: $AppRoot"
Write-Host "Data root: $DataRoot"
