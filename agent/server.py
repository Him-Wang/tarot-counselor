"""
server.py — Olivia agent local web server (Python stdlib only).

Routes:
  GET  /                 web UI
  GET  /api/config       current config (api_key masked) + presets + knowledge docs
  POST /api/config       save config {backend, base_url, api_key, model, temperature, timeout}
  GET  /api/knowledge    list knowledge docs
  POST /api/test         smoke-test current backend
  POST /api/chat         SSE stream: {"message", "history":[...]} -> data: {"token"} ...
"""

import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

import llm
import knowledge

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PERSONA_PATH = os.path.join(REPO_DIR, "prompts", "persona.zh.md")
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
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._body()

        if p == "/api/config":
            cfg = load_config()
            for k in ("backend", "base_url", "api_key", "model", "temperature", "timeout", "think"):
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
            cfg = load_config()
            if body.get("api_key"):
                cfg["api_key"] = body["api_key"]

            # retrieve relevant knowledge for this turn
            context, used = knowledge.retrieve(message)
            system = load_persona()
            if context:
                system += (
                    "\n\n---\n以下是与本次对话相关的专业资料，回答专业判断时以这些资料为准，"
                    "不要臆测；塔罗只用于打开话题与照见感受，风险评估/诊断/干预选择绝不从牌里来。\n\n"
                    + context
                )
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
                self.wfile.write(
                    ("data: " + json.dumps({"meta": used}, ensure_ascii=False) + "\n\n").encode("utf-8")
                )
                self.wfile.flush()
                for token in llm.stream_chat(msgs, cfg):
                    self.wfile.write(
                        ("data: " + json.dumps({"token": token}, ensure_ascii=False) + "\n\n").encode("utf-8")
                    )
                    self.wfile.flush()
                self.wfile.write(b"data: {\"done\": true}\n\n")
                self.wfile.flush()
            except Exception as e:
                payload = json.dumps({"error": str(e)}, ensure_ascii=False)
                self.wfile.write(("data: " + payload + "\n\n").encode("utf-8"))
                self.wfile.flush()
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    port = int(os.environ.get("AGENT_PORT", "8765"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("Olivia agent running at http://127.0.0.1:%d" % port)
    print("Press Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
