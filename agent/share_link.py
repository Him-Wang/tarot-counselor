# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""Shareable deep links for a drawn tarot reading (stdlib only).

A link is ``?reading=<token>`` appended to the Olivia page URL.  The token is:

    o1.<base64url(json)>

where ``json`` is the compact UTF-8 payload described below, with no padding.
The same format is produced/consumed by the browser (``agent/static/app.js``):
the client builds ``o1.<b64url(JSON)`` using ``btoa(unescape(encodeURIComponent(json)))``,
and this module deliberately accepts that *plain base64url JSON* form as well
as a zlib-compressed ``o1z.<base64url(zlib(json))>`` form (kept for compact
server-side tokens).  Version is the leading ``v`` field, always 1.

Payload schema::

    {"v": 1,
     "spread": "三张",
     "question": "...",
     "cards": [{"name": "愚者", "orientation": "正位", "position": "过去"}, ...]}

Limits on decode: token <= 16 KB, decoded JSON <= 16 KB, at most 78 cards.
Only ``dict``/``list``/``str``/``int``/``bool``/``None`` JSON values are accepted;
decode never uses ``eval`` or ``pickle``.  Corrupt / unknown / oversized tokens
return ``None``.

Security note: the token is **tamper-evident only by zlib CRC** (for the
compressed form) / by JSON syntax (for the plain form).  There is no secret in
a stateless share link, so there is no HMAC: a token is NOT authenticated.  A
reader must treat the payload as untrusted text and escape it in the UI.
"""

import base64
import binascii
import json
import zlib

PREFIX = "o1."
Z_PREFIX = "o1z."
MAX_TOKEN_BYTES = 16 * 1024
MAX_DECODED_BYTES = 16 * 1024
MAX_CARDS = 78
VALID_VERSIONS = (1,)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text:
        raise ValueError("empty token")
    # base64.urlsafe_b64decode tolerates junk in some Pythons; validate first.
    for ch in text:
        if not (ch.isascii() and (ch.isalnum() or ch in "-_")):
            raise ValueError("invalid base64url character")
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def encode(payload: dict) -> str:
    """Encode a reading dict into a URL-safe token (compact, zlib-compressed).

    Raises ValueError/TypeError for a malformed payload rather than emitting a
    token a reader would reject.
    """
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    if payload.get("v") not in VALID_VERSIONS:
        raise ValueError("unsupported version")
    cards = payload.get("cards")
    if not isinstance(cards, list) or len(cards) > MAX_CARDS:
        raise ValueError("invalid card list")
    clean = []
    for c in cards:
        if not isinstance(c, dict):
            raise ValueError("invalid card")
        clean.append({
            "name": str(c.get("name", "")),
            "orientation": str(c.get("orientation", "")),
            "position": str(c.get("position", "")),
        })
    clean_payload = {
        "v": 1,
        "spread": str(payload.get("spread", "")),
        "question": str(payload.get("question", "")),
        "cards": clean,
    }
    raw = json.dumps(clean_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_DECODED_BYTES:
        raise ValueError("payload too large")
    return Z_PREFIX + _b64url_encode(zlib.compress(raw, 9))


def decode(token: str):
    """Return a validated payload dict, or ``None`` for any unknown/corrupt input."""
    try:
        if not isinstance(token, str):
            return None
        if len(token.encode("utf-8")) > MAX_TOKEN_BYTES:
            return None
        if token.startswith(Z_PREFIX):
            raw = zlib.decompress(_b64url_decode(token[len(Z_PREFIX):]))
        elif token.startswith(PREFIX):
            raw = _b64url_decode(token[len(PREFIX):])
        else:
            return None
        if len(raw) > MAX_DECODED_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or data.get("v") not in VALID_VERSIONS:
            return None
        cards = data.get("cards")
        if not isinstance(cards, list) or len(cards) > MAX_CARDS:
            return None
        for c in cards:
            if not isinstance(c, dict):
                return None
            for k in ("name", "orientation", "position"):
                if k in c and not isinstance(c[k], str):
                    return None
        for k in ("spread", "question"):
            if k in data and not isinstance(data[k], str):
                return None
        return data
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, zlib.error):
        return None


__all__ = [
    "PREFIX", "Z_PREFIX", "MAX_TOKEN_BYTES", "MAX_DECODED_BYTES", "MAX_CARDS",
    "encode", "decode",
]
