# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
tools.py — callable tools for the Olivia agent (stdlib only).

The model decides *whether* to call a tool; this module defines *what* the
tools are (OpenAI function-calling JSON Schema) and executes them safely.

Design rules:
  - draw_cards is strictly objective/random: the model can never pick, swap
    or "feel" a card. It only chooses the spread and passes the question.
  - Every tool returns a JSON-serialisable dict; results are fed back into
    the conversation as {"role":"tool"} messages for the next model turn.
"""

import json
import os
import random

import knowledge
import memory
import plugin_kb
import scheduler as scheduler_mod
import spreads as spreads_mod

# 牌阵定义集中在 spreads.py；这里取 {名称: [牌位名, ...]} 的映射。
SPREADS = spreads_mod.SPREADS

# Canonical 78-card RWS deck for DRAWING (exactly one entry per card).
# memory.CARD_NAMES is intentionally an alias-rich list for *detection*
# (it includes 一/王牌/Ace/ace variants); that is unsuitable as a draw deck.
_MAJORS = ["愚者", "魔术师", "女祭司", "皇后", "皇帝", "教皇", "恋人", "战车",
           "力量", "隐者", "命运之轮", "正义", "倒吊人", "死神", "节制", "恶魔",
           "塔", "星星", "月亮", "太阳", "审判", "世界"]
_SUITS = ["权杖", "圣杯", "宝剑", "星币"]
_RANKS = ["王牌", "二", "三", "四", "五", "六", "七", "八", "九", "十",
          "侍从", "骑士", "王后", "国王"]  # 14 per suit (Ace + 2-10 + 4 court)
DECK = _MAJORS + [s + r for s in _SUITS for r in _RANKS]   # 22 + 56 = 78
assert len(DECK) == 78 and len(set(DECK)) == 78

# ---- 牌面图片（RWS 公有领域扫描，位于 agent/cards/）----
CARDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards")
_SUIT_SLUG = {"权杖": "wands", "圣杯": "cups", "宝剑": "swords", "星币": "pentacles"}
_RANK_SLUG = {"王牌": "ace", "二": "two", "三": "three", "四": "four", "五": "five",
              "六": "six", "七": "seven", "八": "eight", "九": "nine", "十": "ten",
              "侍从": "page", "骑士": "knight", "王后": "queen", "国王": "king"}


def card_image(name):
    """牌名 → 图片相对路径（如 cards/major-00.jpeg）；无对应图返回 ''。"""
    if name in _MAJORS:
        return "cards/major-%02d.jpeg" % _MAJORS.index(name)
    for suit, slug in _SUIT_SLUG.items():
        if name.startswith(suit):
            rank = name[len(suit):]
            rs = _RANK_SLUG.get(rank)
            if rs:
                return "cards/minor-%s-%s.jpeg" % (slug, rs)
    return ""

TOOL_GUIDE = """【可用工具 / 必须遵守】
- 抽牌：抽牌是系统的本地动作，由系统客观随机完成并直接展示，**你不需要也不应该调用
  draw_cards 工具**；抽牌这一轮系统不会请你参与。下面保留 draw_cards 的工具说明，
  仅在系统显式把牌面交给你解读时使用；你绝不能自己编牌名、挑牌、换牌，
  也不能把记忆里的旧牌当作本次牌面。
  牌阵清单（系统据此抽牌）：
%s
  牌面由系统客观随机产生；随牌给出的传统牌意（核心/正位/逆位）与牌阵位置说明，
  是解牌的既定依据——按「牌意→牌阵位置→对应问题→落到情境」的顺序解读，
  不可自行编造或替换牌意。
  选牌阵的原则：先用最简单的能回答问题的牌阵；问题复杂、牵扯多方、或需要看长期脉络时，
  才用更完整的牌阵。不要为了让解读显得隆重就选大牌阵。
