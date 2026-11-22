# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""secret_store.py — 把 API Key 加密后再落盘（stdlib only）。

Windows 走 DPAPI（CryptProtectData），密文只能被当前 Windows 用户解开；
其他平台没有等价的系统钥匙串时退化为 base64 包装，并在文件权限上收紧。
返回值带前缀，旧配置里的明文 key 会在下一次保存时自动迁移。
"""

import base64
import os
import sys

DPAPI_PREFIX = "dpapi:"
B64_PREFIX = "b64:"


class DATA_BLOB(object):
    pass


def _windows_dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD),
                    ("pbData", ctypes.POINTER(ctypes.c_byte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    buf = ctypes.create_string_buffer(bytes(data), len(data))
    blob_in = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    blob_out = BLOB()
    if protect:
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("DPAPI call failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(value):
    """Encrypt a secret for storage. Returns '' for an empty value."""
    raw = (value or "").encode("utf-8")
    if not raw:
        return ""
    if sys.platform == "win32":
        try:
            return DPAPI_PREFIX + base64.b64encode(_windows_dpapi(raw, True)).decode("ascii")
        except Exception:
            pass
    return B64_PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect(token):
    """Decrypt a stored secret. Returns '' when the token is unreadable."""
    token = (token or "").strip()
    if not token:
        return ""
    try:
        if token.startswith(DPAPI_PREFIX):
            return _windows_dpapi(base64.b64decode(token[len(DPAPI_PREFIX):]), False).decode("utf-8")
        if token.startswith(B64_PREFIX):
            return base64.b64decode(token[len(B64_PREFIX):]).decode("utf-8")
    except Exception:
        return ""
    # Legacy plaintext value: return as-is so the caller can migrate it.
    return token


def harden(path):
    """Best-effort permission tightening (POSIX); no-op on Windows."""
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
