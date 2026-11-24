# The lobby quiz, against the simulator (words written beside each sound),
# with the board on the real TV. Runs as root on the Pi.
import glob, os, shutil, subprocess, time
import numpy as np
from PIL import Image

SIM = "/tmp/pal-sim/"
t0 = time.time()


def stamp(msg):
    print(f"[{time.time()-t0:5.1f}s] {msg}", flush=True)


def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo:
        shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam); os.chmod(cam, 0o644)
    elif os.path.exists(cam):
        os.remove(cam)


n = [0]
def say(text):
    n[0] += 1
    raw = subprocess.run(["espeak-ng", "-v", "en-us+f3", "-s", "140", "--stdout", text], capture_output=True).stdout
    tmp = SIM + f"mic/.{n[0]}.wav"
    subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", tmp], input=raw)
    os.chmod(tmp, 0o666); os.replace(tmp, SIM + f"mic/{n[0]:03d}.wav")


def shot(name):
    w, h = 1366, 768
    p = np.fromfile("/dev/fb0", np.uint16, count=w*h).reshape(h, w).astype(np.uint32)
    rgb = np.stack([((p >> 11) & 31) * 255 // 31, ((p >> 5) & 63) * 255 // 63, (p & 31) * 255 // 31], -1)
    Image.fromarray(rgb.astype(np.uint8)).save(f"/tmp/{name}.png")


def files():
    return sorted(glob.glob(SIM + "said/*.wav"))


def wait_reply(before, settle=4, limit=90):
    end = time.time() + limit
    while time.time() < end and len(files()) <= before:
        time.sleep(0.3)
    last, quiet = len(files()), time.time()
    while time.time() < end and time.time() - quiet < settle:
        time.sleep(0.3)
        if len(files()) != last:
            last, quiet = len(files()), time.time()
    out = []
    for f in files()[before:]:
        try:
            out.append(open(f[:-4] + ".txt").read().strip())
        except FileNotFoundError:
            pass
    return " ".join(out)


def log():
    return open(SIM + "pal.log").read()


TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
time.sleep(125)                      # nobody typing for 2 minutes: PAL may use the screen
show("Neil_Armstrong_pose.jpg")
stamp("greeting: " + wait_reply(0))
time.sleep(2)
before = len(files())
say("Hey pal, quiz me about space.")
stamp("PAL: " + wait_reply(before))
shot("quiz-board")
for i, answer in enumerate(["B.", "A.", "C.", "B.", "A."]):
    before = len(files())
    say(answer)
    stamp(f"me: {answer}  PAL: " + wait_reply(before))
    if i == 1:
        shot("quiz-board2")
shot("quiz-final")
stamp("tools: " + str([l for l in log().splitlines() if l.startswith(("tool:", "quiz:"))]))
show(None)
