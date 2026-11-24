# What link_test.py runs on the rig's private shared screen: two still
# pictures and a moving one, as any menu program would ask for them.
import sys, time
sys.path.insert(0, "/tmp/rig/lib")
import numpy as np
import pictures
from PIL import Image, ImageDraw

def said(what):
    print(what, flush=True)

try:
    photo = pictures.fetch("https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium")
except pictures.NotShown:
    photo = Image.new("L", (640, 480), 40)                    # (offline: shapes will do)
    ImageDraw.Draw(photo).ellipse((120, 60, 520, 420), fill=220)
import os
while not os.path.exists(pictures.BRIDGE):                    # (the test starts its bridge after us)
    time.sleep(0.5)
time.sleep(1)
start = time.monotonic()
key = pictures.show(photo, "A repair photo", told=lambda s: said(f"photo: painting takes {s} s"), more=True)
said(f"photo: came down after {time.monotonic() - start:.1f} s with key {key!r}")
start = time.monotonic()
key = pictures.show(pictures.qr("https://www.ifixit.com/Guide/140588"), "Scan to read on",
                    told=lambda s: said(f"qr: painting takes {s} s"))
said(f"qr: came down after {time.monotonic() - start:.1f} s with key {key!r}")
try:
    canvas = pictures.Canvas(sys.argv[1] if len(sys.argv) > 1 else "320x200")
except pictures.NotShown as e:
    said(f"canvas: refused ({e})")
    said("END")
    time.sleep(600)
said(f"canvas: {canvas.layout}, {canvas.bps} bytes a second")
yy, xx = np.mgrid[0:canvas.height, 0:canvas.width]
start, frames, keys = time.monotonic(), 0, []
while time.monotonic() - start < 8 and not canvas.closed:
    keys += canvas.news(0.02)
    if canvas.ready:
        t = time.monotonic() - start
        x, y = canvas.width * (0.5 + 0.35 * np.cos(t * 2)), canvas.height * (0.5 + 0.3 * np.sin(t * 3))
        dots = ((xx - x) ** 2 + ((yy - y) * 1.2) ** 2 < (canvas.height / 5) ** 2) | ((xx // 16 + yy // 16) % 2 == 0) & (yy > canvas.height * 0.8)
        canvas.send(dots)
        frames += 1
said(f"canvas: {frames} frames in {time.monotonic() - start:.1f} s; keys {keys}")
canvas.close()
said("END")
time.sleep(600)
