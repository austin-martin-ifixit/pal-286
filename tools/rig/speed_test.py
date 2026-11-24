# How fast can the real MS-DOS Kermit 3.16 (in DOSBox, a 286-ish CPU) take a
# sixel photo when the cable runs faster than 9600? Sends one photo unpaced
# at each speed, takes screenshots as it paints, and compares the result dot
# for dot with what it should be (the TV's interpreter, which matches Kermit).
import os, socket, subprocess, sys, time, urllib.request
import numpy as np
from PIL import Image
sys.path.insert(0, "/tmp/rig/lib")
import pictures, tv_terminal

class FakeDisplay:
    cw, ch, top, left = 16, 32, 0, 0
    pixels = np.zeros((32 * 24, 16 * 80), np.uint32)
    def colour(self, rgb): return np.zeros(rgb.shape[:-1], np.uint32)

URL = "https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium"
photo = pictures.from_bytes(urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "x"}), timeout=30).read())
data, _ = pictures.screen(photo, "speed test")
g = tv_terminal.Graphics(FakeDisplay()); g.enter(); g.feed(data[len(pictures.ENTER):])
want = g.dots.copy()
print(f"picture: {len(data)} bytes", flush=True)

def grab():
    subprocess.run(["xdotool", "mousemove", "799", "599"], env={"DISPLAY": ":99"})
    subprocess.run(["/tmp/rig/shot.sh", "speed"])
    return np.asarray(Image.open("/tmp/rig/speed.png").convert("L").crop((80, 100, 720, 500)))[::2] > 128

ini = open("/tmp/rig/MSKERMIT.INI", newline="").read()      # (CRLF: DOS Kermit needs it)
for speed in [int(a) for a in sys.argv[1:]] or [9600, 38400, 57600, 115200]:
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True); time.sleep(1)
    os.makedirs("/tmp/rig/c", exist_ok=True)
    server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 5555)); server.listen(1)
    with open("/tmp/rig/MSKERMIT.speed.INI", "w", newline="") as f:
        f.write(ini.replace("set speed 9600", f"set speed {speed}"))
    subprocess.Popen(["/tmp/rig/start.sh"], env=dict(os.environ, INI="/tmp/rig/MSKERMIT.speed.INI"))
    conn, _ = server.accept(); time.sleep(7)
    start = time.monotonic()
    conn.sendall(data)                      # all at once: the emulated cable sets the pace
    sent = time.monotonic() - start
    done_at = None
    for _ in range(40):
        time.sleep(0.5)
        shot = grab()
        shot[188:] = False                   # (the caption: Kermit's letters differ a little from ours)
        mine = want.copy(); mine[188:] = False
        diff = int((shot != mine).sum())
        if diff < 30:
            done_at = time.monotonic() - start
            break
    print(f"{speed:>6} baud: handed over in {sent:.1f} s; picture complete after "
          f"{done_at:.1f} s" if done_at else f"{speed:>6} baud: never matched; {diff} dots still differ "
          f"(lost data?) after {time.monotonic() - start:.0f} s", flush=True)
    Image.fromarray((shot * 255).astype(np.uint8)).save(f"/tmp/rig/speed-{speed}.png")
    conn.close(); server.close()
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
