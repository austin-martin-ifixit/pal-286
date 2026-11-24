# FixBot mode end to end against the simulated PAL, with a stand-in FixBot
# on 127.0.0.1:8199 (never the real key or server; see run_sim.sh). Runs as
# pal on the Pi after run_sim.sh: run_pal_tests.sh fixbot_sim_test.py:pal
# does both. The lines espeak can't say ("FixBot", "photo") are the Mac's
# Daniel voice: make them first, on the Mac, with tools/tests/fixbot_voices.sh.
# Commands wait at most 40 s, so one misheard can't leave the rest outside
# FixBot's conversation (it listens for 20 s). Screenshots of the simulated
# TV: /tmp/pal-sim/fixbot-step.png and fixbot-answer.png. The "Hey PAL" hand-over at the end uses Claude.
import glob, http.server, json, os, shutil, subprocess, threading, time

SIM = "/tmp/pal-sim/"
VOICES = "/tmp/rig/tests/fixbot-voices/"
KEY = "sim-key-not-real"
CHAT = "5e1f00d5-0000-4000-8000-000000000001"
t0 = time.time()

PLAN = """## iPhone 12 screen replacement

Replacing an iPhone 12 screen takes about an hour. You'll need a P2 pentalobe driver,
a suction handle and an opening pick. (Stand-in FixBot plan.)

1. Power off the phone and remove the two pentalobe screws.
2. Heat the bottom edge, then lift the screen with the suction handle.
3. Disconnect the battery first, then the display cables.
"""
PHOTO = "https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium"
GUIDE = {"title": "iPhone 12 Screen Replacement", "difficulty": "Moderate", "time_required": "1 - 2 hours",
         "source_url": "https://www.ifixit.com/Guide/iPhone+12+Screen+Replacement/140572",
         "tools": [{"text": "iOpener"}, {"text": "P2 Pentalobe Screwdriver"}], "parts": [],
         "introduction": "<p>Replace a cracked or broken screen.</p>",
         "conclusion": "<p>Reassemble in reverse order.</p>",
         "steps": [{"number": n, "title": title, "lines": [{"level": 0, "bullet": "black", "text_rendered": text}],
                    "media": {"type": "image", "data": [{"medium": PHOTO}, {"medium": PHOTO}] if n == 3 else []}}
                   for n, title, text in [(1, "Power off your iPhone", "Hold the side button."),
                                          (2, "Remove the screws", "Remove the two <b>6.7 mm</b> screws."),
                                          (3, "Apply a suction cup", "Apply a suction handle to the bottom edge.")]]}
asked = []        # what PAL sent the stand-in


class FixBot(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/resources/guide/140572"):
            return self.reply(200, GUIDE)
        self.reply(404, {"error": "not_found", "message": "Not here."})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        asked.append({"auth": self.headers.get("Authorization"), "path": self.path, "body": body})
        if self.headers.get("Authorization") != f"Bearer {KEY}":
            return self.reply(401, {"error": "unauthorized"})
        time.sleep(4)                      # (real plans take longer)
        if not body.get("chatid"):
            return self.reply(200, {"chatid": CHAT, "plan": PLAN, "matchedDevice": "iPhone 12",
                                    "primaryGuide": {"guideid": 140572, "title": GUIDE["title"],
                                                     "url": GUIDE["source_url"]},
                                    "partsEstimate": [{"name": "iPhone 12 Screen", "cost": 89.99, "currency": "USD"}]})
        self.reply(200, {"chatid": CHAT, "matchedDevice": "iPhone 12", "partsEstimate": [],
                         "plan": "## That cable\n\nThat's the display's flex cable: the stand-in answer."})


def stamp(msg):
    print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)


def show(photo):
    cam = SIM + "camera/current.jpg"
    shutil.copy(SIM + "photos/" + photo, cam + ".new")
    os.replace(cam + ".new", cam)


n = [0]
def say(text):
    """espeak into the simulated microphone (or, for a name in VOICES, that recording)."""
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
            pass          # a sound effect
    return " ".join(out)


def wait_for(before, needle, limit=120):
    """Waits until PAL has said needle and then gone quiet; what it said."""
    end = time.time() + limit
    while time.time() < end and needle.lower() not in words(said_files()[before:]).lower():
        time.sleep(0.3)
    last, quiet = len(said_files()), time.time()
    while time.time() < end and time.time() - quiet < 3:
        time.sleep(0.3)
        if len(said_files()) != last:
            last, quiet = len(said_files()), time.time()
    return words(said_files()[before:])


def log():
    return open(SIM + "pal.log").read()


results = {}
missing = [v for v in ("iphone", "hello", "photo") if not os.path.exists(VOICES + v + ".wav")]
if missing:
    raise SystemExit(f"No recordings of {missing} in {VOICES}: run tools/tests/fixbot_voices.sh on the Mac first.")
server = http.server.ThreadingHTTPServer(("127.0.0.1", 8199), FixBot)
threading.Thread(target=server.serve_forever, daemon=True).start()
with open(SIM + "state/fixbot.env", "w") as f:
    f.write(f"FIXBOT_API_KEY={KEY}\n")
