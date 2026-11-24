"""Real pictures on the Compaq's plasma screen, sent down the serial cable.

Programs ask the serial bridge for them: show() and put_up() for a still
picture, Canvas for a moving one they draw a screenful at a time. The bridge
picks how (see serial_bridge.py). With PILINK.COM on the Compaq
(dos/pilink.asm) the dots go straight into video memory at up to 115200
baud: a photo in a second or two, in all 640x400 of the plasma's dots when
its BIOS allows, and moving pictures. dots() lays a screen out for that.

Without PILINK, MS-DOS Kermit draws still pictures itself: its Tektronix
4010 emulator draws lines and captions, and inside it DEC VT340 sixel images
appear dot for dot on the CGA screen (640x200 on the Compaq's 640x400
plasma, each dot twice as tall as it is wide). Tested in DOSBox running the
real MS-DOS Kermit 3.16, the same program the Compaq runs:

- ESC FF enters graphics mode and clears it. ESC [ ? 38 l goes back to
  text (which the bridge then repaints).
- A sixel image's first band (6 rows) is drawn 8 rows above the graphics
  cursor (a text baseline; after ESC FF it's 6 rows down, which would put
  the first band off the top), so the cursor is always moved first. Each
  band after the first starts at the left edge, whatever the first did, so
  a picture is placed across by padding every band with blank dots. The
  last band before the end is dropped, so a blank one goes last.
- Sixel aspect settings are ignored: one sixel dot is one screen dot, so
  pictures are squashed to half height first.
- Two colours only (amber and dark): photos are dithered.

At 9600 baud a full-screen photo is about 10 KB of sixels (ten seconds), so
it paints from the top down, like an old BBS; a QR code is about 3 KB.
"""

import base64
import io
import json
import os
import select
import socket
import sys
import termios
import tty
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

Image.MAX_IMAGE_PIXELS = 50_000_000      # (a "picture" bigger than this is a trick)

BRIDGE = os.environ.get("COMPAQ_BRIDGE", "/run/compaq-serial/bridge.sock")   # the serial bridge (shows them)
WIDTH, HEIGHT = 640, 200        # the CGA graphics screen, in dots
TEK_W, TEK_H = 1024, 780        # Tektronix 4010 coordinates (0,0 at the bottom left)
ENTER = b"\x1b\x0c"             # Tektronix mode, screen cleared
LEAVE = b"\x1b[?38l"            # back to text
AGENT = "CompaqPortableIII/1.0 (a Raspberry Pi showing pictures on a 1987 computer)"
CAPTION_ROWS = 11               # dot rows kept for a caption: its letters (8), a gap
FONT = "/opt/compaq/web/vendor/Compaq_Port3.woff"   # VileR's Compaq Portable III font, CC BY-SA
_font, _letters = None, {}


def fit(image, width, height, tall=2):
    """image (PIL), resized to fit width x height screen dots, keeping its
    shape as it will look on the plasma, and turned grey. tall: how many
    times taller than wide a dot is (2 on the CGA's 200 rows, 1 on the
    plasma's own 400)."""
    image = ImageOps.exif_transpose(image).convert("L")
    w, h = image.size
    scale = min(width / w, height * tall / h)
    size = (max(1, round(w * scale)), max(1, round(h * scale / tall)))
    return image.resize(size, Image.LANCZOS)


def dither(grey, contrast=True):
    """Amber or dark, dot by dot (Floyd-Steinberg): what a 1987 screen does
    with a photo."""
    if contrast:
        grey = ImageOps.autocontrast(grey, cutoff=1)
        grey = grey.filter(ImageFilter.UnsharpMask(radius=1.5, percent=80, threshold=2))
    return grey.convert("1")


