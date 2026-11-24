#!/usr/bin/env python3
"""A modern web page as the Pi's own browser draws it (Chromium, with no
screen), squashed onto the Compaq: painted on its screen as dithered amber
pictures, a screenful at a time (the 2026 web through 1987 eyes), or as
text art when pictures can't go up. Mostly unreadable, which is the joke;
Lynx is for reading.

Usage: snapshot.py URL
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.parse

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pictures  # noqa: E402
from chat import page  # noqa: E402

BROWSER = "chromium-headless-shell"
# An 800-wide window: the desktop layout, with headlines still readable once
# squashed to 640 dots. Each screenful of it (800x470) is exactly one
# screen of the Compaq's (640x188 dots, each twice as tall as wide).
WIDTH, SCREEN, SCREENS = 800, 470, 4
COLS = 79
# Light to dark: on paper-white pages the text and pictures are the ink.
RAMP = " .'`,:;-~+=*xoaO0#%@"


def text_art(path):
    image = ImageOps.autocontrast(Image.open(path).convert("L"), cutoff=1)
    rows = int(image.height / image.width * COLS / 2)     # (a character is twice as tall as wide)
    small = np.asarray(image.resize((COLS, rows), Image.LANCZOS), dtype=np.float32)
    ink = (255 - small) / 256 * len(RAMP)                  # dark = more ink
    return ["".join(RAMP[int(v)] for v in row).rstrip() for row in ink]


def shoot(url, work):
    """The page drawn into work/page.png; None, or what went wrong."""
    try:
        subprocess.run([BROWSER, "--disable-gpu", "--hide-scrollbars", "--mute-audio",
                        "--no-first-run", "--disable-extensions", f"--user-data-dir={work}/profile",
                        f"--window-size={WIDTH},{SCREEN * SCREENS}", "--virtual-time-budget=8000",
                        f"--screenshot={work}/page.png", url],
                       cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=90, env=dict(os.environ, HOME=work))
    except subprocess.TimeoutExpired:
        return "The page took too long to draw (more than a minute and a half)."
    if not os.path.exists(f"{work}/page.png"):
        return "The browser couldn't draw that page."
    return None


def screens(path):
    """The page's screenfuls, stopping where it runs out (blank below)."""
    image = Image.open(path).convert("L")
    out = []
    for top in range(0, image.height - SCREEN + 1, SCREEN):
        part = image.crop((0, top, WIDTH, top + SCREEN))
        if out and np.asarray(part).std() < 3:
            break
        out.append(part)
    return out


def as_pictures(path, host):
    """The page on the Compaq's screen. False if pictures can't go up there."""
    parts = screens(path)
    for i, part in enumerate(parts, 1):
        what = f"screenful {i} of {len(parts)}"
        try:
            key = pictures.show(part, f"{host[:50]}, {what}",
                                told=pictures.saying(what, more=i < len(parts)))
        except pictures.NotShown as e:
            if i > 1:
                print(f"  {e}")
                return True
            print(f"  {e} So here it is as text art:")
            return False
        if pictures.stops(key):
            break
    return True


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else ""
    if urllib.parse.urlparse(url).scheme not in ("http", "https") or not shutil.which(BROWSER):
        sys.exit("Usage: snapshot.py http(s)://...")
    host = urllib.parse.urlparse(url).netloc
    host = "".join(c if " " < c <= "~" else "?" for c in host)
    print(f"\n  Photographing {host[:50]} with a 2026 browser, then squashing it into")
    print("  1987 (about 15 seconds; the Pi is working hard)...", flush=True)
    # (F10 closes this screen under us: leave as Python usually does, so
    # the browser's scratch folder goes too. Stragglers of the browser may
    # still be writing in it, which mustn't stop the clean-up.)
    for sign in (signal.SIGHUP, signal.SIGTERM):
        signal.signal(sign, lambda *_: sys.exit(1))
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as work:
        problem = shoot(url, work)
        if problem:
            print(f"  {problem}")
        elif not as_pictures(f"{work}/page.png", host):
            print(f"\n  {host[:40]}, as a 2026 browser draws it, through 1987 eyes".ljust(COLS)[:COLS])
            page(text_art(f"{work}/page.png"))
    input("\n  That's the page. Press Enter. ")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()
