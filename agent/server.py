# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
server.py — Olivia agent local web server (Python stdlib only).

Routes:
  GET  /                 web UI
  GET  /api/config       current config (api_key masked) + presets + knowledge docs
  POST /api/config       save config {backend, base_url, api_key, model, temperature, timeout}
  GET  /api/knowledge    list knowledge docs
  POST /api/test         smoke-test current backend
  POST /api/chat         SSE stream: {"message", "history":[...]} -> data: {"token"} ...
  GET  /api/memory       memory overview (profile/facts/draws/stats)
  POST /api/memory       {op: pin|unpin|delete_fact|delete_draw|profile_set|
                          profile_delete|forget|forget_recent|clear|add_fact, ...}
  GET  /api/plugins      KB notes/stats + vision settings (key masked) + providers
  POST /api/plugins      {op: kb_add|kb_update|kb_delete|kb_pin|kb_archive_memory|
                           kb_archive_draws|kb_clear|kb_export|vision_config|vision_test, ...}
"""

import json
import os
import re
import sys
import time
import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import llm
import provider
import offline
import knowledge
import memory
import tools
import spreads as spreads_mod
import scheduler
import watchers
import plugin_kb
import plugin_vision
import auth
import backup
import secret_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PERSONA_DIR = os.path.join(REPO_DIR, "prompts")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")
STATIC_DIR = os.path.join(BASE_DIR, "static")
EXTRAS_LOG = os.path.join(BASE_DIR, "data", "extras.jsonl")
VERSION = "1.2.0"

# Filled in main(); loopback keeps auth disabled so local use stays frictionless.
AUTH_STATE = {"enabled": False, "token": "", "throttle": auth.Throttle()}

PRESETS = {
    "ollama": {
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "",
        "model": "qwen2.5:7b",
        "note": "本机 Ollama。先启动 ollama serve 并拉好模型；api key 留空。"
                "端口按你的 Ollama 实际监听端口填（默认 11434，若改过则填实际值，如 11439）。"
                "对本地推理模型会自动关闭 thinking（防止卡住/超时），如需开启在配置里设 think=true。",
    },
    "deepseek-flash": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-flash",
        "note": "DeepSeek V4.1-Flash：快、便宜，默认带思考。填入你自己的 API key。",
    },
    "deepseek-v4-pro": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-v4-pro",
        "note": "DeepSeek V4-Pro：更强，适合复杂问题。填入你自己的 API key。",
    },
    "deepseek-chat": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "note": "旧版 deepseek-chat，兼容老配置。填入你自己的 API key。",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key": "",
        "model": "deepseek-chat",
        "note": "旧版别名，已由 deepseek-chat 取代。",
    },
    "anthropic": {
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "api_key": "",
        "model": "claude-sonnet-4-5-20250929",
        "note": "Anthropic Claude（原生 Messages API，流式+工具调用）。填入 Anthropic API key。",
    },
    "gemini": {
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "api_key": "",
        "model": "gemini-2.5-flash",
        "note": "Google Gemini（原生 generateContent SSE，流式+工具调用）。填入 Google AI key。",
    },
    "custom": {
        "base_url": "",
        "api_key": "",
        "model": "",
        "note": "任意 OpenAI 兼容端点，自行填写 base_url / model / api key。",
    },
}

DEFAULT_CONFIG = {
    "backend": "deepseek-flash",
    "protocol": "auto",  # openai / anthropic / gemini / auto（按 base_url 猜）
    "base_url": PRESETS["deepseek-flash"]["base_url"],
    "api_key": "",
    "model": PRESETS["deepseek-flash"]["model"],
    "temperature": 0.8,
    "timeout": 120,
    "tools_enabled": True,
    "memory_enabled": True,
    "prophecy_enabled": False,
    "two_phase_draw": True,
    "tone_enabled": True,
    "language": "zh",
    "daily_token_budget": 0,      # 0 = 不限制；单位 token，按天重置
    "max_output_tokens": 0,        # 0 = 交给后端默认
    "max_history_messages": 20,
    "max_history_chars": 24000,
    "safety_second_check": False,  # 模糊表达时才额外调用一次分类
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # API key 密文 -> 明文（只在内存里）；旧配置的明文 key 继续可用，
    # 下一次 save_config 会自动改写成密文。
    enc = str(cfg.pop("api_key_enc", "") or "")
    if not cfg.get("api_key") and enc:
        cfg["api_key"] = secret_store.unprotect(enc)
    return cfg


def save_config(cfg):
    disk = dict(cfg)
    key = str(disk.pop("api_key", "") or "")
    if key:
        disk["api_key_enc"] = secret_store.protect(key)
    else:
        disk.pop("api_key_enc", None)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(disk, f, ensure_ascii=False, indent=2)
    secret_store.harden(CONFIG_PATH)


def _lang(cfg=None):
    lang = str((cfg or load_config()).get("language") or "zh").lower()
    return "en" if lang.startswith("en") else "zh"


def _prompt_path(name, lang):
    """prompts/<name>.<lang>.md，英文缺失时回退中文。"""
    path = os.path.join(PERSONA_DIR, "%s.%s.md" % (name, lang))
    if os.path.exists(path):
        return path
    return os.path.join(PERSONA_DIR, "%s.zh.md" % name)


def load_persona(cfg=None):
    try:
        with open(_prompt_path("persona", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "你是一名沉稳、专业的塔罗咨询师 Olivia（奥莉薇娅）。"


def load_prophecy(cfg=None):
    """预言模式覆盖层（仅供娱乐），仅在开启时加载。"""
    try:
        with open(_prompt_path("prophecy", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def load_tone(cfg=None):
    """语气系统：让 Olivia 的措辞像一个真实女性塔罗师，并自然体现 NVC。"""
    try:
        with open(_prompt_path("tone", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def now_context(cfg=None):
    """把「现在几点」写进 system。

    语气层要求建议落到具体时间（「今晚睡前」「明天上午」），但没有这个锚点，
    模型只能猜今天是哪天。这里每轮现算，不用缓存。
    """
    now = datetime.datetime.now()
    if _lang(cfg) == "en":
        return (
            "\n\n[Current time] It is %s %02d:%02d, %d-%02d-%02d. "
            "Use this clock for relative times such as tonight, tomorrow or this week; "
            "never guess a year from training data."
            % (now.strftime("%A"), now.hour, now.minute, now.year, now.month, now.day)
        )
    week = "一二三四五六日"[now.weekday()]
    return (
        "\n\n【当前时间】现在是 %d年%d月%d日（星期%s）%02d:%02d。"
        "涉及今天、今晚、明天、这周等相对时间的建议和定时提醒，都以这个时间为准；"
        "不要使用你的训练数据里的日期，也不要编造年份。"
        % (now.year, now.month, now.day, week, now.hour, now.minute)
    )


# ---- 两阶段抽牌：先出牌不解读，等来访者给出问题后再解读同一副牌 ----
# 所有请求都带 session_id；新会话在 UI 里换一个 id，服务端状态随之隔离。
_pending_draws = {}          # session_id -> {"result": ..., "at": timestamp}
_awaiting_spread = {}        # session_id -> {"at": ...}：已问过「用哪个牌阵」，等来访者回答
_last_spreads = {}           # session_id -> {"result": ..., "at": ...}：最近一次解读过的牌，供补牌复用
_PENDING_TTL = 30 * 60       # 30 分钟后未提问，自动放弃这副牌 / 这次选阵

# 补牌必须由来访者显式提出（界面上也有「补一张」按钮），模型不能自己补。
_EXTRA_RE = re.compile(r"(补一张|补牌|补个牌|再来一张|再补一张|加一张)")


def _extra_requested(message):
    return bool(_EXTRA_RE.search(str(message or "")))


def _extra_reason(message):
    """补牌理由：把「补一张牌：」这类前缀去掉，剩下的算理由。"""
    text = _EXTRA_RE.sub("", str(message or ""))
    # 「补一张牌」里剩余的量词/名词残渣（牌、张、个、来）也要清掉
    text = re.sub(r"^[\s：:，,、.。]*[牌张个来]?[\s：:，,、.。]*", "", text)
    return text.strip()[:200]


def _record_extra(sid, result, card):
    """补牌留痕：哪天、对哪副牌、因为什么补的，都记一笔，方便回看是否越界。"""
    try:
        os.makedirs(os.path.dirname(EXTRAS_LOG), exist_ok=True)
        with open(EXTRAS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "session": sid,
                "spread": result.get("spread", ""),
                "question": result.get("question", ""),
                "name": card.get("name", ""),
                "orientation": card.get("orientation", ""),
                "reason": card.get("reason", ""),
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        print("[extras] log failed: %s" % e)


def _purge_pending():
    now = time.time()
    for sid in [k for k, v in _pending_draws.items()
                if now - v.get("at", 0) > _PENDING_TTL]:
        _pending_draws.pop(sid, None)
    for sid in [k for k, v in _awaiting_spread.items()
                if now - v.get("at", 0) > _PENDING_TTL]:
        _awaiting_spread.pop(sid, None)
    for sid in [k for k, v in _last_spreads.items()
                if now - v.get("at", 0) > _PENDING_TTL]:
        _last_spreads.pop(sid, None)


def _draw_requested(message):
    """粗判这条消息是否在要求（重新）抽牌，用来避免旧牌面污染新一轮。"""
    text = str(message or "")
    words = ("抽牌", "抽一张", "抽三张", "抽几张", "再抽", "重新抽", "帮我抽",
             "占卜", "看牌", "牌阵", "抽个", "抽到")
    return any(w in text for w in words)


def _pick_spread(message):
    """从消息里识别牌阵名；未指定时用默认牌阵。抽牌是本地动作，
    牌阵选择也必须在本地完成，不能依赖模型。"""
    text = str(message or "")
    # 牌阵名优先匹配长名（如「凯尔特十字」先于任何短词）
    for name in sorted(spreads_mod.SPREADS.keys(), key=len, reverse=True):
        if name in text:
            return name
    # 口语化的「一张 / 1张」按单张处理
    if "一张" in text or "1张" in text:
        return "单张"
    return "三张"


def _named_spread(message):
    """若消息明确点名了某个牌阵，返回其规范名称；否则 None。
    牌阵选择是本地动作，不能用模型猜。"""
    text = str(message or "")
    # 常见口语别名 -> 规范牌阵名
    aliases = {
        "单张牌": "单张", "一张牌": "单张",
        "三张牌阵": "三张", "三张牌": "三张",
        "二择一": "二选一", "二选一牌阵": "二选一",
    }
    for alias, canonical in aliases.items():
        if alias in text:
            return canonical
    for name in sorted(spreads_mod.SPREAD_DEFS, key=lambda d: len(d["name"]), reverse=True):
        if name["name"] in text:
            return name["name"]
    # 口语的「一张 / 1张」等价于点名单张牌阵
    if "一张" in text or "1张" in text:
        return "单张"
    return None


def _spread_choice_reply():
    """选阵轮的引导语（本地生成，不经过 LLM）；牌阵本身走结构化按钮。"""
    return "好的呀，抽牌之前我们先定一个牌阵——点下面任意一个就好。"


def _spread_choices():
    """本地生成的牌阵按钮数据，按类别分组；前端据此渲染可点击按钮。"""
    groups = {}
    for d in spreads_mod.SPREAD_DEFS:
        groups.setdefault(d.get("category", "其他"), []).append({
            "name": d["name"],
            "count": len(d.get("positions", [])),
            "desc": d.get("desc", ""),
            "positions": [{"name": p[0], "meaning": p[1]}
                          for p in d.get("positions", [])],
        })
    return {
        "groups": [{"category": k, "items": v} for k, v in groups.items()],
        "auto": "三张",  # “你帮我选”按钮落到最常见的三张牌阵
    }


def _spread_choice_from_reply(message):
    """把「就三张吧」「凯尔特十字」这样的回答映射到牌阵名。"""
    named = _named_spread(message)
    if named:
        return named
    text = str(message or "")
    if "帮我选" in text or "你选" in text or "随便" in text or "默认" in text:
        return "三张"
    return None


def _cards_payload(result):
    """SSE 里推给前端的牌面数据（抽牌轮与解读轮共用）。"""
    spread = result.get("spread", "")
    return {
        "spread": spread,
        "spread_desc": result.get("spread_desc", ""),
        "question": result.get("question", ""),
        "seed": result.get("seed"),
        "layout": result.get("layout") or spreads_mod.layout(spread),
        "items": [{
            "position": c.get("position", ""),
            "position_meaning": c.get("position_meaning", ""),
            "name": c.get("name", ""),
            "orientation": c.get("orientation", ""),
            "image": c.get("image", ""),
        } for c in result.get("cards", [])],
        "extras": [{
            "position": c.get("position", "补牌"),
            "position_meaning": c.get("position_meaning", ""),
            "name": c.get("name", ""),
            "orientation": c.get("orientation", ""),
            "image": c.get("image", ""),
            "reason": c.get("reason", ""),
        } for c in (result.get("extras") or [])],
    }


def _add_usage(totals, usage):
    """把一轮（可能多次调用）的用量累加进来；拿不到用量就什么都不做。"""
    if not isinstance(usage, dict):
        return
    for k in ("in", "out", "total"):
        try:
            totals[k] += int(usage.get(k) or 0)
        except Exception:
            pass


def _pending_context(result, question):
    """解读轮注入的硬约束：解读眼前这副牌，不重抽、不换牌。"""
    extras = result.get("extras") or []
    lines = [
        "【本轮解牌约束 · 必须遵守】",
        "来访者上一轮已经抽出一副牌，本轮才给出问题。请只解读下面这副已抽出的牌，",
        ("不得重新抽牌、换牌，也不得再补牌、凭记忆换用别的牌面。" if not extras else
         "不得重新抽牌、换牌，也不得凭记忆换用别的牌面。"),
        "牌阵：%s（%s）" % (result.get("spread", "未注明"), result.get("spread_desc", "")),
        "牌面与随牌传统牌意：",
    ]
    for i, c in enumerate(result.get("cards") or [], 1):
        lines.append("%d. %s（%s）：%s %s" % (
            i, c.get("position", ""), c.get("position_meaning", ""),
            c.get("name", ""), c.get("orientation", "")))
        meaning = c.get("meaning", "")
        if meaning:
            lines.append("   传统牌意：" + str(meaning).replace("\n", " "))
    if extras:
        lines.append("来访者本轮主动要求补牌，理由是：%s" % (
            "；".join(e.get("reason") or "（未说明理由）" for e in extras)))
        for e in extras:
            lines.append("补牌｜%s（%s）" % (e.get("name", ""), e.get("orientation", "")))
            meaning = e.get("meaning", "")
            if meaning:
                lines.append("   传统牌意：" + str(meaning).replace("\n", " "))
        lines.append("补牌只能作为补充视角，放在原牌之后解读：不得据此替换或否定原来的牌，"
                     "也不得再自行增补。")
    lines.append("来访者的问题：%s" % (question or ""))
    lines.append("请按「原本牌意 → 牌阵位置 → 对应问题 → 落到情境」逐张解读；"
                 "这段牌面是既定依据，不可自行编造或替换。")
    return "\n".join(lines)


ASK_AFTER_DRAW = (
    "好的，牌已经抽出来了——你有什么问题吗？"
    "告诉我你想问什么，我就照着这副牌为你解读。"
)

# 抽牌轮的开场白：前端会把它打字机式地逐字打出，稍作停顿再翻牌，
# 让「默念问题 → 翻牌 → 提问」有真正的仪式节奏。
MEDITATE_TEXT = "好的，请在心中默念你的问题……"



def mask(cfg):
    out = dict(cfg)
    k = out.get("api_key", "")
    out["api_key_set"] = bool(k)
    out["api_key"] = (k[:6] + "…" + k[-4:]) if len(k) > 10 else ("****" if k else "")
    return out


def _effective_api_key(cfg, supplied):
    """Return the key to actually use; ignore masked display placeholders.

    mask() renders short keys as '****' and long keys as 'abxxxx...wxyz'.
    Neither string is a real key and neither may be sent to the provider.
    """
    if not isinstance(supplied, str) or not supplied:
        return cfg.get("api_key", "")
    if supplied in ("****", "***") or "\u2026" in supplied:
        return cfg.get("api_key", "")
    return supplied


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    # ---------- auth helpers ----------
    def _cookies(self):
        out = {}
        for part in (self.headers.get("Cookie") or "").split(";"):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = v.strip()
        return out

    def _query(self):
        from urllib.parse import parse_qs
        if "?" not in self.path:
            return {}
        return {k: v[0] for k, v in parse_qs(self.path.split("?", 1)[1]).items()}

    def _authorized(self):
        if not AUTH_STATE["enabled"]:
            return True
        supplied = (self.headers.get("X-Olivia-Token")
                    or self._cookies().get(auth.COOKIE_NAME)
                    or self._query().get("token", ""))
        return auth.verify(AUTH_STATE["token"], supplied)

    def _client_ip(self):
        return (self.client_address or ("", 0))[0]

    def _deny(self):
        self._send_json({
            "error": "unauthorized",
            "auth_required": True,
            "hint": "输入电脑端控制台显示的配对码",
        }, 401)

    def _send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, root_dir, rel, ctype, cache="public, max-age=86400"):
        """安全地发送 root_dir 下的静态文件（禁止路径穿越）。"""
        rel = rel.split("?")[0]
        target = os.path.abspath(os.path.join(root_dir, rel))
        root_abs = os.path.abspath(root_dir)
        if not target.startswith(root_abs + os.sep) or not os.path.isfile(target):
            self._send_json({"error": "not found"}, 404)
            return
        try:
            with open(target, "rb") as f:
                body = f.read()
        except Exception:
            self._send_json({"error": "not found"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)


    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            return {}
        if n < 0 or n > 10 * 1024 * 1024:  # m9: reject oversized bodies (10 MB cap)
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}


    def do_GET(self):
        p = self.path.split("?")[0]

        # ---- PWA / 拆分后的静态资源（不需要鉴权）----
        if p == "/manifest.webmanifest":
            self._send_static(STATIC_DIR, "manifest.webmanifest",
                              "application/manifest+json", "no-cache")
            return
        if p == "/sw.js":
            self._send_static(STATIC_DIR, "sw.js",
                              "application/javascript; charset=utf-8", "no-cache")
            return
        if p == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if p.startswith("/static/"):
            ctypes = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".json": "application/json; charset=utf-8",
            }
            ext = os.path.splitext(p)[1].lower()
            self._send_static(STATIC_DIR, p[len("/static/"):],
                              ctypes.get(ext, "application/octet-stream"))
            return

        if p in ("/", "/index.html"):
            try:
                with open(INDEX_HTML, "rb") as f:
                    body = f.read()
            except Exception:
                body = b"<h1>index.html missing</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            if (AUTH_STATE["enabled"]
                    and auth.verify(AUTH_STATE["token"], self._query().get("token", ""))):
                self.send_header(
                    "Set-Cookie",
                    "%s=%s; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly"
                    % (auth.COOKIE_NAME, AUTH_STATE["token"]))
            self.end_headers()
            self.wfile.write(body)
            return

        # ---- 局域网模式：/api/* 需要配对码 ----
        if p.startswith("/api/") and not self._authorized():
            self._deny()
            return

        if p == "/api/config":
            cfg = load_config()
            self._send_json({
                "config": mask(cfg),
                "presets": PRESETS,
                "docs": knowledge.list_docs(),
                "spreads": spreads_mod.list_spreads(),
                "usage": memory.usage_today(),
                "version": VERSION,
                "auth": {
                    "required": AUTH_STATE["enabled"],
                    "paired": self._authorized(),
                },
            })
        elif p == "/api/backup":
            payload = backup.build(BASE_DIR)
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition",
                             'attachment; filename="olivia-backup.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif p == "/api/knowledge":
            self._send_json({"docs": knowledge.list_docs()})
        elif p.startswith("/cards/"):
            self._send_static(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards"),
                              p[len("/cards/"):], "image/jpeg")
        elif p == "/api/memory":
            self._send_json({
                "enabled": load_config().get("memory_enabled", True),
                "profile": memory.list_profile(),
                "facts": memory.list_facts(),
                "draws": memory.list_draws(),
                "stats": memory.stats(),
            })
        elif p == "/api/schedule":
            self._send_json({
                "status": scheduler.status(),
                "tasks": scheduler.list_tasks(),
                "outbox": scheduler.list_outbox(),
                "watchers": watchers.list_watchers(),
                "watcher_events": watchers.list_events(limit=50),
            })
        elif p == "/api/plugins":
            self._send_json({
                "kb": {
                    "notes": plugin_kb.list_notes(limit=200),
                    "stats": plugin_kb.stats(),
                },
                "vision": {
                    "config": plugin_vision.masked_config(),
                    "configured": plugin_vision.is_configured(),
                    "providers": plugin_vision.known_providers(),
                },
            })
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._body()

        # ---- 配对：唯一不需要既有 Cookie 的 POST ----
        if p == "/api/pair":
            if not AUTH_STATE["enabled"]:
                self._send_json({"ok": True, "auth_required": False})
                return
            ip = self._client_ip()
            if AUTH_STATE["throttle"].blocked(ip):
                self._send_json({"ok": False, "error": "尝试次数过多，请稍后再试"}, 429)
                return
            if auth.verify(AUTH_STATE["token"], body.get("code", "")):
                AUTH_STATE["throttle"].clear(ip)
                self._send_json({"ok": True}, headers={
                    "Set-Cookie": "%s=%s; Path=/; Max-Age=31536000; SameSite=Lax; HttpOnly"
                    % (auth.COOKIE_NAME, AUTH_STATE["token"])})
            else:
                AUTH_STATE["throttle"].fail(ip)
                self._send_json({"ok": False, "error": "配对码不正确"}, 401)
            return

        if p.startswith("/api/") and not self._authorized():
            self._deny()
            return

        if p == "/api/config":
            cfg = load_config()
            for k in ("backend", "protocol", "base_url", "api_key", "model", "temperature", "timeout",
                      "think", "tools_enabled", "memory_enabled", "prophecy_enabled",
                      "two_phase_draw", "tone_enabled", "language", "daily_token_budget",
                      "max_output_tokens", "max_history_messages", "max_history_chars",
                      "safety_second_check"):
                if k in body:
                    cfg[k] = body[k]
            # M1: never overwrite a saved key with a masked display string.
            # mask() returns "****" for short keys (len<=10) and "xxxx…yyyy"
            # for long ones; both are placeholders, not real keys.
            supplied_key = body.get("api_key")
            if isinstance(supplied_key, str) and (
                supplied_key in ("****", "***") or "…" in supplied_key
            ):
                cfg["api_key"] = load_config().get("api_key", "")
            save_config(cfg)
            self._send_json({"ok": True, "config": mask(cfg),
                             "usage": memory.usage_today()})

        elif p == "/api/backup":
            try:
                counts = backup.restore(body, BASE_DIR)
                self._send_json({"ok": True, "counts": counts})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 400)

        elif p == "/api/test":
            # Issue #1: the "test connection" button must probe the values
            # currently shown in the form, not the last saved ones. The UI
            # posts collectConfig(); overlay every connection-relevant field
            # from the request WITHOUT persisting anything. A masked key
            # placeholder falls back to the saved real key.
            saved = load_config()
            effective_key = _effective_api_key(saved, body.get("api_key"))
            cfg = dict(saved)
            for k in ("backend", "protocol", "base_url", "api_key", "model", "temperature",
                      "timeout", "think", "tools_enabled", "memory_enabled",
                      "prophecy_enabled", "tone_enabled", "two_phase_draw"):
                if k in body:
                    cfg[k] = body[k]
            cfg["api_key"] = effective_key
            try:
                reply = provider.check(cfg)
                self._send_json({"ok": True, "reply": reply})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})

        elif p == "/api/chat":
            message = body.get("message", "")
            history = body.get("history", [])
            images = body.get("images", [])  # list of data URLs from the UI
            sid = str(body.get("session_id") or "default")
            cfg = load_config()
            cfg["api_key"] = _effective_api_key(cfg, body.get("api_key"))
            # 离线整理降级：没有可用 key（或模型调用失败）时，不伪装 AI，
            # 只客观整理本地已抽的牌。抽牌本身永远可用，与这个标志无关。
            _offline = offline.is_offline(cfg)

            # ---- 每日 token 预算 ----
            # 超预算不报错、不装死：自动切到离线整理，本地抽牌/读牌仍然可用。
            try:
                _budget = int(cfg.get("daily_token_budget") or 0)
            except (TypeError, ValueError):
                _budget = 0
            _used_today = memory.usage_today()["total"]
            _budget_hit = bool(_budget and _used_today >= _budget)
            if _budget_hit:
                _offline = True

            # ---- 安全闸门（服务端权威）----
            # 危机判定绝不交给模型"自觉调用 crisis_check"：那是个工具，
            # 模型可能不调、也可能抽完牌才调。这里在 /api/chat 的最入口、
            # 早于视觉识别 / 抽牌 / LLM / 记忆写入，一律先过闸门。
            # 命中即切断：牌不发、图不识别、话不进模型、记忆不落库。
            import safety as _safety
            _crisis = _safety.detect(message)
            # 可选的语言学兜底：正则没命中、但出现「不想存在 / better off without me」
            # 这类模糊表达时，才额外让模型做一次 YES/NO 分类（默认关闭）。
            if (not _crisis and not _offline and cfg.get("safety_second_check")
                    and _safety.needs_second_check(message)):
                try:
                    probe = [
                        {"role": "system", "content": _safety.SECOND_CHECK_PROMPT},
                        {"role": "user", "content": str(message)[:800]},
                    ]
                    buf = []
                    for ev in provider.stream_chat_events(probe, cfg, tools=None):
                        if ev["type"] == "token":
                            buf.append(ev["text"])
                    if _safety.parse_second_check("".join(buf)):
                        _crisis = "unknown"
                except Exception as _se:
                    print("[safety] second check skipped: %s" % _se)

            if _crisis:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()

                def _emit_gate(obj):
                    self.wfile.write(
                        ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()

                _emit_gate({"safety": _crisis})
                _emit_gate({"token": _safety.response_for(_crisis)})
                _emit_gate({"done": True})
                return
            # 历史里若残留危机文本（上一轮被拦截的话前端仍会记进 history），
            # 也一并剔除，避免模型拿到危机上下文继续占卜。
            history = [h for h in history
                       if not (isinstance(h, dict)
                               and _safety.detect(str(h.get("content", ""))))]

            # ---- vision bridge: cloud VLM describes images, feed text to main model ----
            vision_ctx = ""
            if images and plugin_vision.is_configured():
                vcfg = plugin_vision.get_vision_config()
                for img in images[:3]:
                    try:
                        desc = plugin_vision.describe_image(img, vcfg, question=message)
                        if desc:
                            vision_ctx += plugin_vision.build_context(desc, message) + "\n"
                    except Exception as ve:
                        # m10: log the detail locally; never leak paths/URLs/keys
                        # into the system prompt or the reply stream.
                        print("[vision] describe_image failed: %s" % ve)
                        vision_ctx += "【图片识别失败，已略过图片内容】\n"

            # explicit "forget" command -> handled locally, streamed as a reply
            import re as _re
            preset_reply = None
            if _re.search(r"(忘掉|忘记|删掉|清除)(刚才|刚刚|前面|上次)?(说的|记的|记住的|这段|这些|线索)", message) \
                    or _re.search(r"忘掉刚才|忘记刚才", message):
                n = memory.forget_recent(3)
                preset_reply = ("好，我已经忘掉最近记下的 %d 条线索。" % n) if n \
                    else "我这边没有找到刚记下的内容。"

            # ---- 两阶段抽牌：选阵 -> 出牌 -> 提问 -> 解读 ----
            _purge_pending()
            two_phase = bool(cfg.get("two_phase_draw", True))
            pending = _pending_draws.get(sid) if two_phase else None
            pending_result = pending.get("result") if pending else None
            asks_draw = _draw_requested(message)
            # 来访者正在回答「用哪个牌阵」：把回答映射成牌阵名，直接抽牌。
            waiting_spread = sid in _awaiting_spread and two_phase
            # 「补一张」里也含「一张」，不能让选阵回答把它误判成单张牌阵
            chosen_spread = (_spread_choice_from_reply(message)
                             if waiting_spread and not _extra_requested(message)
                             else None)
            if chosen_spread:
                _awaiting_spread.pop(sid, None)
                message = chosen_spread + "抽牌"  # 让后续流程按点名牌阵处理
                asks_draw = True
            if pending and asks_draw:
                # 上一轮出的牌还没解读，但来访者又要抽牌：作废旧牌，按新请求抽。
                _pending_draws.pop(sid, None)
                pending = None
                pending_result = None
            # 抽牌是纯本地动作：选阵 + 从 78 张牌客观随机抽 + 拼牌面，
            # 全部由 tools.draw_cards 完成，不经过 LLM，因此抽牌/选阵都不需要 API key。
            # 只有解读轮才需要大模型。
            local_draw = None
            spread_list_reply = None
            spread_choices = None
            if two_phase and preset_reply is None:
                # 明确点名牌阵 -> 直接抽；只说「抽牌」-> 先列牌阵让他点按钮。
                if asks_draw and _named_spread(message):
                    local_draw = tools.draw_cards(spread=_pick_spread(message))
                elif asks_draw:
                    spread_list_reply = _spread_choice_reply()
                    spread_choices = _spread_choices()
                    _awaiting_spread[sid] = {"at": time.time()}

            # ---- 补牌：来访者主动要求时，在上一副牌上补一张 ----
            # 补牌是显式路径：模型自己不能补，只有这条分支会往牌面里加牌，
            # 且必须留下理由，避免「随手加一张」变成绕过牌阵的借口。
            if pending_result is None and _extra_requested(message):
                last = _last_spreads.get(sid)
                if last:
                    pending_result = last.get("result")
                    extra = tools.extra_card(pending_result, _extra_reason(message))
                    if extra.get("ok"):
                        card = extra["card"]
                        pending_result.setdefault("extras", []).append(card)
                        _last_spreads[sid] = {"result": pending_result, "at": time.time()}
                        _record_extra(sid, pending_result, card)

            # retrieve relevant knowledge for this turn
            context, used = knowledge.retrieve(message)
            system = load_persona(cfg) + now_context(cfg)
            # 语气系统：Olivia 的"声音"——真实女性塔罗师的措辞 + 自然 NVC。
            # 放在人格之后、其余上下文之前，确保它稳定地盖住表达方式。
            if cfg.get("tone_enabled", True):
                tone = load_tone(cfg)
                if tone:
                    system += "\n\n---\n" + tone
            # 预言模式（仅供娱乐）：手动开启时才追加覆盖层，安全边界不放开
            if cfg.get("prophecy_enabled", False):
                prophecy = load_prophecy(cfg)
                if prophecy:
                    system += "\n\n---\n" + prophecy
            if context:
                system += (
                    "\n\n---\n以下是与本次对话相关的专业资料，回答专业判断时以这些资料为准，"
                    "不要臆测；塔罗只用于打开话题与照见感受，风险评估/诊断/干预选择绝不从牌里来。\n\n"
                    + context
                )
            # inject private long-term memory (if enabled)
            if cfg.get("memory_enabled", True):
                try:
                    mem_ctx = memory.context(message)
                    if mem_ctx:
                        system += "\n\n---\n" + mem_ctx
                except Exception:
                    pass
            # inject KB notes relevant to this turn
            try:
                notes_ctx, _nids = plugin_kb.search_notes(message, top_k=2)
                if notes_ctx:
                    system += "\n\n---\n以下是用户此前归档的笔记，相关时可自然引用：\n\n" + notes_ctx
            except Exception:
                pass
            if vision_ctx:
                system += "\n\n---\n" + vision_ctx
            use_tools = cfg.get("tools_enabled", True)
            if pending_result:
                # 解读轮：把已抽出的牌面和来访者的问题作为硬约束注入，
                # 同时临时禁用 draw_cards 工具，模型无法重抽或换牌。
                system += "\n\n---\n" + _pending_context(pending_result, message)
                use_tools = False
            elif two_phase:
                # 抽牌轮：牌由系统在本地抽好并直接展示，完全不经过模型；
                # 系统在本轮根本不会调用 LLM，这段说明只用于其它非抽牌消息。
                system += ("\n\n---\n【两阶段抽牌流程】抽牌由系统在本地完成，"
                           "牌面会自动展示，你不需要也不应该调用 draw_cards 工具。"
                           "牌出好后只需温和地问一句来访者想问的问题，例如："
                           "「好的，牌已经抽出来了——你有什么问题吗？告诉我你想问什么，"
                           "我就照着这副牌为你解读。」本轮不要解读任何一张牌；"
                           "等下一轮他给出具体问题后，才只针对这副已抽出的牌解读。")
            if use_tools:
                system += "\n\n---\n" + tools.TOOL_GUIDE
            # 两阶段流程下，解读轮的历史里若含上一轮的抽牌说明，不影响解牌；
            # 关键约束已在 system 里显式给出。
            # 上下文裁剪：按消息条数和字符数双重上限，从最旧的开始丢，
            # 避免长会话把窗口撑爆或把预算烧在重复历史上。
            try:
                max_msgs = max(2, int(cfg.get("max_history_messages") or 20))
            except (TypeError, ValueError):
                max_msgs = 20
            try:
                max_chars = max(2000, int(cfg.get("max_history_chars") or 24000))
            except (TypeError, ValueError):
                max_chars = 24000
            kept = []
            used_chars = len(system)
            for h in reversed(history[-max_msgs:]):
                if not isinstance(h, dict):
                    continue
                text = str(h.get("content", ""))
                if used_chars + len(text) > max_chars:
                    break
                role = h.get("role", "user")
                # m11: only real conversation roles are allowed in; a client
                # must not be able to inject a system message via history.
                if role not in ("user", "assistant"):
                    role = "user"
                kept.append({"role": role, "content": text})
                used_chars += len(text)
            kept.reverse()
            msgs = [{"role": "system", "content": system}] + kept
            msgs.append({"role": "user", "content": message})

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                def emit(obj):
                    self.wfile.write(
                        ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()

                emit({"meta": used})
                if _budget:
                    emit({"budget": {"limit": _budget, "used": _used_today,
                                     "exceeded": _budget_hit}})
                full = []
                usage_totals = {"in": 0, "out": 0, "total": 0}
                # M2: keep the structured draw_cards result for this turn, so
                # draw history records exactly the cards that were drawn.
                turn_draw = None
                if local_draw is not None:
                    # ---- 抽牌轮：纯本地完成，不调用大模型、不需要 API key ----
                    emit({"tool": tools.summary("draw_cards", local_draw)})
                    # 先把「默念问题」的引导语交给前端打字机式呈现，
                    # 稍作停顿后再翻牌，最后由前端打出 ASK 提问。
                    emit({"meditate": MEDITATE_TEXT})
                    emit({"cards": _cards_payload(local_draw)})
                    full.append(MEDITATE_TEXT)
                    full.append(ASK_AFTER_DRAW)
                    emit({"token": ASK_AFTER_DRAW})
                    _pending_draws[sid] = {"result": local_draw, "at": time.time()}
                    turn_draw = local_draw
                elif preset_reply is not None:
                    full.append(preset_reply)
                    emit({"token": preset_reply})
                elif spread_list_reply is not None:
                    # ---- 选阵轮：纯本地列出牌阵按钮，不调用大模型 ----
                    full.append(spread_list_reply)
                    emit({"token": spread_list_reply})
                    emit({"spread_choices": spread_choices})
                elif pending_result is not None and not asks_draw:
                    # ---- 解读轮：牌面已经抽出，直接推给前端渲染，不调工具 ----
                    emit({"cards": _cards_payload(pending_result)})
                    # 用工具摘要的同一格式标出这是已抽出的牌，便于用户对照。
                    emit({"tool": tools.summary("draw_cards", pending_result)})
                    _pending_draws.pop(sid, None)
                    # 记住这副牌：解读完之后若来访者还想补一张，从这里取回原牌面
                    _last_spreads[sid] = {"result": pending_result, "at": time.time()}
                    # 牌在抽牌轮已经记入记忆，这里不再重复入库。
                    turn_draw = None
                    if _offline:
                        # 离线降级：不假装模型解读，只按传统牌意 + 牌位 + 种子
                        # 客观整理这副已抽出的牌，让「看牌 → 读牌」链走完。
                        emit({"offline": True})
                        for piece in offline.chunks(offline.compose(pending_result, message)):
                            full.append(piece)
                            emit({"token": piece})
                    else:
                        for ev in provider.stream_chat_events(msgs, cfg, tools=None):
                            if ev["type"] == "token":
                                full.append(ev["text"])
                                emit({"token": ev["text"]})
                            elif ev["type"] == "done":
                                _add_usage(usage_totals, ev.get("usage"))
                elif _offline:
                    # ---- 离线无牌对话：不调模型，给不越界的引导 ----
                    emit({"offline": True})
                    for piece in offline.chunks(offline.compose_chat(message)):
                        full.append(piece)
                        emit({"token": piece})
                else:
                    # ---- agentic loop: model <-> tools until no tool call ----
                    MAX_ROUNDS = 6
                    for _round in range(MAX_ROUNDS):
                        round_calls = []
                        final_content = ""
                        round_tokens = []
                        for ev in provider.stream_chat_events(
                                msgs, cfg, tools=tools.TOOLS if use_tools else None):
                            if ev["type"] == "token":
                                # 抽牌轮先缓冲模型文本；若真的抽了牌，只输出牌面与固定提问，
                                # 丢掉任何模型自作主张的解读或开场白。
                                # 非抽牌轮（无工具调用）会在下面统一刷出。
                                round_tokens.append(ev["text"])
                            elif ev["type"] == "tool_calls":
                                round_calls = ev["calls"]
                            elif ev["type"] == "done":
                                final_content = ev.get("content", "")
                                _add_usage(usage_totals, ev.get("usage"))
                        if not round_calls:
                            for t in round_tokens:
                                full.append(t)
                                emit({"token": t})
                            break

                        # Build the assistant tool-call message + tool results
                        # in the exact shape the OpenAI protocol expects.
                        tc_payload = []
                        result_msgs = []
                        stop_after_round = False
                        for c in round_calls:
                            name = c.get("name", "")
                            try:
                                args = json.loads(c["arguments"]) if c.get("arguments") else {}
                            except Exception:
                                args = {}
                            result = tools.execute(name, args)
                            emit({"tool": tools.summary(name, result)})
                            if name == "draw_cards" and result.get("ok"):
                                turn_draw = result
                                # 引导语 → 停顿 → 翻牌 → 提问，交给前端做打字机动画。
                                emit({"meditate": MEDITATE_TEXT})
                                full.append(MEDITATE_TEXT)
                                # 把牌面单独推给前端，用于渲染牌图和牌位列表
                                emit({"cards": _cards_payload(result)})
                                if two_phase:
                                    # 抽牌轮：只输出牌面与固定提问，本轮任何模型自作主张的
                                    # 解读/开场白都丢弃；下一轮给出问题后再解读同一副牌。
                                    _pending_draws[sid] = {"result": result, "at": time.time()}
                                    full.append(ASK_AFTER_DRAW)
                                    emit({"token": ASK_AFTER_DRAW})
                                    stop_after_round = True
                                    break
                            tc_payload.append({
                                "id": c.get("id", ""),
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args, ensure_ascii=False),
                                },
                            })
                            result_msgs.append({
                                "role": "tool",
                                "tool_call_id": c.get("id", ""),
                                "content": json.dumps(result, ensure_ascii=False),
                            })
                        if stop_after_round:
                            # 两阶段抽牌：本轮到此为止，不再让模型继续解读。
                            break
                        msgs.append({
                            "role": "assistant",
                            "content": final_content or "",
                            "tool_calls": tc_payload,
                        })
                        msgs.extend(result_msgs)
                    # ---- end agentic loop ----
                if usage_totals["total"]:
                    emit({"usage": usage_totals})
                    try:
                        memory.add_usage(usage_totals["in"], usage_totals["out"])
                    except Exception:
                        pass
                emit({"done": True})
                # persist this turn (rule-based extraction, ~0 ms) after stream
                if cfg.get("memory_enabled", True) and full and preset_reply is None:
                    try:
                        memory.remember(message, "".join(full), draw=turn_draw)
                    except Exception:
                        pass
            except Exception as e:
                # 模型连接失败（有 key 但网络/认证/超时出错）：不把人丢进死胡同。
                # 有牌就用离线整理接住这副牌；没牌也给一条可离线抽牌的引导。
                # 不外泄异常里的 URL / key 细节。
                print("[chat] model call failed, fell back to offline: %s" % e)

                def _emit_err(obj):
                    self.wfile.write(
                        ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()

                _fallback_draw = locals().get("turn_draw") or pending_result
                if _fallback_draw:
                    _emit_err({"offline": True, "fallback": "模型连接失败，已改为离线整理"})
                    for piece in offline.chunks(offline.compose(_fallback_draw, message)):
                        _emit_err({"token": piece})
                else:
                    _emit_err({"offline": True, "fallback": "模型连接失败"})
                    for piece in offline.chunks(offline.compose_chat(message)):
                        _emit_err({"token": piece})
                _emit_err({"done": True})
        elif p == "/api/memory":
            op = body.get("op", "")
            try:
                if op == "pin":
                    ok = memory.pin_fact(int(body.get("id", 0)), True)
                elif op == "unpin":
                    ok = memory.pin_fact(int(body.get("id", 0)), False)
                elif op == "delete_fact":
                    ok = memory.delete_fact(int(body.get("id", 0)))
                elif op == "delete_draw":
                    ok = memory.delete_draw(int(body.get("id", 0)))
                elif op == "profile_set":
                    ok = memory.set_profile(str(body.get("key", "")), str(body.get("value", "")))
                elif op == "profile_delete":
                    ok = memory.delete_profile(str(body.get("key", "")))
                elif op == "add_fact":
                    kind = str(body.get("kind", "fact"))
                    text = str(body.get("text", "")).strip()
                    n = memory._norm(text)
                    if not n:
                        ok = False
                    else:
                        import sqlite3
                        conn = memory._conn()
                        try:
                            conn.execute(
                                "INSERT INTO facts(kind,norm,text,pinned,sensitive,last_seen,created_at) "
                                "VALUES(?,?,?,0,0,?,?)",
                                (kind, n, text, memory._now(), memory._now()))
                            conn.commit()
                            ok = True
                        finally:
                            conn.close()
                elif op == "forget":
                    ok = memory.forget(str(body.get("text", ""))) > 0
                elif op == "forget_recent":
                    ok = memory.forget_recent(int(body.get("n", 3))) > 0
                elif op == "clear":
                    ok = memory.clear()
                elif op == "toggle":
                    cfg = load_config()
                    cfg["memory_enabled"] = bool(body.get("enabled", True))
                    save_config(cfg)
                    ok = True
                else:
                    self._send_json({"ok": False, "error": "unknown op"}, 400)
                    return
                self._send_json({
                    "ok": ok,
                    "profile": memory.list_profile(),
                    "facts": memory.list_facts(),
                    "draws": memory.list_draws(),
                    "stats": memory.stats(),
                    "enabled": load_config().get("memory_enabled", True),
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif p == "/api/schedule":
            op = body.get("op", "")
            try:
                if op == "settings":
                    ok = scheduler.set_settings(body.get("values", {}))
                elif op == "add_task":
                    scheduler.add_task(body.get("task", {}))
                    ok = True
                elif op == "update_task":
                    ok = scheduler.update_task(int(body.get("id", 0)), body.get("task", {}))
                elif op == "delete_task":
                    ok = scheduler.delete_task(int(body.get("id", 0)))
                elif op == "mark_read":
                    ok = scheduler.mark_read(
                        body.get("id"), all_read=bool(body.get("all", False)))
                elif op == "delete_message":
                    ok = scheduler.delete_message(int(body.get("id", 0)))
                elif op == "add_event":
                    ok = scheduler.add_event(
                        str(body.get("kind", "manual")), str(body.get("payload", "")))
                elif op == "add_watcher":
                    watchers.add_watcher(body.get("watcher", {}))
                    ok = True
                elif op == "update_watcher":
                    ok = watchers.update_watcher(int(body.get("id", 0)), body.get("watcher", {}))
                elif op == "delete_watcher":
                    ok = watchers.delete_watcher(int(body.get("id", 0)))
                elif op == "clear_watcher_events":
                    ok = watchers.clear_events()
                elif op == "run_now":
                    fired = scheduler.run_due_tasks(load_config)
                    fired = fired + scheduler.run_watcher_checks(force=True)
                    self._send_json({
                        "ok": True, "fired": fired,
                        "status": scheduler.status(),
                        "tasks": scheduler.list_tasks(),
                        "outbox": scheduler.list_outbox(),
                        "watchers": watchers.list_watchers(),
                        "watcher_events": watchers.list_events(limit=50),
                    })
                    return
                else:
                    self._send_json({"ok": False, "error": "unknown op"}, 400)
                    return
                self._send_json({
                    "ok": ok,
                    "status": scheduler.status(),
                    "tasks": scheduler.list_tasks(),
                    "outbox": scheduler.list_outbox(),
                    "watchers": watchers.list_watchers(),
                    "watcher_events": watchers.list_events(limit=50),
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)

        elif p == "/api/plugins":
            op = body.get("op", "")
            try:
                if op == "kb_add":
                    ok = plugin_kb.add_note(
                        str(body.get("title", "")), str(body.get("content", "")),
                        body.get("tags", ""), source="manual",
                        pinned=bool(body.get("pinned", False))) is not None
                elif op == "kb_update":
                    ok = plugin_kb.update_note(
                        int(body.get("id", 0)),
                        title=body.get("title"), content=body.get("content"),
                        tags=body.get("tags"), pinned=body.get("pinned"))
                elif op == "kb_delete":
                    ok = plugin_kb.delete_note(int(body.get("id", 0)))
                elif op == "kb_pin":
                    ok = plugin_kb.pin_note(int(body.get("id", 0)),
                                            bool(body.get("pinned", True)))
                elif op == "kb_archive_memory":
                    n1 = plugin_kb.archive_memory(limit=int(body.get("limit", 50)))
                    n2 = plugin_kb.archive_draws(limit=int(body.get("limit", 30)))
                    self._send_json({"ok": True, "facts": n1, "draws": n2,
                                     "stats": plugin_kb.stats()})
                    return
                elif op == "kb_clear":
                    ok = plugin_kb.clear()
                elif op == "kb_export":
                    self._send_json({"ok": True, "markdown": plugin_kb.export_markdown()})
                    return
                elif op == "vision_config":
                    vcfg = plugin_vision.get_vision_config()
                    for k in ("enabled", "base_url", "model", "describe_prompt", "detail", "timeout"):
                        if k in body:
                            vcfg[k] = body[k]
                    if body.get("api_key") and "***" not in str(body["api_key"]):
                        vcfg["api_key"] = body["api_key"]
                    all_cfg = plugin_vision.load_config()
                    all_cfg["vision"] = vcfg
                    plugin_vision.save_config(all_cfg)
                    ok = True
                elif op == "vision_test":
                    vcfg = plugin_vision.get_vision_config()
                    if body.get("api_key") and "***" not in str(body["api_key"]):
                        vcfg["api_key"] = body["api_key"]
                    desc = plugin_vision.describe_image(body.get("image", ""), vcfg)
                    self._send_json({"ok": True, "description": desc})
                    return
                else:
                    self._send_json({"ok": False, "error": "unknown op"}, 400)
                    return
                self._send_json({
                    "ok": ok,
                    "kb": {"notes": plugin_kb.list_notes(limit=200), "stats": plugin_kb.stats()},
                    "vision": {"config": plugin_vision.masked_config(),
                               "configured": plugin_vision.is_configured()},
                })
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    # Windows 控制台/重定向到文件时默认不是 UTF-8，启动横幅里的中文会直接抛
    # UnicodeEncodeError，导致局域网模式还没监听就退出。
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    port = int(os.environ.get("AGENT_PORT", "8765"))
    # 默认只监听本机。要让手机（安卓 App）连上，设 AGENT_HOST=0.0.0.0 显式开放到局域网。
    host = os.environ.get("AGENT_HOST", "127.0.0.1")
    AUTH_STATE["enabled"] = auth.enabled(host)
    if AUTH_STATE["enabled"]:
        AUTH_STATE["token"] = auth.load_or_create(BASE_DIR)
    srv = ThreadingHTTPServer((host, port), Handler)
    scheduler.start(load_config)
    # PID 文件：供安装包的 uninstall 精确停止本服务（不误杀其它 python server.py）
    pid_path = os.path.join(BASE_DIR, "olivia.pid")
    try:
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pid_path = None
    shown = "127.0.0.1" if host in ("", "0.0.0.0") else host
    print("Olivia agent v%s running at http://%s:%d" % (VERSION, shown, port))
    if host == "0.0.0.0" and AUTH_STATE["enabled"]:
        code = auth.pretty(AUTH_STATE["token"])
        print("已对局域网开放：手机访问 http://<本机IP>:%d" % port)
        print("配对码：%s（只需在手机/浏览器里输入一次）" % code)
        print("也可直接打开 http://<本机IP>:%d/?token=%s"
              % (port, AUTH_STATE["token"]))
    elif host == "0.0.0.0":
        print("已对局域网开放：同网段的人也能打开，用完请改回默认。")
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if pid_path:
            try:
                os.remove(pid_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()
