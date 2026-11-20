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
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import llm
import knowledge
import memory
import tools
import scheduler
import watchers
import plugin_kb
import plugin_vision

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PERSONA_PATH = os.path.join(REPO_DIR, "prompts", "persona.zh.md")
PROPHECY_PATH = os.path.join(REPO_DIR, "prompts", "prophecy.zh.md")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")

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
    "custom": {
        "base_url": "",
        "api_key": "",
        "model": "",
        "note": "任意 OpenAI 兼容端点，自行填写 base_url / model / api key。",
    },
}

DEFAULT_CONFIG = {
    "backend": "deepseek-flash",
    "base_url": PRESETS["deepseek-flash"]["base_url"],
    "api_key": "",
    "model": PRESETS["deepseek-flash"]["model"],
    "temperature": 0.8,
    "timeout": 120,
    "tools_enabled": True,
    "memory_enabled": True,
    "prophecy_enabled": False,
}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_persona():
    try:
        with open(PERSONA_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "你是一名沉稳、专业的塔罗咨询师 Olivia（奥莉薇娅）。"


def load_prophecy():
    """预言模式覆盖层（仅供娱乐），仅在开启时加载。"""
    try:
        with open(PROPHECY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def mask(cfg):
    out = dict(cfg)
    k = out.get("api_key", "")
    out["api_key_set"] = bool(k)
    out["api_key"] = (k[:6] + "…" + k[-4:]) if len(k) > 10 else ("****" if k else "")
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # quiet

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except Exception:
            return {}

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            try:
                with open(INDEX_HTML, "rb") as f:
                    body = f.read()
            except Exception:
                body = b"<h1>index.html missing</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif p == "/api/config":
            self._send_json({
                "config": mask(load_config()),
                "presets": PRESETS,
                "docs": knowledge.list_docs(),
            })
        elif p == "/api/knowledge":
            self._send_json({"docs": knowledge.list_docs()})
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

        if p == "/api/config":
            cfg = load_config()
            for k in ("backend", "base_url", "api_key", "model", "temperature", "timeout",
                      "think", "tools_enabled", "memory_enabled", "prophecy_enabled"):
                if k in body:
                    cfg[k] = body[k]
            # don't overwrite a saved key with the masked display string
            if isinstance(body.get("api_key"), str) and "…" in body["api_key"]:
                cfg["api_key"] = load_config().get("api_key", "")
            save_config(cfg)
            self._send_json({"ok": True, "config": mask(cfg)})

        elif p == "/api/test":
            cfg = load_config()
            # allow testing with a key supplied inline in this request
            if body.get("api_key"):
                cfg["api_key"] = body["api_key"]
            try:
                reply = llm.check(cfg)
                self._send_json({"ok": True, "reply": reply})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)})

        elif p == "/api/chat":
            message = body.get("message", "")
            history = body.get("history", [])
            images = body.get("images", [])  # list of data URLs from the UI
            cfg = load_config()
            if body.get("api_key"):
                cfg["api_key"] = body["api_key"]

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
                        vision_ctx += "【图片识别失败：%s】\n" % ve

            # explicit "forget" command -> handled locally, streamed as a reply
            import re as _re
            preset_reply = None
            if _re.search(r"(忘掉|忘记|删掉|清除)(刚才|刚刚|前面|上次)?(说的|记的|记住的|这段|这些|线索)", message) \
                    or _re.search(r"忘掉刚才|忘记刚才", message):
                n = memory.forget_recent(3)
                preset_reply = ("好，我已经忘掉最近记下的 %d 条线索。" % n) if n \
                    else "我这边没有找到刚记下的内容。"

            # retrieve relevant knowledge for this turn
            context, used = knowledge.retrieve(message)
            system = load_persona()
            # 预言模式（仅供娱乐）：手动开启时才追加覆盖层，安全边界不放开
            if cfg.get("prophecy_enabled", False):
                prophecy = load_prophecy()
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
            if use_tools:
                system += "\n\n---\n" + tools.TOOL_GUIDE
            msgs = [{"role": "system", "content": system}]
            for h in history[-20:]:
                msgs.append({"role": h.get("role", "user"), "content": h.get("content", "")})
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
                full = []
                if preset_reply is not None:
                    full.append(preset_reply)
                    emit({"token": preset_reply})
                else:
                    # ---- agentic loop: model <-> tools until no tool call ----
                    MAX_ROUNDS = 6
                    for _round in range(MAX_ROUNDS):
                        round_calls = []
                        final_content = ""
                        for ev in llm.stream_chat_events(
                                msgs, cfg, tools=tools.TOOLS if use_tools else None):
                            if ev["type"] == "token":
                                full.append(ev["text"])
                                emit({"token": ev["text"]})
                            elif ev["type"] == "tool_calls":
                                round_calls = ev["calls"]
                            elif ev["type"] == "done":
                                final_content = ev.get("content", "")
                        if not round_calls:
                            break

                        # Build the assistant tool-call message + tool results
                        # in the exact shape the OpenAI protocol expects.
                        tc_payload = []
                        result_msgs = []
                        for c in round_calls:
                            name = c.get("name", "")
                            try:
                                args = json.loads(c["arguments"]) if c.get("arguments") else {}
                            except Exception:
                                args = {}
                            result = tools.execute(name, args)
                            emit({"tool": tools.summary(name, result)})
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
                        msgs.append({
                            "role": "assistant",
                            "content": final_content or "",
                            "tool_calls": tc_payload,
                        })
                        msgs.extend(result_msgs)
                    # ---- end agentic loop ----
                emit({"done": True})
                # persist this turn (rule-based extraction, ~0 ms) after stream
                if cfg.get("memory_enabled", True) and full and preset_reply is None:
                    try:
                        memory.remember(message, "".join(full))
                    except Exception:
                        pass
            except Exception as e:
                payload = json.dumps({"error": str(e)}, ensure_ascii=False)
                self.wfile.write(("data: " + payload + "\n\n").encode("utf-8"))
                self.wfile.flush()
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
    port = int(os.environ.get("AGENT_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    scheduler.start(load_config)
    # PID 文件：供安装包的 uninstall 精确停止本服务（不误杀其它 python server.py）
    pid_path = os.path.join(BASE_DIR, "olivia.pid")
    try:
        with open(pid_path, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    except Exception:
        pid_path = None
    print("Olivia agent running at http://127.0.0.1:%d" % port)
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
