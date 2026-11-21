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
调用工具后，依据工具返回的结果继续；工具没给的信息绝不编造。""" % spreads_mod.catalogue()



TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "draw_cards",
            "description": "保留工具：抽牌正常由系统在本地完成，不要主动调用本工具；"
                           "仅在系统把牌面交给你解读时使用，不要自己生成牌名。",
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
                    "seed": {
                        "type": "integer",
                        "description": "可选：复现同一副牌用的随机数种子。一般情况下留空，由系统客观随机生成。",
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
]


def draw_cards(spread="三张", question="", seed=None):
    """Objective random draw. Returns structured result for the model.

    ``seed`` 只影响牌面与正逆位的产生：给同一个 seed（同一牌阵）必然抽到
    同一副牌。每次抽牌都会生成一个 seed 并随结果返回，供用户复现/自证；
    不指定 seed 时用系统熵生成一个，行为与改造前同样是客观随机。
    """
    spread = spread if spread in SPREADS else "三张"
    meta = spreads_mod.SPREAD_META.get(spread) or {}
    pos_pairs = meta.get("positions") or [(p, "") for p in SPREADS[spread]]
    # 每次抽牌都落一个 seed，用户据此可重放同一副牌（自证没有临时挑牌）。
    if seed is None:
        seed = random.SystemRandom().randrange(0, 2 ** 31)
    try:
        seed = int(seed)
    except (TypeError, ValueError):
        seed = random.SystemRandom().randrange(0, 2 ** 31)
    rng = random.Random(seed)
    # Sample WITHOUT replacement from the canonical 78-card deck: the same
    # card cannot appear twice in one spread (standard tarot rule).
    indices = rng.sample(range(78), len(pos_pairs))
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
        "seed": seed,
        "layout": spreads_mod.layout(spread),
        "cards": cards,
        "note": "牌面由工具客观随机产生，抽到什么解什么；不得更换、补牌或主观挑选。"
                "请依据每张牌随附的传统牌意（核心/正位/逆位）与该牌位在问什么来解读，"
                "不要自行编造牌意，也不要把其他牌位的含义套到这里。",
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


EXECUTORS = {
    "draw_cards": lambda a: draw_cards(a.get("spread", "三张"), a.get("question", ""), a.get("seed")),
    "search_knowledge": lambda a: search_knowledge(a.get("query", "")),
    "save_memory": lambda a: save_memory(a.get("kind", "fact"), a.get("text", "")),
    "crisis_check": lambda a: crisis_check(a.get("text", "")),
    "save_note": lambda a: save_note(a.get("title", ""), a.get("content", ""), a.get("tags", "")),
    "search_notes": lambda a: search_notes(a.get("query", "")),
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
        seed = result.get("seed")
        seed_txt = " · 种子 %s" % seed if seed is not None else ""
        return "抽牌：%s · %d 张（%s）%s%s" % (
            result["spread"], total, cards, more, seed_txt)
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
    return "工具 %s 执行完毕" % name
