# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""mcp_server.py — 把本地抽牌/查牌/检索暴露成 MCP stdio server。

零依赖，走 JSON-RPC 2.0 换行分隔。Claude Desktop / Cursor / Cherry Studio
等客户端配置：

    {"mcpServers": {"olivia-tarot": {
        "command": "python",
        "args": ["C:/path/to/tarot-counselor/agent/mcp_server.py"]
    }}}

它只读知识库并本地抽牌，不联网、不读写用户的记忆与配置。
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import knowledge          # noqa: E402
import spreads as spreads_mod  # noqa: E402
import tools              # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "olivia-tarot", "version": "1.1.0"}

TOOLS = [
    {
        "name": "draw_cards",
        "description": "按传统牌阵本地随机抽牌（不放回，可复现）。返回牌位、正逆位、"
                       "传统牌意与布局坐标。抽牌不调用任何模型。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spread": {"type": "string", "description": "牌阵名，如 单张 / 三张 / 凯尔特十字"},
                "question": {"type": "string", "description": "这次想问的问题（可留空）"},
                "seed": {"type": "integer", "description": "复现种子；同一个种子抽出同一副牌"},
            },
        },
    },
    {
        "name": "lookup_card",
        "description": "查一张韦特塔罗牌的传统牌意（正位/逆位）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "牌名，如 愚者 / 圣杯二 / 宝剑骑士"},
                "orientation": {"type": "string", "enum": ["正位", "逆位", "两者"]},
            },
            "required": ["name"],
        },
    },
    {
        "name": "search_knowledge",
        "description": "检索解牌方法、牌间关系、共情式倾听、伦理与转介等本地资料。",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "检索词"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_spreads",
        "description": "列出全部牌阵及其牌位说明。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _text_result(payload, is_error=False):
    return {
        "content": [{"type": "text",
                     "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
        "isError": bool(is_error),
    }


def call_tool(name, arguments):
    args = arguments or {}
    if name == "draw_cards":
        seed = args.get("seed")
        try:
            seed = int(seed) if seed not in (None, "") else None
        except (TypeError, ValueError):
            seed = None
        return tools.draw_cards(str(args.get("spread") or "三张"),
                                str(args.get("question") or ""), seed=seed)
    if name == "lookup_card":
        return tools.lookup_card(str(args.get("name") or ""),
                                 str(args.get("orientation") or "两者"))
    if name == "search_knowledge":
        return tools.search_knowledge(str(args.get("query") or ""))
    if name == "list_spreads":
        return {"ok": True, "spreads": spreads_mod.list_spreads()}
    raise ValueError("unknown tool: %s" % name)


def handle_message(msg):
    """Pure JSON-RPC handler. Returns a response dict, or None for notifications."""
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    method = msg.get("method")
    mid = msg.get("id")
    if method and str(method).startswith("notifications/"):
        return None
    if mid is None and method:
        return None
    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name") or ""
            raw = call_tool(name, params.get("arguments") or {})
            result = _text_result(raw, is_error=not bool(raw.get("ok", True)))
        elif method in ("resources/list", "prompts/list"):
            result = {"resources": []} if method == "resources/list" else {"prompts": []}
        else:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32603, "message": str(e)}}


def serve(stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            out = {"jsonrpc": "2.0", "id": None,
                   "error": {"code": -32700, "message": "Parse error"}}
        else:
            out = handle_message(msg)
        if out is not None:
            stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
            stdout.flush()


def _selftest():
    init = handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init["result"]["serverInfo"]["name"] == "olivia-tarot"
    listed = handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert len(listed["result"]["tools"]) == 4
    draw = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "draw_cards",
                                      "arguments": {"spread": "三张", "seed": 7}}})
    payload = json.loads(draw["result"]["content"][0]["text"])
    assert payload["ok"] and len(payload["cards"]) == 3
    lookup = handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "lookup_card",
                                        "arguments": {"name": "愚者"}}})
    assert "正位" in lookup["result"]["content"][0]["text"]
    print("mcp self-test ok: 4 tools, draw=3 cards, lookup=愚者")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        serve()
