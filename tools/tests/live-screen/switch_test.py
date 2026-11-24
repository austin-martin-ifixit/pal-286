# Switching programs by voice. Runs as root on the Pi (the TV stands in for the Compaq).
import fcntl, os, pty, struct, subprocess, termios, threading, time
TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
def screen(): return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
def tv(keys):        # typing on the TV's own keyboard (the lobby)
    fd = os.open("/dev/tty7", os.O_RDWR | os.O_NOCTTY)
    for b in keys: fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
    os.close(fd)
def voice(program):
    r = subprocess.run(["sudo", "-u", "pal", "sudo", "-n", "-u", "desk", "/opt/compaq/lib/voice-open", program],
                       capture_output=True, text=True)
    return r.stdout.strip() or r.stderr.strip()
def wait(text, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if text in screen(): return True
        time.sleep(0.3)
    return False
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session menu"]); time.sleep(2)
tv(b"@40-games/10-adventures\r"); time.sleep(2); tv(b"1\r"); time.sleep(1.5); tv(b"\r")
print("1. Zork running (started from the lobby keyboard):", wait("West of House", 12))
tv(b"open mailbox\r"); time.sleep(1)
print("2. PAL, straight after typing in Zork:", voice("guides"))
print("   repair guides on screen:", wait("REPAIR GUIDES") or wait("iFixit", 3))
# A browser user types: a tmux client that isn't the bridge's.
pid, fd = pty.fork()
if pid == 0:
    fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    os.execvp("sudo", ["sudo", "-u", "desk", "env", "TERM=vt102", "tmux", "-L", "compaq", "attach", "-t", "compaq"])
threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
time.sleep(2); os.write(fd, b"x"); time.sleep(1); os.write(fd, b"\x7f"); time.sleep(1)
print("3. PAL, while someone types in a browser:", voice("weather"))
os.kill(pid, 15)
print("4. PAL, main menu:", voice("main-menu") if False else "(skipped: browser typed <30 s ago)")
time.sleep(31)
print("5. PAL, 30 s after the browser stopped:", voice("main-menu"))
print("   main menu on screen:", wait("Choose a number"))
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
