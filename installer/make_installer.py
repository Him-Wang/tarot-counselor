"""
make_installer.py — 生成一个自包含的 Windows 安装包（zip）。

运行： python installer/make_installer.py
产物： installer/dist/Olivia-agent-setup.zip

压缩包解开后是一个"安装源"目录：
    install.bat     双击安装：检测 Python → 选目标目录 → 复制文件 → 建快捷方式 → 可选开机自启
    uninstall.bat   双击卸载：删除快捷方式/开机自启和目标目录
    payload/        agent/ + knowledge/ + prompts/ + README.md（保持兄弟目录关系）

设计原则：
  - 只用 Python 标准库；不写死任何本机路径。
  - 安装、卸载、快捷方式的 PowerShell 逻辑内嵌在本文件，作为单一真相源。
  - 打包时排除隐私数据（agent/config.json、agent/data/、__pycache__）。
"""

import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
OUT_ZIP = os.path.join(DIST, "Olivia-agent-setup.zip")

# ---- 安装脚本（bat 引导 + PowerShell 干实事）--------------------------------

INSTALL_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   Olivia 奥莉薇娅 - 本地 Agent 安装
echo ============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo [失败] 安装未完成，请查看上面的错误信息。
  pause
)
endlocal
"""

UNINSTALL_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================
echo   Olivia 奥莉薇娅 - 卸载
echo ============================================
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1"
pause
endlocal
"""

INSTALL_PS1 = r"""$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $root 'payload'
$defaultDir = Join-Path $env:LOCALAPPDATA 'Olivia'

Write-Host '检测到安装源：' $payload -ForegroundColor Cyan

# 1) 检测 Python 3
$py = $null
foreach ($cand in @('py -3', 'python', 'python3')) {
    try {
        $name = ($cand -split ' ')[0]
        $args = if ($cand -like '* -3') { @('-3','--version') } else { @('--version') }
        $v = & $name @args 2>&1 | Out-String
        if ($v -match 'Python 3') {
            $py = $name
            if ($cand -like '* -3') { $pyArgs = '-3 ' } else { $pyArgs = '' }
            Write-Host ('Python OK: ' + $v.Trim()) -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $py) {
    Write-Host '[错误] 未找到 Python 3。请先安装 https://www.python.org/downloads/ 并勾选 Add to PATH。' -ForegroundColor Red
    exit 1
}

# 2) 选择安装目录
$answer = Read-Host ('安装到哪儿？直接回车使用默认：' + $defaultDir)
$target = if ([string]::IsNullOrWhiteSpace($answer)) { $defaultDir } else { $answer.Trim('"') }
Write-Host ('安装目标：' + $target) -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $target | Out-Null

# 3) 复制文件（保留 agent / knowledge / prompts 的兄弟结构）
Copy-Item -Path (Join-Path $payload '*') -Destination $target -Recurse -Force

# 同时把卸载脚本放进安装目录，方便日后从安装位置卸载
Copy-Item -Path (Join-Path $root 'uninstall.bat') -Destination $target -Force
Copy-Item -Path (Join-Path $root 'uninstall.ps1') -Destination $target -Force

# 4) 写启动器（相对定位，换机可用）
$launcher = Join-Path $target 'Olivia.bat'
@"
@echo off
chcp 65001 >nul
cd /d "%~dp0agent"
where python >nul 2>nul
if errorlevel 1 (
  py -3 server.py
) else (
  python server.py
)
pause
"@ | Set-Content -Path $launcher -Encoding UTF8

# 5) 快捷方式：桌面 + 开始菜单
$ws = New-Object -ComObject WScript.Shell
$linkTargets = @()
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
        $linkTargets += $lnk
        Write-Host ('快捷方式：' + $lnk) -ForegroundColor Green
    }
}
# 记录安装位置供卸载使用
$meta = Join-Path $target '.install-info.json'
@{ target = $target; links = $linkTargets; created = (Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -Path $meta -Encoding UTF8

# 6) 开机自启（可选）
$auto = Read-Host '是否开机自动启动 Olivia？（y/N）'
if ($auto -match '^[yY]') {
    $startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
    $sc = $ws.CreateShortcut((Join-Path $startup 'Olivia.lnk'))
    $sc.TargetPath = $launcher
    $sc.WorkingDirectory = $target
    $sc.Save()
    Write-Host '已加入开机自启。' -ForegroundColor Green
}

# 7) 是否立即启动
$run = Read-Host '现在就启动 Olivia 吗？（y/N）'
if ($run -match '^[yY]') {
    Start-Process -FilePath $launcher
    Write-Host '已启动。浏览器打开 http://127.0.0.1:8765' -ForegroundColor Green
}

Write-Host ''
Write-Host '安装完成！以后双击桌面「Olivia 奥莉薇娅」即可使用。' -ForegroundColor Cyan
Write-Host '首次使用：打开后点右上角「设置」填入你自己的 API key（DeepSeek 等）。' -ForegroundColor Cyan
"""