def sixel(bits, left=0, top=0):
    """A 1-bit PIL image as what Kermit needs to draw it left dots in and
    top dots down from the screen's top left: the graphics cursor placed,
    then the sixel image, run-length packed."""
    w, h = bits.size
    pixels = bits.load()
    out = ["\x1d", tek_xy(0, top + 8).decode("ascii"), "\x1f",
           "\x1bP0;1;0q", f'"1;1;{left + w};{h}', "#1;2;100;100;100", "#1"]
    for band in range(0, h, 6):
        codes = []
        for x in range(w):
            value = 0
            for k in range(6):
                if band + k < h and pixels[x, band + k]:
                    value |= 1 << k
            codes.append(value)
        while codes and codes[-1] == 0:
            codes.pop()                          # nothing to draw past the last dot
        line = [f"!{left}?"] if left > 3 else ["?" * left]
        i = 0
        while i < len(codes):
            j = i
            while j < len(codes) and codes[j] == codes[i]:
                j += 1
            ch = chr(63 + codes[i])
            line.append(f"!{j - i}{ch}" if j - i > 3 else ch * (j - i))
            i = j
        out.append("".join(line) + "-")
    out.append("?-\x1b\\")                # (the band Kermit drops)
    return "".join(out)


def tek_xy(x, y):
    """Screen dots (from the top left) to a Tektronix address."""
    tx = max(0, min(TEK_W - 1, round(x * TEK_W / WIDTH)))
    ty = max(0, min(TEK_H - 1, round((HEIGHT - 1 - y) * TEK_H / HEIGHT)))
    return bytes([0x20 + (ty >> 5), 0x60 + (ty & 31), 0x20 + (tx >> 5), 0x40 + (tx & 31)])


def tek_text(x, y, text):
    """Text drawn in graphics mode, starting x dots in, its letters' bottom
    row y dots down (Kermit's letters are 8x8, drawn from y-7 to y)."""
    safe = "".join(c for c in text if " " <= c <= "~")
    return b"\x1d" + tek_xy(x, y) + b"\x1f" + safe.encode("ascii")


def park():
    """The graphics cursor, out of the way in the bottom right corner."""
    return b"\x1d" + tek_xy(WIDTH - 1, HEIGHT - 1) + b"\x1f"


def layout(image, caption=""):
    """Where a picture goes on the screen: (its dots as a 1-bit image, left,
    top), centred above its caption, if it has one. A 1-bit image (a QR
    code, a page already squashed) is used dot for dot, as it is."""
    room = HEIGHT - CAPTION_ROWS if caption else HEIGHT
    if image.mode == "1" and image.width <= WIDTH and image.height <= room:
        bits = image
    else:
        bits = dither(fit(image, WIDTH, room))
    return bits, (WIDTH - bits.width) // 2, (room - bits.height) // 2


