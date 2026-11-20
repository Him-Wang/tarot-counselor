"""
memory.py — private long-term memory for the Olivia agent (stdlib only).

Design (adapted from mem0's extract/store/retrieve/inject flow and Letta's
core/recall/archival tiers), trimmed for a local, slow-model, stdlib-only app:

  core     -> profile table   : stable user facts, injected every turn
  recall   -> messages table  : raw conversation turns
  archival -> facts table     : rule-extracted durable facts (no LLM call)
  domain   -> draws table     : structured tarot draw history (Olivia-specific)

Extraction is RULE-BASED (regex), ~0 ms, so it never adds latency to a local
9B model. Sensitive/crisis messages are flagged and never promoted to facts.
All data lives in agent/data/memory.db (gitignored, local & private).
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "memory.db")

# Core RWS card names (long/specific first). Used to spot draws in replies.
_MAJORS = [
    "命运之轮", "倒吊人", "女祭司", "魔术师", "愚者", "恋人", "战车", "力量",
    "隐者", "正义", "死神", "节制", "恶魔", "星星", "月亮", "太阳", "审判",
    "世界", "教皇", "皇后", "皇帝", "塔",
]
_SUITS = ["权杖", "圣杯", "宝剑", "星币"]
_RANKS = ["十", "九", "八", "七", "六", "五", "四", "三", "二", "一",
          "侍从", "骑士", "王后", "国王", "王牌", "Ace", "ace"]
CARD_NAMES = _MAJORS + [s + r for s in _SUITS for r in _RANKS]

STOP = set("的 了 和 是 在 我 你 他 她 它 们 这 那 有 就 不 也 都 而 及 与 或 一个 什么 怎么 一些 可以 需要 是否 请 帮 我想 觉得 因为 所以 但是 如果 已经 还是 现在 自己 一下 吧 呢 吗 啊 呀 哦 嗯".split())

CRISIS_RE = re.compile(r"自杀|自残|不想活|活不下去|结束生命|伤害自己|轻生|割腕|跳楼|寻死")


# ---------- low level ----------

def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS profile (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            norm TEXT NOT NULL,
            text TEXT NOT NULL,
            tags TEXT DEFAULT '',
            pinned INTEGER DEFAULT 0,
            sensitive INTEGER DEFAULT 0,
            last_seen TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_facts_norm ON facts(kind, norm);
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            sensitive INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spread TEXT,
            cards TEXT,
            question TEXT,
            created_at TEXT
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _norm(s):
    return re.sub(r"[\s，。！？,.!?、；;：:]", "", s or "")


def _tokens(query):
    q = (query or "").strip().lower()
    toks = set()
    for w in re.findall(r"[a-z0-9]{2,}", q):
        if w not in STOP:
            toks.add(w)
    han = re.findall(r"[\u4e00-\u9fff]", q)
    for i in range(len(han) - 1):
        toks.add(han[i] + han[i + 1])
    for c in han:
        if c not in STOP:
            toks.add(c)
    return toks


def _recency_bonus(created):
    try:
        dt = datetime.strptime(created or "", "%Y-%m-%d %H:%M:%S")
    except Exception:
        return 0
    age = datetime.now() - dt
    if age <= timedelta(days=7):
        return 3
    if age <= timedelta(days=30):
        return 1
    return 0


# ---------- rule-based extraction ----------

def _extract(text):
    """Return (facts, profile_updates, is_sensitive).

    facts: list of (kind, fact_text, pinned)
    """
    t = (text or "").strip()
    facts = []
    profile = {}

    # stable identity / how to address the user
    m = re.search(r"(?:我叫|我的名字是|叫我|你可以叫我|就叫我)\s*[:：]?\s*([^\s，。！？,.!?]{1,12})", t)
    if m:
        profile["称呼"] = m.group(1).strip()

    # explicit "remember this" -> pinned fact
    for m in re.finditer(r"(?:请?记住|别忘了|记得)\s*[:：]?\s*([^，。！？\n]{2,60})", t):
        val = m.group(1).strip()
        if val:
            facts.append(("fact", val, 1))

    # preferences / emotional stances
    pref_re = re.compile(
        r"我(?:很|比较|特别|最|还)?(喜欢|讨厌|不喜欢|在意|想要|希望|偏好|害怕|担心|纠结)([^，。！？\n]{1,40})")
    for m in pref_re.finditer(t):
        val = (m.group(1) + m.group(2)).strip()
        if val:
            facts.append(("pref", val, 0))

    # boundaries / negative instructions (directives only, not emotional
    # states: "我担心X" is already captured as a pref, not a boundary).
    for m in re.finditer(r"(?:不要|别再|请勿)(?:再)?([^，。！？\n]{1,40})", t):
        val = m.group(1).strip()
        if len(val) >= 2:
            facts.append(("boundary", val, 0))

    sensitive = bool(CRISIS_RE.search(t))
    return facts, profile, sensitive


def _store_draw(conn, draw, question, now):
    """Persist a draw from the STRUCTURED draw_cards tool result.

    M2: this used to parse card names out of the assistant's free-text reply,
    which created phantom records (e.g. "塔" matching inside "塔罗牌"). Only
    cards actually drawn by the draw_cards tool are real draws.
    """
    if not isinstance(draw, dict) or not draw.get("ok"):
        return
    items = draw.get("cards") or []
    if not items:
        return
    spread = draw.get("spread") or "未注明"
    found = []
    for c in items[:12]:
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        orientation = str(c.get("orientation", ""))
        found.append({
            "name": name,
            "reversed": ("逆" in orientation) or bool(c.get("reversed")),
        })
    if not found:
        return
    conn.execute(
        "INSERT INTO draws(spread, cards, question, created_at) VALUES(?,?,?,?)",
        (spread, json.dumps(found, ensure_ascii=False), (question or "")[:200], now),
    )


# ---------- public API ----------

def add_fact(kind, text, pinned=False):
    """Insert or refresh a fact (used by the save_memory tool). Returns True."""
    init_db()
    n = _norm(text)
    if not n or CRISIS_RE.search(text or ""):
        return False
    conn = _conn()
    now = _now()
    try:
        row = conn.execute(
            "SELECT id FROM facts WHERE kind=? AND norm=?", (kind, n)).fetchone()
        if row:
            conn.execute(
                "UPDATE facts SET last_seen=?, pinned=MAX(pinned,?) WHERE id=?",
                (now, 1 if pinned else 0, row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO facts(kind,norm,text,tags,pinned,sensitive,last_seen,created_at) "
                "VALUES(?,?,?,?,?,0,?,?)",
                (kind, n, text, "", 1 if pinned else 0, now, now),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def remember(user_msg, reply, draw=None):
    """Persist one turn: raw messages, extracted facts, profile, draw record.

    ``draw`` is the structured result of the draw_cards tool (or None).
    Draw history is only written from this structured result, never by
    scanning the assistant's free-text reply for card names.
    """
    init_db()
    conn = _conn()
    now = _now()
    try:
        facts, profile, sensitive = _extract(user_msg)
        conn.execute(
            "INSERT INTO messages(role,content,sensitive,created_at) VALUES(?,?,?,?)",
            ("user", user_msg or "", 1 if sensitive else 0, now),
        )
        conn.execute(
            "INSERT INTO messages(role,content,sensitive,created_at) VALUES(?,?,?,?)",
            ("assistant", reply or "", 0, now),
        )
        # Crisis content: store raw for continuity, but never auto-promote to
        # durable facts or draw memory. See knowledge/ethics/危机与转介.md.
        if sensitive:
            conn.commit()
            return
        for k, v in profile.items():
            conn.execute(
                "INSERT INTO profile(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (k, v, now),
            )
        for kind, text, pinned in facts:
            n = _norm(text)
            if not n:
                continue
            row = conn.execute(
                "SELECT id FROM facts WHERE kind=? AND norm=?", (kind, n)).fetchone()
            if row:
                conn.execute(
                    "UPDATE facts SET last_seen=?, pinned=MAX(pinned,?) WHERE id=?",
                    (now, pinned, row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO facts(kind,norm,text,tags,pinned,sensitive,last_seen,created_at) "
                    "VALUES(?,?,?,?,?,0,?,?)",
                    (kind, n, text, "", pinned, now, now),
                )
        _store_draw(conn, draw, user_msg, now)
        conn.commit()
    finally:
        conn.close()


def context(query, max_chars=1600):
    """Build the memory block to append to the system prompt ('' if empty)."""
    init_db()
    conn = _conn()
    try:
        parts = []

        prof = conn.execute("SELECT key,value FROM profile ORDER BY key").fetchall()
        if prof:
            s = "\n".join("%s：%s" % (r["key"], r["value"]) for r in prof)
            parts.append("【关于来访者的稳定信息】\n" + s[:600])

        qtoks = _tokens(query)
        rows = conn.execute(
            "SELECT id,kind,text,pinned,created_at FROM facts WHERE sensitive=0").fetchall()
        scored = []
        for r in rows:
            text = (r["text"] or "").lower()
            sc = 0
            for t in qtoks:
                c = text.count(t)
                if c:
                    sc += c * (2 if len(t) >= 2 else 1)
            sc += (r["pinned"] or 0) * 3
            sc += _recency_bonus(r["created_at"])
            if sc > 0:
                scored.append((sc, r))
        scored.sort(key=lambda x: -x[0])
        flines = ["- (%s) %s" % (r["kind"], r["text"]) for _sc, r in scored[:10]]
        if flines:
            parts.append("【记住的线索（仅在相关时自然提及）】\n" + "\n".join(flines)[:700])

        draws = conn.execute(
            "SELECT spread,cards,question,created_at FROM draws ORDER BY id DESC LIMIT 3").fetchall()
        if draws:
            dlines = []
            for r in draws:
                try:
                    cl = json.loads(r["cards"] or "[]")
                except Exception:
                    cl = []
                names = "、".join(
                    c.get("name", "") + ("逆位" if c.get("reversed") else "正位") for c in cl)
                dlines.append("- %s %s：%s（问：%s）" % (
                    (r["created_at"] or "")[:10], r["spread"], names, (r["question"] or "")[:40]))
            parts.append("【近期抽牌记录（可自然回访，不要当成新的牌面）】\n" + "\n".join(dlines)[:400])

        if not parts:
            return ""
        block = "\n\n".join(parts)
        if len(block) > max_chars:
            block = block[:max_chars]
        return ("以下是你此前记住的关于这位来访者的背景，仅在相关时自然、克制地使用；"
                "不要生硬复述，更不要把记忆当作本次牌面信息或专业判断依据。\n\n" + block)
    finally:
        conn.close()


def list_facts(limit=200):
    init_db()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id,kind,text,pinned,sensitive,last_seen,created_at FROM facts "
            "ORDER BY pinned DESC, id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def list_draws(limit=50):
    init_db()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id,spread,cards,question,created_at FROM draws ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["cards"] = json.loads(d.get("cards") or "[]")
            except Exception:
                d["cards"] = []
            out.append(d)
        return out
    finally:
        conn.close()


def list_profile():
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT key,value,updated_at FROM profile ORDER BY key").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_fact(fact_id):
    init_db()
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM facts WHERE id=?", (fact_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def delete_draw(draw_id):
    init_db()
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM draws WHERE id=?", (draw_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def pin_fact(fact_id, pinned):
    init_db()
    conn = _conn()
    try:
        cur = conn.execute("UPDATE facts SET pinned=? WHERE id=?", (1 if pinned else 0, fact_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_profile(key, value):
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO profile(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, _now()))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_profile(key):
    init_db()
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM profile WHERE key=?", (key,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def forget(text):
    """Delete durable facts whose text mentions the given phrase."""
    n = _norm(text)
    if not n:
        return 0
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT id,norm FROM facts").fetchall()
        ids = [r["id"] for r in rows if n in (r["norm"] or "")]
        for i in ids:
            conn.execute("DELETE FROM facts WHERE id=?", (i,))
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def forget_recent(n=3):
    """Undo the last n extracted facts (used by 'forget what I just said').

    M3: clamp n to a non-negative integer — SQLite treats LIMIT -1 as
    "unlimited", so a negative n used to delete every stored fact.
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3
    n = max(0, n)
    if not n:
        return 0
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT id FROM facts ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        ids = [r["id"] for r in rows]
        for i in ids:
            conn.execute("DELETE FROM facts WHERE id=?", (i,))
        conn.commit()
        return len(ids)
    finally:
        conn.close()


def clear():
    """Wipe all memory (profile, facts, messages, draws)."""
    init_db()
    conn = _conn()
    try:
        for table in ("profile", "facts", "messages", "draws"):
            conn.execute("DELETE FROM " + table)
        conn.commit()
        return True
    finally:
        conn.close()


def stats():
    init_db()
    conn = _conn()
    try:
        def c(t):
            return conn.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
        return {"profile": c("profile"), "facts": c("facts"),
                "messages": c("messages"), "draws": c("draws")}
    finally:
        conn.close()
