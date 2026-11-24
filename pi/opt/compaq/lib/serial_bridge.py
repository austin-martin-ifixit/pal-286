#!/usr/bin/env python3
"""Connects the Compaq's serial cable to the shared Compaq session.

Owns the serial port (8N1, no flow control, modem lines ignored for data, at
the speed compaq-serial.service gives: Kermit's own, set in MSKERMIT.INI)
and runs a tmux client for the shared session on a pseudo-terminal, copying
bytes both ways, so the Compaq is one more screen on the session.

The Compaq's screen is repainted when Kermit opens its port (the null modem
cable turns the Compaq's DTR into our DSR/DCD) and on the first key after 5
quiet minutes, in case it missed a change.

After 15 minutes with no key at the Compaq and no change on screen, it shows
a small moving clock instead, so the gas-plasma panel doesn't burn in. A key
at the Compaq (swallowed) wakes it, and so does a change on the shared screen
that someone caused by typing, at the Compaq or in a browser; a program
redrawing a clock by itself doesn't.

PAL, the lobby greeter (compaq-pal.service), can borrow the screen the same
way while it talks: only when nobody has typed anywhere for 2 minutes, and
the same keys and typing that wake the saver hand the screen straight back.
With PILINK as the terminal its eye is drawn in real dots
(pal_screen.dots), and it can beep the Compaq's own speaker.

Pictures: programs and PAL can ask for a picture (see pictures.py). When
the Compaq has PILINK.COM (dos/pilink.asm), the bridge asks Kermit to run
it: PILINK reads the cable itself, at up to 115200 baud, and puts what
arrives straight into video memory, so a photo takes a second or two, in
every dot the plasma has. A program can also hold a canvas and send
screenful after screenful (PotatoTube HD, Doom), hearing each key at the
Compaq go down and come up. Without PILINK, Kermit draws the picture
itself (Tektronix mode, with sixel images), at its own speed. Either way
the picture stays until a key at the Compaq (swallowed) or the program
asking lets go, and the screen comes back as text.

Kermit file transfers can't pass through a shared screen, so menu programs
ask for them over a Unix socket (see transfer.py): the bridge stops relaying
the screen, runs C-Kermit straight on the cable, then repaints. Closing the
request (Ctrl-C in transfer.py) cancels the transfer.

PILINK as the whole terminal: when the Compaq runs PI.BAT, PILINK starts by
itself and says hello, and from then on it is the Compaq's terminal, not
Kermit. Everything that would have gone to Kermit as VT102 text (the
session, the saver, PAL's eye) goes into a copy of the screen here
(text_screen.py) instead, and the cells that changed go to the Compaq's
text mode through PILINK at its full speed. Keys come back as PILINK's key
presses. Pictures need no handover: PILINK switches to graphics and back.
For a file transfer PILINK goes back to DOS with exit code 10, PI.BAT runs
Kermit as a server for C-Kermit here, and C-Kermit's BYE sends it back to
PILINK. Which of the two terminals the Compaq uses is kept in
/run/compaq-serial/terminal, so a restarted bridge doesn't type text at a
PILINK that's waiting for it.

Usage: serial_bridge.py DEVICE [BAUD]   (compaq-serial.service runs it; BAUD
defaults to what data/cable-speed says)
"""

import base64
import collections
import fcntl
import json
import os
import pty
import random
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import termios
import time
import tty
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pal_screen  # noqa: E402
import pictures  # noqa: E402
import pilink  # noqa: E402
import text_screen  # noqa: E402
from PIL import Image  # noqa: E402

TMUX = ["tmux", "-L", "compaq"]
SOCKET = "/run/compaq-serial/bridge.sock"
STATUS = "/run/compaq-serial/status"
TRANSFER_TIMEOUT = 600
QUIET_SECONDS = int(os.environ.get("COMPAQ_QUIET_SECONDS", 300))   # first key after this long repaints
SAVER_SECONDS = int(os.environ.get("COMPAQ_SAVER_SECONDS", 900))
PAL_IDLE_SECONDS = int(os.environ.get("COMPAQ_PAL_IDLE_SECONDS", 120))   # nobody typing this long: PAL may show
PAL_TIMEOUT = 90               # PAL silent this long mid-scene (crashed?): hand the screen back
PAL_LONGEST = 600              # and never more than 10 minutes at a time (burn-in)
PICTURE_LONGEST = 300          # a still picture stays at most 5 minutes (burn-in)
MAX_PICTURE = 8_000_000        # bytes of picture file a request may bring (base64)
TV = os.environ.get("COMPAQ_TV") == "1"   # tv_terminal.py: a TV stands in for the Compaq
WRAP_ON = b"\x1b[?7h"          # tmux relies on autowrap; a real VT102 starts without it
SPEEDS = {"1200": termios.B1200, "2400": termios.B2400, "4800": termios.B4800,
          "9600": termios.B9600, "19200": termios.B19200, "38400": termios.B38400,
          "57600": termios.B57600, "115200": termios.B115200}
# PILINK (dos/pilink.asm): the Compaq's own fast picture program. A file
# called /etc/compaq/no-pilink switches it off (pictures then go through
# Kermit, slowly, and moving ones are refused): for when it misbehaves.
USE_PILINK = (os.environ.get("COMPAQ_PILINK", "on") != "off"
              and not os.path.exists("/etc/compaq/no-pilink"))
ASSUME_READY = os.environ.get("COMPAQ_READY") == "1"   # (the test rig's cable has no modem lines)
KERMIT_BACK = float(os.environ.get("COMPAQ_KERMIT_BACK", 0 if TV else 1.0))   # s: Kermit taking the port back
LINGER = 0.4                   # s PILINK stays up after a picture, in case another follows at once
LINGER_MORE = 6.0              # ...and when the program said more are coming (a guide's photos)
SHARE_EVERY = 0.5              # s between a moving picture's frames for browsers
HOLD_HELLO = 0.1               # s an escape from the Compaq is held back, in case a PILINK hello follows
REGAIN = 20.0                  # s after the terminal PILINK stopped answering: nothing from the Compaq is typing
# PILINK's own messages ("N" and a reason, "R" 0, a key's scancode...): a
# letter and a control or 8-bit value, which nobody types at Kermit (Enter,
# Tab, Backspace and Escape after a letter don't count).
PILINK_CHATTER = re.compile(rb"[KANRQEF][\x00-\x07\x0e-\x1a\x1c-\x1f\x80-\xff]")
DOS_NAMES = r"[A-Za-z0-9:\\._*?~!#$%&'()@^-]{1,80}"   # files to fetch from the Compaq: no spaces, commas or braces


def setup_line(fd, baud):
    """Raw 8N1 at baud, no flow control, ignoring carrier and other modem lines."""
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)
    attrs[2] &= ~(termios.PARENB | termios.CSTOPB | termios.CSIZE | termios.CRTSCTS)
    attrs[2] |= termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[4] = attrs[5] = SPEEDS[str(baud)]
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def set_speed(fd, baud):
    """Changes only the speed, once everything written has left; nothing
    that has arrived is thrown away."""
    attrs = termios.tcgetattr(fd)
    attrs[4] = attrs[5] = SPEEDS[str(baud)]
    termios.tcsetattr(fd, termios.TCSADRAIN, attrs)


