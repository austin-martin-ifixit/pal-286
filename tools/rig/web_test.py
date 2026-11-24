# The web page's picture overlay, end to end: a private web server (127.0.0.1:8099,
# a throwaway password) on a private copy of the shared session, with the
# virtual Compaq: real MS-DOS Kermit in
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



import hashlib, secrets
TEST = "/tmp/rig/webtest"
os.makedirs(TEST, exist_ok=True)
os.chmod(TEST, 0o700)
password = secrets.token_urlsafe(12)
salt = os.urandom(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000).hex()
with open(f"{TEST}/web.env", "w") as f:
    f.write(f"OFFICE_PASSWORD=pbkdf2_sha256${100000}${salt.hex()}${digest}\n")
with open(f"{TEST}/password", "w") as f:       # for the browser check; deleted afterwards
    f.write(password)
os.chmod(f"{TEST}/password", 0o600)

subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                     f"COMPAQ_BRIDGE=/tmp/rig/bridge.sock python3 {LIB}/guides.py 140588; sleep 900"])
time.sleep(6)
bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({device!r}, '9600').run()
"""])
web = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, '/tmp/rig/web')
import server as w
w.TMUX = {TM!r}; w.PICTURE = '/tmp/rig/picture'; w.STATUS_FILE = '/tmp/rig/status'
w.VIEWERS_FILE = '/tmp/rig/viewers'
sys.argv = ['server.py', '--port', '8099', '--bind', '127.0.0.1', '--password-file', '{TEST}/web.env']
w.main()
"""])
print("ready", flush=True)
try:
    time.sleep(int(os.environ.get("RIG_SECONDS", "900")))
finally:
    web.terminate(); bridge.terminate()
    subprocess.run(TM + ["kill-server"])
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
    subprocess.run(["rm", "-rf", TEST])
    print("done", flush=True)
