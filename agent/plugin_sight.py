# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
plugin_sight.py — 统一「看图」管线：本机 OCR 优先，云端视觉模型按需升级。

为什么合并
----------
以前 server.py 里并排两条通道（plugin_ocr.py 本机读字 / plugin_vision.py 云端
描述），各自有配置、各自的失败分支、各自的上下文文案，调用点散在四处。现在
只有一个入口 describe(images, question) → SightResult，策略固定为：

  1. 有图先看本机 OCR（离线、不上传）；读到字就直接用，不再调云端。
  2. 本机没读到字（纯画面截图、照片），且用户配了云端 VLM，再调 VLM 描述。
  3. 都没有，返回一条明确的「看不了图」提示，让主模型如实告诉用户。

一个例外：用户显式开启了「云端优先」（cloud_first=True），此时先试 VLM，
失败再退 OCR。设置页原来的两个分区都还在（引擎没删），但主模型只认这一个管线。

Public API:
  SightResult.context          -> str  注入主模型的说明段落（""=没图）
  SightResult.note             -> str  给 offline.compose() 的纯文字线索
  SightResult.engine           -> str  "ocr" | "vision" | "none"
  SightResult.status           -> str  "ok" | "no-text" | "unavailable" | "no-image"
  describe(images, question=None, cloud_first=False) -> SightResult
  settings()                    -> dict  给 /api/plugins 的状态汇总
"""

import plugin_ocr
import plugin_vision

MAX_IMAGES = 3


class SightResult(object):
    __slots__ = ("context", "note", "engine", "status")

    def __init__(self, context="", note="", engine="none", status="no-image"):
        self.context = context
        self.note = note
        self.engine = engine
        self.status = status

    def __repr__(self):
        return "SightResult(engine=%r, status=%r, note_chars=%d)" % (
            self.engine, self.status, len(self.note))


def settings():
    """给设置页/／api/plugins 用：本机 OCR 状态 + 云端视觉状态。"""
    return {
        "ocr": plugin_ocr.available(),
        "vision": {
            "config": plugin_vision.masked_config(),
            "configured": plugin_vision.is_configured(),
            "providers": plugin_vision.known_providers(),
        },
    }


def _ocr_pass(images):
    """跑本机 OCR；返回 (texts[], raw_note)。"""
    texts = []
    for img in images[:MAX_IMAGES]:
        try:
            txt = plugin_ocr.recognize(img)
        except Exception as exc:
            print("[sight] local OCR failed: %s" % exc)
            txt = ""
        if txt and txt.strip():
            texts.append(txt.strip())
    return texts, "\n\n".join(texts)


def _vision_pass(images, question):
    """跑云端 VLM；返回 (contexts[], ok_count)。"""
    contexts = []
    try:
        cfg = plugin_vision.get_vision_config()
    except Exception:
        cfg = None
    for img in images[:MAX_IMAGES]:
        try:
            desc = plugin_vision.describe_image(img, cfg or None, question=question)
            if desc and desc.strip():
                contexts.append(plugin_vision.build_context(desc.strip(), question))
        except Exception as exc:
            print("[sight] cloud vision failed: %s" % exc)
    return contexts


def describe(images, question=None, cloud_first=False):
    """统一看图入口。策略：OCR 优先 → VLM 升级 → 明确告知看不了。

    images: data URL / base64 / 本地路径的列表（最多取前 3 张）。
    question: 用户附带的问句，拼进上下文。
    cloud_first: True 时先试云端视觉，再退本机 OCR。
    """
    if not images:
        return SightResult()
    cloud_ok = plugin_vision.is_configured()
    ocr_ok = bool(plugin_ocr.available().get("ok"))

    if cloud_first and cloud_ok:
        contexts = _vision_pass(images, question)
        if contexts:
            return SightResult(context="\n".join(contexts) + "\n", note="",
                               engine="vision", status="ok")
        # 云端失败 → 退回 OCR（继续往下）

    texts, note = _ocr_pass(images)
    if texts:
        print("[sight] local OCR read %d image(s), %d chars"
              % (len(texts), sum(len(t) for t in texts)))
        return SightResult(context=plugin_ocr.build_context(note, question),
                           note=note, engine="ocr", status="ok")

    if cloud_ok and not cloud_first:
        contexts = _vision_pass(images, question)
        if contexts:
            return SightResult(context="\n".join(contexts) + "\n", note="",
                               engine="vision", status="ok")

    if ocr_ok:
        ctx = ("【用户发来一张图片】本机 OCR 没在图上读到文字（可能是纯画面，"
               "也可能看不清）。看不清就先请用户用一两句话说说图上是什么，"
               "不要凭空猜测图里的内容。")
        return SightResult(context=ctx, note="", engine="none", status="no-text")
    ctx = ("【用户发来一张图片】本机既没有可用 OCR，也没有配置云端视觉模型。"
           "请如实告诉用户现在看不了图，并可建议在设置里填一个视觉模型的 key。")
    return SightResult(context=ctx, note="", engine="none", status="unavailable")