- search_knowledge(query)：需要专业资料（咨询技术、伦理、危机干预）时调用。
- save_memory(kind, text)：来访者明确表达偏好/边界，或说「请记住」时调用。
- crisis_check(text)：察觉自伤、安全风险或严重侵害时调用；命中后立即跳出塔罗师角色走安全流程。
- save_note(title, content, tags)：来访者要求「记到知识库/归档/笔记本」、或值得长期留存的
  结构化内容（问卷、清单、重要决定）时调用。它与 save_memory 不同：这里是用户主动归档的笔记。
- search_notes(query)：需要调阅用户此前归档的笔记/知识库内容时调用。
- lookup_card(name, orientation)：来访者问到某一张具体的牌、或要核对牌名对应的含义时，
  用这个**按牌名直查**，不要拿 search_knowledge 去碰运气。牌名写「死神」「宝剑八」。
- recall_memory(what)：他问「上次我说过什么」「你记得我什么」「之前抽过什么牌」，
  或你需要主动回想他这个人时调用。what=facts 记下的线索 / profile 稳定画像 /
  draws 抽牌历史 / forget 删掉记错的一条（此时必须给 text，用原文或片段）。
  记错了就当场删，不要将错就错继续引用。
- schedule_reminder(name, intent, kind, run_at)：他说「明晚八点提醒我」「每天早上问我一句」
  「过两小时来看看我」时调用。到点 Olivia 会自己写一条消息进收件箱。
  kind=once 必须用 run_at（YYYY-MM-DD HH:MM，基于上面给你的当前时间推算，不要自己编年份）；
  daily/weekly 用 cron_time（HH:MM）；interval 用 interval_min。设完把时间复述一遍让他确认。
- 补牌：**你不能自己补牌**。只有来访者在界面上主动点「补一张」时，系统才会补一张进来，
  并把补牌理由一并交给你；那种情况下可以解读它，但不得据此替换原来的牌。
调用工具后，依据工具返回的结果继续；工具没给的信息绝不编造。""" % spreads_mod.catalogue()


# 解读轮的工具说明：牌已抽出，只允许补查资料，不允许改牌或写记忆。
TOOL_GUIDE_READ = """【本轮可用工具 / 必须遵守】
- 只开放两个只读工具：lookup_card(name, orientation) 与 search_knowledge(query)。
  需要核对某张牌的传统牌意、或补充解牌方法时调用，不要凭印象编。
- 不得调用 draw_cards：牌已经由系统抽出并展示，不能重抽、换牌或补牌。
- 不得调用 save_memory / save_note / recall_memory / schedule_reminder / crisis_check：
  本轮只解读眼前的牌，长期记忆由系统在回合结束后处理。
