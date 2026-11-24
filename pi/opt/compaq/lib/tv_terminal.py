#!/usr/bin/env python3
"""The Compaq's screen on the Pi's HDMI display, until the real Compaq is
connected.

It plays the part of the Compaq at the end of its serial cable: a VT102
terminal drawn in the Compaq Portable III's own font, amber on dark like its
gas-plasma panel, 80x24 at a whole-number scale (crisp pixels), with the
keyboard plugged into the Pi typing into it. Behind it runs the same serial
bridge the Compaq will use, on a pseudo-terminal instead of a cable, so the
burn-in screen saver and PAL's eye show up here too. Pictures too, both
ways the Compaq shows them. Like MS-DOS Kermit, it understands the
Tektronix graphics mode and sixel images (see pictures.py), on a 640x200
dot screen. And when the bridge asks "Kermit" to run PILINK, the Compaq's
own fast picture program, it plays PILINK too (pilink.Screen): the same
bytes, the same video memory, 640x400 dots, and its keys reported going
down and coming up.

compaq-tv.service runs it on console 7. It draws only while that console
is the one showing, so the login prompt on console 1 (Ctrl+Alt+F1) still
works. Plugging in the Compaq's serial adapter stops it, handing over to
the real thing.

Which Compaq it plays is set in data/tv.conf: one running PI.BAT (TERMINAL=pi,
PILINK as its whole terminal: it says hello by itself, and everything,
text included, arrives as PILINK's commands into its video memory, drawn
here from its text mode's cells) or one running Kermit (TERMINAL=kermit).

How big it draws is set in data/tv.conf too: the Compaq's own size (real; the
screen is drawn dot for dot off screen, then shrunk or grown to the size
of the Compaq's 10-inch panel on this TV), one TV pixel per dot (dot), or
as big as the TV allows (fill). F12 on the TV's keyboard switches between
filling the TV and the Compaq's real size (until the next restart).
"""

import fcntl
import mmap
import os
import pty
import re
import select
import signal
import subprocess
import sys
import termios
import time
import tty

import numpy as np
import pyte
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pilink  # noqa: E402

FONT = "/opt/compaq/web/vendor/Compaq_Port3.woff"   # VileR's Compaq Portable III font, CC BY-SA
SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/tv.conf")
BRIDGE = "/opt/compaq/lib/serial_bridge.py"
COLS, ROWS = 80, 24
KDSETMODE, KD_TEXT, KD_GRAPHICS = 0x4B3A, 0x00, 0x01

# The panel's colours: amber light on a dark brown-black glass.
GLASS = np.array([16, 6, 0], np.float32)
AMBER = np.array([235, 130, 18], np.float32)
BRIGHT = np.array([255, 186, 66], np.float32)   # bold: the plasma's high intensity


GW, GH = 640, 200                 # Kermit's graphics screen on the Compaq, in dots
TEK_W, TEK_H = 1024, 780          # Tektronix coordinates (0,0 at the bottom left)
ENTER, LEAVE = b"\x1b\x0c", b"\x1b[?38l"
CSI = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")
COMMAND, COMMAND_END = b"\x1b_", b"\x1b\\"   # a command for Kermit itself (an APC string)
HOLD = 0.3                        # s a typed key counts as held down, for PILINK's sake (see main)
SIZE_KEY = b"\x1b[24~"            # F12 on the console: fill the TV, or the Compaq's real size


def paint_dots(display, dots):
    """A screen of dots (200 or 400 rows of 640) on the TV, in the panel's
    amber: the plasma's whole 640x400, centred, when the TV has room for
    it, else squeezed into the text's 24 rows."""
    width, height = display.cw * COLS, display.ch * 25
    top = display.top - display.ch // 2
    if top < 0 or top + height > display.height:
        height, top = display.ch * ROWS, display.top
    rows = np.arange(height) * dots.shape[0] // height
    cols = np.arange(width) * dots.shape[1] // width
    lit = dots[rows][:, cols]
    amber, glass = display.colour(AMBER[None, None, :]), display.colour(GLASS[None, None, :])
    display.pixels[top:top + height, display.left:display.left + width] = np.where(lit, amber, glass)
    display.dirty = True


