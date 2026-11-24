#!/usr/bin/env python3
"""Asks the serial bridge to move a file over the Compaq's cable with Kermit.

The shared screen pauses on the Compaq while the transfer runs.
Usage: transfer.py send FILE | transfer.py receive FOLDER [DOS-FILES]
DOS-FILES (like C:\LETTER.TXT or *.TXT) is for when PILINK is the Compaq's
terminal (PI.BAT): the Pi fetches them itself. Through Kermit, someone
types SEND at the Compaq instead.
Exits 0 when the transfer finished, 1 when it didn't, 2 when no Compaq is
connected.
"""

import json
import os
import socket
import sys

SOCKET = "/run/compaq-serial/bridge.sock"


def main():
    if len(sys.argv) not in (3, 4) or sys.argv[1] not in ("send", "receive"):
        sys.exit(__doc__.strip())
    op, target = sys.argv[1], os.path.abspath(sys.argv[2])
    request = {"op": op, "path": target} if op == "send" else {"op": op, "dir": target}
    if op == "receive" and len(sys.argv) == 4:
        request["files"] = sys.argv[3]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.connect(SOCKET)
            conn.sendall((json.dumps(request) + "\n").encode())
            reply = json.loads(conn.makefile().readline() or "{}")
    except KeyboardInterrupt:        # (Ctrl-C is how a transfer is cancelled: the bridge sees us go)
        print("\n  Transfer cancelled.")
        sys.exit(1)
    except (OSError, ValueError):
        print("  The Compaq isn't connected: its cable isn't plugged into the Pi.")
        sys.exit(2)
    print(f"  {reply.get('message', 'No answer from the bridge.')}")
    sys.exit(0 if reply.get("ok") else 1)


if __name__ == "__main__":
    main()