- 工具结果只作解读依据，不改变牌阵与牌面；工具没给的信息绝不编造。"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "draw_cards",
            "description": "保留工具：抽牌正常由系统在本地完成（手选或一键真随机），"
                           "不要主动调用本工具；仅在系统把牌面交给你解读时使用，不要自己生成牌名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "spread": {
                        "type": "string",
                        "enum": list(SPREADS.keys()),
                        "description": "牌阵名，只能从清单里选（单张/三张/关系/二选一/凯尔特十字/四季牌阵……）",
                    },
                    "question": {
                        "type": "string",
                        "description": "来访者所问的问题，原样或简要转述",
                    },
                },
                "required": ["spread"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索专业知识库（共情式倾听、伦理、危机转介等）。"
                           "需要专业依据而非牌面信息时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "把来访者明确表达的偏好、边界或「请记住」的事实存入私人长期记忆。"
                           " crisis/危机内容禁止入库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["fact", "pref", "boundary"],
                        "description": "fact=请记住的事实；pref=偏好；boundary=边界",
                    },
                    "text": {"type": "string", "description": "要记住的内容，用第一人称原话"}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crisis_check",
            "description": "检查文本中是否出现自伤、轻生、伤害他人等急性危机信号。"
                           "命中后必须立即停止解牌，给出求助资源并转介。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "需要检查的来访者文本"}
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "把值得长期留存的内容归档到用户的个人知识库（笔记）。"
                           "用户说「记到知识库/归档/笔记本」或给出清单、决定、问卷等结构化内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题"},
                    "content": {"type": "string", "description": "笔记正文"},
                    "tags": {"type": "string", "description": "逗号分隔的标签，可选"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "检索用户的个人知识库（归档笔记）。需要调阅此前归档的内容时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或问题"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_card",
            "description": "精确查一张牌的韦特传统牌意（按牌名直查，不是关键词检索）。"
                           "来访者问到某张具体牌、或需要核对牌名对应的含义时调用；"
                           "牌名用「死神」「宝剑八」「圣杯王后」这种写法。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "牌名，如 死神 / 宝剑八 / 圣杯王后 / 权杖王牌",
                    },
                    "orientation": {
                        "type": "string",
                        "enum": ["正位", "逆位", "两者"],
                        "description": "要正位、逆位，还是两者都给。默认两者。",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "主动回忆此前记住的线索、稳定画像与抽牌历史。"
                           "需要回访「上次你说过什么」「之前抽过什么牌」时调用；"
                           "也可以用 forget 删掉一条记错的线索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "enum": ["facts", "profile", "draws", "forget"],
                        "description": "facts=记住的线索，profile=稳定画像，"
                                       "draws=抽牌历史，forget=删掉一条线索",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最多返回几条，默认 10",
                    },
                    "text": {
                        "type": "string",
                        "description": "what=forget 时必填：要删除的那条线索原文（或其片段）",
                    },
                },
                "required": ["what"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_reminder",
            "description": "给来访者设一个定时关怀/提醒。他说「明早九点提醒我」「每周一问我进度」"
                           "「过两小时来看看我」时调用。到点后 Olivia 会主动写一条消息进收件箱。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "任务名，如「周一进度问候」"},
                    "intent": {"type": "string", "description": "到点时要 Olivia 说什么、关心什么"},
                    "kind": {
                        "type": "string",
                        "enum": ["once", "daily", "weekly", "interval"],
                        "description": "once=仅一次，daily=每天，weekly=每周，interval=每隔 N 分钟",
                    },
                    "run_at": {
                        "type": "string",
                        "description": "kind=once 时必填，格式 YYYY-MM-DD HH:MM（24 小时制）",
                    },
                    "cron_time": {
                        "type": "string",
                        "description": "kind=daily/weekly 时的时刻，格式 HH:MM，默认 09:00",
                    },
                    "weekday": {
                        "type": "integer",
                        "description": "kind=weekly 时用，0=周一 … 6=周日，默认 0",
                    },
                    "interval_min": {
                        "type": "integer",
                        "description": "kind=interval 时的间隔分钟数，默认 120",
                    },
                },
                "required": ["name", "intent", "kind"],
            },
        },
    },
]


# 解读轮只读工具：牌面已定，模型只能补查资料，不能重抽、换牌或写记忆。
READ_TOOL_NAMES = ("lookup_card", "search_knowledge")
READ_TOOLS = [t for t in TOOLS if t["function"]["name"] in READ_TOOL_NAMES]


# ---- 抽牌随机源 ----
# 软件拿不到物理真随机；能拿到的最强来源是内核 CSPRNG（os.urandom）。
# 两条抽牌路径（手选落位 / 一键真随机）的正逆位都由 random.SystemRandom()
# 即时从内核熵产生：没有种子、不可复现、无可重放的数字。


