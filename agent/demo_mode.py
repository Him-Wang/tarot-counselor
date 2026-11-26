# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Read-only public demo mode for Olivia (Python stdlib only).

WHY THIS EXISTS
---------------
A public demo must not accumulate visitor data.  This module is a single,
reusable guard that another worker can wire into ``agent/server.py`` without
changing any other module.  It deliberately does **not** import ``server``,
``memory`` or any persistence module, so it can be imported anywhere (and by
standalone tests) without circular imports or side effects.

SEMANTICS (what "demo mode" means)
----------------------------------
When enabled (``OLIVIA_DEMO=1`` in the environment, or via ``set_enabled(True)``
from a future ``--demo`` CLI flag), the server:

1. runs with a fixed, known-safe configuration: every API key is discarded,
   the provider is forced offline (empty key + empty base_url + empty model),
   ``memory_enabled`` / ``occult_enabled`` / ``prophecy_enabled`` /
   ``safety_second_check`` are forced off, and the locked product defaults
   (tools / tone / two-phase draw) stay on;
2. writes nothing at all: no config.json, no memory.db / kb.db /
   scheduler.db / watchers.db, no journal notes, no tasks, no watchers, no
   archive entries, no ``extras.jsonl``, no vision config, no PID file if the
   caller routes that write through ``guard_write()``;
3. resets all in-memory per-session state (pending draws, awaiting-spread,
   last-spreads, pending archive) at the start of every HTTP request, so two
   unrelated visitors can never share state;
4. tells the UI it is a demo via ``GET /api/config`` (``"demo": true`` plus a
   short notice) and shows a server-independent banner in ``index.html``.

Replies are produced by ``offline.compose`` / ``offline.compose_chat`` — local,
canned guidance, explicitly labelled "离线整理 … 不是 AI 解读".  There are no
model/network calls in demo mode.

EXACT INTEGRATION INTO agent/server.py (4 call sites + write guards)
-------------------------------------------------------------------
The owning worker/parent applies these edits; this module never edits server.py.

(1) Import, near the other imports at the top of ``agent/server.py``::

        import demo_mode

(2) ``load_config()`` — harden the config on the way out, before any caller
    can see a stored key (replace the final ``return cfg``)::

        return demo_mode.enforce(cfg)

    ``enforce()`` only hardens when :func:`enabled` is True; in a normal
    process it returns an unchanged shallow copy, so this line is safe to
    apply unconditionally.  It covers ``/api/chat``, ``/api/config``,
    ``scheduler.start`` and every other ``load_config()`` consumer.  It does
    not itself prevent writes; that is what ``guard_write()`` is for.

(3) ``do_GET`` / ``do_POST`` — reset per-request state at the very top of each
    handler (after reading ``p``), and expose the banner payload::

        def do_GET(self):
            p = self.path.split("?")[0]
            if demo_mode.enabled():
                demo_mode.reset_in_memory_state(
                    _pending_draws, _awaiting_spread, _last_spreads,
                    _pending_archive)

        def do_POST(self):
            p = self.path.split("?")[0]
            if demo_mode.enabled():
                demo_mode.reset_in_memory_state(
                    _pending_draws, _awaiting_spread, _last_spreads,
                    _pending_archive)
            # ... existing body parsing ...

    NOTE: clearing pending draws every request means the two-phase
    "pick then interpret" flow cannot span requests in demo mode.  The chat
    endpoint falls back to drawing locally, which is the intended demo flow.

    ``GET /api/config`` — add the public flag to the existing JSON object::

        self._send_json({
            "config": mask(cfg),
            ...                       # existing keys unchanged
            **demo_mode.public_config(),   # adds demo/notice/restrictions
        })

    ``GET /`` (index.html) is served verbatim; the hidden
    ``<aside id="demoBanner">`` in index.html is revealed by the one-line
    ``loadConfig()`` hook in ``static/app.js`` (already included in this
    change).  Optional server-side alternative instead of editing app.js::

        if demo_mode.enabled():
            body = body.replace(b"<aside id=\"demoBanner\" hidden>",
                                b"<aside id=\"demoBanner\">", 1)

