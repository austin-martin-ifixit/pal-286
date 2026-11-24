# How many frames a second would a video get on the Compaq through PILINK?
# Plays a video file against the real encoder (lib/pilink.py) with a pretend
# cable: each frame sent is whatever the video shows at that moment, and the
# next can't start until the last has crossed. Prints, for each picture size
# and way of dithering, the bytes a frame takes and the frames a second.
# Touches nothing live. Usage: python3 video_rate.py VIDEO [bytes a second] [seconds] [start at second]
import subprocess, sys
sys.path.insert(0, "/tmp/rig/lib")
import numpy as np
import pilink

VIDEO = sys.argv[1]
BPS = int(sys.argv[2]) if len(sys.argv) > 2 else 11520
SECONDS = int(sys.argv[3]) if len(sys.argv) > 3 else 40
START = int(sys.argv[4]) if len(sys.argv) > 4 else 0
FPS = 15
BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 + 1 / 32
BAYER8 = np.block([[4 * BAYER4 * 16 + 0, 4 * BAYER4 * 16 + 2], [4 * BAYER4 * 16 + 3, 4 * BAYER4 * 16 + 1]])
BAYER8 = (BAYER8 - BAYER8.min()) / 64 + 1 / 128
BAYER2 = np.array([[0, 2], [3, 1]]) / 4 + 1 / 8


def frames(width, height):
    command = ["ffmpeg", "-v", "error", "-ss", str(START), "-t", str(SECONDS), "-i", VIDEO, "-vf",
               f"fps={FPS},scale={width}:{height}:force_original_aspect_ratio=decrease:flags=area,"
               f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(command, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width)


def ordered(matrix):
    def dither(grey):
        h, w = grey.shape
        tiled = np.tile(matrix, (h // matrix.shape[0] + 1, w // matrix.shape[1] + 1))[:h, :w]
        return grey / 255 > tiled
    return dither


def diffused(grey):
    from PIL import Image
    return np.asarray(Image.fromarray(grey).convert("1"), bool)


def stretch(clip):
    low, high = np.percentile(clip, (1, 99))
    return np.clip((clip.astype(np.float32) - low) * 255 / max(1, high - low), 0, 255).astype(np.uint8)


for name in ("320x200", "320x100", "160x100", "640x200"):
    if name == "640x200" and "--all" not in sys.argv:
        continue
    layout = pilink.LAYOUTS[name]
    clip = stretch(frames(layout.width, layout.height))
    for label, dither in (("ordered 4x4", ordered(BAYER4)), ("ordered 8x8", ordered(BAYER8)),
                          ("ordered 2x2", ordered(BAYER2)), ("error diffusion", diffused)):
        encoder = pilink.Encoder(layout, sweep=True)
        encoder.setup()
        clock, shown, total = 0.0, 0, 0
        while clock < len(clip) / FPS:
            ops = encoder.frame(layout.pack(dither(clip[min(len(clip) - 1, int(clock * FPS))])))
            total += len(ops) + 2
            shown += 1
            clock += max((len(ops) + 2) / BPS, 1 / FPS)       # (nothing to send: wait for the next frame)
        print(f"{name:8} {label:16} {total // shown:6} bytes a frame  {shown / clock:5.1f} frames a second", flush=True)
