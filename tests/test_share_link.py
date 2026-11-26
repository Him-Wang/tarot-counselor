# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""test_share_link.py — 分享深链的编解码、损坏_token、大小/版本上限。"""

import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "agent"))
if AGENT not in sys.path:
    sys.path.insert(0, AGENT)

import share_link  # noqa: E402

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print("  ok   %s" % name)
    else:
        failed += 1
        print("  FAIL %s" % name)


def sample():
    return {
        "v": 1,
        "spread": "三张",
        "question": "我今天该怎么和她说？",
        "cards": [
            {"name": "愚者", "orientation": "正位", "position": "过去"},
            {"name": "月亮", "orientation": "逆位", "position": "现在"},
            {"name": "星星", "orientation": "正位", "position": "未来"},
        ],
    }


def main():
    print("\n" + "=" * 46)
    print(" share_link.py 分享深链自查")
    print("=" * 46)

    p = sample()
    tok = share_link.encode(p)
    check("token 带 o1z. 前缀", tok.startswith(share_link.Z_PREFIX))
    check("token 是 URL-safe（无 +/=）", all(c.isalnum() or c in "-_." for c in tok))
    d = share_link.decode(tok)
    check("往返：牌阵一致", d and d["spread"] == p["spread"])
    check("往返：问题一致", d and d["question"] == p["question"])
    check("往返：不含任何 seed 字段", d and "seed" not in d)
    check("往返：牌数一致", d and len(d["cards"]) == len(p["cards"]))
    check("往返：每张牌一致", d and all(
        a["name"] == b["name"] and a["orientation"] == b["orientation"]
        and a["position"] == b["position"]
        for a, b in zip(d["cards"], p["cards"])
    ))

    # 浏览器生成的明文 o1. 形式：btoa(UTF-8 JSON) 的 base64url（无 padding）
    raw = json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    plain = share_link.PREFIX + base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    dp = share_link.decode(plain)
    check("接受浏览器明文 o1. 形式", dp and dp["cards"][0]["name"] == "愚者")
    check("明文 token 无 padding", not plain.endswith("="))

    check("空串 -> None", share_link.decode("") is None)
    check("未知前缀 -> None", share_link.decode("o9.abc") is None)
    check("损坏压缩体 -> None", share_link.decode(tok[:-3] + "xxx") is None)
    check("损坏明文 JSON -> None", share_link.decode("o1.!!") is None)
    check("非字符串输入 -> None", share_link.decode(None) is None)

    bad_ver = dict(p, v=2)
    check("版本不符 -> None", share_link.decode(share_link._b64url_encode(json.dumps(bad_ver).encode())) is None)
    raw2 = json.dumps(bad_ver, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    check("明文版版本不符 -> None",
          share_link.decode(share_link.PREFIX + share_link._b64url_encode(raw2)) is None)

    big_cards = [{"name": "x" * 100, "orientation": "正位", "position": "p"} for _ in range(79)]
    try:
        share_link.encode(dict(p, cards=big_cards))
        check("牌数 > 78 拒绝编码", False)
    except ValueError:
        check("牌数 > 78 拒绝编码", True)
    raw_many = json.dumps(dict(p, cards=big_cards), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    check("牌数 > 78 拒绝解码",
          share_link.decode(share_link.PREFIX + share_link._b64url_encode(raw_many)) is None)

    huge = dict(p, question="问" * (share_link.MAX_DECODED_BYTES + 1))
    try:
        share_link.encode(huge)
        check("超大 payload 拒绝编码", False)
    except ValueError:
        check("超大 payload 拒绝编码", True)
    check("token 超过 16KB 拒绝解码",
          share_link.decode(share_link.PREFIX + "A" * (share_link.MAX_TOKEN_BYTES + 1)) is None)
    raw_huge = json.dumps(huge, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    check("解压后超过 16KB 拒绝解码（明文形式）",
          share_link.decode(share_link.PREFIX + share_link._b64url_encode(raw_huge)) is None)

    src = open(os.path.join(AGENT, "share_link.py"), encoding="utf-8").read()
    check("不 import pickle / 不调用 eval（只走 json/zlib）",
          "import pickle" not in src and "eval(" not in src)

    print("\n" + "=" * 46)
    print(" 分享深链自查：%d 通过 / %d 失败" % (passed, failed))
    print("=" * 46 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
