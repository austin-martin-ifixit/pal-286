# Tonight's fixes, end to end against the simulated PAL. Runs as pal on the Pi
# (so it may use Whisper to hear what PAL said back).
import glob, json, os, shutil, socket, subprocess, time, urllib.request, uuid

SIM = "/tmp/pal-sim/"
t0 = time.time()


def stamp(msg):
    print(f"[{time.time()-t0:5.1f}s] {msg}", flush=True)


def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo:
        shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam)
    elif os.path.exists(cam):
        os.remove(cam)


n = [0]
def say(text):
    n[0] += 1
    raw = subprocess.run(["espeak-ng", "-v", "en-us+m1", "-s", "150", "--stdout", text], capture_output=True).stdout
    tmp = SIM + f"mic/.{n[0]}.tmp.wav"
    subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", tmp], input=raw)
    os.replace(tmp, SIM + f"mic/{n[0]:03d}.wav")


def said_files():
    return sorted(glob.glob(SIM + "said/*.wav"))


def hear(path):
    pcm = subprocess.run(["sox", path, "-r", "16000", "-c", "1", "-b", "16", "-t", "wav", "-"],
                         capture_output=True).stdout
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\n\r\n".encode()
            + pcm + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\njson\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request("http://127.0.0.1:8178/inference", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r).get("text", "").strip()


def tick(path):
    """PAL's "got it" tick (a short sound, no words beside it)."""
    return not os.path.exists(path[:-4] + ".txt") and os.path.getsize(path) < 22050 * 2 * 8 // 10   # (under 0.8 s)


def wait_reply(before, settle=4, limit=90):
    """Waits until PAL has said something (a tick isn't saying) and gone
    quiet; returns the new files."""
    end = time.time() + limit
    while time.time() < end and all(tick(f) for f in said_files()[before:]):
        time.sleep(0.3)
    last, quiet = len(said_files()), time.time()
    while time.time() < end and time.time() - quiet < settle:
        time.sleep(0.3)
        if len(said_files()) != last:
            last, quiet = len(said_files()), time.time()
    return said_files()[before:]


def words(files):
    """What PAL said in those files (the simulator writes the words beside each one)."""
    out = []
    for f in files:
        try:
            out.append(open(f[:-4] + ".txt").read().strip())
        except FileNotFoundError:
            pass          # a sound effect
    return " ".join(out)


def replies_since(before):
    return words(wait_reply(before))


def log():
    return open(SIM + "pal.log").read()


def pal(request, on_line=None):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(120); s.connect("/run/compaq-pal/pal.sock")
        s.sendall((json.dumps(request) + "\n").encode())
        for line in s.makefile():
            a = json.loads(line)
            if on_line: on_line(a)
            if "say" not in a: return a


results = {}
show(None); time.sleep(4)

stamp("1. consent: 'no, don't' must not count as yes")
show("Buzz_Aldrin.jpg"); time.sleep(4)
def on_line(a):
    stamp("   menu: " + (a.get("say") or a.get("message", "")))
    if "listening now" in a.get("say", ""):
        time.sleep(1); say("No, don't do that.")
    elif a.get("say", "").startswith("PAL heard"):    # (as a person would: when told to try again)
        say("Yes.")
r = pal({"op": "enroll", "name": "Buzz", "say_as": ""}, on_line)
consent = [l for l in log().splitlines() if l.startswith("consent:")]
stamp(f"   consent log: {consent[-2:]}")
results["negation refused, then yes accepted"] = r.get("ok") and "not agreed" in consent[-2] and consent[-1].endswith("agreed") and "not" not in consent[-1]
greets = log().count("conversation (greeting)")
time.sleep(10)
results["no hello right after teaching a face"] = log().count("conversation (greeting)") == greets

stamp("2. 'Hey PAL' ... (pause) ... the question")
before = len(said_files())
say("Hey pal.")
time.sleep(2.2)
say("What is seven times six?")
text = replies_since(before)
stamp(f"   PAL said: {text!r}")
results["name, pause, question answered"] = "42" in text or "forty" in text.lower()
files = said_files()[before:]
spoken = [i for i, f in enumerate(files) if not tick(f)]
results["a tick before the answer"] = any(tick(f) for f in files[:spoken[-1]]) if spoken else False
question_text = text

stamp("3. without 'Hey PAL', talk after the conversation is left alone")
time.sleep(14)          # the conversation ends (12 s of quiet)
before = len(said_files())
say("And what was that number again?")
time.sleep(7)
results["no 'Hey PAL': no answer, no tick"] = len(said_files()) == before

stamp("   ...and 'Hey PAL' soon after picks the conversation back up")
before = len(said_files())
say("Hey pal, what was that number again?")
text = replies_since(before)
stamp(f"   PAL said: {text!r}")
results["follow-up remembers"] = "42" in text or "forty" in text.lower()
stamp("   log: " + " | ".join(l for l in log().splitlines()[-6:]))

stamp("4. 'forget me' in conversation, with a check")
time.sleep(14)
before = len(said_files())
say("Hey pal, please forget me.")
asked = wait_reply(before)
if "forgot someone" not in log():
    before = len(said_files())
    say("Yes.")                       # straight away, like a person would
    stamp(f"   PAL said: {words(asked)!r}")
    stamp(f"   PAL said: {replies_since(before)!r}")
else:
    stamp(f"   PAL said: {words(asked)!r}")
people = pal({"op": "status"})["people"]
results["forgotten after confirming"] = people == 0 and "forgot someone, at their request" in log()
tools = [l for l in log().splitlines() if l.startswith("tool:")]
stamp(f"   tools used: {tools}")
show(None)

print()
for name, ok in results.items():
    print(("PASS " if ok else "FAIL ") + name)
