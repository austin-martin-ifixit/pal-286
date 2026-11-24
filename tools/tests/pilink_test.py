# The PILINK encoder against PILINK played in Python (lib/pilink.py): every
# layout, with noise, flat areas, small changes and a forgotten screen.
# Usage: python3 pilink_test.py [path to lib]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
import numpy as np
import pilink

rng = np.random.default_rng(1987)
failures = 0
for name, sweep in (("CGA_640", False), ("CGA_320", False), ("CGA_320x100", False), ("CGA_160", False),
                    ("PLASMA_640", False), ("CGA_640", True), ("CGA_320", True), ("PLASMA_640", True)):
    layout = getattr(pilink, name)
    screen, encoder = pilink.Screen(), pilink.Encoder(layout, sweep)
    name += " swept" if sweep else ""
    said = screen.feed(encoder.setup())
    assert said == bytes((ord("M"), layout.mode)), said
    frames = [rng.random((layout.height, layout.width)) < 0.5,            # noise: the worst case
              np.zeros((layout.height, layout.width), bool),              # dark
              np.ones((layout.height, layout.width), bool)]               # lit
    stripes = np.zeros((layout.height, layout.width), bool)
    stripes[::3, :] = True
    stripes[:, 100:104] = True
    frames.append(stripes)
    moving = stripes.copy()
    for step in range(6):                                                  # a small square, moving
        moving = stripes.copy()
        moving[20 + step:40 + step, 8 * step:8 * step + 24] ^= True
        frames.append(moving)
    sizes = []
    for n, dots in enumerate(frames):
        if n == 5:
            encoder.forget()                                               # (as after lost bytes)
        ops = encoder.frame(layout.pack(dots))
        sizes.append(len(ops))
        for cut in range(0, len(ops), 97):                                 # in pieces, as a cable delivers
            screen.feed(ops[cut:cut + 97])
        assert screen.feed(bytes((pilink.END, n))) == bytes((ord("A"), n))
        shown = screen.dots()
        want = np.repeat(np.repeat(dots, 640 // layout.width, axis=1), shown.shape[0] // layout.height, axis=0)
        if not (shown == want).all():
            failures += 1
            print(f"FAIL {name} frame {n}: {int((shown != want).sum())} dots differ")
    assert encoder.frame(layout.pack(frames[-1])) == b""                   # nothing changed: nothing sent
    print(f"ok   {name}: {layout.size} bytes a screen; sent {sizes}")

# Frames of a film or a game into dots (pictures.Dots), for every size a
# canvas comes in, with both dot patterns and both ways of setting levels.
import pictures
for width, height in ((320, 200), (320, 100), (160, 100), (640, 200), (640, 400), (266, 198), (318, 90)):
    grey = (rng.random((height, width)) * 255).astype(np.uint8)
    for tall in (False, True):
        for levels in (None, (0, 200)):
            dots = pictures.Dots(width, height, tall=tall, levels=levels).dots(grey)
            if dots.shape != (height, width) or dots.dtype != bool or not 0.2 < dots.mean() < 0.8:
                failures += 1
                print(f"FAIL Dots {width}x{height} tall={tall} levels={levels}: {dots.shape}, {dots.mean():.2f} lit")
print("ok   Dots, every size")

buffer = bytearray(b"\x00junk" + pilink.Screen(flags=3).hello() + b"K\x1eK\x9eA\x07\x1b_P")
found = pilink.messages(buffer)
assert found == [("H", (pilink.VERSION, 3, 3)), ("K", 0x1e), ("K", 0x9e), ("A", 7)], found
assert bytes(buffer) == b"\x1b_P", buffer
print("ok   messages")
sys.exit(1 if failures else 0)
