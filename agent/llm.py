"""
llm.py — OpenAI-compatible streaming chat client (stdlib only).

Supports Ollama (/v1) and DeepSeek (/v1), or any endpoint exposing
POST {base_url}/chat/completions with the OpenAI chat schema.
"""

import json
import urllib.request
import urllib.error


def _normalize_base(base_url):
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url 为空，请在设置里填写接口地址")
    if not base.endswith("/v1"):
        # keep arbitrary compatible endpoints as-is, but append /v1 for the
        # well-known Ollama / DeepSeek hosts when the user omitted it.
        if "127.0.0.1" in base or "localhost" in base or "api.deepseek.com" in base:
            base += "/v1"
    return base


def stream_chat(messages, cfg):
    """Yield assistant text tokens as they arrive.

    messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
    cfg: dict with base_url, api_key, model, temperature, timeout
    """
    url = _normalize_base(cfg.get("base_url", "")) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": True,
    }
    headers = {"Content-Type": "application/json"}
    api_key = (cfg.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = "Bearer " + api_key

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        resp = urllib.request.urlopen(req, timeout=float(cfg.get("timeout", 120)))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:800]
        except Exception:
            pass
        raise RuntimeError("HTTP %s %s\n%s" % (e.code, e.reason, body))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接接口：%s" % e.reason)

    with resp:
        for raw in resp:
            try:
                line = raw.decode("utf-8", "replace").strip()
            except Exception:
                continue
            if not line or not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except Exception:
                continue
            try:
                delta = obj["choices"][0]["delta"].get("content")
            except Exception:
                delta = None
            if delta:
                yield delta


def check(cfg):
    """Non-streaming smoke test: send one tiny message, return reply text."""
    url = _normalize_base(cfg.get("base_url", "")) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": "只回复两个字：在线"}],
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    api_key = (cfg.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=float(cfg.get("timeout", 60)))
        obj = json.loads(resp.read().decode("utf-8", "replace"))
        return obj["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError("HTTP %s: %s" % (e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接接口：%s" % e.reason)
