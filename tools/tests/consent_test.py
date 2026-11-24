# Saying "yes" too early, then on cue. Runs as desk against a test PAL.
import json, os, shutil, socket, time
SIM = "/tmp/pal-sim/"
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo: shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam)
    elif os.path.exists(cam): os.remove(cam)
def say(name, as_name): shutil.copy(SIM + f"queue/{name}.wav", SIM + f"mic/{as_name}.wav")
def pal(request, on_line):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(120); s.connect("/run/compaq-pal/pal.sock")
        s.sendall((json.dumps(request) + "\n").encode())
        for line in s.makefile():
            a = json.loads(line); on_line(a)
            if "say" not in a: return a
t0 = time.time()
def on_line(a):
    print(f"[{time.time()-t0:4.1f}s] menu: {a.get('say') or a.get('message')}", flush=True)
    if "Listen..." in a.get("say", ""):
        say("yes", "1-early")                    # too early: PAL is still talking
    if "listening now" in a.get("say", ""):
        time.sleep(1.5); say("yes", "2-on-cue")  # a moment after the cue, like a person
show("Buzz_Aldrin.jpg"); time.sleep(4)
result = pal({"op": "enroll", "name": "Buzz", "say_as": ""}, on_line)
print("enrolled:", result.get("ok"))
time.sleep(2)
def on_line2(a):
    print(f"[{time.time()-t0:4.1f}s] menu: {a.get('say') or a.get('message')}", flush=True)
    if "listening now" in a.get("say", ""):
        time.sleep(1); say("q1", "3-wrong")          # something else first
    elif a.get("say", "").startswith("PAL heard"):   # then, told to try again, the right words
        say("forget", "4-forget")
result = pal({"op": "forget"}, on_line2)
print("forgotten:", result.get("ok"))
show(None)
