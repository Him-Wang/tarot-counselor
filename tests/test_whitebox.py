# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
白盒自查：纯函数/模块级别，不需要起服务、不需要 API key。

覆盖：
  · safety.py  危机闸门（正例/反例/否定/梦境/优先级）
  · provider.py 协议识别 + Anthropic/Gemini 消息与工具转换
  · spreads.py  39 牌阵布局完整性（格数=牌位数、格坐标不重叠）
  · tools.py    抽牌不放回、逆位随机、牌意随牌返回
  · memory.py   危机文本不入库
  · server.py   可导入、配置白名单含 protocol、安全闸门源码位置
  · auth.py     loopback 判定、配对码生成/复用/校验、失败限流
  · secret_store.py API Key 加密落盘与解密
  · db.py       schema 版本迁移幂等
  · backup.py   导出结构、拒收非法文件、合并导入计数
  · mcp_server.py JSON-RPC 握手、工具调用、错误码、stdio 循环、写入 opt-in 白名单
   · goals.py    目标—状态—下一步 CRUD、建议来源、确认边界、任务/关注关联
   · archive.py  占卜档案追加/按用户主题检索/危机内容拒收

运行： python tests/test_whitebox.py
"""

import io
import os
import sys
import json
import random
import shutil
import tempfile
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(os.path.dirname(HERE), "agent")
sys.path.insert(0, AGENT)

# Windows 控制台默认不是 UTF-8，中文用例名会直接抛 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

# 一键真随机：OS 内核熵，每次不同、不可复现、无 seed
result = tools.draw_cards_random("凯尔特十字", "测试")
check("真随机抽牌成功", result.get("ok"), str(result)[:200])
names = [c["name"] for c in result["cards"]]
check("不放回（无重复牌）", len(names) == len(set(names)), str(names))
check("牌位数=10（凯尔特十字）", len(result["cards"]) == 10)
check("每张牌带牌意", all(c.get("meaning") for c in result["cards"]))
check("带几何布局", bool(result.get("layout", {}).get("cells")))
check("真随机不产生 seed（不可复现）", result.get("seed") is None)
check("真随机标记随机源", bool(result.get("random_source")))
check("真随机每次结果不同",
      [c["name"] for c in result["cards"]] !=
      [c["name"] for c in tools.draw_cards_random("凯尔特十字")["cards"]])

# 手动选牌：来访者挑的牌按顺序落位，正逆位由 seed 决定、可复现
_picked = tools.draw_cards("三张", "手选", picks=[0, 4, 21], seed=7)
check("手选直接采用挑出的牌",
      [c["name"] for c in _picked["cards"]] == ["愚者", "皇帝", "世界"],
      str([c["name"] for c in _picked["cards"]]))
check("手选结果标记 manual", _picked.get("manual") is True)
check("手选仍给正逆位", all(c.get("orientation") in ("正位", "逆位")
                        for c in _picked["cards"]))
check("手选忽略重复与越界下标",
      [c["name"] for c in tools.draw_cards("单张", picks=[3, 3, 99, -1], seed=7)["cards"]] == ["皇后"])
check("同 seed + 同 picks 正逆位可复现",
      [(c["name"], c["orientation"]) for c in tools.draw_cards("三张", "x", picks=[0, 4, 21], seed=42)["cards"]]
      == [(c["name"], c["orientation"]) for c in tools.draw_cards("三张", "x", picks=[0, 4, 21], seed=42)["cards"]])
check("手选默认种子来自系统熵且 < 2^53",
      0 <= tools.draw_cards("单张", picks=[3], seed=None)["seed"] < 2 ** 53)
check("抽牌流不是 MT19937",
      tools._SeedStream(42).getrandbits(64) != random.Random(42).getrandbits(64))
_short = tools.draw_cards("三张", picks=[0])
check("手选张数不足时报错、绝不退回随机", _short.get("ok") is False and "reason" in _short)
check("不传 picks 时手选接口报错", tools.draw_cards("三张").get("ok") is False)


# --------------------------------------------------------------- memory
section("memory.py 危机不入库")
memory = importlib.import_module("memory")
check("memory 走统一闸门 self", memory.is_crisis_text("我不想活了"))
check("memory 走统一闸门 threat", memory.is_crisis_text("他打我了"))
check("memory 否定放行", not memory.is_crisis_text("我不会自杀的"))
check("add_fact 拒危机文本", memory.add_fact("fact", "我想自杀") is False)


# --------------------------------------------------------------- offline
section("offline.py 离线整理降级")
offline = importlib.import_module("offline")
check("空 key 判离线", offline.is_offline({"api_key": ""}))
check("掩码 key 判离线", offline.is_offline({"api_key": "sk-****abcd"}))
check("真实 key 不判离线", not offline.is_offline({"api_key": "sk-real12345"}))
_off_draw = tools.draw_cards_random("三张", "我该不该换工作")
_off_text = offline.compose(_off_draw, "我该不该换工作")
check("整理含【离线整理】标识", "离线整理" in _off_text)
check("整理含牌位名（过去/现在/未来）",
      all(p in _off_text for p in ("过去", "现在", "未来")))
check("整理含传统牌意", "传统牌意" in _off_text)
check("整理标注真随机、无种子", "系统真随机" in _off_text and "无种子" in _off_text)
check("整理不承诺预测", "不预言" in _off_text)
check("整理每张牌都列到", all(c["name"] in _off_text for c in _off_draw["cards"]))
check("chunks 切分保留全部文本",
      "".join(offline.chunks(_off_text)).replace(" ", "") == _off_text.replace(" ", ""))
check("无牌时 compose 有引导", "抽牌" in offline.compose(None))
check("无牌对话引导不越界",
      "离线整理" in offline.compose_chat("你好") and "抽牌" in offline.compose_chat("你好"))


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
check("导入 offline 降级模块", "import offline" in server_src)
check("解读轮接离线降级", "offline.compose(pending_result" in server_src)
check("模型失败也兜底离线", "fell back to offline" in server_src)
check("保存配置走密文", 'disk["api_key_enc"] = secret_store.protect(key)' in server_src)
check("读取配置走解密", 'secret_store.unprotect(enc)' in server_src)
check("解读轮只读工具白名单",
      sorted(t["function"]["name"] for t in tools.READ_TOOLS)
      == ["lookup_card", "search_knowledge"])
check("解读轮只放开只读工具",
      "tools.READ_TOOLS" in server_src and "tools.TOOL_GUIDE_READ" in server_src)
# 占卜档案自动归档：解读完成只排队问情绪，答复后才落库；Olivia 不代选
check("解读轮完成后排队入档", "reading_round and pending_result is not None" in server_src)
check("入档前先问情绪", 'emit({"emotion_ask": True})' in server_src)
check("情绪答复才写档案", 'op == "answer_emotion"' in server_src)
check("情绪只记用户说的词", "e in str(body.get(\"text\") or body.get(\"message\") or \"\")" in server_src)
check("未得答复不入档", "_pending_archive.pop(sid, None)" in server_src)


# ------------------------------------------------------------------ auth
section("auth.py 局域网配对")
auth = importlib.import_module("auth")
check("loopback 不启用配对",
      all(not auth.enabled(h) for h in ("127.0.0.1", "localhost", "::1", "")))
check("局域网地址启用配对",
      all(auth.enabled(h) for h in ("0.0.0.0", "192.168.1.5", "10.0.0.2")))
check("normalize 去掉符号并小写", auth.normalize(" AB-12 34 ") == "ab1234")
check("pretty 8 位码分组", auth.pretty("abcd1234") == "abcd-1234")
check("pretty 长 token 原样", auth.pretty("abcdef123456") == "abcdef123456")
check("verify 正确码通过", auth.verify("abcd1234", "ABCD-1234"))
check("verify 错误码拒绝", not auth.verify("abcd1234", "abcd9999"))
check("verify 过短输入拒绝", not auth.verify("abcd1234", "abcd"))
check("verify 空期望拒绝", not auth.verify("", ""))

_auth_tmp = tempfile.mkdtemp(prefix="olivia-auth-")
try:
    code = auth.load_or_create(_auth_tmp)
    check("自动生成 8 位配对码",
          len(code) == 8 and all(c in "0123456789abcdef" for c in code), code)
    _code_file = os.path.join(_auth_tmp, "data", auth.TOKEN_FILE)
    _saved = open(_code_file, encoding="utf-8").read().strip()
    check("配对码落盘", _saved == code)
    check("二次启动复用同一码", auth.load_or_create(_auth_tmp) == code)
    os.environ["OLIVIA_TOKEN"] = "envtoken1234"
    try:
        check("环境变量优先于文件", auth.load_or_create(_auth_tmp) == "envtoken1234")
    finally:
        os.environ.pop("OLIVIA_TOKEN", None)
finally:
    shutil.rmtree(_auth_tmp, ignore_errors=True)

_th = auth.Throttle(limit=3, window=600)
for _ in range(3):
    _th.fail("1.2.3.4")
check("失败达上限后封锁", _th.blocked("1.2.3.4"))
check("其他 IP 不受影响", not _th.blocked("5.6.7.8"))
_th.clear("1.2.3.4")
check("clear 解除封锁", not _th.blocked("1.2.3.4"))


# ---------------------------------------------------------- secret_store
section("secret_store.py API Key 加密")
ss = importlib.import_module("secret_store")
_enc = ss.protect("sk-test-123456")
check("落盘值不是明文", bool(_enc) and "sk-test-123456" not in _enc, _enc[:24])
check("解密还原", ss.unprotect(_enc) == "sk-test-123456")
check("空值不产生密文", ss.protect("") == "" and ss.unprotect("") == "")
check("损坏密文返回空", ss.unprotect("dpapi:notbase64!!!") == "")
check("旧明文配置原样返回", ss.unprotect("sk-legacy") == "sk-legacy")


# -------------------------------------------------------------------- db
section("db.py schema 迁移")
db = importlib.import_module("db")
_db_tmp = tempfile.mkdtemp(prefix="olivia-db-")
try:
    _db_path = os.path.join(_db_tmp, "sub", "t.db")
    conn = db.connect(_db_path)
    check("connect 自动建父目录", os.path.isfile(_db_path))
    check("connect 打开外键", conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
    check("初始 schema 版本为 0", db.version(conn) == 0)
    _calls = []

    def _m1(c):
        _calls.append(1)
        c.execute("CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT)")

    def _m2(c):
        _calls.append(2)
        c.execute("ALTER TABLE a ADD COLUMN w TEXT")

    check("migrate 升到最新版本", db.migrate(conn, [(1, _m1), (2, _m2)]) == 2)
    check("两步迁移依次执行", _calls == [1, 2], repr(_calls))
    check("迁移后新列可用",
          conn.execute("INSERT INTO a (v, w) VALUES ('x', 'y')").rowcount == 1)
    check("重复 migrate 不重跑",
          db.migrate(conn, [(1, _m1), (2, _m2)]) == 2 and _calls == [1, 2])
    check("ensure 首次建表返回 True",
          db.ensure(conn, 3, "CREATE TABLE b (id INTEGER PRIMARY KEY);") is True)
    check("ensure 幂等返回 False",
          db.ensure(conn, 3, "CREATE TABLE b (id INTEGER PRIMARY KEY);") is False)
    check("user_version 记录为 3", db.version(conn) == 3)
    conn.close()
finally:
    shutil.rmtree(_db_tmp, ignore_errors=True)


# ---------------------------------------------------------------- backup
section("backup.py 全量导出/导入")
backup = importlib.import_module("backup")


class _Mem(object):
    def list_profile(self):
        return [{"key": "name", "value": "小明"}]

    def list_facts(self, limit=200):
        return [{"id": 1, "text": "喜欢猫"}]

    def list_draws(self, limit=50):
        return [{"id": 1, "cards": "[]"}]

    def list_messages(self, limit=5000):
        return []

    def set_profile(self, k, v):
        return True

    def add_fact(self, kind, text, pinned=False):
        return True

    def import_draw(self, spread, cards, question, created_at=""):
        return True

    def import_messages(self, items):
        return 0


class _Kb(object):
    def list_notes(self, limit=200):
        return []

    def add_note(self, title, content, tags="", source="", pinned=False):
        return True


class _Sched(object):
    def list_tasks(self):
        return [{"id": 1, "title": "每日一牌"}]

    def add_task(self, t):
        return True


class _Watch(object):
    def list_watchers(self):
        return []

    def add_watcher(self, w):
        return True


_orig_mods = (backup.memory, backup.plugin_kb, backup.scheduler, backup.watchers)
backup.memory, backup.plugin_kb = _Mem(), _Kb()
backup.scheduler, backup.watchers = _Sched(), _Watch()
_bk_tmp = tempfile.mkdtemp(prefix="olivia-backup-")
try:
    _payload = backup.build(_bk_tmp)
    check("导出带格式与版本",
          _payload["format"] == backup.FORMAT and _payload["version"] == backup.VERSION)
    check("导出 counts 与内容一致",
          _payload["counts"]["profile"] == 1 and _payload["counts"]["tasks"] == 1,
          repr(_payload["counts"]))
    check("导出不含 API Key", "api_key" not in json.dumps(_payload))
    try:
        backup.restore({"format": "other"}, _bk_tmp)
        check("拒收非备份文件", False, "未抛 ValueError")
    except ValueError:
        check("拒收非备份文件", True)
    _counts = backup.restore({
        "format": backup.FORMAT, "version": 1,
        "memory": {"profile": [{"key": "city", "value": "上海"}],
                   "facts": [{"text": "怕黑"}],
                   "draws": [{"cards": ["愚者"]}],
                   "messages": []},
        "notes": [{"title": "n", "content": "c"}],
        "tasks": [{"title": "t"}],
        "watchers": [{"keyword": "k"}],
        "extras": [{"kind": "daily"}],
    }, _bk_tmp)
    check("导入按段计数",
          all(_counts[k] == 1 for k in
              ("profile", "facts", "draws", "notes", "tasks", "watchers", "extras")),
          repr(_counts))
    _extras = os.path.join(_bk_tmp, "data", "extras.jsonl")
    check("extras 追加落盘",
          os.path.exists(_extras) and "daily" in open(_extras, encoding="utf-8").read())
finally:
    backup.memory, backup.plugin_kb, backup.scheduler, backup.watchers = _orig_mods
    shutil.rmtree(_bk_tmp, ignore_errors=True)


# ------------------------------------------------------------ mcp_server
section("mcp_server.py JSON-RPC")
mcp = importlib.import_module("mcp_server")
_init = mcp.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
check("initialize 返回协议版本",
      _init["result"]["protocolVersion"] == mcp.PROTOCOL_VERSION)
check("initialize 声明 tools 能力", "tools" in _init["result"]["capabilities"])
_listed = mcp.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
_names = [t["name"] for t in _listed["result"]["tools"]]
check("tools/list 暴露六个只读工具（默认无写入）",
      _names == ["draw_cards", "lookup_card", "search_knowledge", "list_spreads",
                 "list_goals", "search_archive"],
      repr(_names))
check("默认不暴露写入工具",
      not mcp.WRITES_ENABLED and "goal_add" not in _names
      and "confirm_step" not in _names, repr(_names))
check("写入白名单无确认/推进/删除工具",
      not any(x in mcp.WRITE_ALLOWLIST for x in
              ("confirm_step", "update_goal", "delete_goal", "clear", "delete")))
_gated = mcp.call_tool("goal_add", {"title": "x"})
check("未开启时写入工具被拒",
      _gated.get("ok") is False and "OLIVIA_MCP_WRITES" in _gated.get("reason", ""),
      repr(_gated))
check("未开启时调用写工具仍可达（不会 unknown tool）",
      "unknown tool" not in _gated.get("reason", ""), repr(_gated))
_draw = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "draw_cards",
                                       "arguments": {"spread": "三张"}}})
_dp = json.loads(_draw["result"]["content"][0]["text"])
check("MCP 抽牌返回 3 张", _dp.get("ok") and len(_dp.get("cards", [])) == 3)
check("MCP 抽牌是真随机（无 seed、带随机源）",
      _dp.get("seed") is None and bool(_dp.get("random_source")))
_draw2 = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "draw_cards",
                                        "arguments": {"spread": "三张"}}})
_dp2 = json.loads(_draw2["result"]["content"][0]["text"])
check("MCP 真随机两次结果不同",
      [c["name"] for c in _dp["cards"]] != [c["name"] for c in _dp2["cards"]])
_lookup = mcp.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                              "params": {"name": "lookup_card",
                                         "arguments": {"name": "愚者"}}})
_ltext = _lookup["result"]["content"][0]["text"]
check("MCP 查牌含正逆位", "正位" in _ltext and "逆位" in _ltext)
_search = mcp.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                              "params": {"name": "search_knowledge",
                                         "arguments": {"query": "逆位"}}})
check("MCP 知识检索非空", _search["result"]["isError"] is False)
_spreads = mcp.handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                               "params": {"name": "list_spreads", "arguments": {}}})
check("MCP 牌阵数 >= 39",
      len(json.loads(_spreads["result"]["content"][0]["text"])["spreads"]) >= 39)
_lg = mcp.handle_message({"jsonrpc": "2.0", "id": 10, "method": "tools/call",
                          "params": {"name": "list_goals", "arguments": {}}})
check("MCP list_goals 可读",
      json.loads(_lg["result"]["content"][0]["text"]).get("ok") is True)
_sa = mcp.handle_message({"jsonrpc": "2.0", "id": 11, "method": "tools/call",
                          "params": {"name": "search_archive",
                                     "arguments": {"query": "不存在的词xyz"}}})
check("MCP search_archive 可读",
      json.loads(_sa["result"]["content"][0]["text"]).get("ok") is True)
check("未知方法返回 -32601",
      mcp.handle_message({"jsonrpc": "2.0", "id": 8,
                          "method": "nope"})["error"]["code"] == -32601)
check("非法请求返回 -32600",
      mcp.handle_message("hi")["error"]["code"] == -32600)
check("通知不产生响应",
      mcp.handle_message({"jsonrpc": "2.0",
                          "method": "notifications/initialized"}) is None)
_stdin = io.StringIO('{"jsonrpc":"2.0","id":9,"method":"ping"}\n\nnot-json\n')
_stdout = io.StringIO()
mcp.serve(stdin=_stdin, stdout=_stdout)
_lines = [json.loads(l) for l in _stdout.getvalue().strip().splitlines()]
check("stdio 循环处理 ping 与坏行",
      len(_lines) == 2 and _lines[0].get("result") == {}
      and _lines[1]["error"]["code"] == -32700, repr(_lines))


# ---------------------------------------------------------------- goals
section("goals.py 目标—状态—下一步")
goals = importlib.import_module("goals")
_goals_tmp = tempfile.mkdtemp(prefix="olivia-goals-")
_orig_db_path = goals.DB_PATH
_orig_data_dir = goals.DATA_DIR
goals.DB_PATH = os.path.join(_goals_tmp, "goals.db")
goals.DATA_DIR = _goals_tmp

_g1 = goals.add_goal("拿到心理咨询证书", note="明年目标")
check("add_goal 返回 id", bool(_g1), repr(_g1))
check("新目标状态默认 active",
      goals.get_goal(_g1)["status"] == "active")
check("空标题不建目标", goals.add_goal("   ") is None)

goals.set_next_step(_g1, "报名基础课程", source="suggested")
_g = goals.get_goal(_g1)
check("下一步来源 suggested 被保留", _g["next_source"] == "suggested", repr(_g))
goals.set_next_step(_g1, "本周先查好报名条件", source="user")
check("下一步来源 user 被保留",
      goals.get_goal(_g1)["next_source"] == "user")
# 非法来源被强制归一成 user
goals.set_next_step(_g1, "自己定一步", source="hacker")
check("非法来源归一为 user",
      goals.get_goal(_g1)["next_source"] == "user")

_summary = goals.summary_for_prompt()
check("目标摘要含标题", "拿到心理咨询证书" in _summary, repr(_summary))
check("目标摘要标注来源", "你自己定下的下一步" in _summary, repr(_summary))

# 关联 task / watcher
goals.link(_g1, "task", 12)
goals.link(_g1, "watcher", 7)
check("link 到 task 生效",
      any(l["kind"] == "task" and l["ref_id"] == 12
          for l in goals.list_goals()[0]["links"]))
check("goals_for(watcher) 命中",
      any(g["id"] == _g1 for g in goals.goals_for("watcher", 7)))
check("非法 link kind 被拒", not goals.link(_g1, "bogus", 1))
goals.unlink(_g1, "watcher", 7)
check("unlink 生效", not goals.goals_for("watcher", 7))

# 确认边界：confirm_step 把下一步写入完成历史并清空
goals.set_next_step(_g1, "听完第一节课", source="suggested")
check("confirm_step 返回 True", goals.confirm_step(_g1))
_g = goals.get_goal(_g1)
check("确认后下一步清空", _g["next_step"] == "" and _g["next_source"] == "", repr(_g))
check("确认后进入完成步骤历史",
      any(s["text"] == "听完第一节课"
          for s in goals.list_goals()[0]["steps"]))
check("空下一步 confirm 返回 False", not goals.confirm_step(_g1))

goals.update_goal(_g1, {"status": "done"})
check("update_goal 改状态", goals.get_goal(_g1)["status"] == "done")
check("摘要只含 active/paused 目标", "拿到心理咨询证书" not in goals.summary_for_prompt())

_g2 = goals.add_goal("另一目标")
goals.delete_goal(_g1)
check("delete_goal 移除目标", goals.get_goal(_g1) is None)
check("删除后级联清理 steps/links",
      all(g["id"] != _g1 for g in goals.list_goals()))

goals.DB_PATH = _orig_db_path
goals.DATA_DIR = _orig_data_dir
shutil.rmtree(_goals_tmp, ignore_errors=True)


# -------------------------------------------------------------- archive
section("archive.py 占卜档案")
archive = importlib.import_module("archive")
_arc_tmp = tempfile.mkdtemp(prefix="olivia-archive-")
_orig_arc_dir = archive.ARCHIVE_DIR
archive.ARCHIVE_DIR = _arc_tmp

_aid = archive.append("小林", "工作要不要跳槽", "三张", "牌面提示先看清自己的需求",
                      emotion_tags=["迷茫", "焦虑", "自定义情绪"],
                      cards=["愚者", "圣杯二", "宝剑三"])
check("append 返回 id", bool(_aid), repr(_aid))
_a = archive.search(user="小林")[0]
check("档案含时间", bool(_a.get("created_at")))
check("档案含问题/牌阵/要点",
      _a["question"] == "工作要不要跳槽" and _a["spread"] == "三张"
      and "需求" in _a["points"])
check("档案含牌面", len(_a["cards"]) == 3)
check("情绪标签含已知词", "迷茫" in _a["emotion_tags"] and "焦虑" in _a["emotion_tags"])
check("自定义情绪词被保留", "自定义情绪" in _a["emotion_tags"], repr(_a["emotion_tags"]))

archive.append("小林", "感情走向", "凯尔特十字", "沟通是关键", emotion_tags=["期待"])
archive.append("阿明", "考试结果", "单张", "专注当下", emotion_tags=["平静"])
check("按用户检索只返回该用户",
      all(r["user"] == "小林" for r in archive.by_user("小林", limit=10))
      and len(archive.by_user("小林", limit=10)) == 2)
check("按主题检索命中",
      any(r["question"] == "感情走向" for r in archive.by_topic("沟通", limit=10)))
check("全文检索命中", len(archive.search(query="考试", limit=10)) == 1)
check("危机问题不入库（安全闸门）",
      archive.append("小林", "我想伤害自己", "单张", "解读") is None
      and len(archive.search(query="伤害自己", limit=10)) == 0)
check("stats 统计用户数", archive.stats() == {"total": 3, "users": 2}, repr(archive.stats()))
check("clear(user) 只清该用户", archive.clear("小林") and archive.stats()["total"] == 1)

archive.ARCHIVE_DIR = _orig_arc_dir
shutil.rmtree(_arc_tmp, ignore_errors=True)


# ---------------------------------------------------------------- knowledge (English mirror)
section("knowledge.py 英文知识库 / 语言感知加载")
knowledge = importlib.import_module("knowledge")
_REPO = os.path.dirname(HERE)
_EN_ROOT = os.path.join(_REPO, "knowledge", "en")

check("英文根目录存在", os.path.isdir(_EN_ROOT))
_EN_REQUIRED = [
    "INDEX.md",
    "meanings/major-arcana.md", "meanings/wands.md", "meanings/cups.md",
    "meanings/swords.md", "meanings/pentacles.md", "meanings/card-relationships.md",
    "meanings/reading-methods.md",
    "readings/reading-flow.md", "readings/single-card-deep-read.md",
    "readings/reversed-cards.md", "readings/court-cards.md",
    "ethics/crisis-and-referral.md", "skills/empathic-listening.md",
    "spreads/spreads-quick-reference.md",
    "occult/INDEX.md", "occult/symbol-correspondences.md",
    "occult/channeling-and-ritual.md",
]
_missing = [p for p in _EN_REQUIRED if not os.path.isfile(os.path.join(_EN_ROOT, *p.split("/")))]
check("英文文档覆盖所有关键类别", not _missing, "missing: %s" % ", ".join(_missing))

# Every English file carries the required headers.
_bad_headers = []
for _rp in _EN_REQUIRED:
    with open(os.path.join(_EN_ROOT, * _rp.split("/")), "r", encoding="utf-8") as _f:
        _head = _f.read(400)
    if ("SPDX-License-Identifier: CC-BY-NC-SA-4.0" not in _head
            or "Copyright (c) 2026 Him-Wang" not in _head):
        _bad_headers.append(_rp)
check("英文文件带 SPDX 与版权头", not _bad_headers, "bad: %s" % ", ".join(_bad_headers))

_en_docs = knowledge.list_docs(lang="en")
check("list_docs(lang=en) 返回英文路径（相对 en/）",
      bool(_en_docs) and all("en/" not in p and not p.startswith("../") for p in _en_docs)
      and "meanings/major-arcana.md" in _en_docs, repr(_en_docs[:5]))
check("list_docs(lang=en)  occult 默认过滤",
      not any(p.startswith("occult/") for p in _en_docs))
check("list_docs(lang=en, include_occult=True) 含 occult",
      any(p.startswith("occult/") for p in knowledge.list_docs(include_occult=True, lang="en")))
_zh_docs = knowledge.list_docs()
check("无 lang 时仍是中文库路径",
      any("大阿卡纳" in p for p in _zh_docs)
      and not any("major-arcana" in p for p in _zh_docs), repr(_zh_docs[:5]))

_ctx_en, _used_en = knowledge.search("empathic listening counterexamples", lang="en")
check("英文 query 命中英文文档",
      bool(_ctx_en) and bool(_used_en) and "empathic-listening" in " ".join(_used_en), repr(_used_en))
check("英文检索使用英文分词",
      "reversed" in knowledge._tokens("Reversed, COURTS!", lang="en"))
check("中文分词路径不变",
      "逆位" in knowledge._tokens("逆位读法"))

check("_doc_root(en/zh/None) 正确",
      knowledge._doc_root("en").endswith(os.path.join("knowledge", "en"))
      and knowledge._doc_root("zh") == os.path.join(_REPO, "knowledge")
      and knowledge._doc_root() == os.path.join(_REPO, "knowledge"))

check("get_card_entry(en) 读到英文牌义",
      "新" in knowledge.get_card_entry("The Fool", lang="en")["core"]
      or "begin" in knowledge.get_card_entry("The Fool", lang="en")["core"].lower(),
      repr(knowledge.get_card_entry("The Fool", lang="en")))
check("get_card_meaning(en, Upright) 输出英文标签",
      "Upright:" in knowledge.get_card_meaning("The Fool", "Upright", lang="en"),
      repr(knowledge.get_card_meaning("The Fool", "Upright", lang="en")))
_zh_entry = knowledge.get_card_entry("愚者")
check("get_card_entry 无 lang 时仍是中文内容",
      bool(_zh_entry["core"]) and "核心" not in _zh_entry["core"], repr(_zh_entry))

print("\n" + "=" * 46)
print("白盒自查：%d 通过 / %d 失败" % (PASS, FAIL))
print("=" * 46)
sys.exit(1 if FAIL else 0)
