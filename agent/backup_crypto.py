# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""backup_crypto.py — 备份文件的可选口令加密（纯标准库实现）。

为什么不用第三方库
------------------
Olivia 是零依赖项目。这里只用 hashlib / hmac 就能做到「带认证的加密」，
不引入cryptography。方案是教科书式的组合，不是自创算法：

  * 密钥派生：PBKDF2-HMAC-SHA256(passphrase, salt, 200000, 64 字节)，
    前 32 字节作加密密钥、后 32 字节作 MAC 密钥。
  * 加密：HMAC-SHA256(enc_key, nonce || counter_le64) 生成密钥流，与明文异或
    （CTR 模式；计数器从不重复，因为每次都换新 nonce）。
  * 认证：HMAC-SHA256(mac_key, header || ciphertext)，恒定时间比较。
    没有正确口令就解不开，且篡改密文会被检测出来（不是只乱码）。

文件格式（字节序）
------------------
  MAGIC(8) | ITER(4, big-endian) | SALT(16) | NONCE(16) | CIPHERTEXT(n) | TAG(32)

明文就是 UTF-8 的 JSON（backup.build() 的输出）。解密后仍是同一个 dict。

安全提示
--------
口令丢了就找不回数据——没有后门、没有密钥托管。请用足够长的口令，
并把它和备份文件分开保存。此加密只保护「静态文件」，不保护已解密的内存。
"""

import hashlib
import hmac
import os
import struct

MAGIC = b"OLIVIA-E1"
ITERATIONS = 200000
SALT_LEN = 16
NONCE_LEN = 16
KEY_LEN = 32
HEADER_LEN = len(MAGIC) + 4 + SALT_LEN + NONCE_LEN
TAG_LEN = 32


def _derive(passphrase, salt, iterations):
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    material = hashlib.pbkdf2_hmac(
        "sha256", passphrase, salt, int(iterations), dklen=KEY_LEN * 2)
    return material[:KEY_LEN], material[KEY_LEN:]


def _keystream(key, nonce, nbytes):
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        block = hmac.new(key, nonce + struct.pack("<Q", counter), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:nbytes])


def encrypt(plaintext, passphrase):
    """把 bytes/str 明文加密成带认证的二进制 blob。"""
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    if not passphrase:
        raise ValueError("加密备份必须提供口令")
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    enc_key, mac_key = _derive(passphrase, salt, ITERATIONS)
    stream = _keystream(enc_key, nonce, len(plaintext))
    cipher = bytes(a ^ b for a, b in zip(plaintext, stream))
    header = MAGIC + struct.pack(">I", ITERATIONS) + salt + nonce
    tag = hmac.new(mac_key, header + cipher, hashlib.sha256).digest()
    return header + cipher + tag


def decrypt(blob, passphrase):
    """解密 encrypt() 产生的 blob，返回明文 bytes；口令错/篡改则抛 ValueError。"""
    if isinstance(blob, str):
        raise ValueError("加密备份是二进制文件，请按二进制方式读取")
    if len(blob) < HEADER_LEN + TAG_LEN or blob[:len(MAGIC)] != MAGIC:
        raise ValueError("不是 Olivia 加密备份文件")
    iterations = struct.unpack(">I", blob[len(MAGIC):len(MAGIC) + 4])[0]
    if iterations < 10000 or iterations > 5000000:
        raise ValueError("备份文件的迭代次数不合理，已拒绝")
    salt = blob[len(MAGIC) + 4:len(MAGIC) + 4 + SALT_LEN]
    nonce = blob[len(MAGIC) + 4 + SALT_LEN:HEADER_LEN]
    header = blob[:HEADER_LEN]
    cipher = blob[HEADER_LEN:-TAG_LEN]
    tag = blob[-TAG_LEN:]
    enc_key, mac_key = _derive(passphrase, salt, iterations)
    expect = hmac.new(mac_key, header + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(expect, tag):
        raise ValueError("口令错误，或备份文件已被篡改")
    stream = _keystream(enc_key, nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream))
