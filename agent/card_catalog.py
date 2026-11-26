# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Pure helpers for building the 78-card catalog sent to the web UI."""

import os
import re

import knowledge
import tools


_MAJOR_ELEMENTS = {
    "愚者": "风", "魔术师": "风", "女祭司": "水", "皇后": "土",
    "皇帝": "火", "教皇": "土", "恋人": "风", "战车": "水",
    "力量": "火", "隐者": "土", "命运之轮": "火", "正义": "风",
    "倒吊人": "水", "死神": "水", "节制": "火", "恶魔": "土",
    "塔": "火", "星星": "风", "月亮": "水", "太阳": "火",
    "审判": "火", "世界": "土",
}
_MAJOR_ROMAN = ["0", "I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI",
                "XVII", "XVIII", "XIX", "XX", "XXI"]
_CARD_SUITS = {"权杖": ("wands", "火"), "圣杯": ("cups", "水"),
               "宝剑": ("swords", "风"), "星币": ("pentacles", "土")}


def _brief_card(text, limit=72):
    """只把牌义的第一句发给浏览器；完整原文留在服务端。"""
    t = " ".join(str(text or "").split())
    if not t:
        return ""
    m = re.match(r"^.*?[。！？；]", t)
    head = m.group(0) if m else t
    if head.endswith("；"):
        head = head[:-1] + "。"
    if len(head) > limit:
        head = head[:limit].rstrip("，、；：—-") + "…"
    return head


def card_catalog():
    """78 张牌的目录：名字/图片/花色/数字/元素 + knowledge/ 里的牌义。"""
    out = []
    for name in tools.DECK:
        image = tools.card_image(name)
        if not image:
            continue
        cid = os.path.splitext(os.path.basename(image))[0]
        entry = knowledge.get_card_entry(name)
        if name in _MAJOR_ELEMENTS:
            idx = tools.DECK.index(name)
            out.append({
                "id": cid, "name": name, "image": image, "group": "major",
                "deck": "大阿卡纳", "num": _MAJOR_ROMAN[idx],
                "element": _MAJOR_ELEMENTS[name],
                "core": entry["core"],
                "brief_up": _brief_card(entry["up"]),
                "brief_rev": _brief_card(entry["rev"]),
            })
            continue
        suit = name[:2]
        slug, element = _CARD_SUITS.get(suit, ("", ""))
        out.append({
            "id": cid, "name": name, "image": image, "group": slug,
            "deck": "小阿卡纳 · " + suit, "num": name[2:],
            "element": element,
            "core": entry["core"],
            "brief_up": _brief_card(entry["up"]),
            "brief_rev": _brief_card(entry["rev"]),
        })
    return out
