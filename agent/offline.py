# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
offline.py — Olivia 的离线整理（降级路径）

这不是"离线 AI"，也**不伪装成模型解读**。当没有可用的模型连接（没填 key、
key 是占位串、或模型调用失败）时，把系统在本地已经客观抽好的那副牌，按
「牌位所问 + 随牌传统牌意 + 复现种子」整理成一段可读文字，让
「抽牌 → 看牌 → 读牌位含义」这条链在没有网络时也能走完。

刻意和"生成式解读"划清界限（也和别家的语料拼贴产品不同）：
  · 只复述 knowledge/meanings 里随牌返回的传统牌意，不编造、不粉饰；
  · 不预言、不给具体事件建议、不做心理诊断、不替人下结论；
  · 开头明说这是「离线整理」而非模型解读；
  · 纯标准库，零依赖，和 agent 其余部分一致。

元规则仍然是：**牌不开口，人开口。** 离线时这张嘴由传统牌意来当。
"""

import re

# 模型调用不可用的判断：空 key、掩码占位、明显的省略号占位都算离线。
_PLACEHOLDER_MARKERS = ("****", "…", "••••", "xxxx", "XXXX")


def is_offline(cfg):
    """cfg 里没有可用于真实调用的 key 时返回 True。"""
    key = str((cfg or {}).get("api_key") or "").strip()
    if not key:
        return True
    if any(m in key for m in _PLACEHOLDER_MARKERS):
        return True
    return False


_NOTICE = "【离线整理】没有可用的模型连接，以下是本地整理，不是 AI 解读。"

_TAIL = (
    "牌意来自传统韦特体系，只是照见此时此地的线索，不预言结果、也不替你做决定。"
    "等连上模型后，可以说「就着这副牌说说我的问题」，我再为你完整解读。"
)


def _split_meaning(meaning):
    """把「核心：X 正位：Y」拆成 (核心, 本方位正文)。"""
    text = str(meaning or "").strip()
    m = re.match(r"^核心：(.*?)\s+(?:正位|逆位)：(.*)$", text, re.S)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text, ""


def _clip(text, limit=260):
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    # 尽量断在句号，避免半句话
    head = text[:limit]
    at = max(head.rfind("。"), head.rfind("；"))
    return (head[:at + 1] if at >= limit // 2 else head + "…")


def compose(result, question=""):
    """把 tools.draw_cards 的结果整理成一段离线可读文本。"""
    if not result or not result.get("cards"):
        return _NOTICE + "\n\n还没有抽牌。请先说「用三张牌阵抽牌」。"

    spread = result.get("spread") or "抽牌"
    desc = result.get("spread_desc") or ""
    cards = result.get("cards") or []
    q = str(question or result.get("question") or "").strip()

    lines = [_NOTICE]
    head = "牌阵：%s · %d 张" % (spread, len(cards))
    if desc:
        head += "（%s）" % desc
    lines.append(head)
    if q and q != "（来访者未明确说明）":
        lines.append("你问的是：%s" % _clip(q, 120))

    lines.append("")
    for i, c in enumerate(cards, 1):
        pos = c.get("position") or ("第%d张" % i)
        posq = c.get("position_meaning") or ""
        name = c.get("name") or "?"
        ori = c.get("orientation") or ""
        core, body = _split_meaning(c.get("meaning"))

        lines.append("%d. 【%s】%s · %s" % (i, pos, name, ori))
        if posq:
            lines.append("    这个位置在问：%s" % _clip(posq, 80))
        if core:
            lines.append("    传统牌意 · 核心：%s" % _clip(core, 180))
        if body:
            lines.append("    %s时所指：%s" % (ori or "牌面", _clip(body)))
        lines.append("")

    seed = result.get("seed")
    if seed is not None:
        lines.append("复现种子：%s（同种子、同牌阵可抽回同一副牌）" % seed)
    lines.append(_TAIL)
    return "\n".join(lines)


def compose_chat(message="", image_note=""):
    """没有已抽的牌、也没连上模型时，给一句不越界的引导。

    image_note：本机 OCR 从图上读到的字。有就先把字念给用户听，
    让他知道图确实被读到了，再说明离线状态下能做什么。
    """
    head = ""
    if str(image_note or "").strip():
        head = ("【我先把图上的字读出来了】\n" + str(image_note).strip()[:1200] +
                "\n\n（这些字是本机 OCR 读的，可能有错字；看得对不对，你可以直接改。）\n\n")
    return (
        head + _NOTICE + "\n\n"
        "不过抽牌和读牌面都不需要联网。你可以说「用三张牌阵抽牌」，"
        "或点选一个牌阵；我会把牌按传统几何摆好，并把每个牌位在问什么、"
        "每张牌的传统牌意完整整理给你。等连上模型后，再就着这副牌为你解读。"
    )


def chunks(text):
    """按段落切成若干块，交给 SSE 打字机逐段呈现。"""
    text = str(text or "")
    parts = [p for p in text.split("\n\n") if p]
    # 每段后补回 "\n\n" 分隔，最后一段不加尾随空行，保证拼接可还原原文。
    return [p + "\n\n" for p in parts[:-1]] + ([parts[-1]] if parts else [])
