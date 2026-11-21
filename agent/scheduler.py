"""
scheduler.py — L3 proactive layer for the Olivia agent (stdlib only).

Implements four primitives from Anthropic's "building always-on agents":
  timers      -> tasks table (one-shot / daily / weekly / interval)
  inbox       -> events table (manual or future external triggers)
  outbox      -> messages table (proactive messages Olivia sends)
  permissions -> quiet hours + master switch + per-task enabled flag

A background thread wakes every ~30s, finds due tasks, asks the model to
generate a short proactive message (grounded in memory + a user-supplied
intent), stores it in the outbox, and optionally fires a Windows toast.
Everything is local and private; nothing is sent anywhere.
"""

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime, timedelta

import llm
import memory
import watchers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "scheduler.db")
TOAST_PS1 = os.path.join(BASE_DIR, "toast.ps1")

TICK_SECONDS = 30
_ADJECTIVES = ["", ""]  # placeholder kept trivial; messages come from the model


def _now():
    return datetime.now()


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
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            intent TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'daily',   -- once|daily|weekly|interval
            cron_time TEXT DEFAULT '09:00',      -- daily/once: HH:MM
            weekday INTEGER DEFAULT 1,           -- weekly: 0=Mon..6=Sun
            interval_min INTEGER DEFAULT 120,    -- interval: every N minutes
            run_at TEXT,                         -- once: 'YYYY-MM-DD HH:MM'
            enabled INTEGER DEFAULT 1,
            toast INTEGER DEFAULT 1,
            last_run TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            payload TEXT DEFAULT '',
            processed INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            role TEXT DEFAULT 'assistant',
            content TEXT NOT NULL,
            read INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        defaults = {"master": "0", "quiet_start": "22:00", "quiet_end": "08:00"}
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        conn.commit()
    finally:
        conn.close()


# ---------- settings ----------

def get_settings():
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT key,value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


def set_settings(values):
    init_db()
    conn = _conn()
    try:
        for k, v in values.items():
            if k not in ("master", "quiet_start", "quiet_end"):
                continue
            val = "1" if v is True else ("0" if v is False else str(v))
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, val))
        conn.commit()
        return True
    finally:
        conn.close()


def _in_quiet_hours(now=None):
    now = now or _now()
    s = get_settings()
    try:
        qs, qe = s.get("quiet_start", "22:00"), s.get("quiet_end", "08:00")
        sh, sm = map(int, qs.split(":")); eh, em = map(int, qe.split(":"))
        cur = now.hour * 60 + now.minute
        start, end = sh * 60 + sm, eh * 60 + em
        if start <= end:
            return start <= cur < end
        return cur >= start or cur < end
    except Exception:
        return False


# ---------- tasks CRUD ----------

def list_tasks():
    init_db()
    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_task(data):
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO tasks(name,intent,kind,cron_time,weekday,interval_min,run_at,"
            "enabled,toast,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(data.get("name", "主动关怀")).strip() or "主动关怀",
             str(data.get("intent", "关心一下我最近怎么样")).strip(),
             str(data.get("kind", "daily")),
             str(data.get("cron_time", "09:00")),
             int(data.get("weekday", 1) or 1),
             int(data.get("interval_min", 120) or 120),
             str(data.get("run_at", "") or "") or None,
             1 if data.get("enabled", True) else 0,
             1 if data.get("toast", True) else 0,
             _now_s()),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def update_task(task_id, data):
    init_db()
    conn = _conn()
    try:
        fields, vals = [], []
        allowed = ("name", "intent", "kind", "cron_time", "weekday", "interval_min",
                   "run_at", "enabled", "toast")
        for k in allowed:
            if k in data:
                if k in ("enabled", "toast"):
                    val = 1 if data[k] else 0
                elif k in ("weekday", "interval_min"):
                    val = int(data[k] or 0)
                else:
                    val = str(data[k])
                fields.append("%s=?" % k); vals.append(val)
        if fields:
            vals.append(task_id)
            conn.execute("UPDATE tasks SET " + ",".join(fields) + " WHERE id=?", vals)
            conn.commit()
        return True
    finally:
        conn.close()


def delete_task(task_id):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- inbox / outbox ----------

def add_event(kind, payload=""):
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO events(kind,payload,created_at) VALUES(?,?,?)",
            (kind, str(payload), _now_s()))
        conn.commit()
        return True
    finally:
        conn.close()


