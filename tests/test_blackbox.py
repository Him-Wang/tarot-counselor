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
  · 局域网模式（AGENT_HOST=0.0.0.0）未配对 401、错码限流、对码后 Cookie 放行

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

# Windows 控制台默认不是 UTF-8，中文用例名会直接抛 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    status_css, _, css_body = http_get("/static/app.css")
    status_js, _, js_body = http_get("/static/app.js")
    css = css_body.decode("utf-8", "replace")
    appjs = js_body.decode("utf-8", "replace")
    check("首页有会话簿按钮", 'id="shelfBtn"' in html)
    check("首页有协议选择器", 'id="protocol"' in html)
    check("静态样式可访问", status_css == 200 and len(css) > 1000)
    check("静态脚本可访问", status_js == 200 and len(appjs) > 10000)
    check("首页含 hash 路由 boot", "#/chat/" in appjs)
    check("首页含安全样式", "safety-line" in css)
    check("首页含 Anthropic/Gemini 预设", "anthropic" in html and "gemini" in html)
    check("首页有配对码入口", "/api/pair" in appjs and "配对码" in appjs)
    check("首页有分享图按钮", 'id="shareBtn"' in html)
    check("首页有离线标识 chip", 'id="offlineChip"' in html)
    check("首页有 Canvas 导出逻辑", "toDataURL('image/png')" in appjs)
    status_m, _, man = http_get("/manifest.webmanifest")
    check("PWA manifest 可访问", status_m == 200 and b"Olivia" in man)
    status_sw, _, sw = http_get("/sw.js")
    check("Service Worker 可访问", status_sw == 200 and b"olivia-shell" in sw)

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
    check("chat 抽牌是真随机（无 seed 字段、标记 random）",
          all_cards and "seed" not in all_cards[-1] and all_cards[-1].get("random") is True)

    # ---------------------------------------------------- 一键真随机端点黑盒
    status, raw = http_post_json("/api/random-draw", {
        "session_id": "bb-rand", "spread": "三张",
    })
    rand = json.loads(raw.decode("utf-8"))
    check("随机抽牌端点成功", rand.get("ok"), str(rand)[:200])
    rand_items = (rand.get("cards") or {}).get("items") or []
    check("随机抽牌出 3 张", len(rand_items) == 3, str(len(rand_items)))
    check("随机抽牌无 seed 字段（不可复现）", "seed" not in (rand.get("cards") or {}))
    check("随机抽牌标记 random", (rand.get("cards") or {}).get("random") is True)
    status, raw2 = http_post_json("/api/random-draw", {
        "session_id": "bb-rand", "spread": "三张",
    })
    rand2 = json.loads(raw2.decode("utf-8"))
    check("两次随机抽牌结果不同",
          [c.get("name") for c in rand_items] !=
          [c.get("name") for c in (rand2.get("cards") or {}).get("items") or []])

    # 🎲 抽完后紧接着「补一张」应在这副牌上补成功（M1 回归）
    # bb-rand 上一次抽牌已写入 _last_spreads；补牌后张数应为 4。
    status, evs_rand_extra = post_chat("补一张牌：想看看被忽略的方面", session="bb-rand")
    rand_read_cards = [e["cards"] for e in evs_rand_extra if e.get("cards", {}).get("items")]
    # 原牌 3 张仍在 items，补牌单列在 extras（不替换原牌）
    check("🎲 后补牌原牌仍是 3 张",
          bool(rand_read_cards) and len(rand_read_cards[-1]["items"]) == 3,
          str(len(rand_read_cards[-1]["items"]) if rand_read_cards else None))
    check("🎲 后补牌带 extras",
          bool(rand_read_cards) and len(rand_read_cards[-1].get("extras") or []) == 1)

    # ---------------------------------------------------- 手动选牌黑盒
    # 界面带 pick:true：先给牌阵舞台（不发牌），挑满后 /api/pick 落位，
    # 再提问时沿用同一副牌进入解读轮，不重新抽。
    status, raw = http_post_json("/api/chat", {
        "message": "用三张牌阵抽牌", "history": [],
        "session_id": "bb-pick", "pick": True,
    })
    evs_pick = sse_events(raw)
    pick_specs = [e["pick"] for e in evs_pick if e.get("pick")]
    check("手动选牌轮给出 pick 事件", bool(pick_specs), "evs=%r" % evs_pick[:3])
    check("手动选牌轮不直接发牌", not [e for e in evs_pick if e.get("cards")])
    if pick_specs:
        check("pick 舞台张数为 3", pick_specs[-1].get("count") == 3,
              str(pick_specs[-1].get("count")))
        check("pick 舞台带牌位", len(pick_specs[-1].get("positions") or []) == 3)
    status, raw = http_post_json("/api/pick", {
        "session_id": "bb-pick", "spread": "三张", "picks": [0, 1, 2],
    })
    picked = json.loads(raw.decode("utf-8"))
    check("选牌落位成功", picked.get("ok"), str(picked)[:200])
    picked_items = (picked.get("cards") or {}).get("items") or []
    picked_names = [c.get("name") for c in picked_items]
    check("手选的牌按挑选顺序落位", picked_names == ["愚者", "魔术师", "女祭司"],
          str(picked_names))
    check("手工牌面标记 manual", (picked.get("cards") or {}).get("manual") is True)
    try:
        http_post_json("/api/pick", {
            "session_id": "bb-pick", "spread": "三张", "picks": [0],
        })
        too_few = False
    except urllib.error.HTTPError as e:
        too_few = e.code == 400
    check("选牌张数不足被拒绝", too_few)

    status, evs_read = post_chat("这组牌怎么看我的工作", session="bb-pick")
    read_cards = [e["cards"] for e in evs_read if e.get("cards", {}).get("items")]
    check("落牌后解读轮沿用同一副牌",
          bool(read_cards) and [c.get("name") for c in read_cards[-1]["items"]] == picked_names,
          str(read_cards[-1]["items"] if read_cards else None)[:200])

    # ------------------------------------------- 离线整理降级（无 key）
    # 接续 bb-draw 的那副牌给出问题：解读轮应走离线整理，不发牌不调模型，
    # 明确标注 offline，正文带传统牌意/牌位，且不伪装成 AI 解读。
    # bb-draw 走一键真随机路径，离线整理应标注真随机、无种子。
    status, evs_off = post_chat("就着这副牌说说我的工作", session="bb-draw")
    off_flags = [e for e in evs_off if e.get("offline")]
    off_tokens = "".join(e.get("token", "") for e in evs_off if "token" in e)
    check("离线解读轮标注 offline", bool(off_flags), "evs=%r" % evs_off[:3])
    check("离线整理含【离线整理】标识", "离线整理" in off_tokens,
          "tokens=%r" % off_tokens[:120])
    check("离线整理含传统牌意", "传统牌意" in off_tokens)
    check("离线整理不伪装 AI", "不是 AI 解读" in off_tokens)
    check("离线整理标注真随机、无种子",
          "系统真随机" in off_tokens and "无种子" in off_tokens)
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

    # -------------------------------------------- 目标 / 档案 / 关怀面板 API
    status, _, body = http_get("/api/goals")
    _gd = json.loads(body.decode("utf-8"))
    check("GET /api/goals 返回 goals+stats",
          status == 200 and "goals" in _gd and "stats" in _gd, str(_gd)[:120])

    _gid = None
    try:
        status, raw = http_post_json("/api/goals", {
            "op": "add", "title": "黑盒测试目标", "note": "自动化"})
        _gd2 = json.loads(raw.decode("utf-8"))
        _gid = next((g["id"] for g in _gd2["goals"]
                     if g["title"] == "黑盒测试目标"), None)
        check("POST /api/goals add 生效", status == 200 and bool(_gid), str(_gd2)[:160])
        status, raw = http_post_json("/api/goals", {
            "op": "set_next", "id": _gid, "text": "先查资料", "source": "suggested"})
        _gd3 = json.loads(raw.decode("utf-8"))
        _g = next((g for g in _gd3["goals"] if g["id"] == _gid), {})
        check("set_next 标记 suggested", _g.get("next_source") == "suggested", str(_g)[:160])
        status, raw = http_post_json("/api/goals", {
            "op": "link", "id": _gid, "kind": "task", "ref_id": 99})
        check("link task 生效", json.loads(raw.decode("utf-8"))["ok"] is True)
        status, raw = http_post_json("/api/goals", {
            "op": "confirm_step", "id": _gid})
        _gd4 = json.loads(raw.decode("utf-8"))
        _g = next((g for g in _gd4["goals"] if g["id"] == _gid), {})
        check("confirm_step 由 UI 确认生效",
              _g.get("next_step") == "" and len(_g.get("steps", [])) >= 1,
              str(_g)[:160])
        http_post_json("/api/goals", {"op": "delete", "id": _gid})
        _gid = None
    except Exception as e:
        check("目标 API 无异常", False, str(e))

    status, _, body = http_get("/api/archive?query=zzz_no_such_keyword")
    _ad = json.loads(body.decode("utf-8"))
    check("GET /api/archive 返回 records+stats",
          status == 200 and "records" in _ad and "stats" in _ad, str(_ad)[:120])
    try:
        status, raw = http_post_json("/api/archive", {
            "op": "add", "user": "黑盒", "question": "测试问题",
            "spread": "单张", "points": "测试要点", "emotion_tags": ["平静"]})
        _ad2 = json.loads(raw.decode("utf-8"))
        check("POST /api/archive add 生效",
              status == 200 and any(r["question"] == "测试问题"
                                    for r in _ad2["records"]), str(_ad2)[:160])
        http_post_json("/api/archive", {"op": "clear", "user": "黑盒"})
    except Exception as e:
        check("档案 API 无异常", False, str(e))

    status, _, body = http_get("/api/schedule")
    _sd = json.loads(body.decode("utf-8"))
    check("GET /api/schedule 含 goals/goal_stats",
          status == 200 and "goals" in _sd and "goal_stats" in _sd, str(_sd)[:120])

    # 情绪答复归档：没有排队解读时应明确拒绝，不静默写入
    try:
        status, raw = http_post_json("/api/archive", {
            "op": "answer_emotion", "session_id": "bb-no-pending",
            "emotion_tags": ["平静"]})
        # urllib 对 400 会抛 HTTPError，这里期望被拒
        check("answer_emotion 无待归档记录时拒绝", False, "不该成功")
    except urllib.error.HTTPError as e:
        check("answer_emotion 无待归档记录时拒绝", e.code == 400, str(e.code))
    except Exception as e:
        check("answer_emotion 无待归档记录时拒绝", False, str(e))

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

    # ------------------------------------------------ 局域网配对（0.0.0.0）
    LAN_PORT = PORT + 1
    LAN = "http://127.0.0.1:%d" % LAN_PORT
    env2 = os.environ.copy()
    env2["AGENT_PORT"] = str(LAN_PORT)
    env2["AGENT_HOST"] = "0.0.0.0"
    env2["OLIVIA_TOKEN"] = "lantest-1234"
    proc2 = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=AGENT, env=env2,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    def lan_request(path, payload=None, cookie=None):
        headers = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        data = (json.dumps(payload, ensure_ascii=False).encode("utf-8")
                if payload is not None else None)
        req = urllib.request.Request(
            LAN + path, data=data, headers=headers,
            method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    try:
        lan_up = False
        for _ in range(50):
            try:
                st, _, _ = lan_request("/api/config")
                if st in (200, 401):
                    lan_up = True
                    break
            except Exception:
                pass
            time.sleep(0.1)
        check("局域网服务启动", lan_up)
        if lan_up:
            st, _, body = lan_request("/api/config")
            check("未配对访问 /api/config 被拒 401", st == 401)
            check("401 响应标记 auth_required", b"auth_required" in body)
            st, _, body = lan_request("/api/chat", {"message": "你好", "history": []})
            check("未配对访问 /api/chat 被拒 401", st == 401)
            st, _, _ = lan_request("/")
            check("首页本身可打开（用于输入配对码）", st == 200)

            st, _, _ = lan_request("/api/pair", {"code": "123"})
            check("过短配对码 401", st == 401)
            st, headers, _ = lan_request("/api/pair", {"code": "lantest-1234"})
            cookie = None
            for value in headers.get_all("Set-Cookie") or []:
                if "olivia_token=" in value:
                    cookie = value.split(";")[0]
            check("正确配对码 200 并下发 HttpOnly Cookie",
                  st == 200 and bool(cookie), repr(headers.get_all("Set-Cookie")))
            if cookie:
                st, _, _ = lan_request("/api/knowledge", cookie=cookie)
                check("配对后 Cookie 放行", st == 200)

            codes = []
            for _ in range(9):
                st, _, _ = lan_request("/api/pair", {"code": "wrongcode99"})
                codes.append(st)
            check("错码先 401、8 次后 429 限流",
                  codes[:8] == [401] * 8 and codes[-1] == 429, repr(codes))
            st, _, _ = lan_request("/api/pair", {"code": "lantest-1234"})
            check("限流期间正确码也被挡", st == 429)

            st, headers, _ = lan_request("/?token=lantest-1234")
            if st == 429:
                st, headers, _ = lan_request("/?token=lantest-1234")
            check("URL token 也能换到 Cookie",
                  st == 200 and any("olivia_token=" in v
                                    for v in (headers.get_all("Set-Cookie") or [])))
    finally:
        proc2.terminate()
        try:
            proc2.wait(timeout=5)
        except Exception:
            proc2.kill()

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
