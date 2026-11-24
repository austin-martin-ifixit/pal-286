"""PILINK: the Pi's side of its direct line to the Compaq's screen and keys.

PILINK.COM (dos/pilink.asm, which describes the protocol) runs on the
Compaq, reads the serial port itself and puts what arrives straight into
video memory. This module has:

- the screen layouts (pack, unpack): a picture's dots as the bytes of video
  memory, for the CGA's 640x200 and the Compaq plasma's own 640x400, and
  TEXT_80, the 80x25 text screen (a character and an attribute a cell);
- Encoder: turns "the screen should now look like this" into the fewest
  bytes, by remembering what the Compaq is showing and sending only what
  changed (skips, runs of one byte, and the rest as it is); TextEncoder
  does the same for text, and moves the screen up or down when it scrolled;
- Screen: PILINK itself, played in Python. The TV standing in for the
  Compaq uses it (tv_terminal.py), and the tests check the encoder against
  it and it against the real program in DOSBox;
- messages(): what PILINK says back (keys down and up, frames shown,
  trouble), picked out of the bytes from the cable.
"""

import collections
import fnmatch
import sys

import numpy as np

VERSION = 3

# Opcodes (see dos/pilink.asm).
SKIP, LIT, FILL = 0x00, 0x40, 0x80
(NOP, SEEK, LITW, FILLW, BACK, COPY, SCALE, SINK, MODE, CURSOR, OUT, IN, INT10, SOUND, BAUD, END, HELLO,
 QUIT, LEAVE, CHARS, RUN, THERE) = range(0xC0, 0xD6)
ARGS = {NOP: 0, SEEK: 2, BACK: 4, COPY: 6, SCALE: 1, MODE: 1, CURSOR: 2, OUT: 3, IN: 2, INT10: 8, SOUND: 2,
        BAUD: 2, END: 1, HELLO: 0, QUIT: 0, LEAVE: 1}   # bytes after each (LITW, FILLW, SINK and CHARS aside)
KERMIT_EXIT = 10          # LEAVE's exit code that has PI.BAT run Kermit for a file transfer
RUN_EXIT = 12             # RUN's: PI.BAT runs C:\PI\PIRUN.BAT, which PILINK has just written
RUN_MAX = 1024            # bytes of a PIRUN.BAT
# What PILINK's 'N' says went wrong (its bits), for the log.
TROUBLE = ((0x02, "a byte arrived before the last was read (overrun)"), (0x04, "parity"), (0x08, "framing"),
           (0x10, "break"), (0x01, "a command stopped halfway"), (0x20, "not a command"),
           (0x40, "test bytes wrong"), (0x80, "PILINK's buffer was full"))


def trouble(why):
    """PILINK's 'N' value in words."""
    return ", ".join(words for bit, words in TROUBLE if why & bit) or f"code {why}"
STARTED_BY_KERMIT = 2     # in the hello's flags

TEXT, CGA, PLASMA = 0x03, 0x06, 0x40              # BIOS video modes: 80x25 text, 640x200, Compaq 640x400
BANK = 0x2000                                     # graphics rows are dealt out to banks this far apart
ROW = 80                                          # bytes in a row of 640 dots
HELLO_START = b"\x1b_PL"
SPEEDS = (115200, 57600, 38400, 19200, 9600)      # what a PC's serial chip can do, fastest first


def word(n):
    return bytes((n & 0xFF, (n >> 8) & 0xFF))


def divisor(baud):
    """The serial chip's setting for a speed: 115200 divided by it."""
    return 115200 // int(baud)


