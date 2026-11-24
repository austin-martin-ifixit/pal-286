# Web search and the page snapshot, driven from the TV keyboard. Root on the Pi.
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
subprocess.run(["sudo", "-u", "desk", "/opt/compaq/lib/voice-open", "search", "Compaq Portable III"])
time.sleep(10)
print(screen()); shot("web-results")
tv(b"p1\r")
start = time.time()
while time.time() - start < 120 and "through 1987 eyes" not in screen():
    time.sleep(1)
print(f"snapshot took {time.time() - start:.0f} s")
time.sleep(2); shot("web-snapshot"); print(screen())
tv(b"q"); time.sleep(1); tv(b"\r"); time.sleep(2)
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
