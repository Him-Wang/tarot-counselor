# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""auth.py — 局域网模式的配对码鉴权（stdlib only）。

默认 127.0.0.1 不启用（只有本机能访问）。一旦 AGENT_HOST 指向局域网，
启动时读取环境变量 OLIVIA_TOKEN，或在 agent/data/access_token 生成一个
8 位配对码，并打印到控制台。浏览器/安卓首次访问需要输入一次，之后靠
HttpOnly Cookie 记住；命令行可用 X-Olivia-Token 头。
"""

import hmac
import os
import re
import secrets
import threading
import time

LOOPBACK = ("127.0.0.1", "localhost", "::1", "")
COOKIE_NAME = "olivia_token"
TOKEN_FILE = "access_token"
_CODE_RE = re.compile(r"[^0-9a-z]")


def enabled(host):
    """LAN exposure requires pairing; loopback stays frictionless."""
    return str(host or "").strip().lower() not in LOOPBACK


def _paths(base_dir):
    return os.path.join(base_dir, "data", TOKEN_FILE)


def load_or_create(base_dir):
    env = (os.environ.get("OLIVIA_TOKEN") or "").strip()
    if env:
        return env
    path = _paths(base_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            existing = _CODE_RE.sub("", f.read().strip().lower())
        if len(existing) >= 8:
            return existing
    except Exception:
        pass
    token = secrets.token_hex(4)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(token)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
    except Exception:
        pass
    return token


def normalize(code):
    return _CODE_RE.sub("", str(code or "").lower())


def pretty(code):
    code = normalize(code)
    # 只有自动生成的 8 位码才做 xxxx-xxxx 分组；自定义长 token 原样显示。
    return (code[:4] + "-" + code[4:]) if len(code) == 8 else code


def verify(expected, supplied):
    a, b = normalize(expected), normalize(supplied)
    return bool(a) and len(b) >= 8 and hmac.compare_digest(a, b)


class Throttle(object):
    """Slow down brute force on the pairing endpoint."""

    def __init__(self, limit=8, window=600):
        self.limit = limit
        self.window = window
        self._fails = {}
        self._lock = threading.Lock()

    def blocked(self, ip):
        now = time.time()
        with self._lock:
            hits = [t for t in self._fails.get(ip, []) if now - t < self.window]
            self._fails[ip] = hits
            return len(hits) >= self.limit

    def fail(self, ip):
        with self._lock:
            self._fails.setdefault(ip, []).append(time.time())

    def clear(self, ip):
        with self._lock:
            self._fails.pop(ip, None)
