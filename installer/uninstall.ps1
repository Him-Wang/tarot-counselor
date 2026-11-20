$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# 定位安装目录：优先安装目录里的 .install-info.json，否则用默认位置
$infoPath = Join-Path $root '.install-info.json'
if (-not (Test-Path $infoPath)) { $infoPath = Join-Path $env:LOCALAPPDATA 'Olivia\.install-info.json' }
$info = $null
if (Test-Path $infoPath) { $info = Get-Content $infoPath -Raw | ConvertFrom-Json }
$target = if ($info) { $info.target } else { Join-Path $env:LOCALAPPDATA 'Olivia' }

Write-Host ('卸载目标：' + $target) -ForegroundColor Cyan

# 删除快捷方式（含开机自启）
$links = if ($info -and $info.links) { $info.links } else { @() }
foreach ($lnk in $links) { if (Test-Path $lnk) { Remove-Item $lnk -Force } }
foreach ($dir in @(
    ([Environment]::GetFolderPath('Desktop')),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup')
)) {
    if (Test-Path $dir) {
        foreach ($n in @('Olivia 奥莉薇娅.lnk', 'Olivia.lnk')) {
            $p = Join-Path $dir $n
            if (Test-Path $p) { Remove-Item $p -Force }
        }
    }
}
Write-Host '快捷方式与开机自启已移除。' -ForegroundColor Green

# 停止服务（按 PID 精确停止）
$pidFile = Join-Path $target 'agent\olivia.pid'
if (Test-Path $pidFile) {
    $procId = Get-Content $pidFile -Raw
    if ($procId -match '^\d+$') {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        Write-Host ('已停止 Olivia 服务进程 ' + $procId) -ForegroundColor Green
    }
}

# 删除程序目录及其中所有 key / 记忆数据（无需确认，一键卸载）
if (Test-Path $target) {
    Remove-Item -Recurse -Force $target
    Write-Host '已删除程序目录与全部数据。' -ForegroundColor Green
}
Write-Host '卸载完成。' -ForegroundColor Cyan
