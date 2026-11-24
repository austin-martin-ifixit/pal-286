#!/usr/bin/env python3
"""The menu's FixBot: FixBot's own web page (fixbot.ifixit.com), logged in,
on the Compaq's screen, with what's typed here (the TV's keyboard, a browser
on the shared session) passed on to it as keys. The page and its iFixit
login are PAL's (lib/fixbot_page.py, in PAL's service): this program only
asks for it and passes keys along. F10 leaves, as everywhere.

When the page can't be shown (no login yet, or a screen without PILINK's
dots), FixBot's repair plans in text instead (chat.py --backend fixbot).
"""

import json
import os
import select
import socket
import sys
import termios
import tty

PAL_SOCKET = "/run/compaq-pal/pal.sock"


def plans(why):
    print(f"\n  {why}\n  Here are FixBot's repair plans in text instead.\n", flush=True)
    os.execv(sys.executable, [sys.executable, "/opt/compaq/lib/chat.py", "--backend", "fixbot"])


def main():
    print("\n  Opening FixBot (about ten seconds)...", flush=True)
    try:
        pal = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        pal.settimeout(90)
        pal.connect(PAL_SOCKET)
        pal.sendall(b'{"op": "fixbot_page"}\n')
        first = b""
        while not first.endswith(b"\n"):          # (one byte at a time: nothing after it is read early)
            byte = pal.recv(1)
            if not byte:
                break
            first += byte
        answer = json.loads(first or b"{}")
    except (OSError, ValueError) as e:
        plans(f"FixBot's page didn't open (PAL's service: {e}).")
    if not answer.get("ok"):
        plans(answer.get("message", "FixBot's page didn't open."))
    pal.settimeout(None)
    stdin = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin) if os.isatty(stdin) else None
    try:
        if saved:
            tty.setraw(stdin)
        while True:
            ready, _, _ = select.select([stdin, pal], [], [])
            if pal in ready:
                break                              # (PAL took the page down, or went away)
            typed = os.read(stdin, 512)
            if not typed:
                break
            pal.sendall(typed)
    except OSError:
        pass
    finally:
        if saved:
            termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        pal.close()


if __name__ == "__main__":
    main()