(4) Block persistence.  ``guard_write(label)`` raises ``DemoReadOnly`` when
    demo mode is on; it is a no-op returning ``True`` otherwise.  Use the
    fail-fast form for endpoints whose whole purpose is a write (place it
    before any DB access, inside the existing ``try`` block so the existing
    ``except Exception`` returns a 500 JSON error, or catch explicitly for
    403)::

        demo_mode.guard_write("api/config save")   # before save_config(cfg)
        demo_mode.guard_write("api/memory")        # top of POST /api/memory
        demo_mode.guard_write("api/schedule")      # top of POST /api/schedule
        demo_mode.guard_write("api/goals")         # top of POST /api/goals
        demo_mode.guard_write("api/archive")       # top of POST /api/archive
        demo_mode.guard_write("api/plugins")       # top of POST /api/plugins
        demo_mode.guard_write("api/pick")          # before memory.record_draw

    For SSE endpoints, headers may already be sent, so do not raise mid-stream.
    Use the non-throwing predicate around each persistence block instead::

        if demo_mode.should_persist():
            memory.add_usage(...)
            _pending_archive[sid] = {...}
            memory.remember(...)

    The same predicate should wrap ``_record_extra(...)`` (extras.jsonl) and
    the background task in ``main()``::

        if demo_mode.should_persist():
            scheduler.start(load_config)

    and the PID-file write in ``main()``.  ``public_config()["restrictions"]``
    documents exactly which writes are covered.

(5) CRITICAL: re-injected keys.  ``/api/chat`` overwrites the key from the
    request body (``cfg["api_key"] = _effective_api_key(cfg, body.get("api_key"))``)
    and ``POST /api/config`` accepts ``api_key`` from the body.  After (2)
    those would smuggle a real key back into a demo request.  Guard them::

        # /api/chat, right after cfg = load_config():
        if demo_mode.enabled():
            cfg = demo_mode.enforce(cfg)   # re-strip any body-injected key

        # POST /api/config: place demo_mode.guard_write("api/config save")
        # before save_config(cfg) so no body value is ever persisted.

(6) Optional startup banner in ``main()``::

        if demo_mode.enabled():
            print(demo_mode.startup_notice())
        print("Press Ctrl+C to stop.")

For a future CLI flag, call ``demo_mode.set_enabled(True)`` when ``--demo`` is
parsed; ``enabled()`` then returns True regardless of the environment variable.

