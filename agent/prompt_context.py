# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Pure helpers for prompt-file loading and the current-time system anchor."""

import datetime
import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PERSONA_DIR = os.path.join(REPO_DIR, "prompts")


def _disk_language():
    """Mirror the language part of server.load_config() without importing server."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return str((json.load(f) or {}).get("language") or "zh").lower()
    except Exception:
        return "zh"


def _lang(cfg=None):
    # Mirrors server._lang(): a falsy cfg fetches the on-disk config, exactly as
    # load_config() would; a truthy cfg uses its own "language" field.
    lang = _disk_language() if not cfg else str(cfg.get("language") or "zh").lower()
    return "en" if lang.startswith("en") else "zh"


def _prompt_path(name, lang):
    """prompts/<name>.<lang>.md，英文缺失时回退中文。"""
    path = os.path.join(PERSONA_DIR, "%s.%s.md" % (name, lang))
    if os.path.exists(path):
        return path
    return os.path.join(PERSONA_DIR, "%s.zh.md" % name)


def load_persona(cfg=None):
    try:
        with open(_prompt_path("persona", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return "你是一名沉稳、专业的塔罗咨询师 Olivia（奥莉薇娅）。"


def load_prophecy(cfg=None):
    """预言模式覆盖层（仅供娱乐），仅在开启时加载。"""
    try:
        with open(_prompt_path("prophecy", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def load_occult(cfg=None):
    """神秘学模式覆盖层：通灵 / 召唤 / 仪式这类话题的语境与边界，仅在用户开启时加载。"""
    try:
        with open(_prompt_path("occult", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def load_tone(cfg=None):
    """语气系统：让 Olivia 的措辞像一个真实女性塔罗师，并自然体现 NVC。"""
    try:
        with open(_prompt_path("tone", _lang(cfg)), "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def now_context(cfg=None):
    """把「现在几点」写进 system。

    语气层要求建议落到具体时间（「今晚睡前」「明天上午」），但没有这个锚点，
    模型只能猜今天是哪天。这里每轮现算，不用缓存。
    """
    now = datetime.datetime.now()
    if _lang(cfg) == "en":
        return (
            "\n\n[Current time] It is %s %02d:%02d, %d-%02d-%02d. "
            "Use this clock for relative times such as tonight, tomorrow or this week; "
            "never guess a year from training data."
            % (now.strftime("%A"), now.hour, now.minute, now.year, now.month, now.day)
        )
    week = "一二三四五六日"[now.weekday()]
    return (
        "\n\n【当前时间】现在是 %d年%d月%d日（星期%s）%02d:%02d。"
        "涉及今天、今晚、明天、这周等相对时间的建议和定时提醒，都以这个时间为准；"
        "不要使用你的训练数据里的日期，也不要编造年份。"
        % (now.year, now.month, now.day, week, now.hour, now.minute)
    )
