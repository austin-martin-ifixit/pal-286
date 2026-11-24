# PILINK as the Compaq's whole terminal, end to end on the virtual Compaq:
# DOSBox runs PI.BAT (the real PILINK.COM, and the real MS-DOS Kermit for
# transfers) against a private copy of the serial bridge and a private tmux
# session. Checks, with screenshots in /tmp/rig:
#   - PILINK starts by itself, the bridge takes it up, and the session's
#     text arrives in the Compaq's own text mode (term-text.png);
#   - keys typed at the "Compaq" reach the session (term-typed.png);
#   - a picture shows and a key brings the text back (term-picture.png);
#   - PAL's eye scene in real dots (term-pal.png), a quiz board in dots
#     (term-quiz.png), and a beep on the Compaq's own speaker;
#   - a file goes to the Compaq and one comes back, through Kermit as a
#     server, and PILINK comes back by itself afterwards (term-after.png);
#   - the Pi asks whether files are on the Compaq's disk and has DOS run a
#     batch file, then dos.py plays a pretend Doom, and PI comes back by
#     itself each time (term-dos.png).
# Nothing touches the lobby's shared screen. Usage (on the Pi, after
# tools/rig/setup.sh and tools/build-pilink.sh):
#   python3 /tmp/rig/terminal_test.py [boot image]
# With a boot image (make-disks.sh's boot-freedos-pi.img, copied to the Pi)
# the virtual Compaq starts from it, as the real one would from the GoTEK,
# instead of running PI.BAT from a folder.
import base64, io, json, os, pty, select, shutil, socket, subprocess, sys, threading, time, tty
from PIL import Image, ImageDraw

LIB, TM, X = "/tmp/rig/lib", ["tmux", "-L", "rigterm"], {"DISPLAY": ":99"}
BOOT = sys.argv[1] if len(sys.argv) > 1 else None
C, PI_FILES = "/tmp/rig/tc", "/tmp/rig/tc-pi"
sys.path.insert(0, "/tmp/rig")
import build_disks  # noqa: E402

for folder in (C, PI_FILES):
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
shutil.copy(os.path.expanduser("~/build/msk316/files/MSK316.EXE"), f"{C}/KERMIT.EXE")
shutil.copy("/tmp/rig/c/PILINK.COM", f"{C}/PILINK.COM")
for name, text in (("SERVE.INI", open("/tmp/rig/SERVE.INI").read()), ("PI.BAT", build_disks.pi_bat("9600")),
                   ("BACK.TXT", "Written on the Compaq.\n")):
    with open(f"{C}/{name}", "w", newline="\r\n") as f:
        f.write(text.replace("\r", "") + "\n")
with open(f"{PI_FILES}/letter.txt", "w") as f:
    f.write("Sent from the Pi.\n")
conf = open("/tmp/rig/dosbox.conf").read().split("[autoexec]")[0]
with open("/tmp/rig/tc.conf", "w") as f:
    if BOOT:
        shutil.copy(BOOT, f"{C}/BOOT.IMG")
        subprocess.run(["mcopy", "-i", f"{C}/BOOT.IMG", f"{C}/BACK.TXT", "::/BACK.TXT"], check=True,
                       env=dict(os.environ, MTOOLS_SKIP_CHECK="1"))
        f.write(conf + f"[autoexec]\nmount c {C}\nimgmount a {C}/BOOT.IMG -t floppy\nboot -l a\n")
    else:
        f.write(conf + f"[autoexec]\nmount c {C}\nc:\nPI\n")


def on_compaq(name):
    """Is the file on the Compaq's disk?"""
    if not BOOT:
        return os.path.exists(f"{C}/{name}")
    listing = subprocess.run(["mdir", "-b", "-i", f"{C}/BOOT.IMG", "::"], capture_output=True, text=True,
                             env=dict(os.environ, MTOOLS_SKIP_CHECK="1")).stdout
    return f"::/{name}" in listing
subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
for leftover in ("/tmp/rig/bridge.sock", "/tmp/rig/status", "/tmp/rig/terminal", "/tmp/rig/pilink"):
    if os.path.exists(leftover):
        os.remove(leftover)
time.sleep(1)