UNINSTALL_PS1 = r"""$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
# 安装后目录里的 .install-info.json 记录真实位置；若从安装源直接卸载则询问
$infoPath = Join-Path $root '.install-info.json'
if (Test-Path $infoPath) {
    $info = Get-Content $infoPath -Raw | ConvertFrom-Json
    $target = $info.target
} else {
    $defaultDir = Join-Path $env:LOCALAPPDATA 'Olivia'
    $answer = Read-Host ('要卸载哪个目录？直接回车使用默认：' + $defaultDir)
    $target = if ([string]::IsNullOrWhiteSpace($answer)) { $defaultDir } else { $answer.Trim('"') }
    $infoPath = Join-Path $target '.install-info.json'
    if (Test-Path $infoPath) { $info = Get-Content $infoPath -Raw | ConvertFrom-Json }
}
Write-Host ('卸载目标：' + $target) -ForegroundColor Cyan

# 删除快捷方式
$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
foreach ($dir in @($desktop, $startMenu, $startup)) {
    $lnk = Join-Path $dir 'Olivia 奥莉薇娅.lnk'
    if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host ('已删除 ' + $lnk) }
    $lnk2 = Join-Path $dir 'Olivia.lnk'
    if (Test-Path $lnk2) { Remove-Item $lnk2 -Force; Write-Host ('已删除 ' + $lnk2) }
}

# 停止仍在运行的服务（按 server 写的 PID 文件精确停止，不误杀其它 python）
$pidFile = Join-Path $target 'agent\olivia.pid'
if (Test-Path $pidFile) {
    $procId = Get-Content $pidFile -Raw
    if ($procId -match '^\d+$') {
        Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        Write-Host ('已停止 Olivia 服务进程 ' + $procId) -ForegroundColor Green
    }
}

# 删除目标目录
if (Test-Path $target) {
    $confirm = Read-Host ('确认删除整个目录 ' + $target + '？（y/N）')
    if ($confirm -match '^[yY]') {
        Remove-Item -Recurse -Force $target
        Write-Host '已删除程序目录。' -ForegroundColor Green
    } else {
        Write-Host '已保留程序目录（快捷方式已删）。' -ForegroundColor Yellow
    }
}
Write-Host '卸载完成。你的 API key 与记忆数据随目录一并被删除。' -ForegroundColor Cyan
"""


def _should_skip(rel):
    low = rel.replace("\\", "/").lower()
    parts = low.split("/")
    if "__pycache__" in parts:
        return True
    if low.endswith(".pyc") or low.endswith(".db") or low.endswith(".db-wal") or low.endswith(".db-shm"):
        return True
    # 隐私/运行时文件
    if "agent/config.json" in low:
        return True
    if "/data/" in low or low.startswith("data/"):
        return True
    if ".git" in parts:
        return True
    return False


def _add_tree(zf, src_dir, arc_prefix):
    """把 src_dir 下所有文件加入 zip，保持相对结构，跳过隐私/缓存文件。"""
    if not os.path.isdir(src_dir):
        return 0
    n = 0
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, src_dir)
            if _should_skip(os.path.join(arc_prefix, rel)):
                continue
            zf.write(full, os.path.join(arc_prefix, rel).replace("\\", "/"))
            n += 1
    return n


def main():
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # 安装引导脚本
        zf.writestr("install.bat", INSTALL_BAT.encode("utf-8-sig"))
        zf.writestr("uninstall.bat", UNINSTALL_BAT.encode("utf-8-sig"))
        zf.writestr("install.ps1", INSTALL_PS1.encode("utf-8-sig"))
        zf.writestr("uninstall.ps1", UNINSTALL_PS1.encode("utf-8-sig"))
        zf.writestr("使用说明.txt", (
            "Olivia 奥莉薇娅 · 本地 Agent 安装包\r\n"
            "========================================\r\n\r\n"
            "1) 把整个压缩包解压到一个文件夹（不要只解压单个文件）。\r\n"
            "2) 双击 install.bat，按提示选择安装位置，其余一路回车即可。\r\n"
            "3) 安装完双击桌面「Olivia 奥莉薇娅」打开，浏览器访问 http://127.0.0.1:8765 。\r\n"
            "4) 首次使用点右上角「设置」，填入你自己的 API key（DeepSeek 等）。\r\n\r\n"
            "前提：电脑需装 Python 3（https://www.python.org ，安装时勾选 Add to PATH）。\r\n"
            "卸载：双击安装目录里的 uninstall.bat。\r\n"
            "隐私：config.json（API key）与各 .db（记忆/知识库）不会被打包，也不会上传。\r\n"
        ).encode("utf-8-sig"))

        # payload：保持 agent / knowledge / prompts 兄弟结构
        count = 0
        count += _add_tree(zf, os.path.join(REPO, "agent"), "payload/agent")
        count += _add_tree(zf, os.path.join(REPO, "knowledge"), "payload/knowledge")
        count += _add_tree(zf, os.path.join(REPO, "prompts"), "payload/prompts")

        readme = os.path.join(REPO, "README.md")
        if os.path.exists(readme):
            zf.write(readme, "payload/README.md")
            count += 1
        license_path = os.path.join(REPO, "LICENSE")
        if os.path.exists(license_path):
            zf.write(license_path, "payload/LICENSE")
            count += 1

    size_kb = os.path.getsize(OUT_ZIP) / 1024
    print("安装包已生成：%s" % OUT_ZIP)
    print("包含 %d 个数据文件，压缩包大小 %.1f KB" % (count, size_kb))
    print("解压后双击 install.bat 即可安装。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
