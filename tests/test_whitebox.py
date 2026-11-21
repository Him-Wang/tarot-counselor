"""
白盒自查：纯函数/模块级别，不需要起服务、不需要 API key。

覆盖：
  · safety.py  危机闸门（正例/反例/否定/梦境/优先级）
  · provider.py 协议识别 + Anthropic/Gemini 消息与工具转换
  · spreads.py  39 牌阵布局完整性（格数=牌位数、格坐标不重叠）
  · tools.py    抽牌不放回、逆位随机、牌意随牌返回
  · memory.py   危机文本不入库
  · server.py   可导入、配置白名单含 protocol、安全闸门源码位置

运行： python tests/test_whitebox.py
"""

import os
import sys
import json
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(os.path.dirname(HERE), "agent")
sys.path.insert(0, AGENT)

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


def section(title):
    print("\n== %s ==" % title)


# ---------------------------------------------------------------- safety
section("safety.py 危机闸门")
safety = importlib.import_module("safety")
CRISIS_CASES = [
    ("我不想活了，帮我抽牌", "self"),
    ("帮我抽三张，我想死", "self"),
    ("我被他打了", "threat"),
    ("我男朋友打我了", "threat"),
    ("他打我了", "threat"),
    ("我老公昨晚打了我一巴掌", "threat"),
    ("我室友偷我东西还威胁我", "threat"),
    ("我撑不下去了", "self"),
    ("我不会自杀的", None),
    ("我没有想死", None),
    ("我想死你了", None),
    ("奶奶上个月走了", None),
    ("我很想打球", None),
    ("我被家暴了", "threat"),
    ("他扬言要杀了我", "threat"),
    ("我梦到有人追杀我", None),
    ("我想杀了那个伤害我的人", "harm-others"),
    ("我被人强奸了", "sexual-assault"),
]
for text, want in CRISIS_CASES:
    check("detect(%r) == %r" % (text, want), safety.detect(text) == want,
          "got %r" % safety.detect(text))
for kind in ("self", "threat", "sexual-assault", "harm-others",
             "sexual-harm", "unknown"):
    resp = safety.response_for(kind)
    check("response_for(%s) 含求助资源" % kind,
          ("110" in resp or "120" in resp or "热线" in resp) and "占卜" in resp)


# --------------------------------------------------------------- provider
section("provider.py 多协议适配")
provider = importlib.import_module("provider")
check("auto 识别 anthropic",
      provider.detect_protocol({"base_url": "https://api.anthropic.com/v1"}) == "anthropic")
check("auto 识别 gemini",
      provider.detect_protocol({"base_url": "https://generativelanguage.googleapis.com/v1beta"}) == "gemini")
check("auto 识别 openai",
      provider.detect_protocol({"base_url": "https://api.deepseek.com/v1"}) == "openai")
check("显式 protocol 优先",
      provider.detect_protocol({"protocol": "anthropic", "base_url": "https://api.deepseek.com/v1"}) == "anthropic")

msgs = [
    {"role": "system", "content": "你是 Olivia"},
    {"role": "user", "content": "帮我抽牌"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"id": "tc1", "type": "function",
         "function": {"name": "draw_cards", "arguments": '{"spread":"三张"}'}}]},
    {"role": "tool", "tool_call_id": "tc1", "content": '{"ok":true,"cards":[]}'},
]
sys_a, msgs_a = provider._anthropic_messages(msgs)
check("Anthropic system 独立", sys_a == "你是 Olivia", repr(sys_a))
check("Anthropic tool_use 块存在",
      any(b.get("type") == "tool_use" for m in msgs_a if m["role"] == "assistant"
          for b in m["content"]))
check("Anthropic tool_result 嵌 user",
      any(b.get("type") == "tool_result" for m in msgs_a if m["role"] == "user"
          for b in m["content"]))