class Graphics:
    """Kermit's graphics mode, played on the TV as on the Compaq: Tektronix
    lines and text, and DEC sixel pictures. Only what pictures.py sends has
    to work, and does."""

    def __init__(self, display):
        self.display = display
        self.on = False
        self.dots = np.zeros((GH, GW), bool)
        self.pending = b""
        self.x = self.y = 0            # dots: where the next picture band or letter goes
        self.vectors = False           # drawing lines (after GS) or writing text (after US)
        self.first = True              # the first point after GS moves; the rest draw
        self.dirty = False
        self.font = ImageFont.truetype(FONT, 16)
        self.letters = {}

    def enter(self):
        self.on = True
        self.clear()

    def clear(self):
        self.dots[:] = False
        self.x, self.y = 0, 6          # (Kermit's home: the first text line's baseline)
        self.dirty = True

    def feed(self, data):
        """Bytes while in graphics mode. Returns whatever came after the
        switch back to text (b"" while still in graphics)."""
        self.pending += data
        while self.pending:
            p = self.pending
            if p[0] == 0x1b:
                if len(p) < 2:
                    return b""
                if p[1] == 0x0c:                     # ESC FF: clear
                    self.clear()
                    self.pending = p[2:]
                elif p[1] == ord("P"):               # a sixel picture, up to ESC backslash
                    end = p.find(b"\x1b\\")
                    if end < 0:
                        if len(p) > 4_000_000:
                            self.pending = b""
                        return b""
                    self.sixel(p[2:end])
                    self.pending = p[end + 2:]
                elif p[1] == ord("["):
                    if p.startswith(LEAVE):
                        self.on, rest, self.pending = False, p[len(LEAVE):], b""
                        return rest
                    match = CSI.match(p)
                    if not match:
                        if len(p) < 16:
                            return b""               # (the rest is on its way)
                        self.pending = p[2:]
                        continue
                    self.pending = p[match.end():]
                else:
                    self.pending = p[2:]
                continue
            byte = p[0]
            if byte == 0x1d:                         # GS: lines (the first point moves)
                self.vectors, self.first = True, True
                self.pending = p[1:]
            elif byte == 0x1f:                       # US: text
                self.vectors = False
                self.pending = p[1:]
            elif self.vectors:
                if len(p) < 4:
                    return b""
                if not all(0x20 <= c < 0x80 for c in p[:4]):
                    self.pending = p[1:]
                    continue
                hy, ly, hx, lx = p[:4]
                tx, ty = ((hx - 0x20) << 5) | (lx - 0x40), ((hy - 0x20) << 5) | (ly - 0x60)
                x, y = round(tx * GW / TEK_W), round(GH - 1 - ty * GH / TEK_H)
                if not self.first:
                    self.line(self.x, self.y, x, y)
                self.x, self.y, self.first = x, y, False
                self.pending = p[4:]
            else:
                if 0x20 <= byte < 0x7f:
                    self.letter(chr(byte))
                self.pending = p[1:]
        return b""

    def sixel(self, body):
        """Draws a sixel image the way MS-DOS Kermit does (see pictures.py):
        the first band 8 rows above the cursor, the rest down the left edge,
        and the last band left out."""
        start = body.find(b"q")
        data = body[start + 1:] if start >= 0 else b""
        bands = data.split(b"-")
        if bands and not bands[-1]:
            bands.pop()
        if len(bands) > 1:
            bands.pop()
        data = b"-".join(bands)
        x, y, colour, i = self.x, self.y - 8, 1, 0
        while i < len(data):
            c = data[i]
            i += 1
            count = 1
            if c in b'"#':                          # raster attributes or a colour
                j = i
                while j < len(data) and (48 <= data[j] <= 57 or data[j] == 59):
                    j += 1
                if c == ord("#"):
                    numbers = data[i:j].split(b";")
                    if len(numbers) == 1 and numbers[0]:
                        colour = int(numbers[0])
                i = j
                continue
            if c == ord("!"):
                j = i
                while j < len(data) and 48 <= data[j] <= 57:
                    j += 1
                count = int(data[i:j] or b"1")
                c, i = (data[j], j + 1) if j < len(data) else (63, j)
            if c == ord("$"):
                x = 0
            elif c == ord("-"):
                x, y = 0, y + 6               # (each band after the first starts at the left edge)
            elif 63 <= c <= 126:
                bits = c - 63
                top = max(0, y)
                if bits and colour and top < GH:
                    for k in range(6):
                        if bits >> k & 1 and top + k < GH:
                            self.dots[top + k, x:min(GW, x + count)] = True
                x += count
        self.x, self.y = 0, min(GH - 1, y)
        self.dirty = True

    def line(self, x0, y0, x1, y1):
        steps = max(abs(x1 - x0), abs(y1 - y0), 1)
        for t in range(steps + 1):
            x, y = round(x0 + (x1 - x0) * t / steps), round(y0 + (y1 - y0) * t / steps)
            if 0 <= x < GW and 0 <= y < GH:
                self.dots[y, x] = True
        self.dirty = True

    def letter(self, char):
        """A letter 8 dots wide and 8 high, sitting on the current line."""
        if char not in self.letters:
            image = Image.new("L", (8, 16))
            ImageDraw.Draw(image).text((0, 0), char, fill=255, font=self.font)
            self.letters[char] = np.asarray(image, np.float32)[::2] > 128
        top = self.y - 7
        if 0 <= top and self.x + 8 <= GW:
            self.dots[top:top + 8, self.x:self.x + 8] |= self.letters[char]
        self.x += 8
        self.dirty = True

    def render(self, force=False):
        """The dot screen on the TV, over the text area, in the panel's amber."""
        if not (self.dirty or force):
            return
        paint_dots(self.display, self.dots)
        self.dirty = False