SECURITY NOTE
-------------
Demo mode is defence in depth, not a sandbox.  The safe way to host it is
``OLIVIA_DEMO=1 python agent/server.py`` bound to loopback behind a TLS reverse
proxy.  See ``docs/DEMO.md``.  NEVER expose a non-demo instance to the internet.
"""

import os

__all__ = [
    "DemoReadOnly",
    "enabled",
    "set_enabled",
    "enforce",
    "guard_write",
    "should_persist",
    "reset_in_memory_state",
    "public_config",
    "startup_notice",
]

ENV_VAR = "OLIVIA_DEMO"
_TRUTHY = {"1", "true", "yes", "on"}
_CLI_ENABLED = False

DEMO_NOTICE_ZH = (
    "演示模式：对话与抽牌只留在内存里，不会保存。回复是本地离线整理，不是 AI 解读。"
)
DEMO_NOTICE_EN = (
    "Demo mode: nothing you type or draw is saved. Replies are offline, "
    "canned guidance, not AI readings."
)

# Full safe baseline.  Any key absent from the incoming config is filled from
# here; security-sensitive keys are always overwritten by _FORCED below.
_BASE = {
    "backend": "offline",
    "protocol": "auto",
    "base_url": "",
    "api_key": "",
    "model": "",
    "temperature": 0.8,
    "timeout": 30,
    "tools_enabled": True,
    "memory_enabled": False,
    "prophecy_enabled": False,
    "occult_enabled": False,
    "two_phase_draw": True,
    "tone_enabled": True,
    "language": "zh",
    "daily_token_budget": 0,
    "max_output_tokens": 0,
    "max_history_messages": 20,
    "max_history_chars": 24000,
    "safety_second_check": False,
}

# Non-negotiable demo values.  "offline" is a UI marker, not a provider
# protocol: the actual offline switch is the empty api_key/base_url/model,
# which makes offline.is_offline(cfg) True before provider.py ever runs.
_FORCED = {
    "backend": "offline",
    "protocol": "auto",
    "base_url": "",
    "api_key": "",
    "api_key_enc": "",
    "model": "",
    "memory_enabled": False,
    "prophecy_enabled": False,
    "occult_enabled": False,
    "safety_second_check": False,
    "tools_enabled": True,
    "tone_enabled": True,
    "two_phase_draw": True,
    "demo": True,
}
_SENSITIVE = frozenset(_FORCED)


class DemoReadOnly(RuntimeError):
    """Raised by :func:`guard_write` when a write is attempted in demo mode."""


def set_enabled(value):
    """Enable/disable demo mode from a CLI flag (e.g. ``--demo``).

    The environment variable remains authoritative in the sense that either
    source turns demo mode on; call ``set_enabled(False)`` only when the
    process was started without ``OLIVIA_DEMO`` and the flag is absent.
    """
    global _CLI_ENABLED
    _CLI_ENABLED = bool(value)
    return _CLI_ENABLED


def enabled():
    """Return True when the process is running as a public read-only demo.

    Honours ``OLIVIA_DEMO`` (case-insensitive ``1/true/yes/on``) or a prior
    ``set_enabled(True)`` call.  Never raises; safe to call from any handler.
    """
    if _CLI_ENABLED:
        return True
    return str(os.environ.get(ENV_VAR, "") or "").strip().lower() in _TRUTHY


def enforce(cfg=None):
    """Return a *new* hardened config dict; never mutates the argument.

    ``cfg`` may be a full server config, a partial dict, or ``None``.  Every
    non-sensitive value is preserved (so UI preferences such as language
    still work), while all network-capable and persistence-capable knobs are
    overwritten with fixed safe values.  ``api_key_enc`` is removed entirely
    so no encrypted key can be resurrected by ``save_config`` later.

    Intended call site: the last line of ``server.load_config()``.  When demo
    mode is off, returns a plain copy of ``cfg`` (unchanged values) so the
    line can be applied unconditionally.

    Caveat for the parent: ``server.py`` currently accepts an api key from
    the request body in ``/api/chat`` (``_effective_api_key(cfg, body["api_key"])``)
    and in ``POST /api/config``.  Those paths must be routed through
    ``demo_mode.enforce(cfg)`` again (or skipped via ``should_persist()``),
    otherwise a visitor could re-inject a key into a single request.
    """
    if not enabled():
        return dict(cfg) if cfg else dict(_BASE)
    out = dict(_BASE)
    if cfg:
        out.update({k: v for k, v in dict(cfg).items() if k not in _SENSITIVE})
    out.update(_FORCED)
    out.pop("api_key_enc", None)
    return out


def guard_write(label="write"):
    """Block a persistence operation in demo mode.

    Raises :class:`DemoReadOnly` when :func:`enabled` is True; otherwise
    returns True.  ``label`` is only for the error message (use the route
    name or the resource, e.g. ``"api/archive"``).  See the module docstring
    for the exact server.py call sites, and prefer :func:`should_persist`
    inside an already-open SSE response where raising would break the stream.
    """
    if enabled():
        raise DemoReadOnly("演示模式为只读，不允许写入：%s" % label)
    return True


def should_persist():
    """Convenience predicate: ``not enabled()``.

    Use ``if demo_mode.should_persist():`` around memory writes, usage
    accounting, archive staging, extras logging, scheduler startup and PID
    file creation.  This avoids raising after SSE headers have been sent.
    """
    return not enabled()


def reset_in_memory_state(*state_dicts):
    """Clear every supplied per-session dict (demo "auto-reset").

    Pass the server's ``_pending_draws``, ``_awaiting_spread``,
    ``_last_spreads`` and ``_pending_archive``.  Non-dict arguments are
    ignored so callers can pass mixed state safely.  Returns the number of
    dicts actually cleared.  Intended call site: top of ``do_GET``/``do_POST``.
    """
    cleared = 0
    for state in state_dicts:
        if isinstance(state, dict):
            state.clear()
            cleared += 1
    return cleared


def public_config():
    """Return the JSON fragment merged into ``GET /api/config``.

    Shape (stable in both modes)::

        {
          "demo": bool,
          "notice": str,          # non-empty only in demo mode
          "restrictions": {...},  # booleans describing what is unavailable
          "reset": "every_request" | None,
        }

    The front end only needs ``demo``; the rest is documentation for API
    consumers and for anyone auditing a hosted instance.  No secrets are
    ever included.
    """
    on = enabled()
    return {
        "demo": on,
        "notice": DEMO_NOTICE_ZH if on else "",
        # True = unavailable in this process.  In a normal (non-demo) process
        # nothing is restricted; in demo mode every item below is blocked.
        "restrictions": {
            "model_calls": on,
            "persistence": on,
            "memory": on,
            "occult": on,
            "prophecy": on,
            "safety_second_check": on,
        },
        "reset": "every_request" if on else None,
    }


def startup_notice():
    """One-line banner for ``main()``; safe to print in either mode."""
    if enabled():
        return "[DEMO] 只读演示模式已开启：不保存任何数据；回复为离线整理，不是 AI 解读。"
    return ""
