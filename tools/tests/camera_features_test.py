# Mirror, photo booth and "what's wrong with this?", on the simulator's own
# screen (sim_screen.py; shots saved as /tmp/tv-*.png). Root on the Pi.
import glob, os, shutil, subprocess, time
SIM = "/tmp/pal-sim/"
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo: shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam)
    elif os.path.exists(cam): os.remove(cam)
    os.chmod(cam, 0o644) if photo else None
def say(text, name):
    raw = subprocess.run(["espeak-ng", "-v", "en-us+m1", "-s", "150", "--stdout", text], capture_output=True).stdout
    subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", SIM + f"mic/{name}.wav"], input=raw)
    os.chmod(SIM + f"mic/{name}.wav", 0o666)
def shot(name):
    time.sleep(2.5)                   # (the simulator's screen is saved every 2 seconds)
    shutil.copy(SIM + "screen.png", f"/tmp/{name}.png")
def log(): return open(SIM + "pal.log").read()
def settle(quiet=4, limit=60):
    """Waits until PAL has stopped talking (nothing new said for a few seconds)."""
    end = time.time() + limit
    last, since = len(glob.glob(SIM + "said/*.wav")), time.time()
    while time.time() < end and time.time() - since < quiet:
        time.sleep(0.5)
        now = len(glob.glob(SIM + "said/*.wav"))
        if now != last:
            last, since = now, time.time()
time.sleep(8)         # nobody "typing" for 5 seconds, so PAL may borrow the screen
show("Buzz_Aldrin.jpg"); time.sleep(4); settle(5)
print("greeting done:", "conversation over" in log() or "conversation" in log())
time.sleep(4)
say("Hey pal, show me the mirror.", "1"); time.sleep(16); shot("tv-mirror")
print("mirror:", "mirror: on" in log())
settle(5, 60)         # (the mirror runs 30 seconds)
say("Hey pal, please take a photo of me.", "2"); time.sleep(20); shot("tv-photo")
settle(4)             # (the countdown) PAL asks whether to keep it, then listens
print("photo:", "photo booth: took a picture" in log())
say("Yes, save it please.", "3"); time.sleep(4); settle(4)
print("saved:", "saved a portrait" in log(), glob.glob("/var/lib/compaq/portraits/*.txt"))
time.sleep(14)        # (that conversation over)
# Asked while a face is in view (so PAL is listening); the phone comes up
# while PAL is still working out what was said.
say("Hey pal, what's wrong with this phone I'm holding?", "4"); time.sleep(2.5)
show("phone.jpg"); time.sleep(10); settle(5, 60)
print("looked:", "look: someone showed" in log())
time.sleep(25); shot("tv-guide")
show(None)
print("tools:", [l for l in log().splitlines() if l.startswith("tool:")])
said = sorted(glob.glob(SIM + "said/*.txt"))
print("PAL said:")
for f in said[-12:]:
    print("  ", open(f).read().strip()[:150])
