#!/usr/bin/env python3
"""The office message board: short notes anyone at the Compaq or on
compaq.local can read and post, newest first, like a one-room BBS.

Kept in compaq-files/.message-board.txt as tab-separated "time, name,
message" lines; the oldest are dropped past KEEP. Everyone shares the
"desk" account, so the board asks for a name with each post.
"""

import os
import sys
import textwrap
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chat import COLS, page, to_ascii  # noqa: E402

# A hidden file: files received from the Compaq land in compaq-files and
# must not replace it (DOS can't send a name starting with a dot).
BOARD = os.path.expanduser("~/compaq-files/.message-board.txt")
KEEP = 300
LONGEST = 240   # characters per message


def load():
    try:
        with open(BOARD, errors="replace") as f:
            rows = [line.rstrip("\n").split("\t", 2) for line in f]
    except OSError:
        return []
    # (cleaned on the way in as well as on the way out: the file can be
    # edited by hand from the command line)
    return [[row[0][:40], clean(row[1], 20), clean(row[2], LONGEST)] for row in rows if len(row) == 3]


def save_post(name, text):
    rows = load() + [[time.strftime("%Y-%m-%d %H:%M"), name, text]]
    os.makedirs(os.path.dirname(BOARD), exist_ok=True)
    tmp = BOARD + ".new"
    with open(tmp, "w") as f:
        f.writelines("\t".join(row) + "\n" for row in rows[-KEEP:])
    os.replace(tmp, BOARD)


def clean(text, limit):
    """One line of printable ASCII: the Compaq can't show anything else, and a
    stray control character (an Esc, say) could scramble the shared screen."""
    text = "".join(c if " " <= c <= "~" else " " for c in to_ascii(text))
    return " ".join(text.split())[:limit]


def when(stamp):
    try:
        t = time.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return stamp
    return time.strftime("%a %d %b %I:%M %p", t).replace(" 0", " ")


def lines_for(rows):
    out = []
    for stamp, name, text in reversed(rows):
        out.append(f"  {name}, {when(stamp)}")
        out += textwrap.wrap(text, COLS - 6, initial_indent="      ", subsequent_indent="      ")
        out.append("")
    return out


def post():
    print()
    name = clean(input("  Your name: "), 20) or "Anonymous"
    text = clean(input("  Message (one line, Enter to post, empty to cancel):\n  > "), LONGEST)
    if not text:
        print("  Nothing posted.")
        return
    save_post(name, text)
    print("  Posted. Everyone sees it next time they open the board.")


def main():
    while True:
        rows = load()
        print("\033[H\033[2J", end="")   # clear the screen
        print("\n  OFFICE MESSAGE BOARD" + f"{len(rows)} messages".rjust(COLS - 22) + "\n")
        if rows:
            page(lines_for(rows))
        else:
            print("  No messages yet. Be the first to post one.\n")
        choice = input("  P: post a message   Enter: back to the menu   ").strip().lower()
        if choice == "p":
            post()
            input("  Press Enter. ")
        else:
            return


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print()