class Screen(pyte.Screen):
    """pyte's VT102 screen, plus blinking text (SGR 5), which this pyte
    lacks: it rides on the strikethrough flag, which nothing here uses."""

    def select_graphic_rendition(self, *attrs, **kwargs):
        attrs = [9 if a == 5 else 29 if a == 25 else a for a in attrs]
        super().select_graphic_rendition(*attrs, **kwargs)


def settings():
    """data/tv.conf: TERMINAL, SIZE, TV_WIDTH_MM, COMPAQ_MM."""
    found = {"TERMINAL": "pi", "SIZE": "fill", "TV_WIDTH_MM": "0", "COMPAQ_MM": "215x135"}
    try:
        with open(SETTINGS) as f:
            for line in f:
                key, _, value = line.partition("=")
                if value and not key.strip().startswith("#"):
                    found[key.strip()] = value.split("#")[0].strip()
    except OSError:
        pass
    return found


class Display:
    """The HDMI framebuffer, drawn a character cell at a time. At the
    Compaq's own size (data/tv.conf), cells are drawn dot for dot into a
    640x400 screen of our own (native), which present() then fits onto the
    TV at the real size."""

    native = None                 # (the TV's own framebuffer then: tv)
    dirty = False

    def __init__(self, path="/dev/fb0"):
        info = "/sys/class/graphics/" + os.path.basename(path) + "/"
        self.width, self.height = (int(v) for v in open(info + "virtual_size").read().split(","))
        self.depth = int(open(info + "bits_per_pixel").read())
        stride = int(open(info + "stride").read())
        self.fd = os.open(path, os.O_RDWR)
        self.map = mmap.mmap(self.fd, stride * self.height)
        dtype = np.uint16 if self.depth == 16 else np.uint32
        self.pixels = np.ndarray((self.height, stride // dtype().itemsize), dtype, self.map)
        self.font = ImageFont.truetype(FONT, 16)
        self.fb = (self.pixels, self.width, self.height, self.depth)
        self.wanted = settings()
        self.set_size(self.wanted["SIZE"])

    def set_size(self, size):
        """real, dot or fill (see data/tv.conf). The caller clears and
        redraws."""
        self.pixels, self.width, self.height, self.depth = self.fb
        self.native = None
        # Whole-number scale of the Compaq's 640x384 text area, centred.
        self.scale = max(1, min(self.width // (8 * COLS), self.height // (16 * ROWS)))
        if size == "dot":
            self.scale = 1
        elif size != "real" or not self.real_size(self.wanted):
            size = "fill"
        self.size = size
        self.cw, self.ch = 8 * self.scale, 16 * self.scale
        self.left = (self.width - self.cw * COLS) // 2
        self.top = (self.height - self.ch * ROWS) // 2
        self.cache = {}                              # (cells drawn at the old size)

    def real_size(self, wanted):
        """Draws at the Compaq's own size: into a 640x400 screen of our own,
        which present() fits onto the TV as many TV pixels across as the
        Compaq's panel is millimetres wide, times the TV's pixels a
        millimetre. False if tv.conf doesn't give the sizes."""
        try:
            tv_mm = float(wanted["TV_WIDTH_MM"])
            compaq_w, compaq_h = (float(v) for v in wanted["COMPAQ_MM"].lower().split("x"))
        except ValueError:
            return False
        if tv_mm <= 0:
            return False
        per_mm = self.width / tv_mm                  # (TV pixels are square)
        size = (min(self.width, round(compaq_w * per_mm)), min(self.height, round(compaq_h * per_mm)))
        self.tv, self.tv_depth, self.native_size = self.pixels, self.depth, size
        self.tv_at = ((self.height - size[1]) // 2, (self.width - size[0]) // 2)
        self.width, self.height, self.depth, self.scale = 640, 400, 32, 1
        self.native = self.pixels = np.zeros((400, 640), np.uint32)
        return True

    def present(self):
        """At the real size: the screen of our own onto the TV, fitted (each
        TV pixel the average of the dots it covers)."""
        if self.native is None or not self.dirty:
            return
        self.dirty = False
        p = self.native
        rgb = np.stack([(p >> 16) & 255, (p >> 8) & 255, p & 255], -1).astype(np.uint8)
        fitted = np.asarray(Image.fromarray(rgb).resize(self.native_size, Image.BOX), np.uint32)
        r, g, b = fitted[..., 0], fitted[..., 1], fitted[..., 2]
        out = ((((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).astype(np.uint16) if self.tv_depth == 16
               else (r << 16) | (g << 8) | b)
        y, x = self.tv_at
        self.tv[y:y + out.shape[0], x:x + out.shape[1]] = out

    def colour(self, rgb):
        r, g, b = (rgb[..., i].astype(np.uint32) for i in range(3))
        if self.depth == 16:
            return (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).astype(np.uint16)
        return (r << 16) | (g << 8) | b

    def clear(self):
        self.pixels[:, :] = self.colour(GLASS[None, None, :])
        if self.native is not None:              # (the TV around the Compaq's screen: dark)
            self.tv[:, :] = 0
        self.dirty = True

    def glyph(self, char, bright, reverse, underline, cursor):
        """One cell's pixels, made once and kept."""
        key = (char, bright, reverse, underline, cursor)
        if key in self.cache:
            return self.cache[key]
        image = Image.new("L", (8, 16))
        if char.strip():
            ImageDraw.Draw(image).text((0, 0), char, fill=255, font=self.font)
        dots = np.asarray(image, np.float32) / 255 > 0.5
        if underline:
            dots[15, :] = True
        if cursor:
            dots[14:16, :] = ~dots[14:16, :] if reverse else True
        if reverse:
            dots = ~dots
        s = self.scale
        lit = np.repeat(np.repeat(dots, s, 0), s, 1).astype(np.float32)
        # Each dot's lower row a little dimmer, like the panel's fine lines,
        # and a soft glow around the lit dots.
        if s > 1:
            lit[s - 1::s, :] *= 0.72
        glow = np.asarray(Image.fromarray((lit * 255).astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(s * 0.8)), np.float32) / 255
        level = np.clip(lit + 0.3 * glow, 0, 1)[..., None]
        fg = BRIGHT if bright else AMBER
        pixels = self.colour(GLASS + level * (fg - GLASS))
        self.cache[key] = pixels
        return pixels

    def put(self, x, y, pixels):
        top, left = self.top + y * self.ch, self.left + x * self.cw
        self.pixels[top:top + self.ch, left:left + self.cw] = pixels
        self.dirty = True


class Terminal:
    """Draws the pyte screen onto the display, redrawing only what changed."""

    def __init__(self, display):
        self.display = display
        self.screen = Screen(COLS, ROWS)
        self.stream = pyte.ByteStream(self.screen)
        self.stream.use_utf8 = False  # (the session is plain ASCII; in UTF-8 mode pyte ignores line drawing)
        self.blink_on = True
        self.blinking_rows = set()
        self.cursor_at = None

    def feed(self, data):
        self.stream.feed(data)

    def draw_row(self, y):
        row = self.screen.buffer[y]
        cursor = self.screen.cursor
        blinking = False
        for x in range(COLS):
            char = row[x]
            hidden = char.strikethrough and not self.blink_on
            blinking |= char.strikethrough
            at_cursor = (x, y) == (cursor.x, cursor.y) and not cursor.hidden and self.blink_on
            self.display.put(x, y, self.display.glyph(
                " " if hidden else (char.data or " ")[0], char.bold, char.reverse,
                char.underscore, at_cursor))
        if blinking:
            self.blinking_rows.add(y)
        else:
            self.blinking_rows.discard(y)

    def update(self, everything=False):
        rows = set(range(ROWS)) if everything else set(self.screen.dirty)
        cursor = (min(self.screen.cursor.x, COLS - 1), self.screen.cursor.y)
        if cursor != self.cursor_at:
            rows.add(cursor[1])
            if self.cursor_at:
                rows.add(self.cursor_at[1])
            self.cursor_at = cursor
        for y in sorted(rows):
            if 0 <= y < ROWS:
                self.draw_row(y)
        self.screen.dirty.clear()

    def blink(self):
        self.blink_on = not self.blink_on
        for y in self.blinking_rows | {self.screen.cursor.y}:
            if 0 <= y < ROWS:
                self.draw_row(y)


class TextCells:
    """PILINK's text mode, played here: the 80x25 cells (a code page 437
    character and an attribute each) in its video memory, drawn in the
    Compaq's font, and its cursor. Only cells that changed are drawn again.
    The 25th row shows where there's room for it (the session itself has
    24, so it's dark anyway)."""

    def __init__(self, display):
        self.display = display
        self.drawn = None             # (cells, cursor, blink phase) as last drawn
        self.blink_on = True

    def forget(self):
        self.drawn = None

    def area(self):
        d = self.display
        top = d.top - d.ch // 2
        if top >= 0 and top + d.ch * 25 <= d.height:
            return 25, top
        return ROWS, d.top

    def update(self, screen, everything=False):
        d = self.display
        count, top = self.area()
        cells = screen.memory[:4000].reshape(25, 80, 2)
        cursor = tuple(int(v) for v in screen.cursor)
        if everything or self.drawn is None:
            todo = [(y, x) for y in range(count) for x in range(80)]
        else:
            old_cells, old_cursor, old_blink = self.drawn
            changed = (cells != old_cells).any(axis=2)
            if old_blink != self.blink_on:
                changed |= cells[:, :, 1] >= 0x80                      # (blinking text)
            ys, xs = np.nonzero(changed[:count])
            todo = list(zip(ys.tolist(), xs.tolist())) + [old_cursor, cursor]
        for y, x in todo:
            if not (0 <= y < count and 0 <= x < 80):
                continue
            code, attr = int(cells[y, x, 0]), int(cells[y, x, 1])
            hidden = attr & 0x80 and not self.blink_on
            char = " " if hidden or code < 0x20 else bytes((code,)).decode("cp437")
            pixels = d.glyph(char, bool(attr & 0x08), attr & 0x70 == 0x70, False,
                             (y, x) == cursor and self.blink_on)
            t, left = top + y * d.ch, d.left + x * d.cw
            d.pixels[t:t + d.ch, left:left + d.cw] = pixels
            d.dirty = True
        self.drawn = (cells.copy(), cursor, self.blink_on)

    def blink(self, screen):
        self.blink_on = not self.blink_on
        self.update(screen)


def showing(console):
    """Is our console the one on the display?"""
    try:
        with open("/sys/class/tty/tty0/active") as f:
            return f.read().strip() == os.path.basename(os.ttyname(console))
    except OSError:
        return True


def start_bridge(line):
    return subprocess.Popen([sys.executable, "-I", BRIDGE, line],
                            env=dict(os.environ, COMPAQ_TV="1"))


def tell(master, key, pressed):
    """PILINK's word to the bridge that a key went down or up."""
    os.write(master, b"".join(b"K" + bytes((code,)) for code in pilink.scancodes(key, pressed)))


def press(master, keys, held):
    """Keys typed at the console, as PILINK reports them: each goes down,
    and comes up when it hasn't been typed again for a moment (a held key
    repeats). Shift and Ctrl come straight back up, or the next letter
    typed would be shifted too."""
    for chord in pilink.taps(keys):
        *modifiers, key = chord
        for k in chord:
            tell(master, k, True)
        for k in modifiers:
            tell(master, k, False)
            held.pop(k, None)
        held[key] = time.monotonic() + HOLD


def start_pi(master):
    """PI.BAT starting PILINK: its banner, and its hello (said again every
    2 seconds until the Pi answers)."""
    screen = pilink.Screen(flags=0)
    banner = b"PILINK 2: waiting for the Raspberry Pi. (Ctrl+Alt+Esc leaves.)"
    screen.memory[0:len(banner) * 2:2] = np.frombuffer(banner, np.uint8)
    screen.cursor = (1, 0)
    os.write(master, screen.hello())
    return screen


def main():
    console = sys.stdin.fileno()
    saved = termios.tcgetattr(console)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(0))
    display = Display()
    terminal = Terminal(display)
    graphics = Graphics(display)
    cells = TextCells(display)
    pi = settings()["TERMINAL"] != "kermit"   # PILINK as the whole terminal (PI.BAT), or Kermit
    carry = b""
    link = None                   # PILINK, played here while the bridge has it running (with pi, always)
    held = {}                     # keys held down on its behalf: {key: when it's let go}
    master, slave = pty.openpty()
    bridge = start_bridge(os.ttyname(slave))
    restart_at = next_hello = 0.0             # (pi: PILINK starting again, saying hello again)
    was_picture = False
    try:
        fcntl.ioctl(console, KDSETMODE, KD_GRAPHICS)   # the console stops drawing its own text
        tty.setraw(console)                            # keys arrive as the bytes a terminal sends
        display.clear()
        terminal.update(everything=True)
        next_blink = next_full = time.monotonic()
        was_showing = True
        while True:
            now = time.monotonic()
            if pi and link is None and now >= restart_at:
                link = start_pi(master)              # (as PI.BAT does, round and round)
                next_hello, was_showing = now + 2, False
                cells.forget()
            elif pi and link is not None and not link.linked and now >= next_hello:
                os.write(master, link.hello())
                next_hello = now + 2
            wakes = [next_blink] + list(held.values()) + ([next_hello] if pi and link and not link.linked else [])
            wait = min(wakes + ([restart_at] if pi and link is None else [])) - now
            ready, _, _ = select.select([master, console], [], [], max(0.0, wait))
            if master in ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    data = b""
                data = carry + data
                carry = b""
                while data:
                    if link is not None:
                        said = link.feed(data)
                        data = b""
                        if said:
                            os.write(master, said)
                        if link.quit and pi:         # back to DOS, and PI.BAT starts it again
                            link, held, restart_at = None, {}, time.monotonic() + 0.5
                            display.clear()
                        elif link.quit:              # back to "Kermit": the text, as it was
                            link, held = None, {}
                            display.clear()
                            terminal.update(everything=True)
                        continue
                    if pi:                           # (nothing to read until PILINK starts again)
                        break
                    if graphics.on:
                        data = graphics.feed(data)
                        if not graphics.on:          # back to text: show it all again
                            display.clear()
                            terminal.update(everything=True)
                        continue
                    marks = [(data.find(mark), mark) for mark in (ENTER, COMMAND)]
                    marks = [found for found in marks if found[0] >= 0]
                    if not marks:
                        if data.endswith(b"\x1b"):   # (perhaps the start of one of them)
                            data, carry = data[:-1], b"\x1b"
                        terminal.feed(data)
                        break
                    start, mark = min(marks)
                    terminal.feed(data[:start])
                    if mark == ENTER:
                        graphics.enter()
                        data = data[start + len(ENTER):]
                        continue
                    end = data.find(COMMAND_END, start)
                    if end < 0:                      # (the rest of the command is on its way)
                        carry = data[start:] if len(data) - start < 1100 else b""
                        break
                    command = data[start + len(COMMAND):end].decode("ascii", "replace").lower().split()
                    data = data[end + len(COMMAND_END):]
                    if command[:2] == ["run", "pilink"]:
                        link = pilink.Screen(flags=2)    # (2: started by Kermit)
                        os.write(master, link.hello())
            if console in ready:
                keys = os.read(console, 1024)
                if SIZE_KEY in keys and hasattr(display, "set_size"):   # the TV's size, not a key for the Compaq
                    keys = keys.replace(SIZE_KEY, b"")
                    display.set_size("real" if display.size == "fill" else "fill")
                    was_showing = False                  # (below: cleared and drawn again, whole)
                if keys and link is not None:
                    press(master, keys, held)        # (PILINK reports keys going down and coming up)
                elif keys:
                    os.write(master, keys)
            if bridge.poll() is not None:
                time.sleep(2)
                bridge = start_bridge(os.ttyname(slave))
                if link is not None:                 # (PILINK goes with it)
                    link, held = None, {}
                    display.clear()
                    if not pi:
                        terminal.update(everything=True)
            now = time.monotonic()
            for key in [key for key, until in held.items() if now >= until]:
                del held[key]
                tell(master, key, False)
            picture = link is not None and link.mode != pilink.TEXT
            if picture != was_picture:      # (into or out of a picture: all of it again)
                was_picture, was_showing = picture, False
                cells.forget()
            text = pi and link is not None and not picture       # PILINK's text mode
            if not showing(console):        # someone switched to another console
                was_showing = False
                next_blink = now + 0.5
                continue
            if not was_showing or now >= next_full:
                if not was_showing:         # back on show: another console drew here
                    display.clear()
                if picture:
                    paint_dots(display, link.dots())
                elif text:
                    link.changed = False
                    cells.update(link, everything=True)
                elif graphics.on:
                    graphics.render(force=True)
                elif not pi:
                    terminal.update(everything=True)   # (and now and then anyway)
                next_full, was_showing = now + 60, True
            elif picture:
                if link.changed:
                    link.changed = False
                    paint_dots(display, link.dots())
            elif text:
                if link.changed:
                    link.changed = False
                    cells.update(link)
            elif graphics.on:
                graphics.render()
            elif not pi:
                terminal.update()
            if now >= next_blink:
                if text:
                    cells.blink(link)
                elif not graphics.on and not picture and not pi:
                    terminal.blink()
                next_blink = now + 0.5
            display.present()                   # (at the real size: onto the TV, if anything changed)
    finally:
        bridge.terminate()
        try:
            bridge.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bridge.kill()
        if showing(console):     # not over someone's login console
            display.clear()
        fcntl.ioctl(console, KDSETMODE, KD_TEXT)
        termios.tcsetattr(console, termios.TCSANOW, saved)


if __name__ == "__main__":
    main()
