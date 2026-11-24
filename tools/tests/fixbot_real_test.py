# "Hey FixBot" against the REAL FixBot, on the simulated PAL: real plans
# (a minute or so each, on the workspace's FixBot plan), a real guide and
# its photos. Runs as pal on the Pi: on the Mac, tools/tests/fixbot_voices.sh;
# then on the Pi, REAL_FIXBOT=1 bash run_pal_tests.sh fixbot_real_test.py:pal
# Saves the simulated TV at each stage: /tmp/pal-sim/real-*.png
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


def answers():
    return re.findall(r"fixbot: answered in (\d+) s \((\d+) characters\)", log())


def settle(limit):
    """Waits until PAL has been quiet for 4 s (or limit)."""
    end = time.time() + limit
    last, quiet = len(said_files()), time.time()
    while time.time() < end and time.time() - quiet < 4:
        time.sleep(0.3)
        if len(said_files()) != last:
            last, quiet = len(said_files()), time.time()


def wait_for(before, needle, limit):
    end = time.time() + limit
    while time.time() < end and needle.lower() not in words(said_files()[before:]).lower():
        time.sleep(0.5)
    settle(max(5, end - time.time()))
    return words(said_files()[before:])


def snap(name):
    time.sleep(2.5)                        # (the simulated TV is saved every 2 s)
    shutil.copy(SIM + "screen.png", SIM + f"real-{name}.png")


results = {}
show("Buzz_Aldrin.jpg")
time.sleep(6)

stamp("1. 'Hey FixBot, I'm trying to fix my iPhone 12 screen. Can you pull up the guide and walk me through it?'")
before, got = len(said_files()), len(answers())
say("iphone")
text = wait_for(before, "Say next when you're ready", 300)
stamp(f"   PAL said ({len(text.split())} words): {text[:600]!r}")
results["a real plan came back"] = len(answers()) > got
results["the guide FixBot recommended opened"] = "Say next when you're ready" in text
snap("1-overview")

stamp("2. 'Next step.'")
before = len(said_files())
say("Next step.")
text = wait_for(before, "Step 1.", 40)
stamp(f"   PAL said: {text!r}")
results["next: step 1 of the real guide"] = "Step 1." in text
snap("2-step1")

stamp("3. 'Show me the photo.'")
before = len(said_files())
say("photo")
text = wait_for(before, "photo", 40)
stamp(f"   PAL said: {text!r}")
results["the step's real photo"] = "photo" in text.lower()
snap("3-photo")

stamp("4. 'What does this cable do?' (to the real FixBot, with the step)")
before, got = len(said_files()), len(answers())
say("What does this cable do?")
end = time.time() + 300
while time.time() < end and len(answers()) == got:
    time.sleep(1)
settle(120)
text = words(said_files()[before:])
stamp(f"   PAL said ({len(text.split())} words): {text[:600]!r}")
results["a real answer to the question"] = len(answers()) > got
snap("4-answer")

stamp("5. 'We're done.'")
before = len(said_files())
say("We're done.")
text = wait_for(before, "Good luck", 60)
stamp(f"   PAL said: {text!r}")
results["done"] = "Good luck" in text

for line in [l for l in log().splitlines() if l.startswith("fixbot:")]:
    stamp("   log: " + line)
trouble = [l for l in log().splitlines() if any(w in l for w in ("main loop:", "Traceback", "brain:"))]
results["no errors in PAL's log"] = not trouble
print()
for what, ok in results.items():
    print(("ok    " if ok else "FAIL  ") + what)
print("\n" + ("All passed." if all(results.values()) else f"{sum(not v for v in results.values())} failed."))