def draw_cards(spread="三张", question="", picks=None):
    """手动选牌落位：只接受来访者亲手挑出的牌，不再自行随机抽牌。

    需要「一键真随机」请用 draw_cards_random()（OS 内核熵，每次不同、不可复现）。

    ``picks`` 是牌堆下标（0..77）的列表，按顺序落到牌阵的各个牌位。
    手动选牌时不重抽、不替换，只把选中的牌原样铺开；正逆位由内核熵即时产生，
    没有种子、不可复现。
    """
    spread = spread if spread in SPREADS else "三张"
    meta = spreads_mod.SPREAD_META.get(spread) or {}
    pos_pairs = meta.get("positions") or [(p, "") for p in SPREADS[spread]]
    want = len(pos_pairs)
    # 严格校验手选的牌：不够就报错，绝不再退回随机采样。
    clean = []
    if isinstance(picks, (list, tuple)):
        for v in picks:
            try:
                idx = int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(DECK) and idx not in clean:
                clean.append(idx)
    if len(clean) != want:
        return {"ok": False,
                "reason": "手选需要 %d 张不重复的牌，实际只有 %d 张；"
                          "随机抽牌请使用 draw_cards_random()。" % (want, len(clean))}

    rng = random.SystemRandom()          # 内核 CSPRNG，每次取新熵，不可复现
    indices = clean[:want]
    cards = []
    for (pos, pos_meaning), idx in zip(pos_pairs, indices):
        name = DECK[idx]
        reversed_ = bool(rng.getrandbits(1))
        orientation = "逆位" if reversed_ else "正位"
        cards.append({
            "position": pos,
            "position_meaning": pos_meaning,
            "name": name,
            "orientation": orientation,
            "image": card_image(name),
            # 传统牌意由工具随牌面一并返回，作为解牌的既定依据；
            # 模型不得自行编造或替换这里的牌意。
            "meaning": knowledge.get_card_meaning(name, orientation),
        })
    return {
        "ok": True,
        "spread": spread,
        "spread_desc": meta.get("desc", ""),
        "question": question or "（来访者未明确说明）",
        "manual": True,
        "layout": spreads_mod.layout(spread),
        "cards": cards,
        "note": ("牌面由来访者亲手从牌堆中挑出，按挑选顺序落到牌位；不得更换、补牌或主观挑选。"
                 "请依据每张牌随附的传统牌意（核心/正位/逆位）与该牌位在问什么来解读，"
                 "不要自行编造牌意，也不要把其他牌位的含义套到这里。"),
    }


def draw_cards_random(spread="三张", question=""):
    """一键真随机抽牌：每次都从操作系统内核熵重新采样，不可预测、不可复现。

    走 random.SystemRandom()（底层 os.urandom，混入硬件熵），每次调用都取新熵，
    结果不同、无法重放，也不输出任何可用于复现的数字。
    不放回、正逆位各半、传统牌意随牌返回，规则与手选模式一致。
    """
    spread = spread if spread in SPREADS else "三张"
    meta = spreads_mod.SPREAD_META.get(spread) or {}
    pos_pairs = meta.get("positions") or [(p, "") for p in SPREADS[spread]]
    want = len(pos_pairs)
    rng = random.SystemRandom()          # 内核 CSPRNG，每次取新熵，不可复现
    indices = rng.sample(range(len(DECK)), want)
    cards = []
    for (pos, pos_meaning), idx in zip(pos_pairs, indices):
        name = DECK[idx]
        orientation = "逆位" if rng.getrandbits(1) else "正位"
        cards.append({
            "position": pos,
            "position_meaning": pos_meaning,
            "name": name,
            "orientation": orientation,
            "image": card_image(name),
            "meaning": knowledge.get_card_meaning(name, orientation),
        })
    return {
        "ok": True,
        "spread": spread,
        "spread_desc": meta.get("desc", ""),
        "question": question or "（来访者未明确说明）",
        "manual": False,
        "random_source": "os.urandom / SystemRandom (CSPRNG，不可复现)",
        "layout": spreads_mod.layout(spread),
        "cards": cards,
        "note": ("牌面由操作系统内核熵真随机产生：每次都不同、无法复现、无任何可重放的数字。"
                 "不放回，正逆位各半。请依据每张牌随附的传统牌意与该牌位在问什么来解读，"
                 "不要自行编造或替换牌意。"),
    }


def extra_card(result, reason=""):
    """来访者主动要求的「补一张」。

    补牌是模型不能做的动作（见 draw_cards 的 note），只能由用户在界面上点按钮
    触发；因此这个函数不进 TOOLS 表、也没有对应的 execute 分支，只由 server
    在识别到补牌请求时调用。补出的牌从 78 张里挑一张这副牌里没出现过的。
    """
    cards = list((result or {}).get("cards") or [])
    if not cards:
        return {"ok": False, "reason": "还没有可补牌的牌面"}
    used = {c.get("name") for c in cards}
    pool = [n for n in DECK if n not in used]
    if not pool:
        return {"ok": False, "reason": "这副牌已经抽满了 78 张，无从再补"}
    rng = random.SystemRandom()
    name = rng.choice(pool)
    orientation = "逆位" if rng.getrandbits(1) else "正位"
    reason = str(reason or "").strip()
    return {
        "ok": True,
        "reason": reason,
        "card": {
            "position": "补牌",
            "position_meaning": "来访者主动补的一张，用来看原先漏掉的侧面",
            "name": name,
            "orientation": orientation,
            "image": card_image(name),
            "meaning": knowledge.get_card_meaning(name, orientation),
            "extra": True,
            "reason": reason,
        },
    }