def compaq_ready(fd):
    """True while the Compaq holds DTR, which the null modem wires to our DSR/DCD."""
    if ASSUME_READY:
        return True
    try:
        bits = struct.unpack("i", fcntl.ioctl(fd, termios.TIOCMGET, struct.pack("i", 0)))[0]
    except OSError:
        return False
    return bool(bits & (termios.TIOCM_DSR | termios.TIOCM_CAR))


def start_client():
    """A tmux client for the shared session, on a new 80x24 pseudo-terminal."""
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        # tmux's own complaints ("no server running") stay off the Compaq.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        env = dict(os.environ, TERM="vt102", LANG="C", LC_ALL="C")
        os.execvpe(TMUX[0], TMUX + ["attach-session", "-t", "compaq"], env)
    return pid, fd


def unfinished_hello(data):
    """True when data ends partway through a PILINK hello (ESC _ P L, three
    bytes, ESC \\): the rest is still on the cable."""
    start = data.rfind(pilink.HELLO_START[:2])
    rest = data[start:]
    return start >= 0 and len(rest) < len(pilink.HELLO_START) + 5 and pilink.HELLO_START.startswith(rest[:4])


def link_status(ready):
    """For ./check.sh: whether the Compaq is actually there at the cable."""
    if TV:
        return "tv"
    return "connected" if ready else "waiting for Kermit on the Compaq"


def write_status(text, path=None):
    path = path or STATUS            # (looked up now: tests point STATUS somewhere of their own)
    try:
        with open(path + ".new", "w") as f:
            f.write(text + "\n")
        os.replace(path + ".new", path)
    except OSError:
        pass


def cable_speed():
    """The cable's everyday speed: Kermit's, from data/cable-speed (the one
    place it's set; the Compaq's MSKERMIT.INI is built from it too)."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../data/cable-speed")) as f:
            speed = f.read().split()[0]
    except (OSError, IndexError):
        speed = "9600"
    return speed if speed in SPEEDS else "9600"


def runtime_file(name):
    """A file next to the status (in /run/compaq-serial)."""
    return os.path.join(os.path.dirname(STATUS), name)


def read_status(name):
    try:
        with open(runtime_file(name)) as f:
            return f.read().strip()
    except OSError:
        return ""


def write_speed(baud):
    """For programs that pace themselves to the cable (PotatoTube): its
    everyday speed, next to the status."""
    write_status(str(baud), runtime_file("speed"))


def write_all(fd, data):
    """Writes all of it, waiting whenever the line's buffer is full."""
    while data:
        try:
            data = data[os.write(fd, data):]
        except BlockingIOError:
            select.select([], [fd], [], 1)


class Port:
    """The cable as PILINK's link uses it: bytes are queued here and written
    as the line takes them, so a screenful on its way never holds the bridge
    up. A TV standing in has no cable to set the pace, so the pace is kept
    here (paced), at the speed a real cable would have."""

    def __init__(self, fd, baud, paced):
        self.fd, self.baud, self.paced = fd, int(baud), paced
        self.out = bytearray()
        self.free_at = 0.0

    def queue(self, data):
        self.out += data

    def drop(self):
        """Forgets what hasn't gone yet."""
        self.out.clear()
        try:
            termios.tcflush(self.fd, termios.TCOFLUSH)
        except termios.error:
            pass

    def speed(self, baud):
        write_all(self.fd, bytes(self.out))          # what's queued belongs to the old speed
        self.out.clear()
        self.baud = int(baud)
        if not self.paced:
            set_speed(self.fd, baud)

    def pump(self, now):
        """Writes what the line will take now."""
        if not self.out:
            return
        if self.paced:
            if now < self.free_at:
                return
            count = min(len(self.out), max(16, self.baud // 500))     # a fiftieth of a second's worth
            write_all(self.fd, bytes(self.out[:count]))
            self.free_at = max(self.free_at, now - 0.1) + count * 10 / self.baud
        else:
            try:
                count = os.write(self.fd, bytes(self.out[:4096]))
            except BlockingIOError:
                return
        del self.out[:count]

    def wait(self, now):
        """Seconds until pump() can write again, when that's a matter of
        time (None: nothing queued, or the line itself will say)."""
        return max(0.0, self.free_at - now) if self.out and self.paced else None

    def writable(self):
        """Should the bridge wait for the line to take more?"""
        return bool(self.out) and not self.paced


def tmux(*args):
    try:
        return subprocess.run(TMUX + list(args), capture_output=True, text=True, timeout=5).stdout
    except subprocess.TimeoutExpired:
        return ""


def last_typed(skip_pid=None):
    """Wall-clock time anyone last typed into the shared session (0 if
    unknown). From each client's last keypress: the session's own activity
    time also moves when a browser merely connects. skip_pid leaves one
    client out (ours: the lobby)."""
    latest = 0
    for line in tmux("list-clients", "-F", "#{client_pid} #{client_activity} #{client_created}").splitlines():
        try:
            pid, activity, created = (int(v) for v in line.split())
        except ValueError:
            continue
        if activity > created and pid != skip_pid:
            latest = max(latest, activity)
    return latest


# A known starting point for a repaint: full scroll region, plain text,
# normal character sets (G1 = line drawing, as tmux expects), autowrap on,
# cursor home on a clear screen.
RESET = b"\x1b[r\x1b[0m\x0f\x1b(B\x1b)0\x1b[?7h\x1b[H\x1b[2J"


def redraw(write, client_pid):
    """Repaints the Compaq's whole screen from the shared session. A window
    size change (SIGWINCH to our tmux client) makes tmux forget what it
    thought the terminal looked like and draw everything from scratch, which
    a plain refresh doesn't (the saver or PAL may have moved the cursor or
    changed the scroll region behind its back). write: where the Compaq's
    text goes (Bridge.text)."""
    write(RESET)
    try:
        os.kill(client_pid, signal.SIGWINCH)
    except ProcessLookupError:
        pass


PUNCTUATION = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-",
                             "\u2014": "-", "\u2026": "...", "\u00bf": "", "\u00a1": ""})


def printable(text, limit):
    """Plain printable ASCII: nothing PAL passes on can send the Compaq an
    escape sequence. Accents are dropped, not the letters ("Que tal?" for
    "\u00bfQu\u00e9 tal?")."""
    text = unicodedata.normalize("NFKD", str(text).translate(PUNCTUATION))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c if " " <= c <= "~" else " " for c in text)[:limit]


