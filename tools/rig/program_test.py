# A program, end to end on the virtual Compaq: real MS-DOS Kermit in
# DOSBox, a private copy of the serial bridge, a private tmux server. Keys are
# sent as the Compaq would send them (into the cable). Nothing touches the
# lobby's shared screen.
import os, pty, signal, socket, subprocess, sys, threading, time, tty
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


PROGRAM, STEPS = sys.argv[1], eval(sys.argv[2])
if os.path.exists("/tmp/rig/terminal"):          # (a PI.BAT test's: this one is Kermit's)
    os.remove("/tmp/rig/terminal")
open('/tmp/rig/potato-status', 'w').write('connected\n')     # [(keys, shot name, seconds), ...]
subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                     f"COMPAQ_BRIDGE=/tmp/rig/bridge.sock PAL_SOCKET=/nonexistent/pal.sock COMPAQ_STATUS=/tmp/rig/potato-status python3 {LIB}/{PROGRAM}; sleep 600"])
time.sleep(6)                                  # Kermit starting
bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({device!r}, '9600').run()
"""])
time.sleep(4)
for typed, name, wait in STEPS:
    if typed:
        keys(typed)
    img = shot(name, wait)
    if "qr" in name:
        found, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.cvtColor(np.asarray(img.resize((1280, 800), Image.NEAREST)), cv2.COLOR_RGB2BGR))
        print(f"{name}: QR reads", found or "(nothing)", flush=True)
print(subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout[-900:])
bridge.terminate(); bridge.wait()
subprocess.run(TM + ["kill-server"])
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
print("done")
