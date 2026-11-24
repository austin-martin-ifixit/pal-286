# Music by voice: simulated camera and microphone, the real TV speaker and
# screen. Root on the Pi.
import glob, os, shutil, subprocess, time
import numpy as np
from PIL import Image
SIM = "/tmp/pal-sim/"
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo: shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam); os.chmod(cam, 0o644)
    elif os.path.exists(cam): os.remove(cam)
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
def log(): return open(SIM + "pal.log").read()
def wait_log(text, count, limit):
    end = time.time() + limit
    while time.time() < end and log().count(text) < count: time.sleep(0.5)
    return log().count(text) >= count
TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
time.sleep(125)                     # nobody typing for 2 minutes: PAL may use the screen
show("Buzz_Aldrin.jpg")
print("greeted:", wait_log("conversation over", 1, 60)); time.sleep(3)
say("Hey pal, play the hall of the mountain king.")
print("tune started:", wait_log("music:", 1, 60)); time.sleep(12); shot("music-card")
wait_log("conversation over", 2, 120); time.sleep(3)
say("Hey pal, compose a brand new song about the lobby.")
print("composed one:", wait_log("music: a new tune", 1, 150)); time.sleep(8); shot("music-original")
wait_log("conversation over", 3, 150); time.sleep(3)
say("Hey pal, sing happy birthday to Austin.")
print("sang:", wait_log("music: a song", 1, 90)); time.sleep(6); shot("music-birthday")
wait_log("conversation over", 4, 120)
show(None)
print("tools:", [l for l in log().splitlines() if l.startswith(("tool:", "music:"))])
for f in sorted(glob.glob(SIM + "said/*.txt"))[-14:]:
    print("  PAL:", open(f).read().strip()[:160])
