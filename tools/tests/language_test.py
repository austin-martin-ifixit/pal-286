# Switching languages on request. Runs as pal against the simulator.
import glob, os, shutil, subprocess, time
SIM = "/tmp/pal-sim/"
t0 = time.time()
def stamp(m): print(f"[{time.time()-t0:5.1f}s] {m}", flush=True)
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo: shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam)
    elif os.path.exists(cam): os.remove(cam)
n = [0]
def say(text, voice="en-us+m1"):
    n[0] += 1
    raw = subprocess.run(["espeak-ng", "-v", voice, "-s", "140", "--stdout", text], capture_output=True).stdout
    tmp = SIM + f"mic/.{n[0]}.wav"
    subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", tmp], input=raw)
    os.replace(tmp, SIM + f"mic/{n[0]:03d}.wav")
def files(): return sorted(glob.glob(SIM + "said/*.wav"))
def wait_reply(before, settle=4, limit=90):
    end = time.time() + limit
    while time.time() < end and len(files()) <= before: time.sleep(0.3)
    last, quiet = len(files()), time.time()
    while time.time() < end and time.time() - quiet < settle:
        time.sleep(0.3)
        if len(files()) != last: last, quiet = len(files()), time.time()
    out = []
    for f in files()[before:]:
        try: out.append(open(f[:-4] + ".txt").read().strip())
        except FileNotFoundError: pass
    return " ".join(out)
def log(): return open(SIM + "pal.log").read()
show("Buzz_Aldrin.jpg")
stamp("greeting: " + wait_reply(0)); time.sleep(2)
b = len(files()); say("Hey pal, can you speak Spanish with me?")
stamp("PAL: " + wait_reply(b))
b = len(files()); say("¿Cuál es la capital de Francia?", "es")
stamp("PAL: " + wait_reply(b))
b = len(files()); say("Pon un poco de música, por favor.", "es")
stamp("PAL: " + wait_reply(b, limit=120))
stamp("log: " + " | ".join(l for l in log().splitlines() if l.startswith(("language", "tool", "music"))))
time.sleep(50)
stamp("back to English: " + str(log().rstrip().endswith("language: en") or "language: en" in log().split("language: es")[-1]))
show(None)
