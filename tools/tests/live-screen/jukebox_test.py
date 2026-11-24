# The jukebox from the lobby keyboard (the TV), with real sound. Root on the Pi.
import fcntl, os, subprocess, termios, time
import numpy as np
from PIL import Image
TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
def screen(): return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
def tv(keys):
    fd = os.open("/dev/tty7", os.O_RDWR | os.O_NOCTTY)
    for b in keys: fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
    os.close(fd)
def shot(name):
    w, h = 1366, 768
    p = np.fromfile("/dev/fb0", np.uint16, count=w*h).reshape(h, w).astype(np.uint32)
    rgb = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31], -1)
    Image.fromarray(rgb.astype(np.uint8)).save(f"/tmp/{name}.png")
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session menu"]); time.sleep(2)
tv(b"@18-pal/12-jukebox\r"); time.sleep(3)
shot("jb-list"); print("list shown:", "JUKEBOX" in screen())
n = next(i for i, l in enumerate(screen().splitlines()) if "Entertainer" in l)
num = [l for l in screen().splitlines() if "Entertainer" in l][0]
import re
pick = re.findall(r"(\d+)\. The Entertainer", num)[0]
tv(pick.encode() + b"\r"); time.sleep(6); shot("jb-playing"); print(screen())
time.sleep(6); shot("jb-playing2")
tv(b"x"); time.sleep(3); shot("jb-stopped"); print(screen())
tv(b"\r"); time.sleep(1); tv(b"d\r"); time.sleep(10); shot("jb-daisy")
time.sleep(40)
print(screen())
tv(b"\r"); time.sleep(1); tv(b"\r")
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
