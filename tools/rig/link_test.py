# The whole picture path on the virtual Compaq: a private copy of the serial
# bridge, the real MS-DOS Kermit in DOSBox, and the real PILINK.COM, which
# the bridge asks Kermit to run. A program asks for two still pictures and a
# moving one (link_demo.py); keys are pressed at the "Compaq" itself.
# Nothing touches the lobby's shared screen.
# Usage (on the Pi, after tools/rig/setup.sh): python3 /tmp/rig/link_test.py [pilink|kermit] [layout]
# SPEED=38400 in the environment runs Kermit and the bridge at that speed
# instead of 9600 (what data/cable-speed would set).
import os, pty, select, signal, socket, subprocess, sys, threading, time, tty
from PIL import Image

MODE = sys.argv[1] if len(sys.argv) > 1 else "pilink"
LAYOUT = sys.argv[2] if len(sys.argv) > 2 else "320x200"
SPEED = os.environ.get("SPEED", "9600")
LIB, TM, X = "/tmp/rig/lib", ["tmux", "-L", "rigtest"], {"DISPLAY": ":99"}
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
for leftover in ("/tmp/rig/bridge.sock", "/tmp/rig/status", "/tmp/rig/terminal"):
    if os.path.exists(leftover):
        os.remove(leftover)
time.sleep(1)

server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 5555)); server.listen(1)
with open("/tmp/rig/MSKERMIT.INI", newline="") as f:       # (CRLF: DOS Kermit needs it)
    settings = f.read().replace("9600", SPEED)
with open("/tmp/rig/MSKERMIT.speed.INI", "w", newline="") as f:
    f.write(settings)
subprocess.Popen(["/tmp/rig/start.sh"], env=dict(os.environ, INI="/tmp/rig/MSKERMIT.speed.INI"))
server.settimeout(30)
kermit, _ = server.accept()
master, slave = pty.openpty()
tty.setraw(slave)
device = os.ttyname(slave)

def relay():                                   # the cable (DOSBox's serial chip sets the pace)
    while True:
        r, _, _ = select.select([master, kermit], [], [])
        if master in r:
            kermit.sendall(os.read(master, 4096))
        if kermit in r:
            data = kermit.recv(4096)
            if not data:
                return
            os.write(master, data)
threading.Thread(target=relay, daemon=True).start()

def shot(name):
    subprocess.run(["xdotool", "mousemove", "799", "599"], env=X)
    time.sleep(0.3)
    subprocess.run(["/tmp/rig/shot.sh", name])
    Image.open(f"/tmp/rig/{name}.png").convert("L").crop((80, 100, 720, 500)).save(f"/tmp/rig/{name}.png")

def press(key):                                # at the Compaq's own keyboard
    subprocess.run(["xdotool", "keydown", key], env=X)
    time.sleep(0.15)
    subprocess.run(["xdotool", "keyup", key], env=X)

def screen():
    return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout

def wait_for(text, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if text in screen():
            return True
        time.sleep(0.2)
    return False

bridge = None
try:
    subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                         f"COMPAQ_BRIDGE=/tmp/rig/bridge.sock python3 {LIB}/../link_demo.py {LAYOUT}; sleep 600"])
    time.sleep(6)                              # Kermit starting
    env = dict(os.environ, COMPAQ_READY="1", COMPAQ_PILINK="on" if MODE == "pilink" else "off")
    bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({device!r}, {SPEED!r}).run()
"""], env=env)
    start = time.monotonic()
    ok = wait_for("photo: painting", 40)
    print(f"photo asked for and on its way after {time.monotonic() - start:.1f} s: {ok}", flush=True)
    time.sleep(14 if MODE == "kermit" else 4)
    shot("link-photo")
    press("space")
    ok = wait_for("qr: painting", 40)
    time.sleep(6 if MODE == "kermit" else 2.5)
    shot("link-qr")
    press("space")
    if wait_for("canvas:", 30):
        time.sleep(3)
        shot("link-canvas")
        press("a")
        wait_for("END", 20)
    time.sleep(3)                              # Kermit again, and the text repainted
    shot("link-text-again")
    print(screen().rstrip()[-700:], flush=True)
finally:
    if bridge:
        bridge.terminate(); bridge.wait()
    subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
print("done")
