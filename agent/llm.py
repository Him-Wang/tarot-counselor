# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
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


def _is_local(base_url):
    """True for loopback endpoints (Ollama in this app)."""
    u = (base_url or "").lower()
    return "127.0.0.1" in u or "localhost" in u


def _extra_options(base_url, cfg):
    """Return extra payload fields for local Ollama endpoints.

    Local reasoning models (e.g. DeepSeek-R1 distilled / dsv4-*-heretic) keep
    thinking ON by default and can burn the entire token budget on invisible
    reasoning, which looks like a hang or timeout. Ollama's OpenAI-compatible
    endpoint honours options.think=false (verified); top-level think and
    num_ctx overrides either don't work or force a slow model reload, so we
    do not touch them here. Remote APIs (DeepSeek etc.) get nothing extra.
    Set cfg["think"] = True to opt back in.
    """
    if _is_local(base_url) and cfg.get("think") is not True:
        return {"options": {"think": False}}
    return {}


def stream_chat(messages, cfg):
    """Yield assistant text tokens as they arrive.

    messages: [{"role": "system"|"user"|"assistant", "content": str}, ...]
    cfg: dict with base_url, api_key, model, temperature, timeout
    """
    raw_base = cfg.get("base_url", "")
    url = _normalize_base(raw_base) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": True,
    }
    payload.update(_extra_options(raw_base, cfg))
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


def stream_chat_events(messages, cfg, tools=None):
    """Streaming chat that also surfaces tool calls.

    Yields event dicts:
      {"type": "token",      "text": <str>}              -- assistant text delta
      {"type": "tool_calls", "calls": [ {id,name,arguments}, ... ]}
      {"type": "done",       "content": <str>, "tool_calls": [...]}

    The caller drives the agentic loop: on "tool_calls", execute each tool,
    append the assistant message (with tool_calls) and {"role":"tool"} results
    to `messages`, then call this generator again for the next turn.
    """
    raw_base = cfg.get("base_url", "")
    url = _normalize_base(raw_base) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    payload.update(_extra_options(raw_base, cfg))
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

    content_parts = []
    calls_by_index = {}

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
                delta = obj["choices"][0].get("delta", {}) or {}
            except Exception:
                delta = {}
            text = delta.get("content")
            if text:
                content_parts.append(text)
                yield {"type": "token", "text": text}
            tool_call_seq = 0
            for tc in (delta.get("tool_calls") or []):
                # m3: some providers omit "index"; use a positional counter so
                # parallel tool calls don't collapse into one merged slot.
                idx = tc.get("index")
                if idx is None:
                    idx = tool_call_seq
                tool_call_seq += 1
                slot = calls_by_index.setdefault(
                    idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]

    calls = []
    for idx in sorted(calls_by_index):
        slot = calls_by_index[idx]
        if slot["name"]:
            calls.append(slot)
    full_content = "".join(content_parts)
    if calls:
        yield {"type": "tool_calls", "calls": calls}
    yield {"type": "done", "content": full_content, "tool_calls": calls}


def complete(messages, cfg):
    """Non-streaming completion for a provided message list. Returns text.

    Used by the proactive scheduler to generate a short message without
    driving a full streaming/agentic loop.
    """
    raw_base = cfg.get("base_url", "")
    url = _normalize_base(raw_base) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": False,
    }
    payload.update(_extra_options(raw_base, cfg))
    headers = {"Content-Type": "application/json"}
    api_key = (cfg.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(cfg.get("timeout", 120))) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
        msg = obj["choices"][0].get("message", {})
        return (msg.get("content") or "")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError("HTTP %s: %s" % (e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接接口：%s" % e.reason)


def check(cfg):
    """Non-streaming smoke test: send one tiny message, return reply text."""
    raw_base = cfg.get("base_url", "")
    url = _normalize_base(raw_base) + "/chat/completions"
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": "只回复两个字：在线"}],
        "stream": False,
    }
    payload.update(_extra_options(raw_base, cfg))
    headers = {"Content-Type": "application/json"}
    api_key = (cfg.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(cfg.get("timeout", 60))) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
        return obj["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError("HTTP %s: %s" % (e.code, body))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接接口：%s" % e.reason)
