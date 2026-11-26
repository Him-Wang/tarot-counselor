# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Pure payload builders for draw / pick / reading-round SSE events."""

import spreads as spreads_mod


def _cards_payload(result):
    """SSE 里推给前端的牌面数据（抽牌轮与解读轮共用）。"""
    spread = result.get("spread", "")
    return {
        "spread": spread,
        "spread_desc": result.get("spread_desc", ""),
        "question": result.get("question", ""),
        "manual": bool(result.get("manual")),
        "random": bool(result.get("random_source")),
        "layout": result.get("layout") or spreads_mod.layout(spread),
        "items": [{
            "position": c.get("position", ""),
            "position_meaning": c.get("position_meaning", ""),
            "name": c.get("name", ""),
            "orientation": c.get("orientation", ""),
            "image": c.get("image", ""),
        } for c in result.get("cards", [])],
        "extras": [{
            "position": c.get("position", "补牌"),
            "position_meaning": c.get("position_meaning", ""),
            "name": c.get("name", ""),
            "orientation": c.get("orientation", ""),
            "image": c.get("image", ""),
            "reason": c.get("reason", ""),
        } for c in (result.get("extras") or [])],
    }


def _pick_payload(spread):
    """选牌轮的舞台数据：牌阵、牌位与张数，由前端摆出扇形牌堆。"""
    meta = spreads_mod.SPREAD_META.get(spread) or {}
    positions = meta.get("positions") or []
    return {
        "spread": spread,
        "spread_desc": meta.get("desc", ""),
        "count": len(positions),
        "layout": spreads_mod.layout(spread),
        "positions": [{"name": p[0], "meaning": p[1]} for p in positions],
    }


def _add_usage(totals, usage):
    """把一轮（可能多次调用）的用量累加进来；拿不到用量就什么都不做。"""
    if not isinstance(usage, dict):
        return
    for k in ("in", "out", "total"):
        try:
            totals[k] += int(usage.get(k) or 0)
        except Exception:
            pass


def _pending_context(result, question):
    """解读轮注入的硬约束：解读眼前这副牌，不重抽、不换牌。"""
    extras = result.get("extras") or []
    lines = [
        "【本轮解牌约束 · 必须遵守】",
        "来访者上一轮已经抽出一副牌，本轮才给出问题。请只解读下面这副已抽出的牌，",
        ("不得重新抽牌、换牌，也不得再补牌、凭记忆换用别的牌面。" if not extras else
         "不得重新抽牌、换牌，也不得凭记忆换用别的牌面。"),
        "牌阵：%s（%s）" % (result.get("spread", "未注明"), result.get("spread_desc", "")),
        "牌面与随牌传统牌意：",
    ]
    for i, c in enumerate(result.get("cards") or [], 1):
        lines.append("%d. %s（%s）：%s %s" % (
            i, c.get("position", ""), c.get("position_meaning", ""),
            c.get("name", ""), c.get("orientation", "")))
        meaning = c.get("meaning", "")
        if meaning:
            lines.append("   传统牌意：" + str(meaning).replace("\n", " "))
    if extras:
        lines.append("来访者本轮主动要求补牌，理由是：%s" % (
            "；".join(e.get("reason") or "（未说明理由）" for e in extras)))
        for e in extras:
            lines.append("补牌｜%s（%s）" % (e.get("name", ""), e.get("orientation", "")))
            meaning = e.get("meaning", "")
            if meaning:
                lines.append("   传统牌意：" + str(meaning).replace("\n", " "))
        lines.append("补牌只能作为补充视角，放在原牌之后解读：不得据此替换或否定原来的牌，"
                     "也不得再自行增补。")
    lines.append("来访者的问题：%s" % (question or ""))
    lines.append("请按「原本牌意 → 牌阵位置 → 对应问题 → 落到情境」逐张解读；"
                 "这段牌面是既定依据，不可自行编造或替换。")
    return "\n".join(lines)


ASK_AFTER_DRAW = (
    "好的，牌已经抽出来了——你有什么问题吗？"
    "告诉我你想问什么，我就照着这副牌为你解读。"
)

# 抽牌轮的开场白：前端会把它打字机式地逐字打出，稍作停顿再翻牌，
# 让「默念问题 → 翻牌 → 提问」有真正的仪式节奏。
MEDITATE_TEXT = "好的，请在心中默念你的问题……"
