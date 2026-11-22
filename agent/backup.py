# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""backup.py — 全量导出/导入（记忆、笔记、定时、盯事、补牌记录）。

只导出用户数据，不导出 API key。导入默认是合并：已存在的条目会更新或
跳过，不会清空现有数据。危机文本本来就不进 facts，导出时自然也不会带出。
"""

import datetime
import json
import os

import memory
import plugin_kb
import scheduler
import watchers

FORMAT = "olivia-backup"
VERSION = 1


def _extras_path(base_dir):
    return os.path.join(base_dir, "data", "extras.jsonl")


def build(base_dir):
    tasks = scheduler.list_tasks()
    watchers_list = watchers.list_watchers()
    extras = []
    try:
        with open(_extras_path(base_dir), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        extras.append(json.loads(line))
                    except Exception:
                        pass
    except Exception:
        pass
    return {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "memory": {
            "profile": memory.list_profile(),
            "facts": memory.list_facts(limit=10000),
            "draws": memory.list_draws(limit=10000),
            "messages": memory.list_messages(limit=5000),
        },
        "notes": plugin_kb.list_notes(limit=10000),
        "tasks": tasks,
        "watchers": watchers_list,
        "extras": extras,
        "counts": {
            "profile": len(memory.list_profile()),
            "facts": len(memory.list_facts(limit=10000)),
            "draws": len(memory.list_draws(limit=10000)),
            "messages": len(memory.list_messages(limit=5000)),
            "notes": len(plugin_kb.list_notes(limit=10000)),
            "tasks": len(tasks),
            "watchers": len(watchers_list),
        },
    }


def restore(payload, base_dir):
    """Merge a backup into the local database. Returns per-section counts."""
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise ValueError("不是 Olivia 备份文件")
    counts = {"profile": 0, "facts": 0, "draws": 0, "messages": 0,
              "notes": 0, "tasks": 0, "watchers": 0, "extras": 0}

    mem = payload.get("memory") or {}
    for p in mem.get("profile") or []:
        if isinstance(p, dict) and p.get("key"):
            if memory.set_profile(str(p["key"]), str(p.get("value", ""))):
                counts["profile"] += 1
    for f in mem.get("facts") or []:
        if isinstance(f, dict) and f.get("text"):
            if memory.add_fact(str(f.get("kind", "fact")), str(f["text"]),
                               bool(f.get("pinned"))):
                counts["facts"] += 1
    for d in mem.get("draws") or []:
        if isinstance(d, dict) and d.get("cards"):
            cards = d.get("cards")
            if isinstance(cards, list):
                cards = json.dumps(cards, ensure_ascii=False)
            if memory.import_draw(str(d.get("spread", "")), str(cards),
                                  str(d.get("question", "")),
                                  str(d.get("created_at", ""))):
                counts["draws"] += 1

    counts["messages"] = memory.import_messages(mem.get("messages") or [])

    for n in payload.get("notes") or []:
        if isinstance(n, dict) and (n.get("title") or n.get("content")):
            if plugin_kb.add_note(str(n.get("title", "")), str(n.get("content", "")),
                                  n.get("tags", ""), source="import",
                                  pinned=bool(n.get("pinned"))):
                counts["notes"] += 1

    for t in payload.get("tasks") or []:
        if isinstance(t, dict):
            try:
                scheduler.add_task(t)
                counts["tasks"] += 1
            except Exception:
                pass

    for w in payload.get("watchers") or []:
        if isinstance(w, dict):
            try:
                watchers.add_watcher(w)
                counts["watchers"] += 1
            except Exception:
                pass

    extras = payload.get("extras") or []
    if extras:
        path = _extras_path(base_dir)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                for e in extras:
                    if isinstance(e, dict):
                        f.write(json.dumps(e, ensure_ascii=False) + "\n")
                        counts["extras"] += 1
        except Exception:
            pass
    return counts
