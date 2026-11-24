# Any menu program on the virtual Compaq with PILINK: the real MS-DOS Kermit
# and the real PILINK.COM in DOSBox, a private copy of the serial bridge and
# a private tmux server. Everything typed is typed at the "Compaq" itself
# (DOSBox's keyboard), so in text it goes through Kermit and in pictures
# through PILINK, as it will on the real machine. Nothing touches the
# lobby's shared screen, and PAL's socket points nowhere (no sound).
# Usage (on the Pi, after tools/rig/setup.sh):
#   python3 /tmp/rig/gfx_test.py "potato.py" "[('type', 'bunny\r', 20), ('shot', 'list', 0), ...]"
# Steps are (what, value, seconds to wait afterwards): type TEXT, key NAME
# (xdotool's names: Return, Up, space...), down NAME, up NAME, shot NAME
# (saved as /tmp/rig/NAME.png), wait.
import os, pty, select, socket, subprocess, sys, threading, time, tty
from PIL import Image

PROGRAM, STEPS = sys.argv[1], eval(sys.argv[2])
LIB, TM, X = "/tmp/rig/lib", ["tmux", "-L", "rigtest"], {"DISPLAY": ":99"}
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
for leftover in ("/tmp/rig/bridge.sock", "/tmp/rig/status", "/tmp/rig/terminal"):
    if os.path.exists(leftover):
        os.remove(leftover)
time.sleep(1)

server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 5555)); server.listen(1)
subprocess.Popen(["/tmp/rig/start.sh"])
server.settimeout(30)
kermit, _ = server.accept()
master, slave = pty.openpty()
tty.setraw(slave)

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

def xdo(*args):
    subprocess.run(["xdotool", *args], env=X)

def shot(name):
    xdo("mousemove", "799", "599")
    time.sleep(0.2)
    subprocess.run(["/tmp/rig/shot.sh", name])
    Image.open(f"/tmp/rig/{name}.png").convert("L").crop((80, 100, 720, 500)).save(f"/tmp/rig/{name}.png")

bridge = None
try:
    time.sleep(6)                              # Kermit starting
    env = dict(os.environ, COMPAQ_READY="1")
    bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({os.ttyname(slave)!r}, '9600').run()
"""], env=env)
    for _ in range(100):                       # (the bridge takes a moment to start listening)
        if os.path.exists("/tmp/rig/bridge.sock"):
            break
        time.sleep(0.2)
    subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                         "COMPAQ_BRIDGE=/tmp/rig/bridge.sock COMPAQ_RUNTIME=/tmp/rig PAL_SOCKET=/nonexistent/pal.sock "
                         f"DOOM_FRAMES=/tmp/rig/doom-frames python3 {LIB}/{PROGRAM}; echo; echo ENDED; sleep 600"])
    time.sleep(5)
    for what, value, wait in STEPS:
        if what == "type":
            for char in value:                 # (one at a time: Kermit at 9600 baud, a person typing)
                xdo("key", {"\r": "Return", " ": "space"}.get(char, char))
                time.sleep(0.08)
        elif what == "key":
            xdo("keydown", value); time.sleep(0.12); xdo("keyup", value)
        elif what == "down":
            xdo("keydown", value)
        elif what == "up":
            xdo("keyup", value)
        elif what == "shot":
            shot(value)
        time.sleep(wait)
    print(subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout.rstrip()[-900:])
finally:
    if bridge:
        bridge.terminate(); bridge.wait()
    subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
print("done")