sys_g, contents_g = provider._gemini_contents(msgs)
check("Gemini systemInstruction 独立", sys_g == "你是 Olivia", repr(sys_g))
check("Gemini functionCall 存在",
      any("functionCall" in p for m in contents_g if m["role"] == "model"
          for p in m["parts"]))
check("Gemini functionResponse 存在",
      any("functionResponse" in p for m in contents_g if m["role"] == "user"
          for p in m["parts"]))

TOOLS = [{"type": "function", "function": {
    "name": "draw_cards", "description": "抽牌",
    "parameters": {"type": "object", "properties": {"spread": {"type": "string"}}}}}]
check("Anthropic tools 转换",
      provider._anthropic_tools(TOOLS)[0]["input_schema"]["type"] == "object")
check("Gemini tools 转换",
      provider._gemini_tools(TOOLS)[0]["functionDeclarations"][0]["name"] == "draw_cards")


# --------------------------------------------------------------- spreads
section("spreads.py 牌阵布局")
spreads = importlib.import_module("spreads")
spread_list = spreads.list_spreads()
check("牌阵数量 >= 39", len(spread_list) >= 39, "got %d" % len(spread_list))
bad_cells = []
for s in spread_list:
    name = s["name"]
    lay = spreads.layout(name)
    n = len(s["positions"])
    cells = lay["cells"]
    if len(cells) != n:
        bad_cells.append("%s: cells %d != positions %d" % (name, len(cells), n))
        continue
    # 第三项 90 = 横放的「交叉牌」，传统上压在中心牌上（凯尔特十字/命运模式），
    # 属于刻意设计；只有完全相同的 (col,row,rot) 才算真重叠。
    coords = [tuple(c) for c in cells]
    if len(set(coords)) != len(coords):
        bad_cells.append("%s: 重叠格 %r" % (name, coords))
check("全部牌阵格数=牌位数且无意外重叠", not bad_cells, "; ".join(bad_cells[:5]))
check("指引之星七格不重叠",
      len(set(tuple(c[:2]) for c in spreads.layout("指引之星")["cells"])) == 7)


# ----------------------------------------------------------------- tools
section("tools.py 抽牌")
tools = importlib.import_module("tools")
result = tools.draw_cards("凯尔特十字", "测试")
check("抽牌成功", result.get("ok"), str(result)[:200])
names = [c["name"] for c in result["cards"]]
check("不放回（无重复牌）", len(names) == len(set(names)), str(names))
check("牌位数=10（凯尔特十字）", len(result["cards"]) == 10)
check("每张牌带牌意", all(c.get("meaning") for c in result["cards"]))
check("带几何布局", bool(result.get("layout", {}).get("cells")))


# --------------------------------------------------------------- memory
section("memory.py 危机不入库")
memory = importlib.import_module("memory")
check("memory 走统一闸门 self", memory.is_crisis_text("我不想活了"))
check("memory 走统一闸门 threat", memory.is_crisis_text("他打我了"))
check("memory 否定放行", not memory.is_crisis_text("我不会自杀的"))
check("add_fact 拒危机文本", memory.add_fact("fact", "我想自杀") is False)


# --------------------------------------------------------------- server
section("server.py 集成点")
server_src = open(os.path.join(AGENT, "server.py"), encoding="utf-8").read()
check("导入 safety 闸门", "import safety as _safety" in server_src)
check("导入 provider 适配层", "import provider" in server_src)
check("闸门在视觉桥之前",
      server_src.find("安全闸门（服务端权威）") < server_src.find("vision bridge"))
check("闸门在抽牌分支之前",
      server_src.find("安全闸门（服务端权威）") < server_src.find("两阶段抽牌：选阵"))
check("已切换到 provider.stream_chat_events",
      "provider.stream_chat_events" in server_src)
check("配置白名单含 protocol", '"protocol"' in server_src)


print("\n" + "=" * 46)
print("白盒自查：%d 通过 / %d 失败" % (PASS, FAIL))
print("=" * 46)
sys.exit(1 if FAIL else 0)
