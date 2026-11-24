# The TV standing in for the Compaq, with nothing live: tv_terminal.py draws
# into a pretend display and reads a pretend keyboard, its bridge is a
# private copy with a private tmux server, and a program asks for two still
# pictures and a moving one (tools/rig/link_demo.py). Checks that the TV
# plays PILINK (pictures at the cable's pace, in the plasma's 640x400, keys
# reported down and up) and goes back to text. Saves what the "TV" showed as
# /tmp/rig/tv-*.png. Needs tools/rig/setup.sh first.
# Usage (on the Pi): python3 /tmp/rig/tv_link_test.py [layout] [real] [kermit]
# The TV plays a Compaq running PI.BAT (PILINK as its whole terminal), or
# with kermit, one running Kermit that starts PILINK for pictures.
# real: a pretend 1366x768 TV like the lobby's, showing the Compaq at its own
# size (data/tv.conf's SIZE=real, on the lobby's 31.5-inch Samsung).
import os, pty, subprocess, sys, threading, time, tty, types
sys.path.insert(0, "/tmp/rig/lib")
import numpy as np
from PIL import Image, ImageFont
import tv_terminal as tv

LAYOUT = sys.argv[1] if len(sys.argv) > 1 else "320x200"
REAL = "real" in sys.argv[2:]
KERMIT = "kermit" in sys.argv[2:]
_settings = tv.settings
tv.settings = lambda: dict(_settings(), TERMINAL="kermit" if KERMIT else "pi")
LIB, TM = "/tmp/rig/lib", ["tmux", "-L", "rigtv"]
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
for leftover in ("/tmp/rig/tv/bridge.sock", "/tmp/rig/tv/status"):
    if os.path.exists(leftover):
        os.remove(leftover)
os.makedirs("/tmp/rig/tv", exist_ok=True)


class Pretend(tv.Display):
    """A 1920x1080 TV that is only an array (with real: 1366x768, 16-bit,
    showing the Compaq at its own size)."""

    def __init__(self):
        width, height, depth = (1366, 768, 16) if REAL else (1920, 1080, 32)
        self.fb = (np.zeros((height, width), np.uint16 if depth == 16 else np.uint32), width, height, depth)
        self.font = ImageFont.truetype(tv.FONT, 16)
        self.wanted = {"TV_WIDTH_MM": "697", "COMPAQ_MM": "215x135"}
        self.set_size("real" if REAL else "fill")


display = Pretend()
tv.Display = lambda: display
tv.fcntl = types.SimpleNamespace(ioctl=lambda *args: 0)      # (no console to put into graphics mode)
tv.showing = lambda console: True
tv.start_bridge = lambda line: subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/tv/bridge.sock'; b.STATUS = '/tmp/rig/tv/status'
b.Bridge({line!r}, '9600').run()
"""], env=dict(os.environ, COMPAQ_TV="1"))
keyboard, console = pty.openpty()                             # the TV's keyboard, and the console it types at
tty.setraw(console)
sys.stdin = os.fdopen(console)


def snapshot(name):
    """The whole pretend TV, as it is."""
    if display.native is not None:
        display.dirty = True
        display.present()
    p, _, _, depth = display.fb
    p = p.astype(np.uint32)
    if depth == 16:
        rgb = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31], -1)
    else:
        rgb = np.stack([(p >> 16) & 255, (p >> 8) & 255, p & 255], -1)
    image = Image.fromarray(rgb.astype(np.uint8))
    if REAL:
        image.save(f"/tmp/rig/tv-real-{name}.png")
    else:
        image.resize((960, 540), Image.BOX).save(f"/tmp/rig/tv-{name}.png")


def screen():
    return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout


def wait_for(text, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if text in screen():
            return True
        time.sleep(0.2)
    return False


def drive():
    code = 1
    try:
        for _ in range(100):
            if os.path.exists("/tmp/rig/tv/bridge.sock"):
                break
            time.sleep(0.2)
        subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                             f"COMPAQ_BRIDGE=/tmp/rig/tv/bridge.sock python3 /tmp/rig/link_demo.py {LAYOUT}; sleep 600"])
        start = time.monotonic()
        ok = wait_for("photo: painting", 40)
        print(f"photo on its way after {time.monotonic() - start:.1f} s: {ok}", flush=True)
        time.sleep(4.5)
        snapshot("photo")
        os.write(keyboard, b" ")                               # a key at the TV's keyboard
        wait_for("qr: painting", 20)
        time.sleep(2)
        snapshot("qr")
        os.write(keyboard, b" ")
        if wait_for("canvas:", 20):
            time.sleep(3)
            snapshot("canvas")
            os.write(keyboard, b"a")
            wait_for("END", 20)
        time.sleep(2)
        snapshot("text-again")
        if REAL:                                               # F12: fill the TV, then back
            os.write(keyboard, tv.SIZE_KEY)
            time.sleep(1.5)
            snapshot("f12-fill")
            print("F12:", display.size, flush=True)
            os.write(keyboard, tv.SIZE_KEY)
            time.sleep(1.5)
            snapshot("f12-real")
            print("F12 again:", display.size, flush=True)
        print(screen().rstrip()[-600:], flush=True)
        code = 0
    finally:
        subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "rig/tv/bridge.sock"])
        os._exit(code)


threading.Thread(target=drive, daemon=True).start()
tv.main()
