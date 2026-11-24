# Doom in real dots and PotatoTube HD on the REAL lobby screen (the TV
# standing in, or the Compaq), typed into the real shared session, with
# snapshots of what the TV showed. It closes whatever is open there, plays a
# 30-second video's sound through PAL, and takes about three minutes. Empty
# lobby only (or when Austin says to). Run as root on the Pi:
#   sudo python3 -I tv_programs_check.py [doom] [potato]
# Snapshots land in /tmp/rig/live-*.png.
import subprocess, sys, time
import numpy as np
from PIL import Image

TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]


def tm(*args):
    return subprocess.run(TM + list(args), capture_output=True, text=True).stdout


def keys(*names):
    tm("send-keys", "-t", "compaq", *names)


def typed(words):
    tm("send-keys", "-t", "compaq", "-l", words)


def pane():
    return tm("capture-pane", "-p", "-t", "compaq")


def wait_for(words, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if words in pane():
            return True
        time.sleep(0.3)
    return False


def shot(name):
    """What's on the TV now, as /tmp/rig/live-NAME.png."""
    info = "/sys/class/graphics/fb0/"
    width, height = (int(v) for v in open(info + "virtual_size").read().split(","))
    stride = int(open(info + "stride").read())
    if int(open(info + "bits_per_pixel").read()) == 16:
        p = np.fromfile("/dev/fb0", np.uint16, count=stride // 2 * height).reshape(height, -1)[:, :width].astype(np.uint32)
        rgb = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31], -1)
    else:
        p = np.fromfile("/dev/fb0", np.uint32, count=stride // 4 * height).reshape(height, -1)[:, :width]
        rgb = np.stack([(p >> 16) & 255, (p >> 8) & 255, p & 255], -1)
    Image.fromarray(rgb.astype(np.uint8)).save(f"/tmp/rig/live-{name}.png")


def last_lines(count=4):
    return " / ".join(line.strip() for line in pane().splitlines() if line.strip())[-300:]


which = sys.argv[1:] or ["doom", "potato"]
try:
    if "doom" in which:
        tm("respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session open 40-games/07-doom")
        wait_for("Press Enter to start", 15)
        keys("Enter")
        print("Doom took the screen in real dots:", wait_for("DOOM is on the Compaq's screen", 25), flush=True)
        time.sleep(9)
        shot("doom-1")
        for _ in range(3):                       # through its menus: a new game
            keys("Enter")
            time.sleep(1.3)
        time.sleep(5)
        shot("doom-2")
        for _ in range(30):                      # a key held down, as a keyboard repeats it: walking
            keys("Up")
            time.sleep(0.1)
        shot("doom-3")
        for _ in range(12):
            keys("Right")
            time.sleep(0.1)
        keys("Space")
        time.sleep(2)
        shot("doom-4")
        keys("C-c")
        wait_for("pictures in", 10)
        print("Doom:", last_lines(), flush=True)
        time.sleep(4)
    if "potato" in which:
        tm("respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session open 30-internet/15-potatotube")
        wait_for("Search YouTube", 20)
        typed("big buck bunny trailer")
        keys("Enter")
        print("PotatoTube found videos:", wait_for("S: new search", 90), flush=True)
        typed("h1")
        keys("Enter")
        print("PotatoTube HD started:", wait_for("POTATOTUBE HD", 180), flush=True)
        time.sleep(7)
        shot("potato-1")
        time.sleep(9)
        shot("potato-2")
        wait_for("pictures in real dots", 120)
        print("PotatoTube HD:", last_lines(), flush=True)
    try:
        print("the bridge says PILINK managed:", open("/run/compaq-serial/pilink").read().strip())
    except OSError:
        pass
finally:
    time.sleep(1)
    tm("respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session")       # the welcome screen again
