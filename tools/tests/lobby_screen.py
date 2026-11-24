# The lobby simulator's Compaq screen (lobby_sim.sh starts it, as desk):
# the TV stand-in (tv_terminal.py) playing a Compaq running PI, drawn into a
# pretend 640x400 plasma instead of the TV, behind its own serial bridge.
# What it shows is saved as /tmp/lobbysim/screen/screen.png every second,
# and writing to the pipe /tmp/lobbysim/screen/keyboard types on its keyboard.
# Usage (lobby_sim.sh): python3 -I - < lobby_screen.py
import os, pty, sys, threading, time, tty, types
sys.path.insert(0, "/opt/compaq/lib")
import numpy as np
from PIL import Image, ImageFont
import tv_terminal as tv

SIM = "/tmp/lobbysim/screen"            # (desk's own folder in the simulator's)


class Plasma(tv.Display):
    """The Compaq's own 640x400 screen, dot for dot, as an array."""

    def __init__(self):
        self.width, self.height, self.depth, self.scale = 640, 400, 32, 1
        self.pixels = np.zeros((self.height, self.width), np.uint32)
        self.cw, self.ch = 8, 16
        self.left, self.top = 0, (self.height - self.ch * tv.ROWS) // 2
        self.font = ImageFont.truetype(tv.FONT, 16)
        self.size, self.cache = "real", {}

    def set_size(self, size):
        pass


display = Plasma()
tv.Display = lambda: display
tv.fcntl = types.SimpleNamespace(ioctl=lambda *args: 0)      # (no console to put into graphics mode)
tv.showing = lambda console: True
keyboard, console = pty.openpty()
tty.setraw(console)
sys.stdin = os.fdopen(console)
KEYS = f"{SIM}/keyboard"
if os.path.exists(KEYS):
    os.remove(KEYS)
os.mkfifo(KEYS)
os.chmod(KEYS, 0o622)


def type_keys():
    while True:
        with open(KEYS, "rb", buffering=0) as f:
            for chunk in iter(lambda: f.read(256), b""):
                os.write(keyboard, chunk)


def keep_saving():
    while True:
        p = display.pixels
        rgb = np.stack([(p >> 16) & 255, (p >> 8) & 255, p & 255], -1).astype(np.uint8)
        Image.fromarray(rgb).save(f"{SIM}/.screen.png")
        os.replace(f"{SIM}/.screen.png", f"{SIM}/screen.png")
        time.sleep(1)


threading.Thread(target=type_keys, daemon=True).start()
threading.Thread(target=keep_saving, daemon=True).start()
tv.main()
