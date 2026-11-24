#!/usr/bin/env python3
"""DOOM in the Compaq's own dots.

Real Doom (the shareware first episode) runs here on the Pi, at its usual
speed. Whenever the Compaq's screen is ready for another picture, this asks
the game for the frame it's showing right now, turns it into amber dots and
sends it through PILINK, which only carries what changed. Keys come back
from the Compaq as "down" and "up", so they can be held: walk, turn and
fire like 1993.

The picture starts as 320 dots by 100 rows (each row drawn twice), which a
115200 baud cable carries about 5 to 7 times a second. The ` key (under
Esc) switches to all 200 rows, finer and about 3 to 4 a second, and back.

Sound stays off: Doom's own would need the lobby speaker, which is PAL's.

Without PILINK on the Compaq (or the game's frame version on the Pi) it's
the text version, doom-ascii, as before.

Usage: doomhd.py   (apps/40-games/07-doom runs it, in the saved-games folder)
"""

import os
import select
import signal
import subprocess
import sys
import termios
import time
import tty

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pictures  # noqa: E402
import pilink  # noqa: E402

FRAMES = os.environ.get("DOOM_FRAMES", "/opt/compaq-net/bin/doom-frames")   # (tools/doomgeneric_frames.c)
ASCII = "/opt/compaq-net/bin/doom-ascii"
WAD = "/usr/share/games/doom/doom1.wad"
START = ["-skill", "2", "-warp", "1", "1"]   # straight into the first level, not the demo (Esc: Doom's menu)
WIDTH, HEIGHT = 320, 200             # Doom's own screen
HOLD = 0.25                          # s a key typed in a browser (or at the TV) counts as held down
SIZES = ("320x100", "320x200")       # quicker, sharper: the ` key goes from one to the other
SWITCH = 0x29                        # that key's scancode
DOTS = dict(levels=(0, 200), gamma=0.7, sharpen=0.5)   # how its frames become dots (pictures.Dots)

# The Compaq's keys (PC scancodes) as Doom's own key codes.
KEYS = {0x48: 0xad, 0x50: 0xaf, 0x4B: 0xac, 0x4D: 0xae,      # arrows: walk and turn
        0x39: 0xa3, 0x1D: 0xa3,                              # Space or Ctrl: fire
        0x12: 0xa2,                                          # E: open, use
        0x33: 0xa0, 0x34: 0xa1,                              # , and . : step sideways
        0x2A: 0xb6, 0x36: 0xb6, 0x38: 0xb8,                  # Shift: run. Alt: arrows step sideways
        0x1C: 13, 0x01: 27, 0x0F: 9, 0x0E: 0x7f}             # Enter, Esc (Doom's menu), Tab (map), Backspace
KEYS.update({number: ord(char) for number, char in pilink.PLAIN.items() if number not in KEYS})
KEYS.update({number: 0x80 + number for number in range(0x3B, 0x44)})   # F1 to F9 (F10 is the main menu)


class Game:
    """The game itself, running at its own pace."""

    def __init__(self):
        self.frames, write = os.pipe()
        self.process = subprocess.Popen(
            [FRAMES, "-iwad", WAD, "-scaling", "1", *START], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, pass_fds=(write,), env=dict(os.environ, DOOM_FRAMES_FD=str(write)))
        os.close(write)
        self.asked = False

    def running(self):
        return self.process.poll() is None

    def tell(self, command):
        try:
            self.process.stdin.write(command)
            self.process.stdin.flush()
        except OSError:
            pass

    def key(self, code, pressed):
        self.tell((b"D" if pressed else b"U") + bytes((code,)))

    def ask(self):
        """Asks for the frame the game is showing now (frame() collects it)."""
        if not self.asked:
            self.asked = True
            self.tell(b"F")

    def frame(self):
        """The frame asked for: HEIGHT x WIDTH greys, or None if the game has ended."""
        self.asked = False
        data = b""
        while len(data) < WIDTH * HEIGHT:
            more = os.read(self.frames, WIDTH * HEIGHT - len(data))
            if not more:
                return None
            data += more
        return np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH)

    def stop(self):
        self.process.kill()
        self.process.wait()
        os.close(self.frames)


