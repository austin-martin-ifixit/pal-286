# The lobby rehearsal after the review fixes. Runs as desk on the Pi.
import glob, json, os, shutil, socket, subprocess, sys, threading, time
sys.path.insert(0, "/tmp")
from bridge_test3_lib import FakeCable, go_welcome, shared

SIM = "/tmp/pal-sim/"
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo:
        shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam)
    elif os.path.exists(cam):
        os.remove(cam)
def say(name): shutil.copy(SIM + f"queue/{name}.wav", SIM + f"mic/{name}.wav")
def spoken(): return len(glob.glob(SIM + "said/*.wav"))
def wait_spoken(count, seconds):
    end = time.time() + seconds
    while time.time() < end and spoken() < count:
        time.sleep(0.3)
    return spoken() >= count
def log_lines(): return open(SIM + "pal.log").read()
def pal(request, on_line=None, timeout=200):
    out = []
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(timeout); s.connect("/run/compaq-pal/pal.sock")
        s.sendall((json.dumps(request) + "\n").encode())
        for line in s.makefile():
            answer = json.loads(line); out.append(answer)
            if on_line: on_line(answer)
            if "say" not in answer: break
    return out

go_welcome()
cable = FakeCable(COMPAQ_SAVER_SECONDS="900", COMPAQ_PAL_IDLE_SECONDS="5")
screens = []
def pump():
    last = None
    while cable.running:
        cable.read(0.4)
        text = "\n".join(l.rstrip() for l in cable.screen.display)
        if "P A L" in text and text != last:
            last = text; screens.append(text)
threading.Thread(target=pump, daemon=True).start()
t0 = time.time()
def stamp(msg): print(f"[{time.time()-t0:5.1f}s] {msg}", flush=True)
try:
    show(None); time.sleep(5)
    stamp("1. Buzz teaches PAL his face (and must say yes)")
    show("Buzz_Aldrin.jpg"); time.sleep(3)
    def on_line(a):
        stamp("   menu shows: " + (a.get("say") or a.get("message", "")))
        if "listening now" in a.get("say", ""):
            say("yes")
    pal({"op": "enroll", "name": "Buzz", "say_as": ""}, on_line)
    stamp(f"   PAL knows: {pal({'op': 'status'})[0]['people']} face(s)")
    show(None); time.sleep(6)

    stamp("2. a stranger (Neil) walks up")
    before = spoken(); show("Neil_Armstrong_pose.jpg")
    stamp(f"   greeted: {wait_spoken(before + 1, 40)}")
    say("q1"); stamp("   asks: what is the weather like today?")
    stamp(f"   answered: {wait_spoken(before + 2, 60)}")
    say("q2"); stamp("   says: thanks, see you later")
    stamp(f"   answered: {wait_spoken(before + 3, 60)}")
    time.sleep(16 + 32)   # the conversation ends, then the follow-up half minute passes
    n = log_lines().count("conversation (")
    say("paul"); stamp("   says (not to PAL): is Paul in today?")
    time.sleep(10)
    stamp(f"   PAL stayed out of it: {log_lines().count('conversation (') == n}")
    show(None); time.sleep(6)

    stamp("3. Buzz comes back")
    before = spoken(); show("Buzz_Aldrin.jpg")
    stamp(f"   greeted: {wait_spoken(before + 1, 40)}")
    time.sleep(16)                 # don't count as someone typing
    say("dust"); stamp("   asks: hey pal, open dust run")
    end = time.time() + 60
    while time.time() < end and "Enter: play" not in shared():
        time.sleep(0.5)
    stamp(f"   DUSTRUN open on the shared screen: {'Enter: play' in shared()}")
    time.sleep(8); go_welcome(); time.sleep(3)
    before = spoken()
    say("series"); stamp("   asks: hey pal, who won the most recent World Series?")
    stamp(f"   answered: {wait_spoken(before + 1, 90)}")
    time.sleep(20)

    stamp("4. Buzz asks the menu to forget him (and must say forget me)")
    def on_line2(a):
        stamp("   menu shows: " + (a.get("say") or a.get("message", "")))
        if "listening now" in a.get("say", ""):
            say("forget")
    pal({"op": "forget"}, on_line2)
    stamp(f"   PAL knows: {pal({'op': 'status'})[0]['people']} face(s)")
finally:
    show(None); cable.close(); go_welcome()
print("\n=== the last Compaq screen PAL showed ===")
if screens:
    print("\n".join("|" + l.ljust(80) + "|" for l in screens[-1].split("\n")[14:]))
