# "Hey FixBot" through FixBot's OWN page (lib/fixbot_page.py) with the real
# iFixit login, on the simulated PAL: a repair walked through, the guide
# panel, the next step, a webcam photo asked about, and goodbye. Each
# question is a real FixBot chat on that account. Runs as pal on the Pi: on
# the Mac, tools/tests/fixbot_voices.sh; then on the Pi,
# REAL_FIXBOT_PAGE=1 bash run_pal_tests.sh fixbot_page_test.py:pal
# Saves the simulated TV at each stage: /tmp/pal-sim/page-*.png
import glob, os, re, shutil, subprocess, time

SIM = "/tmp/pal-sim/"
VOICES = "/tmp/rig/tests/fixbot-voices/"
t0 = time.time()


def stamp(msg):
    print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)


def show(photo):
    cam = SIM + "camera/current.jpg"
    shutil.copy(SIM + "photos/" + photo, cam + ".new")
    os.replace(cam + ".new", cam)


n = [0]
def say(text):
    n[0] += 1
    tmp = SIM + f"mic/.{n[0]}.tmp.wav"
    if os.path.exists(VOICES + text + ".wav"):
        shutil.copy(VOICES + text + ".wav", tmp)
    else:
        raw = subprocess.run(["espeak-ng", "-v", "en-us+m1", "-s", "150", "--stdout", text], capture_output=True).stdout
        subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", tmp], input=raw)
    os.replace(tmp, SIM + f"mic/{n[0]:03d}.wav")


def said_files():
    return sorted(glob.glob(SIM + "said/*.wav"))


def words(files):
    out = []
    for f in files:
        try:
            out.append(open(f[:-4] + ".txt").read().strip())
        except FileNotFoundError:
            pass
    return " ".join(out)


def log():
    return open(SIM + "pal.log").read()


def answered():
    return len(re.findall(r"fixbot page: answered in", log()))


def settle(limit):
    end = time.time() + limit
    last, quiet = len(said_files()), time.time()
    while time.time() < end and time.time() - quiet < 4:
        time.sleep(0.3)
        if len(said_files()) != last:
            last, quiet = len(said_files()), time.time()


def ask(line, needle=None, limit=200):
    """Says line; waits for FixBot's next answer (or needle) and PAL to finish
    reading it; returns what PAL said."""
    before, got = len(said_files()), answered()
    say(line)
    end = time.time() + limit
    while time.time() < end:
        if needle and needle.lower() in words(said_files()[before:]).lower():
            break
        if not needle and answered() > got:
            break
        time.sleep(0.5)
    settle(120)
    return words(said_files()[before:])


def snap(name):
    time.sleep(2.5)                        # (the simulated TV is saved every 2 s)
    shutil.copy(SIM + "screen.png", SIM + f"page-{name}.png")


results = {}
show("Buzz_Aldrin.jpg")
time.sleep(6)

stamp("1. 'Hey FixBot, I'm trying to fix my iPhone 12 screen. Can you pull up the guide and walk me through it?'")
text = ask("iphone", limit=240)
stamp(f"   PAL said ({len(text.split())} words): {text[:500]!r}")
results["the page opened, logged in"] = "fixbot page: open (logged in)" in log()
results["FixBot answered, read out"] = answered() >= 1 and len(text.split()) > 12
results["it named the guide"] = "iphone 12" in text.lower() and "guide" in text.lower()
results["no Claude in it"] = "timing:" not in log().split("fixbot page: open")[-1]
snap("1-answer")

stamp("2. 'Open the guide.'")
text = ask("guide", needle="screen", limit=40)
stamp(f"   PAL said: {text!r}")
results["the guide panel opened"] = "The guide's on the screen" in text
snap("2-guide")

stamp("3. 'What's the next step?' (to FixBot)")
text = ask("nextstep")
stamp(f"   PAL said ({len(text.split())} words): {text[:500]!r}")
results["FixBot answered the next step"] = answered() >= 2 and len(text.split()) > 8
snap("3-next")

stamp("4. 'Take a picture of this.' (the camera sees a phone)")
show("phone.jpg")
time.sleep(2)
text = ask("picture", needle="ask FixBot about it", limit=60)
stamp(f"   PAL said: {text!r}")
results["the photo went into FixBot's photo button"] = "Got it" in text and "a photo for FixBot" in log()

stamp("5. 'What is this part, and what does it do?' (with the photo)")
text = ask("whatisthis")
stamp(f"   PAL said ({len(text.split())} words): {text[:500]!r}")
results["FixBot answered about the photo"] = answered() >= 3 and len(text.split()) > 8
snap("5-photo-answer")
show("Buzz_Aldrin.jpg")

stamp("6. 'We're done.'")
text = ask("We're done.", needle="Good luck", limit=60)
stamp(f"   PAL said: {text!r}")
results["done: goodbye, and a fresh chat for the next person"] = "Good luck" in text

for line in [l for l in log().splitlines() if l.startswith("fixbot")]:
    stamp("   log: " + line)
trouble = [l for l in log().splitlines() if any(w in l for w in ("main loop:", "Traceback", "brain:"))]
results["no errors in PAL's log"] = not trouble
print()
for what, ok in results.items():
    print(("ok    " if ok else "FAIL  ") + what)
print("\n" + ("All passed." if all(results.values()) else f"{sum(not v for v in results.values())} failed."))
