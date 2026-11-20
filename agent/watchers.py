"""
watchers.py — condition-triggered "watch one thing" layer for Olivia (stdlib only).

A watcher periodically fetches an external data source (web page / RSS / JSON API /
weather) and evaluates a simple rule.  It only produces a signal when the rule is
met — this is the "盯住一件事，条件满足才提醒" primitive that turns the L3 layer
from a plain cron greeter into a real condition-driven agent.

Design constraints (carried over from the rest of the project):
  * Python stdlib only (urllib / sqlite3 / re / xml.etree) — no requests, no feed lib.
  * NO local-model dependency: fetch + evaluate are pure Python.  Message wording
    is a template; the scheduler MAY optionally ask the model to embellish it,
    but a failure there never blocks the signal.
  * Everything local: watchers and evaluation history live in agent/data/watchers.db.

Source types
  http     : GET a URL, treat response body as text
  rss      : GET an RSS/Atom feed, extract latest item titles + links
  json     : GET a JSON endpoint, read a dotted field path (e.g. current.temperature_2m)
  weather  : Open-Meteo current weather for a city (no API key)

Rules
  contains / not_contains / regex : text matching
  gt / gte / lt / lte            : numeric comparison against `threshold`
  changed                         : fingerprint differs from last observation
  new_item                        : RSS latest item differs from last observation
  always                          : every due check fires (still cooldown-limited)
"""

import json
import os
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "watchers.db")

# Small built-in coordinate table for the weather source; anything else falls
# back to Beijing. Users can always pick `json` with their own URL instead.
CITY_COORDS = {
    "北京": (39.9042, 116.4074), "上海": (31.2304, 121.4737),
    "广州": (23.1291, 113.2644), "深圳": (22.5431, 114.0579),
    "杭州": (30.2741, 120.1551), "成都": (30.5728, 104.0668),
    "南京": (32.0603, 118.7969), "武汉": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398), "重庆": (29.5630, 106.5516),
    "苏州": (31.2989, 120.5853), "天津": (39.3434, 117.3616),
    "长沙": (28.2282, 112.9388), "厦门": (24.4798, 118.0894),
    "青岛": (36.0671, 120.3826), "香港": (22.3193, 114.1694),
    "台北": (25.0330, 121.5654), "东京": (35.6762, 139.6503),
    "纽约": (40.7128, -74.0060), "伦敦": (51.5074, -0.1278),
}

NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
DEFAULT_UA = "Olivia-Watcher/1.0 (local personal agent; stdlib urllib)"


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
        CREATE TABLE IF NOT EXISTS watchers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            intent TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'http',
            url TEXT DEFAULT '',
            city TEXT DEFAULT '',
            field_path TEXT DEFAULT '',
            rule TEXT NOT NULL DEFAULT 'contains',
            keyword TEXT DEFAULT '',
            threshold REAL DEFAULT 0,
            interval_min INTEGER DEFAULT 60,
            cooldown_min INTEGER DEFAULT 60,
            enabled INTEGER DEFAULT 1,
            toast INTEGER DEFAULT 1,
            last_check TEXT,
            last_value TEXT DEFAULT '',
            last_fire TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS watcher_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watcher_id INTEGER,
            name TEXT,
            fired INTEGER DEFAULT 0,
            summary TEXT DEFAULT '',
            message TEXT DEFAULT '',
            created_at TEXT
        );
        """)
        conn.commit()
    finally:
        conn.close()


# ---------- CRUD ----------

SOURCE_TYPES = ("http", "rss", "json", "weather")
RULES = ("contains", "not_contains", "regex", "gt", "gte", "lt", "lte",
         "changed", "new_item", "always")


def list_watchers():
    init_db()
    conn = _conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM watchers ORDER BY id")]
    finally:
        conn.close()


def add_watcher(data):
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO watchers(name,intent,source_type,url,city,field_path,rule,"
            "keyword,threshold,interval_min,cooldown_min,enabled,toast,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(data.get("name", "我的关注")).strip() or "我的关注",
             str(data.get("intent", "有变化时提醒我")).strip(),
             str(data.get("source_type", "http")) if data.get("source_type") in SOURCE_TYPES else "http",
             str(data.get("url", "") or "").strip(),
             str(data.get("city", "") or "").strip(),
             str(data.get("field_path", "") or "").strip(),
             str(data.get("rule", "contains")) if data.get("rule") in RULES else "contains",
             str(data.get("keyword", "") or "").strip(),
             float(data.get("threshold", 0) or 0),
             max(1, int(data.get("interval_min", 60) or 60)),
             max(0, int(data.get("cooldown_min", 60) or 60)),
             1 if data.get("enabled", True) else 0,
             1 if data.get("toast", True) else 0,
             _now_s()),
        )
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def update_watcher(wid, data):
    init_db()
    conn = _conn()
    try:
        fields, vals = [], []
        bool_keys = ("enabled", "toast")
        int_keys = ("interval_min", "cooldown_min")
        enum_keys = {"source_type": SOURCE_TYPES, "rule": RULES}
        for k in ("name", "intent", "source_type", "url", "city", "field_path",
                  "rule", "keyword", "threshold", "interval_min", "cooldown_min",
                  "enabled", "toast"):
            if k not in data:
                continue
            v = data[k]
            if k in bool_keys:
                v = 1 if v else 0
            elif k in int_keys:
                v = max(0, int(v or 0)) if k == "cooldown_min" else max(1, int(v or 1))
            elif k == "threshold":
                v = float(v or 0)
            elif k in enum_keys and v not in enum_keys[k]:
                continue
            else:
                v = str(v)
            fields.append("%s=?" % k); vals.append(v)
        if fields:
            vals.append(wid)
            conn.execute("UPDATE watchers SET " + ",".join(fields) + " WHERE id=?", vals)
            conn.commit()
        return True
    finally:
        conn.close()


def delete_watcher(wid):
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM watchers WHERE id=?", (wid,))
        conn.execute("DELETE FROM watcher_events WHERE watcher_id=?", (wid,))
        conn.commit()
        return True
    finally:
        conn.close()


def list_events(limit=100, watcher_id=None):
    init_db()
    conn = _conn()
    try:
        if watcher_id:
            rows = conn.execute(
                "SELECT * FROM watcher_events WHERE watcher_id=? ORDER BY id DESC LIMIT ?",
                (watcher_id, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM watcher_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def clear_events():
    init_db()
    conn = _conn()
    try:
        conn.execute("DELETE FROM watcher_events")
        conn.commit()
        return True
    finally:
        conn.close()


# ---------- fetching ----------

def _get_text(url, timeout=20):
    if not url or not str(url).lower().startswith(("http://", "https://")):
        raise ValueError("需要有效的 http(s) 地址")
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA,
                                               "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(500000)
        enc = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(enc, "replace")


def _local(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def _parse_feed(text):
    root = ET.fromstring(text)
    items = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = ""
        link = ""
        for ch in el:
            lt = _local(ch.tag)
            if lt == "title" and not title:
                title = (ch.text or "").strip()
            elif lt == "link":
                href = ch.get("href")
                if href:
                    link = href.strip()
                elif (ch.text or "").strip():
                    link = (ch.text or "").strip()
            elif lt == "guid" and not link:
                link = (ch.text or "").strip()
        if title or link:
            items.append({"title": title, "link": link})
    return items


def _dig(obj, path):
    cur = obj
    for part in [p for p in str(path).split(".") if p]:
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(part)
            cur = cur[part]
        elif isinstance(cur, list):
            idx = int(part)
            cur = cur[idx]
        else:
            raise KeyError(part)
    return cur


def _to_number(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = NUM_RE.search(str(text))
    return float(m.group()) if m else None


def fetch(w):
    """Return (value_text, numeric_or_None, items_list, extra_note)."""
    stype = w.get("source_type", "http")
    url = str(w.get("url", "") or "").strip()
    if stype == "weather":
        city = str(w.get("city", "") or "北京").strip()
        lat, lon = CITY_COORDS.get(city, CITY_COORDS["北京"])
        if not url:
            url = ("https://api.open-meteo.com/v1/forecast"
                   "?latitude=%s&longitude=%s&current=temperature_2m,weather_code"
                   % (lat, lon))
        stype = "json"
        if not w.get("field_path"):
            w = dict(w); w["field_path"] = "current.temperature_2m"
    if stype == "json" and not url:
        raise ValueError("JSON 数据源需要填写接口地址")

    text = _get_text(url)

    if stype == "rss":
        items = _parse_feed(text)
        if not items:
            raise ValueError("没有解析到 RSS/Atom 条目")
        value_text = "\n".join(i["title"] for i in items[:20])
        return value_text, None, items, "feed"
    if stype == "json":
        obj = json.loads(text)
        val = _dig(obj, w.get("field_path", ""))
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        value_text = str(val)
        return value_text, _to_number(val), [], str(w.get("field_path", ""))
    # http (plain text / html)
    value_text = re.sub(r"\s+", " ", text).strip()[:20000]
    return value_text, _to_number(value_text[:200]), [], "text"


# ---------- rule evaluation ----------

def _fingerprint(w, value_text, items):
    if w.get("rule") == "new_item" and items:
        return items[0].get("link") or items[0].get("title", "")
    return value_text[:500]


def evaluate(w, value_text, numeric, items):
    """Return (fired: bool, summary: str, fingerprint: str).

    `w['last_value']` is the previous fingerprint; a false/empty value means
    "no baseline yet" for changed/new_item rules (first check establishes it).
    """
    rule = w.get("rule", "contains")
    fp = _fingerprint(w, value_text, items)
    prev = str(w.get("last_value", "") or "")
    kw = str(w.get("keyword", "") or "").strip()

    if rule == "contains":
        hit = bool(kw) and kw.lower() in value_text.lower()
        return hit, ("命中关键词「%s」" % kw) if hit else "", fp
    if rule == "not_contains":
        hit = bool(kw) and kw.lower() not in value_text.lower()
        return hit, ("未出现关键词「%s」" % kw) if hit else "", fp
    if rule == "regex":
        if not kw:
            return False, "", fp
        try:
            m = re.search(kw, value_text, re.I)
        except re.error as e:
            return False, ("正则无效：%s" % e), fp
        return bool(m), (("匹配「%s」：%s" % (kw, m.group()[:80])) if m else ""), fp
    if rule in ("gt", "gte", "lt", "lte"):
        thr = float(w.get("threshold", 0) or 0)
        if numeric is None:
            return False, "未能从数据源解析出数值", fp
        ops = {"gt": numeric > thr, "gte": numeric >= thr,
               "lt": numeric < thr, "lte": numeric <= thr}
        hit = ops[rule]
        sym = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}[rule]
        return hit, ("数值 %s %s %s" % (numeric, sym, thr)) if hit else "", fp
    if rule == "changed":
        if not prev:
            return False, "已建立初始基线", fp
        hit = fp != prev
        return hit, ("内容有变化" if hit else ""), fp
    if rule == "new_item":
        if not prev:
            return False, "已记录最新条目作为基线", fp
        hit = fp != prev
        latest = items[0].get("title", "") if items else ""
        return hit, ("新条目：%s" % latest) if hit else "", fp
    if rule == "always":
        return True, "每次检查都会触发", fp
    return False, "", fp


def _cooldown_ok(w, now):
    last = w.get("last_fire")
    if not last:
        return True
    try:
        t = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return True
    return (now - t).total_seconds() >= int(w.get("cooldown_min", 60) or 0) * 60


def is_due(w, now):
    if not w.get("enabled"):
        return False
    last = w.get("last_check")
    if not last:
        return True
    try:
        t = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return True
    return (now - t).total_seconds() >= max(1, int(w.get("interval_min", 60) or 60)) * 60


def build_message(w, summary):
    name = w.get("name", "我的关注")
    intent = w.get("intent", "有变化时提醒我")
    if summary:
        return "我一直在盯着「%s」：%s。%s" % (name, summary, intent)
    return "我一直在盯着「%s」：%s" % (name, intent)


def log_event(w, fired, summary, message):
    init_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO watcher_events(watcher_id,name,fired,summary,message,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (w.get("id"), w.get("name", ""), 1 if fired else 0,
             str(summary or ""), str(message or ""), _now_s()))
        conn.commit()
    finally:
        conn.close()