def play(canvas):
    """Runs the game on a canvas until it ends or the screen is taken away."""
    game = Game()
    stdin = sys.stdin.fileno() if sys.stdin.isatty() else None
    saved = termios.tcgetattr(stdin) if stdin is not None else None
    held = {}                                   # keys typed here, "held" until... {Doom's code: when}
    shown, started = 0, time.monotonic()

    def dither_for(canvas):
        return pictures.Dots(WIDTH, canvas.height, tall=canvas.height != HEIGHT, **DOTS)

    def switch(canvas):                         # the other picture size
        other = SIZES[1 - SIZES.index(canvas.layout)] if canvas.layout in SIZES else SIZES[0]
        canvas.close()
        return pictures.Canvas(other)

    dither = dither_for(canvas)
    stopped = []                                # Ctrl-C: leave tidily, like quitting from Doom's menu
    old = signal.signal(signal.SIGINT, lambda *_: stopped.append(True))
    try:
        if stdin is not None:
            tty.setcbreak(stdin)
        while game.running() and not canvas.closed and not stopped:
            if canvas.ready:
                game.ask()
            now = time.monotonic()
            wait = min([now + 0.25] + list(held.values())) - now
            watch = [canvas, game.frames] + ([stdin] if stdin is not None else [])
            ready, _, _ = select.select(watch, [], [], max(0.0, wait))
            switching = False
            if canvas in ready:
                for key, pressed, _ in canvas.news():       # keys at the Compaq: down, and up
                    if key == SWITCH:
                        switching |= pressed
                    elif key & 0x7F in KEYS:
                        game.key(KEYS[key & 0x7F], pressed)
            if stdin in ready:
                # Keys from a browser (or the TV's keyboard) only say what
                # was typed: each counts as held for a moment, and a key
                # kept down repeats, which keeps it held.
                for chord in pilink.taps(os.read(stdin, 256)):
                    for key in chord:
                        code = KEYS.get(key & 0x7F)
                        if key == SWITCH:
                            switching = True
                        elif code and code not in held:
                            game.key(code, True)
                        if code and key != SWITCH:
                            held[code] = time.monotonic() + HOLD
            now = time.monotonic()
            for code in [code for code, until in held.items() if now >= until]:
                del held[code]
                game.key(code, False)
            if game.frames in ready:
                grey = game.frame()
                if grey is None:
                    break
                if not canvas.closed:
                    canvas.send(dither.dots(grey[::2] if canvas.height != HEIGHT else grey))
                    shown += 1
            if switching and not canvas.closed:
                try:
                    canvas = switch(canvas)
                except pictures.NotShown:
                    break
                dither = dither_for(canvas)
    finally:
        signal.signal(signal.SIGINT, old)
        game.stop()
        canvas.close()
        if saved is not None:
            termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
    return shown, time.monotonic() - started


def text_doom():
    """The text version, as before PILINK."""
    os.execv(ASCII, [ASCII, "-iwad", WAD, "-nocolor", "-chars", "ascii", "-scaling", "9", *START])


def main():
    if not os.access(FRAMES, os.X_OK):
        text_doom()
    try:
        canvas = pictures.Canvas(SIZES[0])
    except pictures.NotShown:
        text_doom()
    print("\033[H\033[2J\n  DOOM is on the Compaq's screen, in real dots.\n")
    print("  At the Compaq, keys can be held: arrows walk and turn, Space or Ctrl")
    print("  fires, E opens doors, Shift runs, comma and period step sideways,")
    print("  1 to 7 pick a weapon, Tab is the map, Esc is Doom's menu.")
    print("  The ` key (under Esc) swaps a quicker picture for a sharper one.\n")
    print("  From a browser the same keys work as taps.")
    print("  F10 (or Ctrl-\\) leaves for the main menu; Ctrl-C leaves and says how it went.", flush=True)
    shown, seconds = play(canvas)
    print(f"\n  That was {shown} pictures in {int(seconds)} seconds"
          f" ({shown / max(seconds, 1):.1f} a second down the cable).")
    time.sleep(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
