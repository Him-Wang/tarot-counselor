# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""tls_server.py — 局域网 HTTPS 支持（可选，零第三方依赖）。

Olivia 默认只监听 127.0.0.1，明文 HTTP 是可以接受的。一旦要「手机连电脑」
或「局域网里别人访问」，HTTP 会把对话内容、API key 输入框和网络状态暴露在
同一网段。这个模块提供两件事：

  1. generate_self_signed(...)  —— 没有 openssl 也能造一张自签证书。
     纯标准库实现 RSA-2048 密钥对 + X.509v3 证书（SHA-256 签名，带 SAN）。
     生成的私钥留在本地，权限收紧到仅当前用户可读。
  2. wrap_server(...)           —— 给已有的 HTTPServer 套上 SSLContext。

注意：自签证书只能解决「传输加密」，浏览器会提示「不受信任」，需要手动
点继续，或在手机上安装这张证书。它不是身份验证。真正对公网开放请用
Let's Encrypt 等正规证书 + 反向代理（见 docs/DEPLOY.md）。

用法：
    from tls_server import generate_self_signed, ssl_context
    cert, key = generate_self_signed(host="127.0.0.1", lan_ip="192.168.1.7")
    ctx = ssl_context(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
"""

import base64
import datetime
import hashlib
import os
import random
import socket
import ssl
import struct
import time

# ---------------- DER / ASN.1 最小编码工具 ----------------


def _der(tag, value):
    n = len(value)
    if n < 0x80:
        length = bytes([n])
    elif n < 0x100:
        length = bytes([0x81, n])
    elif n < 0x10000:
        length = bytes([0x82]) + struct.pack(">H", n)
    else:
        length = bytes([0x83]) + struct.pack(">I", n)[1:]
    return bytes([tag]) + length + value


def _seq(*parts):
    return _der(0x30, b"".join(parts))


def _setof(*parts):
    return _der(0x31, b"".join(parts))


def _integer(value):
    if value == 0:
        body = b"\x00"
    else:
        body = value.to_bytes((value.bit_length() + 7) // 8, "big")
        if body[0] & 0x80:
            body = b"\x00" + body
    return _der(0x02, body)


def _oid(dotted):
    arcs = [int(a) for a in dotted.split(".")]
    body = bytearray([arcs[0] * 40 + arcs[1]])
    for arc in arcs[2:]:
        chunk = [arc & 0x7F]
        arc >>= 7
        while arc:
            chunk.insert(0, (arc & 0x7F) | 0x80)
            arc >>= 7
        body.extend(chunk)
    return _der(0x06, bytes(body))


def _boolean(value):
    return _der(0x01, b"\xff" if value else b"\x00")


def _bitstring(value, unused=0):
    return _der(0x03, bytes([unused]) + value)


def _ia5(text):
    return _der(0x16, text.encode("ascii"))


def _utf8(text):
    return _der(0x0C, text.encode("utf-8"))


def _name(common_name):
    rdn = _setof(_seq(_oid("2.5.4.3"), _utf8(common_name)))
    return _seq(rdn)


def _algorithm_rsa_sha256():
    return _seq(_oid("1.2.840.113549.1.1.11"), _der(0x05, b""))


def _algorithm_rsa():
    return _seq(_oid("1.2.840.113549.1.1.1"), _der(0x05, b""))


def _utc_time(dt):
    return _der(0x17, dt.strftime("%y%m%d%H%M%SZ").encode("ascii"))


def _spki(n, e):
    pkcs1 = _seq(_integer(n), _integer(e))
    return _seq(_algorithm_rsa(), _bitstring(pkcs1))


# ---------------- RSA 密钥生成（Miller-Rabin） ----------------


def _is_probable_prime(n, rounds=24):
    if n < 2:
        return False
    small = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits):
    while True:
        cand = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(cand):
            return cand


def _modinv(a, m):
    old_r, r = a, m
    old_s, s = 1, 0
    while r:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
    if old_r != 1:
        raise ValueError("no modular inverse")
    return old_s % m


def _generate_rsa(bits=2048):
    e = 65537
    p = _prime(bits // 2)
    q = _prime(bits // 2)
    while p == q:
        q = _prime(bits // 2)
    n = p * q
    phi = (p - 1) * (q - 1)
    d = _modinv(e, phi)
    dp = d % (p - 1)
    dq = d % (q - 1)
    qinv = _modinv(q, p)
    return {"n": n, "e": e, "d": d, "p": p, "q": q, "dp": dp, "dq": dq, "qinv": qinv}


# ---------------- PKCS#1 v1.5 签名 ----------------

_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _rsa_sign(digest, key):
    k = (key["n"].bit_length() + 7) // 8
    payload = _SHA256_DIGESTINFO + digest
    ps_len = k - len(payload) - 3
    if ps_len < 8:
        raise ValueError("RSA modulus too small")
    em = b"\x00\x01" + b"\xff" * ps_len + b"\x00" + payload
    m = int.from_bytes(em, "big")
    sig = pow(m, key["d"], key["n"])
    return sig.to_bytes(k, "big")


# ---------------- PEM 输出 ----------------


def _pem(label, der):
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return "-----BEGIN %s-----\n%s\n-----END %s-----\n" % (
        label, "\n".join(lines), label)


def _pkcs1_private(key):
    return _seq(
        _integer(0), _integer(key["n"]), _integer(key["e"]), _integer(key["d"]),
        _integer(key["p"]), _integer(key["q"]), _integer(key["dp"]),
        _integer(key["dq"]), _integer(key["qinv"]),
    )


# ---------------- 公开 API ----------------


def generate_self_signed(host="127.0.0.1", lan_ip=None, dns="localhost", days=825,
                         cert_path=None, key_path=None, bits=2048):
    """生成自签证书。返回 (cert_pem, key_pem)。给 paths 就顺手落盘并收紧权限。"""
    key = _generate_rsa(bits)
    now = datetime.datetime.utcnow()
    not_before = _utc_time(now - datetime.timedelta(days=1))
    not_after = _utc_time(now + datetime.timedelta(days=days))
    serial = int.from_bytes(os.urandom(16), "big") & ~(1 << 127)

    names = []
    if host and host not in ("0.0.0.0", "::"):
        try:
            names.append(_der(0x87, socket.inet_aton(host)))  # [7] IP
        except OSError:
            names.append(_der(0x82, _ia5(host)))             # [2] DNS
    if lan_ip:
        try:
            names.append(_der(0x87, socket.inet_aton(lan_ip)))
        except OSError:
            pass
    if dns:
        names.append(_der(0x82, _ia5(dns)))
    san = _der(0x30, b"".join(names))

    extensions = _seq(
        _seq(_oid("2.5.29.19"), _boolean(True),
             _der(0x04, _seq(_boolean(True)))),  # basicConstraints CA:TRUE
        _seq(_oid("2.5.29.15"), _boolean(True),
             _der(0x04, _bitstring(bytes([0xA4]), 0))),
        # digitalSignature + keyEncipherment + keyCertSign
        _seq(_oid("2.5.29.17"), _der(0x04, san)),
    )

    subject = _name("Olivia LAN (self-signed)")
    tbs = _seq(
        _der(0xA0, _integer(2)),        # version v3
        _integer(serial),
        _algorithm_rsa_sha256(),
        subject,                        # self-signed: issuer == subject
        _seq(not_before, not_after),
        subject,
        _spki(key["n"], key["e"]),
        _der(0xA3, extensions),
    )
    sig = _rsa_sign(hashlib.sha256(tbs).digest(), key)
    cert_der = _seq(tbs, _algorithm_rsa_sha256(), _bitstring(sig))
    cert_pem = _pem("CERTIFICATE", cert_der)
    key_pem = _pem("RSA PRIVATE KEY", _pkcs1_private(key))

    if cert_path or key_path:
        if cert_path:
            with open(cert_path, "w", encoding="ascii") as f:
                f.write(cert_pem)
        if key_path:
            with open(key_path, "w", encoding="ascii") as f:
                f.write(key_pem)
            try:
                os.chmod(key_path, 0o600)  # POSIX；Windows 下被忽略
            except OSError:
                pass
    return cert_pem, key_pem


def ssl_context(cert_path, key_path, password=None):
    """建一个现代 TLS 上下文（TLS1.2+，禁用弱套件）。"""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert_path, key_path, password=password)
    return ctx


def wrap_httpd(httpd, cert_path, key_path, password=None):
    """给已有 HTTPServer 套 TLS；返回同一个 httpd 便于链式调用。"""
    ctx = ssl_context(cert_path, key_path, password)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    return httpd


def ensure_cert(data_dir, host="127.0.0.1", lan_ip=None, days=825):
    """证书不存在就生成；存在就直接返回路径。供 server.py 启动时调用。"""
    os.makedirs(data_dir, exist_ok=True)
    cert = os.path.join(data_dir, "lan-cert.pem")
    key = os.path.join(data_dir, "lan-key.pem")
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        generate_self_signed(host=host, lan_ip=lan_ip, days=days,
                             cert_path=cert, key_path=key)
    return cert, key
