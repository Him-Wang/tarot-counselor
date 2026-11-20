$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path   # installer 目录

# ---------- 1) 智能定位安装源：优先同目录 payload（zip 分发），否则用仓库根 ----------
$payload = Join-Path $root 'payload'
$src = $null
if (Test-Path (Join-Path $payload 'agent\server.py')) {
    $src = $payload
} else {
    $repoRoot = Split-Path -Parent $root
    if (Test-Path (Join-Path $repoRoot 'agent\server.py')) { $src = $repoRoot }
}
if (-not $src) {
    Write-Host '[错误] 找不到安装源（agent\server.py）。请把整个 installer 文件夹与 agent/knowledge/prompts 放在一起，或使用完整安装包。' -ForegroundColor Red
    exit 1
}
Write-Host ('安装源：' + $src) -ForegroundColor DarkGray

# ---------- 2) 检测 Python 3，并解析出真实 python.exe / pythonw.exe ----------
$pyExe = $null
foreach ($cand in @('py -3', 'python', 'python3')) {
    $name = ($cand -split ' ')[0]
    try {
        if ($name -eq 'py') { $ver = & py -3 --version 2>&1 | Out-String }
        else { $ver = & $name --version 2>&1 | Out-String }
        if ($ver -match 'Python 3') {
            if ($name -eq 'py') { $pyExe = (& py -3 -c "import sys;print(sys.executable)" 2>&1).Trim() }
            else { $pyExe = (Get-Command $name -ErrorAction Stop).Source }
            break
        }
    } catch {}
}
if (-not $pyExe -or -not (Test-Path $pyExe)) {
    Write-Host '[错误] 未找到 Python 3。请先安装 https://www.python.org/downloads/ 并勾选 Add Python to PATH。' -ForegroundColor Red
    exit 1
}
$pyDir = Split-Path -Parent $pyExe
$pythonw = Join-Path $pyDir 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $pyExe }
Write-Host ('Python OK: ' + $pyExe) -ForegroundColor Green

# ---------- 3) 安装目录（问，回车用默认）；若已装过先停旧服务 ----------
$defaultDir = Join-Path $env:LOCALAPPDATA 'Olivia'
$answer = Read-Host ('安装到哪儿？直接回车用默认：' + $defaultDir)
$target = if ([string]::IsNullOrWhiteSpace($answer)) { $defaultDir } else { $answer.Trim('"') }
$oldPid = Join-Path $target 'agent\olivia.pid'
if (Test-Path $oldPid) {
    $old = Get-Content $oldPid -Raw
    if ($old -match '^\d+$') { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue }
}
New-Item -ItemType Directory -Force -Path $target | Out-Null
Write-Host ('安装到：' + $target) -ForegroundColor Cyan

# ---------- 4) 复制文件（agent / knowledge / prompts 保持兄弟结构）----------
foreach ($d in @('agent', 'knowledge', 'prompts')) {
    $s = Join-Path $src $d
    if (Test-Path $s) { Copy-Item -Path $s -Destination $target -Recurse -Force }
}
foreach ($f in @('README.md', 'LICENSE')) {
    $s = Join-Path $src $f
    if (Test-Path $s) { Copy-Item -Path $s -Destination $target -Force }
}
# 隐私清理：绝不携带 key / 记忆 / 缓存 / 旧 pid
Remove-Item (Join-Path $target 'agent\config.json') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $target 'agent\data') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $target 'agent\olivia.pid') -Force -ErrorAction SilentlyContinue
Get-ChildItem $target -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
# 卸载脚本随安装落位，方便日后从安装目录卸载
foreach ($f in @('uninstall.bat', 'uninstall.ps1')) {
    $s = Join-Path $root $f
    if (Test-Path $s) { Copy-Item -Path $s -Destination $target -Force }
}

# ---------- 5) 启动器：双击即后台启动 + 打开浏览器 ----------
$launcher = Join-Path $target 'Olivia.bat'
@"
@echo off
chcp 65001 >nul
cd /d "%~dp0agent"
start "" "$pythonw" "%~dp0agent\server.py"
timeout /t 2 >nul
start "" http://127.0.0.1:8765
"@ | Set-Content -Path $launcher -Encoding UTF8

# ---------- 6) 快捷方式：桌面 + 开始菜单 ----------
$ws = New-Object -ComObject WScript.Shell
$links = @()
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
foreach ($dir in @($desktop, $startMenu)) {
    if (Test-Path $dir) {
        $lnk = Join-Path $dir 'Olivia 奥莉薇娅.lnk'
        $sc = $ws.CreateShortcut($lnk)
        $sc.TargetPath = $launcher
        $sc.WorkingDirectory = $target
        $sc.Description = 'Olivia 塔罗咨询师 · 本地 Agent'
        $sc.Save()
        $links += $lnk
    }
}

# ---------- 7) 开机自启（问，默认否；指向 pythonw，无黑窗口）----------
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
$auto = Read-Host '是否开机自动启动？（y/N，直接回车=否）'
if ($auto -match '^[yY]' -and (Test-Path $startup)) {
    $sc = $ws.CreateShortcut((Join-Path $startup 'Olivia.lnk'))
    $sc.TargetPath = $pythonw
    $sc.Arguments = '"' + (Join-Path $target 'agent\server.py') + '"'
    $sc.WorkingDirectory = (Join-Path $target 'agent')
    $sc.Description = 'Olivia Agent 开机自启'
    $sc.Save()
    $links += (Join-Path $startup 'Olivia.lnk')
    Write-Host '已加入开机自启。' -ForegroundColor Green
}

# ---------- 8) 记录安装信息，供卸载使用 ----------
@{
    target  = $target
    links   = $links
    pyexe   = $pyExe
    pythonw = $pythonw
    created = (Get-Date).ToString('o')
} | ConvertTo-Json | Set-Content -Path (Join-Path $target '.install-info.json') -Encoding UTF8

# ---------- 9) 立即启动（问，默认否）+ 打开浏览器（OLIVIA_NO_LAUNCH=1 仅供自动化验证）----------
$run = Read-Host '是否立即启动并打开浏览器？（y/N，直接回车=否）'
$runYes = $run -match '^[yY]'
if ($runYes -and $env:OLIVIA_NO_LAUNCH -ne '1') {
    Start-Process -FilePath $pythonw -ArgumentList ('"' + (Join-Path $target 'agent\server.py') + '"') -WorkingDirectory (Join-Path $target 'agent') -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Start-Process 'http://127.0.0.1:8765'
}

Write-Host ''
Write-Host '安装完成！桌面/开始菜单快捷方式已建好。' -ForegroundColor Cyan
if ($auto -match '^[yY]') { Write-Host '开机自启已设置。' -ForegroundColor Cyan }
if ($runYes) { Write-Host '服务已启动，浏览器已打开 http://127.0.0.1:8765 。' -ForegroundColor Cyan }
else { Write-Host '以后双击桌面「Olivia 奥莉薇娅」即可启动。' -ForegroundColor Cyan }
Write-Host '首次使用：点右上角「设置」填入你自己的 API key（DeepSeek 等）。' -ForegroundColor Cyan
