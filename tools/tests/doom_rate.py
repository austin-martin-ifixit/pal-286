# Doom through PILINK, without a screen: runs the game's frame version
# (tools/doomgeneric_frames.c) for a while, lets its own demo play, walks
# and turns a little, and feeds what it shows to the real encoder with a
# pretend cable. Prints bytes a frame and frames a second for each picture
# size, and saves a few frames as they'd look, to /tmp/rig/doom-frames.png.
# Touches nothing live. Usage: DOOM_FRAMES=path python3 doom_rate.py [bytes a second] [seconds]
import os, sys, time
sys.path.insert(0, "/tmp/rig/lib")
import numpy as np
from PIL import Image
import doomhd, pictures, pilink

BPS = int(sys.argv[1]) if len(sys.argv) > 1 else 11520
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 45
samples = []
for name in os.environ.get("SIZES", "320x200 320x100").split():
    layout = pilink.LAYOUTS[name]
    game = doomhd.Game()
    encoder = pilink.Encoder(layout, sweep=True)
    encoder.setup()
    dither = pictures.Dots(layout.width, layout.height, **eval(os.environ.get('DOTS', 'doomhd.DOTS')))
    start, busy_until, shown, total, sizes = time.monotonic(), 0.0, 0, 0, []
    pressed = False
    while time.monotonic() - start < SECONDS and game.running():
        now = time.monotonic() - start
        if now > 20 and not pressed:                 # after the demo has run a while: play it ourselves
            pressed = True
            for key in (13, 13, 13):                 # Enter through the menus: a new game
                game.key(key, True); time.sleep(0.2); game.key(key, False); time.sleep(0.6)
            game.key(0xad, True); game.key(0xae, True)       # walk forwards, turning right
        if now < busy_until:
            time.sleep(min(0.01, busy_until - now))
            continue
        game.ask()
        grey = game.frame()
        if grey is None:
            break
        dots = dither.dots(grey if layout.height == 200 else grey[::2])
        ops = encoder.frame(layout.pack(dots))
        sizes.append(len(ops) + 2)
        busy_until = (time.monotonic() - start) + max(1 / 35, (len(ops) + 2) / BPS)
        shown += 1
        if name == "320x200" and shown in (3, 40, 90, 150):
            samples.append(np.repeat(dots, 2, axis=1))
    elapsed = time.monotonic() - start
    game.stop()
    demo = [s for s in sizes[5:]]
    print(f"{name:8} at {BPS} bytes a second: {shown / elapsed:5.1f} frames a second, "
          f"{int(np.mean(demo))} bytes a frame (most {max(demo)})", flush=True)
if samples:
    sheet = np.concatenate([np.concatenate(samples[:2], axis=1), np.concatenate(samples[2:4], axis=1)]) if len(samples) >= 4 else samples[0]
    Image.fromarray(np.repeat(sheet, 2, axis=0)).save("/tmp/rig/doom-frames.png")
