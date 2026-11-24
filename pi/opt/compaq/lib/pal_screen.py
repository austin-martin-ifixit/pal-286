"""What PAL 286, the lobby greeter, shows on the Compaq while it talks: a
glowing eye under a nameplate, the conversation typed out at the pace of the
voice, and a status line ("LISTENING", "THINKING").

The serial bridge draws this instead of the shared screen, and only when
nobody is using the Compaq (see serial_bridge.py). Plain VT102: a few hundred
bytes to draw, then only the typed words. The eye sits in a slightly
different place each time, so it can't burn into the plasma.

When PILINK is the Compaq's terminal, the bridge shows the same scene in
real dots instead (dots()): a round eye whose centre pulses while PAL
listens, with the nameplate, the words and the status in the Compaq's own
font; and PAL's full-screen boards drawn properly (see "boards in dots").
"""

import collections
import math
import random
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = "/opt/compaq/web/vendor/Compaq_Port3.woff"   # VileR's Compaq Portable III font, CC BY-SA
BAYER = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                  [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                  [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                  [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]) / 64 + 1 / 128

ESC = "\x1b"
RESET = (ESC + "[r" + ESC + "[0m" + "\x0f" + ESC + "(B" + ESC + "[?6l" + ESC + "[4l" + ESC + "[?7h"
         + ESC + "[?25h")                  # (the cursor back on, after a picture hid it)
TEXT_TOP, TEXT_BOTTOM = 16, 22      # rows the conversation scrolls in
STATUS_ROW = 24
# A full-screen picture (the mirror, the photo booth): the picture and its
# label above, and what PAL says scrolling along the bottom two rows.
CANVAS_ROWS = 22
CAPTION_TOP, CAPTION_BOTTOM = 23, 24
WIDTH = 74                          # text column width

# The eye, as rings from the centre out (distance in rows; a character cell
# is about twice as tall as it is wide). The centre is lit: reverse video.
RINGS = [(1.15, "LIT"), (1.9, "@"), (2.6, "O"), (3.3, "o"), (3.9, ":"), (4.4, "."),
         (5.0, " "), (5.9, "#")]
EYE_ROWS = 11


def eye_rows():
    """The eye: rows of ring characters ("LIT" for the lit centre, "" outside)."""
    rows = []
    for r in range(EYE_ROWS):
        dy = r - EYE_ROWS // 2
        cells = []
        for c in range(-12, 13):
            d = math.hypot(c / 2.1, dy)
            for limit, ch in RINGS:
                if d < limit:
                    cells.append(ch)
                    break
            else:
                cells.append("")
        rows.append(cells)
    return rows


def draw_eye(top, left, blink=False):
    out = []
    lit_on = ESC + ("[7;5m" if blink else "[7m")
    for i, cells in enumerate(eye_rows()):
        line, lit = "", False
        for ch in cells:
            if ch == "LIT" and not lit:
                line += lit_on
                lit = True
            elif ch != "LIT" and lit:
                line += ESC + "[0m"
                lit = False
            line += " " if ch in ("LIT", "") else ch
        if lit:
            line += ESC + "[0m"
        out.append(f"{ESC}[{top + i};{left}H{line}")
    return "".join(out)


class Scene:
    """PAL's screen. The bridge calls begin() to take over the Compaq's
    screen, say()/status() as PAL talks, and due() in its loop to get the next
    few characters of typing; end() hands the screen back."""

    def __init__(self, name="PAL 286"):
        self.name = name
        self.active = False
        self.queue = collections.deque()   # (text, characters a second)
        self.next_at = 0.0
        self.top = self.left = 0
        self.blinking = False
        self.canvas = None        # what a full-screen picture's rows show now
        # What the screen shows, for dots(): the conversation's rows (typed
        # so far) and the status line.
        self.rows = [""] * (TEXT_BOTTOM - TEXT_TOP + 1)
        self.status_text, self.status_blink = "", False
        self.changed = True
        self.board = None         # what a full-screen board means, for dots (see board())
        self.dither = None

    # ---------------------------------------------------------- drawing

    def begin(self, now, canvas=False):
        """The whole scene: clear screen, nameplate, eye, empty text area.
        Or (canvas) just a clear screen, for full-screen pictures."""
        self.active = True
        self.queue.clear()
        self.next_at = now
        self.board, self.changed = None, True
        self.rows = [""] * (TEXT_BOTTOM - TEXT_TOP + 1)
        if canvas:
            self.canvas = [""] * CANVAS_ROWS
            return (RESET + ESC + "[H" + ESC + "[2J" + ESC + "[?25l"   # no cursor over the picture
                    + f"{ESC}[{CAPTION_TOP};{CAPTION_BOTTOM}r"     # PAL's words scroll here
                    + f"{ESC}[{CAPTION_BOTTOM};1H").encode("ascii")
        self.canvas = None
        self.top = random.randint(1, 3)
        self.left = random.randint(24, 32)
        self.status_text, self.status_blink = "", False
        plate = "  " + " ".join(self.name.upper()) + "  "
        plate_left = self.left + 12 - len(plate) // 2
        out = (RESET + ESC + "[H" + ESC + "[2J"
               + f"{ESC}[{self.top};{plate_left}H{ESC}[7m{plate}{ESC}[0m"
               + draw_eye(self.top + 2, self.left)
               + f"{ESC}[{TEXT_TOP};{TEXT_BOTTOM}r"      # the text area scrolls by itself
               + f"{ESC}[{TEXT_BOTTOM};1H")
        return out.encode("ascii")

    def frame(self, lines):
        """A full-screen picture (the mirror, a photo): only the rows that
        changed are sent, which keeps a moving picture going at 9600 baud."""
        if not self.active or self.canvas is None:
            return b""
        out = []
        for y, text in enumerate(lines[:CANVAS_ROWS]):
            text = text[:79]
            if text != self.canvas[y]:
                out.append(f"{ESC}[{y + 1};1H{text}{ESC}[K")
                self.canvas[y] = text
                self.changed = True
        # (the cursor goes back to where PAL's words are being typed)
        return (ESC + "7" + "".join(out) + ESC + "8").encode("ascii") if out else b""

    def eye(self, blink):
        """Redraws just the lit centre, blinking (listening) or steady."""
        if not self.active or self.canvas is not None or blink == self.blinking:
            return b""
        self.blinking, self.changed = blink, True
        return (ESC + "7" + draw_eye(self.top + 2, self.left, blink) + ESC + "8").encode("ascii")

    def say(self, who, text, cps=40):
        """Queues a line of the conversation to be typed out at cps characters
        a second: PAL's words in time with its voice, a person's words (as
        PAL heard them) quickly, after "> "."""
        if not self.active:
            return
        prefix = "  " if who == "pal" else "  > "
        for line in textwrap.wrap(text, WIDTH, initial_indent=prefix,
                                  subsequent_indent="    " if who != "pal" else "  ") or [prefix]:
            self.queue.append(("\r\n" + line, cps))

    def status(self, text, blink=False):
        """The bottom line, outside the scrolling area: written at once.
        (Not over a picture: the bottom rows are PAL's words then.)"""
        if not self.active or self.canvas is not None:
            return b""
        self.status_text, self.status_blink, self.changed = text.upper()[:79], blink, True
        style = ESC + ("[5m" if blink else "[0m")
        out = (ESC + "7" + f"{ESC}[{STATUS_ROW};1H{ESC}[K" + style
               + text.upper().center(79).rstrip() + ESC + "[0m" + ESC + "8")
        return out.encode("ascii") + self.eye(blink)

    def due(self, now):
        """The next characters to type, if it's time; else b""."""
        if not self.queue or now < self.next_at:
            return b""
        text, cps = self.queue[0]
        # A few characters at a time keeps the pace without a write per letter.
        step = max(1, round(cps / 10))
        chunk, rest = text[:step], text[step:]
        if rest:
            self.queue[0] = (rest, cps)
        else:
            self.queue.popleft()
        self.next_at = now + len(chunk) / cps
        for char in chunk:                  # (what the rows now show, for dots())
            if char == "\n":
                self.rows = self.rows[1:] + [""]
            elif char != "\r":
                self.rows[-1] = (self.rows[-1] + char)[:80]
        self.changed = True
        return chunk.encode("ascii", "replace")

    def wait(self, now):
        """Seconds until due() has something, or None when nothing is queued."""
        return max(0.0, self.next_at - now) if self.queue else None

    def end(self):
        """Leaves the terminal in a plain state for the shared screen's repaint."""
        self.active = False
        self.canvas = self.board = None
        self.queue.clear()
        self.blinking = False
        return (RESET + ESC + "[H" + ESC + "[2J").encode("ascii")


# ---------------------------------------------------------------- in dots

_LETTERS = {}


def letter(char, tall):
    """A character of the Compaq's font as dots: 8 wide, 16 high (8 in the
    CGA's 640x200: each pair of rows as one, so no stroke goes missing)."""
    key = (char, tall)
    if key not in _LETTERS:
        image = Image.new("L", (8, 16))
        if char.strip():
            ImageDraw.Draw(image).text((0, 0), char, fill=255, font=_font())
        dots = np.asarray(image) > 128
        _LETTERS[key] = dots if tall else dots.reshape(8, 2, 8).any(axis=1)
    return _LETTERS[key]


_FONTS = []


def _font():
    if not _FONTS:
        _FONTS.append(ImageFont.truetype(FONT, 16))
    return _FONTS[0]


def write(dots, row, col, text, cell, reverse=False):
    """Text on the dot screen at a character cell (rows and columns from 1)."""
    tall = cell == 16
    y = (row - 1) * cell
    for i, char in enumerate(text[:81 - col]):
        x = (col - 1 + i) * 8
        if y + cell > dots.shape[0] or x + 8 > dots.shape[1]:
            break
        glyph = letter(char, tall)
        dots[y:y + cell, x:x + 8] = ~glyph if reverse else glyph


_EYES = {}


def eye(height, width, cx, cy, radius, aspect, pulse):
    """A round eye in dithered dots: a bright centre (dimmer when pulse is
    off), rings fading outwards, a dark gap and a lit rim. (Kept: the same
    few are drawn over and over.)"""
    key = (height, width, cx, cy, radius, aspect, pulse)
    if key not in _EYES:
        if len(_EYES) > 8:
            _EYES.clear()
        _EYES[key] = _eye(*key)
    return _EYES[key]


def _eye(height, width, cx, cy, radius, aspect, pulse):
    ys, xs = np.mgrid[0:height, 0:width]
    d = np.hypot((xs - cx) / radius, (ys - cy) * aspect / radius)
    level = np.select(
        [d < 0.2, d < 0.45, d < 0.78, d < 0.84, d < 0.93],
        [np.full_like(d, 1.0 if pulse else 0.62), 0.85 - (d - 0.2) * 1.6, 0.42 - (d - 0.45) * 0.9,
         np.zeros_like(d), np.full_like(d, 0.55)], 0.0)
    threshold = np.tile(BAYER, (height // 8 + 1, width // 8 + 1))[:height, :width]
    return level > threshold


def dots(scene, height, now):
    """The scene as a (height, 640) array of dots: 400 rows on the plasma's
    own mode, 200 on the CGA's. The centre of the eye pulses twice a second
    while PAL listens; a blinking status does too. A full-screen board:
    canvas_dots()."""
    if scene.canvas is not None:
        return canvas_dots(scene, height, now)
    cell = height // 25
    out = np.zeros((height, 640), bool)
    pulse = not scene.blinking or int(now * 2) % 2 == 0
    cx, cy = (scene.left + 11) * 8 + 4, (scene.top + 2 + EYE_ROWS // 2 - 1) * cell + cell // 2
    radius = 5.4 * 16
    out |= eye(height, 640, cx, cy, radius, 16 / cell, pulse)
    plate = "  " + " ".join(scene.name.upper()) + "  "
    write(out, scene.top, scene.left + 12 - len(plate) // 2 + 1, plate, cell, reverse=True)
    for i, text in enumerate(scene.rows):
        write(out, TEXT_TOP + i, 1, text, cell)
    if scene.status_text and (not scene.status_blink or int(now * 2) % 2 == 0):
        write(out, STATUS_ROW, 1, scene.status_text.center(79).rstrip(), cell)
    return out


def animating(scene):
    """Does the dot picture change with time alone (a pulse or a blink)?"""
    return scene.blinking or scene.status_blink


# ---------------------------------------------------------------- boards in dots
#
# PAL's full-screen boards come as 22 rows of text (for Kermit) and, beside
# them, what the board means (board()): the quiz's question and choices,
# the tune and the notes sounding now, or a small camera frame for the
# mirror. In dots they're drawn properly: big lettering, a real piano
# keyboard, the camera as a picture. PAL's words run along the last rows.

BOARD_ROWS = 22
LOW, HIGH = 36, 111                 # the keyboard: C2 to D#8, as the jukebox's text one
BLACK = {1, 3, 6, 8, 10}


def _ascii(value, limit):
    return "".join(c for c in str(value or "") if " " <= c <= "~")[:limit]


def _number(value, low=0, high=99):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def board(data):
    """What PAL said a board means, checked (anyone on the bridge's socket
    could send one), or None."""
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind == "quiz":
        choices = data.get("choices") if isinstance(data.get("choices"), list) else []
        return {"kind": kind, "question": _ascii(data.get("question"), 400),
                "choices": [_ascii(c, 120) for c in choices[:4]], "number": _number(data.get("number")),
                "total": _number(data.get("total")), "score": _number(data.get("score")),
                "topic": _ascii(data.get("topic"), 30)}
    if kind == "final":
        return {"kind": kind, "score": _number(data.get("score")), "total": _number(data.get("total")),
                "title": _ascii(data.get("title"), 70)}
    if kind == "music":
        notes = data.get("notes") if isinstance(data.get("notes"), list) else []
        try:
            t, total = max(0.0, float(data.get("t", 0))), max(0.0, float(data.get("total", 0)))
        except (TypeError, ValueError):
            t, total = 0.0, 0.0
        return {"kind": kind, "title": _ascii(data.get("title"), 60), "by": _ascii(data.get("by"), 75),
                "fact": _ascii(data.get("fact"), 240), "notes": [_number(n, 0, 127) for n in notes[:16]],
                "t": t, "total": total}
    if kind == "mirror":
        import base64
        width, height = _number(data.get("width"), 0, 320), _number(data.get("height"), 0, 240)
        try:
            raw = base64.b64decode(str(data.get("image", "")), validate=True)
        except ValueError:
            return None
        if width < 16 or height < 16 or len(raw) != width * height:
            return None
        return {"kind": kind, "image": np.frombuffer(raw, np.uint8).reshape(height, width)}
    return None


def big(dots, y, text, cell, scale=2, x=None):
    """Text in letters scale times the size, centred (or from x)."""
    tall = cell == 16
    width = len(text) * 8 * scale
    x = (640 - width) // 2 if x is None else x
    for i, char in enumerate(text):
        glyph = np.kron(letter(char, tall), np.ones((scale, scale), bool))
        left = x + i * 8 * scale
        if left < 0 or left + glyph.shape[1] > 640 or y + glyph.shape[0] > dots.shape[0]:
            continue
        dots[y:y + glyph.shape[0], left:left + glyph.shape[1]] |= glyph


def centred(dots, row, text, cell):
    text = text[:80]
    write(dots, row, 1 + (80 - len(text)) // 2, text, cell)


def rule(dots, y, x0, x1):
    dots[y, x0:x1] = True


def quiz_dots(dots, b, cell):
    big(dots, cell // 2, "LOBBY QUIZ", cell, 2)
    left = f"QUESTION {b['number']} OF {b['total']}" if b["number"] and b["total"] else "QUESTION"
    if b["topic"]:
        left += f"  -  {b['topic'].upper()}"
    write(dots, 4, 4, left, cell)
    score = f"SCORE: {b['score']}"
    write(dots, 4, 77 - len(score), score, cell)
    rule(dots, 4 * cell + cell // 2, 24, 616)
    row = 6
    for line in textwrap.wrap(b["question"], 70)[:4]:
        write(dots, row, 6, line, cell)
        row += 1
    row += 1
    for letter_, choice in zip("ABCD", b["choices"]):
        lines = textwrap.wrap(choice, 62)[:2] or [""]
        write(dots, row, 8, f" {letter_} ", cell, reverse=True)
        for k, line in enumerate(lines):
            write(dots, row + k, 13, line, cell)
        row += len(lines) + (1 if row + len(lines) < 20 else 0)
    centred(dots, 21, "Say the letter, or the answer.", cell)


def final_dots(dots, b, cell):
    big(dots, cell // 2, "LOBBY QUIZ", cell, 2)
    centred(dots, 6, "F I N A L   S C O R E", cell)
    big(dots, 8 * cell, f"{b['score']} / {b['total']}", cell, 4)
    if b["title"]:
        title = b["title"].upper()
        if len(title) <= 38:
            big(dots, 16 * cell, title, cell, 2)
        else:
            centred(dots, 16, title, cell)
    centred(dots, 21, "(C) 1987 PAL SOFTWARE.  ALL RIGHTS RESERVED.  NO CAP.", cell)


def piano(dots, top, height, playing):
    """A piano keyboard, LOW to HIGH, across the screen: white keys lit,
    black ones dark, and a key sounding now pressed: dark inside a lit
    outline (a black key, lit inside a dark one)."""
    def fold(midi):
        while midi < LOW:
            midi += 12
        while midi > HIGH:
            midi -= 12
        return midi
    playing = {fold(m) for m in playing}
    whites = [m for m in range(LOW, HIGH + 1) if m % 12 not in BLACK]
    width = 624 // len(whites)
    left0 = (640 - width * len(whites)) // 2
    place = {}
    for i, m in enumerate(whites):
        x = left0 + i * width
        place[m] = x
        dots[top:top + height, x:x + width - 1] = True
        if m in playing:                              # (pressed: dark inside its outline)
            dots[top + 1:top + height - 2, x + 2:x + width - 3] = False
    for m in range(LOW, HIGH + 1):
        if m % 12 in BLACK:
            x = place[m - 1] + width - width // 3
            bw, bh = (width * 2) // 3, (height * 3) // 5
            dots[top:top + bh, x:x + bw] = False
            if m in playing:
                dots[top + 2:top + bh - 2, x + 2:x + bw - 2] = True


def music_dots(dots, b, cell):
    centred(dots, 1, "P A L   2 8 6   J U K E B O X", cell)
    title = b["title"].upper()
    if len(title) <= 38:
        big(dots, cell + cell // 2, title, cell, 2)
    else:
        centred(dots, 3, title, cell)
    centred(dots, 5, b["by"], cell)
    for i, line in enumerate(textwrap.wrap(b["fact"], 70)[:3]):
        centred(dots, 7 + i, line, cell)
    piano(dots, 11 * cell, 5 * cell, b["notes"])
    total, t = b["total"], b["t"]
    bar_left, bar_width, y = 120, 400, 18 * cell
    dots[y, bar_left:bar_left + bar_width] = dots[y + cell - 2, bar_left:bar_left + bar_width] = True
    dots[y:y + cell - 1, bar_left] = dots[y:y + cell - 1, bar_left + bar_width - 1] = True
    done = int(bar_width * min(1.0, t / total)) if total else 0
    dots[y + 2:y + cell - 3, bar_left + 2:bar_left + 2 + max(0, done - 4)] = True
    clock = f"{int(t) // 60}:{int(t) % 60:02d} / {int(total) // 60}:{int(total) % 60:02d}"
    write(dots, 19, 67, clock, cell)
    centred(dots, 21, "A KEY AT THE COMPAQ STOPS THE MUSIC", cell)


def mirror_dots(dots, b, cell, scene):
    """The camera as a picture in dots, 4:3 on the plasma (in the CGA's
    640x200, each dot is twice as tall, so half the rows)."""
    from PIL import Image
    import pictures
    height = (BOARD_ROWS - 1) * cell
    width = 448
    grey = np.asarray(Image.fromarray(b["image"]).resize((width, height), Image.BILINEAR))
    if getattr(scene, "dither", None) is None or scene.dither[0] != (width, height):
        scene.dither = ((width, height), pictures.Dots(width, height))
    left = (640 - width) // 2
    dots[0:height, left:left + width] = scene.dither[1].dots(grey)
    centred(dots, BOARD_ROWS, "- MIRROR MODE -", cell)


def canvas_dots(scene, height, now):
    """A full-screen board in dots: drawn from what it means when PAL said,
    else its rows of text in the Compaq's font; PAL's words below."""
    cell = height // 25
    out = np.zeros((height, 640), bool)
    b = scene.board
    if b and b["kind"] == "quiz":
        quiz_dots(out, b, cell)
    elif b and b["kind"] == "final":
        final_dots(out, b, cell)
    elif b and b["kind"] == "music":
        music_dots(out, b, cell)
    elif b and b["kind"] == "mirror":
        mirror_dots(out, b, cell, scene)
    else:
        for i, text in enumerate(scene.canvas or []):
            write(out, i + 1, 1, text, cell)
    for i, text in enumerate(scene.rows[-2:]):
        write(out, CAPTION_TOP + i, 1, text, cell)
    return out
