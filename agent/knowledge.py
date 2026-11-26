# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
knowledge.py — lightweight keyword auto-retrieval over the knowledge/ directory.

No jieba needed: Chinese is handled with character bigrams + substring
matching, which works well enough for topic lookup without dependencies.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
KNOWLEDGE_DIR = os.path.join(REPO_DIR, "knowledge")
MEANINGS_DIR = os.path.join(KNOWLEDGE_DIR, "meanings")

# stop tokens that carry little topic signal
STOP = set("的 了 和 是 在 我 你 他 她 它 们 这 那 有 就 不 也 都 而 及 与 或 一个 什么 怎么 一些 可以 需要 是否 请 帮 我想 觉得 因为 所以 但是 如果 已经 还是 现在 自己".split())


def _read_files():
    docs = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return docs
    for root, _dirs, files in os.walk(KNOWLEDGE_DIR):
        for fn in files:
            if not fn.lower().endswith((".md", ".txt")):
                continue
            if fn.upper() == "INDEX.MD":
                continue  # index is navigation, not content
            path = os.path.join(root, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            rel = os.path.relpath(path, KNOWLEDGE_DIR).replace("\\", "/")
            docs.append({"rel": rel, "text": text})
    return docs


def _tokens(query):
    q = query.strip().lower()
    toks = set()
    # latin / digit words
    for w in re.findall(r"[a-z0-9]{2,}", q):
        if w not in STOP:
            toks.add(w)
    # Chinese character bigrams + individual chars
    han = re.findall(r"[\u4e00-\u9fff]", q)
    for i in range(len(han) - 1):
        toks.add(han[i] + han[i + 1])
    for c in han:
        if c not in STOP:
            toks.add(c)
    return toks


OCCULT_PREFIX = "occult/"


def retrieve(query, top_k=3, max_chars=9000, include_occult=False):
    """Return (selected_docs_as_context_string, list_of_relpaths_used).

    include_occult=False 时 knowledge/occult/ 下的资料完全不参与检索——
    神秘学语境库只有在用户显式打开「神秘学模式」后才进上下文。
    """
    docs = _read_files()
    if not include_occult:
        docs = [d for d in docs if not d["rel"].replace("\\", "/").startswith(OCCULT_PREFIX)]
    if not docs or not query.strip():
        return "", []

    toks = _tokens(query)
    if not toks:
        return "", []

    scored = []
    for d in docs:
        text = d["text"].lower()
        score = 0
        for t in toks:
            c = text.count(t)
            if c:
                # bigrams weigh more than single chars
                score += c * (2 if len(t) >= 2 else 1)
        # metadata title/tag lines get a boost
        head = "\n".join(text.splitlines()[:8])
        for t in toks:
            if t in head:
                score += 3
        # 神秘学语境库是本轮显式开启才进来的：篇幅短，若按原始命中次数
        # 排序会被牌义词条那种大文件整片压住，这里按 1.6 倍加权。
        if include_occult and d["rel"].replace("\\", "/").startswith(OCCULT_PREFIX):
            score = int(score * 1.6)
        if score:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])

    used = []
    parts = []
    total = 0
    for _score, d in scored:
        if len(used) >= top_k or total >= max_chars:
            break
        chunk = d["text"].strip()
        if total + len(chunk) > max_chars:
            chunk = chunk[:max(0, max_chars - total)]
        if not chunk:
            continue
        parts.append("【资料：%s】\n%s" % (d["rel"], chunk))
        used.append(d["rel"])
        total += len(chunk)

    return ("\n\n".join(parts), used) if parts else ("", [])


def list_docs(include_occult=False):
    docs = _read_files()
    if not include_occult:
        docs = [d for d in docs if not d["rel"].replace("\\", "/").startswith(OCCULT_PREFIX)]
    return [d["rel"] for d in docs]


_MEANINGS_CACHE = {}


def _append_note(card, bucket, text):
    """Append a "- xx补充：" line to an existing meaning bucket."""
    text = text.strip()
    if not text:
        return
    cur = _MEANINGS_CACHE[card].get(bucket, "")
    _MEANINGS_CACHE[card][bucket] = (cur + " " + text).strip() if cur else text


def _load_meanings():
    """Parse knowledge/meanings/*.md into {card_name: {'core','正位','逆位'}}."""
    if _MEANINGS_CACHE:
        return _MEANINGS_CACHE
    if not os.path.isdir(MEANINGS_DIR):
        return _MEANINGS_CACHE
    import re as _re
    for root, _dirs, files in os.walk(MEANINGS_DIR):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            # m4: parser state must NOT leak between files — a file ending
            # on a heading used to attach its continuation lines to the next
            # file's last card.
            current = None
            bucket = None
            path = os.path.join(root, fn)
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if line.startswith("## "):
                        current = line[3:].strip()
                        bucket = None
                        if current:
                            _MEANINGS_CACHE.setdefault(current, {})
                        continue
                    if current is None:
                        continue
                    if line.startswith("- 核心："):
                        _MEANINGS_CACHE[current]["core"] = line[len("- 核心："):].strip()
                        bucket = None
                    elif line.startswith("核心："):
                        _MEANINGS_CACHE[current]["core"] = line[len("核心："):].strip()
                        bucket = None
                    elif line.startswith("- 正位："):
                        _MEANINGS_CACHE[current]["正位"] = line[len("- 正位："):].strip()
                        bucket = "正位"
                    elif line.startswith("- 逆位："):
                        _MEANINGS_CACHE[current]["逆位"] = line[len("- 逆位："):].strip()
                        bucket = "逆位"
                    elif line.startswith("- 正位补充："):
                        _append_note(current, "正位", line[len("- 正位补充："):])
                        bucket = None
                    elif line.startswith("- 逆位补充："):
                        _append_note(current, "逆位", line[len("- 逆位补充："):])
                        bucket = None
                    elif line.startswith("- 牌面象征："):
                        _MEANINGS_CACHE[current].setdefault("象征", []).append(
                            line[len("- 牌面象征："):].strip())
                        bucket = None
                    elif line.startswith("- 宫廷牌视角："):
                        _MEANINGS_CACHE[current].setdefault("视角", []).append(
                            line[len("- 宫廷牌视角："):].strip())
                        bucket = None
                    elif bucket and line and not line.startswith(("#", "-")):
                        # only plain continuation lines extend the bucket;
                        # stray headings/bullets must not be appended
                        _MEANINGS_CACHE[current][bucket] += " " + line
    return _MEANINGS_CACHE


def get_card_meaning(name, orientation="正位"):
    """Return the RWS meaning note for a card, or '' if not found."""
    m = _load_meanings().get(name)
    if not m:
        return ""
    core = m.get("core", "")
    body = m.get(orientation, "")
    parts = []
    if core:
        parts.append("核心：" + core)
    symbols = m.get("象征") or []
    if symbols:
        parts.append("牌面：" + "；".join(symbols))
    if body:
        parts.append(orientation + "：" + body)
    view = m.get("视角") or []
    if view:
        parts.append("宫廷牌：" + "；".join(view))
    return " ".join(parts)

def get_card_entry(name):
    """Structured meaning for one card, for the 牌义 page."""
    m = _load_meanings().get(name) or {}
    return {
        "core": (m.get("core") or "").strip(),
        "up": (m.get("正位") or "").strip(),
        "rev": (m.get("逆位") or "").strip(),
        "symbols": [x.strip() for x in (m.get("象征") or []) if x and x.strip()][:4],
    }
