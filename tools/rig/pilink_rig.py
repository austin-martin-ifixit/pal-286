# The real PILINK.COM (dos/pilink.asm) in DOSBox, a CGA PC at about a 286's
# speed, driven straight down its serial port: no bridge, no tmux, nothing
# live. Checks the hello, a picture dot for dot against a screenshot, each
# cable speed (how long a full screen of noise takes, the worst case), the
# widened-dot modes, key presses and releases, lost bytes, and quitting.
# Usage (on the Pi, after tools/rig/setup.sh): python3 /tmp/rig/pilink_rig.py [fifo|nofifo] [rxdelay ms]
import os, socket, subprocess, sys, time
import numpy as np
from PIL import Image
sys.path.insert(0, "/tmp/rig/lib")
import pilink
from dosbox_link import X, Link, check, launch

FIFO = (sys.argv[1] if len(sys.argv) > 1 else "fifo") == "fifo"
RXDELAY = int(sys.argv[2]) if len(sys.argv) > 2 else 0     # 0: a late byte is lost, as on the real chip
rng = np.random.default_rng(3)


def grab(name="pilink"):
    subprocess.run(["xdotool", "mousemove", "799", "599"], env=X)
    time.sleep(0.4)
    subprocess.run(["/tmp/rig/shot.sh", name])
    picture = Image.open(f"/tmp/rig/{name}.png").convert("L").crop((80, 100, 720, 500))
    picture.save(f"/tmp/rig/{name}.png")
    return np.asarray(picture)[::2] > 128


def show(link, encoder, dots, number):
    """Sends a screenful and waits for PILINK to say it's shown: (seconds, bytes sent)."""
    ops = encoder.frame(encoder.layout.pack(dots)) + bytes((pilink.END, number))
    start = time.monotonic()
    link.send(ops)
    shown = link.expect("A", 60, number)
    return (time.monotonic() - start if shown else None), len(ops)


def matches(layout, dots, name):
    want = np.repeat(np.repeat(dots, 640 // layout.width, axis=1), 200 // layout.height, axis=0)
    got = grab(name)
    return int((got != want).sum())


results = []
link = Link(launch("pilink 3" + ("" if FIFO else " /N"), RXDELAY))          # standing alone, at 38400
hello = link.expect("H", 15)
results.append(check("hello", hello is not None, str(hello)))
if not hello:
    sys.exit(1)
fifo_on = bool(hello[1][1] & 1)
print(f"     serial chip buffer (FIFO) in use: {fifo_on}", flush=True)

layout = pilink.CGA_640
encoder = pilink.Encoder(layout)
link.send(encoder.setup())
results.append(check("mode 6 (640x200)", link.expect("M", 5) == ("M", pilink.CGA)))

picture = np.zeros((200, 640), bool)                                  # shapes: easy to judge by eye
yy, xx = np.mgrid[0:200, 0:640]
picture |= ((xx - 320) / 2.4) ** 2 + (yy - 100) ** 2 < 80 ** 2
picture ^= ((xx // 16 + yy // 8) % 2 == 0) & (xx < 160)
picture[::10, 400:] = True
seconds, sent = show(link, encoder, picture, 1)
wrong = matches(layout, picture, "pilink-shapes") if seconds else -1
results.append(check("a picture at 38400", seconds is not None and wrong == 0,
                     f"{sent} bytes in {seconds:.2f} s, {wrong} dots wrong" if seconds else "no answer"))

for speed in (38400, 57600, 115200):
    link.send(bytes((pilink.BAUD,)) + pilink.word(pilink.divisor(speed)))
    switched = link.expect("B", 3)
    time.sleep(0.1)
    link.send(pilink.test_pattern(2048) + bytes((pilink.END, 100)))
    tested = link.expect("A", 5, 100)
    if not (switched and tested):
        results.append(check(f"{speed} baud", False, f"switch {switched}, test {tested}, then {link.inbox}"))
        link.expect("H", 5)                                         # (it goes back to the last good speed)
        continue
    noise = rng.random((200, 640)) < 0.5
    seconds, sent = show(link, encoder, noise, 2)
    wrong = matches(layout, noise, f"pilink-noise-{speed}") if seconds else -1
    trouble = [m for m in link.inbox if m[0] in "NR"]
    results.append(check(f"{speed} baud", seconds is not None and wrong == 0 and not trouble,
                         (f"a full screen of noise ({sent} bytes) in {seconds:.2f} s = {sent / seconds / 1000:.1f} KB/s, "
                          f"{wrong} dots wrong" if seconds else "no answer") + (f", trouble {trouble}" if trouble else "")))
    back, sent = show(link, encoder, picture, 3)
    results.append(check(f"{speed} baud, back to the shapes", back is not None,
                         f"{sent} bytes in {back:.2f} s" if back else "no answer"))

for name in ("CGA_320", "CGA_320x100", "CGA_160"):
    layout = getattr(pilink, name)
    encoder = pilink.Encoder(layout)
    link.send(encoder.setup())
    link.expect("M", 5)
    small = rng.random((layout.height, layout.width)) < 0.5
    seconds, sent = show(link, encoder, small, 4)
    wrong = matches(layout, small, f"pilink-{name}") if seconds else -1
    results.append(check(f"{name} (dots {layout.wide} wide, {layout.tall * 200 // layout.height // layout.tall if False else layout.tall} tall)",
                         seconds is not None and wrong == 0,
                         f"{sent} bytes in {seconds:.2f} s, {wrong} dots wrong" if seconds else "no answer"))

# Keys: down and up, as the keyboard says them (A is scancode 1E, released 9E).
link.inbox.clear()
subprocess.run(["xdotool", "keydown", "a"], env=X)
down = link.expect("K", 3)
time.sleep(0.3)
subprocess.run(["xdotool", "keyup", "a"], env=X)
up = None
for _ in range(40):                                                    # (a held key repeats: wait for the release)
    key = link.expect("K", 2)
    if key is None or key[1] & 0x80:
        up = key
        break
results.append(check("a key down, then up", down == ("K", 0x1e) and up == ("K", 0x9e), f"{down}, {up}"))

# Lost bytes: a command cut short. PILINK says so, waits for quiet, and is ready again.
link.send(bytes((pilink.LITW,)) + pilink.word(500) + b"x" * 20)
lost = link.expect("N", 3)
ready = link.expect("R", 3)
results.append(check("a command cut short", lost == ("N", 1) and ready == ("R", 0), f"{lost}, {ready}"))
layout = pilink.CGA_640
encoder = pilink.Encoder(layout)
link.send(encoder.setup())
link.expect("M", 5)
seconds, sent = show(link, encoder, picture, 5)
wrong = matches(layout, picture, "pilink-after") if seconds else -1
results.append(check("the screen again afterwards", seconds is not None and wrong == 0,
                     f"{sent} bytes in {seconds:.2f} s, {wrong} dots wrong" if seconds else "no answer"))

link.send(bytes((pilink.QUIT,)))
results.append(check("quit", link.expect("Q", 5) == ("Q", 0)))
time.sleep(1.5)
grab("pilink-after-quit")
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
print("ALL OK" if all(results) else "SOMETHING FAILED")
sys.exit(0 if all(results) else 1)
