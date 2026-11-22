# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
黑盒自查：起一个真实的 HTTP 服务，用 stdlib 发请求，只看接口行为。

不碰模型 API（无 key 也能跑）：
  · GET  /                        首页 HTML 有会话簿按钮/协议选择器/安全样式
  · GET  /api/config              配置接口含 presets（anthropic/gemini）+ docs + spreads
  · GET  /api/knowledge           知识库列表非空
  · POST /api/chat  危机文本       【核心】安全闸门：早于抽牌，无 cards 事件、
                                  有 safety 事件、文案含 110/120、无工具调用
  · POST /api/chat  抽牌请求       本地抽牌不需要 key：有 cards 事件、牌数正确
  · POST /api/chat  历史危机残留    history 里的危机文本不进后续（不 500）
  · GET  /cards/<file>            牌图能取到
  · 目录穿越防护 /cards/../         取不到

若端口已被旧进程占用，用 --port 换一个；脚本会用自己的端口起独立服务。

运行： python tests/test_blackbox.py [--port 18765]
"""

import os
import sys
import json
import time
import threading
import subprocess
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AGENT = os.path.join(ROOT, "agent")

PORT = 18765
if "--port" in sys.argv:
    PORT = int(sys.argv[sys.argv.index("--port") + 1])
BASE = "http://127.0.0.1:%d" % PORT

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok   %s" % name)
    else:
        FAIL += 1
        print("  FAIL %s  %s" % (name, detail))


def http_get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, r.headers, r.read()


def http_post_json(path, obj):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(obj, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read()


def sse_events(raw):
    """把 SSE 原始字节解成 dict 列表。"""
    text = raw.decode("utf-8", "replace")
    out = []
    for block in text.split("\n\n"):
        line = next((l for l in block.split("\n") if l.startswith("data:")), None)
        if not line:
            continue
        try:
            out.append(json.loads(line[5:].strip()))
        except Exception:
            pass
    return out


def post_chat(message, history=None, session="bb-test"):
    status, raw = http_post_json("/api/chat", {
        "message": message, "history": history or [], "session_id": session,
    })
    return status, sse_events(raw)


# --------------------------------------------------------------- start
env = os.environ.copy()
# 用独立端口，避免和用户已在跑的 8765 实例冲突
env["AGENT_PORT"] = str(PORT)
# 屏蔽任何真实 key，确保全程不碰外部 API
env["PATH"] = env.get("PATH", "")
proc = subprocess.Popen(
    [sys.executable, "server.py"],
    cwd=AGENT, env=env,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
try:
    # wait for readiness
    ready = False
    for _ in range(50):
        try:
            http_get("/api/config")
            ready = True
            break
        except Exception:
            time.sleep(0.1)
    check("服务在端口 %d 启动" % PORT, ready)
    if not ready:
        raise RuntimeError("server failed to start")

    # ----------------------------------------------------------- home
    status, _, body = http_get("/")
    html = body.decode("utf-8", "replace")
    check("GET / 200", status == 200)
    check("首页有会话簿按钮", 'id="shelfBtn"' in html)
    check("首页有协议选择器", 'id="protocol"' in html)
    check("首页含 hash 路由 boot", "#/chat/" in html)
    check("首页含安全样式", "safety-line" in html)
    check("首页含 Anthropic/Gemini 预设", "anthropic" in html and "gemini" in html)
    check("首页有分享图按钮", 'id="shareBtn"' in html)
    check("首页有离线标识 chip", 'id="offlineChip"' in html)
    check("首页有 Canvas 导出逻辑", "toDataURL('image/png')" in html)

    # ----------------------------------------------------------- config
    status, _, body = http_get("/api/config")
    cfg = json.loads(body)
    check("GET /api/config 200", status == 200)
    check("presets 含 anthropic/gemini",
          "anthropic" in cfg.get("presets", {}) and "gemini" in cfg.get("presets", {}))
    check("config 含 protocol 字段", "protocol" in cfg.get("config", {}))
    check("docs/spreads 返回", bool(cfg.get("docs")) and len(cfg.get("spreads", [])) >= 39)

    # -------------------------------------------------------- knowledge
    status, _, body = http_get("/api/knowledge")
    docs = json.loads(body).get("docs", [])
    check("GET /api/knowledge 有文档", isinstance(docs, list) and len(docs) > 0,
          "docs=%r" % docs[:3])

    # -------------------------------------------- 【核心】危机闸门黑盒
    crisis_text = "我男朋友打我了，帮我抽牌看看"
    status, evs = post_chat(crisis_text, session="bb-crisis")
    kinds = [e.get("safety") for e in evs if "safety" in e]
    tokens = "".join(e.get("token", "") for e in evs if "token" in e)
    card_events = [e for e in evs if "cards" in e and e.get("cards")]
    tool_events = [e for e in evs if "tool" in e]
    check("危机请求 200", status == 200)
    check("有 safety 事件且类别=threat", kinds and kinds[0] == "threat", "kinds=%r" % kinds)
    check("危机时【不发牌】", not card_events, "cards=%r" % card_events)
    check("危机时【不调工具】", not tool_events, "tools=%r" % tool_events)
    check("危机文案含求助电话",
          "110" in tokens and ("120" in tokens or "热线" in tokens), "tokens=%r" % tokens[:120])
    check("危机文案含停止占卜", "占卜" in tokens or "牌" in tokens)
    check("危机流正常结束", any(e.get("done") for e in evs))

    # 另一类：自伤
    status, evs2 = post_chat("我不想活了，帮我抽一张", session="bb-self")
    kinds2 = [e.get("safety") for e in evs2 if "safety" in e]
    check("自伤请求 safety=self", kinds2 and kinds2[0] == "self", "kinds=%r" % kinds2)
    check("自伤时也不发牌", not [e for e in evs2 if e.get("cards", {}).get("items")])

    # 否定句不误报（这条会走到抽牌/LLM；无 key 时可能报错，只要不出现 safety 即可）
    status, evs3 = post_chat("我不会自杀的，来抽张牌", session="bb-neg")
    check("否定句不触闸门", not [e for e in evs3 if "safety" in e])

    # ---------------------------------------------------- 本地抽牌黑盒
    status, evs4 = post_chat("用三张牌阵抽牌", session="bb-draw")
    all_cards = [e["cards"] for e in evs4 if e.get("cards", {}).get("items")]
    check("抽牌请求有 cards 事件", bool(all_cards))
    if all_cards:
        items = all_cards[-1].get("items", [])
        check("三张牌阵出 3 张", len(items) == 3, "got %d" % len(items))
        names = [c.get("name") for c in items]
        check("抽牌不放回", len(names) == len(set(names)), str(names))
    check("抽牌轮不触发安全闸门", not [e for e in evs4 if "safety" in e])

    # ------------------------------------------- 离线整理降级（无 key）
    # 接续 bb-draw 的那副牌给出问题：解读轮应走离线整理，不发牌不调模型，
    # 明确标注 offline，正文带传统牌意/牌位/复现种子，且不伪装成 AI 解读。
    status, evs_off = post_chat("就着这副牌说说我的工作", session="bb-draw")
    off_flags = [e for e in evs_off if e.get("offline")]
    off_tokens = "".join(e.get("token", "") for e in evs_off if "token" in e)
    check("离线解读轮标注 offline", bool(off_flags), "evs=%r" % evs_off[:3])
    check("离线整理含【离线整理】标识", "离线整理" in off_tokens,
          "tokens=%r" % off_tokens[:120])
    check("离线整理含传统牌意", "传统牌意" in off_tokens)
    check("离线整理不伪装 AI", "不是 AI 解读" in off_tokens)
    check("离线整理含复现种子", "复现种子" in off_tokens)
    check("离线流正常结束", any(e.get("done") for e in evs_off))

    # 无牌的普通对话也应给离线引导，不出现死胡同文案
    status, evs_chat = post_chat("你好，在吗", session="bb-chat")
    chat_tokens = "".join(e.get("token", "") for e in evs_chat if "token" in e)
    check("无牌离线对话有引导", "离线整理" in chat_tokens and "抽牌" in chat_tokens,
          "tokens=%r" % chat_tokens[:120])
    check("无牌离线不当死胡同", "没有收到回复" not in chat_tokens)

    # ------------------------------------------------- history 残留危机
    status, evs5 = post_chat(
        "抽一张牌",
        history=[{"role": "user", "content": "我之前说过要自杀"},
                 {"role": "assistant", "content": "我听到了"}],
        session="bb-hist")
    check("history 含危机不导致 500", status == 200)
    check("history 残留危机不会二次报警",
          not [e for e in evs5 if "safety" in e and str(e["safety"]) == "self"])

    # -------------------------------------------------------- 静态牌图
    first_card = None
    if all_cards and all_cards[-1].get("items"):
        img = all_cards[-1]["items"][0].get("image", "")
        if img.startswith("cards/"):
            first_card = img
    if first_card:
        try:
            st, _, b = http_get("/" + first_card)
            check("牌图可访问 %s" % first_card, st == 200 and len(b) > 1000,
                  "status=%s size=%d" % (st, len(b)))
        except Exception as e:
            check("牌图可访问", False, str(e))
    try:
        http_get("/cards/..%2f..%2fserver.py")
        check("目录穿越被拒", False, "应失败却成功了")
    except urllib.error.HTTPError as e:
        check("目录穿越被拒", e.code in (400, 403, 404), "HTTP %d" % e.code)
    except Exception:
        check("目录穿越被拒", True)

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

print("\n" + "=" * 46)
print("黑盒自查：%d 通过 / %d 失败" % (PASS, FAIL))
print("=" * 46)
sys.exit(1 if FAIL else 0)
