"""Pictures for PAL's screen: the webcam turned into text art (the mirror
and the photo booth), and photos for Claude to look at (what's wrong with
this phone?). Nothing here is kept unless someone asks to save a portrait.
"""

import base64
import os
import time

import cv2
import numpy as np

# Darkest to brightest: on the amber plasma, more ink is more glow.
RAMP = " .'`,:;-~+=*xoaO0#%@"
PORTRAITS = "/var/lib/compaq/portraits"   # saved photo-booth pictures (pal:desk 2750)


def text_art(image, cols=79, rows=22, mirror=True):
    """The picture as rows of characters, keeping its shape (a character
    cell is about twice as tall as it is wide), centred in cols x rows."""
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if mirror:
        grey = cv2.flip(grey, 1)
    h, w = grey.shape
    width = min(cols, int(rows * 2 * w / h))
    height = min(rows, int(width * h / w / 2))
    small = cv2.resize(grey, (width, height), interpolation=cv2.INTER_AREA)
    # Even out the lighting so faces and things stand out in a dim lobby.
    small = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4)).apply(small)
    levels = (small.astype(np.float32) / 256 * len(RAMP)).astype(int)
    pad = " " * ((cols - width) // 2)
    lines = [pad + "".join(RAMP[v] for v in row) for row in levels]
    top = (rows - height) // 2
    return [""] * top + lines + [""] * (rows - height - top)


def picture(image, mirror=True):
    """A camera frame as a grey PIL image (mirrored, as a mirror shows
    people), for a real picture on the Compaq's screen (pictures.py)."""
    from PIL import Image
    grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return Image.fromarray(cv2.flip(grey, 1) if mirror else grey)


def jpeg_base64(image, longest=768):
    """A photo for Claude: JPEG, no bigger than it needs to be."""
    h, w = image.shape[:2]
    scale = min(1.0, longest / max(h, w))
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(data.tobytes()).decode() if ok else None


def save_portrait(lines, caption):
    """Keeps a photo-booth picture for the gallery (the PAL 286 menu)."""
    name = time.strftime("%Y%m%d-%H%M%S") + ".txt"
    path = os.path.join(PORTRAITS, name)
    with open(path, "w") as f:
        f.write(caption + "\n" + "\n".join(lines) + "\n")
    os.chmod(path, 0o640)
    return name