show("Buzz_Aldrin.jpg")
time.sleep(6)                              # (someone in view: PAL listens)

stamp("1. 'Hey FixBot, I'm trying to fix my iPhone 12 screen... walk me through it'")
before = len(said_files())
say("iphone")
text = wait_for(before, "say next when you're ready", 150)
stamp(f"   PAL said: {text[:300]!r}...")
first = asked[0]["body"] if asked else {}
stamp(f"   FixBot was sent: {json.dumps(first)[:300]}")
results["FixBot asked with the key"] = bool(asked) and asked[0]["auth"] == f"Bearer {KEY}"
results["their words, word for word, as device and symptoms"] = (
    "iphone 12" in first.get("device", {}).get("model", "").lower()
    and first.get("device", {}).get("model") == first.get("context", {}).get("symptoms") and "chatid" not in first)
results["'Asking FixBot', then FixBot's plan read out"] = "Asking FixBot" in text and "takes about an hour" in text
results["the guide it recommended opened (they asked for it)"] = "iPhone 12 Screen Replacement" in text and "3 steps" in text
results["no Claude in it"] = "timing:" not in log().split("fixbot: a new repair")[-1]

stamp("2. 'Next step.'")
before = len(said_files())
say("Next step.")
text = wait_for(before, "Step 1.", 40)
stamp(f"   PAL said: {text!r}")
results["next: step 1"] = "Step 1. Power off your iPhone" in text

stamp("3. 'Go to step 3.'")
before = len(said_files())
say("Go to step 3.")
text = wait_for(before, "Step 3.", 40)
stamp(f"   PAL said: {text!r}")
results["step 3 by number"] = "Step 3. Apply a suction cup" in text
time.sleep(2.5)
shutil.copy(SIM + "screen.png", SIM + "fixbot-step.png")    # (the simulated TV, every 2 s)

stamp("4. 'Show me the photo.'")
before = len(said_files())
say("photo")
text = wait_for(before, "photo", 40)
stamp(f"   PAL said: {text!r}")
results["the step's photo shown"] = "Photo 1 of 2" in text

stamp("5. 'What does this cable do?' (a question: to FixBot, with where they are)")
before = len(said_files())
say("What does this cable do?")
text = wait_for(before, "stand-in answer", 60)
follow = asked[-1]["body"] if len(asked) > 1 else {}
stamp(f"   PAL said: {text!r}")
stamp(f"   FixBot was sent: {json.dumps(follow)[:300]}")
symptoms = follow.get("context", {}).get("symptoms", "")
results["the same conversation (chatid)"] = follow.get("chatid") == CHAT
results["their question, then the step they're on"] = (
    "cable" in symptoms.lower() and symptoms.endswith("(I'm on step 3 of 3 of the guide "
                                                       "\"iPhone 12 Screen Replacement\": Apply a suction cup.)"))
results["FixBot's answer read out"] = "flex cable" in text
shutil.copy(SIM + "screen.png", SIM + "fixbot-answer.png")

stamp("6. 'Next step.' (back to the guide)")
before = len(said_files())
say("Next step.")
text = wait_for(before, "end of the guide", 40)
stamp(f"   PAL said: {text!r}")
results["next after the answer: the guide goes on"] = "end of the guide" in text

stamp("7. 'We're done.'")
before = len(said_files())
say("We're done.")
text = wait_for(before, "Good luck", 40)
stamp(f"   PAL said: {text!r}")
results["done: goodbye"] = "Good luck with the repair" in text

stamp("8. 'Hey FixBot.' on its own: a new repair, FixBot asks what")
time.sleep(5)
before = len(said_files())
say("hello")
text = wait_for(before, "What are you fixing")
stamp(f"   PAL said: {text!r}")
results["'Hey FixBot' alone: what are you fixing?"] = "What are you fixing" in text
time.sleep(25)                             # (nobody answers: it ends)

stamp("9. 'Hey PAL' with a repair question: PAL hands it to FixBot, word for word")
before, sent = len(said_files()), len(asked)
say("Hey PAL, can you help me fix the battery in my iPhone 12?")
text = wait_for(before, "takes about an hour", 150)
handed = asked[sent]["body"] if len(asked) > sent else {}
stamp(f"   PAL said: {text[:200]!r}")
stamp(f"   FixBot was sent: {json.dumps(handed)[:300]}")
results["PAL hands repairs to FixBot"] = "battery" in handed.get("context", {}).get("symptoms", "").lower()
results["what they said, not PAL's words"] = "help me fix the battery" in handed.get("context", {}).get("symptoms", "").lower()

time.sleep(25)
trouble = [line for line in log().splitlines() if any(w in line for w in ("main loop:", "Traceback", "brain:"))]
results["no errors in PAL's log"] = not trouble
for line in [line for line in log().splitlines() if line.startswith("fixbot:")]:
    stamp("   log: " + line)
os.remove(SIM + "state/fixbot.env")
server.shutdown()
print()
for what, ok in results.items():
    print(("ok    " if ok else "FAIL  ") + what)
print("\n" + ("All passed." if all(results.values()) else f"{sum(not v for v in results.values())} failed."))
