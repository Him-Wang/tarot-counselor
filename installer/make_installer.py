"""
make_installer.py — 生成一个自包含的 Windows 安装包（zip）。

运行： python installer/make_installer.py
产物： installer/dist/Olivia-agent-setup.zip

两种方式部署（都会 "双击 installer/install.bat 全自动完成，零提问"）：
  A. 直接双击本仓库的 installer/install.bat —— 从仓库根拷文件安装（开发/本机用）。
  B. 生成本 zip 发给别人 —— 解压后双击里面的 install.bat（内含 payload，脱离仓库也能装）。

设计原则：
  - 只用 Python 标准库；不写死任何本机路径。
  - install/uninstall 脚本以同目录文件为唯一真相源，本脚本只负责打包与生成说明。
  - 打包时排除隐私数据（agent/config.json、agent/data/、__pycache__）。
"""

import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
OUT_ZIP = os.path.join(DIST, "Olivia-agent-setup.zip")

SCRIPTS = ["install.bat", "uninstall.bat", "install.ps1", "uninstall.ps1"]


def _should_skip(rel):
    low = rel.replace("\\", "/").lower()
    parts = low.split("/")
    if "__pycache__" in parts:
        return True
    if low.endswith((".pyc", ".db", ".db-wal", ".db-shm", ".pid")):
        return True
    if "agent/config.json" in low:
        return True
    if "/data/" in low or low.startswith("data/"):
        return True
    if ".git" in parts:
        return True
    return False


def _add_tree(zf, src_dir, arc_prefix):
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


def _read_script(name):
    with open(os.path.join(HERE, name), "r", encoding="utf-8-sig") as f:
        return f.read().encode("utf-8-sig")


def main():
    # 确认脚本齐全
    missing = [s for s in SCRIPTS if not os.path.exists(os.path.join(HERE, s))]
    if missing:
        print("[错误] 缺少脚本文件：%s" % ", ".join(missing))
        return 1

    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # 安装/卸载脚本：直接来自 installer 目录（唯一真相源）
        for s in SCRIPTS:
            zf.writestr(s, _read_script(s))
        zf.writestr("使用说明.txt", (
            "Olivia 奥莉薇娅 · 本地 Agent 一键安装包\r\n"
            "========================================\r\n\r\n"
            "【安装】解压整个 zip 到一个文件夹，双击 install.bat —— 全自动，无需任何操作。\r\n"
            "  会自动：检测 Python → 装到 %LOCALAPPDATA%\\Olivia → 建桌面/开始菜单快捷方式\r\n"
            "  → 设开机自启 → 启动服务并打开浏览器 http://127.0.0.1:8765 。\r\n"
            "  首次使用点右上角「设置」填入你自己的 API key（DeepSeek 等）。\r\n\r\n"
            "【卸载】双击安装目录里的 uninstall.bat —— 全自动删除快捷方式、自启、服务与数据。\r\n"
            "  也可双击本 zip 里的 uninstall.bat。\r\n\r\n"
            "前提：电脑需装 Python 3（https://www.python.org ，安装时勾选 Add to PATH）。\r\n"
            "隐私：config.json（API key）与各 .db（记忆/知识库）不会被打包，也不会上传。\r\n"
        ).encode("utf-8-sig"))

        count = 0
        count += _add_tree(zf, os.path.join(REPO, "agent"), "payload/agent")
        count += _add_tree(zf, os.path.join(REPO, "knowledge"), "payload/knowledge")
        count += _add_tree(zf, os.path.join(REPO, "prompts"), "payload/prompts")
        for name in ("README.md", "LICENSE"):
            p = os.path.join(REPO, name)
            if os.path.exists(p):
                zf.write(p, "payload/" + name)
                count += 1

    size_kb = os.path.getsize(OUT_ZIP) / 1024
    print("安装包已生成：%s" % OUT_ZIP)
    print("包含 %d 个数据文件，压缩包大小 %.1f KB" % (count, size_kb))
    print("发给别人：解压后双击 install.bat 即可，全程零操作。")
    print("本机安装：直接双击本目录的 install.bat 即可。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
