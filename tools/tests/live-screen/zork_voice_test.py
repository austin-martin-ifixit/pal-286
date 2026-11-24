# Talking to Zork: open it from the TV keyboard, then "say" commands. Root on the Pi.
import fcntl, glob, os, shutil, subprocess, termios, time
TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
SIM = "/tmp/pal-sim/"
def screen(): return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
def tv(keys):
    fd = os.open("/dev/tty7", os.O_RDWR | os.O_NOCTTY)
    for b in keys: fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
    os.close(fd)
def show(photo):
    cam = SIM + "camera/current.jpg"
    if photo: shutil.copy(SIM + "photos/" + photo, cam + ".new"); os.replace(cam + ".new", cam); os.chmod(cam, 0o644)
    elif os.path.exists(cam): os.remove(cam)
def say(text, name):
    raw = subprocess.run(["espeak-ng", "-v", "en-us+m1", "-s", "150", "--stdout", text], capture_output=True).stdout
    subprocess.run(["sox", "-t", "wav", "-", "-r", "16000", "-c", "1", "-b", "16", SIM + f"mic/{name}.wav"], input=raw)
    os.chmod(SIM + f"mic/{name}.wav", 0o666)
show("Buzz_Aldrin.jpg"); time.sleep(25)       # (the player is in view; PAL says hello first)
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session menu"]); time.sleep(2)
tv(b"@40-games/10-adventures\r"); time.sleep(2); tv(b"4\r"); time.sleep(1.5); tv(b"\r"); time.sleep(4)
print("Zork open:", "West of House" in screen())
time.sleep(12)   # PAL's screen watcher notices the game, and says moves can be spoken
print("voice hint given:", "told the player they can speak" in open(SIM + "pal.log").read())
tests = [("Open the mailbox.", "open the mailbox"),
         ("I want to get the paper thing out of the mailbox.", "take"),
         ("Okay, read it.", "read")]
for i, (line, want) in enumerate(tests):
    say(line, f"{i}")
    end = time.time() + 25
    while time.time() < end and f">{want}" not in screen():
        time.sleep(0.5)
    typed = [l for l in screen().splitlines() if l.startswith(">" + want)]
    print(f"said {line!r}: typed {typed[-1] if typed else None!r}")
    time.sleep(2)
for l in screen().splitlines()[-8:]:
    print("   |", l)
print("power-on beep and other sounds written:", len(glob.glob(SIM + "said/*.wav")))
show(None)
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
