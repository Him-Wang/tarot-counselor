# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""
knowledge.py — lightweight keyword auto-retrieval over the knowledge/ directory.

No jieba needed: Chinese is handled with character bigrams + substring
matching, which works well enough for topic lookup without dependencies.
English (lang="en") uses the mirror under knowledge/en/ with lowercase word
tokenization; every public function keeps its old behaviour when lang is
omitted.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(BASE_DIR)
KNOWLEDGE_DIR = os.path.join(REPO_DIR, "knowledge")
MEANINGS_DIR = os.path.join(KNOWLEDGE_DIR, "meanings")

# stop tokens that carry little topic signal
STOP = set("的 了 和 是 在 我 你 他 她 它 们 这 那 有 就 不 也 都 而 及 与 或 一个 什么 怎么 一些 可以 需要 是否 请 帮 我想 觉得 因为 所以 但是 如果 已经 还是 现在 自己".split())
# English function words are filtered only on the English path; the Chinese
# path is byte-for-byte identical to the original implementation.
STOP_EN = set("""a an the and or but if then than is are was were be been being am do does did doing have has had having
it its it's this that these those i you your yours he him his she her hers we us our ours they them their theirs me my
of in on at to for from with without within into onto over under about above below between through during before after
as by so not no nor yes can could may might must shall should will would just also very more most less least much many
some any all each every both either neither own same such other another what which who whom whose when where why how
there here please want need like know think feel tell give take make get go come see look find use using used one two
three well really okay ok""".split())


def _is_en(lang):
    """True only for English requests ('en', 'en-US', ...)."""
    return str(lang or "").strip().lower().startswith("en")


def _doc_root(lang=None):
    """Return the knowledge root for a language.

    en -> knowledge/en (English mirror); zh / None -> knowledge (original).
    """
    if _is_en(lang):
        return os.path.join(KNOWLEDGE_DIR, "en")
    return KNOWLEDGE_DIR


def _meanings_root(lang=None):
    return os.path.join(_doc_root(lang), "meanings")


def _read_files(lang=None):
    root = _doc_root(lang)
    docs = []
    if not os.path.isdir(root):
        return docs
    for dirpath, _dirs, files in os.walk(root):
        if not _is_en(lang):
            # The English mirror lives inside knowledge/en/. Callers without
            # lang must keep seeing only the original Chinese tree.
            _dirs[:] = [d for d in _dirs if d.lower() != "en"]
        for fn in files:
            if not fn.lower().endswith((".md", ".txt")):
                continue
            if fn.upper() == "INDEX.MD":
                continue  # index is navigation, not content
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue
            rel = os.path.relpath(path, root).replace("\\", "/")
            docs.append({"rel": rel, "text": text})
    return docs


def _tokens(query, lang=None):
    """Tokenize a query. The Chinese path is unchanged; English splits on
    non-letters and lowercases, with stopword filtering."""
    q = query.strip().lower()
    if _is_en(lang):
        toks = set()
        for w in re.findall(r"[a-z]+", q):
            if len(w) >= 2 and w not in STOP_EN:
                toks.add(w)
        return toks
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


def retrieve(query, top_k=3, max_chars=9000, include_occult=False, lang=None):
    """Return (selected_docs_as_context_string, list_of_relpaths_used).

    include_occult=False 时 knowledge/occult/ 下的资料完全不参与检索——
    神秘学语境库只有在用户显式打开「神秘学模式」后才进上下文。
    With lang="en", reads knowledge/en/ and uses English tokenization; any
    missing English file falls back to the Chinese tree.
    """
    docs = _read_files(lang)
    if not include_occult:
        docs = [d for d in docs if not d["rel"].replace("\\", "/").startswith(OCCULT_PREFIX)]
    if not docs or not query.strip():
        return "", []

    toks = _tokens(query, lang)
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

    if not parts and _is_en(lang):
        # Fallback: the English mirror may not cover this query; retry with
        # the original Chinese tree and its bigram tokenizer.
        return retrieve(query, top_k=top_k, max_chars=max_chars,
                        include_occult=include_occult, lang=None)
    return ("\n\n".join(parts), used) if parts else ("", [])


def search(query, include_occult=False, lang=None):
    """Alias of retrieve(): (context_string, relpaths) for a keyword query.

    Added so callers have a clearly named retrieval entry point; identical
    behaviour to retrieve() for every argument combination.
    """
    return retrieve(query, top_k=3, max_chars=9000,
                    include_occult=include_occult, lang=lang)


def list_docs(include_occult=False, lang=None):
    docs = _read_files(lang)
    if not include_occult:
        docs = [d for d in docs if not d["rel"].replace("\\", "/").startswith(OCCULT_PREFIX)]
    return [d["rel"] for d in docs]


_MEANINGS_CACHE = {}
_EN_STOP_PREFIXES = ("core:", "keyword", "number:", "symbolism:", "upright:", "reversed:",
                     "court perspective:", "keywords:")


def _append_note(card, bucket, text, lang=None):
    """Append a "- xx补充：" / "- Upright note:" line to an existing bucket."""
    text = text.strip()
    if not text:
        return
    cache = _MEANINGS_CACHE.setdefault(lang or "zh", {})

    cur = cache[card].get(bucket, "")
    cache[card][bucket] = (cur + " " + text).strip() if cur else text


