# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
safety.py — Olivia 的独立安全闸门（stdlib only）。

设计原则（与 lunar-mirror 的做法不同，这是 Olivia 自己的路子）：

1. **服务端权威**：检测放在 server.py 的 /api/chat 入口，早于抽牌、早于
   视觉、早于 LLM、早于记忆写入。不依赖模型"记得调用 crisis_check"。
2. **不绕弯的中文句式**：覆盖"他打我了""我男朋友打我了""我被他打了"
   这类最常见的主谓宾表述，而不是只认"我被……"的书面句式。
3. **否定处理**："我不会自杀的""我没有想死"不报警；"我不想活了"报警。
4. **沉默不入库**：命中时由 server 直接返回安全文案，不抽牌、不记记忆。

本模块只做判定与文案，不碰网络、不碰数据库。
"""

import re

# ---------- 自伤 / 轻生 ----------
_SELF_HARM_PATTERNS = [
    r"自杀", r"自残", r"自伤", r"轻生", r"寻死",
    r"想死(?!你|我|他|她|它|人)",
    r"不想活", r"不想再活", r"活不下去", r"活不下",
    r"撑不下去", r"撑不住了", r"熬不下去",
    r"结束生命", r"结束自己的生命", r"了结自己", r"了结生命",
    r"割腕", r"跳楼", r"服毒", r"上吊", r"吞药", r"过量服药", r"烧炭",
    r"伤害自己", r"伤害我自己", r"把自己弄死", r"弄死自己",
    r"活着(?:真|好|太|很)?(?:没意思|没有意义|没意义|太累|好累|太痛苦|很痛苦|没劲)",
    r"人生(?:没有|没)意义", r"活着没意思",
]
_SELF_HARM_RE = [re.compile(p) for p in _SELF_HARM_PATTERNS]

# 紧贴在关键词前面的否定词 —— 只抵消它后面那一个命中，
# 同一句话里若还有其它真实命中，照样报警。
_NEGATION_BEFORE = re.compile(r"(?:不会|没有|绝不|从不|不打算|没必要|不用|不是)(?:再)?(?:去)?$")


# ---------- 他人施暴 / 威胁 ----------
# 打(电话/球/游戏/招呼…) 不是暴力，必须排除。
_HIT = (r"(?:打(?!电话|手机|招呼|球|游戏|字|车|工|扫|开)|揍|砍|捅|杀|伤害|"
        r"威胁|骚扰|跟踪|强奸|猥亵|性侵|殴打|家暴)")
_ACTOR = (r"(?:有人|他|她|他们|那个人|同事|领导|老公|老婆|男友|女友|"
          r"男朋友|女朋友|父亲|母亲|爸爸|妈妈|室友|邻居|孩子|家里人|"
          r"我老公|我老婆|我男朋友|我女朋友|我同学|我老师|我老板|我哥|我姐)")

_THREAT_PATTERNS = [
    _ACTOR + r".{0,12}" + _HIT + r"(?:了|过)?(?:我|我们)",
    r"我(?:被|让|给)(?:他|她|他们|人)?.{0,6}" + _HIT,
    r"我被(?:家暴|殴打|威胁|跟踪|性侵|强奸|猥亵)",
    r"家暴|家庭暴力",
    r"(?:要|想|扬言|准备|打算).{0,6}(?:杀|弄死|打死|砍死)(?:了)?(?:我|我们)",
    _ACTOR + r".{0,4}(?:拿|带|举)(?:刀|枪).{0,6}(?:冲|朝|对|砍|捅)(?:我|我们)?",
]
_THREAT_RE = [re.compile(p) for p in _THREAT_PATTERNS]

# 梦境/虚构语境：不做危机判定（"我梦到有人追杀我"不是现实威胁）
_DREAM_RE = re.compile(r"梦到|梦见|梦里|做梦|梦境|幻想|小说|电影里|电视剧")


# ---------- 伤害他人 ----------
_HARM_OTHERS_PATTERNS = [
    r"我.{0,8}(?:想|要|准备|打算|计划)(?:去)?(?:杀|弄死|捅|砍|打死)(?:了)?.{0,10}(?:他|她|他们|人|某人)",
    r"(?:怎么|如何)(?:杀人|弄死|伤害别人|伤害他人|下毒)",
    r"让(?:他|她|他们|你|某人)死",
    r"(?:拿|带|买)(?:刀|枪).{0,8}(?:捅|砍|杀|弄死)",
]
_HARM_OTHERS_RE = [re.compile(p) for p in _HARM_OTHERS_PATTERNS]


# ---------- 性侵 / 性暴力 ----------
_SEXUAL_ASSAULT_PATTERNS = [
    r"(?:我被|我遭到|我遭遇|遭到|遭遇)(?:强奸|性侵|猥亵|性骚扰)",
    r"被(?:人|他|她|他们)?(?:强奸|性侵|猥亵|性骚扰)",
    _ACTOR + r".{0,8}(?:强奸|性侵|猥亵|性骚扰)(?:我|我们)",
    r"(?:被|遭)(?:强迫|逼迫).{0,4}(?:发生关系|性行为)",
]
_SEXUAL_ASSAULT_RE = [re.compile(p) for p in _SEXUAL_ASSAULT_PATTERNS]

_SEXUAL_HARM_PATTERNS = [
    r"(?:我|自己).{0,8}(?:想|要|准备|打算|计划)(?:去)?(?:强奸|性侵|猥亵|性骚扰)",
    r"怎么(?:强奸|性侵|猥亵|性骚扰)",
]
_SEXUAL_HARM_RE = [re.compile(p) for p in _SEXUAL_HARM_PATTERNS]

# ---------- English patterns ----------
# 英文人格包已可用，闸门不能只认中文。英文不做逐词否定解析，
# 而是看命中词前 24 个字符里是否出现否定词，宁可再生一次误报也不漏。
_EN_SELF_HARM_PATTERNS = [
    r"\b(?:kill|killing)\s+myself\b",
    r"\bsuicid(?:e|al)\b",
    r"\bend\s+(?:my|this)\s+life\b",
    r"\b(?:want|wanna|going)\s+to\s+die\b",
    r"\bdon'?t\s+want\s+to\s+(?:live|be\s+alive)\b",
    r"\b(?:cut|hurt|harm)\s+myself\b",
    r"\bno\s+reason\s+to\s+live\b",
    r"\bbetter\s+off\s+dead\b",
    r"\bcan'?t\s+go\s+on\s+living\b",
]
_EN_SELF_HARM_RE = [re.compile(p, re.I) for p in _EN_SELF_HARM_PATTERNS]

_EN_NEG_BEFORE = re.compile(
    r"(?:not|never|don'?t|doesn'?t|didn'?t|wouldn'?t|won'?t|isn'?t|ain'?t|"
    r"no\s+longer|no\s+intention\s+of)\s+(?:\w+\s+){0,3}$", re.I)

_EN_DREAM_RE = re.compile(
    r"\b(?:dream(?:t|ed|ing)?|in\s+my\s+dream|movie|film|novel|fiction|"
    r"video\s+game|roleplay)\b", re.I)

_EN_THREAT_RE = [
    re.compile(p, re.I) for p in [
        r"\b(?:he|she|they|my\s+(?:husband|wife|boyfriend|girlfriend|partner|"
        r"father|mother|dad|mom|roommate|boss|colleague))\s+"
        r"(?:hit|hits|beat|beats|punched|slapped|choked|strangled|kicked)\s+me\b",
        r"\b(?:i\s+was|i'?ve\s+been)\s+(?:hit|beaten|abused|assaulted|raped|"
        r"sexually\s+assaulted|molested|stalked)\b",
        r"\bdomestic\s+(?:violence|abuse)\b",
        r"\b(?:he|she|they)\s+threatened\s+to\s+(?:kill|hurt|harm)\s+me\b",
        r"\b(?:someone|somebody)\s+is\s+(?:following|stalking)\s+me\b",
    ]
]

_EN_HARM_OTHERS_RE = [
    re.compile(p, re.I) for p in [
        r"\bi\s+(?:want|wanna|plan|intend|am\s+going)\s+to\s+"
        r"(?:kill|murder|shoot|stab|strangle)\s+(?:him|her|them|someone|somebody)\b",
        r"\bhow\s+to\s+(?:kill|murder|poison)\s+(?:someone|somebody|a\s+person)\b",
        r"\bi\s+(?:want|plan)\s+to\s+hurt\s+(?:him|her|them)\b",
    ]
]


def _any(patterns, text):
    return any(p.search(text) for p in patterns)


def _self_harm_hit(text):
    for p in _SELF_HARM_RE:
        for m in p.finditer(text):
            prefix = text[max(0, m.start() - 6):m.start()]
            if _NEGATION_BEFORE.search(prefix):
                continue
            return True
    for p in _EN_SELF_HARM_RE:
        for m in p.finditer(text):
            prefix = text[max(0, m.start() - 24):m.start()]
            if _EN_NEG_BEFORE.search(prefix):
                continue
            return True
    return False


def detect(text):
    """返回危机类别字符串，或 None。

    类别：sexual-assault / sexual-harm / threat / harm-others / self
    """
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return None
    if _DREAM_RE.search(t) or _EN_DREAM_RE.search(t):
        return None
    if _any(_SEXUAL_ASSAULT_RE, t):
        return "sexual-assault"
    if _any(_SEXUAL_HARM_RE, t):
        return "sexual-harm"
    # 先判"我要伤害别人"，避免"我想杀了那个伤害我的人"被威胁句式吃掉
    if _any(_HARM_OTHERS_RE, t) or any(p.search(t) for p in _EN_HARM_OTHERS_RE):
        return "harm-others"
    if _any(_THREAT_RE, t) or any(p.search(t) for p in _EN_THREAT_RE):
        return "threat"
    if _self_harm_hit(t):
        return "self"
    return None


# ---------- 可选的语言学兜底 ----------
# 正则抓不到隐喻/间接表达。开启 safety_second_check 后，命中这些模糊词
# 才额外让模型做一次很小的 YES/NO 判定，避免每轮都多花一次调用。
_AMBIGUOUS = re.compile(
    r"(不想存在|消失掉|结束这一切|一了百了|想解脱|不想醒来|"
    r"better\s+off\s+without\s+me|end\s+it\s+all|no\s+way\s+out|"
    r"tired\s+of\s+living|don'?t\s+want\s+to\s+be\s+here)", re.I)

SECOND_CHECK_PROMPT = (
    "你是安全分类器。判断下面这句话是否表达了自伤、轻生、被暴力伤害或伤害他人的"
    "现实意图（不是电影/小说/梦境/比喻）。只输出一个词：YES 或 NO。\n\n"
)


def needs_second_check(text):
    return bool(_AMBIGUOUS.search(str(text or "")))


def parse_second_check(reply):
    return bool(re.search(r"\bYES\b", str(reply or ""), re.I))



def is_crisis(text):
    return detect(text) is not None


# ---------- 安全回应（Olivia 自己的口吻：稳、短、可执行） ----------
_COMMON = (
    "我现在不能以占卜的身份回应你——你说的这些让我担心你的安全。\n\n"
    "先把牌放一放，你不需要一个人扛：\n"
    "· 如果有人正在伤害你或威胁你，请立刻拨打 110。\n"
    "· 如果你有伤害自己的念头，请马上联系身边信任的人，或拨打当地心理危机热线、120、110。\n"
    "· 情况紧急就直接去医院急诊。\n\n"
    "等你确认安全了，我再陪你看牌。这不是拒绝你——是我更在意你能不能好好地坐在这里。"
)

RESPONSES = {
    "self": _COMMON,
    "threat": (
        "我现在不能以占卜的身份回应你——有人让你处在不安全里，这件事比牌面重要得多。\n\n"
        "如果此刻有危险，请立刻离开现场并拨打 110；也可以联系信任的人陪着你，"
        "或拨打当地心理援助热线。受伤就直接去医院急诊或拨打 120。\n\n"
        "等安全了，我们再坐下来看牌。"
    ),
    "sexual-assault": (
        "我现在不能以占卜的身份回应你——你经历的这件事，不该由一副牌来评说。\n\n"
        "如果正处于危险中请拨打 110；事后也可以联系当地妇联、法律援助或心理援助热线。"
        "你愿意说，我就在这里听；不愿意说，也完全没关系。"
    ),
    "sexual-harm": _COMMON,
    "harm-others": (
        "我现在不能以占卜的身份回应你——我听到的是你已经被推到很边缘的位置。\n\n"
        "请先离开可能让自己或别人受伤的场景，联系身边的人或拨打 110 / 120。"
        "等这阵过去，我们再谈牌。"
    ),
}

DEFAULT_RESPONSE = _COMMON


def response_for(kind):
    return RESPONSES.get(kind, DEFAULT_RESPONSE)
