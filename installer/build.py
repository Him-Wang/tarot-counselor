"""
build.py — 构建两个原生 exe（纯 csc.exe，零第三方依赖）：
  Olivia.exe      —— 安装后的启动器：后台起服务 + 打开浏览器
  Olivia-setup.exe—— 单文件安装器：内嵌 payload.zip 与 Olivia.exe，解压即装

用法： python installer/build.py
产物： installer/dist/Olivia.exe、installer/dist/Olivia-setup.exe
"""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DIST = os.path.join(HERE, "dist")
FX = r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
CSC = os.path.join(FX, "csc.exe")


def run(cmd):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = r.stdout.decode("utf-8", "replace")
    print(out.strip())
    if r.returncode != 0:
        raise RuntimeError("compile failed (exit %d)" % r.returncode)


def build_launcher():
    out = os.path.join(DIST, "Olivia.exe")
    run([CSC, "/nologo", "/target:winexe", "/optimize+",
         "/out:" + out,
         "/r:" + os.path.join(FX, "System.dll"),
         "/r:" + os.path.join(FX, "System.Windows.Forms.dll"),
         os.path.join(HERE, "Launcher.cs")])
    return out


def make_payload():
    path = os.path.join(DIST, "payload.zip")
    if os.path.exists(path):
        os.remove(path)

    def skip(rel):
        low = rel.replace("\\", "/").lower()
        parts = low.split("/")
        if "__pycache__" in parts:
            return True
        if low.endswith((".pyc", ".db", ".db-wal", ".db-shm", ".pid", ".json")):
            return True
        if "agent/config.json" in low or "/data/" in low:
            return True
        if ".git" in parts:
            return True
        return False

    n = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for d in ("agent", "knowledge", "prompts", "skills"):
            base = os.path.join(REPO, d)
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for fn in files:
                    full = os.path.join(root, fn)
                    arc = os.path.join(d, os.path.relpath(full, base)).replace("\\", "/")
                    if skip(arc):
                        continue
                    zf.write(full, arc)
                    n += 1
        for name in ("README.md", "LICENSE", "COMMERCIAL.md"):
            p = os.path.join(REPO, name)
            if os.path.exists(p):
                zf.write(p, name)
                n += 1
    print("payload: %d files, %.1f MB" % (n, os.path.getsize(path) / 1048576.0))
    return path


def build_setup(payload, launcher):
    out = os.path.join(DIST, "Olivia-setup.exe")
    run([CSC, "/nologo", "/target:winexe", "/optimize+",
         "/out:" + out,
         "/resource:" + payload + ",payload.zip",
         "/resource:" + launcher + ",launcher.exe",
         "/r:" + os.path.join(FX, "System.dll"),
         "/r:" + os.path.join(FX, "System.Core.dll"),
         "/r:" + os.path.join(FX, "System.IO.Compression.dll"),
         "/r:" + os.path.join(FX, "System.IO.Compression.FileSystem.dll"),
         "/r:" + os.path.join(FX, "System.Windows.Forms.dll"),
         os.path.join(HERE, "Setup.cs")])
    return out


def main():
    if not os.path.exists(CSC):
        print("[错误] 找不到 csc.exe：%s" % CSC)
        return 1
    os.makedirs(DIST, exist_ok=True)
    launcher = build_launcher()
    payload = make_payload()
    setup = build_setup(payload, launcher)
    print("构建完成：")
    print("  " + launcher)
    print("  " + setup)
    return 0


if __name__ == "__main__":
    sys.exit(main())