def list_outbox(limit=50, unread_only=False):
    init_db()
    conn = _conn()
    try:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM messages WHERE read=0 ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_read(msg_id=None, all_read=False):
    init_db()
    conn = _conn()
    try:
        if all_read:
            conn.execute("UPDATE messages SET read=1")
        elif msg_id is not None:
            conn.execute("UPDATE messages SET read=1 WHERE id=?", (msg_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_message(msg_id):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM messages WHERE id=?", (msg_id,))
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- due-task evaluation ----------

def _is_due(task, now):
    kind = task["kind"]
    last = task["last_run"]
    last_dt = None
    if last:
        try:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    if kind == "once":
        if not task["run_at"]:
            return False
        try:
            target = datetime.strptime(task["run_at"], "%Y-%m-%d %H:%M")
        except Exception:
            return False
        # M4: a "once" task must fire exactly once, ever — not once per day.
        return now >= target and last_dt is None
    if kind in ("daily", "card"):
        # card = 每日一牌：和 daily 一样按 cron_time 每天一次，只是内容由本地抽牌生成
        hh, mm = (task["cron_time"] or "09:00").split(":")
        target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if now < target:
            return False
        # m1: compare against the scheduled time, not just the calendar day,
        # so a manual run at 08:00 doesn't suppress the 09:00 fire.
        return last_dt is None or last_dt < target
    if kind == "weekly":
        if now.weekday() != int(task["weekday"]):
            return False
        hh, mm = (task["cron_time"] or "09:00").split(":")
        target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if now < target:
            return False
        return last_dt is None or last_dt < target
    if kind == "interval":
        mins = max(1, int(task["interval_min"] or 120))
        if last_dt is None:
            return True
        return now - last_dt >= timedelta(minutes=mins)
    return False


def _fire_toast(title, body):
    if not os.path.exists(TOAST_PS1):
        return False
    try:
        ps = os.environ.get("PSModulePath", "")
        exe = "powershell.exe"
        for cand in (r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                     r"C:\Windows\System32\WindowsPowerShell\v1.0\pwsh.exe"):
            if os.path.exists(cand):
                exe = cand; break
        proc = subprocess.run(
            [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", TOAST_PS1,
             "-Title", title, "-Body", body[:200]],
            capture_output=True, text=True, timeout=25,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return "OK" in (proc.stdout or "")
    except Exception:
        return False


def daily_card_message():
    """每日一牌：本地客观抽一张，写成一条可读的晨间消息。

    不调用模型，所以没有 key / 模型不可用时也照常送达。
    """
    try:
        import tools as tools_mod
        res = tools_mod.draw_cards(spread="单张")
        c = (res.get("cards") or [{}])[0]
        name = c.get("name", "")
        ori = c.get("orientation", "")
        meaning = re.sub(r"\s+", " ", str(c.get("meaning") or "")).strip()
        if len(meaning) > 200:
            meaning = meaning[:200] + "…"
        out = "今天这张牌：%s（%s）。" % (name, ori)
        if meaning:
            out += meaning
        out += "不用急着解它，先看看今天有没有哪一刻让你想起这张牌。"
        return out
    except Exception as e:
        return "今天的牌没能抽出来（%s），晚一点再试试。" % e


def run_due_tasks(cfg_loader):
    """Check all enabled tasks, generate + deliver proactive messages.

    cfg_loader: callable returning the current config dict (avoids circular
    import with server.py).
    """
    settings = get_settings()
    if settings.get("master", "0") not in ("1", "True", "true"):
        return []
    if _in_quiet_hours():
        return []

    conn = _conn()
    try:
        rows = conn.execute("SELECT * FROM tasks WHERE enabled=1").fetchall()
        tasks = [dict(r) for r in rows]
    finally:
        conn.close()

    now = _now()
    fired = []
    cfg = None
    for task in tasks:
        if not _is_due(task, now):
            continue
        try:
            if task["kind"] == "card":
                # 每日一牌：纯本地抽牌，不需要模型也不需要 key
                content = daily_card_message()
            else:
                if cfg is None:
                    cfg = cfg_loader()
                mem_ctx = memory.context(task["intent"])
                system = load_persona_short()
                system += "\n\n你是主动关怀助手。根据下面的意图，写一条简短、温暖、自然的中文消息（1-3 句），像朋友发来的关心，不要机械、不要问太多问题、不要使用表情符号。只输出消息正文。"
                if mem_ctx:
                    system += "\n\n" + mem_ctx
                user = "主动关怀意图：" + task["intent"]
                content = (llm.complete(
                    [{"role": "system", "content": system},
                     {"role": "user", "content": user}], cfg) or "").strip()
                if not content:
                    content = "今天过得怎么样？我在，想说的时候随时找我。"
        except Exception as e:
            content = "（主动消息生成失败：%s）" % e
        content = content[:600]

        conn = _conn()
        try:
            conn.execute("UPDATE tasks SET last_run=? WHERE id=?", (_now_s(), task["id"]))
            conn.execute(
                "INSERT INTO messages(task_id,role,content,read,created_at) "
                "VALUES(?,?,?,0,?)", (task["id"], "assistant", content, _now_s()))
            conn.commit()
        finally:
            conn.close()
        if task["toast"]:
            _fire_toast("Olivia · " + task["name"], content)
        fired.append({"task_id": task["id"], "name": task["name"], "content": content})
    return fired


def run_watcher_checks(force=False):
    """Evaluate condition watchers: fetch sources, test rules, deliver on hit.

    Pure-Python by design (no model call), so it works even when the local
    model is unavailable.  A watcher firing inserts a message into the SAME
    outbox as timed tasks and optionally fires the same desktop toast.
    `force=True` ignores interval/cooldown (used by the UI "check now" button).
    """
    settings = get_settings()
    if settings.get("master", "0") not in ("1", "True", "true"):
        return []
    if _in_quiet_hours() and not force:
        return []

    now = _now()
    fired = []
    rows = watchers.list_watchers()
    for row in rows:
        w = dict(row)
        if not w.get("enabled"):
            continue
        if not force and not watchers.is_due(w, now):
            continue
        if not force and not watchers._cooldown_ok(w, now):
            continue

        summary = ""
        hit = False
        fp = ""
        try:
            value_text, numeric, items, _ = watchers.fetch(w)
            hit, summary, fp = watchers.evaluate(w, value_text, numeric, items)
        except Exception as e:
            summary = "抓取/判断失败：%s" % e
            hit = False
            fp = str(w.get("last_value", "") or "")

        # Persist the observation in the watchers' OWN db (not scheduler.db).
        wconn = watchers._conn()
        try:
            wconn.execute(
                "UPDATE watchers SET last_check=?, last_value=? WHERE id=?",
                (_now_s(), fp[:500], w["id"]))
            wconn.commit()
        finally:
            wconn.close()

        if not hit:
            if force:
                watchers.log_event(w, False, summary, "")
            continue

        message = watchers.build_message(w, summary)
        # Message goes into scheduler's outbox; last_fire into watchers' db.
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO messages(task_id,role,content,read,created_at) "
                "VALUES(?,?,?,0,?)", (None, "assistant", message, _now_s()))
            conn.commit()
        finally:
            conn.close()
        wconn = watchers._conn()
        try:
            wconn.execute("UPDATE watchers SET last_fire=? WHERE id=?", (_now_s(), w["id"]))
            wconn.commit()
        finally:
            wconn.close()
        watchers.log_event(w, True, summary, message)
        if w.get("toast"):
            _fire_toast("Olivia · " + w.get("name", "关注"), message)
        fired.append({"watcher_id": w["id"], "name": w.get("name"),
                      "summary": summary, "content": message})
    return fired


def load_persona_short():
    path = os.path.join(os.path.dirname(BASE_DIR), "prompts", "persona.zh.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        return text[:1500]
    except Exception:
        return "你是一名塔罗咨询师 Olivia（奥莉薇娅），温暖而克制。"


# ---------- background thread ----------

_thread = None
_stop = threading.Event()


def start(cfg_loader):
    global _thread
    init_db()
    if _thread and _thread.is_alive():
        return _thread
    _stop.clear()

    def loop():
        while not _stop.wait(TICK_SECONDS):
            try:
                run_due_tasks(cfg_loader)
            except Exception:
                pass
            try:
                run_watcher_checks()
            except Exception:
                pass
    _thread = threading.Thread(target=loop, name="olivia-scheduler", daemon=True)
    _thread.start()
    return _thread


def stop():
    _stop.set()


def status():
    s = get_settings()
    return {
        "master": s.get("master", "0") == "1",
        "quiet_start": s.get("quiet_start", "22:00"),
        "quiet_end": s.get("quiet_end", "08:00"),
        "in_quiet_hours": _in_quiet_hours(),
        "task_count": len(list_tasks()),
        "watcher_count": len([w for w in watchers.list_watchers() if w.get("enabled")]),
        "unread": len(list_outbox(unread_only=True)),
        "thread_alive": bool(_thread and _thread.is_alive()),
    }
