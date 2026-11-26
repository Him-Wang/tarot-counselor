# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Streamable HTTP 传输的黑盒自查：起临时端口的真实 HTTP 服务，用 stdlib 发请求。

覆盖：initialize / tools/list / tools/call / SSE / 通知 202 / CORS 预检 /
GET+DELETE 405 / 默认只读（写工具不可见）、以及端口与关闭的生命周期。

运行： python tests/test_mcp_http.py
退出码：全部 PASS 为 0，有 FAIL 为 1。
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(os.path.dirname(HERE), "agent")
sys.path.insert(0, AGENT)

# Windows 控制台默认不是 UTF-8，中文用例名会直接抛 UnicodeEncodeError。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 权限边界从环境变量在 import 时确定；这里显式关掉写入，断言默认只读。
os.environ.pop("OLIVIA_MCP_WRITES", None)

import mcp_http  # noqa: E402  (sys.path 注入之后才能导入)

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


# --------------------------------------------------------------- start
server = mcp_http.create_server("127.0.0.1", 0)
PORT = server.server_address[1]
BASE = "http://127.0.0.1:%d" % PORT
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

try:
    # ----------------------------------------------------------- helpers
    def request(method, path, data=None, headers=None):
        req = urllib.request.Request(
            BASE + path, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def post(obj, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        return request("POST", "/mcp", body, hdrs)

    section("GET /health")
    status, headers, body = request("GET", "/health")
    health = json.loads(body.decode("utf-8"))
    check("health 200", status == 200)
    check("health 内容", health == {"status": "ok",
                                    "transport": "streamable-http"}, repr(health))

    section("POST /mcp JSON-RPC")
    status, headers, body = post({"jsonrpc": "2.0", "id": 1,
                                  "method": "initialize"})
    init = json.loads(body.decode("utf-8"))
    check("initialize 200", status == 200)
    check("initialize id 回显", init.get("id") == 1, repr(init))
    check("initialize serverInfo",
          init.get("result", {}).get("serverInfo", {}).get("name") == "olivia-tarot")
    check("initialize 声明 tools 能力",
          "tools" in init.get("result", {}).get("capabilities", {}))

    status, headers, body = post({"jsonrpc": "2.0", "id": 2,
                                  "method": "tools/list"})
    listed = json.loads(body.decode("utf-8"))
    names = [t["name"] for t in listed["result"]["tools"]]
    check("tools/list 200", status == 200)
    check("默认暴露六个只读工具",
          names == ["draw_cards", "lookup_card", "search_knowledge",
                    "list_spreads", "list_goals", "search_archive"], repr(names))
    check("写工具默认不可见", "goal_add" not in names
          and "archive_append" not in names, repr(names))

    status, headers, body = post(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "draw_cards",
                    "arguments": {"spread": "三张"}}})
    draw = json.loads(body.decode("utf-8"))
    payload = json.loads(draw["result"]["content"][0]["text"])
    check("tools/call draw_cards 200", status == 200)
    check("tools/call 返回 3 张牌",
          payload.get("ok") is True and len(payload.get("cards", [])) == 3,
          repr(payload)[:200])
    check("tools/call 抽牌是真随机（无 seed 字段）",
          "seed" not in payload and bool(payload.get("random_source")),
          repr(payload)[:200])

    status, headers, body = post(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "goal_add", "arguments": {"title": "x"}}})
    gated = json.loads(body.decode("utf-8"))
    gated_payload = json.loads(gated["result"]["content"][0]["text"])
    check("写工具仍被服务端闸门拒绝（无新增权力）",
          gated_payload.get("ok") is False
          and "OLIVIA_MCP_WRITES" in gated_payload.get("reason", ""),
          repr(gated_payload))

    section("CORS / SSE / 通知 / 错误")
    check("POST 带 Access-Control-Allow-Origin",
          headers.get("Access-Control-Allow-Origin") == "*")
    check("CORS Allow-Headers 含 Mcp-Session-Id",
          "Mcp-Session-Id" in headers.get("Access-Control-Allow-Headers", ""))
    check("CORS Allow-Headers 含 Content-Type / Accept",
          "Content-Type" in headers.get("Access-Control-Allow-Headers", "")
          and "Accept" in headers.get("Access-Control-Allow-Headers", ""))

    status, _, body = request("OPTIONS", "/mcp")
    check("OPTIONS 预检 204", status == 204)

    status, hdrs, body = post(
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        {"Accept": "application/json, text/event-stream"})
    text = body.decode("utf-8")
    check("SSE 200", status == 200)
    check("SSE Content-Type", "text/event-stream" in hdrs.get("Content-Type", ""))
    check("SSE 含 event/data 帧", "event: message\n" in text
          and '"id": 5' in text, repr(text)[:200])

    status, _, body = post(
        {"jsonrpc": "2.0", "method": "notifications/initialized"})
    check("纯通知 202", status == 202)
    check("纯通知无响应体", body == b"", repr(body))

    status, _, body = post({"jsonrpc": "2.0", "id": 6, "method": "nope"})
    err = json.loads(body.decode("utf-8"))
    check("未知方法 -32601", err["error"]["code"] == -32601)

    status, _, body = request("POST", "/mcp", b"not-json",
                              {"Content-Type": "application/json"})
    err = json.loads(body.decode("utf-8"))
    check("非法 JSON -32700", err["error"]["code"] == -32700)

    section("GET / DELETE / 404")
    status, hdrs, _ = request("GET", "/mcp")
    check("GET /mcp 405", status == 405)
    check("GET /mcp Allow: POST", "POST" in hdrs.get("Allow", ""))
    status, _, _ = request("DELETE", "/mcp")
    check("DELETE /mcp 405", status == 405)
    status, _, _ = request("GET", "/nope")
    check("未知路径 404", status == 404)

finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)

print("\n" + "=" * 46)
print("MCP Streamable HTTP 自查：%d 通过 / %d 失败" % (PASS, FAIL))
print("=" * 46)
sys.exit(1 if FAIL else 0)
