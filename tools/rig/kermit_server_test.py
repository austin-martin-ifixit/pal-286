# MS-DOS Kermit started for one file transfer and nothing else: the way
# PI.BAT runs it when the Compaq's terminal is PILINK. DOSBox starts
#   KERMIT -f SERVE.INI     (the cable's settings, then SERVER)
# and the Pi's C-Kermit sends a file to it, fetches one back, and says BYE,
# which should end MS-DOS Kermit and let the batch file carry on.
# Usage (on the Pi, after tools/rig/setup.sh):
#   python3 /tmp/rig/kermit_server_test.py ["KERMIT ... (the batch file's line)"]
import os, pty, select, shutil, socket, subprocess, sys, threading, time, tty

LINE = sys.argv[1] if len(sys.argv) > 1 else "KERMIT -f SERVE.INI"

C = "/tmp/rig/kc"
shutil.rmtree(C, ignore_errors=True)
os.makedirs(C)
os.makedirs(f"{C}/SUB")
shutil.copy(os.path.expanduser("~/build/msk316/files/MSK316.EXE"), f"{C}/KERMIT.EXE")
with open(f"{C}/SERVE.INI", "w", newline="\r\n") as f:
    f.write("set port com1\nset speed 9600\nset parity none\nset flow-control none\n"
            "set file collision rename\nserver\n")
with open(f"{C}/BACK.TXT", "w", newline="\r\n") as f:
    f.write("A file from the Compaq.\n")
with open(f"{C}/RUN.BAT", "w", newline="\r\n") as f:
    f.write(LINE.replace("|", "\n") + "\nECHO BATCH WENT ON > C:\\DONE.TXT\n")   # (| between lines)
conf = open("/tmp/rig/dosbox.conf").read().split("[autoexec]")[0]
with open("/tmp/rig/kc.conf", "w") as f:
    f.write(conf + f"[autoexec]\nmount c {C}\nc:\nRUN.BAT\n")
os.makedirs("/tmp/rig/kc-pi", exist_ok=True)
with open("/tmp/rig/kc-pi/hello.txt", "w") as f:
    f.write("A file from the Pi.\n")

subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
time.sleep(1)
server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 5555)); server.listen(1)
subprocess.run("pgrep -f 'Xvfb :99' >/dev/null || (Xvfb :99 -screen 0 800x600x24 >/dev/null 2>&1 &)", shell=True)
dosbox = subprocess.Popen(["dosbox", "-conf", "/tmp/rig/kc.conf"], env=dict(os.environ, DISPLAY=":99", SDL_AUDIODRIVER="dummy"),
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
server.settimeout(30)
cable, _ = server.accept()
master, slave = pty.openpty()
tty.setraw(slave)

def relay():
    while True:
        r, _, _ = select.select([master, cable], [], [])
        if master in r:
            cable.sendall(os.read(master, 4096))
        if cable in r:
            data = cable.recv(4096)
            if not data:
                return
            os.write(master, data)
threading.Thread(target=relay, daemon=True).start()
time.sleep(6)
settings = f"set carrier-watch off, set line {os.ttyname(slave)}, set speed 9600, set flow-control none, set parity none"
started = time.time()
result = subprocess.run(["kermit", "-Y", "-B", "-C", f"{settings}, send hello.txt, get BACK.TXT, bye, exit"],
                        cwd="/tmp/rig/kc-pi", capture_output=True, text=True, timeout=180)
print(f"C-Kermit: exit {result.returncode} after {time.time() - started:.1f} s")
time.sleep(4)
print("on the Compaq:", sorted(os.listdir(C)))
print("back on the Pi:", sorted(os.listdir("/tmp/rig/kc-pi")))
print("the batch file went on:", os.path.exists(f"{C}/DONE.TXT"))
subprocess.run(["/tmp/rig/shot.sh", "kc-end"])
dosbox.kill()
