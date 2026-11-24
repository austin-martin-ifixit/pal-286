#!/usr/bin/env python3
"""Runs a program, translating its UTF-8 output into what a VT100 can show.

Some programs draw with Unicode characters even in an ASCII locale. This
sits between them and the Compaq: box-drawing characters become VT100 line
graphics, a few symbols become ASCII look-alikes, and anything else becomes
"?". Each character stays one column wide, so full-screen layouts hold.
Keystrokes pass through untouched.

Usage: asciify.py command [args...]
"""

import codecs
import fcntl
import os
import pty
import select
import signal
import sys
import termios
import tty

# Box-drawing characters as letters of the VT100 line-graphics set (ESC ( 0).
LINE_GRAPHICS = {
    "─": "q", "━": "q", "═": "q", "│": "x", "┃": "x", "║": "x",
    "┌": "l", "╭": "l", "╔": "l", "┐": "k", "╮": "k", "╗": "k",
    "└": "m", "╰": "m", "╚": "m", "┘": "j", "╯": "j", "╝": "j",
    "├": "t", "╠": "t", "┤": "u", "╣": "u", "┬": "w", "╦": "w",
    "┴": "v", "╩": "v", "┼": "n", "╬": "n",
}
LOOKALIKES = {
    "▲": "^", "▼": "v", "►": ">", "▶": ">", "▷": ">", "▸": ">", "→": ">",
    "◄": "<", "◀": "<", "◁": "<", "◂": "<", "←": "<", "…": ".",
    "·": ".", "•": "*", "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-",
    "—": "-", " ": " ", "©": "c", "°": "o", "×": "x",
    "█": "#", "▓": "#", "▒": ":", "░": ".", "▀": '"', "▄": "_",
    "♠": "S", "♥": "H", "♦": "D", "♣": "C", "♤": "S", "♡": "H", "♢": "D", "♧": "C",
    "▌": "|", "▐": "|", "▖": " ", "▗": " ", "▘": " ", "▝": " ",
    "▙": " ", "▛": " ", "▜": " ", "▟": " ",
}


def translate(text):
    out, graphics = [], False
    for ch in text:
        if ch in LINE_GRAPHICS:
            if not graphics:
                out.append("\x1b(0")
                graphics = True
            out.append(LINE_GRAPHICS[ch])
            continue
        if graphics:
            out.append("\x1b(B")
            graphics = False
        out.append(ch if ch < "\x80" else LOOKALIKES.get(ch, "?"))
    if graphics:
        out.append("\x1b(B")
    return "".join(out)


def write_all(fd, data):
    while data:
        data = data[os.write(fd, data):]


def main():
    command = sys.argv[1:]
    if not command:
        sys.exit(__doc__.strip())

    size = fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8)
    pid, child = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, size)
        try:
            os.execvp(command[0], command)
        except OSError:
            os._exit(127)            # (not installed: no traceback on the shared screen)

    saved = termios.tcgetattr(0)
    tty.setraw(0)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    hung_up = False
    try:
        while True:
            ready, _, _ = select.select([0, child], [], [])
            if child in ready:
                try:
                    data = os.read(child, 4096)
                except OSError:  # the program exited
                    break
                if not data:
                    break
                write_all(1, translate(decoder.decode(data)).encode("ascii"))
            if 0 in ready:
                data = os.read(0, 1024)
                if not data:
                    hung_up = True
                    break
                write_all(child, data)
    except OSError:  # the serial line went away (adapter unplugged)
        hung_up = True
    finally:
        try:
            termios.tcsetattr(0, termios.TCSAFLUSH, saved)
        except termios.error:
            pass
    if hung_up:
        # Pass the hangup on, as if the program had been on the line itself.
        try:
            os.kill(pid, signal.SIGHUP)
        except ProcessLookupError:
            pass
    _, status = os.waitpid(pid, 0)
    sys.exit(os.waitstatus_to_exitcode(status))


if __name__ == "__main__":
    main()
