# The PAL simulator's own screen, so its tests don't draw on the lobby's:
# the TV stand-in (tv_terminal.py) drawing into a pretend display, behind a
# private serial bridge (/tmp/pal-sim/bridge.sock) and a private tmux server
# (tmux -L palsim). run_sim.sh starts it, as pal, and points the simulated
# PAL at it (COMPAQ_BRIDGE). Every 2 seconds what it shows is saved as
# /tmp/pal-sim/screen.png, for tests and for people to look at.
# PAL may borrow this screen after 5 quiet seconds, not 2 minutes.
# Usage (as pal, from run_sim.sh): python3 -I - < sim_screen.py
import os, pty, subprocess, sys, threading, time, tty, types
sys.path.insert(0, "/opt/compaq/lib")
import numpy as np
from PIL import Image, ImageFont
import tv_terminal as tv

SIM, TM = "/tmp/pal-sim", ["tmux", "-L", "palsim"]
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
for leftover in ("bridge.sock", "status", "terminal"):
    if os.path.exists(f"{SIM}/{leftover}"):
        os.remove(f"{SIM}/{leftover}")


class Pretend(tv.Display):
    """A 1280x720 TV that is only an array."""

    def __init__(self):
        self.width, self.height, self.depth = 1280, 720, 32
        self.pixels = np.zeros((self.height, self.width), np.uint32)
        self.scale = max(1, min(self.width // (8 * tv.COLS), self.height // (16 * tv.ROWS)))
        self.cw, self.ch = 8 * self.scale, 16 * self.scale
        self.left = (self.width - self.cw * tv.COLS) // 2
        self.top = (self.height - self.ch * tv.ROWS) // 2
        self.font = ImageFont.truetype(tv.FONT, 16)
        self.cache = {}


display = Pretend()
tv.Display = lambda: display
tv.fcntl = types.SimpleNamespace(ioctl=lambda *args: 0)      # (no console to put into graphics mode)
tv.showing = lambda console: True
tv.start_bridge = lambda line: subprocess.Popen([sys.executable, "-I", "-c", f"""
import sys; sys.path.insert(0, '/opt/compaq/lib')
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '{SIM}/bridge.sock'; b.STATUS = '{SIM}/status'
b.Bridge({line!r}, '9600').run()
"""], env=dict(os.environ, COMPAQ_TV="1", COMPAQ_PAL_IDLE_SECONDS="5"))
keyboard, console = pty.openpty()                             # the pretend TV's keyboard
tty.setraw(console)
sys.stdin = os.fdopen(console)
# Tests type on it by writing to /tmp/pal-sim/keyboard (as at the lobby
# TV's keyboard: with a moving picture up, keys go to its owner).
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


threading.Thread(target=type_keys, daemon=True).start()


def keep_saving():
    for _ in range(100):
        if os.path.exists(f"{SIM}/bridge.sock"):
            break
        time.sleep(0.2)
    # (SHELL: pal's own is nologin, which would end the session at once)
    subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                         "printf '\\n  The PAL simulator\\047s screen (nothing here is the lobby\\047s)\\n'; "
                         "sleep 86400"], env=dict(os.environ, SHELL="/bin/sh"))
    while True:
        rgb = np.stack([(display.pixels >> 16) & 255, (display.pixels >> 8) & 255, display.pixels & 255], -1)
        Image.fromarray(rgb.astype(np.uint8)).save(f"{SIM}/.screen.png")
        os.replace(f"{SIM}/.screen.png", f"{SIM}/screen.png")
        time.sleep(2)


threading.Thread(target=keep_saving, daemon=True).start()
try:
    tv.main()
finally:
    subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