server = socket.socket(); server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(("127.0.0.1", 5555)); server.listen(1)
subprocess.run("pgrep -f 'Xvfb :99' >/dev/null || (Xvfb :99 -screen 0 800x600x24 >/dev/null 2>&1 &)", shell=True)
dosbox = subprocess.Popen(["dosbox", "-conf", "/tmp/rig/tc.conf"], env=dict(os.environ, **X, SDL_AUDIODRIVER="dummy"),
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

failures = 0


def check(what, good, detail=""):
    global failures
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  {detail}"), flush=True)
    failures += not good


def shot(name):
    subprocess.run(["xdotool", "mousemove", "799", "599"], env=X)
    time.sleep(0.2)
    subprocess.run(["/tmp/rig/shot.sh", name])
    image = Image.open(f"/tmp/rig/{name}.png").convert("L").crop((80, 100, 720, 500))
    image.save(f"/tmp/rig/{name}.png")
    return image


def lit(image):
    """How much of the screen is lit (0 to 1)."""
    return sum(1 for v in image.getdata() if v > 100) / (image.width * image.height)


def ask(request, wait=True):
    conn = socket.socket(socket.AF_UNIX)
    conn.connect("/tmp/rig/bridge.sock")
    conn.sendall((json.dumps(request) + "\n").encode())
    if not wait:
        return conn
    conn.settimeout(200)
    answer = json.loads(conn.makefile().readline() or "{}")
    conn.close()
    return answer


def status(name):
    try:
        return open(f"/tmp/rig/{name}").read().strip()
    except OSError:
        return ""


def wait_for(what, seconds):
    end = time.time() + seconds
    while time.time() < end and not what():
        time.sleep(0.5)
    return what()


bridge = None
try:
    bridge = subprocess.Popen([sys.executable, "-c", f"""
import sys; sys.path.insert(0, {LIB!r})
import serial_bridge as b
b.TMUX = {TM!r}; b.SOCKET = '/tmp/rig/bridge.sock'; b.STATUS = '/tmp/rig/status'
b.Bridge({os.ttyname(slave)!r}, '9600').run()
"""], env=dict(os.environ, COMPAQ_READY="1"))
    wait_for(lambda: os.path.exists("/tmp/rig/bridge.sock"), 20)
    subprocess.run(TM + ["new-session", "-d", "-s", "compaq", "-x", "80", "-y", "24",
                         "printf '\\033[1mPILINK TERMINAL TEST\\033[0m  (typed keys echo below)\\n'; "
                         "for i in $(seq 1 18); do echo \"line $i of the Pi's text, drawn by PILINK\"; done; "
                         "stty -icanon -echo; cat; sleep 600"])
    up = wait_for(lambda: "the whole terminal" in status("pilink"), 90 if BOOT else 40)
    check("PILINK started by PI.BAT and was taken up as the terminal", up, status("pilink"))
    time.sleep(3)
    check("the bridge remembers the Compaq's terminal", status("terminal") == "pilink", status("terminal"))
    check("the session's text on the Compaq", lit(shot("term-text")) > 0.02)
    for char in "hello":
        subprocess.run(["xdotool", "key", char], env=X)
        time.sleep(0.1)
    time.sleep(2)
    pane = subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
    check("keys at the Compaq reach the session", "hello" in pane, pane[-200:])
    shot("term-typed")

    picture = Image.new("L", (320, 200), 0)
    ImageDraw.Draw(picture).ellipse((60, 20, 260, 180), fill=255)
    buffer = io.BytesIO(); picture.save(buffer, "PNG")
    conn = ask({"op": "picture", "image": base64.b64encode(buffer.getvalue()).decode(), "caption": "A test"},
               wait=False)
    conn.settimeout(30)
    answer = json.loads(conn.makefile().readline() or "{}")
    check("a picture through the terminal PILINK, no handover", answer.get("showing") not in (None, False), answer)
    time.sleep(3)
    check("the picture on the Compaq", lit(shot("term-picture")) > 0.15)
    subprocess.run(["xdotool", "key", "space"], env=X)
    done = json.loads(conn.makefile().readline() or "{}")
    check("a key takes the picture down", done.get("done") == "a key", done)
    time.sleep(3)
    check("and the text comes back", 0.02 < lit(shot("term-back")) < 0.15)

    def pal(**request):
        return ask(dict(op="pal", **request))
    answer = pal(action="begin", name="PAL 286", requested=True)
    check("PAL takes the screen", answer.get("shown"), answer)
    pal(action="say", who="human", text="Hey PAL, what's the weather like?", cps=200)
    pal(action="say", who="pal", text="Sunny, and a fine day for a 1987 computer.", cps=60)
    pal(action="status", text="listening", blink=True)
    time.sleep(4)
    image = shot("term-pal")
    centre = image.crop((180, 40, 400, 220))
    check("PAL's eye drawn (term-pal.png shows whether in dots)", lit(centre) > 0.15, lit(centre))
    answer = pal(action="beep", notes=[[990, 0.2]])
    check("a beep on the Compaq's own speaker", answer.get("beeped") is True, answer)
    pal(action="end")
    pal(action="begin", name="PAL 286", canvas=True, requested=True)
    rows = ["", "LOBBY QUIZ (as text)"] + [""] * 20
    pal(action="frame", lines=rows, board={"kind": "quiz", "question": "Which company made this computer?",
                                           "choices": ["IBM", "Compaq", "Apple"], "number": 1, "total": 3,
                                           "score": 0, "topic": "Old computers"})
    time.sleep(4)
    title = shot("term-quiz").crop((240, 0, 400, 40))               # the big LOBBY QUIZ
    check("a quiz board in dots (big lettering, term-quiz.png)", lit(title) > 0.12, lit(title))
    pal(action="end")
    time.sleep(3)
    check("PAL hands the text back", 0.02 < lit(shot("term-after-pal")) < 0.15)

    def gone_and_back():
        os.remove("/tmp/rig/pilink")      # (the bridge writes it again when PILINK is back up)
    gone_and_back()
    started = time.time()
    answer = ask({"op": "send", "path": f"{PI_FILES}/letter.txt"})
    check(f"a file to the Compaq ({time.time() - started:.1f} s): {answer.get('message')}",
          answer.get("ok") and on_compaq("LETTER.TXT"), answer)
    back = wait_for(lambda: "the whole terminal" in status("pilink"), 30)
    check("PILINK came back by itself after the transfer", back and status("terminal") == "pilink")
    time.sleep(2)
    answer = ask({"op": "receive", "dir": PI_FILES})
    check("a receive asks which files", answer.get("need") == "files", answer)
    gone_and_back()
    answer = ask({"op": "receive", "dir": PI_FILES, "files": "BACK.TXT"})
    check(f"a file from the Compaq: {answer.get('message')}", answer.get("ok")
          and os.path.exists(f"{PI_FILES}/back.txt"), (answer, os.listdir(PI_FILES)))
    time.sleep(1)
    back = wait_for(lambda: "the whole terminal" in status("pilink"), 30)
    time.sleep(4)
    check("and again, with the text on the screen", back and lit(shot("term-after")) > 0.02)

    # A DOS program the Pi starts (lib/dos.py): PILINK 3 writes C:\PI\PIRUN.BAT,
    # DOS runs it, and its last line starts PI again from C:\PI (where the
    # Kermit disk's INSTALL.BAT puts everything on the real Compaq).
    os.makedirs(f"{C}/PI", exist_ok=True)
    for name in ("PILINK.COM", "PI.BAT", "KERMIT.EXE", "SERVE.INI"):
        shutil.copy(f"{C}/{name}", f"{C}/PI/{name}")
    answer = ask({"op": "there", "name": "C:\\PI\\PILINK.COM"})
    check("a file on the Compaq's disk, asked through the bridge", answer.get("there") is True, answer)
    answer = ask({"op": "there", "name": "C:\\DOOM\\DOOM4.WAD"})
    check("and one that isn't there", answer.get("ok") and answer.get("there") is False, answer)
    conn = ask({"op": "run", "title": "a test", "batch": "ECHO OFF\nECHO RAN> C:\\RAN.TXT\nC:\nCD \\PI\nPI\n"},
               wait=False)
    conn.settimeout(90)
    answers = conn.makefile()
    first = json.loads(answers.readline() or "{}")
    check("a DOS program through the bridge: PILINK goes to DOS", first.get("ok"), first)
    later = json.loads(answers.readline() or "{}")
    conn.close()
    check("the program ran, and the bridge says PI is back", later.get("back") and on_compaq("RAN.TXT"), later)
    # The menu's way, as Doom does it: a pretend Doom already on the disk.
    os.makedirs(f"{C}/DOOM", exist_ok=True)
    with open(f"{C}/DOOM/DOOM4.WAD", "w") as f:
        f.write("not really Doom\n")
    with open(f"{C}/DOOM/D286CBW.BAT", "w", newline="\r\n") as f:   # (a batch, so it ends by starting PI)
        f.write("ECHO PLAYED> C:\\PLAYED.TXT\nC:\nCD \\PI\nPI\n")
    rescan = ask({"op": "run", "title": "DOSBox catching up", "batch": "RESCAN\nC:\nCD \\PI\nPI\n"}, wait=False)
    rescan.settimeout(90)                  # (DOSBox doesn't see files put in its C: from outside until then)
    rescans = rescan.makefile()
    rescans.readline(), rescans.readline()
    rescan.close()
    time.sleep(3)
    played = subprocess.run([sys.executable, "-I", f"{LIB}/dos.py", "play", "doom"], input="\n", text=True,
                            capture_output=True, timeout=120, env=dict(os.environ, COMPAQ_BRIDGE="/tmp/rig/bridge.sock"))
    check("dos.py play doom: Doom8088 on the Compaq, and back", played.returncode == 0 and on_compaq("PLAYED.TXT"),
          (played.returncode, played.stdout[-300:], played.stderr[-300:]))
    back = wait_for(lambda: "the whole terminal" in status("pilink"), 30)
    time.sleep(4)
    check("the text on the screen again after DOS", back and lit(shot("term-dos")) > 0.02)
finally:
    if bridge:
        bridge.terminate(); bridge.wait()
    subprocess.run(TM + ["kill-server"], stderr=subprocess.DEVNULL)
    dosbox.kill()
print("ALL OK" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)
