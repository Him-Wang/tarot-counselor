"""
plugin_kb.py — personal knowledge base (archival extension of memory), stdlib only.

Relationship to memory.py:
  memory.py  = automatic, rule-extracted short/long-term clues about the user
               (profile / facts / messages / draws). Fast, zero LLM call.
  plugin_kb  = user-curated, structured NOTES + an archive of what mattered.
               It is the "archival tier" — deliberate, searchable, exportable.

Notes are stored in SQLite (agent/data/kb.db, gitignored). Search uses
character-bigram scoring (same trick as knowledge.py / memory.py), so no
vector DB or extra dependency is needed.

Public API:
  add_note(title, content, tags)      -> id
  update_note(id, **fields)           -> bool
  delete_note(id)                     -> bool
  get_note(id)                        -> dict | None
  list_notes(limit, tag)              -> [dict]
  search_notes(query, top_k, max_chars) -> (context_str, [ids])
  archive_memory(limit)               -> int  (pull recent facts into notes)
  stats()                             -> dict
  export_markdown()                   -> str
"""

import json
import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "kb.db")


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
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            tags TEXT DEFAULT '',
            pinned INTEGER DEFAULT 0,
            source TEXT DEFAULT 'manual',   -- manual | memory | chat | vision
            created_at TEXT,
            updated_at TEXT
        );
        """)
        conn.commit()
    finally:
        conn.close()


def _norm_tags(tags):
    if isinstance(tags, (list, tuple)):
        return ",".join(str(t).strip() for t in tags if str(t).strip())
    return str(tags or "").strip()


# ---------- CRUD ----------

def add_note(title, content, tags="", source="manual", pinned=False):
    init_db()
    title = (title or "无标题").strip()
    content = (content or "").strip()
    if not content:
        return None
    conn = _conn()
    try:
        now = _now()
        conn.execute(
            "INSERT INTO notes(title,content,tags,pinned,source,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (title, content, _norm_tags(tags), 1 if pinned else 0,
             source, now, now))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def update_note(note_id, title=None, content=None, tags=None, pinned=None):
    init_db()
    fields, vals = [], []
    if title is not None:
        fields.append("title=?"); vals.append(str(title).strip() or "无标题")
    if content is not None:
        fields.append("content=?"); vals.append(str(content).strip())
    if tags is not None:
        fields.append("tags=?"); vals.append(_norm_tags(tags))
    if pinned is not None:
        fields.append("pinned=?"); vals.append(1 if pinned else 0)
    if not fields:
        return False
    fields.append("updated_at=?"); vals.append(_now())
    vals.append(note_id)
    conn = _conn()
    try:
        conn.execute("UPDATE notes SET " + ",".join(fields) + " WHERE id=?", vals)
        conn.commit()
        return True
    finally:
        conn.close()


def delete_note(note_id):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_note(note_id):
    init_db()
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_notes(limit=100, tag=None):
    init_db()
    conn = _conn()
    try:
        if tag:
            rows = conn.execute(
                "SELECT * FROM notes WHERE tags LIKE ? ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                ("%" + str(tag) + "%", limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def pin_note(note_id, pinned=True):
    return update_note(note_id, pinned=pinned)


# ---------- retrieval ----------

def search_notes(query, top_k=3, max_chars=4000):
    """Bigram-scored search. Returns (context_str, [matched note ids])."""
    init_db()
    q = (query or "").strip().lower()
    if not q:
        return "", []
    toks = set()
    import re
    for w in re.findall(r"[a-z0-9]{2,}", q):
        toks.add(w)
    han = re.findall(r"[\u4e00-\u9fff]", q)
    for i in range(len(han) - 1):
        toks.add(han[i] + han[i + 1])
    for c in han:
        toks.add(c)

    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM notes").fetchall()
    finally:
        conn.close()

    scored = []
    for r in rows:
        text = ((r["title"] or "") + "\n" + (r["content"] or "") + "\n" + (r["tags"] or "")).lower()
        score = 0
        for t in toks:
            c = text.count(t)
            if c:
                score += c * (2 if len(t) >= 2 else 1)
        title = (r["title"] or "").lower()
        # m6: an empty title must not match every query ("" is in every q)
        if title and (title in q or q in title):
            score += 5
        score += (r["pinned"] or 0) * 2
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])

    parts, ids, total = [], [], 0
    for _sc, r in scored:
        if len(ids) >= top_k or total >= max_chars:
            break
        chunk = "【笔记：%s】\n%s" % (r["title"], r["content"])
        if total + len(chunk) > max_chars:
            chunk = chunk[:max(0, max_chars - total)]
        if not chunk:
            continue
        parts.append(chunk)
        ids.append(r["id"])
        total += len(chunk)
    return ("\n\n".join(parts), ids) if parts else ("", [])


# ---------- archive from memory ----------

def archive_memory(limit=50):
    """Pull recent durable facts from memory.py into curated notes.

    Each fact becomes a note with source='memory'. Already-archived facts are
    skipped (matched by exact title+content), so this is idempotent.
    """
    try:
        import memory
        facts = memory.list_facts(limit=limit)
    except Exception:
        return 0
    init_db()
    conn = _conn()
    try:
        added = 0
        existing = set(
            (r["title"], r["content"]) for r in
            conn.execute("SELECT title,content FROM notes WHERE source='memory'").fetchall())
        kind_label = {"fact": "事实", "pref": "偏好", "boundary": "边界"}
        for f in facts:
            text = f["text"]
            title = "[%s] %s" % (kind_label.get(f["kind"], f["kind"]),
                                 text[:20])
            if (title, text) in existing:
                continue
            now = _now()
            conn.execute(
                "INSERT INTO notes(title,content,tags,pinned,source,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (title, text, f.get("kind", ""), 1 if f.get("pinned") else 0,
                 "memory", now, now))
            added += 1
        conn.commit()
        return added
    finally:
        conn.close()


def archive_draws(limit=30):
    """Pull recent tarot draws into notes (source='memory'), idempotent."""
    try:
        import memory
        draws = memory.list_draws(limit=limit)
    except Exception:
        return 0
    init_db()
    conn = _conn()
    try:
        added = 0
        existing = set(r["content"] for r in
                       conn.execute("SELECT content FROM notes WHERE source='memory'").fetchall())
        for d in draws:
            cards = "、".join(
                c.get("name", "") + ("逆位" if c.get("reversed") else "正位")
                for c in (d.get("cards") or []))
            content = "[%s] %s　问：%s　（%s）" % (
                d.get("spread", ""), cards, d.get("question", "") or "—",
                d.get("created_at", ""))
            if content in existing:
                continue
            now = _now()
            conn.execute(
                "INSERT INTO notes(title,content,tags,pinned,source,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                ("抽牌归档", content, "抽牌", 0, "memory", now, now))
            added += 1
        conn.commit()
        return added
    finally:
        conn.close()


# ---------- misc ----------

def stats():
    init_db()
    conn = _conn()
    try:
        total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
        by_source = {}
        for r in conn.execute("SELECT source, COUNT(*) c FROM notes GROUP BY source").fetchall():
            by_source[r["source"]] = r["c"]
        return {"total": total, "by_source": by_source}
    finally:
        conn.close()


def export_markdown():
    """Export the whole KB as a single Markdown string (for backup/portability)."""
    notes = list_notes(limit=100000)
    lines = ["# 个人知识库导出", ""]
    for n in notes:
        tags = "[%s]" % n["tags"] if n["tags"] else ""
        lines += ["## %s %s" % (n["title"], tags),
                  "*来源：%s　创建：%s*" % (n["source"], n["created_at"]),
                  "", n["content"], ""]
    return "\n".join(lines)


def clear():
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM notes")
        conn.commit()
        return True
    finally:
        conn.close()