def screen(image, caption=""):
    """Everything to send for one picture: graphics mode, the picture, its
    caption, the cursor tucked away. (bytes, the whole screen's dots as a
    1-bit image, caption left out, for anyone watching elsewhere)"""
    bits, left, top = layout(image, caption)
    out = ENTER + sixel(bits, left, top).encode("ascii")
    if caption:
        caption = caption[:WIDTH // 8 - 1]
        out += tek_text((WIDTH - len(caption) * 8) // 2, HEIGHT - 2, caption)
    whole = Image.new("1", (WIDTH, HEIGHT), 0)
    whole.paste(bits, (left, top))
    return out + park(), whole


def letter(char, rows):
    """One letter of the Compaq's own font as dots: 8 wide, and 16 tall or
    (every other row, the size of Kermit's graphics letters) 8."""
    import numpy as np
    global _font
    if (char, rows) not in _letters:
        if _font is None:
            try:
                _font = ImageFont.truetype(FONT, 16)
            except OSError:
                _font = False                # (not installed here: PIL's own small letters)
        cell = Image.new("L", (8, 16))
        if _font:
            ImageDraw.Draw(cell).text((0, 0), char, fill=255, font=_font)
        else:
            ImageDraw.Draw(cell).text((1, 3), char, fill=255)
        grid = np.asarray(cell) > 128
        _letters[char, rows] = grid if rows == 16 else grid[::2]
    return _letters[char, rows]


def dots(image, caption="", height=HEIGHT):
    """A whole screen for PILINK: a (height, 640) array of dots, True where
    lit, the picture centred above its caption. height 200 is the CGA
    screen (each dot twice as tall as wide); 400 is every dot the plasma
    has (square). A 1-bit image made for 200 rows (a QR code, a page
    already squashed) is used dot for dot, each row twice on 400."""
    import numpy as np
    double = height != HEIGHT
    letter_rows = 16 if double else 8
    room = height - (letter_rows + 3 if caption else 0)
    if image.mode == "1" and image.width <= WIDTH and image.height * (2 if double else 1) <= room:
        bits = image.resize((image.width, image.height * 2), Image.NEAREST) if double else image
    else:
        bits = dither(fit(image, WIDTH, room, 1 if double else 2))
    screen = np.zeros((height, WIDTH), bool)
    left, top = (WIDTH - bits.width) // 2, (room - bits.height) // 2
    screen[top:top + bits.height, left:left + bits.width] = np.asarray(bits.convert("1"), bool)
    if caption:
        text = "".join(c if " " <= c <= "~" else " " for c in caption)[:WIDTH // 8 - 1]
        x, y = (WIDTH - len(text) * 8) // 2, height - letter_rows - 1
        for i, char in enumerate(text):
            screen[y:y + letter_rows, x + 8 * i:x + 8 * i + 8] |= letter(char, letter_rows)
    return screen


def from_bytes(data):
    return Image.open(io.BytesIO(data))


def fetch(url, limit=10_000_000):
    """A picture from the web, as a PIL image. Raises NotShown."""
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise NotShown("That picture is too big to fetch.")
        image = from_bytes(data)
        image.load()
        return image
    except NotShown:
        raise
    except Exception as e:       # (offline, gone, or not a picture PIL can read)
        raise NotShown("Couldn't fetch that picture. Is the Pi online?") from e


def qr(text):
    """A QR code for text (a web address, say), ready to show as it is:
    dark squares on lit amber (what phone cameras expect), each the same
    size, square on the plasma (twice as many dots across as rows down),
    as big as fits."""
    import qrcode                 # (python3-qrcode)
    code = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(text)
    try:
        code.make(fit=True)
    except Exception as e:       # (more than a QR code holds)
        raise NotShown("That's too long for a QR code.") from e
    modules = code.get_matrix()                      # True = a dark square, quiet zone included
    n = len(modules)
    across = next((m for m in (8, 6, 4, 2) if n * m <= WIDTH - 40 and n * m // 2 <= HEIGHT - 20), 2)
    down = across // 2
    image = Image.new("1", (n * across, n * down), 1)
    pixels = image.load()
    for r, row in enumerate(modules):
        for c, dark in enumerate(row):
            if dark:
                for y in range(r * down, (r + 1) * down):
                    for x in range(c * across, (c + 1) * across):
                        pixels[x, y] = 0
    return image


class NotShown(Exception):
    """A picture couldn't go up; the message says why, for the person at the
    screen."""


def encode(image):
    """A PIL image or picture file bytes, as picture file bytes worth sending."""
    if not isinstance(image, Image.Image):
        return image
    image = image.copy()
    if image.mode != "1":
        image.thumbnail((1280, 1280))            # (no need to send more than this)
        image = image.convert("L")
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def answer(conn):
    """One reply line from the bridge, read a byte at a time so nothing after
    it is taken: {} if it hung up instead."""
    line = b""
    while not line.endswith(b"\n"):
        byte = conn.recv(1)
        if not byte:
            break
        line += byte
    return json.loads(line or b"{}")


def put_up(image, caption="", lobby_only=False, more=False):
    """Puts a picture on the Compaq's screen and returns once it's on its
    way: (the connection holding it there, seconds it takes to paint).
    Close the connection to take the picture down; it turns readable when
    the picture comes down some other way (a key at the Compaq, another
    picture, 5 minutes), and then key(conn) says which key. image: a PIL
    image or picture file bytes. Browsers watching the shared screen see
    it too, unless lobby_only (PAL's photo booth). more: another picture
    follows this one (the Compaq then waits a few seconds for it before
    going back to text; see release()). Raises NotShown."""
    request = {"op": "picture", "image": base64.b64encode(encode(image)).decode(),
               "caption": caption, "lobby": bool(lobby_only), "more": bool(more)}
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.settimeout(30)              # (the first picture waits for PILINK to start, off a floppy perhaps)
        conn.connect(BRIDGE)
        conn.sendall((json.dumps(request) + "\n").encode())
        first = answer(conn)
    except (OSError, ValueError) as e:
        conn.close()
        raise NotShown("The Compaq's screen isn't connected right now.") from e
    if not first.get("showing"):
        conn.close()
        raise NotShown(first.get("message", "The Compaq's screen didn't take the picture."))
    conn.settimeout(5)
    return conn, float(first["showing"])


def key(conn):
    """The key pressed at the Compaq that took a picture down ("" if it came
    down some other way), once conn (from put_up) is readable."""
    try:
        return str(answer(conn).get("key", ""))
    except (OSError, ValueError):
        return ""


def release():
    """No more pictures after all: the Compaq needn't wait for the next
    one (see put_up's more) and goes back to text at once."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(BRIDGE)
            conn.sendall(b'{"op": "text"}\n')
            answer(conn)
    except (OSError, ValueError):
        pass


def show(image, caption="", keys=True, told=None, more=False):
    """Shows a picture on the Compaq's screen and waits until someone
    presses a key there, or (keys) one is typed here, in this program's own
    terminal (so someone watching in a browser can go on too). told, if
    given, hears how many seconds it takes to paint, once it's on its way.
    more: another picture follows unless the key says stop. Returns the key
    ("" if the picture came down another way). Raises NotShown."""
    conn, seconds = put_up(image, caption, more=more)
    if told:
        told(seconds)
    stdin = sys.stdin.fileno() if keys and sys.stdin.isatty() else None
    saved = termios.tcgetattr(stdin) if stdin is not None else None
    pressed = ""
    try:
        if stdin is not None:
            tty.setcbreak(stdin)
        while True:
            ready, _, _ = select.select([conn] + ([stdin] if stdin is not None else []), [], [])
            if conn in ready:
                pressed = key(conn)                  # a key at the Compaq (or it timed out)
                return pressed
            if stdin in ready:
                pressed = os.read(stdin, 16).decode("latin-1")
                return pressed
    finally:
        if saved is not None:
            termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        conn.close()
        if more and (not pressed or stops(pressed)):
            release()


class Dots:
    """Turns the frames of a moving picture (greys) into dots for a Canvas.
    Each dot is lit if the picture there is brighter than a fixed pattern's
    value at that spot ("ordered" dithering): the pattern never moves, so
    what stays still in the picture stays the same dots, and only what
    changes has to cross the cable. (A still photo is dithered by spreading
    each dot's error to its neighbours, which looks finer, but then every
    frame of a film would differ everywhere.) The darkest and brightest
    parts are stretched to dark and lit, and edges are sharpened a little,
    which one-colour dots need."""

    PATTERN = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))
    PATTERN_TALL = ((0, 4, 2, 6), (5, 1, 7, 3))      # for dots twice as tall as wide: half the rows

    def __init__(self, width, height, gamma=0.8, sharpen=1.0, levels=None, tall=False):
        """levels: the greys to treat as dark and as lit, (low, high), when
        they're known and fixed (a game). Left out, they follow the film.
        tall: each dot is twice as tall as it is wide (the 320x100 canvas)."""
        import numpy as np
        pattern = np.array(self.PATTERN_TALL if tall else self.PATTERN, np.float32)
        pattern = (pattern + 0.5) / pattern.size
        rows, columns = pattern.shape
        self.pattern = np.tile(pattern, (-(-height // rows), -(-width // columns)))[:height, :width]
        self.gamma, self.sharpen = gamma, sharpen
        self.follow = levels is None
        self.low, self.high = levels or (None, None)

    def dots(self, grey):
        """grey: a (height, width) array, 0 dark to 255 bright. Returns the
        same shape, True where a dot is lit."""
        import numpy as np
        if self.follow:
            low, high = np.percentile(grey[::4, ::4], (2, 99.5))
            if self.low is None:
                self.low, self.high = low, high
            # Only when the film's light has really changed (a cut, a fade),
            # and then all at once: a level that crept every frame would
            # change dots all over the screen every frame.
            elif max(abs(low - self.low), abs(high - self.high)) > 0.12 * max(self.high - self.low, 24.0):
                self.low, self.high = low, high
        level = np.clip((grey.astype(np.float32) - self.low) / max(self.high - self.low, 24.0), 0, 1)
        if self.gamma != 1:
            level **= self.gamma
        if self.sharpen:
            edge = np.pad(level, 1, mode="edge")
            around = (edge[:-2, 1:-1] + edge[2:, 1:-1] + edge[1:-1, :-2] + edge[1:-1, 2:] + level) / 5
            level += self.sharpen * (level - around)
        return level > self.pattern


class Canvas:
    """A moving picture on the Compaq's screen, drawn by this program a
    screenful at a time (PotatoTube HD, Doom). It needs PILINK on the
    Compaq (or the TV standing in): otherwise opening one raises NotShown,
    and the program falls back to text.

    layout is the picture's size in dots: "320x200" (8,000 bytes a
    screenful at most), "160x100" (2,000: fat dots, more frames a second),
    "640x200", or "640x400" (the plasma's own; .width and .height say what
    was given). send() a screenful whenever .ready says the last one has
    arrived: only what changed crosses the cable. news() says which keys
    went down and up at the Compaq. bps is the cable's bytes a second."""

    def __init__(self, layout="320x200", lobby_only=False):
        self.conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.conn.settimeout(30)
            self.conn.connect(BRIDGE)
            self.conn.sendall((json.dumps({"op": "canvas", "layout": layout, "lobby": bool(lobby_only)})
                               + "\n").encode())
            first = answer(self.conn)
        except (OSError, ValueError) as e:
            self.conn.close()
            raise NotShown("The Compaq's screen isn't connected right now.") from e
        if not first.get("canvas"):
            self.conn.close()
            raise NotShown(first.get("message", "This screen can't show moving pictures."))
        self.layout, self.bps = str(first["layout"]), int(first["bps"])
        self.width, self.height = int(first["width"]), int(first["height"])
        self.ready, self.closed, self.pending = True, False, b""
        self.why = ""                       # (the screen's reason, when it takes the picture away)
        self.conn.settimeout(None)

    def fileno(self):
        return self.conn.fileno()

    def send(self, dots):
        """A screenful: a (height, width) array, True where a dot is lit."""
        import numpy as np
        packed = np.packbits(np.asarray(dots, bool), axis=1).tobytes()
        try:
            self.conn.sendall(b"F" + len(packed).to_bytes(4, "big") + packed)
        except OSError:
            self.closed = True
        self.ready = False

    def news(self, timeout=0.0):
        """Waits up to timeout seconds for word from the screen. Returns the
        keys since last asked, as (key, down?, what it types): key is the
        PC keyboard's scancode (pilink.py has their names), reported when
        it goes down and again when it comes up. Sets .ready when the last
        screenful has arrived, and .closed when the screen has been taken
        away (the main menu key, the Compaq unplugged)."""
        keys = []
        while not self.closed:
            readable, _, _ = select.select([self.conn], [], [], timeout)
            if not readable:
                break
            timeout = 0.0
            try:
                data = self.conn.recv(65536)
            except OSError:
                data = b""
            if not data:
                self.closed = True
                break
            *lines, self.pending = (self.pending + data).split(b"\n")
            for line in lines:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if message.get("ready"):
                    self.ready = True
                elif "done" in message:               # (first: it also says which key ended it, maybe none)
                    self.closed, self.why = True, str(message["done"])
                elif "key" in message:
                    keys.append((int(message["key"]), bool(message.get("down")), str(message.get("typed", ""))))
        return keys

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def stops(key):
    """Does this key mean "enough pictures" (Q, X or Esc)?"""
    return key.lower() in ("q", "x", "\x1b", "\x03")


def saying(what, more=True):
    """A told= for show(): says on the shared screen what's being painted
    and for how long, and how to go on (someone watching in a browser sees
    this instead)."""
    def say(seconds):
        print(f"  Painting {what} on the Compaq's screen (about {max(1, round(seconds))} seconds).")
        print("  A key there (or here) " + ("for the next one, Q to stop." if more else "to go on."),
              flush=True)
    return say
