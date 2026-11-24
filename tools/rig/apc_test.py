# Can the Pi make the real MS-DOS Kermit 3.16 run a DOS program? Sends Kermit
# commands inside an APC escape sequence (ESC _ ... ESC \) for each setting of
# SET TERMINAL APC, and reports what came back and what the screen showed.
# Usage (on the Pi): python3 /tmp/rig/apc_test.py
import os, socket, subprocess, sys, time
from PIL import Image

def shot(name):
    subprocess.run(["xdotool", "mousemove", "799", "599"], env={"DISPLAY": ":99"})
    subprocess.run(["/tmp/rig/shot.sh", name])
    Image.open(f"/tmp/rig/{name}.png").convert("L").crop((80, 100, 720, 500)).save(f"/tmp/rig/{name}.png")

ini = open("/tmp/rig/MSKERMIT.INI", newline="").read()      # (CRLF: DOS Kermit needs it)
for setting in sys.argv[1:] or ["unchecked", "on", "off"]:
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True); time.sleep(1)
    os.makedirs("/tmp/rig/c", exist_ok=True)
    with open("/tmp/rig/c/HELLO.BAT", "w", newline="") as f:
        f.write("@echo off\r\necho HELLO FROM DOS > C:\\RAN.TXT\r\n")
    try: os.remove("/tmp/rig/c/RAN.TXT")
    except FileNotFoundError: pass
    server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 5555)); server.listen(1)
    with open("/tmp/rig/MSKERMIT.apc.INI", "w", newline="") as f:
        f.write(ini.replace("connect\r\n", f"set terminal apc {setting}\r\nconnect\r\n"))
    subprocess.Popen(["/tmp/rig/start.sh"], env=dict(os.environ, INI="/tmp/rig/MSKERMIT.apc.INI"))
    conn, _ = server.accept(); conn.settimeout(0.2); time.sleep(7)
    conn.sendall(b"\x1b[2J\x1b[HBefore the APC.\r\n")
    time.sleep(1)
    conn.sendall(b"\x1b_run hello\x1b\\")
    start, got = time.monotonic(), b""
    while time.monotonic() - start < 8:
        try: got += conn.recv(4096)
        except socket.timeout: pass
        if os.path.exists("/tmp/rig/c/RAN.TXT") and time.monotonic() - start > 3: break
    ran = os.path.exists("/tmp/rig/c/RAN.TXT")
    conn.sendall(b"After the APC: still a terminal.\r\n"); time.sleep(1.5)
    shot(f"apc-{setting}")
    print(f"apc {setting}: DOS program ran: {ran}; bytes from Kermit: {got!r}", flush=True)
    conn.close(); server.close()
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
