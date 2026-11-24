"""The shared session's screen as the Compaq's own text mode holds it, for
when PILINK is the Compaq's terminal (PI.BAT): the serial bridge feeds this
the VT102 bytes it would have sent Kermit, and sends the Compaq the cells
that changed (pilink.TEXT_80, through pilink.TextEncoder).

Each of the session's 24 rows becomes a row of 80 cells, a character in the
PC's own code page 437 (so tmux's line drawing comes out as real lines) and
an attribute: plain, bright (bold), reversed or blinking. The 25th row,
which the session doesn't have, stays dark.
"""

import numpy as np
import pyte

import pilink

COLS, ROWS = 80, 24
HIDDEN = (25, 0)          # a cursor row past the screen's last: no cursor
PLAIN, BRIGHT, REVERSED, BLINK = 0x07, 0x0F, 0x70, 0x80


class _Screen(pyte.Screen):
    """pyte's VT102 screen, plus blinking text (SGR 5), which this pyte
    lacks: it rides on the strikethrough flag, which nothing here uses
    (as in tv_terminal.py)."""

    def select_graphic_rendition(self, *attrs, **kwargs):
        attrs = [9 if a == 5 else 29 if a == 25 else a for a in attrs]
        super().select_graphic_rendition(*attrs, **kwargs)


_CODES = {}


def code(char):
    """A character as the PC's code page 437 has it ("?" if it hasn't)."""
    if char not in _CODES:
        try:
            encoded = char.encode("cp437")
        except UnicodeEncodeError:
            encoded = b"?"
        _CODES[char] = encoded[0] if len(encoded) == 1 else 0x3F
    return _CODES[char]


def attribute(char):
    attr = PLAIN
    if char.reverse:
        attr = REVERSED
    elif char.bold:
        attr = BRIGHT
    if char.strikethrough:
        attr |= BLINK
    return attr


class TextScreen:
    def __init__(self):
        self.screen = _Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.stream.use_utf8 = False  # (the session is plain ASCII; in UTF-8 mode pyte ignores line drawing)
        self.memory = pilink.BLANK_TEXT.copy()
        self.everything = True        # every row needs reading again
        self.dirty = True             # something changed since the Compaq was last sent it

    def feed(self, data):
        self.stream.feed(data)
        self.dirty = True

    def touch(self):
        """The Compaq needs the whole screen again (after a picture)."""
        self.dirty = True

    def cells(self):
        """The text screen's memory and the cursor, for Link.show."""
        rows = range(ROWS) if self.everything else sorted(self.screen.dirty)
        for y in rows:
            if not 0 <= y < ROWS:
                continue
            line = self.screen.buffer[y]
            base = y * COLS * 2
            for x in range(COLS):
                char = line[x]
                self.memory[base + 2 * x] = code((char.data or " ")[0])
                self.memory[base + 2 * x + 1] = attribute(char)
        self.screen.dirty.clear()
        self.everything = self.dirty = False
        cursor = self.screen.cursor
        where = HIDDEN if cursor.hidden else (min(cursor.y, ROWS - 1), min(cursor.x, COLS - 1))
        return self.memory.copy(), where

    def rows(self):
        """The screen as text (for tests)."""
        return [self.memory[y * COLS * 2:(y + 1) * COLS * 2:2].tobytes().decode("cp437") for y in range(ROWS)]
