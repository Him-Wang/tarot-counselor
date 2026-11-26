# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""test_backup_crypto.py — 加密备份的往返 / 口令错误 / 篡改检测。"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "agent"))
if AGENT not in sys.path:
    sys.path.insert(0, AGENT)

import backup_crypto  # noqa: E402

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


def main():
    print("\n" + "=" * 46)
    print(" backup_crypto.py 加密备份自查")
    print("=" * 46)

    payload = ('{"format":"olivia-backup","memory":{"profile":'
               '[{"key":"昵称","value":"小星"}]}}').encode("utf-8")
    pw = "一段足够长的正确口令 2026!"

    blob = backup_crypto.encrypt(payload, pw)
    check("密文不等于明文", blob != payload)
    check("密文带魔数", blob[:len(backup_crypto.MAGIC)] == backup_crypto.MAGIC)
    check("往返解密一致", backup_crypto.decrypt(blob, pw) == payload)
    check("随机 salt/nonce：两次加密不同",
          backup_crypto.encrypt(payload, pw) != blob)

    try:
        backup_crypto.decrypt(blob, "错误口令")
        check("错误口令被拒", False)
    except ValueError:
        check("错误口令被拒", True)

    tampered = bytearray(blob)
    tampered[backup_crypto.HEADER_LEN] ^= 0x01
    try:
        backup_crypto.decrypt(bytes(tampered), pw)
        check("篡改检测", False)
    except ValueError:
        check("篡改检测", True)

    try:
        backup_crypto.decrypt(b"not an olivia blob", pw)
        check("非法文件头被拒", False)
    except ValueError:
        check("非法文件头被拒", True)

    try:
        backup_crypto.encrypt(payload, "")
        check("空口令被拒", False)
    except ValueError:
        check("空口令被拒", True)

    print("\n" + "=" * 46)
    print(" 加密备份自查：%d 通过 / %d 失败" % (passed, failed))
    print("=" * 46 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
