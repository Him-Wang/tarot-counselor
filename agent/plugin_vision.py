# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
plugin_vision.py — multimodal vision bridge (cloud VLM configurable), stdlib only.

ARCHITECTURE (for pure-text main models):
    用户发图 → VLM(云端，可配) 看图生成文字描述 → 描述注入主模型对话
主模型本身不需要视觉能力；任何 OpenAI 兼容的视觉模型都能接（OpenAI / 通义 /
智谱 / Moonshot / 自建 VLM 网关…），只要填 base_url + api_key + model。

DESIGN NOTES:
  - 完全不依赖本地模型（用户明确要求）。
  - 只做"图片 → 中文文字描述"，不把图片直接喂给纯文本主模型。
  - 图片可来自：前端上传的 data URL / base64 / 本地文件路径。
  - 所有网络调用走 urllib.request，无第三方依赖。
  - 配置和密钥存 agent/data/plugins.json（gitignored），按 OpenAI 惯例传 Bearer key。

Public API:
  default_config()               -> dict
  known_providers()              -> [dict]  常见视觉 API 预设
  is_configured(cfg)             -> bool
  describe_image(image, cfg, question=None, detail="auto") -> str
      image: data URL ("data:image/png;base64,..." / "data:image/jpeg;base64,...")
             or raw base64 string, or a local file path
  build_context(description, question) -> str  把描述包装成给主模型的上下文
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(DATA_DIR, "plugins.json")

DEFAULT_DESCRIBE_PROMPT = (
    "请用中文详细描述这张图片的内容：画面里有什么人/物/场景、颜色与布局、"
    "文字信息（如有）、以及任何可能影响塔罗占卜或情绪解读的细节。"
    "只描述客观可见的信息，不要臆测、不要编造。若图片看不清或无法识别，如实说明。"
)


def default_config():
    return {
        "enabled": False,
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
        "describe_prompt": DEFAULT_DESCRIBE_PROMPT,
        "detail": "auto",  # low | high | auto
        "timeout": 120,
    }


def known_providers():
    """Common OpenAI-compatible vision endpoints, to help users configure."""
    return [
        {"name": "OpenAI", "base_url": "https://api.openai.com/v1",
         "model": "gpt-4o-mini", "note": "需 OpenAI key"},
        {"name": "通义千问 VL", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
         "model": "qwen-vl-max", "note": "灵积 OpenAI 兼容模式"},
        {"name": "智谱 GLM-4V", "base_url": "https://open.bigmodel.cn/api/paas/v4",
         "model": "glm-4v-plus", "note": "智谱开放平台"},
        {"name": "Moonshot", "base_url": "https://api.moonshot.cn/v1",
         "model": "moonshot-v1-8k-vision-preview", "note": "月之暗面"},
        {"name": "自定义", "base_url": "", "model": "",
         "note": "任意 OpenAI 兼容视觉 API 网关"},
    ]


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return True


def get_vision_config():
    """Merge saved config over defaults."""
    cfg = dict(default_config())
    saved = load_config().get("vision", {})
    if isinstance(saved, dict):
        cfg.update(saved)
    return cfg


def is_configured(cfg=None):
    cfg = cfg or get_vision_config()
    return bool(cfg.get("enabled") and cfg.get("api_key") and
                cfg.get("model") and cfg.get("base_url"))


def _mime_of(data_url_or_path):
    if data_url_or_path.startswith("data:"):
        m = re.match(r"data:(image/[a-zA-Z0-9.+-]+);base64,", data_url_or_path)
        return m.group(1) if m else "image/jpeg"
    ext = os.path.splitext(data_url_or_path)[1].lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".gif": "image/gif"}.get(ext, "image/jpeg")


def _to_data_url(image):
    """Normalize input to a data URL string."""
    if not image:
        raise ValueError("图片内容为空")
    if image.startswith("data:"):
        return image
    if os.path.isfile(image):
        with open(image, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return "data:%s;base64,%s" % (_mime_of(image), b64)
    # treat as raw base64
    try:
        base64.b64decode(image, validate=False)
    except Exception:
        raise ValueError("无法识别的图片格式（既非 data URL、路径，也非 base64）")
    return "data:image/jpeg;base64,%s" % image


def _normalize_base(base):
    base = (base or "").rstrip("/")
    if base and not base.endswith("/v1") and not base.endswith("/v4"):
        # most OpenAI-compatible endpoints use /v1; but user may supply full path
        if re.search(r"/v\d+$", base):
            return base
        return base + "/v1"
    return base


def describe_image(image, cfg=None, question=None, detail=None):
    """Send an image to the configured cloud VLM and return a Chinese description.

    Returns the plain-text description string. Raises RuntimeError with a
    human-readable message on failure.
    """
    cfg = cfg or get_vision_config()
    if not cfg.get("api_key") or not cfg.get("model") or not cfg.get("base_url"):
        raise RuntimeError("视觉插件未配置：请在设置里填写 API 地址、密钥和视觉模型。")
    data_url = _to_data_url(image)
    detail = detail or cfg.get("detail", "auto")
    prompt = (cfg.get("describe_prompt") or DEFAULT_DESCRIBE_PROMPT)
    if question:
        prompt += "\n\n用户针对这张图片的问题是：%s" % question

    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": data_url, "detail": detail}},
        ]}],
        "temperature": 0.2,
        "max_tokens": 1000,
        "stream": False,
    }
    url = _normalize_base(cfg["base_url"]) + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )
    timeout = int(cfg.get("timeout", 120))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError("视觉 API HTTP %d：%s" % (e.code, body))
    except Exception as e:
        raise RuntimeError("视觉 API 请求失败：%s" % e)

    try:
        content = obj["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("视觉 API 返回格式异常，未找到描述文本。")
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return (content or "").strip()


def build_context(description, question=None):
    """Wrap the VLM description into a prompt block for the main text model."""
    head = "【用户发来一张图片。以下是视觉模型对它的客观描述，请据此结合牌面作答；不要声称自己『看见了』图片，把它当作用户提供的线索即可。】"
    body = "\n图片描述：%s" % description
    if question:
        body += "\n用户附带的问题：%s" % question
    return head + body


def masked_config(cfg=None):
    """Return config with api_key masked for the settings UI."""
    cfg = cfg or get_vision_config()
    out = dict(cfg)
    k = out.get("api_key", "")
    if k:
        out["api_key"] = k[:4] + "***" + k[-4:] if len(k) > 8 else "***"
    return out
