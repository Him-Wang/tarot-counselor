# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""archive.py — 占卜档案（stdlib only）。

每次占卜追加一条 JSON：时间、问题、牌阵、解读要点、用户情绪标签。
情绪标签必须由 Olivia 询问用户、得到答复后记录——不猜测、不从文本推断。

读档函数按用户 / 主题 / 关键词检索。档案是纯本地个人数据：
默认落在 agent/data/archive/（已被 .gitignore 排除，不会进版本库）。
危机内容不写入档案（与 memory 的安全策略一致）。
"""

import json
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARCHIVE_DIR = os.path.join(BASE_DIR, "data", "archive")

# 占卜档案不是医疗/心理病历；不做诊断式标签，只记录用户亲口说出的情绪词。
KNOWN_EMOTIONS = (
    "平静", "焦虑", "难过", "开心", "愤怒", "迷茫", "纠结", "疲惫",
    "放松", "期待", "失落", "害怕", "安心", "委屈", "愧疚", "希望",
)


def _safe(s):
    return re.sub(r"[^\w\u4e00-\u9fff-]", "_", str(s or "default"))[:60] or "default"


def _path(user):
    return os.path.join(ARCHIVE_DIR, _safe(user or "default") + ".jsonl")


def _now_s():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _read_all(user=None):
    """读取一个或多个用户的全部记录（最新在后）。"""
    if not os.path.isdir(ARCHIVE_DIR):
        return []
    names = []
    if user:
        p = _path(user)
        if os.path.isfile(p):
            names = [p]
    else:
        names = [os.path.join(ARCHIVE_DIR, f) for f in sorted(os.listdir(ARCHIVE_DIR))
                 if f.endswith(".jsonl")]
    out = []
    for p in names:
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except (ValueError, TypeError):
                        continue
        except OSError:
            continue
    out.sort(key=lambda r: r.get("created_at", ""))
    return out


def append(user, question, spread, points, emotion_tags=None, cards=None, extra=None):
    """追加一条占卜档案，返回记录 id（时间戳串）。

    emotion_tags 只接受用户亲口确认过的情绪词；调用方（Olivia）负责先询问。
    危机文本不入库。
    """
    try:
        import safety as _safety
        if _safety.detect(str(question or "")) or _safety.detect(str(points or "")):
            return None
    except Exception:
        pass
    tags = []
    for t in (emotion_tags or []):
        t = str(t).strip()
        if t and t in KNOWN_EMOTIONS and t not in tags:
            tags.append(t)
        elif t and t not in KNOWN_EMOTIONS and t not in tags:
            # 用户亲口说的自定义情绪词也保留，但去掉控制字符。
            t = re.sub(r"[\x00-\x1f]", "", t)[:24]
            if t:
                tags.append(t)
    rec = {
        "id": datetime.now().strftime("%Y%m%d%H%M%S%f"),
        "created_at": _now_s(),
        "user": str(user or "default").strip() or "default",
        "question": str(question or "").strip()[:2000],
        "spread": str(spread or "").strip()[:120],
        "points": str(points or "").strip()[:4000],
        "emotion_tags": tags,
        "cards": [str(c) for c in (cards or [])][:30],
    }
    if extra and isinstance(extra, dict):
        for k in ("session_id", "source", "note"):
            if k in extra:
                rec[k] = str(extra[k])[:500]
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    with open(_path(rec["user"]), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec["id"]


def search(query="", user=None, topic=None, limit=20):
    """按用户 / 主题 / 自由词检索档案，返回记录列表（最新在前）。

    topic 匹配问题、牌阵、解读要点与情绪标签；query 做同样的全文包含匹配。
    """
    q = str(query or "").strip().lower()
    topic = str(topic or "").strip().lower()
    hits = []
    for r in reversed(_read_all(user)):
        hay = " ".join(str(r.get(k, "")) for k in
                       ("question", "spread", "points", "user")) + " " + \
              " ".join(r.get("emotion_tags") or [])
        low = hay.lower()
        if q and q not in low:
            continue
        if topic and topic not in low:
            continue
        hits.append(r)
        if limit and len(hits) >= limit:
            break
    return hits


def by_user(user, limit=20):
    return search(user=user, limit=limit)


def by_topic(topic, limit=20):
    return search(topic=topic, limit=limit)


def stats():
    recs = _read_all()
    return {"total": len(recs), "users": len(set(r.get("user", "default") for r in recs))}


def clear(user=None):
    """清空某个用户（或全部）的档案。"""
    if not os.path.isdir(ARCHIVE_DIR):
        return True
    if user:
        p = _path(user)
        if os.path.isfile(p):
            os.remove(p)
    else:
        for f in os.listdir(ARCHIVE_DIR):
            if f.endswith(".jsonl"):
                os.remove(os.path.join(ARCHIVE_DIR, f))
    return True