class Saver:
    """The burn-in screen saver: time and date in a small block that moves
    once a minute on an otherwise dark screen. A few dozen bytes a minute."""

    def __init__(self):
        self.on = False
        self.minute = None

    def start(self, write):
        self.on, self.minute = True, None
        self.tick(write)

    def tick(self, write):
        now = time.localtime()
        minute = time.strftime("%H:%M", now)
        if minute == self.minute:
            return
        self.minute = minute
        rows = [time.strftime("%I:%M %p", now).lstrip("0"), time.strftime("%a %d %b", now),
                "", "press a key"]
        width = max(map(len, rows))
        top, left = random.randint(1, 24 - len(rows)), random.randint(1, 80 - width)
        out = "\x1b[0m\x1b[H\x1b[2J" + "".join(f"\x1b[{top + i};{left}H{row.center(width)}"
                                             for i, row in enumerate(rows))
        write(out.encode("ascii"))


def transfer(request, conn, line, device, baud, server=False):
    """Runs C-Kermit on the cable for one send or receive; returns the reply.
    The requester closing its connection cancels the transfer. server: the
    Compaq's Kermit is a server (PI.BAT), so a receive fetches the files
    named in request["files"], and BYE ends it either way."""
    op = request.get("op")
    if op == "send":
        path = str(request.get("path", ""))
        if not os.path.isfile(path):
            return {"ok": False, "message": "That file isn't there any more."}
        if any(c in path for c in "{}\\,"):
            return {"ok": False, "message": "Kermit can't send a file whose name has { } \\ or a comma in it."}
        action, cwd = f"send {{{path}}}", os.path.dirname(path) or "."
    elif op == "receive":
        action, cwd = "receive", str(request.get("dir") or os.path.expanduser("~"))
        if server:
            files = str(request.get("files", ""))
            if not re.fullmatch(DOS_NAMES, files):
                return {"ok": False, "message": "Which files? A DOS name, like C:\\LETTER.TXT or *.TXT."}
            action = f"get {files}"
    else:
        return {"ok": False, "message": "That wasn't a transfer request."}
    if server:
        action += ", bye"

    # C-Kermit on the cable itself, settings matching MSKERMIT.INI. (Its
    # "remote mode" would look for a login terminal, which a service lacks.)
    settings = (f"set carrier-watch off, set line {device}, set speed {baud}, "
                "set flow-control none, set parity none")
    command = ["kermit", "-Y", "-B", "-C", f"{settings}, {action}, exit"]
    if TV:
        return {"ok": False, "message": "File transfers need the Compaq itself; the TV is only standing in."}
    write_status("transferring")
    try:
        try:
            kermit = subprocess.Popen(command, cwd=cwd, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            return {"ok": False, "message": f"Kermit couldn't start ({e.strerror})."}
        deadline = time.monotonic() + TRANSFER_TIMEOUT
        while kermit.poll() is None:
            hung_up, _, _ = select.select([conn], [], [], 1)
            if hung_up and not conn.recv(1):      # the requester gave up
                kermit.kill()
                kermit.wait()
                return {"ok": False, "message": "Cancelled."}
            if time.monotonic() > deadline:
                kermit.kill()
                kermit.wait()
                return {"ok": False, "message": "The Compaq didn't answer, so the transfer was stopped."}
        if kermit.returncode == 0:
            return {"ok": True, "message": "Done."}
        return {"ok": False, "message": "The transfer didn't finish."}
    finally:
        setup_line(line, baud)
        termios.tcflush(line, termios.TCIFLUSH)
        write_status(link_status(compaq_ready(line)))


class Picture:
    """A still picture for the Compaq's screen. conn is whoever asked: told
    how long it takes to paint, and when it comes down. It goes through
    PILINK when the Compaq has it (via "link"); otherwise Kermit draws it
    from sixels, sent a little at a time at the cable's pace (via
    "kermit"), so nothing waits on a full buffer."""

    moving = False

    def __init__(self, image, caption, conn, now, lobby=False, more=False):
        self.image, self.caption, self.conn = image, caption, conn
        self.lobby, self.more = lobby, more
        self.started = now
        self.via = None                  # (None: waiting for PILINK to start)
        self.data, self.sent, self.next_at = b"", 0, now

    def due(self, now, rate):
        if self.sent >= len(self.data) or now < self.next_at:
            return b""
        chunk = self.data[self.sent:self.sent + max(96, rate // 10)]
        self.sent += len(chunk)
        self.next_at = now + len(chunk) / rate
        return chunk

    def wait(self, now):
        return max(0.0, self.next_at - now) if self.sent < len(self.data) else None


class Canvas:
    """A moving picture a program draws itself (PotatoTube HD, Doom). It
    sends screenful after screenful down conn (pictures.Canvas); only the
    latest is shown, as fast as the cable carries them, and it's told when
    each is on the screen and which keys go down and up at the Compaq.
    PILINK only: Kermit can't keep up."""

    moving = True
    more = False
    caption = ""

    def __init__(self, layout, conn, now, lobby=False):
        self.layout, self.conn, self.lobby = layout, conn, lobby
        self.started = self.heard = now
        self.via = None
        self.buffer = bytearray()
        self.shared_at = 0.0

    def wait(self, now):
        return None

    def frames(self, data):
        """Takes bytes from the program; returns the newest whole screenful
        (packed rows), None if there isn't one yet, or False if what came
        isn't a screenful at all. Each is "F", 4 bytes of length, the rows."""
        self.buffer += data
        size, newest = self.layout.frame_bytes, None
        while len(self.buffer) >= 5:
            if self.buffer[0] != ord("F") or int.from_bytes(self.buffer[1:5], "big") != size:
                return False
            if len(self.buffer) < 5 + size:
                break
            newest = bytes(self.buffer[5:5 + size])
            del self.buffer[:5 + size]
        return newest


def read_request(conn):
    """One JSON request line from the control socket, or None."""
    conn.settimeout(5)
    try:
        request = json.loads(conn.makefile().readline(MAX_PICTURE) or "null")
    except (OSError, ValueError):
        return None
    conn.settimeout(None)
    return request if isinstance(request, dict) else None


def reply(conn, answer):
    """Sends the answer; False if the requester had already given up."""
    try:
        conn.sendall((json.dumps(answer) + "\n").encode())
        return True
    except OSError:
        return False


class Bridge:
    def __init__(self, device, baud):
        self.device, self.baud = device, baud
        self.rate = int(baud) // 10                  # bytes a second the cable carries, at Kermit's speed
        self.line = os.open(device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        setup_line(self.line, baud)
        self.port = Port(self.line, baud, paced=TV)
        self.link = pilink.Link(self.port, baud)     # PILINK, when the Compaq has it
        # Which terminal the Compaq uses: "kermit" (VT102 text down the
        # cable) or "pilink" (PILINK started by PI.BAT; the text goes into
        # self.vt and through the link). Kept across restarts of the bridge.
        self.mode, self.vt = "kermit", None
        if USE_PILINK and read_status("terminal") == "pilink":
            self.use("pilink")
        self.held, self.held_since = b"", 0.0       # an escape that may start a PILINK hello
        self.lost_at = -1e9                          # when the terminal PILINK stopped answering
        self.hello_asked = -1e9                      # when the bridge last asked who's there
        self.beeps = collections.deque()             # (when, timer divisor) for the Compaq's speaker
        self.pilink_line, self.resends_said, self.resends_at = "", 0, 0.0   # (the pilink status file: link_news)
        self.scene_tick = 0.0                        # PAL's eye in dots: when it next pulses
        self.link_failures = 0
        self.linger_until = 0.0                      # PILINK stays up until then, with no picture
        self.text_at = 0.0                           # Kermit is a terminal again from then
        self.repaint_due = False
        self.native = None                           # (connection, title): a DOS program the Pi started is running

        try:
            os.unlink(SOCKET)
        except FileNotFoundError:
            pass
        self.control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.control.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        self.control.listen(4)

        self.client_pid, self.client = start_client()
        if self.mode == "kermit":
            write_all(self.line, WRAP_ON)
        self.last_key = 0.0                      # last key at the Compaq
        self.last_activity = time.monotonic()    # last key or screen change
        self.was_ready = compaq_ready(self.line)
        write_status(link_status(self.was_ready))
        self.saver = Saver()
        self.scene = pal_screen.Scene()
        self.scene_from_saver = False
        self.pal_heard = 0.0                     # PAL's last request
        self.asleep_since = 0.0                  # wall clock: saver or scene took over
        self.checked = 0.0
        self.recheck = False
        self.scene_started = 0.0
        self.picture = None                      # what's being shown (a Picture or a Canvas)
        self.pictures_shown = 0
        self.unshare_picture()                   # (one left behind by a crash)
        write_speed(baud)

    # ---------------------------------------------------------- the screen

    def use(self, mode):
        """Which terminal the Compaq uses from now on (see __init__)."""
        if mode == "pilink" and self.vt is None:
            self.vt = text_screen.TextScreen()
        elif mode == "kermit":
            self.vt = None
        self.mode = mode
        write_status(mode, runtime_file("terminal"))

    def text(self, data):
        """VT102 text for the Compaq's screen: down the cable to Kermit, or
        into the copy of the screen PILINK shows."""
        if self.mode == "pilink":
            self.vt.feed(data)
        else:
            write_all(self.line, data)

    def redraw(self):
        redraw(self.text, self.client_pid)

    def scene_in_dots(self):
        """PAL's scene or board, drawn in real dots (PILINK is the terminal)."""
        return self.scene.active and self.link.terminal and self.link.state == "on" and not self.picture

    def show_text(self, now):
        """PILINK is the terminal: send it what changed on the text screen,
        or PAL's scene in dots."""
        if self.scene_in_dots():
            animating = pal_screen.animating(self.scene)
            if (self.scene.changed or animating) and now >= self.scene_tick:
                layout = pilink.PLASMA_640 if self.link.plasma else pilink.CGA_640
                self.link.show(layout, layout.pack(pal_screen.dots(self.scene, layout.height, now)), now)
                self.scene.changed = False
                # At most 5 drawings a second (the link sends only the newest
                # anyway), and when it pulses, on the next half second.
                self.scene_tick = max(now + 0.2, (int(now * 2) + 1) / 2) if animating else now + 0.2
            return
        if (self.vt and self.vt.dirty and self.link.terminal and self.link.state == "on"
                and not self.picture):
            memory, cursor = self.vt.cells()
            self.link.show(pilink.TEXT_80, memory, now, cursor=cursor)

    def beep(self, notes, now):
        """Plays notes ([[hertz (0: quiet), seconds], ...]) on the Compaq's
        own speaker, through PILINK as the terminal. False if it can't."""
        if TV or not (self.link.terminal and self.link.state == "on") or not isinstance(notes, list):
            return False                 # (the TV has no PC speaker: PAL uses its own)
        at = max(now, self.beeps[-1][0] if self.beeps else now)
        for note in notes[:64]:
            try:
                hertz, seconds = float(note[0]), min(2.0, max(0.0, float(note[1])))
            except (TypeError, ValueError, IndexError):
                return False
            self.beeps.append((at, round(1193182 / hertz) if 37 <= hertz <= 20000 else 0))
            at += seconds
        self.beeps.append((at, 0))
        return True

    def play_beeps(self, now):
        while self.beeps and self.beeps[0][0] <= now:
            _, divisor = self.beeps.popleft()
            if self.link.terminal and self.link.state == "on":
                self.port.queue(bytes((pilink.SOUND,)) + pilink.word(divisor))
            else:
                self.beeps.clear()

    def graphics(self):
        """A picture is up, or PILINK still has the Compaq's screen (as a
        picture program; as its terminal it's the text's)."""
        return self.picture is not None or (self.link.state != "off" and not self.link.terminal)

    def asleep(self):
        """The Compaq shows the saver, PAL or a picture instead of the shared screen."""
        return self.saver.on or self.scene.active or self.graphics()

    def fall_asleep(self):
        if not self.asleep():
            self.asleep_since = time.time()

    def someone_typed(self):
        """Has anyone in a browser pressed a key since the Compaq fell
        asleep? (A key at the Compaq comes down the cable, and wakes it
        there.) Asks tmux at most every 2 seconds; when it's too soon to
        ask, the loop asks again shortly (recheck), so a keypress isn't
        missed. tmux counts in whole seconds, so a key in the second the
        Compaq fell asleep (often the very key that asked for a picture)
        doesn't count."""
        now = time.monotonic()
        if now - self.checked < 2:
            self.recheck = True
            return False
        self.checked, self.recheck = now, False
        return last_typed(skip_pid=self.client_pid) > self.asleep_since

    def menu_key(self, now):
        """F10 (Ctrl-\\) at the Compaq: back to the main menu from anything,
        even a picture PAL put up (FixBot's page, the mirror: its owner hears
        "menu") or PAL's own screen, not just from the program underneath."""
        if self.picture:
            self.end_picture("menu", now, pilink.MENU_KEY)
        if self.asleep():
            self.wake(now)
        self.last_activity = self.last_key = now
        write_all(self.client, pilink.MENU_KEY)

    def wake(self, now):
        """Back to the shared screen, from the saver, PAL or a picture."""
        if self.picture:
            self.end_picture("a key", now)
        if self.scene.active:
            self.text(self.scene.end())
        self.saver.on = False
        self.last_activity = self.last_key = now
        self.repaint(now)

    def repaint(self, now):
        """The shared screen again, as soon as the Compaq is a terminal: at
        once, or (the loop sees to it) when PILINK has handed back to
        Kermit."""
        if (self.link.state == "off" or self.link.terminal) and now >= self.text_at and not self.asleep():
            self.repaint_due = False
            self.redraw()
        else:
            self.repaint_due = True

    def end_scene(self, now):
        """PAL is done: back to the saver if that's where it started, or to
        the shared screen."""
        self.text(self.scene.end())
        if self.scene_from_saver:
            self.saver.start(self.text)
        else:
            self.last_activity = now
            self.redraw()

    def can_link(self):
        """Is PILINK worth asking for? (Not if this Compaq has already
        turned out not to have it, or isn't there at all. With PILINK as the
        terminal, only while it's there.)"""
        if self.mode == "pilink":
            return self.link.terminal
        return USE_PILINK and self.link.available is not False and (TV or compaq_ready(self.line))

    def take_screen(self, now):
        """Clears the way for a picture: the last one, PAL, the saver."""
        if self.picture:
            self.end_picture("another picture", now)
        if self.scene.active:
            self.text(self.scene.end())    # (PAL hears "not shown" next time it asks)
        self.saver.on = False
        self.fall_asleep()

    def show_picture(self, request, conn, now):
        """A program (or PAL) asks for a picture: {"op": "picture", "image":
        base64 of a picture file, "caption": text, "more": another will
        follow}. Answers {"showing": seconds to paint} once it's on its way
        and {"done": why} when it comes down; the connection stays open
        until then."""
        caption = printable(request.get("caption", ""), 79)
        try:
            image = pictures.from_bytes(base64.b64decode(str(request.get("image", "")), validate=True))
            image.load()
        except Exception:        # (not a picture, or one PIL can't read)
            reply(conn, {"showing": False, "message": "That isn't a picture I can show."})
            conn.close()
            return
        self.take_screen(now)
        self.picture = Picture(image, caption, conn, now, bool(request.get("lobby")), bool(request.get("more")))
        self.start_picture(now)

    def open_canvas(self, request, conn, now):
        """A program asks to draw a moving picture itself: {"op": "canvas",
        "layout": "320x200" (see pilink.LAYOUTS)}. Answers {"canvas": True,
        "layout", "width", "height", "bps"} once PILINK is running, or
        {"canvas": False, "message"}; then see Canvas."""
        layout = pilink.LAYOUTS.get(str(request.get("layout", "320x200")))
        if layout is None or not self.can_link():
            reply(conn, {"canvas": False, "message": "This screen can't show moving pictures right now."
                         if layout else "There's no such picture size."})
            conn.close()
            return
        self.take_screen(now)
        self.picture = Canvas(layout, conn, now, bool(request.get("lobby")))
        self.start_picture(now)

    def start_picture(self, now):
        """Gets the waiting picture going: through PILINK if the Compaq has
        it (asking Kermit to start it first), else as sixels."""
        if self.link.state == "on":
            self.paint(now)
        elif self.link.state != "off" or now < self.text_at:
            pass                                      # (starting or stopping: the loop comes back)
        elif self.mode == "pilink":                   # (the Compaq isn't running PI.BAT right now)
            self.end_picture("no screen", now)
        elif self.can_link():
            self.link.start(now)
        elif self.picture.moving:
            self.end_picture("no graphics", now)
            self.repaint(now)
        else:
            self.paint_sixels(now)

    def paint(self, now):
        """PILINK is running: the waiting picture goes to it."""
        picture = self.picture
        picture.via = "link"
        if picture.moving:
            if picture.layout is pilink.PLASMA_640 and not self.link.plasma:
                picture.layout = pilink.CGA_640       # (no 640x400 on this machine: the program adapts)
            layout = picture.layout
            answer = {"canvas": True, "layout": layout.name, "width": layout.width, "height": layout.height,
                      "bps": self.link.bps}
        else:
            layout = pilink.PLASMA_640 if self.link.plasma else pilink.CGA_640
            dots = pictures.dots(picture.image, picture.caption, layout.height)
            self.link.show(layout, layout.pack(dots), now)
            answer = {"showing": round(self.link.frame_bytes / self.link.bps + 0.3, 1)}
            if not picture.lobby:
                self.share_picture(Image.fromarray(dots), picture.caption)
        if not reply(picture.conn, answer):
            self.end_picture("let go", now)
            self.repaint(now)

    def paint_sixels(self, now):
        """No PILINK: Kermit draws the picture itself, at its own speed."""
        picture = self.picture
        picture.via = "kermit"
        picture.data, whole = pictures.screen(picture.image, picture.caption)
        picture.next_at = now
        if not reply(picture.conn, {"showing": round(len(picture.data) / self.rate, 1)}):
            self.end_picture("let go", now)
            self.repaint(now)
        elif not picture.lobby:
            self.share_picture(whole, picture.caption)

    def canvas_heard(self, now):
        """The program holding a canvas sent something (or hung up)."""
        canvas = self.picture
        try:
            data = canvas.conn.recv(262144)
        except OSError:
            data = b""
        newest = canvas.frames(data) if data else False
        if newest is False:
            self.end_picture("let go", now)
            self.repaint(now)
            return
        if newest is None or canvas.via != "link":
            return
        canvas.heard = now
        self.link.show(canvas.layout, canvas.layout.arrange(newest), now, sweep=True)
        if not canvas.lobby and now - canvas.shared_at >= SHARE_EVERY:
            canvas.shared_at = now
            rows = np.frombuffer(newest, np.uint8).reshape(canvas.layout.height, -1)
            self.share_picture(Image.fromarray(np.unpackbits(rows, axis=1).astype(bool)), "")

    def link_news(self, now):
        """What PILINK's link has to report (see pilink.Link)."""
        lost = sum(self.link.losses.values())
        if lost != self.resends_said and self.pilink_line and now - self.resends_at > 5:
            # (for ./check.sh: lost bytes are the first suspect when pictures
            # crawl, and why they were lost says what to fix)
            self.resends_said, self.resends_at = lost, now
            why = "; ".join(f"{n}x {reason}" for reason, n in self.link.losses.most_common(3))
            write_status(f"{self.pilink_line}; bytes lost {lost} times ({why}): {self.link.repairs} frames "
                         f"repaired, {self.link.resends} screens sent again", runtime_file("pilink"))
        while self.link.events:
            event = self.link.events.pop(0)
            picture = self.picture
            if event[0] == "up":
                self.link_failures = 0
                # (for ./check.sh: what PILINK managed on this Compaq)
                self.pilink_line = (f"{self.link.speed} baud, {'640x400' if self.link.plasma else '640x200'} dots"
                                    + (", the whole terminal" if self.link.terminal else ""))
                write_status(self.pilink_line, runtime_file("pilink"))
                if self.link.terminal:
                    self.terminal_up(now)
                    if self.native:                   # a DOS program the Pi started has ended
                        native, self.native = self.native[0], None
                        reply(native, {"back": True})
                        native.close()
                if picture and picture.via is None:
                    self.paint(now)
                else:
                    self.linger_until = now
            elif event[0] == "shown":
                if picture and picture.moving and not reply(picture.conn, {"ready": True}):
                    self.end_picture("let go", now)
                    self.repaint(now)
            elif event[0] == "key":
                _, key, pressed, typed = event
                self.last_activity = self.last_key = now
                if typed == pilink.MENU_KEY:          # F10: the main menu, whatever is showing
                    self.menu_key(now)
                elif self.link.terminal and not (picture and picture.moving):
                    if pressed and typed:             # the Compaq's terminal: typing, as from Kermit
                        self.compaq_typed(typed, now)
                elif picture and picture.moving:
                    reply(picture.conn, {"key": key, "down": pressed, "typed": typed.decode("latin-1")})
                elif picture and pressed and typed:   # a key takes a still picture down (and is swallowed)
                    self.end_picture("a key", now, typed)
                    self.wake(now)
                elif pressed and typed and not picture:   # between pictures: typed blind, but typed
                    write_all(self.client, typed)
            elif event[0] == "down":
                why = event[1]
                self.text_at = now + (KERMIT_BACK if why != "absent" else 0)
                if self.mode == "pilink":             # the terminal went (a transfer, or the Compaq left)
                    self.text_at = now
                    if why == "lost":                 # (it'll be back at its first speed after 15 quiet seconds)
                        self.lost_at = now
                    write_speed(self.baud)
                    self.was_ready = compaq_ready(self.line)
                    write_status(link_status(self.was_ready))
                    if picture:
                        self.end_picture("a key" if why == "left" else "lost", now)
                    continue
                if why != "stopped":
                    self.link_failures += 1
                    if self.link_failures >= 2:       # (twice running: sixels for this connection)
                        self.link.available = False
                    if self.link.available is False:
                        write_status("not on the Compaq's disk" if why == "absent" else "not answering",
                                     runtime_file("pilink"))
                if picture and picture.via == "link":             # it was showing, and PILINK has gone
                    self.end_picture("a key" if why == "left" else "lost", now)
                    picture = None
                if picture is None:
                    self.repaint(now)
                # (a picture still waiting is started again by the loop)

    def terminal_up(self, now):
        """PILINK started by itself (PI.BAT) and is up: it's the Compaq's
        terminal now. The whole screen goes to it, from scratch."""
        if self.mode != "pilink":
            self.use("pilink")
        write_speed(self.link.speed)                 # (text goes at the link's speed now: PotatoTube's pace)
        write_status(link_status(True))              # (the Compaq is there: Kermit never opened the port to say so)
        self.vt = text_screen.TextScreen()
        if self.scene.active:
            self.scene.end()
        self.saver.on = False
        self.last_activity = self.last_key = now
        if not self.picture:
            self.redraw()

    def compaq_typed(self, data, now):
        """Something typed at the Compaq (through Kermit or PILINK)."""
        self.last_activity = now
        if self.asleep() and pilink.MENU_KEY in data:   # (F10 isn't dropped: the menu, from anything)
            self.menu_key(now)
            return
        if self.asleep():   # a key at the Compaq wakes it; the key itself is dropped
            if self.picture:
                self.end_picture("a key", now, data)    # (but a picture's owner hears it)
            self.wake(now)
            return
        if self.mode == "kermit" and now - self.last_key > QUIET_SECONDS:
            self.redraw()
        self.last_key = now
        write_all(self.client, data)

    def leave_terminal(self, now):
        """Asks PILINK, as the terminal, to go back to DOS so PI.BAT starts
        Kermit for a transfer; waits (a few seconds at most) until it has."""
        if not self.link.leave(pilink.KERMIT_EXIT, now):
            return False
        if not self.await_link(lambda: self.link.state == "off", 3.0):
            self.link.down("stopped")
        self.link_news(time.monotonic())
        return True

    def await_link(self, done, seconds):
        """Keeps the cable going, and only the cable, until done() or for
        seconds at most. Returns done()."""
        deadline = time.monotonic() + seconds
        while not done() and time.monotonic() < deadline:
            self.port.pump(time.monotonic())
            ready, _, _ = select.select([self.line], [self.line] if self.port.writable() else [], [], 0.1)
            if self.line in ready:
                try:
                    self.link.feed(os.read(self.line, 4096), time.monotonic())
                except BlockingIOError:
                    pass
            self.link.tick(time.monotonic())
        return done()

    def no_dos(self):
        """Why the Pi can't start DOS programs on the Compaq now ("": it can)."""
        if TV:
            return "DOS programs need the Compaq itself; the TV is only standing in."
        if self.mode != "pilink" or not self.link.terminal or self.link.state != "on":
            return "The Compaq isn't running PI right now."
        if (self.link.version or 1) < 3:
            return ("This Compaq's PILINK is too old to start DOS programs: it needs the new Kermit disk "
                    "(A:INSTALL at its DOS prompt).")
        if self.picture:
            return "The Compaq is showing a picture. Try again in a moment."
        return ""

    def ask_there(self, request, now):
        """{"op": "there", "name": a DOS name}: is that file on the Compaq's disks?"""
        name = str(request.get("name", ""))
        why = self.no_dos()
        if why or not self.link.there(name, now):
            return {"ok": False, "message": why or "That isn't a DOS name the Compaq can look for."}
        answer = []

        def answered():
            for event in self.link.events:
                if event[0] == "there" and event[1] == name:
                    self.link.events.remove(event)
                    answer.append(event[2])
                    return True
            return self.link.state != "on"
        self.await_link(answered, 5.0)
        if not answer or answer[0] is None:
            return {"ok": False, "message": "The Compaq didn't answer."}
        return {"ok": True, "there": answer[0]}

    def run_dos(self, request, conn, now):
        """A program asks for a DOS program on the Compaq itself: {"op":
        "run", "batch": a batch file's lines (ending by starting PI again),
        "title": what it is}. PILINK, as the Compaq's terminal, writes it as
        C:\\PI\\PIRUN.BAT and goes to DOS, which runs it. The answer:
        {"ok": True} once it has gone, then {"back": True} when PI is back
        (the program has ended); or {"ok": False, "message": why not}. The
        connection is kept until then."""
        why = self.no_dos()
        if not why and self.scene.active:
            self.text(self.scene.end())
        if not why and not self.link.run(str(request.get("batch", "")), now):
            why = "That's too long for one batch file on the Compaq."
        if not why:
            failed = ("ran", False)
            self.await_link(lambda: self.link.state == "off" or failed in self.link.events, 12.0)
            if failed in self.link.events:
                self.link.events.remove(failed)
                why = "The Compaq couldn't write C:\\PI\\PIRUN.BAT (no C:\\PI folder, or a full disk?)."
            elif self.link.state != "off":
                self.link.down("stopped")
        if why:
            reply(conn, {"ok": False, "message": why})
            conn.close()
            return
        if self.native:                              # (an earlier asker is waiting still: it won't hear)
            self.native[0].close()
        title = str(request.get("title") or "a DOS program")[:60]
        self.native = (conn, title)
        reply(conn, {"ok": True})
        self.link_news(time.monotonic())
        write_status(f"running {title} on the Compaq itself (DOS); the Pi gets it back when it ends",
                     runtime_file("pilink"))

    def share_picture(self, whole, caption):
        """The picture for browsers watching the shared screen (the web
        server lays it over their screen): picture.png, in the plasma's two
        colours, and picture.json, next to bridge.sock."""
        self.pictures_shown += 1
        base = os.path.join(os.path.dirname(SOCKET), "picture")
        whole = whole.convert("1")
        image = Image.new("P", whole.size, 0)
        image.putpalette([19, 5, 0, 255, 106, 22])      # the web page's glass and amber
        image.paste(1, (0, 0, *whole.size), whole)
        try:
            image.save(base + ".png.new", "PNG")
            os.replace(base + ".png.new", base + ".png")
            with open(base + ".json.new", "w") as f:
                json.dump({"id": self.pictures_shown, "caption": caption}, f)
            os.replace(base + ".json.new", base + ".json")
        except OSError:
            pass

    def unshare_picture(self):
        for name in ("picture.json", "picture.png"):
            try:
                os.unlink(os.path.join(os.path.dirname(SOCKET), name))
            except OSError:
                pass

    def end_picture(self, why, now, key=b""):
        """The picture comes down (the caller sees to the text coming
        back). Whoever showed it hears why, and which key (so a slideshow
        can go on or stop). PILINK, if it drew it, stays up a moment: the
        next picture may be on its way."""
        picture, self.picture = self.picture, None
        self.unshare_picture()
        if picture.via == "kermit":
            write_all(self.line, pictures.LEAVE)
        elif self.link.terminal and self.vt:
            self.vt.touch()                           # (the text comes back)
        elif self.link.state != "off":
            self.linger_until = now + (LINGER_MORE if picture.more and why == "a key" else LINGER)
        if picture.moving and picture.via is None:
            reply(picture.conn, {"canvas": False, "message": "This screen can't show moving pictures right now."})
        else:
            reply(picture.conn, {"done": why, "key": key[:8].decode("latin-1")})
        picture.conn.close()

    def compaq_busy(self, now, requested=False):
        """Why PAL mustn't cover the Compaq ("": it may). Someone is using
        it: they typed, here or on the web, in the last PAL_IDLE_SECONDS.
        Something a person in the lobby asked PAL for (a chat they started
        by saying its name, the mirror, a photo) only waits for browsers: the
        person at the lobby keyboard is the one asking."""
        if self.saver.on:
            return ""
        if requested:
            web = time.time() - last_typed(skip_pid=self.client_pid)
            return f"typed on the web {web:.0f} s ago" if web < 30 else ""
        key, typed = now - self.last_key, time.time() - last_typed()
        if key < PAL_IDLE_SECONDS:
            return f"a key at the Compaq {key:.0f} s ago"
        if typed < PAL_IDLE_SECONDS:
            return f"typed on the web {typed:.0f} s ago"
        return ""

    def pal(self, request, now):
        """One request from PAL: begin, say, status or end its scene."""
        self.pal_heard = now
        action = request.get("action")
        canvas = bool(request.get("canvas"))
        if action == "beep":            # the Compaq's own speaker: no scene needed
            return {"ok": True, "beeped": self.beep(request.get("notes"), now)}
        if action == "begin" and (not self.scene.active or canvas != (self.scene.canvas is not None)):
            if self.graphics():
                print("pal: its screen not shown: a picture is up", file=sys.stderr, flush=True)
                return {"ok": True, "shown": False}      # a picture is up: it isn't PAL's to cover
            busy = "" if self.scene.active else self.compaq_busy(now, bool(request.get("requested")))
            if busy:
                # (for the log: "PAL's eye didn't come up" is otherwise a mystery)
                print(f"pal: its screen not shown: someone's using the Compaq ({busy})", file=sys.stderr, flush=True)
                return {"ok": True, "shown": False}
            if not self.scene.active:
                self.scene_from_saver = self.saver.on
                self.scene_started = now
                self.fall_asleep()
                self.saver.on = False
            self.scene.name = printable(request.get("name") or "PAL 286", 20)
            self.text(self.scene.begin(now, canvas=canvas))
        elif not self.scene.active:
            return {"ok": True, "shown": False}
        elif action == "say":
            try:
                cps = min(200.0, max(5.0, float(request.get("cps", 40))))
            except (TypeError, ValueError):
                cps = 40.0
            self.scene.say("pal" if request.get("who") == "pal" else "human",
                           printable(request.get("text", ""), 800), cps)
        elif action == "frame":
            rows = request.get("lines")
            if isinstance(rows, list):
                self.text(self.scene.frame([printable(r, 79) for r in rows[:24]]))
            if self.scene.canvas is not None:                    # (what it means, for dots)
                self.scene.board, self.scene.changed = pal_screen.board(request.get("board")), True
        elif action == "status":
            self.text(self.scene.status(printable(request.get("text", ""), 60),
                                                   bool(request.get("blink"))))
        elif action == "end":
            if request.get("wake"):     # PAL opened a program: show it
                self.wake(now)
            else:
                self.end_scene(now)
            return {"ok": True, "shown": False}
        return {"ok": True, "shown": True}

    def from_compaq(self, data, now, hold=True):
        """Bytes from the cable: PILINK's messages, or keys typed at Kermit.
        A PILINK hello (ESC _ P L ...) is never typing, and starts a
        terminal; an escape at the very end, or a hello not finished yet,
        is held back a moment in case the rest follows. (The real cable's
        USB adapter hands a hello over a few bytes at a time.)"""
        if self.link.state != "off":            # PILINK talking: keys, and its answers
            self.link.feed(data, now)
            self.link_news(now)
            return
        if USE_PILINK and hold and unfinished_hello(data):
            self.held, self.held_since = data, now
            return
        if USE_PILINK and pilink.HELLO_START[:2] in data:
            self.link.feed(data, now)           # (a terminal PILINK saying hello)
            if self.link.terminal and self.mode != "pilink":
                self.use("pilink")              # (at once: text sent now would be taken for commands)
            self.link_news(now)
            return
        if USE_PILINK and hold and data.endswith(b"\x1b"):
            self.held, self.held_since = data, now
            return
        chatter = USE_PILINK and PILINK_CHATTER.search(data)
        if chatter or (self.mode == "pilink" and now - self.lost_at < REGAIN):
            # PILINK out of step with the Pi (or perhaps, just after it
            # stopped answering, at another speed): never typing. Echoed back
            # as Kermit text, its "N" and "R" are commands to it, and the two
            # answered each other all night (2026-11-03). Asked who's there it
            # says hello, and is taken up again; left quiet, it starts over
            # at its first speed and says hello by itself.
            if self.mode != "pilink":
                self.use("pilink")
            if chatter and now - self.hello_asked > 2.0:
                self.port.queue(bytes((pilink.HELLO,)))
                self.hello_asked = now
            return
        if self.mode == "pilink":
            self.use("kermit")                  # someone started Kermit by hand: text goes to it again
            write_all(self.line, WRAP_ON)
            self.wake(now)
            return
        self.compaq_typed(data, now)

    # ---------------------------------------------------------- the loop

    def run(self):
        while True:
            now = time.monotonic()
            waits = [5, self.scene.wait(now), self.link.wait(now), self.port.wait(now)]
            if self.picture:
                waits.append(self.picture.wait(now))
            if self.link.state == "on" and not self.picture and not self.link.terminal:
                waits.append(max(0.0, self.linger_until - now))
            if self.held:
                waits.append(max(0.0, self.held_since + HOLD_HELLO - now))
            if self.beeps:
                waits.append(max(0.0, self.beeps[0][0] - now))
            if self.scene_in_dots() and (self.scene.changed or pal_screen.animating(self.scene)):
                waits.append(max(0.02, self.scene_tick - now))
            if self.repaint_due or (self.picture and self.picture.via is None):
                waits.append(max(0.05, self.text_at - now))
            watch = [self.line, self.client, self.control] + ([self.picture.conn] if self.picture else [])
            ready, _, _ = select.select(watch, [self.line] if self.port.writable() else [], [],
                                        min(w for w in waits if w is not None))
            now = time.monotonic()

            # Kermit just opened the port on the Compaq: show it the screen.
            # (While PILINK runs the port is its business: Kermit lets go
            # of it and takes it back, which isn't the Compaq arriving.)
            if self.link.state == "off":
                is_ready = compaq_ready(self.line)
                if is_ready and not self.was_ready and self.mode == "kermit":
                    self.link.available = self.link.best = self.link.plasma = None   # (perhaps another disk)
                    self.link_failures = 0
                    self.wake(now)
                if is_ready != self.was_ready:
                    write_status(link_status(is_ready))
                self.was_ready = is_ready

            moving = bool(self.picture and self.picture.moving)   # (its program takes the keys itself)
            if (self.asleep() and not moving and self.recheck and now - self.checked >= 2
                    and self.someone_typed()):
                self.wake(now)
            if self.picture:
                picture = self.picture
                silent = now - (picture.heard if picture.moving else picture.started)
                if picture.moving and picture.conn in ready:
                    self.canvas_heard(now)
                elif picture.conn in ready or silent > PICTURE_LONGEST:
                    # Whoever asked has let go (moved on, or quit), or it's
                    # been up long enough: back to the shared screen.
                    self.end_picture("let go" if picture.conn in ready else "time", now)
                    self.wake(now)
                elif picture.via == "kermit":
                    write_all(self.line, picture.due(now, self.rate))
                elif picture.via is None and self.link.state == "off" and now >= self.text_at:
                    self.start_picture(now)
            elif self.link.state == "on" and now >= self.linger_until and not self.link.terminal:
                self.link.stop(now)                   # no picture followed: Kermit again
            self.link.tick(now)
            self.link_news(now)
            if self.held and now - self.held_since >= HOLD_HELLO:   # no hello followed: a key after all
                held, self.held = self.held, b""
                self.from_compaq(held, now, hold=False)
            if self.repaint_due and not self.picture:
                self.repaint(now)

            if self.scene.active:
                self.text(self.scene.due(now))
                if ((now - self.pal_heard > PAL_TIMEOUT and not self.scene.queue)
                        or now - self.scene_started > PAL_LONGEST):
                    self.end_scene(now)
            elif self.saver.on:
                self.saver.tick(self.text)
            elif not self.asleep() and now - self.last_activity > SAVER_SECONDS:
                # Quiet here for a while; but has anyone typed elsewhere (a
                # browser)? A program's own clock doesn't count: calcurse or
                # IRC redrawing a clock mustn't keep the plasma lit all night.
                typed = last_typed()
                if time.time() - typed < SAVER_SECONDS:
                    self.last_activity = now - (time.time() - typed)
                else:
                    self.fall_asleep()
                    self.saver.start(self.text)

            if self.client in ready:
                try:
                    data = os.read(self.client, 4096)
                except OSError:
                    data = b""
                if not data:  # tmux client ended (session restarting): reattach
                    os.close(self.client)
                    os.waitpid(self.client_pid, 0)
                    time.sleep(2)
                    self.client_pid, self.client = start_client()
                    continue
                if self.asleep():
                    # Only a change someone typed wakes the Compaq; output that
                    # arrives while it sleeps is dropped and repainted on waking.
                    if not (self.picture and self.picture.moving) and self.someone_typed():
                        self.wake(now)
                    continue
                self.text(data)

            if self.line in ready:
                try:
                    data = os.read(self.line, 4096)
                except BlockingIOError:
                    data = None
                if data == b"":
                    sys.exit("serial line closed")
                if data:
                    data, self.held = self.held + data, b""
                    self.from_compaq(data, now)

            self.show_text(now)
            self.play_beeps(now)
            self.port.pump(now)

            if self.control in ready:
                conn, _ = self.control.accept()
                request = read_request(conn)
                if request is not None and request.get("op") == "picture":
                    self.show_picture(request, conn, now)     # (keeps the connection)
                    continue
                if request is not None and request.get("op") == "canvas":
                    self.open_canvas(request, conn, now)      # (keeps the connection)
                    continue
                if request is not None and request.get("op") == "run":
                    self.run_dos(request, conn, now)          # (keeps the connection)
                    continue
                with conn:
                    if request is None:
                        continue
                    if request.get("op") == "pal":
                        was_shown = self.scene.active
                        if not reply(conn, self.pal(request, now)) and self.scene.active and not was_shown:
                            self.end_scene(now)    # PAL gave up waiting: don't strand its eye
                        continue
                    if request.get("op") == "text":   # no more pictures: PILINK needn't wait for one
                        self.linger_until = now
                        reply(conn, {"ok": True})
                        continue
                    if request.get("op") == "there":
                        reply(conn, self.ask_there(request, now))
                        continue
                    if self.graphics():        # a transfer needs Kermit, and the cable
                        reply(conn, {"ok": False, "message": "The Compaq is showing a picture. Try again in a moment."})
                        continue
                    server = self.mode == "pilink"
                    if TV:
                        reply(conn, {"ok": False, "message": "File transfers need the Compaq itself; "
                                     "the TV is only standing in."})
                        continue
                    if server and not self.link.terminal:
                        reply(conn, {"ok": False, "message": "The Compaq isn't running PI right now (type PI at its "
                                     "DOS prompt)."})
                        continue
                    if server and request.get("op") == "receive" and not request.get("files"):
                        reply(conn, {"ok": False, "need": "files",
                                     "message": "Which files? A DOS name, like C:\\LETTER.TXT or *.TXT."})
                        continue
                    if self.scene.active:
                        self.text(self.scene.end())
                    if server and not self.leave_terminal(now):
                        reply(conn, {"ok": False, "message": "This Compaq's PILINK is too old for transfers: "
                                     "./make-disks.sh, and the new Kermit disk."})
                        continue
                    reply(conn, transfer(request, conn, self.line, self.device, self.baud, server))
                    os.set_blocking(self.line, False)
                self.saver.on = False
                self.last_activity = self.last_key = time.monotonic()   # a transfer isn't idle time
                self.redraw()


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip())
    baud = sys.argv[2] if len(sys.argv) > 2 else cable_speed()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        Bridge(sys.argv[1], baud).run()
    finally:
        write_status("not connected")


if __name__ == "__main__":
    main()