def search_knowledge(query=""):
    context, used = knowledge.retrieve(str(query), top_k=2)
    return {
        "ok": bool(context),
        "query": query,
        "docs": used,
        "context": context or "知识库中没有匹配到相关资料；不要臆测，可如实说明。",
    }


def save_memory(kind="fact", text=""):
    text = str(text).strip()
    if not text:
        return {"ok": False, "reason": "内容为空"}
    if memory.CRISIS_RE.search(text):
        return {"ok": False, "reason": "危机内容不入库"}
    kind = kind if kind in ("fact", "pref", "boundary") else "fact"
    ok = memory.add_fact(kind, text, pinned=(kind == "fact"))
    return {"ok": ok, "kind": kind, "text": text}


def crisis_check(text=""):
    hit = bool(memory.CRISIS_RE.search(str(text)))
    return {
        "ok": True,
        "crisis": hit,
        "note": ("检测到急性危机信号：立即停止抽牌与解读，先给求助资源并转介；"
                 "这条压过所有塔罗规则。") if hit else "未检测到急性危机信号。",
    }


def save_note(title="", content="", tags=""):
    nid = plugin_kb.add_note(title, content, tags, source="chat")
    return {"ok": nid is not None, "id": nid, "title": title,
            "note": "已归档到个人知识库。" if nid else "内容为空，未归档。"}


def search_notes(query=""):
    context, ids = plugin_kb.search_notes(str(query), top_k=3)
    return {"ok": bool(context), "query": query, "ids": ids,
            "context": context or "个人知识库中没有匹配的笔记；不要臆测。"}


