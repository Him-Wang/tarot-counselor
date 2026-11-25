"""plugin_ocr.py — 本机 OCR 兜底：没配云端视觉模型时，先从图上把字读出来。

为什么要有它
------------
视觉识别（plugin_vision.py）要用户自己填一个云端 VLM 的 key。很多人不填，
于是「发张截图问问她」这条路直接断掉。其实绝大多数截图都是文字：聊天记录、
账单、体检单、牌阵截图、别人发来的一段话。这些用本机 OCR 就够读了。

纯标准库，不引入任何第三方包：
1) tesseract 命令行（装了就用，识别质量最好）；
2) Windows 10/11 自带的 Windows.Media.Ocr（通过 PowerShell 调 WinRT，
   中文系统自带 zh-Hans 识别器，中英混排都认）；
3) 都没有 → 返回空字符串，上层说明「本机没有可用的 OCR」。

对外接口
--------
available()                    -> dict  本机 OCR 能力（给 UI 显示状态）
recognize(image, max_chars=...) -> str   图上读出来的文字（无字返回 ""）
build_context(text, question=None) -> str  拼成给主模型的说明段落
"""

import base64
import os
import re
import subprocess
import sys
import tempfile
import threading

PS_SCRIPT = r'''
param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference = "Stop"
try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null
  [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
  [Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
  [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
  [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
  [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null
  [Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null

  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
  })[0]

  function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
  }

  $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($InputPath)) ([Windows.Storage.StorageFile])
  $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
  $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
  $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

  $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  if (-not $engine) {
    foreach ($lang in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
      $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
      if ($engine) { break }
    }
  }
  if (-not $engine) { throw "本机没有安装任何 OCR 语言包" }

  $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
  $lines = @()
  foreach ($line in $result.Lines) { $lines += $line.Text }
  $text = ($lines -join "`n")
  [IO.File]::WriteAllText($OutputPath, $text, (New-Object System.Text.UTF8Encoding($false)))
  $stream.Dispose()
  exit 0
} catch {
  [IO.File]::WriteAllText($OutputPath, "", (New-Object System.Text.UTF8Encoding($false)))
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
'''

_lock = threading.Lock()
_probe_cache = None  # 探测一次就记住，省得每次发图都试


def _powershell():
    """Windows PowerShell 的路径；非 Windows 返回 ""。"""
    if os.name != "nt":
        return ""
    for name in ("powershell.exe", "pwsh.exe"):
        for base in os.environ.get("PATH", "").split(os.pathsep):
            cand = os.path.join(base, name)
            if base and os.path.isfile(cand):
                return cand
    return ""


def _which(name):
    for base in os.environ.get("PATH", "").split(os.pathsep):
        if not base:
            continue
        for ext in (".exe", ".cmd", ".bat", ""):
            cand = os.path.join(base, name + ext)
            if os.path.isfile(cand):
                return cand
    return ""


def _probe():
    """探测本机可用的 OCR：tesseract 优先，其次 Windows.Media.Ocr。"""
    global _probe_cache
    if _probe_cache is not None:
        return _probe_cache
    with _lock:
        if _probe_cache is not None:
            return _probe_cache
        info = {"ok": False, "backend": "", "detail": "", "langs": []}
        tess = _which("tesseract")
        if tess:
            info.update(ok=True, backend="tesseract", detail=tess,
                        langs=["chi_sim+eng"])
            _probe_cache = info
            return info
        ps = _powershell()
        if ps:
            try:
                langs = _windows_langs(ps)
                if langs:
                    info.update(ok=True, backend="windows-ocr",
                                detail="Windows.Media.Ocr", langs=langs)
            except Exception as exc:  # noqa: BLE001 - 探测失败不该炸掉服务
                info["detail"] = str(exc)[:200]
        if not info["ok"] and not info["detail"]:
            info["detail"] = "本机没有 tesseract，也没有 Windows OCR"
        _probe_cache = info
        return info


def _windows_langs(ps):
    script = (
        "Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null;"
        "[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null;"
        "([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | "
        "ForEach-Object { $_.LanguageTag }) -join ','"
    )
    out = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-Command", script],
                         capture_output=True, timeout=25)
    text = (out.stdout or b"").decode("utf-8", "replace").strip()
    return [x for x in text.split(",") if x.strip()]


