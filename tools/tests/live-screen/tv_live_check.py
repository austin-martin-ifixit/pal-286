# One photo and six seconds of a moving picture on the REAL lobby screen (the
# TV standing in, or the Compaq), through the real bridge, with snapshots of
# what the TV actually showed. About 20 seconds; nothing is typed. Empty
# lobby only (or when Austin says to). Run as root on the Pi:
#   sudo python3 -I tv_live_check.py     (snapshots land in /tmp/rig/live-*.png)
import subprocess, sys, time
import numpy as np
from PIL import Image

DEMO = r'''
import sys, time
sys.path.insert(0, "/opt/compaq/lib")
import numpy as np
import pictures
from PIL import Image, ImageDraw
try:
    photo = pictures.fetch("https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium")
except pictures.NotShown:
    photo = Image.new("L", (640, 480), 40)
    ImageDraw.Draw(photo).ellipse((120, 60, 520, 420), fill=220)
start = time.monotonic()
conn, seconds = pictures.put_up(photo, "A test picture: back in a moment")
print(f"photo on its way after {time.monotonic() - start:.1f} s, painting takes {seconds} s", flush=True)
time.sleep(seconds + 4)
conn.close()
time.sleep(0.2)
canvas = pictures.Canvas("320x200")
print(f"canvas {canvas.layout} at {canvas.bps} bytes a second", flush=True)
yy, xx = np.mgrid[0:canvas.height, 0:canvas.width]
start, frames = time.monotonic(), 0
while time.monotonic() - start < 6 and not canvas.closed:
    canvas.news(0.02)
    if canvas.ready:
        t = time.monotonic() - start
        x, y = canvas.width * (0.5 + 0.35 * np.cos(t * 2)), canvas.height * (0.5 + 0.3 * np.sin(t * 3))
        canvas.send((xx - x) ** 2 + ((yy - y) * 1.2) ** 2 < (canvas.height / 5) ** 2)
        frames += 1
print(f"moving picture: {frames} frames in {time.monotonic() - start:.1f} s", flush=True)
canvas.close()
'''


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


demo = subprocess.Popen(["sudo", "-u", "desk", "python3", "-I", "-c", DEMO], stdout=subprocess.PIPE, text=True)
line = demo.stdout.readline().strip()
print(line, flush=True)
if "painting takes" in line:
    time.sleep(float(line.split("painting takes")[1].split()[0]) + 1.5)
    shot("photo")
line = demo.stdout.readline().strip()
print(line, flush=True)
if line.startswith("canvas"):
    time.sleep(3)
    shot("moving")
print(demo.stdout.read().strip(), flush=True)
demo.wait()
time.sleep(3)
shot("text-again")
try:
    print("the bridge says PILINK managed:", open("/run/compaq-serial/pilink").read().strip())
except OSError:
    print("the bridge left no word about PILINK")