def lookup_card(name="", orientation="两者"):
    """按牌名直查传统牌意（精确匹配，不走关键词检索）。"""
    raw = str(name or "").strip()
    if not raw:
        return {"ok": False, "reason": "牌名为空"}
    # 容忍「宝剑 8」「圣杯 ace」这类写法，统一到规范牌名
    norm = raw.replace(" ", "").replace("Ａ", "A")
    aliases = {"王牌": "王牌", "A": "王牌", "a": "王牌", "ace": "王牌", "Ace": "王牌"}
    for k, v in aliases.items():
        if norm.endswith(k) and len(norm) > len(k):
            norm = norm[:-len(k)] + v
            break
    if norm not in DECK:
        # 常见错写：数字写成阿拉伯数字
        zh = {"1": "王牌", "2": "二", "3": "三", "4": "四", "5": "五",
              "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}
        for suit in _SUITS:
            if norm.startswith(suit):
                tail = norm[len(suit):]
                if tail in zh:
                    norm = suit + zh[tail]
                    break
    if norm not in DECK:
        return {"ok": False, "name": raw,
                "reason": "牌库里没有这张牌；牌名要用「死神」「宝剑八」「圣杯王后」这种写法。",
                "examples": ["愚者", "死神", "宝剑八", "圣杯王后", "权杖王牌"]}
    want = str(orientation or "两者")
    out = {"ok": True, "name": norm}
    if want in ("正位", "两者"):
        out["正位"] = knowledge.get_card_meaning(norm, "正位")
    if want in ("逆位", "两者"):
        out["逆位"] = knowledge.get_card_meaning(norm, "逆位")
    out["image"] = card_image(norm)
    out["note"] = "这是既定的传统牌意，不要改写或替换；解读时按「牌意→牌位→问题→情境」使用。"
    return out


def recall_memory(what="facts", limit=10, text=""):
    """主动回忆：线索 / 画像 / 抽牌历史，或删掉一条线索。"""
    what = str(what or "facts")
    try:
        limit = max(1, min(int(limit or 10), 50))
    except (TypeError, ValueError):
        limit = 10
    if what == "forget":
        snippet = str(text or "").strip()
        if not snippet:
            return {"ok": False, "reason": "要删哪一条？请给出线索原文或其中一段。"}
        # 先按原文精确/包含匹配找到 id，再删；找不到就如实说
        facts = memory.list_facts(limit=200)
        hit = None
        for f in facts:
            if snippet in (f.get("text") or ""):
                hit = f
                break
        if not hit:
            return {"ok": False, "reason": "没有找到包含「%s」的线索。" % snippet[:30]}
        ok = memory.delete_fact(hit["id"])
        return {"ok": bool(ok), "deleted": hit.get("text", "")[:60] if ok else ""}
    if what == "profile":
        rows = memory.list_profile()
        return {"ok": True, "profile": [{"key": r.get("key"), "value": r.get("value")}
                                        for r in rows[:limit]]}
    if what == "draws":
        rows = memory.list_draws(limit=limit)
        out = []
        for d in rows:
            cards = "、".join(
                (c.get("name", "") + ("逆位" if c.get("reversed") else "正位"))
                for c in (d.get("cards") or []))
            out.append({"date": (d.get("created_at") or "")[:16],
                        "spread": d.get("spread", ""),
                        "cards": cards,
                        "question": d.get("question", "")})
        return {"ok": True, "draws": out}
    rows = memory.list_facts(limit=limit)
    return {"ok": True, "facts": [{"kind": r.get("kind"), "text": r.get("text"),
                                   "pinned": bool(r.get("pinned"))} for r in rows]}


def schedule_reminder(name="", intent="", kind="once", run_at="",
                      cron_time="09:00", weekday=0, interval_min=120):
    """给来访者建一个定时关怀任务（走 scheduler 的 tasks 表）。"""
    import re as _re
    kind = str(kind or "once")
    if kind not in ("once", "daily", "weekly", "interval"):
        return {"ok": False, "reason": "kind 只能是 once / daily / weekly / interval"}
    name = str(name or "").strip() or "主动关怀"
    intent = str(intent or "").strip() or "关心一下我最近怎么样"
    data = {"name": name[:60], "intent": intent[:400], "kind": kind,
            "enabled": True, "toast": True}
    if kind == "once":
        ra = str(run_at or "").strip().replace("/", "-")
        if not _re.match(r"^\d{4}-\d{1,2}-\d{1,2}([ T]\d{1,2}:\d{2})?$", ra):
            return {"ok": False,
                    "reason": "kind=once 需要 run_at，格式 YYYY-MM-DD HH:MM，例如 2026-12-25 09:00。"}
        if "T" in ra:
            ra = ra.replace("T", " ")
        if len(ra) == 10:                      # 只给日期 -> 默认当天 09:00
            ra += " 09:00"
        date_part, hm = ra.split(" ")
        y, mo, d = date_part.split("-")
        hh, mm = hm.split(":")
        data["run_at"] = "%s-%02d-%02d %02d:%02d" % (
            y, int(mo), int(d), int(hh), int(mm))
        data["cron_time"] = data["run_at"][11:]
    elif kind in ("daily", "weekly"):
        ct = str(cron_time or "09:00").strip()
        if not _re.match(r"^\d{1,2}:\d{2}$", ct):
            return {"ok": False, "reason": "cron_time 要用 HH:MM，例如 09:00。"}
        hh, mm = ct.split(":")
        data["cron_time"] = "%02d:%02d" % (int(hh), int(mm))
        if kind == "weekly":
            try:
                data["weekday"] = max(0, min(int(weekday or 0), 6))
            except (TypeError, ValueError):
                data["weekday"] = 0
    else:  # interval
        try:
            data["interval_min"] = max(5, int(interval_min or 120))
        except (TypeError, ValueError):
            data["interval_min"] = 120
    try:
        tid = scheduler_mod.add_task(data)
    except Exception as e:
        return {"ok": False, "reason": "创建定时任务失败：%s" % e}
    label = {"once": "仅一次", "daily": "每天", "weekly": "每周", "interval": "每隔"}[kind]
    when = (data.get("run_at") or data.get("cron_time") or
            ("%d 分钟" % data.get("interval_min", 120)))
    return {"ok": bool(tid), "id": tid, "name": data["name"],
            "when": "%s %s" % (label, when),
            "note": "已加入主动关怀；到点后消息会出现在「关怀」收件箱，"
                    "需要桌面通知请确认总开关已开。"}


EXECUTORS = {
    "draw_cards": lambda a: draw_cards_random(a.get("spread", "三张"), a.get("question", "")),
    "search_knowledge": lambda a: search_knowledge(a.get("query", "")),
    "save_memory": lambda a: save_memory(a.get("kind", "fact"), a.get("text", "")),
    "crisis_check": lambda a: crisis_check(a.get("text", "")),
    "save_note": lambda a: save_note(a.get("title", ""), a.get("content", ""), a.get("tags", "")),
    "search_notes": lambda a: search_notes(a.get("query", "")),
    "lookup_card": lambda a: lookup_card(a.get("name", ""), a.get("orientation", "两者")),
    "recall_memory": lambda a: recall_memory(a.get("what", "facts"),
                                             a.get("limit", 10), a.get("text", "")),
    "schedule_reminder": lambda a: schedule_reminder(
        a.get("name", ""), a.get("intent", ""), a.get("kind", "once"),
        a.get("run_at", ""), a.get("cron_time", "09:00"),
        a.get("weekday", 0), a.get("interval_min", 120)),
}


def execute(name, arguments=None):
    """Execute a tool call; always return a JSON-serialisable dict."""
    args = arguments if isinstance(arguments, dict) else {}
    fn = EXECUTORS.get(name)
    if not fn:
        return {"ok": False, "error": "未知工具：%s" % name}
    try:
        return fn(args)
    except Exception as e:
        return {"ok": False, "error": "工具执行失败：%s" % e}


def summary(name, result):
    """Short human-readable line for the UI tool badge."""
    if name == "draw_cards" and result.get("ok"):
        cards = "、".join("%s%s" % (c["name"], c["orientation"])
                        for c in result["cards"][:3])
        more = "…" if len(result["cards"]) > 3 else ""
        total = len(result.get("cards") or [])
        src = result.get("random_source")
        tag = " · 真随机" if src else ""
        return "抽牌：%s · %d 张（%s）%s%s" % (
            result["spread"], total, cards, more, tag)
    if name == "search_knowledge":
        return "检索资料：%s" % ("、".join(result.get("docs") or []) or "无匹配")
    if name == "save_memory":
        return "记住：%s" % result.get("text", "")[:30]
    if name == "crisis_check":
        return "危机检查：%s" % ("命中，转安全流程" if result.get("crisis") else "未命中")
    if name == "save_note":
        return "归档笔记：%s" % result.get("title", "")[:30]
    if name == "search_notes":
        return "检索笔记：%s" % ("、".join(str(i) for i in result.get("ids") or []) or "无匹配")
    if name == "lookup_card":
        if not result.get("ok"):
            return "查牌：%s" % (result.get("reason") or "未找到")
        return "查牌：%s（%s）" % (result.get("name", ""), "已取传统牌意")
    if name == "recall_memory":
        what = result.get("what") or ""
        if "facts" in result:
            return "回忆线索：%d 条" % len(result.get("facts") or [])
        if "profile" in result:
            return "回忆画像：%d 项" % len(result.get("profile") or [])
        if "draws" in result:
            return "回忆抽牌：%d 次" % len(result.get("draws") or [])
        if result.get("ok"):
            return "忘掉：%s" % (result.get("deleted") or "")[:30]
        return "回忆：%s" % (result.get("reason") or "无结果")
    if name == "schedule_reminder":
        if not result.get("ok"):
            return "定时关怀：%s" % (result.get("reason") or "创建失败")
        return "定时关怀：%s（%s）" % (result.get("name", ""), result.get("when", ""))
    return "工具 %s 执行完毕" % name