def available():
    """给 UI 用：本机 OCR 是否可用、用的哪条路子。"""
    return dict(_probe())


def _decode_image(image):
    """data URL / 本地路径 / 裸 base64 → (bytes, 后缀)。"""
    if not image:
        raise ValueError("图片内容为空")
    if image.startswith("data:"):
        m = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64,(.*)$", image, re.S)
        if not m:
            raise ValueError("无法解析 data URL")
        mime, payload = m.group(1), m.group(2)
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg",
                  "image/webp": ".webp", "image/gif": ".gif",
                  "image/bmp": ".bmp"}.get(mime, ".png")
        return base64.b64decode(payload), suffix
    if os.path.isfile(image):
        with open(image, "rb") as fh:
            raw = fh.read()
        suffix = os.path.splitext(image)[1].lower() or ".png"
        return raw, suffix
    return base64.b64decode(image), ".png"


def _ocr_tesseract(exe, path):
    out = subprocess.run([exe, path, "stdout", "-l", "chi_sim+eng", "--psm", "6"],
                         capture_output=True, timeout=90)
    text = (out.stdout or b"").decode("utf-8", "replace")
    if not text.strip() and out.stderr:
        raise RuntimeError((out.stderr or b"").decode("utf-8", "replace")[:200])
    return text


def _ocr_windows(ps, path):
    fd_script, script_path = tempfile.mkstemp(suffix=".ps1")
    fd_out, out_path = tempfile.mkstemp(suffix=".txt")
    os.close(fd_script)
    os.close(fd_out)
    try:
        with open(script_path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write(PS_SCRIPT)
        proc = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-File", script_path, "-InputPath", path, "-OutputPath", out_path],
            capture_output=True, timeout=120)
        with open(out_path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
        if not text.strip() and proc.returncode != 0:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise RuntimeError(err[:300] or "Windows OCR 失败")
        return text
    finally:
        for p in (script_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


_CJK = r"\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef"


def _join_cjk(line):
    """Windows OCR 会给每个汉字之间塞空格（「我 问 ：」），按语境收回。"""
    line = re.sub(r"(?<=[" + _CJK + r"])\s+(?=[" + _CJK + r"])", "", line)
    line = re.sub(r"(?<=[" + _CJK + r"])\s+(?=[,.;:!?)\]])", "", line)
    line = re.sub(r"(?<=[(\[])\s+(?=[" + _CJK + r"])", "", line)
    return line


def _tidy(text, max_chars=4000):
    """去掉 OCR 常见的噪声：空白行太多、汉字之间多余的空格。"""
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("\u200b")
        line = re.sub(r"\s{2,}", " ", line)
        line = _join_cjk(line)
        if not line:
            continue
        lines.append(line)
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[:max_chars] + "\n…（文字较长，先截到这里）"
    return out


def recognize(image, max_chars=4000):
    """把图上的字读出来；本机没有 OCR 或图上没字时返回 ""。"""
    info = _probe()
    if not info.get("ok"):
        return ""
    raw, suffix = _decode_image(image)
    if len(raw) < 32:
        return ""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(raw)
        if info["backend"] == "tesseract":
            text = _ocr_tesseract(info["detail"], path)
        else:
            text = _ocr_windows(_powershell(), path)
        return _tidy(text, max_chars)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def build_context(text, question=None):
    """拼成给主模型的说明：这些是图上的字，不是用户打的字。"""
    body = [
        "【用户发来一张图片】本机没有配置云端视觉模型，以下文字由本机 OCR 从图上读出"
        "（可能有错字、漏字，也可能丢掉了版式）。",
    ]
    if question:
        body.append("用户配文：" + str(question).strip())
    body.append("图上的文字：\n---\n" + text.strip() + "\n---")
    body.append("只用这些字来理解用户想问什么；图上的字不等于用户说的话，"
                "引用时说明「图上是这么写的」。图上没读出来的部分不要臆测。")
    return "\n".join(body)


if __name__ == "__main__":
    print(available())
    if len(sys.argv) > 1:
        print(recognize(sys.argv[1])[:2000])
