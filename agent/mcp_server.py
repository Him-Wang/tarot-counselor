# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""mcp_server.py — 把本地抽牌/查牌/检索/有限写入暴露成 MCP stdio server。

零依赖，走 JSON-RPC 2.0 换行分隔。Claude Desktop / Cursor / Cherry Studio
等客户端配置：

    {"mcpServers": {"olivia-tarot": {
        "command": "python",
        "args": ["C:/path/to/tarot-counselor/agent/mcp_server.py"]
    }}}

权限边界（重要）：
  * 默认只读——和 1.2.0 之前完全一样，不联网、不写用户数据。
  * 有限写入是**显式 opt-in**：设置环境变量 OLIVIA_MCP_WRITES=1 才开放。
  * 即使开放，白名单里也**没有**删除/清空/确认下一步的工具——
    「确认做到」「推进状态」这类决定只能本人在网页 UI 上做，MCP 客户端
    （另一个 AI）无权替用户拍板。这是 Olivia「不替你决定」底线的延伸。
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
import goals              # noqa: E402
import archive            # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "olivia-tarot", "version": "1.3.0"}

# 有限写入：显式 opt-in，默认关闭。
WRITES_ENABLED = os.environ.get("OLIVIA_MCP_WRITES", "").strip() in ("1", "true", "True", "yes")
# 白名单：都是「新增/提出建议」，绝无删除、清空、确认、推进状态。
WRITE_ALLOWLIST = (
    "save_memory",       # 记一条偏好/线索
    "schedule_reminder",  # 加一个定时关怀
    "goal_add",          # 新建一个目标
    "goal_suggest_step",  # 提出下一步建议（source 强制 suggested）
    "archive_append",    # 追加一条占卜档案
)

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
    {
        "name": "list_goals",
        "description": "列出用户正在推进的目标、状态与下一步（只读）。"
                       "下一步会标注是用户自己定的，还是尚未点头的建议。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_archive",
        "description": "按用户/主题/关键词检索本地占卜档案（只读）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "全文检索词"},
                "topic": {"type": "string", "description": "主题，匹配问题/牌阵/要点/情绪标签"},
                "user": {"type": "string", "description": "限定某个用户的档案"},
                "limit": {"type": "integer", "description": "最多返回几条，默认 20"},
            },
        },
    },
]

WRITE_TOOLS = [
    {
        "name": "save_memory",
        "description": "【需开启写入】记下一条用户偏好/边界/请记住的内容。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "description": "fact/pref/boundary"},
                "text": {"type": "string", "description": "要记住的内容"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "schedule_reminder",
        "description": "【需开启写入】加一个定时关怀任务（到点写消息进收件箱）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"}, "intent": {"type": "string"},
                "kind": {"type": "string", "enum": ["once", "daily", "weekly", "interval"]},
                "run_at": {"type": "string"}, "cron_time": {"type": "string"},
            },
            "required": ["name", "intent", "kind"],
        },
    },
    {
        "name": "goal_add",
        "description": "【需开启写入】新建一个目标（状态固定为进行中，下一步留空由用户自己定）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "目标名称"},
                "note": {"type": "string", "description": "背景备注"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "goal_suggest_step",
        "description": "【需开启写入】为一个目标提出「下一步建议」。"
                       "来源强制标记为 suggested（用户尚未点头），"
                       "不能替用户确认、不能推进状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "目标 id"},
                "text": {"type": "string", "description": "建议的下一步"},
            },
            "required": ["id", "text"],
        },
    },
    {
        "name": "archive_append",
        "description": "【需开启写入】追加一条占卜档案。"
                       "情绪标签仅接受用户亲口确认过的词。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user": {"type": "string"}, "question": {"type": "string"},
                "spread": {"type": "string"}, "points": {"type": "string"},
                "emotion_tags": {"type": "array", "items": {"type": "string"}},
                "cards": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["question", "spread", "points"],
        },
    },
]

if WRITES_ENABLED:
    TOOLS = TOOLS + WRITE_TOOLS


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
    if name == "list_goals":
        return {"ok": True, "goals": goals.list_goals()}
    if name == "search_archive":
        return {"ok": True, "records": archive.search(
            query=str(args.get("query", "")), topic=str(args.get("topic", "")),
            user=str(args.get("user", "")) or None,
            limit=int(args.get("limit", 20) or 20))}

    # ---- 有限写入：opt-in + 白名单 ----
    if name in WRITE_ALLOWLIST:
        if not WRITES_ENABLED:
            return {"ok": False, "reason": "写入工具未开启：设置 OLIVIA_MCP_WRITES=1 后重启 MCP server。"}
        if name == "save_memory":
            return tools.save_memory(str(args.get("kind", "fact")), str(args.get("text", "")))
        if name == "schedule_reminder":
            return tools.schedule_reminder(
                str(args.get("name", "")), str(args.get("intent", "")),
                str(args.get("kind", "once")), str(args.get("run_at", "")),
                str(args.get("cron_time", "09:00")))
        if name == "goal_add":
            gid = goals.add_goal(str(args.get("title", "")), str(args.get("note", "")))
            return {"ok": bool(gid), "id": gid,
                    "note": "目标已建；下一步请你自己定，或由 Olivia 提出建议待你确认。"}
        if name == "goal_suggest_step":
            ok = goals.set_next_step(int(args.get("id", 0)), str(args.get("text", "")),
                                     source="suggested")
            return {"ok": ok, "source": "suggested",
                    "note": "这是建议，尚未确认；只有你能在网页界面确认做到。"}
        if name == "archive_append":
            rid = archive.append(
                str(args.get("user", "")), str(args.get("question", "")),
                str(args.get("spread", "")), str(args.get("points", "")),
                args.get("emotion_tags") or [], args.get("cards") or [])
            return {"ok": bool(rid), "id": rid}
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
    # 默认只读：6 个（原 4 个 + list_goals / search_archive）；开启写入后 +5。
    expected = 11 if WRITES_ENABLED else 6
    assert len(listed["result"]["tools"]) == expected, (
        "工具数 %d != 预期 %d" % (len(listed["result"]["tools"]), expected))
    draw = handle_message({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "draw_cards",
                                      "arguments": {"spread": "三张", "seed": 7}}})
    payload = json.loads(draw["result"]["content"][0]["text"])
    assert payload["ok"] and len(payload["cards"]) == 3
    lookup = handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                             "params": {"name": "lookup_card",
                                        "arguments": {"name": "愚者"}}})
    assert "正位" in lookup["result"]["content"][0]["text"]
    print("mcp self-test ok: %d tools, draw=3 cards, lookup=愚者" % expected)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        serve()
