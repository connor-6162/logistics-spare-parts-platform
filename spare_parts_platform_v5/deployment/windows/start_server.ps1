# 计划任务实际执行的启动脚本。
# 它加载生产环境变量，校验虚拟环境，然后以前台等待方式启动 serve.py；
# Waitress 退出码会原样返回给计划任务，便于 Windows 判断是否需要重启。
$ErrorActionPreference = "Stop"

# 根据脚本自身位置推导应用目录，避免写死部署盘符。
$AppRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ConfigPath = Join-Path $PSScriptRoot "production.env.ps1"
$DataRoot = if (Test-Path -LiteralPath "D:\") { "D:\SparePartsData" } else { "C:\SparePartsData" }
$LogRoot = Join-Path $DataRoot "logs"

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Missing production configuration: $ConfigPath"
}

# 点加载 production.env.ps1，把数据库、域名、AI 和 Waitress 参数注入当前进程。
. $ConfigPath
New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null

$PythonExe = Join-Path $AppRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

Set-Location -LiteralPath $AppRoot
$ServerScript = Join-Path $AppRoot "serve.py"
# -Wait 保持计划任务存活；日志目录由部署层统一准备。
$Process = Start-Process `
    -FilePath $PythonExe `
    -ArgumentList $ServerScript `
    -WorkingDirectory $AppRoot `
    -Wait `
    -PassThru

exit $Process.ExitCode