class Layout:
    """How a mode's dot rows sit in video memory: dealt out in turn to
    `banks` banks, each BANK bytes on from the last (the CGA: even rows,
    then odd rows; the plasma's 640x400: four banks). With rows=2 or 4 on
    top, PILINK repeats every write one bank on (scale), so only the first
    bank's rows are sent and each is that many dots tall."""

    def __init__(self, mode, width, height, banks, wide=1, tall=1):
        self.mode, self.width, self.height, self.banks = mode, width, height, banks
        self.wide, self.tall = wide, tall                   # PILINK's scale: each dot this many wide and tall
        self.columns = width // 8                           # bytes sent per row
        self.sent_banks = banks // tall
        self.rows = height // self.sent_banks               # rows in each bank
        self.size = (self.sent_banks - 1) * (BANK // wide) + self.rows * self.columns
        self.scale = wide | tall << 4
        # Where each byte of the picture, taken row by row down the screen,
        # sits in pack()'s bytes (the rows of different banks interleaved).
        row = np.arange(height)
        starts = (row % self.sent_banks) * (BANK // wide) + (row // self.sent_banks) * self.columns
        self.sweep = (starts[:, None] + np.arange(self.columns)[None, :]).reshape(-1)

    def pack(self, dots):
        """A (height, width) array of dots (True: lit) as the bytes to send,
        laid out as PILINK will put them into video memory."""
        dots = np.asarray(dots, bool)
        if dots.shape != (self.height, self.width):
            raise ValueError(f"expected {self.width}x{self.height} dots, got {dots.shape[1]}x{dots.shape[0]}")
        return self.arrange(np.packbits(dots, axis=1))

    def arrange(self, packed):
        """The same, from rows already packed 8 dots to a byte (the leftmost
        dot the high bit): height * columns bytes."""
        packed = np.frombuffer(packed, np.uint8) if isinstance(packed, (bytes, bytearray)) else np.asarray(packed, np.uint8)
        packed = packed.reshape(self.height, self.columns)
        memory = np.zeros(self.size, np.uint8)
        for bank in range(self.sent_banks):
            start = bank * (BANK // self.wide)
            memory[start:start + self.rows * self.columns] = packed[bank::self.sent_banks].reshape(-1)
        return memory

    @property
    def frame_bytes(self):
        """Bytes in one screenful of packed rows (what arrange() takes)."""
        return self.height * self.columns

    def address(self, position):
        """Where in video memory a position in pack()'s bytes lands."""
        return position * self.wide


CGA_640 = Layout(CGA, 640, 200, 2)                # every dot of the CGA screen: 16,000 bytes
CGA_320 = Layout(CGA, 320, 200, 2, wide=2)        # dots twice as wide: 8,000 bytes
CGA_320x100 = Layout(CGA, 320, 100, 2, wide=2, tall=2)   # ...and twice as tall: 4,000
CGA_160 = Layout(CGA, 160, 100, 2, wide=4, tall=2)       # fat square dots: 2,000 bytes a screen
PLASMA_640 = Layout(PLASMA, 640, 400, 4)          # every dot the plasma has: 32,000 bytes
LAYOUTS = {"640x400": PLASMA_640, "640x200": CGA_640, "320x200": CGA_320, "320x100": CGA_320x100,
           "160x100": CGA_160}
for _name, _layout in LAYOUTS.items():
    _layout.name = _name


class TextLayout:
    """The 80x25 text screen: each cell a character (code page 437) and an
    attribute (07 plain, 0F bright, 70 reversed, +80 blinking), row by row."""
    mode, name, scale = TEXT, "text", 0x11
    width, height = 80, 25
    sent_banks, columns = 1, 160
    size = width * height * 2

    @staticmethod
    def address(position):
        return position


TEXT_80 = TextLayout()
BLANK_TEXT = np.tile(np.array([0x20, 0x07], np.uint8), TEXT_80.width * TEXT_80.height)   # a cleared text screen


class Encoder:
    """Remembers what the Compaq's video memory holds and turns each new
    screenful into the commands that change only what differs."""

    GAP = 2          # unchanged bytes this close between changed ones are sent anyway (cheaper than a skip)
    RUN = 4          # this many equal bytes are sent as a run

    def __init__(self, layout, sweep=False):
        """sweep: send changes row by row down the screen, not bank by
        bank. A bank is every other row (every fourth on the plasma), so
        bank by bank a still picture arrives as a coarse whole that then
        fills in, which suits a photo; a moving one would show two moments
        combed together, where a sweep shows one clean edge moving down.
        It costs 3 bytes for each row that changed."""
        self.layout = layout
        self.sweep = sweep and layout.sent_banks > 1
        self.shown = None            # what the Compaq shows (None: not known, send it all)
        self.sent = None             # where the last frame wrote (in memory order)
        self.doubtful = None         # bytes to send again whatever they are (doubt())

    def forget(self):
        """The Compaq's screen is no longer what we think (bytes were lost)."""
        self.shown = self.sent = self.doubtful = None

    def doubt(self):
        """Bytes were lost in the last frame, and only what it changed can be
        wrong (PILINK 3 stops before acting on anything after a loss): the
        next frame sends that again too. False if it isn't known."""
        if self.shown is None or self.sent is None:
            return False
        self.doubtful = self.sent if self.doubtful is None else self.doubtful | self.sent
        self.sent = None
        return True

    def setup(self):
        """The commands that put the Compaq in this layout's mode, cleared."""
        self.shown = np.zeros(self.layout.size, np.uint8)
        self.sent = self.doubtful = None
        return bytes((MODE, self.layout.mode, SCALE, self.layout.scale))

    def frame(self, memory):
        """The commands that make the screen show memory (from
        layout.pack). Empty if nothing changed."""
        memory = np.asarray(memory, np.uint8)
        if memory.shape != (self.layout.size,):
            raise ValueError("that isn't this layout's size")
        # "new" and "old" are the screen in the order it's sent: as it sits
        # in memory, or (sweep) row by row down the screen. where[] takes a
        # position in them back to its place in memory.
        where = self.layout.sweep if self.sweep else None
        new = memory[where] if self.sweep else memory
        if self.shown is None:
            changed = np.ones(new.size, bool)
        else:
            changed = new != (self.shown[where] if self.sweep else self.shown)
            if self.doubtful is not None:
                changed |= self.doubtful[where] if self.sweep else self.doubtful
                self.doubtful = None
            if not changed.any():
                return b""
            for gap in range(1, self.GAP + 1):          # close small gaps between changes
                near = changed[:-gap - 1] & changed[gap + 1:]
                for k in range(1, gap + 1):
                    changed[k:k + near.size] |= near
        self.shown = memory.copy()
        if self.sweep:
            self.sent = np.zeros(memory.size, bool)       # (memory has gaps between banks)
            self.sent[where] = changed
        else:
            self.sent = changed.copy()

        # Cut the screen into stretches: unchanged, or changed with one byte
        # value. A changed stretch of RUN or more is a run; shorter ones
        # next to each other join into one "as it is" stretch. (In a sweep
        # no stretch runs on from one row into the next: they're in
        # different places in memory.)
        edge = np.empty(new.size, bool)
        edge[0] = True
        edge[1:] = (new[1:] != new[:-1]) | (changed[1:] != changed[:-1])
        if self.sweep:
            edge[::self.layout.columns] = True
        starts = np.flatnonzero(edge)
        lengths = np.diff(np.append(starts, new.size))
        kind = np.where(changed[starts], np.where(lengths >= self.RUN, 2, 1), 0)   # 0 skip, 1 as is, 2 run
        join = np.empty(starts.size, bool)
        join[0] = True
        join[1:] = (kind[1:] != kind[:-1]) | (kind[1:] == 2)
        if self.sweep:
            join |= starts % self.layout.columns == 0
        firsts = np.flatnonzero(join)
        starts, kind = starts[firsts], kind[firsts]
        ends = np.append(starts[1:], new.size)
        places = where[starts] if self.sweep else starts

        data = new.tobytes()
        out = bytearray()
        here = None                   # where PILINK's "here" is, in memory (None: must seek)
        for start, end, what, place in zip(starts.tolist(), ends.tolist(), kind.tolist(), places.tolist()):
            if what == 0:
                continue
            if here != place:
                if here is not None and 0 < place - here <= 128:
                    skip = place - here
                    while skip:
                        n = min(64, skip)
                        out.append(SKIP + n - 1)
                        skip -= n
                else:
                    out += bytes((SEEK,)) + word(self.layout.address(place))
            n = end - start
            here = place + n
            if what == 2:
                value = data[start]
                if n > 128:
                    out += bytes((FILLW,)) + word(n) + bytes((value,))
                else:
                    while n:
                        m = min(64, n)
                        out += bytes((FILL + m - 1, value))
                        n -= m
            elif n > 128:
                out += bytes((LITW,)) + word(n) + data[start:end]
            else:
                at = start
                while n:
                    m = min(64, n)
                    out.append(LIT + m - 1)
                    out += data[at:at + m]
                    at, n = at + m, n - m
        return bytes(out)


class TextEncoder:
    """Encoder for the text screen: the cells that changed go as runs of
    characters in one attribute (CHARS, a byte a character), a long run of
    one cell as that cell copied along (BACK), and when the text scrolled,
    the screen is moved first (COPY) so only the new lines go."""

    GAP = 2          # unchanged cells this close between changed ones are sent anyway
    RUN = 12         # this many equal cells in a row are sent as one, copied along
    SCROLL_GAIN = 3  # rows a move must save to be worth it

    def __init__(self, layout=None, sweep=False):
        self.layout = TEXT_80
        self.sweep = False
        self.shown = None

    def forget(self):
        self.shown = None

    def setup(self):
        self.shown = BLANK_TEXT.copy()          # (setting the mode clears the screen to this)
        return bytes((MODE, TEXT, SCALE, 0x11))

    def scroll(self, new):
        """If the text moved up or down, the COPY that moves it, and what
        the screen then shows; else (b"", None)."""
        width = self.layout.columns
        rows = self.layout.height - 1                       # (the last row is never the session's)
        old = self.shown[:rows * width].reshape(rows, width)
        want = new[:rows * width].reshape(rows, width)
        same_now = int((old == want).all(1).sum())
        best, best_gain = None, self.SCROLL_GAIN - 1
        for shift in range(1 - rows, rows):
            if shift == 0:
                continue
            moved = old.copy()
            if shift > 0:                                   # up: row r shows what row r + shift did
                moved[:rows - shift] = old[shift:]
            else:
                moved[-shift:] = old[:rows + shift]
            gain = int((moved == want).all(1).sum()) - same_now
            if gain > best_gain:
                best, best_gain = (shift, moved), gain
        if best is None:
            return b"", None
        shift, moved = best
        count = (rows - abs(shift)) * width
        src, dst = (shift * width, 0) if shift > 0 else (0, -shift * width)
        after = self.shown.copy()
        after[:rows * width] = moved.reshape(-1)
        return bytes((COPY,)) + word(src) + word(dst) + word(count), after

    def frame(self, memory):
        memory = np.asarray(memory, np.uint8)
        if memory.shape != (self.layout.size,):
            raise ValueError("that isn't the text screen's size")
        out = bytearray()
        if self.shown is None:
            out += self.setup()
        elif np.array_equal(memory, self.shown):
            return b""
        else:
            moved, after = self.scroll(memory)
            if after is not None:
                out += moved
                self.shown = after
        new = memory.view("<u2")
        changed = new != self.shown.view("<u2")
        if not changed.any():
            self.shown = memory.copy()
            return bytes(out)
        for gap in range(1, self.GAP + 1):                  # close small gaps between changes
            near = changed[:-gap - 1] & changed[gap + 1:]
            for k in range(1, gap + 1):
                changed[k:k + near.size] |= near
        self.shown = memory.copy()
        chars, attrs = memory[0::2], memory[1::2]
        here = None
        cells = np.flatnonzero(changed)
        breaks = np.flatnonzero(np.diff(cells) != 1) + 1
        for stretch in np.split(cells, breaks):
            start, end = int(stretch[0]), int(stretch[-1]) + 1
            place = start * 2
            if here != place:
                if here is not None and 0 < place - here <= 128:
                    skip = place - here
                    while skip:
                        n = min(64, skip)
                        out.append(SKIP + n - 1)
                        skip -= n
                else:
                    out += bytes((SEEK,)) + word(place)
            here = end * 2
            cell = start
            while cell < end:
                attr = attrs[cell]
                stop = cell + 1                             # this attribute's stretch
                while stop < end and attrs[stop] == attr:
                    stop += 1
                at = cell
                while at < stop:
                    same = at + 1                           # a run of one cell?
                    while same < stop and chars[same] == chars[at]:
                        same += 1
                    if same - at >= self.RUN:
                        out += bytes((CHARS, attr, 1, chars[at]))
                        out += bytes((BACK,)) + word(2) + word((same - at - 1) * 2)
                        at = same
                        continue
                    upto = at                               # characters until the next long run
                    while upto < stop:
                        run = upto + 1
                        while run < stop and chars[run] == chars[upto]:
                            run += 1
                        if run - upto >= self.RUN:
                            break
                        upto = run
                    while at < upto:
                        n = min(255, upto - at)
                        out += bytes((CHARS, attr, n)) + chars[at:at + n].tobytes()
                        at += n
                cell = stop
        return bytes(out)


def test_pattern(n=2048, first=0):
    """A line test: n bytes, each one more than the last, which PILINK
    checks and throws away."""
    return bytes((SINK,)) + word(n) + bytes((first + i) & 0xFF for i in range(n))


WIDE = np.zeros(256, np.uint16)       # each byte with its dots doubled, left byte first (as stored)
for _b in range(256):
    _wide = 0
    for _bit in range(8):
        if _b >> _bit & 1:
            _wide |= 3 << (2 * _bit)
    WIDE[_b] = (_wide >> 8) | ((_wide & 0xFF) << 8)       # little-endian in memory: left byte first


def widen(values, wide):
    """Bytes with every dot made `wide` (1, 2 or 4) dots wide."""
    values = np.asarray(values, np.uint8)
    for _ in range({1: 0, 2: 1, 4: 2}[wide]):
        values = WIDE[values].view(np.uint8)
    return values


class Screen:
    """PILINK, played in Python: feed() it what the Pi sends, and it keeps
    the same video memory the Compaq would and returns what PILINK would
    say back. (No keys and no clock: whoever uses it adds those.)"""

    def __init__(self, flags=0):
        self.memory = np.zeros(0x10000, np.uint8)
        self.mode = TEXT
        self.flags = flags
        self.here = 0
        self.wide = self.tall = 1
        self.pending = b""
        self.cursor = (0, 0)
        self.speed = None             # a change of speed asked for (the divisor), for whoever cares
        self.sound = 0
        self.quit = False
        self.exit_code = None
        self.changed = True           # the picture changed since someone last looked
        self.linked = False           # the Pi has spoken (until then only a command counts)
        self.files = set()            # DOS names THERE finds (upper case; tests fill it in)
        self.can_run = False          # does RUN work (the TV standing in has no DOS to run)
        self.ran = None               # the PIRUN.BAT that RUN wrote

    def hello(self):
        return HELLO_START + bytes((VERSION + 0x20, self.flags + 0x20, self.mode + 0x20)) + b"\x1b\\"

    def put(self, values):
        """Bytes onto the screen here, widened and repeated as the scale says."""
        values = widen(values, self.wide)
        end = self.here + values.size
        if end > 0x10000:                                   # (off the end of the segment: wraps)
            values = values[:0x10000 - self.here]
            end = 0x10000
        self.memory[self.here:end] = values
        if self.tall == 2:
            low, high = self.here + BANK, min(0x10000, end + BANK)
            self.memory[low:high] = values[:max(0, high - low)]
        self.here = end & 0xFFFF
        self.changed = True

    def feed(self, data):
        """Takes bytes from the Pi; returns PILINK's answers."""
        p = self.pending + bytes(data)
        out = bytearray()
        i, n = 0, len(p)
        while i < n and not self.quit:
            op = p[i]
            if not self.linked and op < 0xC0:           # (text for Kermit: ignored)
                i += 1
                continue
            self.linked = True
            if op < 0x40:
                self.here = (self.here + (op + 1) * self.wide) & 0xFFFF
                i += 1
            elif op < 0x80:
                count = op - 0x3F
                if i + 1 + count > n:
                    break
                self.put(np.frombuffer(p, np.uint8, count, i + 1))
                i += 1 + count
            elif op < 0xC0:
                if i + 2 > n:
                    break
                self.put(np.full(op - 0x7F, p[i + 1], np.uint8))
                i += 2
            elif op == CHARS:
                if i + 3 > n:
                    break
                count = p[i + 2]
                if i + 3 + count > n:
                    break
                end = min(0x10000, self.here + 2 * count)
                cells = (end - self.here) // 2
                self.memory[self.here:end:2] = np.frombuffer(p, np.uint8, cells, i + 3)
                self.memory[self.here + 1:end:2] = p[i + 1]
                self.here = end & 0xFFFF
                self.changed = True
                i += 3 + count
            elif op in (LITW, SINK, RUN, THERE):
                if i + 3 > n:
                    break
                count = p[i + 1] | p[i + 2] << 8
                if i + 3 + count > n:
                    break
                body = np.frombuffer(p, np.uint8, count, i + 3)
                i += 3 + count
                if op == LITW:
                    self.put(body)
                elif op == RUN:
                    if self.can_run and 0 < count <= RUN_MAX:
                        self.ran, self.quit, self.exit_code = body.tobytes(), True, RUN_EXIT
                        out += b"Q\x00"
                    else:
                        out += b"E\x01"
                elif op == THERE:
                    name = body.tobytes().decode("cp437").upper()
                    out += b"F\x01" if any(fnmatch.fnmatchcase(f, name) for f in self.files) else b"F\x00"
                elif count and (np.diff(body.astype(np.int16)) % 256 != 1).any():
                    out += b"N\x40R\x00"
            elif op == FILLW:
                if i + 4 > n:
                    break
                self.put(np.full(p[i + 1] | p[i + 2] << 8, p[i + 3], np.uint8))
                i += 4
            elif op in ARGS:
                size = ARGS[op]
                if i + 1 + size > n:
                    break
                a = p[i + 1:i + 1 + size]
                i += 1 + size
                if op == SEEK:
                    self.here = a[0] | a[1] << 8
                elif op == BACK:
                    back, count = a[0] | a[1] << 8, a[2] | a[3] << 8
                    for _ in range(count):                  # (a byte at a time: a short "back" repeats)
                        self.memory[self.here] = self.memory[(self.here - back) & 0xFFFF]
                        self.here = (self.here + 1) & 0xFFFF
                    self.changed = True
                elif op == COPY:
                    src, dst, count = (a[k] | a[k + 1] << 8 for k in (0, 2, 4))
                    count = min(count, 0x10000 - max(src, dst))
                    self.memory[dst:dst + count] = self.memory[src:src + count].copy()
                    self.here = (dst + count) & 0xFFFF
                    self.changed = True
                elif op == SCALE:
                    if a[0] & 15 not in (1, 2, 4) or a[0] >> 4 not in (1, 2):
                        out += b"N\x20R\x00"
                        self.wide = self.tall = 1          # (PILINK sets its scale back after trouble)
                    else:
                        self.wide, self.tall = a[0] & 15, a[0] >> 4
                elif op == MODE:
                    if a[0] in (TEXT, CGA, PLASMA, 0x02, 0x04, 0x05):
                        self.mode = a[0]
                        self.memory[:] = 0
                        if a[0] in (TEXT, 0x02):                    # (the BIOS clears text to blanks)
                            self.memory[:0x4000] = np.tile(BLANK_TEXT[:2], 0x2000)
                    self.here, self.wide, self.tall, self.changed = 0, 1, 1, True
                    out += bytes((ord("M"), self.mode))
                elif op == CURSOR:
                    self.cursor = (a[0], a[1])
                    self.changed = True
                elif op == IN:
                    out += b"I\xff"
                elif op == INT10:
                    out += b"V\x00v\x00"
                elif op == SOUND:
                    self.sound = a[0] | a[1] << 8
                elif op == BAUD:
                    self.speed = a[0] | a[1] << 8
                    out += bytes((ord("B"), a[0]))
                elif op == END:
                    out += bytes((ord("A"), a[0]))
                elif op == HELLO:
                    out += self.hello()
                elif op in (QUIT, LEAVE):
                    out += b"Q\x00"
                    self.quit = True
                    self.exit_code = a[0] if op == LEAVE else 0
            else:
                out += b"N\x20R\x00"
                self.wide = self.tall = 1
                i = n
        self.pending = p[i:]
        return bytes(out)

    def text(self):
        """The text screen's 25 rows, as plain text (for tests)."""
        return [self.memory[row * 160:row * 160 + 160:2].tobytes().decode("cp437") for row in range(25)]

    def dots(self):
        """The screen as PILINK's graphics modes show it: a (rows, 640)
        array of dots, 200 rows for the CGA mode and 400 for the plasma's."""
        banks = 4 if self.mode == PLASMA else 2
        rows = 100
        picture = np.zeros((rows * banks, 640), bool)
        for bank in range(banks):
            raw = self.memory[bank * BANK:bank * BANK + rows * ROW].reshape(rows, ROW)
            picture[bank::banks] = np.unpackbits(raw, axis=1).astype(bool)
        return picture


def messages(buffer):
    """Picks PILINK's messages out of buffer (a bytearray of bytes from the
    cable, which it empties as far as it can): a list of (letter, value),
    with a hello as ("H", (version, flags, mode)). Bytes that are neither
    are dropped (line noise, or Kermit's leavings)."""
    found = []
    i = 0
    while i < len(buffer):
        if buffer[i] == 0x1b:
            if len(buffer) - i < 9:
                if HELLO_START.startswith(bytes(buffer[i:i + 4])) or bytes(buffer[i:i + 4]) == HELLO_START:
                    break                                   # (the rest is on its way)
                i += 1
                continue
            if bytes(buffer[i:i + 4]) == HELLO_START and bytes(buffer[i + 7:i + 9]) == b"\x1b\\":
                found.append(("H", tuple(b - 0x20 for b in buffer[i + 4:i + 7])))
                i += 9
                continue
            i += 1
            continue
        if chr(buffer[i]) in "KANRMIVvBQEF":
            if i + 2 > len(buffer):
                break
            found.append((chr(buffer[i]), buffer[i + 1]))
            i += 2
            continue
        i += 1
    del buffer[:i]
    return found


# ---------------------------------------------------------------- keys

MENU_KEY = b"\x1c"        # Ctrl-\: the shared session's "back to the main menu" (tmux.conf)
PLAIN, SHIFTED = {}, {}   # scancode: the character its key types
for _first, _plain, _shifted in ((0x02, "1234567890-=", "!@#$%^&*()_+"), (0x10, "qwertyuiop[]", "QWERTYUIOP{}"),
                                 (0x1E, "asdfghjkl;'`", 'ASDFGHJKL:"~'), (0x2B, "\\zxcvbnm,./", "|ZXCVBNM<>?"),
                                 (0x39, " ", " ")):
    for _i, (_a, _b) in enumerate(zip(_plain, _shifted)):
        PLAIN[_first + _i], SHIFTED[_first + _i] = _a, _b
# Keys that send the same whatever Shift does: what a VT102 (and tmux) expects.
OTHER = {0x01: b"\x1b", 0x0E: b"\x7f", 0x0F: b"\t", 0x1C: b"\r", 0x37: b"*", 0x4A: b"-", 0x4E: b"+",
         0x3B: b"\x1bOP", 0x3C: b"\x1bOQ", 0x3D: b"\x1bOR", 0x3E: b"\x1bOS", 0x3F: b"\x1b[15~",
         0x40: b"\x1b[17~", 0x41: b"\x1b[18~", 0x42: b"\x1b[19~", 0x43: b"\x1b[20~", 0x44: MENU_KEY,
         0x47: b"\x1b[1~", 0x48: b"\x1b[A", 0x49: b"\x1b[5~", 0x4B: b"\x1b[D", 0x4D: b"\x1b[C",
         0x4F: b"\x1b[4~", 0x50: b"\x1b[B", 0x51: b"\x1b[6~", 0x52: b"\x1b[2~", 0x53: b"\x1b[3~"}
SHIFTS, CTRL, ALT, CAPS = (0x2A, 0x36), 0x1D, 0x38, 0x3A
EXTENDED = 0x100          # added to a key's number when the keyboard marks it E0 (the grey arrows, right Ctrl)


class Keyboard:
    """Follows the Compaq's keyboard through the scancodes PILINK passes on:
    which keys are down, and what each press would have typed at a
    terminal."""

    def __init__(self):
        self.down = set()
        self.caps = False
        self.extended = False
        self.skip = 0

    def feed(self, code):
        """One scancode. Returns (key, down?, what it types as bytes), or
        None for a byte that is only part of a longer code. key is the
        scancode without its release bit, plus EXTENDED for E0 keys."""
        if self.skip:
            self.skip -= 1
            return None
        if code == 0xE0:
            self.extended = True
            return None
        if code == 0xE1:                       # Pause: two more bytes follow, and it types nothing
            self.skip = 2
            return None
        extended, self.extended = self.extended, False
        number, pressed = code & 0x7F, not code & 0x80
        if extended and number in SHIFTS:      # (the keyboard's own pretend Shifts around grey keys)
            return None
        key = number | (EXTENDED if extended else 0)
        if not pressed:
            self.down.discard(key)
            return key, False, b""
        held = key in self.down                # (a held key repeats its press)
        self.down.add(key)
        if number == CAPS and not held:
            self.caps = not self.caps
        return key, True, self.types(number)

    def types(self, number):
        shift = any(k in self.down for k in SHIFTS)
        ctrl = CTRL in self.down or CTRL | EXTENDED in self.down
        alt = ALT in self.down or ALT | EXTENDED in self.down
        if number in OTHER:
            out = OTHER[number]
        elif number in PLAIN:
            ch = SHIFTED[number] if shift else PLAIN[number]
            if self.caps and ch.isalpha():
                ch = ch.swapcase()
            if ctrl and "@" <= ch.upper() <= "_":
                ch = chr(ord(ch.upper()) & 0x1F)
            elif ctrl and ch in " 2":
                ch = "\0"
            out = ch.encode("ascii")
        else:
            return b""
        return b"\x1b" + out if alt and out != MENU_KEY else out


# What the Linux console sends for its keys, as scancodes (for the TV's
# keyboard standing in for the Compaq's, see taps()).
_CONSOLE = {b"\x1b[A": 0x148, b"\x1b[B": 0x150, b"\x1b[C": 0x14D, b"\x1b[D": 0x14B, b"\x1b[1~": 0x147,
            b"\x1b[2~": 0x152, b"\x1b[3~": 0x153, b"\x1b[4~": 0x14F, b"\x1b[5~": 0x149, b"\x1b[6~": 0x151,
            b"\x1b[[A": 0x3B, b"\x1b[[B": 0x3C, b"\x1b[[C": 0x3D, b"\x1b[[D": 0x3E, b"\x1b[[E": 0x3F,
            b"\x1b[17~": 0x40, b"\x1b[18~": 0x41, b"\x1b[19~": 0x42, b"\x1b[20~": 0x43, b"\x1b[21~": 0x44,
            b"\x1b": 0x01, b"\x7f": 0x0E, b"\x08": 0x0E, b"\t": 0x0F, b"\r": 0x1C, b"\n": 0x1C,
            MENU_KEY: 0x44}
_BY_LENGTH = sorted(_CONSOLE, key=len, reverse=True)
_KEY_OF = {ch: (number, False) for number, ch in PLAIN.items()}
_KEY_OF.update({ch: (number, True) for number, ch in SHIFTED.items() if ch not in _KEY_OF})


def scancodes(key, pressed):
    """A key (as Keyboard numbers them) going down or up, as the bytes the
    keyboard would send."""
    code = (key & 0x7F) | (0 if pressed else 0x80)
    return bytes((0xE0, code)) if key & EXTENDED else bytes((code,))


def taps(typed):
    """Bytes typed at a terminal, as the keys that type them: a list of
    lists of keys, each list pressed together (Shift or Ctrl first)."""
    found, i = [], 0
    while i < len(typed):
        for sequence in _BY_LENGTH:
            if typed.startswith(sequence, i):
                found.append([_CONSOLE[sequence]])
                i += len(sequence)
                break
        else:
            ch = chr(typed[i])
            i += 1
            if ch in _KEY_OF:
                number, shift = _KEY_OF[ch]
                found.append([SHIFTS[0], number] if shift else [number])
            elif ch < " " and chr(ord(ch) + 0x60) in _KEY_OF:     # Ctrl and a letter
                found.append([CTRL, _KEY_OF[chr(ord(ch) + 0x60)][0]])
    return found


# ---------------------------------------------------------------- the link

class Link:
    """One conversation with PILINK, from asking Kermit to start it to
    handing the Compaq back: finds the fastest speed the cable and the
    Compaq manage, shows screens (only the latest wanted: a moving picture
    never queues up), and hears keys. Whoever owns it (the serial bridge)
    gives it a port to write to and the bytes that arrive, calls tick() as
    time passes, and takes its news from events:

      ("up",)                    PILINK is running and tuned: show() works
      ("shown", number or None)  the last screen sent is on the Compaq
      ("key", key, down, typed)  a key at the Compaq (see Keyboard.feed)
      ("down", why)              it's over: "stopped" (we asked), "absent"
                                 (PILINK never answered: not on that disk),
                                 "left" (Ctrl+Alt+Esc at the Compaq),
                                 "quiet" or "lost" (it stopped answering)

    PILINK can also start by itself, as the Compaq's terminal (PI.BAT): its
    hello then arrives with nobody having asked. feed() takes it up the
    same way (terminal is then True), and it stays up until the Compaq
    leaves or leave() asks it to (for a file transfer).

    port has queue(bytes), drop() (forget what's queued) and speed(baud)."""

    START = 9.0           # seconds for Kermit to load PILINK (off a floppy, perhaps) and for its hello
    STILL_HERE = 3.0      # PILINK goes back to Kermit after 15 quiet seconds: say something this often
    LAUNCH = b"\x1b_run pilink /k\x1b\\"          # Kermit runs this as a command (SET TERMINAL APC UNCHECKED)

    def __init__(self, port, base):
        self.port, self.base = port, int(base)
        self.available = None         # has the Compaq got PILINK? (None: not tried)
        self.best = None              # the fastest speed that passed its test
        self.resends = 0              # screens lost on the way and sent again whole (lost())
        self.repairs = 0              # frames that lost bytes and had just their changes sent again
        self.losses = collections.Counter()   # why bytes were lost: {why: times}
        self.logged_at, self.unlogged = -1e9, 0
        self.plasma = None            # does its BIOS do the 640x400 mode?
        self.state = "off"            # off, starting, tuning, probing, on, stopping
        self.speed = self.base
        self.events = []
        self.terminal = False         # PILINK started by itself: the Compaq's terminal
        self.version = None
        self.clear()

    def clear(self):
        self.buffer = bytearray()
        self.keyboard = Keyboard()
        self.encoder = None
        self.wanted = self.current = None      # (layout, memory): to show next; showing now
        self.in_flight = None
        self.sequence = 0
        self.frame_bytes = 0
        self.deadline = None
        self.step = None
        self.candidates = []
        self.previous = self.base
        self.recovering = self.nudged = self.stop_wanted = False
        self.setting_mode, self.after_mode = False, b""   # a mode sent, its 'M' not heard yet
        self.last_sent = 0.0
        self.cursor_at = None         # where the text cursor was last put
        self.rescale = False          # PILINK set its scale back after trouble: send it with the next frame
        self.asking = []              # THERE questions not answered yet (their names, in order)

    # ------------------------------------------------------------ for the owner

    @property
    def bps(self):
        """Bytes a second the cable carries at the speed in use."""
        return self.speed // 10

    def start(self, now):
        if self.state != "off":
            self.stop_wanted = False
            return
        self.clear()
        self.port.queue(self.LAUNCH)
        self.state, self.deadline = "starting", now + self.START

    def stop(self, now):
        """Asks PILINK to hand the Compaq back to Kermit."""
        if self.state in ("off", "stopping"):
            return
        if self.state != "on":                 # (not there yet: as soon as it is)
            self.stop_wanted = True
            return
        self.port.drop()
        self.port.queue(bytes((QUIT,)))
        self.state, self.deadline = "stopping", now + 2.0

    def leave(self, code, now):
        """Asks a PILINK that is the Compaq's terminal to go back to DOS with
        this exit code (KERMIT_EXIT: PI.BAT runs Kermit, then PILINK again).
        False if this PILINK can't (an older one, or not up)."""
        if self.state != "on" or (self.version or 1) < 2:
            return False
        self.port.drop()
        self.port.queue(bytes((LEAVE, code)))
        self.state, self.deadline = "stopping", now + 2.0
        return True

    def run(self, batch, now):
        """Asks a PILINK 3 that is the Compaq's terminal to have DOS run batch
        (a batch file's lines) and come back: it writes C:\\PI\\PIRUN.BAT and
        leaves with RUN_EXIT, and the batch ends by starting PI. Then
        ("down", "stopped") once it has gone, or ("ran", False) if the file
        couldn't be written and it stayed. False if this PILINK can't."""
        data = batch.replace("\r\n", "\n").replace("\n", "\r\n").encode("cp437", "replace")
        if self.state != "on" or (self.version or 1) < 3 or not data or len(data) > RUN_MAX:
            return False
        self.port.queue(bytes((RUN,)) + word(len(data)) + data)    # (after the frame on its way)
        self.state, self.deadline = "stopping", now + 10.0
        return True

    def there(self, name, now):
        """Asks a PILINK 3 whether a file is on the Compaq's disks (a DOS
        name, wildcards allowed): ("there", name, True or False) follows,
        or None if the answer was lost. False if it can't be asked."""
        data = name.encode("cp437", "replace")
        if self.state != "on" or (self.version or 1) < 3 or not data or len(data) > 127:
            return False
        self.asking.append(name)
        self.port.queue(bytes((THERE,)) + word(len(data)) + data)
        return True

    def show(self, layout, memory, now, sweep=False, cursor=None):
        """The screen should look like memory (layout.pack or .arrange, or
        for TEXT_80 the cells). Only the latest asked for is sent, once the
        last one has arrived. sweep: for a moving picture (see Encoder).
        cursor: (row, column) for text; a row past the last hides it."""
        self.wanted = (layout, memory, sweep, cursor)
        self.pump(now)

    def feed(self, data, now):
        """Bytes from the cable."""
        self.buffer += data
        for letter, value in messages(self.buffer):
            if letter == "K":
                key = self.keyboard.feed(value)
                if key and self.state == "on":
                    self.events.append(("key",) + key)
            elif letter == "Q":
                if self.state != "off":
                    self.down("stopped" if self.state == "stopping" else "left" if value == 1 else "quiet")
            elif self.state != "off":
                getattr(self, "heard_" + self.state)(letter, value, now)
            elif letter == "H" and not value[1] & STARTED_BY_KERMIT:
                self.adopt(value, now)

    def adopt(self, hello, now):
        """A PILINK nobody asked for said hello: the Compaq's terminal."""
        self.clear()
        self.terminal = True
        self.state = "starting"
        self.heard_starting("H", hello, now)

    def wait(self, now):
        """Seconds until tick() next has something to do (None: nothing)."""
        if self.state == "off":
            return None
        times = [t for t in (self.deadline, self.last_sent + self.STILL_HERE if self.state == "on" else None)
                 if t is not None]
        return max(0.0, min(times) - now) if times else None

    def tick(self, now):
        if self.state == "off":
            return
        if self.state == "on" and now - self.last_sent >= self.STILL_HERE:
            self.port.queue(bytes((NOP,)))
            self.last_sent = now
        if self.deadline is None or now < self.deadline:
            return
        self.deadline = None
        if self.state == "starting":           # no hello: this Compaq (or disk) has no PILINK
            self.available = False
            self.down("absent")
        elif self.state == "tuning":
            if self.step == "retreating":
                self.nudge(now)
            else:
                self.retreat(now)
        elif self.state == "probing":
            self.plasma = False
            self.up(now)
        elif self.state == "on":
            if self.recovering:
                self.nudge(now)
            elif self.setting_mode:            # no word that the mode was set
                self.lost(now, "no answer to a new mode")
                self.nudge(now)
            elif self.in_flight is not None:   # no word that the screen arrived
                self.port.drop()
                self.lost(now, "no answer to a frame")
                self.nudge(now)
        elif self.state == "stopping":
            self.down("stopped")

    # ------------------------------------------------------------ inside

    def down(self, why):
        if why == "lost" and not self.terminal:    # (in case it's still there, deaf: back to Kermit)
            self.port.queue(bytes((QUIT,)))
        if self.speed != self.base or why == "lost":
            self.port.speed(self.base)
        self.speed, self.state, self.terminal = self.base, "off", False
        self.clear()
        self.events.append(("down", why))

    def nudge(self, now):
        """Nothing heard when something was due: ask once who's there, then give up."""
        if self.nudged:
            self.down("lost")
            return
        self.nudged = True
        self.port.queue(bytes((HELLO,)))
        self.deadline = now + 3.0

    def heard_starting(self, letter, value, now):
        if letter != "H":
            return
        self.available, self.nudged, self.version = True, False, value[0]
        self.candidates = [s for s in ([self.best] if self.best else SPEEDS) if s > self.base]
        self.next_speed(now)

    def next_speed(self, now):
        if self.stop_wanted:
            return self.up(now)
        if not self.candidates:
            self.best = self.best or self.speed
            return self.probe(now)
        self.port.queue(bytes((BAUD,)) + word(divisor(self.candidates[0])))
        self.state, self.step, self.deadline = "tuning", "asked", now + 1.5

    def heard_tuning(self, letter, value, now):
        if self.step == "asked" and letter == "B":
            self.previous, self.speed = self.speed, self.candidates[0]
            self.port.speed(self.speed)
            self.port.queue(test_pattern() + bytes((END, 255)))
            self.step, self.deadline = "testing", now + 2051 * 10 / self.speed + 2.0
        elif self.step == "testing" and (letter, value) == ("A", 255):
            self.best, self.candidates, self.nudged = self.speed, [], False
            self.probe(now)
        elif letter == "H":                    # it went back to the last speed that worked
            if self.step == "testing":
                self.speed = self.previous
                self.port.drop()
                self.port.speed(self.speed)
            self.candidates.pop(0)
            self.nudged = False
            self.next_speed(now)
        elif letter in "NR" and self.step != "retreating":
            self.retreat(now)

    def retreat(self, now):
        """This speed didn't work: back to the last one, where PILINK will
        say hello again (within a couple of seconds)."""
        self.port.drop()
        if self.step == "testing":
            self.speed = self.previous
            self.port.speed(self.speed)
        self.step, self.deadline = "retreating", now + 4.0

    def probe(self, now):
        """Once per connection: does the BIOS take the plasma's 640x400 mode?"""
        if self.plasma is not None or self.stop_wanted:
            return self.up(now)
        self.port.queue(bytes((MODE, PLASMA)))
        self.state, self.deadline = "probing", now + 3.0

    def heard_probing(self, letter, value, now):
        if letter == "M":
            self.plasma = value == PLASMA
            self.up(now)

    def up(self, now):
        self.state, self.deadline, self.last_sent = "on", None, now
        if self.stop_wanted:
            self.stop_wanted = False
            return self.stop(now)
        self.events.append(("up",))
        self.pump(now)

    def heard_on(self, letter, value, now):
        if letter == "A":
            if value == self.in_flight:
                self.in_flight, self.deadline, self.nudged = None, None, False
                self.events.append(("shown", value))
                self.pump(now)
        elif letter == "M" and self.setting_mode:   # the mode is set: now the screen
            self.setting_mode, self.deadline = False, None
            self.pump(now)
        elif letter == "F" and self.asking:
            self.events.append(("there", self.asking.pop(0), bool(value)))
        elif letter == "N":                    # bytes were lost: it says R when the line is quiet
            self.port.drop()
            self.lost(now, trouble(value), partial=True)
            self.deadline = now + 3.0
        elif letter in "RH" and (self.recovering or letter == "H"):
            if letter == "H":
                self.lost(now, "PILINK started again")
            self.recovering, self.deadline, self.nudged = False, None, False
            self.pump(now)

    def lost(self, now, why, partial=False):
        """What the Compaq shows is no longer known. After an 'N' from PILINK
        3 (partial) only what the frame on its way changed can be wrong: that
        goes again with the next frame, and its scale (PILINK sets that back).
        Otherwise the whole screen goes again, mode and all: at 38400 baud
        that's 8 seconds for 640x400, which is what made video crawl."""
        self.losses[why] += 1
        self.log_loss(why, now)
        if (partial and (self.version or 1) >= 3 and isinstance(self.encoder, Encoder) and not self.setting_mode
                and self.encoder.doubt()):
            self.repairs += 1
            self.rescale = True
        else:
            self.resends += 1
            if self.encoder:
                self.encoder.forget()
        for name in self.asking:               # (questions on their way were thrown away too)
            self.events.append(("there", name, None))
        self.asking = []
        self.in_flight, self.recovering = None, True
        self.setting_mode, self.after_mode = False, b""
        self.wanted = self.wanted or self.current

    def log_loss(self, why, now):
        """A line in the bridge's log, at most one every 10 seconds."""
        self.unlogged += 1
        if now - self.logged_at < 10:
            return
        others = f" (and {self.unlogged - 1} more since the last note)" if self.unlogged > 1 else ""
        print(f"pilink: bytes lost at {self.speed} baud, in a {self.frame_bytes}-byte frame: {why}{others}",
              file=sys.stderr, flush=True)
        self.logged_at, self.unlogged = now, 0

    def heard_stopping(self, letter, value, now):
        if letter == "E":                      # RUN couldn't write its batch file: still here
            self.state, self.deadline = "on", None
            self.events.append(("ran", False))
            self.pump(now)

    def pump(self, now):
        """Sends the wanted screen, if PILINK is ready for one."""
        if (self.state != "on" or self.in_flight is not None or self.recovering or self.setting_mode
                or not self.wanted):
            return
        layout, memory, sweep, cursor = self.current = self.wanted
        self.wanted = None
        out, setup = self.after_mode, b""
        self.after_mode = b""
        if self.encoder is None or self.encoder.layout is not layout:
            self.encoder = (TextEncoder if layout is TEXT_80 else Encoder)(layout, sweep)
            setup = self.encoder.setup()
            self.cursor_at, self.rescale = None, False
        elif self.encoder.shown is None:
            setup = self.encoder.setup()       # (after lost bytes: its mode and scale again too)
            self.cursor_at, self.rescale = None, False
        if setup:
            # The mode on its own, and the rest once PILINK answers 'M': while
            # the Compaq's BIOS sets a mode it doesn't hear the line, and what
            # arrives then is lost (then asked for again, mode and all).
            self.port.queue(setup[:2])
            self.after_mode, self.wanted, self.setting_mode = setup[2:], self.current, True
            self.deadline, self.last_sent = now + 3.0, now
            return
        self.encoder.sweep = sweep and layout.sent_banks > 1
        if self.rescale:
            out += bytes((SCALE, layout.scale))
            self.rescale = False
        out += self.encoder.frame(memory)
        if cursor is not None and cursor != self.cursor_at:
            out += bytes((CURSOR, *cursor))
            self.cursor_at = cursor
        if not out:
            self.frame_bytes = 0
            self.events.append(("shown", None))
            return
        self.sequence = self.sequence % 250 + 1
        self.in_flight = self.sequence
        self.frame_bytes = len(out) + 2
        self.port.queue(out + bytes((END, self.sequence)))
        self.deadline = now + self.frame_bytes * 10 / self.speed + 3.0
        self.last_sent = now
