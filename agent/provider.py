# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
provider.py — Olivia 的多协议模型接入层（stdlib only）。

不照抄别家：Olivia 的 agentic loop 是服务端驱动的（server.py 用 OpenAI
工具调用协议跑循环）。这里做的是**协议适配**，把 Anthropic Messages API 与
Gemini generateContent API 翻译成同一个事件流：

    {"type": "token",      "text": ...}
    {"type": "tool_calls", "calls": [{"id","name","arguments"}, ...]}
    {"type": "done",       "content": ..., "tool_calls": [...]}

因此 server.py 的循环、抽牌、记忆、危机闸门完全不用改。

支持协议（cfg["protocol"]）：
  openai    默认，{base}/chat/completions
  anthropic {base}/v1/messages，x-api-key + anthropic-version
  gemini    {base}/v1beta/models/{model}:streamGenerateContent?alt=sse
  auto      按 base_url 猜（含 anthropic → anthropic，含 googleapis/gemini → gemini）
"""

import json
import urllib.request
import urllib.error

DEFAULT_TIMEOUT = 120


# ---------- 协议选择 ----------

def detect_protocol(cfg):
    p = str(cfg.get("protocol") or "auto").strip().lower()
    if p in ("openai", "anthropic", "gemini"):
        return p
    base = str(cfg.get("base_url") or "").lower()
    if "anthropic" in base:
        return "anthropic"
    if "googleapis" in base or "gemini" in base:
        return "gemini"
    return "openai"


def _headers(cfg, extra=None):
    h = {"Content-Type": "application/json"}
    key = str(cfg.get("api_key") or "").strip()
    if key:
        h["Authorization"] = "Bearer " + key
    if extra:
        h.update(extra)
    return h


def _open(req, timeout):
    try:
        return urllib.request.urlopen(req, timeout=float(timeout))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:800]
        except Exception:
            pass
        raise RuntimeError("HTTP %s %s\n%s" % (e.code, e.reason, body))
    except urllib.error.URLError as e:
        raise RuntimeError("无法连接接口：%s" % e.reason)


def _post(url, headers, payload, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST")
    return _open(req, timeout)


def _norm_usage(u):
    """把三种协议各自的 usage 形态归一成 {"in","out","total"}。

    缺字段就记 0；整条没有用量信息时返回 None，前端据此决定显不显示。
    """
    if not isinstance(u, dict) or not u:
        return None

    def _i(*keys):
        for k in keys:
            v = u.get(k)
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                return int(v)
        return 0

    pin = _i("prompt_tokens", "input_tokens", "promptTokenCount")
    pout = _i("completion_tokens", "output_tokens", "candidatesTokenCount")
    total = _i("total_tokens", "totalTokenCount") or (pin + pout)
    if not (pin or pout):
        return None
    return {"in": pin, "out": pout, "total": total}


def _sse_events(resp):
    """逐行读 SSE，yield (event_type, data_str)；兼容只有 data: 的流。"""
    event = None
    for raw in resp:
        try:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
        except Exception:
            continue
        if line == "":
            if event is not None:
                yield event
                event = None
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
            yield (event or "message", data)
            event = None
    if event is not None:
        yield event


# =====================================================================
#  OpenAI（保留原逻辑，作为适配器的一条分支）
# =====================================================================

def _clean_base(base_url, suffix):
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("base_url 为空，请在设置里填写接口地址")
    return base + suffix


def _openai_events(messages, cfg, tools):
    url = _clean_base(cfg.get("base_url", ""), "/chat/completions")
    payload = {
        "model": cfg.get("model", ""),
        "messages": messages,
        "temperature": float(cfg.get("temperature", 0.8)),
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    if cfg.get("max_output_tokens"):
        try:
            payload["max_tokens"] = max(1, int(cfg["max_output_tokens"]))
        except (TypeError, ValueError):
            pass
    # 本地 Ollama 推理模型默认关 thinking（与 llm.py 一致）
    base = str(cfg.get("base_url", "")).lower()
    if ("127.0.0.1" in base or "localhost" in base) and cfg.get("think") is not True:
        payload["options"] = {"think": False}
    # 用量统计：OpenAI 兼容端点在流末尾补一个只带 usage 的 chunk，但必须先
    # 显式打开 include_usage。本地 Ollama 不认这个字段，直接跳过。
    if not ("127.0.0.1" in base or "localhost" in base):
        payload["stream_options"] = {"include_usage": True}
    try:
        resp = _post(url, _headers(cfg), payload, cfg.get("timeout", DEFAULT_TIMEOUT))
    except RuntimeError as e:
        # 少数第三方兼容网关会把不认识的 stream_options 当参数错误：
        # 去掉它重试一次，宁可拿不到用量也不能让整轮对话失败。
        if "stream_options" in str(e):
            payload.pop("stream_options", None)
            resp = _post(url, _headers(cfg), payload, cfg.get("timeout", DEFAULT_TIMEOUT))
        else:
            raise
    parts, calls, usage = [], {}, None
    with resp:
        for _type, chunk in _sse_events(resp):
            if chunk == "[DONE]":
                break
            try:
                obj = json.loads(chunk)
            except Exception:
                continue
            u = obj.get("usage")
            if isinstance(u, dict) and u:
                usage = u
            try:
                delta = obj["choices"][0].get("delta", {}) or {}
            except Exception:
                delta = {}
            text = delta.get("content")
            if text:
                parts.append(text)
                yield {"type": "token", "text": text}
            seq = 0
            for tc in (delta.get("tool_calls") or []):
                idx = tc.get("index")
                if idx is None:
                    idx = seq
                seq += 1
                slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    out = [calls[i] for i in sorted(calls) if calls[i]["name"]]
    if out:
        yield {"type": "tool_calls", "calls": out}
    yield {"type": "done", "content": "".join(parts), "tool_calls": out,
           "usage": _norm_usage(usage)}


# =====================================================================
#  Anthropic Messages API
# =====================================================================

def _anthropic_messages(messages):
    """OpenAI messages -> (system_str, anthropic_messages)。
    Anthropic 把 system 独立出来，且 tool_result 必须嵌在 user 内容块里。
    """
    system_parts = []
    out = []

    def flush_user(blocks):
        if blocks and out and out[-1]["role"] == "user":
            out[-1]["content"].extend(blocks)
        elif blocks:
            out.append({"role": "user", "content": blocks})

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(str(content))
            continue
        if role == "tool":
            result = content
            try:
                obj = json.loads(content)
                result = obj.get("content") or content
            except Exception:
                pass
            flush_user([{
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id", ""),
                "content": str(result),
            }])
            continue
        if role == "assistant":
            blocks = []
            if content:
                blocks.append({"type": "text", "text": str(content)})
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function") or {}
                args = fn.get("arguments") or "{}"
                try:
                    args_obj = json.loads(args)
                except Exception:
                    args_obj = {}
                blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": args_obj,
                })
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue
        # user
        flush_user([{"type": "text", "text": str(content)}])
    return "\n\n".join(system_parts), out


def _anthropic_tools(tools):
    """OpenAI tools -> Anthropic tools。"""
    out = []
    for t in (tools or []):
        fn = t.get("function", {}) if t.get("type") == "function" else {}
        if not fn and "name" in t:
            fn = t
        if not fn.get("name"):
            continue
        out.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return out


def _anthropic_events(messages, cfg, tools):
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/v1/messages"
    system, msgs = _anthropic_messages(messages)
    payload = {
        "model": cfg.get("model", ""),
        "messages": msgs,
        "max_tokens": int(cfg.get("max_output_tokens") or cfg.get("max_tokens") or 4096),
        "stream": True,
    }
    if system:
        payload["system"] = system
    if cfg.get("temperature") is not None:
        payload["temperature"] = float(cfg.get("temperature", 0.8))
    atools = _anthropic_tools(tools)
    if atools:
        payload["tools"] = atools
    headers = _headers(cfg, {
        "x-api-key": str(cfg.get("api_key") or "").strip(),
        "anthropic-version": "2023-06-01",
    })
    resp = _post(url, headers, payload, cfg.get("timeout", DEFAULT_TIMEOUT))

    parts, blocks, usage = [], {}, {}
    with resp:
        for event, data in _sse_events(resp):
            if event in ("ping", "message_stop"):
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            etype = obj.get("type") or event
            if etype == "message_start":
                # 输入 token 只在 message_start 里给一次
                u = (obj.get("message") or {}).get("usage") or {}
                if u.get("input_tokens") is not None:
                    usage["input_tokens"] = int(u["input_tokens"])
                # 命中提示缓存的 token 也算进输入量，前端一并显示
                extra_in = 0
                for k in ("cache_read_input_tokens", "cache_creation_input_tokens"):
                    if u.get(k):
                        extra_in += int(u[k])
                if extra_in:
                    usage["input_tokens"] = usage.get("input_tokens", 0) + extra_in
            elif etype == "message_delta":
                # 输出 token 在 message_delta 里累积给出
                u = obj.get("usage") or {}
                if u.get("output_tokens") is not None:
                    usage["output_tokens"] = int(u["output_tokens"])
                if u.get("input_tokens") is not None and "input_tokens" not in usage:
                    usage["input_tokens"] = int(u["input_tokens"])
            if etype == "content_block_start":
                b = obj.get("content_block") or {}
                idx = obj.get("index", 0)
                if b.get("type") == "tool_use":
                    blocks[idx] = {
                        "id": b.get("id", ""), "name": b.get("name", ""),
                        "arguments": "",
                    }
            elif etype == "content_block_delta":
                d = obj.get("delta") or {}
                idx = obj.get("index", 0)
                if d.get("type") == "text_delta":
                    t = d.get("text") or ""
                    if t:
                        parts.append(t)
                        yield {"type": "token", "text": t}
                elif d.get("type") == "input_json_delta":
                    if idx in blocks:
                        blocks[idx]["arguments"] += d.get("partial_json") or ""
            elif etype == "error":
                err = obj.get("error") or {}
                raise RuntimeError("Anthropic 错误：%s" % err.get("message", str(obj)[:300]))

    calls = []
    for idx in sorted(blocks):
        b = blocks[idx]
        if b["name"]:
            if not b["arguments"]:
                b["arguments"] = "{}"
            calls.append(b)
    if calls:
        yield {"type": "tool_calls", "calls": calls}
    yield {"type": "done", "content": "".join(parts), "tool_calls": calls,
           "usage": _norm_usage(usage)}


def anthropic_check(cfg):
    """连通性探测（非流式）。"""
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base + "/v1/messages"
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": "只回复两个字：在线"}],
        "max_tokens": 32,
    }
    headers = _headers(cfg, {
        "x-api-key": str(cfg.get("api_key") or "").strip(),
        "anthropic-version": "2023-06-01",
    })
    resp = _post(url, headers, payload, cfg.get("timeout", 60))
    with resp:
        obj = json.loads(resp.read().decode("utf-8", "replace"))
    return "".join(b.get("text", "") for b in obj.get("content", [])
                   if b.get("type") == "text")


# =====================================================================
#  Gemini generateContent API
# =====================================================================

def _tool_name_for_id(messages, tool_call_id):
    """从对话里找回 tool_call_id 对应的函数名（Gemini functionResponse 需要）。"""
    for m in reversed(messages):
        if m.get("role") != "assistant":
            continue
        for tc in (m.get("tool_calls") or []):
            if tc.get("id") == tool_call_id:
                return (tc.get("function") or {}).get("name", "tool")
    return "tool"


def _gemini_contents(messages):
    """OpenAI messages -> (systemInstruction, contents)。"""
    system_parts, out = [], []

    def flush_user(parts):
        if parts and out and out[-1]["role"] == "user":
            out[-1]["parts"].extend(parts)
        elif parts:
            out.append({"role": "user", "parts": parts})

    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(str(content))
            continue
        if role == "tool":
            name = _tool_name_for_id(messages, m.get("tool_call_id", ""))
            try:
                obj = json.loads(content)
                response = obj if isinstance(obj, dict) else {"result": obj}
            except Exception:
                response = {"result": str(content)}
            flush_user([{"functionResponse": {"name": name, "response": response}}])
            continue
        if role == "assistant":
            parts = []
            if content:
                parts.append({"text": str(content)})
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function") or {}
                args = fn.get("arguments") or "{}"
                try:
                    args_obj = json.loads(args)
                except Exception:
                    args_obj = {}
                parts.append({"functionCall": {"name": fn.get("name", ""),
                                               "args": args_obj}})
            if parts:
                out.append({"role": "model", "parts": parts})
            continue
        flush_user([{"text": str(content)}])
    return "\n\n".join(system_parts), out


def _gemini_tools(tools):
    decls = []
    for t in (tools or []):
        fn = t.get("function", {}) if t.get("type") == "function" else {}
        if not fn and "name" in t:
            fn = t
        if not fn.get("name"):
            continue
        decls.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return [{"functionDeclarations": decls}] if decls else []


def _gemini_events(messages, cfg, tools):
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    if base.endswith("/v1beta"):
        base = base[:-7]
    model = cfg.get("model", "")
    url = "%s/v1beta/models/%s:streamGenerateContent?alt=sse" % (
        base, urllib.request.quote(model, safe=""))
    system, contents = _gemini_contents(messages)
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(cfg.get("temperature", 0.8)),
        },
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    if cfg.get("max_output_tokens"):
        try:
            payload["generationConfig"]["maxOutputTokens"] = max(
                1, int(cfg["max_output_tokens"]))
        except (TypeError, ValueError):
            pass
    gtools = _gemini_tools(tools)
    if gtools:
        payload["tools"] = gtools
    headers = {"Content-Type": "application/json"}
    key = str(cfg.get("api_key") or "").strip()
    if key:
        headers["x-goog-api-key"] = key
    resp = _post(url, headers, payload, cfg.get("timeout", DEFAULT_TIMEOUT))

    parts, calls, usage = [], {}, {}
    with resp:
        for _event, data in _sse_events(resp):
            try:
                obj = json.loads(data)
            except Exception:
                continue
            # Gemini 每个 chunk 都带 usageMetadata，最后一个才是整轮总数
            um = obj.get("usageMetadata")
            if isinstance(um, dict) and um:
                usage = um
            cands = obj.get("candidates") or []
            if not cands:
                continue
            content = cands[0].get("content") or {}
            for part in (content.get("parts") or []):
                text = part.get("text")
                if text:
                    parts.append(text)
                    yield {"type": "token", "text": text}
                fc = part.get("functionCall")
                if fc:
                    name = fc.get("name", "")
                    # Gemini 把参数按块累积，这里按函数名合并
                    slot = calls.setdefault(name, {"id": "gemini_%s" % name,
                                                   "name": name, "arguments": ""})
                    args = fc.get("args")
                    if args:
                        slot["arguments"] += json.dumps(args, ensure_ascii=False) \
                            if isinstance(args, dict) else str(args)
            if obj.get("error"):
                raise RuntimeError("Gemini 错误：%s" %
                                   str(obj["error"].get("message", obj["error"])[:300]))

    out = []
    for name in calls:
        c = calls[name]
        # 合并多次 args 片段：取最后一次完整 JSON
        raw = c["arguments"]
        try:
            json.loads(raw)
        except Exception:
            raw = raw[raw.find("{"):] if "{" in raw else "{}"
            try:
                json.loads(raw)
            except Exception:
                raw = "{}"
        c["arguments"] = raw
        out.append(c)
    if out:
        yield {"type": "tool_calls", "calls": out}
    yield {"type": "done", "content": "".join(parts), "tool_calls": out,
           "usage": _norm_usage(usage)}


def gemini_check(cfg):
    base = str(cfg.get("base_url", "")).strip().rstrip("/")
    if base.endswith("/v1beta"):
        base = base[:-7]
    model = cfg.get("model", "")
    url = "%s/v1beta/models/%s:generateContent" % (
        base, urllib.request.quote(model, safe=""))
    payload = {
        "contents": [{"role": "user", "parts": [{"text": "只回复两个字：在线"}]}],
        "generationConfig": {"temperature": 0.1},
    }
    headers = {"Content-Type": "application/json"}
    key = str(cfg.get("api_key") or "").strip()
    if key:
        headers["x-goog-api-key"] = key
    resp = _post(url, headers, payload, cfg.get("timeout", 60))
    with resp:
        obj = json.loads(resp.read().decode("utf-8", "replace"))
    cands = obj.get("candidates") or []
    if not cands:
        raise RuntimeError("Gemini 未返回内容：%s" % str(obj)[:300])
    return "".join(p.get("text", "") for p in
                   (cands[0].get("content") or {}).get("parts", []))


# =====================================================================
#  统一入口
# =====================================================================

def stream_chat_events(messages, cfg, tools=None):
    proto = detect_protocol(cfg)
    if proto == "anthropic":
        return _anthropic_events(messages, cfg, tools)
    if proto == "gemini":
        return _gemini_events(messages, cfg, tools)
    return _openai_events(messages, cfg, tools)


def check(cfg):
    proto = detect_protocol(cfg)
    if proto == "anthropic":
        return anthropic_check(cfg)
    if proto == "gemini":
        return gemini_check(cfg)
    # openai: 复用 llm.check
    import llm
    return llm.check(cfg)
