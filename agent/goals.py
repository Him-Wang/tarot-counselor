# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""goals.py — 「目标—状态—下一步」模型（stdlib only）。

这是把灵光式长程事务机制落到 Olivia 关怀域的核心：
一个目标有明确的状态 (active/paused/done/dropped) 与一个「下一步」。
下一步只有两种来源：来访者自己确认的 (user)，或 Olivia 提出的建议
(suggested, 需要来访者点头)。Olivia 永远不会自己把下一步标成完成，
也不会自己推进状态——这守住「不替你决定」的第一原则。

定时任务 (scheduler.tasks) 与盯事 (watchers) 可以通过 goal_links 关联到
目标；到点/命中时，scheduler 会把目标上下文带进主动汇报。

Everything is local: agent/data/goals.db. No network, no model calls.
"""

import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "goals.db")

STATUSES = ("active", "paused", "done", "dropped")
STATUS_LABEL = {"active": "进行中", "paused": "暂停", "done": "已完成", "dropped": "已放下"}
LINK_KINDS = ("task", "watcher")


def _now_s():
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
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            next_step TEXT DEFAULT '',
            next_source TEXT DEFAULT '',
            note TEXT DEFAULT '',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS goal_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER DEFAULT 1,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS goal_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            ref_id INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_steps_goal ON goal_steps(goal_id);
        CREATE INDEX IF NOT EXISTS idx_links_goal ON goal_links(goal_id);
        """)
        conn.commit()
    finally:
        conn.close()


# ---------- CRUD ----------

def add_goal(title, note="", status="active", next_step="", next_source="user"):
    init_db()
    title = str(title or "").strip()
    if not title:
        return None
    if status not in STATUSES:
        status = "active"
    next_source = "suggested" if next_source == "suggested" else "user"
    conn = _conn()
    try:
        now = _now_s()
        cur = conn.execute(
            "INSERT INTO goals(title,status,next_step,next_source,note,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (title[:200], status, str(next_step or "").strip()[:500], next_source,
             str(note or "").strip()[:2000], now, now))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_goal(gid, data):
    """状态与目标文本的显式更新——只由来访者/UI 调用，Olivia 不自动推进。"""
    init_db()
    conn = _conn()
    try:
        fields, vals = [], []
        if "title" in data and str(data["title"] or "").strip():
            fields.append("title=?"); vals.append(str(data["title"]).strip()[:200])
        if "note" in data:
            fields.append("note=?"); vals.append(str(data["note"] or "")[:2000])
        if "status" in data and data["status"] in STATUSES:
            fields.append("status=?"); vals.append(data["status"])
        if fields:
            fields.append("updated_at=?"); vals.append(_now_s())
            vals.append(gid)
            conn.execute("UPDATE goals SET " + ",".join(fields) + " WHERE id=?", vals)
            conn.commit()
        return True
    finally:
        conn.close()


def get_goal(gid):
    init_db()
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM goals WHERE id=?", (gid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_goals(status=None):
    init_db()
    conn = _conn()
    try:
        if status in STATUSES:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status=? ORDER BY id", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM goals ORDER BY id").fetchall()
        out = []
        for r in rows:
            g = dict(r)
            g["steps"] = [dict(s) for s in conn.execute(
                "SELECT id,text,created_at FROM goal_steps WHERE goal_id=? ORDER BY id DESC LIMIT 20",
                (g["id"],))]
            g["links"] = [dict(l) for l in conn.execute(
                "SELECT kind,ref_id FROM goal_links WHERE goal_id=? ORDER BY id", (g["id"],))]
            out.append(g)
        return out
    finally:
        conn.close()


def delete_goal(gid):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM goal_steps WHERE goal_id=?", (gid,))
        conn.execute("DELETE FROM goal_links WHERE goal_id=?", (gid,))
        conn.execute("DELETE FROM goals WHERE id=?", (gid,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- 下一步 ----------

def set_next_step(gid, text, source="user"):
    """记录下一步。source='suggested' 表示这是 Olivia 的建议，需来访者确认。"""
    init_db()
    text = str(text or "").strip()
    source = "suggested" if source == "suggested" else "user"
    conn = _conn()
    try:
        conn.execute(
            "UPDATE goals SET next_step=?, next_source=?, updated_at=? WHERE id=?",
            (text[:500], source, _now_s(), gid))
        conn.commit()
        return True
    finally:
        conn.close()


def confirm_step(gid):
    """来访者确认「这一步做到了」：把当前下一步写进已完成历史并清空。

    Olivia 自己绝不调用这个函数；它只由 UI / 来访者显式触发。
    """
    init_db()
    conn = _conn()
    try:
        row = conn.execute("SELECT next_step FROM goals WHERE id=?", (gid,)).fetchone()
        if not row or not (row["next_step"] or "").strip():
            return False
        conn.execute(
            "INSERT INTO goal_steps(goal_id,text,done,created_at) VALUES(?,?,1,?)",
            (gid, row["next_step"], _now_s()))
        conn.execute(
            "UPDATE goals SET next_step='', next_source='', updated_at=? WHERE id=?",
            (_now_s(), gid))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- 关联 task / watcher ----------

def link(gid, kind, ref_id):
    init_db()
    if kind not in LINK_KINDS:
        return False
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO goal_links(goal_id,kind,ref_id) VALUES(?,?,?)",
            (gid, kind, int(ref_id)))
        conn.commit()
        return True
    finally:
        conn.close()


def unlink(gid, kind, ref_id):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM goal_links WHERE goal_id=? AND kind=? AND ref_id=?",
                     (gid, kind, int(ref_id)))
        conn.commit()
        return True
    finally:
        conn.close()


def goals_for(kind, ref_id):
    """这个 task/watcher 关联到哪些目标（供 scheduler 汇报时标注）。"""
    init_db()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT g.* FROM goals g JOIN goal_links l ON l.goal_id=g.id "
            "WHERE l.kind=? AND l.ref_id=? ORDER BY g.id", (kind, int(ref_id))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def summary_for_prompt(limit=8):
    """给 scheduler / watcher 消息生成用的目标摘要，明确标注下一步来源。"""
    init_db()
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT title,status,next_step,next_source FROM goals "
            "WHERE status IN ('active','paused') ORDER BY id LIMIT ?", (limit,)).fetchall()
        if not rows:
            return ""
        lines = []
        for r in rows:
            step = (r["next_step"] or "").strip()
            if step:
                tag = "你自己定下的下一步" if r["next_source"] == "user" else "你还没点头的建议"
                lines.append("- %s（%s）：下一步「%s」(%s)" % (
                    r["title"], STATUS_LABEL.get(r["status"], r["status"]), step, tag))
            else:
                lines.append("- %s（%s）：还没定下一步" % (
                    r["title"], STATUS_LABEL.get(r["status"], r["status"])))
        return ("【你正在推进的目标（只作背景，不要替他决定或擅自推进）】\n"
                + "\n".join(lines))
    finally:
        conn.close()


def stats():
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT status, COUNT(*) n FROM goals GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
    finally:
        conn.close()
