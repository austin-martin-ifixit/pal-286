# PAL's picture tools (photo booth, QR codes), end to end on the virtual Compaq: real MS-DOS Kermit in
# DOSBox, a private copy of the serial bridge, a private tmux server. Keys are
# sent as the Compaq would send them (into the cable). Nothing touches the
# lobby's shared screen.
import os
os.environ['COMPAQ_BRIDGE'] = '/tmp/rig/bridge.sock'
sys_path_done = None
import pty, signal, socket, subprocess, sys, threading, time, tty
import cv2
import numpy as np
from PIL import Image

LIB = "/tmp/rig/lib"
TM = ["tmux", "-L", "rigtest"]
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
time.sleep(1)

server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 5555)); server.listen(1)
subprocess.Popen(["/tmp/rig/start.sh"])
kermit, _ = server.accept()
master, slave = pty.openpty()
tty.setraw(slave)
device = os.ttyname(slave)

def relay():
    while True:
        r, _, _ = __import__("select").select([master, kermit], [], [])
        if master in r:
            data = os.read(master, 96)               # at a 9600-baud cable's pace
            kermit.sendall(data)
            time.sleep(len(data) / 960)
        if kermit in r:
            data = kermit.recv(4096)
            if not data:
                return
            os.write(master, data)
threading.Thread(target=relay, daemon=True).start()

def keys(text):
    os.write(master, text.encode())          # as if typed at the Compaq

def shot(name, wait):
    time.sleep(wait)
    subprocess.run(["xdotool", "mousemove", "799", "599"], env={"DISPLAY": ":99"})
    time.sleep(0.3)
    subprocess.run(["/tmp/rig/shot.sh", name])
    img = Image.open(f"/tmp/rig/{name}.png").convert("RGB").crop((80, 100, 720, 500))
    img.save(f"/tmp/rig/{name}.png")
    return img



sys.path[:0] = ["/tmp/rig/lib"]
import pictures, ifixit                      # (the new ones, before PAL adds /opt/compaq/lib)
sys.path.insert(0, "/tmp/rig/pal")
import pal as P
import urllib.request

subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                     "echo; echo '  THE SHARED SCREEN (a stand-in)'; sleep 600"])
time.sleep(6)
bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({device!r}, '9600').run()
"""])
time.sleep(4)

class Fake:
    pass
class FakeScreen:
    shown = canvas = False
    pictures = 0
    def begin(self, canvas=False, requested=False):
        self.shown, self.canvas = True, canvas
        return True
    def frame(self, lines):
        print("  (fell back to text art)")
        return True
pal = Fake()
pal.screen = FakeScreen()
pal.eyes = Fake(); pal.eyes.status = "ok"
pal.speak = lambda word: print("  PAL says:", word)
pal.lock = threading.Lock()
data = urllib.request.urlopen(urllib.request.Request(
    "https://guide-images.cdn.ifixit.com/igi/3DrAgS2S2IaCnYj6.medium", headers={"User-Agent": "x"}), timeout=30).read()
pal.latest = [cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)]
pal.mouth = Fake(); pal.mouth.sound = lambda s: None
pal.talking = True
pal.show_picture = lambda *a: P.Pal.show_picture(pal, *a)
pal.hold_photo = lambda *a: None

convo = {}
print("take_photo ->", P.Pal.take_photo(pal, convo)[:120], "...")
print("  kept for the gallery:", type(convo["photo"][0]).__name__, "of", len(convo["photo"][0]), "text lines")
shot("p1-photo", 14)
print("show_qr_code ->", P.Pal.show_qr_code(pal, "https://www.ifixit.com/Guide/iPhone+12+Battery+Replacement/140588", "iPhone 12 battery guide"))
img = shot("p2-qr", 7)
found, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(np.asarray(img.resize((1280, 800), Image.NEAREST)), cv2.COLOR_RGB2BGR))
print("  QR on Kermit's screen reads:", found or "(nothing)")
keys(" ")
shot("p3-after-key", 5)
for bad in ("javascript:alert(1)", "https://exa mple.com/", "ftp://x.org/", "https://" + "a" * 500):
    print(f"show_qr_code({bad[:30]!r}) ->", P.Pal.show_qr_code(pal, bad, ""))
print(subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout.strip()[:200])
bridge.terminate(); bridge.wait()
subprocess.run(TM + ["kill-server"])
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
print("done")
