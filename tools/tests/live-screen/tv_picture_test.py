# pictures.show() on the real TV (through the real bridge), with screenshots,
# and a QR code checked with OpenCV's reader. Root on the Pi (reads /dev/fb0).
import os, subprocess, sys, threading, time, urllib.request
import cv2
import numpy as np
from PIL import Image
sys.path.insert(0, "/opt/compaq/lib")
import pictures

def shot(name):
    w, h = 1366, 768
    p = np.fromfile("/dev/fb0", np.uint16, count=w*h).reshape(h, w).astype(np.uint32)
    rgb = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31], -1)
    Image.fromarray(rgb.astype(np.uint8)).save(f"/tmp/{name}.png")
    return rgb.astype(np.uint8)

def show_for(image, caption, seconds, name):
    """show() in a thread, a screenshot after seconds, then let go (as a program moving on would)."""
    result = {}
    def run():
        result["r"] = pictures.show(image, caption, keys=False)
    t = threading.Thread(target=run, daemon=True); t.start()
    time.sleep(seconds)
    rgb = shot(name)
    return rgb

URL = "https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium"
photo = pictures.from_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "CompaqPortableIII/1.0"}), timeout=30).read())
# (show() waits for a key at the Compaq; this test lets go by exiting the
# thread's connection: run each in its own process instead)
for name, args in (("tv-pic-photo", "photo"), ("tv-pic-qr", "qr")):
    child = subprocess.Popen([sys.executable, "-c", f"""
import sys, urllib.request; sys.path.insert(0, '/opt/compaq/lib'); import pictures
if '{args}' == 'photo':
    img = pictures.from_bytes(urllib.request.urlopen(urllib.request.Request('{URL}', headers={{'User-Agent': 'x'}}), timeout=30).read())
    print(pictures.show(img, 'Step 1: Eject the SIM card tray', keys=False))
else:
    print(pictures.show(pictures.qr('https://www.ifixit.com/Guide/iPhone+12+Battery+Replacement/140588'), 'Scan to open this guide on your phone', keys=False))
"""])
    time.sleep(14 if args == "photo" else 7)
    rgb = shot(name)
    if args == "qr":
        found, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        print("QR read off the TV screenshot:", found or "(not readable)")
    child.terminate(); child.wait()
    time.sleep(2)
shot("tv-pic-after")
print("done")