def _load_meanings(lang=None):
    """Parse knowledge/meanings/*.md (or the English mirror) into
    {card_name: {'core','正位','逆位'}}.

    The English mirror uses English prefixes (Core:, Upright:, Reversed:,
    Symbolism:, Court perspective:) but the same internal bucket keys
    ('core', '正位', '逆位', ...) so get_card_meaning / get_card_entry can
    serve both languages without changing their return shape.
    """
    key = lang or "zh"
    cache = _MEANINGS_CACHE.setdefault(key, {})
    if cache:
        return cache
    root = _meanings_root(lang)
    if not os.path.isdir(root):
        return cache
    import re as _re
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if not fn.lower().endswith(".md"):
                continue
            # m4: parser state must NOT leak between files — a file ending
            # on a heading used to attach its continuation lines to the next
            # file's last card.
            current = None
            bucket = None
            path = os.path.join(dirpath, fn)
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if line.startswith("## "):
                        current = line[3:].strip()
                        bucket = None
                        if current:
                            cache.setdefault(current, {})
                        continue
                    if current is None:
                        continue
                    if line.startswith("- 核心："):
                        cache[current]["core"] = line[len("- 核心："):].strip()
                        bucket = None
                    elif line.startswith("核心："):
                        cache[current]["core"] = line[len("核心："):].strip()
                        bucket = None
                    elif line.startswith("- 正位："):
                        cache[current]["正位"] = line[len("- 正位："):].strip()
                        bucket = "正位"
                    elif line.startswith("- 逆位："):
                        cache[current]["逆位"] = line[len("- 逆位："):].strip()
                        bucket = "逆位"
                    elif line.startswith("- 正位补充："):
                        _append_note(current, "正位", line[len("- 正位补充："):], lang)
                        bucket = None
                    elif line.startswith("- 逆位补充："):
                        _append_note(current, "逆位", line[len("- 逆位补充："):], lang)
                        bucket = None
                    elif line.startswith("- 牌面象征："):
                        cache[current].setdefault("象征", []).append(
                            line[len("- 牌面象征："):].strip())
                        bucket = None
                    elif line.startswith("- 宫廷牌视角："):
                        cache[current].setdefault("视角", []).append(
                            line[len("- 宫廷牌视角："):].strip())
                        bucket = None
                    elif _is_en(lang):
                        # English mirror prefixes
                        low = line.lower()
                        if low.startswith("- core:"):
                            cache[current]["core"] = line[len("- core:"):].strip()
                            bucket = None
                        elif low.startswith("core:"):
                            cache[current]["core"] = line[len("core:"):].strip()
                            bucket = None
                        elif low.startswith("- upright note:"):
                            _append_note(current, "正位", line[len("- upright note:"):], lang)
                            bucket = None
                        elif low.startswith("- reversed note:"):
                            _append_note(current, "逆位", line[len("- reversed note:"):], lang)
                            bucket = None
                        elif low.startswith("- upright:"):
                            cache[current]["正位"] = line[len("- upright:"):].strip()
                            bucket = "正位"
                        elif low.startswith("- reversed:"):
                            cache[current]["逆位"] = line[len("- reversed:"):].strip()
                            bucket = "逆位"
                        elif low.startswith("- symbolism:"):
                            cache[current].setdefault("象征", []).append(
                                line[len("- symbolism:"):].strip())
                            bucket = None
                        elif low.startswith("- court perspective:"):
                            cache[current].setdefault("视角", []).append(
                                line[len("- court perspective:"):].strip())
                            bucket = None
                        elif bucket and line and not line.startswith(("#", "-")) and \
                                not low.startswith(_EN_STOP_PREFIXES):
                            cache[current][bucket] += " " + line
                    elif bucket and line and not line.startswith(("#", "-")):
                        # only plain continuation lines extend the bucket;
                        # stray headings/bullets must not be appended
                        cache[current][bucket] += " " + line
    return cache


def _meaning_entry(name, lang=None):
    """Look up a card entry in the requested language, falling back to zh."""
    m = _load_meanings(lang).get(name)
    if m and (m.get("core") or m.get("正位") or m.get("逆位")):
        return m
    if _is_en(lang):
        m = _load_meanings(None).get(name)
        if m and (m.get("core") or m.get("正位") or m.get("逆位")):
            return m
    return m or {}


def get_card_meaning(name, orientation="正位", lang=None):
    """Return the RWS meaning note for a card, or '' if not found.

    When lang="en", orientation may be 'Upright'/'Reversed' in addition to
    the original '正位'/'逆位'.
    """
    m = _meaning_entry(name, lang)
    if not m:
        return ""
    label = orientation
    if orientation in ("Upright", "upright", "正位"):
        orientation = "正位"
        if _is_en(lang):
            label = "Upright"
    elif orientation in ("Reversed", "reversed", "逆位"):
        orientation = "逆位"
        if _is_en(lang):
            label = "Reversed"
    core = m.get("core", "")
    body = m.get(orientation, "")
    parts = []
    if core:
        parts.append("核心：" + core if not _is_en(lang) else "Core: " + core)
    symbols = m.get("象征") or []
    if symbols:
        parts.append(("牌面：" if not _is_en(lang) else "Symbols: ") + "；".join(symbols))
    if body:
        parts.append((label + "：" if not _is_en(lang) else label + ": ") + body)
    view = m.get("视角") or []
    if view:
        parts.append(("宫廷牌：" if not _is_en(lang) else "Court: ") + "；".join(view))
    return " ".join(parts)


def get_card_entry(name, lang=None):
    """Structured meaning for one card, for the 牌义 page."""
    m = _meaning_entry(name, lang)
    return {
        "core": (m.get("core") or "").strip(),
        "up": (m.get("正位") or "").strip(),
        "rev": (m.get("逆位") or "").strip(),
        "symbols": [x.strip() for x in (m.get("象征") or []) if x and x.strip()][:4],
    }
