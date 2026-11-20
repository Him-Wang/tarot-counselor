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
import random

import knowledge
import memory
import plugin_kb

# Standard spreads and their position labels (RWS tradition).
SPREADS = {
    "单张": ["指引"],
    "三张": ["过去", "现在", "未来"],
    "凯尔特十字": ["现状", "阻碍", "意识目标", "潜意识根基", "过去", "未来",
                 "自我", "所处环境", "希望与恐惧", "最终结果"],
}

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

TOOL_GUIDE = """【可用工具 / 必须遵守】
- draw_cards(spread, question)：来访者请求抽牌、占卜、看牌时**必须**调用此工具。
  spread 只能是「单张」「三张」「凯尔特十字」。牌面由工具客观随机产生，
  你绝不能自己编牌名、挑牌、换牌，也不能把记忆里的旧牌当作本次牌面。
- search_knowledge(query)：需要专业资料（咨询技术、伦理、危机干预）时调用。
- save_memory(kind, text)：来访者明确表达偏好/边界，或说「请记住」时调用。
- crisis_check(text)：察觉自伤、安全风险或严重侵害时调用；命中后立即跳出塔罗师角色走安全流程。
- save_note(title, content, tags)：来访者要求「记到知识库/归档/笔记本」、或值得长期留存的
  结构化内容（问卷、清单、重要决定）时调用。它与 save_memory 不同：这里是用户主动归档的笔记。
- search_notes(query)：需要调阅用户此前归档的笔记/知识库内容时调用。
调用工具后，依据工具返回的结果继续；工具没给的信息绝不编造。"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "draw_cards",
            "description": "按指定牌阵客观随机抽牌，返回每张牌的牌名、正逆位和牌阵位置。"
                           "用户请求抽牌/占卜/看牌时必须调用，不要自己生成牌名。",
            "parameters": {
                "type": "object",
                "properties": {
                    "spread": {
                        "type": "string",
                        "enum": list(SPREADS.keys()),
                        "description": "牌阵：单张 / 三张 / 凯尔特十字",
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
]


def draw_cards(spread="三张", question=""):
    """Objective random draw. Returns structured result for the model."""
    spread = spread if spread in SPREADS else "三张"
    positions = SPREADS[spread]
    rng = random.SystemRandom()
    # Sample WITHOUT replacement from the canonical 78-card deck: the same
    # card cannot appear twice in one spread (standard tarot rule).
    indices = rng.sample(range(78), len(positions))
    cards = []
    for pos, idx in zip(positions, indices):
        name = DECK[idx]
        reversed_ = bool(rng.getrandbits(1))
        cards.append({
            "position": pos,
            "name": name,
            "orientation": "逆位" if reversed_ else "正位",
        })
    return {
        "ok": True,
        "spread": spread,
        "question": question or "（来访者未明确说明）",
        "cards": cards,
        "note": "牌面由工具客观随机产生，抽到什么解什么；不得更换、补牌或主观挑选。",
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
    "draw_cards": lambda a: draw_cards(a.get("spread", "三张"), a.get("question", "")),
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
        return "抽牌：%s（%s）%s" % (result["spread"], cards, more)
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
