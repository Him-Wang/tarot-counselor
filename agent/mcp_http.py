# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""mcp_http.py — MCP Streamable HTTP 传输（spec 2025-03-26），零依赖。

与 stdio 版共用同一份 JSON-RPC 分发逻辑（mcp_server.handle_message），
因此工具集、权限边界、错误码完全一致：默认只读，OLIVIA_MCP_WRITES=1
才开放同一份白名单，不新增任何写入能力。

启动：

    python agent/mcp_http.py
    # MCP_HTTP_HOST=0.0.0.0 MCP_HTTP_PORT=9000 python agent/mcp_http.py

端点（默认 http://127.0.0.1:8766）：
    POST /mcp     JSON-RPC 2.0（单条或 batch）。Accept 含 text/event-stream
                  时以 SSE 回 `event: message` / `data: <json>`；否则回 JSON。
                  纯通知返回 202 Accepted、无响应体。
    GET  /mcp     405（本实现 stateless，不提供服务端主动推送的 SSE 流）
    DELETE /mcp   405（无会话可终止）
    OPTIONS       204 CORS 预检
    GET  /health  {"status":"ok","transport":"streamable-http"}

安全：默认只绑定回环地址 127.0.0.1；绑定 0.0.0.0 / :: 时打印警告。
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import mcp_server  # noqa: E402  (sys.path 注入之后才能导入)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766

CORS_ALLOW_HEADERS = "Content-Type, Accept, Mcp-Session-Id, Authorization"


class MCPRequestHandler(BaseHTTPRequestHandler):
    """把 JSON-RPC 消息转发给 mcp_server.handle_message 的 HTTP 适配器。"""

    server_version = "OliviaMCP-HTTP/1.0"
    # 每个响应都带 Content-Length（SSE 用 Connection: close），可以安全长连接。
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------ helpers
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                         "POST, GET, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send(self, status, body=b"", content_type=None, extra_headers=None):
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_json(self, status, obj, extra_headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json", extra_headers)

    def _send_sse(self, responses):
        """一次性发完所有 JSON-RPC 响应，然后关闭连接（无会话、无长流）。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self._cors_headers()
        self.end_headers()
        for resp in responses:
            data = json.dumps(resp, ensure_ascii=False)
            self.wfile.write(
                ("event: message\ndata: %s\n\n" % data).encode("utf-8"))
        self.wfile.flush()
        self.close_connection = True

    def _path(self):
        return self.path.split("?", 1)[0].rstrip("/") or "/"

    def _wants_sse(self):
        return "text/event-stream" in self.headers.get("Accept", "")

    def log_message(self, fmt, *args):
        logging.debug("mcp_http: " + fmt, *args)

    # ------------------------------------------------------------ routes
    def do_POST(self):
        if self._path() != "/mcp":
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""

        msg = None
        is_batch = False
        try:
            msg = json.loads(raw.decode("utf-8"))
            is_batch = isinstance(msg, list)
            items = msg if is_batch else [msg]
            responses = [r for r in (mcp_server.handle_message(item)
                                     for item in items)
                         if r is not None]
        except Exception:
            responses = [{"jsonrpc": "2.0", "id": None,
                          "error": {"code": -32700, "message": "Parse error"}}]

        # 纯通知（或全是通知的 batch）：202 Accepted，无响应体。
        if not responses:
            self._send(202)
            return

        if self._wants_sse():
            self._send_sse(responses)
        else:
            self._send_json(200, responses if is_batch else responses[0])

    def do_GET(self):
        path = self._path()
        if path == "/health":
            self._send_json(200, {"status": "ok",
                                  "transport": "streamable-http"})
        elif path == "/mcp":
            self._send_json(
                405, {"error": "GET not supported; stateless transport uses POST"},
                {"Allow": "POST"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_DELETE(self):
        if self._path() == "/mcp":
            self._send_json(405, {"error": "no sessions to delete"},
                            {"Allow": "POST"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_OPTIONS(self):
        # CORS 预检：204 + CORS 头，无响应体。
        self._send(204)


def create_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """创建（不启动）ThreadingHTTPServer；port=0 可选系统分配的空闲端口。"""
    return ThreadingHTTPServer((host, port), MCPRequestHandler)


def main():
    host = os.environ.get("MCP_HTTP_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    raw_port = os.environ.get("MCP_HTTP_PORT", str(DEFAULT_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        port = DEFAULT_PORT

    if host in ("0.0.0.0", "::"):
        logging.warning(
            "MCP HTTP transport bound to %s (all interfaces): "
            "expose /mcp only behind authentication/TLS.", host)

    server = create_server(host, port)
    logging.info("Olivia MCP Streamable HTTP listening on http://%s:%d/mcp",
                 host, server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    main()
