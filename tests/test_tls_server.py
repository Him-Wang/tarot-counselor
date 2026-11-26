# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Him-Wang
"""test_tls_server.py — 自签证书生成与 TLS 握手（纯标准库）。"""

import os
import ssl
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.normpath(os.path.join(HERE, "..", "agent"))
if AGENT not in sys.path:
    sys.path.insert(0, AGENT)

import tls_server  # noqa: E402

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
    print(" tls_server.py 局域网 HTTPS 自查")
    print("=" * 46)

    d = tempfile.mkdtemp(prefix="olivia-tls-")
    cert_path = os.path.join(d, "cert.pem")
    key_path = os.path.join(d, "key.pem")
    cert, key = tls_server.generate_self_signed(
        host="127.0.0.1", lan_ip="192.168.1.7", days=30,
        cert_path=cert_path, key_path=key_path)

    check("证书 PEM 格式", cert.startswith("-----BEGIN CERTIFICATE-----"))
    check("私钥 PEM 格式", key.startswith("-----BEGIN RSA PRIVATE KEY-----"))
    check("证书落盘", os.path.isfile(cert_path) and os.path.getsize(cert_path) > 0)
    check("私钥落盘", os.path.isfile(key_path) and os.path.getsize(key_path) > 0)

    ctx = tls_server.ssl_context(cert_path, key_path)
    check("TLS 上下文 TLSv1.2+", ctx.minimum_version == ssl.TLSVersion.TLSv1_2)

    # 真实握手：本地起一个 TLS 服务器，客户端连上拿一下证书
    import socket
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def serve():
        try:
            conn, _ = listener.accept()
            with ctx.wrap_socket(conn, server_side=True) as s:
                s.recv(1)
        except Exception:
            pass
        finally:
            listener.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    client_ctx = ssl.create_default_context()
    client_ctx.check_hostname = False
    client_ctx.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=3) as raw:
            with client_ctx.wrap_socket(raw, server_hostname="localhost") as s:
                peer = s.getpeercert(binary_form=True)
                check("TLS 握手成功且拿到证书", bool(peer))
                check("握手证书非空", len(peer) > 100)
    except Exception as exc:
        check("TLS 握手成功且拿到证书", False)
        print("       handshake error: %s" % exc)
    t.join(timeout=3)

    print("\n" + "=" * 46)
    print(" 局域网 HTTPS 自查：%d 通过 / %d 失败" % (passed, failed))
    print("=" * 46 + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
