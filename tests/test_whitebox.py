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
  · mcp_server.py JSON-RPC 握手、工具调用、错误码、stdio 循环

运行： python tests/test_whitebox.py
"""

import io
import os
import sys
import json
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


# --------------------------------------------------------------- offline
section("offline.py 离线整理降级")
offline = importlib.import_module("offline")
check("空 key 判离线", offline.is_offline({"api_key": ""}))
check("掩码 key 判离线", offline.is_offline({"api_key": "sk-****abcd"}))
check("真实 key 不判离线", not offline.is_offline({"api_key": "sk-real12345"}))
_off_draw = tools.draw_cards("三张", "我该不该换工作", seed=42)
_off_text = offline.compose(_off_draw, "我该不该换工作")
check("整理含【离线整理】标识", "离线整理" in _off_text)
check("整理含牌位名（过去/现在/未来）",
      all(p in _off_text for p in ("过去", "现在", "未来")))
check("整理含传统牌意", "传统牌意" in _off_text)
check("整理含复现种子", "复现种子：42" in _off_text)
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
check("tools/list 暴露四个工具",
      _names == ["draw_cards", "lookup_card", "search_knowledge", "list_spreads"],
      repr(_names))
_draw = mcp.handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "draw_cards",
                                       "arguments": {"spread": "三张", "seed": 7}}})
_dp = json.loads(_draw["result"]["content"][0]["text"])
check("MCP 抽牌返回 3 张", _dp.get("ok") and len(_dp.get("cards", [])) == 3)
_draw2 = mcp.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "draw_cards",
                                        "arguments": {"spread": "三张", "seed": 7}}})
_dp2 = json.loads(_draw2["result"]["content"][0]["text"])
check("同 seed 抽出同一副牌",
      [c["name"] for c in _dp["cards"]] == [c["name"] for c in _dp2["cards"]])
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


print("\n" + "=" * 46)
print("白盒自查：%d 通过 / %d 失败" % (PASS, FAIL))
print("=" * 46)
sys.exit(1 if FAIL else 0)
