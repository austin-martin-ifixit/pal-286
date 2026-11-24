#!/usr/bin/env python3
"""Shows what a program would look like on the Compaq.

Runs a command on an 80x24 pseudo-terminal set up like the serial login
(TERM=vt102, plain ASCII locale), types the given keys, then prints the final
screen, how long that output takes at 9600 baud, and any non-ASCII bytes
(which the Compaq would show as garbage). Needs python3-pyte; run it on the Pi.

Usage: screentest.py [--wait SECONDS] [--keys KEYS]... -- command [args]
KEYS take Python escapes (e.g. 'q\\r', '\\x1b'); each is typed after a wait.
"""

import argparse
import codecs
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import time

import pyte


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--wait", type=float, default=3.0)
    parser.add_argument("--keys", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command

    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        # Programs run inside tmux, so they see TERM=screen (tmux turns that
        # into VT102 for the Compaq); override with SCREENTEST_TERM.
        env = dict(os.environ, TERM=os.environ.get("SCREENTEST_TERM", "screen"),
                   LANG="C", LC_ALL="C")
        os.execvpe(command[0], command, env)

    screen = pyte.Screen(80, 24)
    stream = pyte.ByteStream(screen)
    raw = bytearray()

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    return
                raw.extend(data)
                stream.feed(data)

    pump(args.wait)
    for keys in args.keys:
        os.write(fd, codecs.decode(keys, "unicode_escape").encode("latin-1"))
        pump(args.wait)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    print("+" + "-" * 80 + "+")
    for line in screen.display:
        print("|" + line + "|")
    print("+" + "-" * 80 + "+")
    high = sorted({b for b in raw if b > 127})
    print(f"{len(raw)} bytes, about {len(raw) / 960:.1f} s at 9600 baud; "
          f"non-ASCII bytes: {[hex(b) for b in high[:10]] if high else 'none'}")


if __name__ == "__main__":
    main()
